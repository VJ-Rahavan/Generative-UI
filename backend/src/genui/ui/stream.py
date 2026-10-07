"""Incremental parser that turns a streamed assistant answer into prose + UI components.

The model writes its answer as optional prose followed by a fenced block, one component per
line:

    Here's your progress.
    ```ui
    {"type": "text", "content": "Bench press", "variant": "heading"}
    {"type": "chart", ...}
    ```

LLM providers stream message text token by token (Groq does not stream tool-call arguments),
so parsing the text lets each component be validated and shown the moment its JSON closes.

The parser is deliberately forgiving about framing: it extracts every complete top-level
JSON object inside the UI region, so JSONL, pretty-printed objects, a bare `[...]` array or a
`{"components": [...]}` wrapper all work. A UI region opens at a ```ui / ```json / ``` fence,
or at a line that starts with `{` or `[` (unfenced JSON).
"""

import json
import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

from genui.ui.validation import validate_component

_UI_FENCE_TAGS = {"", "ui", "json", "jsonl"}


# --------------------------------------------------------------------------- events


@dataclass(slots=True, frozen=True)
class TextOut:
    text: str


@dataclass(slots=True, frozen=True)
class UIStart:
    block_id: str


@dataclass(slots=True, frozen=True)
class UIComponent:
    block_id: str
    component: dict[str, Any]


@dataclass(slots=True, frozen=True)
class UIEnd:
    block_id: str


ParseEvent = TextOut | UIStart | UIComponent | UIEnd


@dataclass(slots=True)
class _Segment:
    kind: str  # "text" | "ui"
    text: str = ""
    block_id: str = ""
    components: list[dict[str, Any]] = field(default_factory=list)


# --------------------------------------------------------------------------- JSON scanning


class _ObjectScanner:
    """Collects characters of top-level JSON objects; returns each one when its braces close.

    Only `{`/`}` outside strings change depth, so arrays, commas and whitespace *between*
    objects are skipped naturally.
    """

    def __init__(self) -> None:
        self.depth = 0
        self._chars: list[str] = []
        self._in_string = False
        self._escaped = False

    @property
    def has_partial(self) -> bool:
        return self.depth > 0

    def feed(self, ch: str) -> str | None:
        if self.depth == 0:
            if ch == "{":
                self.depth = 1
                self._chars = [ch]
            return None
        self._chars.append(ch)
        if self._in_string:
            if self._escaped:
                self._escaped = False
            elif ch == "\\":
                self._escaped = True
            elif ch == '"':
                self._in_string = False
        elif ch == '"':
            self._in_string = True
        elif ch == "{":
            self.depth += 1
        elif ch == "}":
            self.depth -= 1
            if self.depth == 0:
                return "".join(self._chars)
        return None


# --------------------------------------------------------------------------- parser


