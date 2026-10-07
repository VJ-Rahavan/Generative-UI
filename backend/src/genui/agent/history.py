"""Compact earlier turns before replaying them to the LLM.

Past UI is the bulk of the history (full component JSON), so each ```ui block is replaced by
a one-line text outline of what was shown. Past data-tool results are truncated. The model
keeps the gist of the conversation at a fraction of the tokens.

Conversations created before streaming UI used a `render_ui` tool call instead; those calls
(and their tool results) are compacted the same way.
"""

import json
from typing import Any

from genui.llm import ChatMessage
from genui.ui.stream import parse_answer

LEGACY_RENDER_UI_TOOL = "render_ui"

_OUTLINE_MAX_CHARS = 700


def compact_history(messages: list[ChatMessage], *, tool_result_chars: int) -> list[ChatMessage]:
    ui_call_ids: set[str] = set()
    compacted: list[ChatMessage] = []

    for message in messages:
        role = message.get("role")
        if role == "assistant" and "```" in str(message.get("content") or ""):
            message = {**message, "content": compact_answer(str(message["content"]))}
        if role == "assistant" and message.get("tool_calls"):
            kept_calls, outlines = [], []
            for call in message["tool_calls"]:
                if call["function"]["name"] == LEGACY_RENDER_UI_TOOL:
                    ui_call_ids.add(call["id"])
                    outlines.append(outline_ui(call["function"]["arguments"]))
                else:
                    kept_calls.append(call)
            text = "\n".join(filter(None, [message.get("content"), *outlines])) or None
            new_message: ChatMessage = {"role": "assistant", "content": text}
            if kept_calls:
                new_message["tool_calls"] = kept_calls
            elif text is None:
                continue
            compacted.append(new_message)
        elif role == "tool":
            if message.get("tool_call_id") in ui_call_ids:
                continue
            content = str(message.get("content", ""))
            if len(content) > tool_result_chars:
                content = content[:tool_result_chars] + "…[truncated]"
            compacted.append({**message, "content": content})
        else:
            compacted.append(message)
    return compacted


def compact_answer(content: str) -> str:
    """Replace the ```ui block(s) of a stored answer with a one-line outline."""
    parsed = parse_answer(content)
    if not parsed.ui_opened:
        return content
    return "\n".join(filter(None, [parsed.prose_text(), outline_components(parsed.components())]))


def outline_ui(arguments: str) -> str:
    """Outline of a legacy render_ui tool call."""
    try:
        data = json.loads(arguments)
        components = data.get("components", data) if isinstance(data, dict) else data
    except json.JSONDecodeError:
        return "[Showed UI]"
    return outline_components(components if isinstance(components, list) else [])


def outline_components(components: list[Any]) -> str:
    """Human-readable outline of rendered components, e.g. for history or logs."""
    parts = [_describe(c) for c in components if isinstance(c, dict)]
    text = "[Showed UI: " + "; ".join(p for p in parts if p) + "]"
    return text if len(text) <= _OUTLINE_MAX_CHARS else text[: _OUTLINE_MAX_CHARS - 2] + "…]"


def _describe(c: dict[str, Any]) -> str:
    kind = c.get("type", "?")
    match kind:
        case "text":
            return f'text "{str(c.get("content", ""))[:80]}"'
        case "metric":
            return f"metric {c.get('label')}={c.get('value')}{c.get('unit') or ''}"
        case "chart":
            return f'{c.get("chart_type", "")} chart "{c.get("title") or ""}"'
        case "table" | "list":
            n = len(c.get("rows") or c.get("items") or [])
            return f'{kind} "{c.get("title") or ""}" ({n} rows)'
        case "button":
            return f'button "{c.get("label")}"→{c.get("action")}'
        case "form":
            fields = ",".join(
                str(f.get("name")) for f in c.get("fields", []) if isinstance(f, dict)
            )
            return f"form→{c.get('action')}({fields})"
        case "workout_plan":
            return f'workout_plan "{c.get("title")}" ({len(c.get("days", []))} days)'
        case "exercise_card":
            return f"exercise_card {c.get('name')}"
        case "card" | "layout":
            inner = [_describe(ch) for ch in c.get("children", []) if isinstance(ch, dict)]
            title = f' "{c["title"]}"' if c.get("title") else ""
            return f"{kind}{title}[{', '.join(inner)}]"
        case _:
            return str(kind)
