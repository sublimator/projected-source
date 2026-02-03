"""
Protocol Buffers (.proto) code extraction using tree-sitter.

Uses coder3101/tree-sitter-proto grammar which supports both proto2 and proto3.
"""

import ctypes
import logging
import re
from pathlib import Path
from typing import Dict, Optional, Tuple

from tree_sitter import Language, Node, Parser

from ..core.extractor import BaseExtractor

logger = logging.getLogger(__name__)

# Load the proto grammar from bundled .so file
_PROTO_SO_PATH = Path(__file__).parent / "proto_grammar" / "proto.so"


def _load_proto_language() -> Language:
    """Load the proto language from the bundled .so file."""
    if not _PROTO_SO_PATH.exists():
        raise RuntimeError(
            f"Proto grammar not found at {_PROTO_SO_PATH}. See .ai-docs/proto-investigations.md for build instructions."
        )
    lib = ctypes.CDLL(str(_PROTO_SO_PATH))
    lib.tree_sitter_proto.restype = ctypes.c_void_p
    return Language(lib.tree_sitter_proto())


class ProtoExtractor(BaseExtractor):
    """Protocol Buffers extractor with message/enum extraction support."""

    def __init__(self):
        self._language = _load_proto_language()
        super().__init__(self._language)
        self._parser = Parser(self._language)

    def extract_message(self, file_path: Path, message_name: str) -> Tuple[str, int, int]:
        """
        Extract a message definition by name.

        Args:
            file_path: Path to the .proto file
            message_name: Name of the message to extract

        Returns:
            Tuple of (code_text, start_line, end_line)
        """
        source = file_path.read_bytes()
        tree = self._parser.parse(source)

        node = self._find_message(tree.root_node, message_name)
        if not node:
            raise ValueError(f"Message '{message_name}' not found in {file_path}")

        text = node.text.decode("utf8") if node.text else ""
        return text, node.start_point.row + 1, node.end_point.row + 1

    def extract_enum(self, file_path: Path, enum_name: str) -> Tuple[str, int, int]:
        """
        Extract an enum definition by name.

        Args:
            file_path: Path to the .proto file
            enum_name: Name of the enum to extract

        Returns:
            Tuple of (code_text, start_line, end_line)
        """
        source = file_path.read_bytes()
        tree = self._parser.parse(source)

        node = self._find_enum(tree.root_node, enum_name)
        if not node:
            raise ValueError(f"Enum '{enum_name}' not found in {file_path}")

        text = node.text.decode("utf8") if node.text else ""
        return text, node.start_point.row + 1, node.end_point.row + 1

    def extract_service(self, file_path: Path, service_name: str) -> Tuple[str, int, int]:
        """
        Extract a service definition by name.

        Args:
            file_path: Path to the .proto file
            service_name: Name of the service to extract

        Returns:
            Tuple of (code_text, start_line, end_line)
        """
        source = file_path.read_bytes()
        tree = self._parser.parse(source)

        node = self._find_service(tree.root_node, service_name)
        if not node:
            raise ValueError(f"Service '{service_name}' not found in {file_path}")

        text = node.text.decode("utf8") if node.text else ""
        return text, node.start_point.row + 1, node.end_point.row + 1

    def extract_marker(self, file_path: Path, marker_name: str) -> Tuple[str, int, int]:
        """
        Extract content between marker comments.

        Markers use the syntax:
            //@@start marker-name
            ... content ...
            //@@end marker-name

        Args:
            file_path: Path to the .proto file
            marker_name: Name of the marker

        Returns:
            Tuple of (code_text, start_line, end_line)
        """
        content = file_path.read_text()
        lines = content.splitlines()

        start_pattern = re.compile(rf"^\s*//@@start\s+{re.escape(marker_name)}\s*$")
        end_pattern = re.compile(rf"^\s*//@@end\s+{re.escape(marker_name)}\s*$")

        start_line = None
        end_line = None

        for i, line in enumerate(lines):
            if start_pattern.match(line):
                start_line = i + 1  # 1-indexed
            elif end_pattern.match(line) and start_line is not None:
                end_line = i + 1
                break

        if start_line is None:
            raise ValueError(f"Marker '//@@start {marker_name}' not found in {file_path}")
        if end_line is None:
            raise ValueError(f"Marker '//@@end {marker_name}' not found in {file_path}")

        # Extract lines between markers (exclusive of marker lines)
        extracted_lines = lines[start_line : end_line - 1]
        text = "\n".join(extracted_lines)

        return text, start_line + 1, end_line - 1

    def extract_message_marker(self, file_path: Path, message_name: str, marker_name: str) -> Tuple[str, int, int]:
        """
        Extract a marked section from within a message definition.

        Args:
            file_path: Path to the .proto file
            message_name: Name of the message containing the marker
            marker_name: Name of the marker

        Returns:
            Tuple of (code_text, start_line, end_line)
        """
        source = file_path.read_bytes()
        tree = self._parser.parse(source)

        node = self._find_message(tree.root_node, message_name)
        if not node:
            raise ValueError(f"Message '{message_name}' not found in {file_path}")

        return self._extract_marker_from_node(file_path, node, marker_name, f"message '{message_name}'")

    def _find_message(self, root: Node, name: str) -> Optional[Node]:
        """Find a message node by name."""
        return self._find_definition(root, "message", "message_name", name)

    def _find_enum(self, root: Node, name: str) -> Optional[Node]:
        """Find an enum node by name."""
        return self._find_definition(root, "enum", "enum_name", name)

    def _find_service(self, root: Node, name: str) -> Optional[Node]:
        """Find a service node by name."""
        return self._find_definition(root, "service", "service_name", name)

    def _find_definition(self, node: Node, def_type: str, name_type: str, target_name: str) -> Optional[Node]:
        """
        Generic finder for proto definitions (message, enum, service).

        Args:
            node: Node to search in
            def_type: Type of definition node (e.g., "message", "enum")
            name_type: Type of name node (e.g., "message_name", "enum_name")
            target_name: Name to find

        Returns:
            The matching node or None
        """
        if node.type == def_type:
            for child in node.children:
                if child.type == name_type:
                    if child.text and child.text.decode("utf8") == target_name:
                        return node

        # Recurse into children
        for child in node.children:
            result = self._find_definition(child, def_type, name_type, target_name)
            if result:
                return result

        return None

    def _extract_marker_from_node(
        self, file_path: Path, node: Node, marker_name: str, context: str
    ) -> Tuple[str, int, int]:
        """Extract marker content from within a node."""
        text = node.text.decode("utf8") if node.text else ""
        lines = text.splitlines()
        node_start_line = node.start_point.row + 1

        start_pattern = re.compile(rf"^\s*//@@start\s+{re.escape(marker_name)}\s*$")
        end_pattern = re.compile(rf"^\s*//@@end\s+{re.escape(marker_name)}\s*$")

        start_idx = None
        end_idx = None

        for i, line in enumerate(lines):
            if start_pattern.match(line):
                start_idx = i
            elif end_pattern.match(line) and start_idx is not None:
                end_idx = i
                break

        if start_idx is None:
            raise ValueError(f"Marker '//@@start {marker_name}' not found in {context}")
        if end_idx is None:
            raise ValueError(f"Marker '//@@end {marker_name}' not found in {context}")

        # Extract lines between markers (exclusive)
        extracted_lines = lines[start_idx + 1 : end_idx]
        extracted_text = "\n".join(extracted_lines)

        start_line = node_start_line + start_idx + 1
        end_line = node_start_line + end_idx - 1

        return extracted_text, start_line, end_line

    def find_markers_in_file(self, file_path: Path) -> Dict[str, Tuple[int, int]]:
        """
        Find all markers in a proto file.

        Returns:
            Dict mapping marker names to (start_line, end_line) tuples
        """
        content = file_path.read_text()
        lines = content.splitlines()

        markers: Dict[str, Tuple[int, int]] = {}
        start_pattern = re.compile(r"^\s*//@@start\s+([\w-]+)\s*$")
        end_pattern = re.compile(r"^\s*//@@end\s+([\w-]+)\s*$")

        open_markers: Dict[str, int] = {}

        for i, line in enumerate(lines):
            start_match = start_pattern.match(line)
            if start_match:
                name = start_match.group(1)
                open_markers[name] = i + 1

            end_match = end_pattern.match(line)
            if end_match:
                name = end_match.group(1)
                if name in open_markers:
                    markers[name] = (open_markers[name], i + 1)
                    del open_markers[name]

        return markers
