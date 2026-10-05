"""System prompt assembly and the `render_ui` tool definition."""

from datetime import date
from typing import Any

from genui.ui.catalog import component_catalog

RENDER_UI_TOOL = "render_ui"

RENDER_UI_SPEC: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": RENDER_UI_TOOL,
        "description": (
            "Render interactive UI components to the user. `components` is an ordered list of "
            "component objects that must follow the component catalog in the system prompt. "
            "Call this once per answer, after gathering any data you need."
        ),
        # Kept deliberately loose: Groq rejects the whole generation if arguments don't match
        # the declared schema. Strict validation happens server-side with actionable errors.
        "parameters": {
            "type": "object",
            "properties": {
                "components": {
                    "type": "array",
                    "items": {"type": "object"},
                    "description": "UI components (see the component catalog).",
                }
            },
            "required": ["components"],
        },
    },
}

_UI_RULES = """\
## How you respond: generative UI
You answer by composing UI, not long prose. The app renders the components you pass to the \
`render_ui` tool.

1. Gather data first: call data tools as needed (several in a row is fine).
2. Then call `render_ui` exactly once with the full answer. Put the key message in the UI \
itself (e.g. a `text` heading/body); keep any plain chat text to one short sentence or none.
3. Plain text without `render_ui` is fine only for brief small talk or clarifying a vague \
request.
4. Prefer the right component: `metric` for headline numbers, `chart` for trends, `table` for \
logs/sets, `list` for tips, `alert` for warnings, `progress` for goals, `exercise_card` for \
technique, `workout_plan` for programs, `timer` for rest/holds, `form` to collect input, \
`button` for next actions. Group with `layout` (grid of metrics) and `card`.
5. Interactivity: `button` and `form` carry an `action` (snake_case, e.g. `save_plan`, \
`log_body_weight`). When the user clicks/submits, you receive a user message starting with \
`[UI event]` containing the action and data. Handle it (usually by calling a tool) and render \
the result. Put everything you will need to handle a button into its `payload`.
6. Never ask for information in prose when a `form` can collect it. Prefill sensible defaults.
7. Charts: `data` is a list of flat objects; `x_key` and every series `key` must exist in \
them. Pass ISO dates (YYYY-MM-DD) as x values — the app formats them. Pie charts take one \
series. Colors come from the app theme. Don't wrap a chart, table or list in a `card` just \
to add a title — they have their own `title`.
8. If `render_ui` returns a validation error, fix exactly those issues and call it again.
9. Never write component JSON, raw HTML or markdown tables in your message text — the user \
only sees UI passed through the `render_ui` tool call. This applies to follow-ups after \
[UI event] messages too.

## Components
Each component is an object with a `type` plus the fields below (`?` = optional). \
`Component` means any component (for nesting inside `card` / `layout`).
{catalog}
"""


def build_system_prompt(persona: str, *, today: date | None = None) -> str:
    today = today or date.today()
    header = f"Today is {today.isoformat()} ({today.strftime('%A')})."
    return "\n\n".join([persona.strip(), header, _UI_RULES.format(catalog=component_catalog())])
