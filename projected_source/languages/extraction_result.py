"""
Data class for extraction results with all the info you might need.
"""

from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class ExtractionResult:
    """Result from extracting code elements."""

    text: str
    start_line: int
    end_line: int
    start_column: int = 0
    end_column: int = 0
    node: Optional[Any] = None  # tree-sitter Node
    node_type: Optional[str] = None
    qualified_name: Optional[str] = None

    @property
    def line_count(self) -> int:
        """Number of lines in the extracted text."""
        return self.end_line - self.start_line + 1

    @property
    def location(self) -> str:
        """Human-readable location string."""
        if self.start_line == self.end_line:
            return f"line {self.start_line}"
        return f"lines {self.start_line}-{self.end_line}"

    def to_tuple(self) -> tuple:
        """For backwards compatibility."""
        return (self.text, self.start_line, self.end_line)
