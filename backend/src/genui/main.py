"""FastAPI application factory and entry point (`uv run genui`)."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from genui.agent import ChatAgent, build_system_prompt
from genui.api.deps import AppContainer
from genui.api.router import api_router
from genui.core.config import get_settings
from genui.core.logging import configure_logging
from genui.core.tracing import configure_tracing
from genui.db.session import Database
from genui.domain.fitness.prompt import FITNESS_PERSONA
from genui.domain.fitness.seed import seed_demo_data
from genui.domain.fitness.tools import registry as fitness_tools
from genui.llm import LangChainProvider, build_chat_model

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings.log_level)
    configure_tracing(settings)

    db = Database(settings.database_url, echo=settings.database_echo)
    await db.create_all()
    if settings.seed_demo_data:
        await seed_demo_data(db.session_factory, settings.default_user_id)

    llm = LangChainProvider(build_chat_model(settings), model_name=settings.groq_model)
    if not settings.llm_configured:
        logger.warning("GROQ_API_KEY is not set — chat requests will return an error event.")

    agent = ChatAgent(
        llm=llm,
        tools=fitness_tools,
        session_factory=db.session_factory,
        settings=settings,
        system_prompt=lambda: build_system_prompt(FITNESS_PERSONA),
    )
    app.state.container = AppContainer(
        settings=settings, db=db, llm=llm, tools=fitness_tools, agent=agent
    )
    logger.info("%s ready (model=%s)", settings.app_name, llm.model)
    try:
        yield
    finally:
        await llm.aclose()
        await db.dispose()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=f"{settings.app_name} API", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(api_router, prefix=settings.api_prefix)
    return app


app = create_app()


def run() -> None:
    settings = get_settings()
    uvicorn.run("genui.main:app", host=settings.host, port=settings.port, reload=settings.is_dev)
