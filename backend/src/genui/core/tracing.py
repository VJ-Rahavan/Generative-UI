"""Optional LangSmith tracing.

LangSmith reads its settings from process environment variables, while our settings may come
from `.env` via pydantic-settings — so export them explicitly at startup.
"""

import logging
import os

from genui.core.config import Settings

logger = logging.getLogger(__name__)


def configure_tracing(settings: Settings) -> None:
    if not settings.langsmith_tracing:
        return
    if not (settings.langsmith_api_key and settings.langsmith_api_key.get_secret_value()):
        logger.warning("LANGSMITH_TRACING is on but LANGSMITH_API_KEY is missing; not tracing.")
        return
    os.environ["LANGSMITH_TRACING"] = "true"
    os.environ["LANGSMITH_API_KEY"] = settings.langsmith_api_key.get_secret_value()
    os.environ["LANGSMITH_PROJECT"] = settings.langsmith_project
    logger.info("LangSmith tracing enabled (project=%s)", settings.langsmith_project)
