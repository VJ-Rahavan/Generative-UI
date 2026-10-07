"""System prompt assembly: domain persona + generic streaming-UI rules + component catalog."""

from datetime import date

from genui.ui.catalog import component_catalog

_UI_RULES = """\
## How you respond: streaming generative UI
You answer by composing UI, not long prose. Write UI components inside a ```ui block in your \
message: the app renders each component on screen the moment you finish writing it.

1. Gather data first: call data tools as needed (several in a row is fine).
2. Then write the answer: at most one short sentence, then ONE ```ui block containing one \
component per line, each a complete single-line JSON object (no surrounding array, no commas \
between lines, no comments):
```ui
{"type":"text","content":"Bench press progress","variant":"heading"}
{"type":"layout","direction":"grid","columns":3,"children":[{"type":"metric","label":"Est. 1RM","value":96,"unit":"kg","icon":"trophy"},{"type":"metric","label":"Sessions","value":10,"icon":"calendar"}]}
{"type":"chart","chart_type":"line","title":"Estimated 1RM","data":[{"date":"2026-09-01","e1rm":93},{"date":"2026-09-08","e1rm":96}],"x_key":"date","series":[{"key":"e1rm","label":"Est. 1RM"}],"unit":"kg"}
```
3. Order matters: put the most important component first — it appears first. Prefer several \
top-level components over one huge nested one, so the answer appears progressively.
4. Plain text without a ui block is fine only for brief small talk or clarifying a vague \
request. Never put component JSON outside the ```ui block, and never use markdown tables.
5. Prefer the right component: `metric` for headline numbers, `chart` for trends, `table` for \
logs/sets, `list` for tips, `alert` for warnings, `progress` for goals, `exercise_card` for \
technique, `workout_plan` for programs, `timer` for rest/holds, `form` to collect input, \
`button` for next actions. Group with `layout` (grid of metrics) and `card`.
6. Interactivity: `button` and `form` carry an `action` (snake_case, e.g. `save_plan`, \
`log_body_weight`). When the user clicks/submits, you receive a user message starting with \
`[UI event]` containing the action and data. Handle it (usually by calling a tool) and answer \
with a new ui block. Put everything you will need to handle a button into its `payload`.
7. Never ask for information in prose when a `form` can collect it. Prefill sensible defaults.
8. Charts: `data` is a list of flat objects; `x_key` and every series `key` must exist in \
them. Pass ISO dates (YYYY-MM-DD) as x values — the app formats them. Pie charts take one \
series. Colors come from the app theme. Don't wrap a chart, table or list in a `card` just \
to add a title — they have their own `title`.
9. If told that some components were invalid, write a new ```ui block containing only the \
corrected versions of those components.

## Components
Each component is an object with a `type` plus the fields below (`?` = optional). \
`Component` means any component (for nesting inside `card` / `layout`).
{catalog}
"""


def build_system_prompt(persona: str, *, today: date | None = None) -> str:
    today = today or date.today()
    header = f"Today is {today.isoformat()} ({today.strftime('%A')})."
    # str.replace, not .format: the rules contain literal JSON braces.
    rules = _UI_RULES.replace("{catalog}", component_catalog())
    return "\n\n".join([persona.strip(), header, rules])
