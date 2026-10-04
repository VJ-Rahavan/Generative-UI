"""Tool registry: typed async functions the LLM can call to read/write real data.

    registry = ToolRegistry()

    @registry.tool(label="Searching exercises")
    async def search_exercises(args: SearchArgs, ctx: ToolContext) -> dict: ...

The first parameter's Pydantic model defines the JSON schema sent to the LLM and validates
the arguments it returns. The docstring becomes the tool description.
"""

import inspect
import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, get_type_hints

from pydantic import BaseModel, ValidationError

from genui.core.schema_utils import format_validation_error, llm_json_schema
from genui.db.session import SessionFactory

logger = logging.getLogger(__name__)


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
    name: str
    description: str
    label: str
    args_model: type[BaseModel]
    func: ToolFunc

    def spec(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": llm_json_schema(self.args_model),
            },
        }


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
            self.register(
                Tool(
                    name=tool_name,
                    description=inspect.getdoc(func) or tool_name,
                    label=label or tool_name.replace("_", " ").capitalize(),
                    args_model=args_model,
                    func=func,
                )
            )
            return func

        return decorator

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"Tool '{tool.name}' is already registered")
        self._tools[tool.name] = tool

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
            args = tool.args_model.model_validate(raw)
        except ValidationError as exc:
            return ToolResult(ok=False, error="Invalid arguments:\n" + format_validation_error(exc))
        try:
            return ToolResult(ok=True, data=await tool.func(args, ctx))
        except ToolError as exc:
            return ToolResult(ok=False, error=str(exc))
        except Exception:
            logger.exception("tool %s failed", name)
            return ToolResult(ok=False, error=f"Internal error while running '{name}'.")
