"""
Java code extraction using tree-sitter.

Supports classes, interfaces, enums, records, methods, constructors,
fields, and markers.
"""

import logging
import re
from pathlib import Path
from typing import Dict, List, Tuple

import tree_sitter_java as ts_java
from tree_sitter import Language, Query, QueryCursor

from ..core.extractor import BaseExtractor
from .utils import node_text

logger = logging.getLogger(__name__)

_java_language = None


def _get_java_language():
    global _java_language
    if _java_language is None:
        _java_language = Language(ts_java.language())
    return _java_language


class JavaExtractor(BaseExtractor):
    """Java extractor using tree-sitter."""

    def __init__(self):
        super().__init__(_get_java_language())

    def extract_function(self, file_path: Path, function_name: str, signature: str = None) -> Tuple[str, int, int]:
        """Extract a method or constructor by name.

        Supports:
            - Methods: extract_function(file, 'Handler.process')
            - Constructors: extract_function(file, 'Handler.Handler')
            - Top-level search: extract_function(file, 'process') — searches all classes
        """
        source = file_path.read_bytes()
        root = self.parse_bytes(source)

        if "." in function_name:
            parts = function_name.split(".")
            class_name = parts[0]
            method_name = parts[1]
            node = self._find_method_node(root, class_name, method_name)
        else:
            # Search all classes for this method name
            node = self._find_method_anywhere(root, function_name)

        if node is None:
            raise ValueError(f"Method '{function_name}' not found in {file_path}")

        text = node_text(node)
        start = node.start_point.row + 1
        end = node.end_point.row + 1
        return text, start, end

    def extract_function_marker(self, file_path: Path, function_name: str, marker: str) -> Tuple[str, int, int]:
        """Extract a marker within a method."""
        source = file_path.read_bytes()
        root = self.parse_bytes(source)

        if "." in function_name:
            parts = function_name.split(".")
            node = self._find_method_node(root, parts[0], parts[1])
        else:
            node = self._find_method_anywhere(root, function_name)

        if node is None:
            raise ValueError(f"Method '{function_name}' not found in {file_path}")

        markers = self.find_markers_in_node(node)
        if marker not in markers:
            available = ", ".join(markers.keys()) if markers else "none"
            raise ValueError(f"Marker '{marker}' not found in '{function_name}'. Available: {available}")

        start_line, end_line = markers[marker]
        return self.extract_lines(file_path, start_line, end_line)

    def extract_struct(self, file_path: Path, name: str) -> Tuple[str, int, int]:
        """Extract a class, interface, enum, or record by name."""
        source = file_path.read_bytes()
        root = self.parse_bytes(source)

        node = self._find_type_declaration(root, name)
        if node is None:
            raise ValueError(f"Class/interface/enum/record '{name}' not found in {file_path}")

        text = node_text(node)
        start = node.start_point.row + 1
        end = node.end_point.row + 1
        return text, start, end

    def extract_struct_marker(self, file_path: Path, name: str, marker: str) -> Tuple[str, int, int]:
        """Extract a marker within a class/interface."""
        source = file_path.read_bytes()
        root = self.parse_bytes(source)

        node = self._find_type_declaration(root, name)
        if node is None:
            raise ValueError(f"Class/interface '{name}' not found in {file_path}")

        markers = self.find_markers_in_node(node)
        if marker not in markers:
            available = ", ".join(markers.keys()) if markers else "none"
            raise ValueError(f"Marker '{marker}' not found in '{name}'. Available: {available}")

        start_line, end_line = markers[marker]
        return self.extract_lines(file_path, start_line, end_line)

    def extract_variable(self, file_path: Path, var_name: str) -> Tuple[str, int, int]:
        """Extract a field declaration by name.

        Supports:
            - Qualified: extract_variable(file, 'Handler.MAX')
            - Unqualified: extract_variable(file, 'MAX') — searches all classes
        """
        source = file_path.read_bytes()
        root = self.parse_bytes(source)

        if "." in var_name:
            parts = var_name.split(".")
            class_name = parts[0]
            field_name = parts[1]
            node = self._find_field_node(root, class_name, field_name)
        else:
            node = self._find_field_anywhere(root, var_name)

        if node is None:
            raise ValueError(f"Field '{var_name}' not found in {file_path}")

        text = node_text(node)
        start = node.start_point.row + 1
        end = node.end_point.row + 1
        return text, start, end

    def extract_enum(self, file_path: Path, enum_name: str) -> Tuple[str, int, int]:
        """Extract an enum declaration by name."""
        return self.extract_struct(file_path, enum_name)

    def list_symbols(self, file_path: Path) -> List[Dict]:
        """List all extractable symbols in a file."""
        source = file_path.read_bytes()
        root = self.parse_bytes(source)
        symbols: List[Dict] = []

        self._collect_symbols(root, symbols)

        # Add markers
        markers = self.find_markers_in_file(file_path)
        for marker_name, (start, end) in markers.items():
            symbols.append(
                {
                    "name": marker_name,
                    "kind": "marker",
                    "param": "marker",
                    "line": start,
                    "end_line": end,
                }
            )

        return symbols

    def find_markers_in_node(self, node) -> Dict[str, Tuple[int, int]]:
        """Override: Java uses line_comment/block_comment instead of comment."""
        query = Query(self.language, "(line_comment) @comment")
        cursor = QueryCursor(query)
        matches = cursor.matches(node)

        markers: Dict[str, Tuple[int, int]] = {}
        active_markers: Dict[str, int] = {}

        for _, captures in matches:
            comments = captures.get("comment", [])
            for comment in comments:
                if not comment or not comment.text:
                    continue
                text = node_text(comment)
                line_num = comment.start_point.row + 1

                if "//@@start" in text:
                    match = re.search(r"//@@start\s+([\w-]+)", text)
                    if match:
                        active_markers[match.group(1)] = line_num + 1
                elif "//@@end" in text:
                    match = re.search(r"//@@end\s+([\w-]+)", text)
                    if match:
                        name = match.group(1)
                        if name in active_markers:
                            markers[name] = (active_markers.pop(name), line_num - 1)

        return markers

    # --- Internal helpers ---

    _TYPE_DECL_TYPES = ("class_declaration", "interface_declaration", "enum_declaration", "record_declaration")

    def _find_type_declaration(self, root, name: str):
        """Find a class, interface, enum, or record by name at top level."""
        for node in root.children:
            if node.type in self._TYPE_DECL_TYPES:
                name_node = node.child_by_field_name("name")
                if name_node and node_text(name_node) == name:
                    return node
        return None

    def _find_method_node(self, root, class_name: str, method_name: str):
        """Find a method or constructor within a class."""
        class_node = self._find_type_declaration(root, class_name)
        if class_node is None:
            return None

        body = class_node.child_by_field_name("body")
        if body is None:
            return None

        for child in body.children:
            if child.type == "method_declaration":
                name_node = child.child_by_field_name("name")
                if name_node and node_text(name_node) == method_name:
                    return child
            elif child.type == "constructor_declaration":
                name_node = child.child_by_field_name("name")
                if name_node and node_text(name_node) == method_name:
                    return child
        return None

    def _find_method_anywhere(self, root, method_name: str):
        """Search all classes for a method by name."""
        for node in root.children:
            if node.type in self._TYPE_DECL_TYPES:
                body = node.child_by_field_name("body")
                if body is None:
                    continue
                for child in body.children:
                    if child.type in ("method_declaration", "constructor_declaration"):
                        name_node = child.child_by_field_name("name")
                        if name_node and node_text(name_node) == method_name:
                            return child
        return None

    def _find_field_node(self, root, class_name: str, field_name: str):
        """Find a field within a class."""
        class_node = self._find_type_declaration(root, class_name)
        if class_node is None:
            return None
        return self._find_field_in_body(class_node, field_name)

    def _find_field_anywhere(self, root, field_name: str):
        """Search all classes for a field by name."""
        for node in root.children:
            if node.type in self._TYPE_DECL_TYPES:
                result = self._find_field_in_body(node, field_name)
                if result:
                    return result
        return None

    def _find_field_in_body(self, type_node, field_name: str):
        """Find a field declaration in a type's body."""
        body = type_node.child_by_field_name("body")
        if body is None:
            return None
        for child in body.children:
            if child.type == "field_declaration":
                for sub in child.children:
                    if sub.type == "variable_declarator":
                        name_node = sub.child_by_field_name("name")
                        if name_node and node_text(name_node) == field_name:
                            return child
        return None

    def _collect_symbols(self, root, symbols: List[Dict]):
        """Collect all extractable symbols."""
        for child in root.children:
            if child.type not in self._TYPE_DECL_TYPES:
                continue

            name_node = child.child_by_field_name("name")
            if not name_node:
                continue

            type_name = node_text(name_node)
            kind = {
                "class_declaration": "class",
                "interface_declaration": "interface",
                "enum_declaration": "enum",
                "record_declaration": "record",
            }.get(child.type, "class")

            param = "enum" if kind == "enum" else "struct"

            symbols.append(
                {
                    "name": type_name,
                    "kind": kind,
                    "param": param,
                    "line": child.start_point.row + 1,
                    "end_line": child.end_point.row + 1,
                }
            )

            body = child.child_by_field_name("body")
            if body is None:
                continue

            for member in body.children:
                if member.type == "method_declaration":
                    mname = member.child_by_field_name("name")
                    if mname:
                        symbols.append(
                            {
                                "name": f"{type_name}.{node_text(mname)}",
                                "kind": "method",
                                "param": "function",
                                "line": member.start_point.row + 1,
                                "end_line": member.end_point.row + 1,
                            }
                        )
                elif member.type == "constructor_declaration":
                    mname = member.child_by_field_name("name")
                    if mname:
                        symbols.append(
                            {
                                "name": f"{type_name}.{node_text(mname)}",
                                "kind": "constructor",
                                "param": "function",
                                "line": member.start_point.row + 1,
                                "end_line": member.end_point.row + 1,
                            }
                        )
                elif member.type == "field_declaration":
                    for sub in member.children:
                        if sub.type == "variable_declarator":
                            fname = sub.child_by_field_name("name")
                            if fname:
                                symbols.append(
                                    {
                                        "name": f"{type_name}.{node_text(fname)}",
                                        "kind": "field",
                                        "param": "var",
                                        "line": member.start_point.row + 1,
                                        "end_line": member.end_point.row + 1,
                                    }
                                )
