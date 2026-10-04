"""Shared FastAPI dependencies."""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from genui.agent import ChatAgent
from genui.core.config import Settings
from genui.db.session import Database
from genui.llm import LLMProvider
from genui.tools import ToolRegistry


@dataclass(slots=True)
class AppContainer:
    """Long-lived services, built once in the app lifespan."""

    settings: Settings
    db: Database
    llm: LLMProvider
    tools: ToolRegistry
    agent: ChatAgent


def get_container(request: Request) -> AppContainer:
    container: AppContainer = request.app.state.container
    return container


async def get_session(
    container: Annotated[AppContainer, Depends(get_container)],
) -> AsyncIterator[AsyncSession]:
    async with container.db.session() as session:
        yield session


def get_user_id(container: Annotated[AppContainer, Depends(get_container)]) -> str:
    # Single demo user until authentication is added.
    return container.settings.default_user_id


ContainerDep = Annotated[AppContainer, Depends(get_container)]
SessionDep = Annotated[AsyncSession, Depends(get_session)]
UserIdDep = Annotated[str, Depends(get_user_id)]
