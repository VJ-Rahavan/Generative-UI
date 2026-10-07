"""The generative-UI agent loop.

Per user turn:
  1. Persist the user message, load trimmed history.
  2. Loop (bounded by `agent_max_steps`):
     - stream the LLM; the answer text goes through `AnswerStreamParser`, which forwards
       prose and emits each UI component the moment its JSON is complete (streaming UI)
     - run data tool calls, feeding results back
     - if some components were invalid, ask the model for corrected versions (bounded)
     - stop once the model answers without tool calls
  3. Persist each step atomically (assistant message + its tool results) so history stays valid.
"""

import asyncio
import json
import logging
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from typing import Any

from langsmith import traceable

from genui.agent.events import AgentEvent
from genui.agent.history import compact_history
from genui.core.config import Settings
from genui.db.session import SessionFactory
from genui.llm import ChatMessage, Completion, LLMError, LLMProvider, TextDelta
from genui.services.conversations import Block, ConversationRepository
from genui.tools import ToolContext, ToolRegistry
from genui.ui.stream import AnswerStreamParser, ParseEvent, TextOut, UIComponent, UIEnd, UIStart

logger = logging.getLogger(__name__)

_MAX_TOOL_USE_RETRIES = 2
_MAX_RETRY_DELAY_SECONDS = 60.0


@dataclass(slots=True, frozen=True)
class _RetryNotice:
    message: str


@dataclass(slots=True)
class _StepOutput:
    completion: Completion | None = None


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
        self._tool_specs = tools.specs()

    async def run(
        self, *, user_id: str, conversation_id: str | None, user_input: UserInput
    ) -> AsyncIterator[AgentEvent]:
        """Stream one turn's events. Always ends with `done` unless the client disconnects."""
        async for event in self._run_turn(user_id, conversation_id, user_input):
            yield event
        yield AgentEvent("done", {})

    @traceable(
        run_type="chain",
        name="chat_turn",
        process_inputs=lambda inputs: {
            "user_id": inputs.get("user_id"),
            "conversation_id": inputs.get("conversation_id"),
            "input": getattr(inputs.get("user_input"), "llm_content", None),
        },
        reduce_fn=lambda events: {
            "events": [e.type for e in events],
            "components": [e.data["component"] for e in events if e.type == "ui_component"],
        },
    )
    async def _run_turn(
        self, user_id: str, conversation_id: str | None, user_input: UserInput
    ) -> AsyncIterator[AgentEvent]:
        """One user turn. Traced as a single LangSmith run (LLM + tool calls nested) when
        tracing is enabled; a no-op otherwise."""
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
        repairs = 0
        rendered_any = False

        try:
            for _ in range(self._settings.agent_max_steps):
                parser, out = AnswerStreamParser(), _StepOutput()
                async for event in self._stream_step(messages, parser, out):
                    yield event
                completion = out.completion
                assert completion is not None
                rendered_any = rendered_any or parser.component_count > 0

                assistant: ChatMessage = {"role": "assistant", "content": completion.text or None}
                if completion.tool_calls:
                    assistant["tool_calls"] = [c.to_message() for c in completion.tool_calls]
                    tool_messages: list[ChatMessage] = []
                    async for event in self._run_tools(completion, ctx, tool_messages):
                        yield event
                    messages += [assistant, *tool_messages]
                    await self._persist(
                        conversation_id,
                        [("assistant", assistant, parser.display_blocks() or None)]
                        + [("tool", m, None) for m in tool_messages],
                    )
                    continue

                # Final answer (no tool calls).
                if not completion.text.strip():
                    yield _error("The model returned an empty response. Please try again.")
                    return
                await self._persist(
                    conversation_id, [("assistant", assistant, parser.display_blocks() or None)]
                )
                if not parser.errors:
                    return

                logger.info("invalid UI components:\n%s", "\n".join(parser.errors))
                if repairs >= self._settings.agent_max_ui_repairs:
                    if not rendered_any:
                        yield _error("Sorry, I couldn't build a valid interface for that. "
                                     "Try rephrasing your request.", "ui_invalid")  # fmt: skip
                    return
                repairs += 1
                yield AgentEvent("status", {"message": "Fixing part of the interface…"})
                messages += [assistant, {"role": "user", "content": _repair_prompt(parser)}]

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

    async def _stream_step(
        self, messages: list[ChatMessage], parser: AnswerStreamParser, out: _StepOutput
    ) -> AsyncIterator[AgentEvent]:
        """Stream one LLM call, turning its text into prose and UI events as it arrives."""
        async for item in self._stream_with_retry(messages):
            if isinstance(item, TextDelta):
                for parsed in parser.feed(item.text):
                    yield _to_event(parsed)
            elif isinstance(item, _RetryNotice):
                yield AgentEvent("status", {"message": item.message})
            else:
                out.completion = item
        for parsed in parser.finish():
            yield _to_event(parsed)

    async def _run_tools(
        self, completion: Completion, ctx: ToolContext, results: list[ChatMessage]
    ) -> AsyncIterator[AgentEvent]:
        """Execute the step's tool calls, appending tool-result messages to `results`."""
        for call in completion.tool_calls:
            label = self._tools.label(call.name)
            yield AgentEvent("tool_start", {"id": call.id, "name": call.name, "label": label})
            outcome = await self._tools.execute(call.name, call.arguments, ctx)
            yield AgentEvent("tool_end", {"id": call.id, "name": call.name, "ok": outcome.ok})
            results.append(
                {"role": "tool", "tool_call_id": call.id,
                 "content": self._tool_content(outcome.to_llm())}
            )  # fmt: skip

    async def _stream_with_retry(
        self, messages: list[ChatMessage]
    ) -> AsyncIterator[TextDelta | Completion | _RetryNotice]:
        """Stream one LLM step, retrying transient failures and malformed tool calls.

        Retries happen only if nothing was streamed to the client yet (so output is never
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

    def _tool_content(self, result: dict[str, Any]) -> str:
        content = json.dumps(result, ensure_ascii=False, default=str)
        if len(content) > self._settings.tool_result_max_chars:
            content = content[: self._settings.tool_result_max_chars] + "…[truncated]"
        return content

    async def _persist(
        self, conversation_id: str, rows: list[tuple[str, ChatMessage, list[Block] | None]]
    ) -> None:
        async with self._session_factory() as session:
            await ConversationRepository(session).add_messages(conversation_id, rows)
            await session.commit()


def _to_event(parsed: ParseEvent) -> AgentEvent:
    match parsed:
        case TextOut(text=text):
            return AgentEvent("text", {"delta": text})
        case UIStart(block_id=block_id):
            return AgentEvent("ui_start", {"id": block_id})
        case UIComponent(block_id=block_id, component=component):
            return AgentEvent("ui_component", {"id": block_id, "component": component})
        case UIEnd(block_id=block_id):
            return AgentEvent("ui_end", {"id": block_id})
    raise TypeError(f"unknown parse event: {parsed!r}")


def _repair_prompt(parser: AnswerStreamParser) -> str:
    n = parser.component_count
    shown = "Nothing was" if not n else f"{n} component{'s were' if n > 1 else ' was'}"
    return (
        f"[system] {shown} rendered. These components were invalid and NOT shown:\n"
        + "\n".join(parser.errors)
        + "\nWrite a new ```ui block containing only corrected versions of these components."
    )


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
