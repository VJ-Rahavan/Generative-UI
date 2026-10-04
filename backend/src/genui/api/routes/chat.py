from collections.abc import AsyncIterator

from fastapi import APIRouter, HTTPException, status
from sse_starlette import EventSourceResponse

from genui.agent import UserInput
from genui.api.deps import ContainerDep, SessionDep, UserIdDep
from genui.api.schemas import ChatRequest
from genui.services.conversations import ConversationRepository

router = APIRouter(tags=["chat"])


@router.post("/chat", response_class=EventSourceResponse)
async def chat(
    body: ChatRequest, container: ContainerDep, session: SessionDep, user_id: UserIdDep
) -> EventSourceResponse:
    """Run one assistant turn and stream events as Server-Sent Events.

    Send either a typed `message` or a UI `event` (button click / form submit).
    Omit `conversation_id` to start a new conversation; its id arrives in the first event.
    """
    if body.conversation_id:
        repo = ConversationRepository(session)
        if await repo.get(body.conversation_id, user_id) is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found")

    if body.event is not None:
        user_input = UserInput.from_event(body.event.action, body.event.payload, body.event.label)
    else:
        user_input = UserInput.from_message(body.message or "")

    async def stream() -> AsyncIterator[dict[str, str]]:
        async for event in container.agent.run(
            user_id=user_id, conversation_id=body.conversation_id, user_input=user_input
        ):
            yield event.to_sse()

    return EventSourceResponse(stream(), ping=15)
