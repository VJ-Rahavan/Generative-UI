# FitTrack: a generative UI fitness coach

FitTrack is an AI fitness coach that **answers with interactive UI instead of text**. Ask "How did
my training go this week?" and the model fetches your real training data, then composes a
dashboard of metrics, charts, tables and buttons on the fly. Clicking a button or submitting a form
sends the interaction back to the model, which acts on it (logging a workout, saving a plan,
calculating macros) and renders the result.

- **Backend:** Python 3.12, FastAPI, LangChain (`ChatGroq` + `StructuredTool`s) on Groq (`openai/gpt-oss-120b`),
  Pydantic v2, SQLAlchemy 2 (async), optional LangSmith tracing
- **Frontend:** React 19, TypeScript, Vite, Tailwind CSS v4, Recharts

## How it works

```
 User message / UI event
          │
          ▼
 POST /api/chat ──► Agent loop (backend/src/genui/agent/agent.py)
                      │  1. Stream the LLM (LangChain ChatGroq). It calls data tools
                      │     (read/write workouts, metrics, plans…) as needed, then writes
                      │     its answer with a ```ui block: one JSON component per line.
                      │  2. AnswerStreamParser (ui/stream.py) reads the text as it streams,
                      │     validates each component against the Pydantic catalog the
                      │     moment its JSON closes, and emits it immediately.
                      │     Invalid → only those components go back to the model to fix.
                      │  3. Persist every step; stream events to the browser (SSE).
                      ▼
 SSE events: text · tool_start/tool_end · ui_start · ui_component (×N) · ui_end
             · status · error · done
          │
          ▼
 React renderer: one component per catalog type (frontend/src/components/genui/)
          │
 Button click / form submit ──► POST /api/chat { event: {action, payload} } ──► …
```

**Why the UI streams as text.** Groq sends a tool call's arguments in one piece at the end,
so UI passed through a tool call can only appear all at once. Message text streams token by
token, so the model writes components as text and each one appears as soon as it has been
generated, with a skeleton showing while the next is on its way.

**Why it's safe.** The model never writes HTML or JavaScript. It can only pick from a fixed
catalog of 14 components, and the backend validates every component before it reaches the
browser.

| Component | Use |
|---|---|
| `text`, `metric`, `card`, `layout`, `table`, `chart` (line/bar/area/pie), `list`, `alert`, `progress` | General display |
| `button`, `form` | Interaction: sends `action` + `payload` back to the agent |
| `exercise_card`, `workout_plan`, `timer` | Fitness-specific |

## Quick start

Prerequisites: [uv](https://docs.astral.sh/uv/), Node 20+ and a [Groq API key](https://console.groq.com/keys).

```bash
make install          # uv sync + npm install; creates backend/.env from the example
# put your key in backend/.env →  GROQ_API_KEY=gsk_...
make dev              # backend on :8010, frontend on :5180
```

Open **http://localhost:5180**. On first start the backend creates `backend/fittrack.db` and seeds
8 weeks of demo training and body-weight history, so the dashboards have data straight away.

Other commands: `make backend`, `make frontend`, `make lint`, `make format`, `make build`,
`make reset-db` (wipes the DB; demo data is re-seeded on the next start). Run `make help` for the list.

## Project structure

```
backend/src/genui/
  main.py               App factory and lifespan (DB, seeding, LLM, agent wiring)
  core/                 Settings (env/.env), logging, schema helpers
  db/                   Async engine/session (create_all, no migrations), chat tables
  ui/
    components.py       ★ The component catalog (Pydantic): the LLM ↔ frontend contract
    validation.py       Validates one component at a time
    stream.py           ★ Streaming parser: prose + ```ui block → validated components as they arrive
    catalog.py          Compact catalog text for the system prompt (generated from the models)
  llm/                  LLMProvider protocol + LangChain implementation (ChatGroq, message conversion)
  tools/registry.py     @registry.tool → LangChain StructuredTool; register() accepts any LangChain tool
  agent/
    agent.py            ★ The agent loop (streaming, tools, UI validation/repair, retries)
    prompts.py          Generic streaming-UI rules (```ui block format) + component catalog
    history.py          Compacts earlier turns to save tokens
    events.py           SSE event types
  services/             Conversation repository, grouping messages into turns
  api/                  FastAPI routes (chat SSE, conversations, health, schema)
  domain/fitness/       Exercise library, fitness tables, 11 tools, persona prompt, demo seed

frontend/src/
  App.tsx               Layout: sidebar, message list, message box
  hooks/useChat.ts      Stream state (turns, tool activity, status, stop/load/reset)
  lib/api.ts, sse.ts    API client and the POST stream reader
  types/ui.ts           TypeScript mirror of the component catalog
  components/genui/     ★ UIRenderer (type → React component registry) and one view per component
  components/chat/      Messages, Composer, EmptyState
```

## Extending it

### Add a data tool

Write an async function with a Pydantic arguments model in `backend/src/genui/domain/fitness/tools.py`:

```python
class StreakArgs(BaseModel):
    weeks: int = Field(12, ge=1, le=52)

