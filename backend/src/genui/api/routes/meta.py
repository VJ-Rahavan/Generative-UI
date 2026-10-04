from typing import Any

from fastapi import APIRouter

from genui.api.deps import ContainerDep
from genui.api.schemas import HealthResponse, ToolInfo
from genui.ui.validation import ui_json_schema

router = APIRouter(tags=["meta"])


@router.get("/health", response_model=HealthResponse)
async def health(container: ContainerDep) -> HealthResponse:
    settings = container.settings
    return HealthResponse(
        app=settings.app_name, model=container.llm.model, llm_configured=settings.llm_configured
    )


@router.get("/ui/schema")
async def ui_schema() -> dict[str, Any]:
    """JSON Schema of the UI component catalog (useful for generating frontend types)."""
    return ui_json_schema()


@router.get("/tools", response_model=list[ToolInfo])
async def list_tools(container: ContainerDep) -> list[ToolInfo]:
    return [
        ToolInfo(name=t.name, label=t.label, description=t.description)
        for t in container.tools.tools
    ]
