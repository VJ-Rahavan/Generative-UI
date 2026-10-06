"""Tool registry built on LangChain tools.

Domain tools are plain typed async functions:

    registry = ToolRegistry()

    @registry.tool(label="Searching exercises")
    async def search_exercises(args: SearchArgs, ctx: ToolContext) -> dict: ...

The decorator wraps each one in a LangChain `StructuredTool` (the args model becomes its
`args_schema`, the docstring its description). Any other LangChain `BaseTool` — e.g. from
`langchain-community` — can be added with `registry.register(tool)`.

The per-request `ToolContext` (user id, DB sessions) is passed through LangChain's
`RunnableConfig`, so it never appears in the schema the LLM sees.
"""

import inspect
import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, get_type_hints

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool, StructuredTool
from langchain_core.utils.function_calling import convert_to_openai_tool
from pydantic import BaseModel, ValidationError

from genui.core.schema_utils import format_validation_error
from genui.db.session import SessionFactory

logger = logging.getLogger(__name__)

TOOL_CONTEXT_KEY = "genui_tool_context"


class ToolError(Exception):
    """Expected, user-facing failure (e.g. 'exercise not found'). Message is shown to the LLM."""


@dataclass(frozen=True, slots=True)
class ToolContext:
    user_id: str
    session_factory: SessionFactory


@dataclass(slots=True)
class ToolResult:
    ok: bool
    data: Any = None
    error: str | None = None

    def to_llm(self) -> dict[str, Any]:
        return {"ok": True, "data": self.data} if self.ok else {"ok": False, "error": self.error}


ToolFunc = Callable[[Any, ToolContext], Awaitable[Any]]


@dataclass(frozen=True, slots=True)
class Tool:
    """A registered LangChain tool plus UI metadata."""

    lc_tool: BaseTool
    label: str

    @property
    def name(self) -> str:
        return self.lc_tool.name

    @property
    def description(self) -> str:
        return self.lc_tool.description

    def spec(self) -> dict[str, Any]:
        """OpenAI-format function spec, as sent to the chat model."""
        return convert_to_openai_tool(self.lc_tool)


def _with_context(func: ToolFunc, args_model: type[BaseModel]) -> Callable[..., Awaitable[Any]]:
    """Adapt `func(args, ctx)` to LangChain's kwargs-based call, reading ctx from the config."""

    async def run(config: RunnableConfig, **kwargs: Any) -> Any:
        ctx = (config.get("configurable") or {}).get(TOOL_CONTEXT_KEY)
        if not isinstance(ctx, ToolContext):
            raise ToolError("Tool context is missing.")
        return await func(args_model.model_validate(kwargs), ctx)

    return run


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def tool(
        self, *, name: str | None = None, label: str | None = None
    ) -> Callable[[ToolFunc], ToolFunc]:
        def decorator(func: ToolFunc) -> ToolFunc:
            params = list(inspect.signature(func).parameters)
            args_model = get_type_hints(func).get(params[0]) if params else None
            if not (isinstance(args_model, type) and issubclass(args_model, BaseModel)):
                raise TypeError(f"{func.__name__}: first parameter must be a Pydantic model")
            tool_name = name or func.__name__
            lc_tool = StructuredTool.from_function(
                coroutine=_with_context(func, args_model),
                name=tool_name,
                description=inspect.getdoc(func) or tool_name,
                args_schema=args_model,
            )
            self.register(lc_tool, label=label)
            return func

        return decorator

    def register(self, lc_tool: BaseTool, *, label: str | None = None) -> None:
        """Register any LangChain tool (custom or from the LangChain ecosystem)."""
        if lc_tool.name in self._tools:
            raise ValueError(f"Tool '{lc_tool.name}' is already registered")
        self._tools[lc_tool.name] = Tool(
            lc_tool=lc_tool, label=label or lc_tool.name.replace("_", " ").capitalize()
        )

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def label(self, name: str) -> str:
        tool = self._tools.get(name)
        return tool.label if tool else name

    @property
    def tools(self) -> list[Tool]:
        return list(self._tools.values())

    def specs(self) -> list[dict[str, Any]]:
        return [t.spec() for t in self._tools.values()]

    async def execute(self, name: str, raw_arguments: str, ctx: ToolContext) -> ToolResult:
        tool = self._tools.get(name)
        if tool is None:
            return ToolResult(
                ok=False, error=f"Unknown tool '{name}'. Available: {', '.join(self._tools)}"
            )
        try:
            raw = json.loads(raw_arguments or "{}")
        except json.JSONDecodeError as exc:
            return ToolResult(ok=False, error=f"Arguments are not valid JSON: {exc}")
        try:
            data = await tool.lc_tool.ainvoke(
                raw, config={"configurable": {TOOL_CONTEXT_KEY: ctx}, "run_name": name}
            )
        except ValidationError as exc:
            return ToolResult(ok=False, error="Invalid arguments:\n" + format_validation_error(exc))
        except ToolError as exc:
            return ToolResult(ok=False, error=str(exc))
        except Exception:
            logger.exception("tool %s failed", name)
            return ToolResult(ok=False, error=f"Internal error while running '{name}'.")
        return ToolResult(ok=True, data=data)
