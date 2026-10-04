"""Groq implementation of LLMProvider (streaming chat completions with tool calling)."""

import logging
from collections.abc import AsyncIterator
from typing import Any

import groq
from groq import AsyncGroq

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


class GroqProvider:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client: AsyncGroq | None = None
        if settings.groq_api_key and settings.groq_api_key.get_secret_value():
            self._client = AsyncGroq(
                api_key=settings.groq_api_key.get_secret_value(),
                timeout=settings.llm_timeout_seconds,
                # Retries are done by the agent so it can tell the user what's happening.
                max_retries=0,
            )

    @property
    def model(self) -> str:
        return self._settings.groq_model

    async def stream(
        self, messages: list[ChatMessage], tools: list[ToolSpec] | None = None
    ) -> AsyncIterator[StreamItem]:
        if self._client is None:
            raise LLMError("GROQ_API_KEY is not configured on the server.", code="not_configured")

        request: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": self._settings.llm_temperature,
            "max_completion_tokens": self._settings.llm_max_tokens,
            "stream": True,
        }
        if tools:
            request["tools"] = tools
            request["tool_choice"] = "auto"
        if self._settings.llm_reasoning_effort and self.model.startswith(_REASONING_MODEL_PREFIXES):
            request["extra_body"] = {"reasoning_effort": self._settings.llm_reasoning_effort}

        text_parts: list[str] = []
        calls: dict[int, dict[str, str]] = {}
        finish_reason: str | None = None
        usage: dict[str, Any] | None = None

        try:
            stream = await self._client.chat.completions.create(**request)
            async for chunk in stream:
                x_groq = getattr(chunk, "x_groq", None)
                if x_groq is not None and getattr(x_groq, "usage", None) is not None:
                    usage = x_groq.usage.model_dump()
                if not chunk.choices:
                    continue
                choice = chunk.choices[0]
                delta = choice.delta
                if delta.content:
                    text_parts.append(delta.content)
                    yield TextDelta(delta.content)
                # Tool calls may arrive whole or as fragments keyed by index.
                for tc in delta.tool_calls or []:
                    slot = calls.setdefault(tc.index, {"id": "", "name": "", "arguments": ""})
                    if tc.id:
                        slot["id"] = tc.id
                    if tc.function is not None:
                        if tc.function.name:
                            slot["name"] = slot["name"] or tc.function.name
                        if tc.function.arguments:
                            slot["arguments"] += tc.function.arguments
                if choice.finish_reason:
                    finish_reason = choice.finish_reason
        except groq.APIStatusError as exc:
            raise _to_llm_error(exc) from exc
        except groq.APIConnectionError as exc:  # includes timeouts
            raise LLMError(f"Could not reach Groq: {exc}", code="connection_error") from exc

        tool_calls = [
            ToolCall(id=c["id"] or f"call_{i}", name=c["name"], arguments=c["arguments"] or "{}")
            for i, c in sorted(calls.items())
            if c["name"]
        ]
        if usage:
            logger.debug("groq usage: %s", usage)
        yield Completion(
            text="".join(text_parts),
            tool_calls=tool_calls,
            finish_reason=finish_reason,
            usage=usage,
        )

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.close()


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
    header = exc.response.headers.get("retry-after")
    if header:
        try:
            retry_after = float(header)
        except ValueError:
            retry_after = None
    return LLMError(message, code=code, status=exc.status_code, retry_after=retry_after)
