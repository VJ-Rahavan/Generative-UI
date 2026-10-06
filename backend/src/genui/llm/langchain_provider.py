"""LLMProvider backed by a LangChain chat model (ChatGroq by default).

The agent speaks OpenAI-style message dicts (which is also what we persist). This module
converts them to LangChain messages, streams `AIMessageChunk`s from the model and assembles
the final `Completion`. Swapping provider = returning a different `BaseChatModel` from
`build_chat_model`.
"""

import json
import logging
from collections.abc import AsyncIterator
from typing import Any

import groq
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    BaseMessage,
    HumanMessage,
    InvalidToolCall,
    SystemMessage,
    ToolMessage,
)
from langchain_core.messages import (
    ToolCall as LCToolCall,
)

from genui.core.config import Settings
from genui.llm.base import (
    ChatMessage,
    Completion,
    LLMError,
    StreamItem,
    TextDelta,
    ToolCall,
    ToolSpec,
)

logger = logging.getLogger(__name__)

# Models that accept the `reasoning_effort` parameter.
_REASONING_MODEL_PREFIXES = ("openai/gpt-oss",)


def build_chat_model(settings: Settings) -> BaseChatModel | None:
    """Create the LangChain chat model from settings (None if no API key is configured)."""
    if not settings.llm_configured:
        return None
    from langchain_groq import ChatGroq

    extra: dict[str, Any] = {}
    if settings.llm_reasoning_effort and settings.groq_model.startswith(_REASONING_MODEL_PREFIXES):
        extra["reasoning_effort"] = settings.llm_reasoning_effort
    return ChatGroq(
        model=settings.groq_model,
        api_key=settings.groq_api_key,
        temperature=settings.llm_temperature,
        max_tokens=settings.llm_max_tokens,
        timeout=settings.llm_timeout_seconds,
        # Retries are done by the agent so it can tell the user what's happening.
        max_retries=0,
        **extra,
    )


class LangChainProvider:
    def __init__(self, chat_model: BaseChatModel | None, *, model_name: str) -> None:
        self._chat_model = chat_model
        self._model_name = model_name

    @property
    def model(self) -> str:
        return self._model_name

    async def stream(
        self, messages: list[ChatMessage], tools: list[ToolSpec] | None = None
    ) -> AsyncIterator[StreamItem]:
        if self._chat_model is None:
            raise LLMError("GROQ_API_KEY is not configured on the server.", code="not_configured")

        runnable = (
            self._chat_model.bind_tools(tools, tool_choice="auto") if tools else self._chat_model
        )
        full: AIMessageChunk | None = None
        try:
            async for chunk in runnable.astream(to_langchain_messages(messages)):
                if not isinstance(chunk, AIMessageChunk):
                    continue
                # Chunks merge with `+`; tool-call fragments are joined by index.
                full = chunk if full is None else full + chunk
                if text := _text(chunk.content):
                    yield TextDelta(text)
        except groq.APIStatusError as exc:
            raise _to_llm_error(exc) from exc
        except groq.APIConnectionError as exc:  # includes timeouts
            raise LLMError(f"Could not reach Groq: {exc}", code="connection_error") from exc

        yield _to_completion(full)

    async def aclose(self) -> None:
        """ChatGroq manages its own HTTP clients; nothing to release."""


# --------------------------------------------------------------------------- conversion


def to_langchain_messages(messages: list[ChatMessage]) -> list[BaseMessage]:
    """OpenAI-style dicts (as stored in the DB) → LangChain message objects."""
    converted: list[BaseMessage] = []
    for message in messages:
        role = message.get("role")
        content = message.get("content") or ""
        if role == "system":
            converted.append(SystemMessage(content=content))
        elif role == "user":
            converted.append(HumanMessage(content=content))
        elif role == "assistant":
            tool_calls: list[LCToolCall] = []
            invalid: list[InvalidToolCall] = []
            for call in message.get("tool_calls") or []:
                fn = call["function"]
                raw = fn.get("arguments") or "{}"
                try:
                    args = json.loads(raw)
                    if not isinstance(args, dict):
                        raise ValueError("arguments must be an object")
                    tool_calls.append(
                        LCToolCall(name=fn["name"], args=args, id=call["id"], type="tool_call")
                    )
                except ValueError as exc:  # JSONDecodeError is a ValueError
                    invalid.append(
                        InvalidToolCall(
                            name=fn["name"],
                            args=raw,
                            id=call["id"],
                            error=str(exc),
                            type="invalid_tool_call",
                        )  # fmt: skip
                    )
            converted.append(
                AIMessage(content=content, tool_calls=tool_calls, invalid_tool_calls=invalid)
            )
        elif role == "tool":
            converted.append(ToolMessage(content=content, tool_call_id=message["tool_call_id"]))
        else:
            raise ValueError(f"Unsupported message role: {role!r}")
    return converted


def _text(content: str | list[Any]) -> str:
    if isinstance(content, str):
        return content
    return "".join(
        block.get("text", "") if isinstance(block, dict) else str(block)
        for block in content
        if not isinstance(block, dict) or block.get("type") == "text"
    )


def _to_completion(message: AIMessageChunk | None) -> Completion:
    if message is None:
        return Completion(text="")
    calls = [
        ToolCall(id=tc.get("id") or f"call_{i}", name=tc["name"], arguments=json.dumps(tc["args"]))
        for i, tc in enumerate(message.tool_calls)
    ]
    # Malformed arguments: pass the raw string through so validation can report the problem.
    calls += [
        ToolCall(id=tc.get("id") or f"invalid_{i}", name=tc.get("name") or "",
                 arguments=tc.get("args") or "{}")
        for i, tc in enumerate(message.invalid_tool_calls)
        if tc.get("name")
    ]  # fmt: skip
    usage = dict(message.usage_metadata) if message.usage_metadata else None
    if usage:
        logger.debug("llm usage: %s", usage)
    return Completion(
        text=_text(message.content),
        tool_calls=calls,
        finish_reason=message.response_metadata.get("finish_reason"),
        usage=usage,
    )


def _to_llm_error(exc: groq.APIStatusError) -> LLMError:
    code: str | None = None
    message = str(exc)
    body = exc.body
    if isinstance(body, dict):
        err = body.get("error", body)
        if isinstance(err, dict):
            code = err.get("code") or err.get("type")
            message = err.get("message") or message
    if exc.status_code == 429:
        code = code or "rate_limited"
    retry_after: float | None = None
    if header := exc.response.headers.get("retry-after"):
        try:
            retry_after = float(header)
        except ValueError:
            retry_after = None
    return LLMError(message, code=code, status=exc.status_code, retry_after=retry_after)
