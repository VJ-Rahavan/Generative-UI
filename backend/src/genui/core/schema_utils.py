"""Helpers for turning Pydantic models into compact, LLM-friendly JSON schemas."""

import copy
from typing import Any

from pydantic import BaseModel, ValidationError


def strip_titles(node: Any, *, in_properties: bool = False) -> Any:
    """Remove auto-generated `title` keys (but keep properties that are *named* title)."""
    if isinstance(node, dict):
        out: dict[str, Any] = {}
        for key, value in node.items():
            if not in_properties and key == "title" and isinstance(value, str):
                continue
            out[key] = strip_titles(value, in_properties=key in ("properties", "$defs"))
        return out
    if isinstance(node, list):
        return [strip_titles(item) for item in node]
    return node


def inline_refs(schema: dict[str, Any]) -> dict[str, Any]:
    """Inline non-recursive `$ref`s so tool parameter schemas are flat and self-contained."""
    defs = schema.get("$defs", {})

    def resolve(node: Any, seen: frozenset[str]) -> Any:
        if isinstance(node, dict):
            ref = node.get("$ref")
            if isinstance(ref, str) and ref.startswith("#/$defs/"):
                name = ref.removeprefix("#/$defs/")
                if name in seen:  # recursive type: leave the ref in place
                    return node
                target = copy.deepcopy(defs[name])
                extras = {k: v for k, v in node.items() if k != "$ref"}
                return resolve({**target, **extras}, seen | {name})
            return {k: resolve(v, seen) for k, v in node.items() if k != "$defs"}
        if isinstance(node, list):
            return [resolve(item, seen) for item in node]
        return node

    return resolve(schema, frozenset())


def llm_json_schema(model: type[BaseModel], *, inline: bool = True) -> dict[str, Any]:
    schema = model.model_json_schema()
    if inline:
        schema = inline_refs(schema)
    return strip_titles(schema)


def format_validation_error(exc: ValidationError, *, max_errors: int = 15) -> str:
    """Render a ValidationError as short `path: message` lines the LLM can act on."""
    lines = []
    for err in exc.errors()[:max_errors]:
        path = ".".join(str(p) for p in err["loc"]) or "<root>"
        lines.append(f"- {path}: {err['msg']}")
    remaining = len(exc.errors()) - max_errors
    if remaining > 0:
        lines.append(f"- ... and {remaining} more errors")
    return "\n".join(lines)
