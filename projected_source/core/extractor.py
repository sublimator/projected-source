"""
Tree-sitter based code extraction with comment directive support.
"""

import logging
import re
from pathlib import Path
from typing import Dict, List, Tuple

from tree_sitter import Language, Node, Parser, Query, QueryCursor

logger = logging.getLogger(__name__)


class BaseExtractor:
    """Base class for language-specific extractors."""

    def __init__(self, language):
        self.language = language
        self.parser = Parser(language)

    def parse_file(self, file_path: Path) -> Node:
        """Parse a file and return the root node."""
        source = file_path.read_bytes()
        tree = self.parser.parse(source)
        return tree.root_node

    def parse_bytes(self, source: bytes) -> Node:
        """Parse source bytes and return the root node."""
        tree = self.parser.parse(source)
        return tree.root_node

    def extract_lines(self, file_path: Path, start_line: int, end_line: int) -> Tuple[str, int, int]:
        """
        Extract lines from a file.

        Returns:
            Tuple of (code_text, start_line, end_line)
        """
        lines = file_path.read_text().splitlines()
        # Convert to 0-based indexing
        start = max(0, start_line - 1)
        end = min(len(lines), end_line)

        code_lines = lines[start:end]
        return "\n".join(code_lines), start_line, end_line

    def find_markers_in_node(self, node: Node) -> Dict[str, Tuple[int, int]]:
        """
        Find comment markers within a given node.

        Uses tree-sitter queries with predicates to find //@@start and //@@end markers.

        Args:
            node: The node to search within (e.g., function body or root)

        Returns:
            Dict mapping marker names to (start_line, end_line) tuples
        """
        # Query for ALL comments first (no predicate)
        comment_query = Query(self.language, "(comment) @comment")
        cursor = QueryCursor(comment_query)
        matches = cursor.matches(node)

        markers = {}
        active_markers = {}  # Track open markers

        for _, captures in matches:
            comments = captures.get("comment", [])
            for comment in comments:
                if not comment or not comment.text:
                    continue

                text = comment.text.decode("utf8")
                line_num = comment.start_point.row + 1

                # Check for marker patterns in the comment text
                # Using Python regex since tree-sitter regex can be tricky
                if "//@@start" in text:
                    match = re.search(r"//@@start\s+([\w-]+)", text)
                    if match:
                        marker_name = match.group(1)
                        # Store the line AFTER the comment
                        active_markers[marker_name] = line_num + 1
                        logger.debug(f"Found start marker '{marker_name}' at line {line_num}")

                elif "//@@end" in text:
                    match = re.search(r"//@@end\s+([\w-]+)", text)
                    if match:
                        marker_name = match.group(1)
                        if marker_name in active_markers:
                            start_line = active_markers.pop(marker_name)
                            # End at line BEFORE the comment
                            end_line = line_num - 1
                            markers[marker_name] = (start_line, end_line)
                            logger.debug(f"Found end marker '{marker_name}' at line {line_num}")
                        else:
                            logger.warning(f"Found //@@end {marker_name} without matching //@@start")

        # Warn about unclosed markers
        for marker_name in active_markers:
            logger.warning(f"Marker '{marker_name}' was not closed with //@@end")

        return markers

    def find_markers_in_file(self, file_path: Path) -> Dict[str, Tuple[int, int]]:
        """Find all markers in a file."""
        root = self.parse_file(file_path)
        return self.find_markers_in_node(root)

    def extract_marker(self, file_path: Path, marker_name: str) -> Tuple[str, int, int]:
        """
        Extract code between marker comments.

        Returns:
            Tuple of (code_text, start_line, end_line)
        """
        markers = self.find_markers_in_file(file_path)

        if marker_name not in markers:
            available = ", ".join(markers.keys()) if markers else "none"
            raise ValueError(f"Marker '{marker_name}' not found. Available markers: {available}")

        start_line, end_line = markers[marker_name]
        return self.extract_lines(file_path, start_line, end_line)

    def extract_function(self, file_path: Path, function_name: str) -> Tuple[str, int, int]:
        """
        Extract a function by name.
        Must be implemented by language-specific subclasses.
        """
        raise NotImplementedError("Subclasses must implement extract_function")


class MarkerExtractor:
    """Helper class for finding markers with tree-sitter predicates."""

    @staticmethod
    def find_directive_comments(node: Node, language: Language) -> List[Node]:
        """
        Find comments containing //@@ directives using tree-sitter predicates.

        CRITICAL: Use double parentheses for predicates!
        """
        # Try using #match? predicate - with proper double parens!
        query_text = """
        ((comment) @comment 
          (#match? @comment "//@@"))
        """

        try:
            query = Query(language, query_text)
            cursor = QueryCursor(query)
            matches = cursor.matches(node)

            directive_comments = []
            for _, captures in matches:
                comments = captures.get("comment", [])
                directive_comments.extend(comments)

            logger.debug(f"Found {len(directive_comments)} directive comments using predicate")
            return directive_comments

        except Exception as e:
            logger.warning(f"Predicate query failed: {e}, falling back to manual filtering")

            # Fallback: get all comments and filter manually
            simple_query = Query(language, "(comment) @comment")
            cursor = QueryCursor(simple_query)
            matches = cursor.matches(node)

            directive_comments = []
            for _, captures in matches:
                comments = captures.get("comment", [])
                for comment in comments:
                    if comment and comment.text and "//@@" in comment.text.decode("utf8"):
                        directive_comments.append(comment)

            return directive_comments