@registry.tool(label="Calculating your streak")
async def get_training_streak(args: StreakArgs, ctx: ToolContext) -> dict[str, Any]:
    """Consecutive weeks with at least one workout."""   # ← becomes the tool description
    ...
```

The decorator wraps the function in a LangChain `StructuredTool`: the arguments model becomes
its `args_schema` (the JSON schema the LLM sees) and validates what the LLM sends. The
per-request `ToolContext` (user id, DB sessions) is passed through LangChain's `RunnableConfig`,
so the model never sees it. Raise `ToolError("…")` for expected failures; the message goes back
to the model.

Ready-made LangChain tools plug in directly:

```python
from langchain_core.tools import tool

@tool
def convert_lb_to_kg(pounds: float) -> float:
    """Convert pounds to kilograms."""
    return round(pounds * 0.453592, 2)

registry.register(convert_lb_to_kg, label="Converting units")
```

### Switch LLM provider

The agent only depends on a LangChain `BaseChatModel`. To use another provider, install its
integration (e.g. `uv add langchain-openai`) and return that model from `build_chat_model()` in
`backend/src/genui/llm/langchain_provider.py`. The provider needs to support tool calling and
streaming.

### Add a UI component

1. **Backend:** add a model to `ui/components.py` with `type: Literal["your_type"]` and include
   it in the `Component` union. The prompt catalog and validation update automatically.
2. **Frontend:** add the matching interface to `types/ui.ts` and a view in
   `components/genui/components/`, then register it in `UIRenderer.tsx`. TypeScript fails the
   build until every type in the catalog has a renderer.

### Switch domain

The engine (`agent/`, `ui/`, `llm/`, `tools/`) knows nothing about fitness. A new domain needs
its own tool registry, persona prompt and tables, wired up in `main.py`.

## Configuration

Settings come from environment variables or `backend/.env` (see `backend/.env.example`).

| Variable | Default | Notes |
|---|---|---|
| `GROQ_API_KEY` | — | Required for chat |
| `GROQ_MODEL` | `openai/gpt-oss-120b` | Any Groq chat model with tool calling |
| `LLM_REASONING_EFFORT` | `medium` | `low` / `medium` / `high`; only sent to gpt-oss models |
| `LLM_MAX_RETRIES` | `3` | Retries on rate limits and server errors, shown to the user as a status message |
| `AGENT_MAX_STEPS` / `AGENT_MAX_UI_REPAIRS` | `8` / `2` | Limits per turn |
| `HISTORY_MAX_MESSAGES` | `40` | Messages from earlier turns sent to the model (compacted) |
| `LANGSMITH_TRACING` / `LANGSMITH_API_KEY` / `LANGSMITH_PROJECT` | `false` / — / `fittrack` | Optional tracing: each chat turn is one trace, with its LLM and tool calls nested inside |
| `DATABASE_URL` | `sqlite+aiosqlite:///./fittrack.db` | For Postgres: `postgresql+asyncpg://…` and `uv sync --extra postgres` |
| `SEED_DEMO_DATA` | `true` | Seeds demo history for an empty user |
| `PORT` / `CORS_ORIGINS` | `8010` / `["http://localhost:5180"]` | |

Frontend: `frontend/.env.local` can set `VITE_API_TARGET` (where the dev server forwards `/api`)
or `VITE_API_BASE` (call the API directly).

### Groq free tier

The free tier allows **8,000 tokens per minute** for `gpt-oss-120b`. One answer usually takes 2 LLM
calls of about 4–5k tokens, so after roughly one answer per minute you'll see *"Groq rate limit
reached, continuing in Ns…"* while the agent waits and retries. The prompt is already kept small:
a compact component catalog, and earlier turns are compacted. For unrestricted use, upgrade to
Groq's Dev tier.

## API

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/chat` | `{conversation_id?, message}` or `{conversation_id?, event: {action, payload, label?}}` → SSE stream |
| `GET` | `/api/conversations` | List conversations |
| `GET` | `/api/conversations/{id}` | Conversation with its rendered turns |
| `DELETE` | `/api/conversations/{id}` | Delete a conversation |
| `GET` | `/api/health` | Status, model, whether the LLM is configured |
| `GET` | `/api/ui/schema` | JSON Schema of the component catalog |
| `GET` | `/api/tools` | Registered tools |

Interactive API docs: http://localhost:8010/docs

## Not done yet (deliberately deferred)

- **Security:** authentication (everything runs as a single `demo` user; every table already
  has a `user_id` column), input limits per user
- **Rate limiting** per user/IP
- **Observability:** structured logs and metrics (LLM and tool tracing is available through LangSmith)
- **Testing:** pytest with a fake LLM (the provider is behind a protocol) and frontend tests
- **LangGraph:** skipped for now. The tools are already LangChain tools, so a LangGraph agent could reuse them
  if we need human approval steps, multiple agents or resumable workflows
- **Deployment:** Docker, docker-compose (API + web + Postgres), CI
- **Schema migrations:** tables are created with `create_all`; schema changes currently need `make reset-db`
