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


@dataclass
class EnclosedMarkerResult:
    """A marker extraction plus the enclosing source range that contains it."""

    marker_text: str
    marker_start_line: int
    marker_end_line: int
    enclosure_text: str
    enclosure_start_line: int
    enclosure_end_line: int
    enclosure_kind: Optional[str] = None
    enclosure_name: Optional[str] = None

    @property
    def text(self) -> str:
        """Marker text, matching the legacy extraction result shape."""
        return self.marker_text

    @property
    def start_line(self) -> int:
        """Marker start line, matching the legacy extraction result shape."""
        return self.marker_start_line

    @property
    def end_line(self) -> int:
        """Marker end line, matching the legacy extraction result shape."""
        return self.marker_end_line

    def to_tuple(self) -> tuple:
        """For backwards compatibility with marker extraction APIs."""
        return (self.marker_text, self.marker_start_line, self.marker_end_line)
