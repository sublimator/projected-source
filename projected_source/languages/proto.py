"""
Protocol Buffers (.proto) code extraction using tree-sitter.

Uses the coder3101/tree-sitter-proto grammar (proto2 + proto3), installed as a
pinned git dependency (``tree-sitter-proto`` in pyproject.toml) since it is not
published to PyPI. The grammar's C source is compiled at install time, so this
works on any platform with a C compiler — no prebuilt binary is bundled.
"""

import logging
from pathlib import Path
from typing import List, Optional, Tuple

import tree_sitter_proto
from tree_sitter import Language, Node, Parser

from ..core.extractor import BaseExtractor

logger = logging.getLogger(__name__)


class ProtoExtractor(BaseExtractor):
    """Protocol Buffers extractor with message/enum extraction support."""

    def __init__(self):
        self._language = Language(tree_sitter_proto.language())
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

    # extract_marker and find_markers_in_file are inherited from
    # BaseExtractor: the grammar exposes (comment) nodes, so markers are
    # found via tree-sitter and never inside string literals.

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
        """Extract marker content from within a node's subtree.

        Uses the tree-sitter comment scan, so marker-shaped lines inside
        string literals are never mistaken for markers. Node positions are
        absolute, so the returned lines need no rebasing.
        """
        markers = self.find_markers_in_node(node)
        if marker_name not in markers:
            available = ", ".join(markers.keys()) if markers else "none"
            raise ValueError(f"Marker '{marker_name}' not found in {context}. Available: {available}")

        start_line, end_line = markers[marker_name]
        return self.extract_lines(file_path, start_line, end_line)

    def list_symbols(self, file_path: Path) -> List[dict]:
        """List all extractable symbols in a proto file."""
        source = file_path.read_bytes()
        tree = self._parser.parse(source)
        symbols = []

        def _node_name(node):
            return node.text.decode("utf8") if node.text else None

        def collect(node):
            if node.type == "message":
                for child in node.children:
                    if child.type == "message_name":
                        name = _node_name(child)
                        if name:
                            symbols.append({
                                "name": name,
                                "kind": "message",
                                "param": "message",
                                "line": node.start_point.row + 1,
                            })
                        break
            elif node.type == "enum":
                for child in node.children:
                    if child.type == "enum_name":
                        name = _node_name(child)
                        if name:
                            symbols.append({
                                "name": name,
                                "kind": "enum",
                                "param": "enum",
                                "line": node.start_point.row + 1,
                            })
                        break
            elif node.type == "service":
                for child in node.children:
                    if child.type == "service_name":
                        name = _node_name(child)
                        if name:
                            symbols.append({
                                "name": name,
                                "kind": "service",
                                "param": "service",
                                "line": node.start_point.row + 1,
                            })
                        break

            for child in node.children:
                collect(child)

        collect(tree.root_node)

        # Also find markers
        markers = self.find_markers_in_file(file_path)
        for marker_name, (start_line, end_line) in markers.items():
            symbols.append({
                "name": marker_name,
                "kind": "marker",
                "param": "marker",
                "line": start_line,
                "end_line": end_line,
            })

        return symbols

