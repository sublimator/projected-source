"""
Custom tags support for projected-source.

This module provides types and utilities for projects to define their own
custom Jinja2 tags via a .projected-source.py file.
"""

from pathlib import Path
from typing import TYPE_CHECKING, Protocol

# Re-export jinja2.Environment for convenience
from jinja2 import Environment

if TYPE_CHECKING:
    from .core.renderer import TemplateRenderer


class CustomTagsProvider(Protocol):
    """Protocol for custom tag providers (optional - for type checking)."""

    def setup_custom_tags(self, env: Environment, renderer: "TemplateRenderer") -> None:
        """
        Register custom tags with the Jinja2 environment.

        Args:
            env: The Jinja2 Environment to register tags with
            renderer: The TemplateRenderer instance (has _code_function, etc.)
        """
        ...


# Export commonly needed types
__all__ = [
    "Environment",
    "Path",
    "CustomTagsProvider",
]
