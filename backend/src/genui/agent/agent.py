"""The generative-UI agent loop.

Per user turn:
  1. Persist the user message, load trimmed history.
  2. Loop (bounded by `agent_max_steps`):
     - stream the LLM; forward text deltas
     - run data tool calls, feeding results back
     - validate `render_ui` calls; emit valid UI, return validation errors to the model to repair
     - stop once UI rendered successfully, or the model answers without tool calls
  3. Persist each step atomically (assistant message + its tool results) so history stays valid.
"""

import asyncio
import json
import logging
import re
import uuid
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from typing import Any

from genui.agent.events import AgentEvent
from genui.agent.history import compact_history
from genui.agent.prompts import RENDER_UI_SPEC, RENDER_UI_TOOL
from genui.core.config import Settings
from genui.db.session import SessionFactory
from genui.llm import ChatMessage, Completion, LLMError, LLMProvider, TextDelta, ToolCall
from genui.services.conversations import Block, ConversationRepository
from genui.tools import ToolContext, ToolRegistry
from genui.ui.validation import parse_ui_arguments

logger = logging.getLogger(__name__)

_MAX_TOOL_USE_RETRIES = 2
_UI_AS_TEXT_NUDGE = (
    "[system] You wrote UI JSON as message text, which the user cannot see as an interface. "
    "Call the render_ui tool with the components instead, and fix any invalid fields."
)
_MAX_RETRY_DELAY_SECONDS = 60.0


@dataclass(slots=True, frozen=True)
class _RetryNotice:
    message: str


class _TextGate:
    """Streams assistant text, but holds it back when it starts like JSON or a code fence —
    i.e. the model wrote a UI spec as text instead of calling `render_ui`. Held text is
    recovered as real UI (or released as text) once the step completes."""

    def __init__(self) -> None:
        self._buffer = ""
        self._mode: str = "undecided"  # -> "stream" | "hold"

    @property
    def held(self) -> bool:
        return self._mode == "hold"

    def feed(self, delta: str) -> str:
        """Return the text to forward to the client now."""
        if self._mode == "stream":
            return delta
        self._buffer += delta
        if self._mode == "hold":
            return ""
        stripped = self._buffer.lstrip()
        if not stripped:
            return ""
        if stripped[0] in "{[`":
            self._mode = "hold"
            return ""
        self._mode = "stream"
        return self._buffer


_FENCE = re.compile(r"^```[a-zA-Z]*\s*|\s*```$")


class ConversationNotFoundError(Exception):
    pass


@dataclass(slots=True)
class UserInput:
    """A user turn: either a typed message or an interaction with generated UI."""

    llm_content: str
    display: Block
    title: str

    @classmethod
    def from_message(cls, text: str) -> "UserInput":
        text = text.strip()
        return cls(llm_content=text, display={"type": "text", "text": text}, title=text[:80])

    @classmethod
    def from_event(cls, action: str, payload: dict[str, Any], label: str | None) -> "UserInput":
        data = json.dumps(payload, ensure_ascii=False, default=str)
        content = f"[UI event] action={action!r} data={data}"
        display = {"type": "event", "action": action, "payload": payload, "label": label}
        return cls(llm_content=content, display=display, title=label or action.replace("_", " "))


@dataclass(slots=True)
class _Step:
    """Outcome of processing one LLM completion."""

    assistant: ChatMessage
    display: list[Block] = field(default_factory=list)
    tool_messages: list[ChatMessage] = field(default_factory=list)
    rendered: bool = False
    ui_failed: bool = False


