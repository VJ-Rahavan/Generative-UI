"""Events streamed from the agent to the client (sent as SSE `event:` / `data:` pairs).

conversation  {conversation_id, title}        first event of every stream
text          {delta}                         assistant prose chunk
tool_start    {id, name, label}               a data tool started
tool_end      {id, name, ok}                  a data tool finished
ui_start      {id}                            a UI block opened (more components coming)
ui_component  {id, component}                 one validated component, streamed as generated
ui_end        {id}                            the UI block is complete
status        {message}                       transient progress note (rate limit, repair)
error         {message, code}                 recoverable failure for this turn
done          {}                              always the last event
"""

import json
from dataclasses import dataclass
from typing import Any, Literal

EventType = Literal[
    "conversation",
    "text",
    "tool_start",
    "tool_end",
    "ui_start",
    "ui_component",
    "ui_end",
    "status",
    "error",
    "done",
]


@dataclass(slots=True, frozen=True)
class AgentEvent:
    type: EventType
    data: dict[str, Any]

    def to_sse(self) -> dict[str, str]:
        return {"event": self.type, "data": json.dumps(self.data, default=str)}
