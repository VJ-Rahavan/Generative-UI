"""Parse and validate `render_ui` tool-call arguments produced by the LLM."""

import json
from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError

from genui.core.schema_utils import format_validation_error, strip_titles
from genui.ui.components import UISpec

MAX_NESTING_DEPTH = 6


@dataclass(slots=True)
class UIParseResult:
    ok: bool
    components: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None


def parse_ui_arguments(raw: str | dict[str, Any] | list[Any]) -> UIParseResult:
    """Validate raw tool arguments into JSON-ready component dicts.

    Lenient about envelope shape (bare list, JSON-encoded string), strict about components.
    """
    try:
        data: Any = json.loads(raw) if isinstance(raw, str) else raw
        if isinstance(data, list):
            data = {"components": data}
        if isinstance(data, dict) and isinstance(data.get("components"), str):
            data["components"] = json.loads(data["components"])
    except json.JSONDecodeError as exc:
        return UIParseResult(ok=False, error=f"Arguments are not valid JSON: {exc}")

    try:
        spec = UISpec.model_validate(data)
    except ValidationError as exc:
        return UIParseResult(ok=False, error=format_validation_error(exc))

    components = [c.model_dump(mode="json", exclude_none=True) for c in spec.components]
    depth = max(_depth(c) for c in components)
    if depth > MAX_NESTING_DEPTH:
        return UIParseResult(
            ok=False, error=f"Components nested {depth} levels deep; max is {MAX_NESTING_DEPTH}."
        )
    return UIParseResult(ok=True, components=components)


def ui_json_schema() -> dict[str, Any]:
    """Schema of `UISpec` (with $defs, since components are recursive) for prompts/clients."""
    return strip_titles(UISpec.model_json_schema())


def _depth(node: dict[str, Any]) -> int:
    children = node.get("children") or []
    return 1 + max((_depth(c) for c in children), default=0)
