"""Conversation persistence and history shaping."""

from collections.abc import Sequence
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from genui.db.base import utcnow
from genui.db.models import Conversation, Message

Block = dict[str, Any]


class ConversationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, user_id: str, title: str) -> Conversation:
        conversation = Conversation(user_id=user_id, title=title[:200] or "New conversation")
        self.session.add(conversation)
        await self.session.flush()
        return conversation

    async def get(self, conversation_id: str, user_id: str) -> Conversation | None:
        return await self.session.scalar(
            select(Conversation).where(
                Conversation.id == conversation_id, Conversation.user_id == user_id
            )
        )

    async def list_for_user(self, user_id: str, *, limit: int = 50) -> Sequence[Conversation]:
        result = await self.session.scalars(
            select(Conversation)
            .where(Conversation.user_id == user_id)
            .order_by(Conversation.updated_at.desc())
            .limit(limit)
        )
        return result.all()

    async def delete(self, conversation: Conversation) -> None:
        await self.session.delete(conversation)

    async def add_messages(
        self,
        conversation_id: str,
        messages: list[tuple[str, dict[str, Any], list[Block] | None]],
    ) -> None:
        """Append (role, llm_payload, display_blocks) rows and bump the conversation."""
        for role, payload, display in messages:
            self.session.add(
                Message(
                    conversation_id=conversation_id, role=role, payload=payload, display=display
                )
            )
        conversation = await self.session.get(Conversation, conversation_id)
        if conversation is not None:
            conversation.updated_at = utcnow()

    async def messages(self, conversation_id: str) -> Sequence[Message]:
        result = await self.session.scalars(
            select(Message).where(Message.conversation_id == conversation_id).order_by(Message.id)
        )
        return result.all()

    async def llm_history(self, conversation_id: str, *, limit: int) -> list[dict[str, Any]]:
        """The last `limit` messages in LLM wire format, starting at a user message so that
        no tool result is ever orphaned from its assistant tool call."""
        result = await self.session.scalars(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.id.desc())
            .limit(limit)
        )
        rows = list(reversed(result.all()))
        while rows and rows[0].role != "user":
            rows.pop(0)
        return [row.payload for row in rows]


def build_turns(messages: Sequence[Message]) -> list[dict[str, Any]]:
    """Group stored messages into chat turns for the frontend.

    One assistant turn may span several LLM messages (tool calls, tool results, final text);
    their display blocks are concatenated in order. Tool messages have no display.
    """
    turns: list[dict[str, Any]] = []
    for message in messages:
        if message.role == "user":
            blocks = message.display or [
                {"type": "text", "text": str(message.payload.get("content", ""))}
            ]
            turns.append({"role": "user", "blocks": blocks})
        elif message.role == "assistant" and message.display:
            if not turns or turns[-1]["role"] != "assistant":
                turns.append({"role": "assistant", "blocks": []})
            turns[-1]["blocks"].extend(message.display)
    return turns
