"""Request/response models for the HTTP API."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class UIEventIn(BaseModel):
    """A button click or form submit from generated UI."""

    action: str = Field(min_length=1, max_length=100)
    payload: dict[str, Any] = Field(default_factory=dict)
    label: str | None = Field(None, max_length=200, description="Human-readable label")


class ChatRequest(BaseModel):
    conversation_id: str | None = None
    message: str | None = Field(None, max_length=8000)
    event: UIEventIn | None = None

    @model_validator(mode="after")
    def _exactly_one_input(self) -> "ChatRequest":
        has_message = bool(self.message and self.message.strip())
        if has_message == (self.event is not None):
            raise ValueError("Provide exactly one of 'message' (non-empty) or 'event'")
        return self


class ConversationSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    created_at: datetime
    updated_at: datetime


class Turn(BaseModel):
    role: Literal["user", "assistant"]
    blocks: list[dict[str, Any]]


class ConversationDetail(ConversationSummary):
    turns: list[Turn]


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    app: str
    model: str
    llm_configured: bool


class ToolInfo(BaseModel):
    name: str
    label: str
    description: str
