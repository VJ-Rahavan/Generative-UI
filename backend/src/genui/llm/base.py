"""Provider-agnostic LLM streaming interface (OpenAI-style chat messages + function tools)."""

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, Protocol

ChatMessage = dict[str, Any]
ToolSpec = dict[str, Any]


@dataclass(slots=True)
class ToolCall:
    id: str
    name: str
    arguments: str  # raw JSON string as produced by the model

    def to_message(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": "function",
            "function": {"name": self.name, "arguments": self.arguments},
        }


@dataclass(slots=True)
class TextDelta:
    text: str


@dataclass(slots=True)
class Completion:
    """Final item of every stream: the fully assembled assistant turn."""

    text: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    finish_reason: str | None = None
    usage: dict[str, Any] | None = None


StreamItem = TextDelta | Completion


class LLMError(Exception):
    def __init__(self, message: str, *, code: str | None = None, status: int | None = None):
        super().__init__(message)
        self.code = code
        self.status = status

    @property
    def is_tool_use_failure(self) -> bool:
        """The model produced a malformed tool call; retrying the step usually fixes it."""
        return self.code == "tool_use_failed"


class LLMProvider(Protocol):
    @property
    def model(self) -> str: ...

    def stream(
        self, messages: list[ChatMessage], tools: list[ToolSpec] | None = None
    ) -> AsyncIterator[StreamItem]:
        """Yield TextDelta items as they arrive, then exactly one Completion."""
        ...

    async def aclose(self) -> None: ...
