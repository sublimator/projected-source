"""Extract the declarative `review_scope` variable from a template's source.

`review_scope` must be a *literal* dict assigned at module scope so the CLI can
read it before `ChangesSet.from_diff()` runs — without rendering, which would be
too late (the ChangesSet is already built) and could side-effect. Because it is
read from the entry template's AST, a `review_scope` inside an {% include %}d
child is invisible: "declare scope in the entry template" holds structurally.

See .ai-docs/specs/audit-verb-and-change-partition.md §5.
"""

import logging
from typing import Any, Dict, Optional

import jinja2
from jinja2 import nodes

from .renderer import ChunkExtension, CodeContextExtension

logger = logging.getLogger(__name__)

ALLOWED_KEYS = {"base", "include", "exclude"}


class ReviewScopeError(ValueError):
    """A review_scope that is present but non-literal or schema-invalid."""


def extract_review_scope(source: str) -> Optional[Dict[str, Any]]:
    """Return the schema-checked review_scope, or None if the template has none.

    A non-literal value (a variable or call the pre-pass cannot evaluate) or a
    schema violation raises ReviewScopeError — a review_scope that silently
    mis-scopes is worse than none.
    """
    # Same extension set as the renderer so a template using {% code_context %}
    # still parses; a genuinely broken template is left to surface its own error
    # at render time rather than here.
    env = jinja2.Environment(extensions=[CodeContextExtension, ChunkExtension])
    try:
        ast = env.parse(source)
    except jinja2.TemplateSyntaxError as exc:
        # Don't let a template that declares a scope lose it silently just
        # because the minimal pre-pass env can't parse a render-time construct
        # (a project extension, {% do %}, etc.) — warn so it isn't mistaken for
        # "no scope" (F15).
        if "review_scope" in source:
            logger.warning(
                "Template declares review_scope but the scope pre-pass could not parse it "
                "(%s); review_scope was NOT applied.",
                exc,
            )
        return None

    for node in ast.body:
        if (
            isinstance(node, nodes.Assign)
            and isinstance(node.target, nodes.Name)
            and node.target.name == "review_scope"
        ):
            try:
                value = node.node.as_const()  # type: ignore[attr-defined]  # jinja2 nodes have as_const() at runtime
            except nodes.Impossible:
                raise ReviewScopeError(
                    "review_scope must be a literal dict (no variables or calls)"
                )
            return _validate(value)
    return None


def _validate(value: Any) -> Dict[str, Any]:
    if not isinstance(value, dict):
        raise ReviewScopeError("review_scope must be a dict")

    unknown = set(value) - ALLOWED_KEYS
    if unknown:
        raise ReviewScopeError(f"review_scope has unknown keys: {sorted(unknown)}")

    base = value.get("base")
    if base is not None and not isinstance(base, str):
        raise ReviewScopeError("review_scope.base must be a string or null")

    normalized: Dict[str, Any] = {"base": base}
    for key, default in (("include", ["**"]), ("exclude", [])):
        raw = value.get(key, default)
        if not isinstance(raw, list) or not all(isinstance(x, str) for x in raw):
            raise ReviewScopeError(f"review_scope.{key} must be a list of strings")
        normalized[key] = list(raw)
    return normalized


def read_template_scope(template_path) -> Optional[Dict[str, Any]]:
    """extract_review_scope() for a file path; None if unreadable."""
    try:
        source = open(template_path, encoding="utf-8").read()
    except OSError:
        return None
    return extract_review_scope(source)