class ChatAgent:
    def __init__(
        self,
        *,
        llm: LLMProvider,
        tools: ToolRegistry,
        session_factory: SessionFactory,
        settings: Settings,
        system_prompt: Callable[[], str],
    ) -> None:
        self._llm = llm
        self._tools = tools
        self._session_factory = session_factory
        self._settings = settings
        self._system_prompt = system_prompt
        self._tool_specs = [RENDER_UI_SPEC, *tools.specs()]

    async def run(
        self, *, user_id: str, conversation_id: str | None, user_input: UserInput
    ) -> AsyncIterator[AgentEvent]:
        """Stream one turn's events. Always ends with `done` unless the client disconnects."""
        async for event in self._run_turn(user_id, conversation_id, user_input):
            yield event
        yield AgentEvent("done", {})

    async def _run_turn(
        self, user_id: str, conversation_id: str | None, user_input: UserInput
    ) -> AsyncIterator[AgentEvent]:
        conversation_id, title, history = await self._start_turn(
            user_id, conversation_id, user_input
        )
        yield AgentEvent("conversation", {"conversation_id": conversation_id, "title": title})

        messages: list[ChatMessage] = [
            {"role": "system", "content": self._system_prompt()},
            *compact_history(history, tool_result_chars=self._settings.history_tool_result_chars),
            {"role": "user", "content": user_input.llm_content},
        ]
        ctx = ToolContext(user_id=user_id, session_factory=self._session_factory)
        ui_failures = 0

        try:
            for _ in range(self._settings.agent_max_steps):
                completion: Completion | None = None
                gate = _TextGate()
                async for item in self._stream_with_retry(messages):
                    if isinstance(item, TextDelta):
                        if visible := gate.feed(item.text):
                            yield AgentEvent("text", {"delta": visible})
                    elif isinstance(item, _RetryNotice):
                        yield AgentEvent("status", {"message": item.message})
                    else:
                        completion = item
                assert completion is not None

                if not completion.tool_calls and gate.held:
                    # The model wrote JSON as text. Recover it as UI if it's a valid spec.
                    ui_text = _FENCE.sub("", completion.text.strip())
                    if parse_ui_arguments(ui_text).ok:
                        call = ToolCall(
                            id=f"call_{uuid.uuid4().hex[:12]}", name=RENDER_UI_TOOL,
                            arguments=ui_text,
                        )  # fmt: skip
                        completion = Completion(text="", tool_calls=[call])
                    elif '"type"' in ui_text or "components" in ui_text:
                        ui_failures += 1
                        if ui_failures > self._settings.agent_max_ui_repairs:
                            yield _error("Sorry, I couldn't build a valid interface for that. "
                                         "Try rephrasing your request.", "ui_invalid")  # fmt: skip
                            return
                        messages.append({"role": "assistant", "content": completion.text})
                        messages.append({"role": "user", "content": _UI_AS_TEXT_NUDGE})
                        yield AgentEvent("status", {"message": "Refining the interface…"})
                        continue
                    else:
                        yield AgentEvent("text", {"delta": completion.text})

                if not completion.tool_calls:
                    if completion.text.strip():
                        await self._persist(
                            conversation_id,
                            [("assistant", {"role": "assistant", "content": completion.text},
                              [{"type": "text", "text": completion.text}])],
                        )  # fmt: skip
                    else:
                        yield _error("The model returned an empty response. Please try again.")
                    return

                step = _Step(assistant=_assistant_message(completion))
                if completion.text.strip() and not gate.held:
                    step.display.append({"type": "text", "text": completion.text})

                for call in completion.tool_calls:
                    async for event in self._handle_call(call, ctx, step):
                        yield event

                messages.append(step.assistant)
                messages.extend(step.tool_messages)
                await self._persist(
                    conversation_id,
                    [("assistant", step.assistant, step.display or None)]
                    + [("tool", m, None) for m in step.tool_messages],
                )

                if step.rendered and not step.ui_failed:
                    return
                if step.ui_failed:
                    ui_failures += 1
                    if ui_failures > self._settings.agent_max_ui_repairs:
                        yield _error("Sorry, I couldn't build a valid interface for that. "
                                     "Try rephrasing your request.", "ui_invalid")  # fmt: skip
                        return
                    yield AgentEvent("status", {"message": "Refining the interface…"})

            yield _error("Reached the step limit before finishing. Try a narrower request.")
        except LLMError as exc:
            logger.warning("LLM error (%s): %s", exc.code, exc)
            yield _error(_friendly_llm_error(exc), exc.code)
        except Exception:
            logger.exception("agent turn failed")
            yield _error("Something went wrong while generating a response.", "internal")

    # ------------------------------------------------------------------ internals

    async def _start_turn(
        self, user_id: str, conversation_id: str | None, user_input: UserInput
    ) -> tuple[str, str, list[ChatMessage]]:
        async with self._session_factory() as session:
            repo = ConversationRepository(session)
            if conversation_id:
                conversation = await repo.get(conversation_id, user_id)
                if conversation is None:
                    raise ConversationNotFoundError(conversation_id)
                history = await repo.llm_history(
                    conversation.id, limit=self._settings.history_max_messages
                )
            else:
                conversation = await repo.create(user_id, user_input.title)
                history = []
            await repo.add_messages(
                conversation.id,
                [("user", {"role": "user", "content": user_input.llm_content},
                  [user_input.display])],
            )  # fmt: skip
            await session.commit()
            return conversation.id, conversation.title, history

    async def _stream_with_retry(
        self, messages: list[ChatMessage]
    ) -> AsyncIterator[TextDelta | Completion | _RetryNotice]:
        """Stream one LLM step, retrying transient failures and malformed tool calls.

        Retries happen only if nothing was streamed to the client yet (so text is never
        duplicated). Waits are surfaced as notices instead of a silent spinner.
        """
        tool_use_retries = transient_retries = 0
        while True:
            emitted = False
            try:
                async for item in self._llm.stream(messages, self._tool_specs):
                    emitted = emitted or isinstance(item, TextDelta)
                    yield item
                return
            except LLMError as exc:
                if emitted:
                    raise
                if exc.is_tool_use_failure and tool_use_retries < _MAX_TOOL_USE_RETRIES:
                    tool_use_retries += 1
                    logger.info("retrying after tool_use_failed (%d)", tool_use_retries)
                    continue
                if not exc.is_retryable or transient_retries >= self._settings.llm_max_retries:
                    raise
                transient_retries += 1
                delay = min(exc.retry_after or 2.0**transient_retries, _MAX_RETRY_DELAY_SECONDS)
                reason = "Groq rate limit reached" if exc.status == 429 else "AI service hiccup"
                logger.info("%s; retrying in %.0fs (%d)", reason, delay, transient_retries)
                yield _RetryNotice(f"{reason} — continuing in {delay:.0f}s…")
                await asyncio.sleep(delay)

    async def _handle_call(
        self, call: ToolCall, ctx: ToolContext, step: _Step
    ) -> AsyncIterator[AgentEvent]:
        if call.name == RENDER_UI_TOOL:
            parsed = parse_ui_arguments(call.arguments)
            if parsed.ok:
                block: Block = {
                    "type": "ui",
                    "id": uuid.uuid4().hex[:12],
                    "components": parsed.components,
                }
                step.display.append(block)
                step.rendered = True
                result: dict[str, Any] = {"ok": True, "message": "UI rendered to the user."}
                yield AgentEvent("ui", block)
            else:
                step.ui_failed = True
                logger.info("render_ui validation failed:\n%s", parsed.error)
                result = {
                    "ok": False,
                    "error": "Invalid components; nothing was shown. Fix these and call "
                    f"render_ui again:\n{parsed.error}",
                }
        else:
            label = self._tools.label(call.name)
            yield AgentEvent("tool_start", {"id": call.id, "name": call.name, "label": label})
            outcome = await self._tools.execute(call.name, call.arguments, ctx)
            yield AgentEvent("tool_end", {"id": call.id, "name": call.name, "ok": outcome.ok})
            result = outcome.to_llm()

        content = json.dumps(result, ensure_ascii=False, default=str)
        if len(content) > self._settings.tool_result_max_chars:
            content = content[: self._settings.tool_result_max_chars] + "…[truncated]"
        step.tool_messages.append({"role": "tool", "tool_call_id": call.id, "content": content})

    async def _persist(
        self, conversation_id: str, rows: list[tuple[str, ChatMessage, list[Block] | None]]
    ) -> None:
        async with self._session_factory() as session:
            await ConversationRepository(session).add_messages(conversation_id, rows)
            await session.commit()


def _assistant_message(completion: Completion) -> ChatMessage:
    message: ChatMessage = {"role": "assistant", "content": completion.text or None}
    if completion.tool_calls:
        message["tool_calls"] = [c.to_message() for c in completion.tool_calls]
    return message


def _error(message: str, code: str | None = None) -> AgentEvent:
    return AgentEvent("error", {"message": message, "code": code})


def _friendly_llm_error(exc: LLMError) -> str:
    match exc.code:
        case "not_configured":
            return "The AI service isn't configured (missing GROQ_API_KEY)."
        case "rate_limited" | "rate_limit_exceeded" if "request too large" in str(exc).lower():
            return (
                "This conversation is too long for the current Groq plan's token limit. "
                "Start a new conversation or upgrade the Groq tier."
            )
        case "rate_limited" | "rate_limit_exceeded":
            return "The AI service is busy (rate limited). Please wait a moment and retry."
        case "connection_error":
            return "Couldn't reach the AI service. Check your connection and retry."
        case "tool_use_failed":
            return "The model produced an invalid tool call. Please try again."
        case _:
            return f"The AI service returned an error: {exc}"