class AnswerStreamParser:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.component_count = 0
        self._segments: list[_Segment] = []
        self._mode = "prose"  # "prose" | "ui"
        self._pending = ""  # current prose line while we decide whether it opens UI
        self._line_decided = False
        self._swallow_line = False  # skip the remainder of a closing-fence line
        self._fenced = False
        self._backticks = 0
        self._scanner = _ObjectScanner()
        self._block_id = ""

    # -- public API ---------------------------------------------------------------

    def feed(self, text: str) -> list[ParseEvent]:
        events: list[ParseEvent] = []
        prose: list[str] = []
        for ch in text:
            if self._mode == "prose":
                self._feed_prose(ch, prose, events)
            else:
                self._feed_ui(ch, prose, events)
        self._flush_prose(prose, events)
        return events

    def finish(self) -> list[ParseEvent]:
        events: list[ParseEvent] = []
        if self._mode == "prose" and self._pending:
            line, self._pending = self._pending, ""
            if not self._is_fence(line):
                self._flush_prose([line], events)
        elif self._mode == "ui":
            if self._scanner.has_partial:
                self.errors.append("the last component was cut off before its JSON closed")
            self._close_ui(events)
        return events

    @property
    def ui_opened(self) -> bool:
        return any(s.kind == "ui" for s in self._segments)

    def display_blocks(self) -> list[dict[str, Any]]:
        """Blocks to persist and show for this answer, in order."""
        blocks: list[dict[str, Any]] = []
        for seg in self._segments:
            if seg.kind == "text" and seg.text.strip():
                blocks.append({"type": "text", "text": seg.text.strip()})
            elif seg.kind == "ui" and seg.components:
                blocks.append({"type": "ui", "id": seg.block_id, "components": seg.components})
        return blocks

    def prose_text(self) -> str:
        return "\n".join(s.text.strip() for s in self._segments if s.kind == "text").strip()

    def components(self) -> list[dict[str, Any]]:
        return [c for s in self._segments if s.kind == "ui" for c in s.components]

    # -- prose mode -----------------------------------------------------------------

    def _feed_prose(self, ch: str, prose: list[str], events: list[ParseEvent]) -> None:
        if self._swallow_line:
            self._swallow_line = ch != "\n"
            return
        if self._line_decided:
            prose.append(ch)
            if ch == "\n":
                self._line_decided = False
            return

        self._pending += ch
        stripped = self._pending.lstrip()
        if ch == "\n":
            line, self._pending = self._pending, ""
            if self._is_fence(line):
                self._flush_prose(prose, events)
                self._open_ui(events, fenced=True)
            else:
                prose.append(line)
            return
        if stripped.startswith("```") and ch == "{" and self._is_fence(stripped[:-1]):
            # Fence and JSON on the same line: ```ui {"type": ...
            self._pending = ""
            self._flush_prose(prose, events)
            self._open_ui(events, fenced=True)
            self._feed_ui(ch, prose, events)
            return
        if not stripped or stripped[0] == "`":
            return  # whitespace or a possible fence: wait for the rest of the line
        if stripped[0] in "{[":
            self._flush_prose(prose, events)
            self._open_ui(events, fenced=False)
            pending, self._pending = stripped, ""
            for c in pending:
                self._feed_ui(c, prose, events)
            return
        prose.append(self._pending)
        self._pending = ""
        self._line_decided = True

    @staticmethod
    def _is_fence(line: str) -> bool:
        s = line.strip()
        return s.startswith("```") and s[3:].strip().lower() in _UI_FENCE_TAGS

    def _flush_prose(self, prose: list[str], events: list[ParseEvent]) -> None:
        if not prose:
            return
        text = "".join(prose)
        prose.clear()
        if not text:
            return
        if self._segments and self._segments[-1].kind == "text":
            self._segments[-1].text += text
        else:
            self._segments.append(_Segment(kind="text", text=text))
        events.append(TextOut(text))

    # -- UI mode --------------------------------------------------------------------

    def _open_ui(self, events: list[ParseEvent], *, fenced: bool) -> None:
        self._mode = "ui"
        self._fenced = fenced
        self._backticks = 0
        self._scanner = _ObjectScanner()
        self._block_id = uuid.uuid4().hex[:12]
        self._segments.append(_Segment(kind="ui", block_id=self._block_id))
        events.append(UIStart(self._block_id))

    def _close_ui(self, events: list[ParseEvent]) -> None:
        events.append(UIEnd(self._block_id))
        self._mode = "prose"
        self._pending = ""
        self._line_decided = False

    def _feed_ui(self, ch: str, prose: list[str], events: list[ParseEvent]) -> None:
        scanner = self._scanner
        if scanner.depth == 0:
            if self._fenced and ch == "`":
                self._backticks += 1
                if self._backticks == 3:
                    self._close_ui(events)
                    self._swallow_line = True
                return
            self._backticks = 0
            if not self._fenced and ch.isalpha():
                # Unfenced JSON followed by prose: back to prose mode.
                self._close_ui(events)
                self._feed_prose(ch, prose, events)
                return
        obj = scanner.feed(ch)
        if obj is not None:
            for component in self._components_from(obj):
                events.append(UIComponent(self._block_id, component))

    def _components_from(self, raw: str) -> Iterator[dict[str, Any]]:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            self.errors.append(f"invalid JSON ({exc.msg}) in: {raw[:120]}")
            return
        items = (
            data["components"]
            if isinstance(data, dict) and "type" not in data and "components" in data
            else [data]
        )
        for item in items if isinstance(items, list) else [items]:
            result = validate_component(item)
            if result.component is not None:
                self.component_count += 1
                self._segments[-1].components.append(result.component)
                yield result.component
            else:
                kind = item.get("type", "?") if isinstance(item, dict) else "?"
                self.errors.append(f'component "{kind}":\n{result.error}')


def parse_answer(text: str) -> AnswerStreamParser:
    """Parse a complete answer at once (used for history and stored messages)."""
    parser = AnswerStreamParser()
    parser.feed(text)
    parser.finish()
    return parser
