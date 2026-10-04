from fastapi import APIRouter, HTTPException, Query, Response, status

from genui.api.deps import SessionDep, UserIdDep
from genui.api.schemas import ConversationDetail, ConversationSummary, Turn
from genui.services.conversations import ConversationRepository, build_turns

router = APIRouter(prefix="/conversations", tags=["conversations"])


@router.get("", response_model=list[ConversationSummary])
async def list_conversations(
    session: SessionDep, user_id: UserIdDep, limit: int = Query(50, ge=1, le=200)
) -> list[ConversationSummary]:
    conversations = await ConversationRepository(session).list_for_user(user_id, limit=limit)
    return [ConversationSummary.model_validate(c) for c in conversations]


@router.get("/{conversation_id}", response_model=ConversationDetail)
async def get_conversation(
    conversation_id: str, session: SessionDep, user_id: UserIdDep
) -> ConversationDetail:
    repo = ConversationRepository(session)
    conversation = await repo.get(conversation_id, user_id)
    if conversation is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found")
    turns = build_turns(await repo.messages(conversation.id))
    return ConversationDetail(
        **ConversationSummary.model_validate(conversation).model_dump(),
        turns=[Turn.model_validate(t) for t in turns],
    )


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(
    conversation_id: str, session: SessionDep, user_id: UserIdDep
) -> Response:
    repo = ConversationRepository(session)
    conversation = await repo.get(conversation_id, user_id)
    if conversation is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found")
    await repo.delete(conversation)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
