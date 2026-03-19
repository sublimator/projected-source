"""
TypeScript/TSX code extraction using tree-sitter.

Supports functions, classes, interfaces, enums, type aliases,
variable declarations, methods, and markers.
"""

import logging
from pathlib import Path
from typing import Dict, List, Tuple

import tree_sitter_typescript as ts_ts
from tree_sitter import Language

from ..core.extractor import BaseExtractor
from .utils import node_text

logger = logging.getLogger(__name__)

_ts_language = None
_tsx_language = None


def _get_ts_language():
    global _ts_language
    if _ts_language is None:
        _ts_language = Language(ts_ts.language_typescript())
    return _ts_language


def _get_tsx_language():
    global _tsx_language
    if _tsx_language is None:
        _tsx_language = Language(ts_ts.language_tsx())
    return _tsx_language


class TypeScriptExtractor(BaseExtractor):
    """TypeScript extractor using tree-sitter."""

    def __init__(self, tsx: bool = False):
        language = _get_tsx_language() if tsx else _get_ts_language()
        super().__init__(language)
        self._tsx = tsx

    def extract_function(self, file_path: Path, function_name: str, signature: str = None) -> Tuple[str, int, int]:
        """Extract a function or method by name.

        Supports:
            - Top-level functions: extract_function(file, 'processData')
            - Methods: extract_function(file, 'Handler.process')
            - Arrow functions: extract_function(file, 'myArrow')
        """
        source = file_path.read_bytes()
        root = self.parse_bytes(source)

        # Check for dotted path (Class.method)
        if "." in function_name:
            parts = function_name.split(".")
            class_name = parts[0]
            method_name = parts[1]
            return self._extract_method(file_path, source, root, class_name, method_name)

        # Try function declaration first
        node = self._find_function(root, function_name)
        if node is None:
            # Try arrow function / variable declaration
            node = self._find_variable(root, function_name)
        if node is None:
            raise ValueError(f"Function '{function_name}' not found in {file_path}")

        text = node_text(node)
        start = node.start_point.row + 1
        end = node.end_point.row + 1
        return text, start, end

    def extract_function_marker(self, file_path: Path, function_name: str, marker: str) -> Tuple[str, int, int]:
        """Extract a marker within a function."""
        source = file_path.read_bytes()
        root = self.parse_bytes(source)

        if "." in function_name:
            parts = function_name.split(".")
            class_name = parts[0]
            method_name = parts[1]
            node = self._find_method_node(root, class_name, method_name)
        else:
            node = self._find_function(root, function_name)
            if node is None:
                node = self._find_variable(root, function_name)

        if node is None:
            raise ValueError(f"Function '{function_name}' not found in {file_path}")

        markers = self.find_markers_in_node(node)
        if marker not in markers:
            available = ", ".join(markers.keys()) if markers else "none"
            raise ValueError(f"Marker '{marker}' not found in function '{function_name}'. Available: {available}")

        start_line, end_line = markers[marker]
        return self.extract_lines(file_path, start_line, end_line)

    def extract_struct(self, file_path: Path, name: str) -> Tuple[str, int, int]:
        """Extract a class, interface, type alias, or enum by name."""
        source = file_path.read_bytes()
        root = self.parse_bytes(source)

        node = self._find_class(root, name)
        if node is None:
            node = self._find_interface(root, name)
        if node is None:
            node = self._find_type_alias(root, name)
        if node is None:
            node = self._find_enum(root, name)
        if node is None:
            raise ValueError(f"Class/interface/type/enum '{name}' not found in {file_path}")

        text = node_text(node)
        start = node.start_point.row + 1
        end = node.end_point.row + 1
        return text, start, end

    def extract_struct_marker(self, file_path: Path, name: str, marker: str) -> Tuple[str, int, int]:
        """Extract a marker within a class/interface."""
        source = file_path.read_bytes()
        root = self.parse_bytes(source)

        node = self._find_class(root, name)
        if node is None:
            node = self._find_interface(root, name)
        if node is None:
            raise ValueError(f"Class/interface '{name}' not found in {file_path}")

        markers = self.find_markers_in_node(node)
        if marker not in markers:
            available = ", ".join(markers.keys()) if markers else "none"
            raise ValueError(f"Marker '{marker}' not found in '{name}'. Available: {available}")

        start_line, end_line = markers[marker]
        return self.extract_lines(file_path, start_line, end_line)

    def extract_variable(self, file_path: Path, var_name: str) -> Tuple[str, int, int]:
        """Extract a variable/constant declaration by name."""
        source = file_path.read_bytes()
        root = self.parse_bytes(source)

        node = self._find_variable(root, var_name)
        if node is None:
            raise ValueError(f"Variable '{var_name}' not found in {file_path}")

        text = node_text(node)
        start = node.start_point.row + 1
        end = node.end_point.row + 1
        return text, start, end

    def extract_enum(self, file_path: Path, enum_name: str) -> Tuple[str, int, int]:
        """Extract an enum declaration by name."""
        source = file_path.read_bytes()
        root = self.parse_bytes(source)

        node = self._find_enum(root, enum_name)
        if node is None:
            raise ValueError(f"Enum '{enum_name}' not found in {file_path}")

        text = node_text(node)
        start = node.start_point.row + 1
        end = node.end_point.row + 1
        return text, start, end

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

    # --- Internal helpers ---

    def _find_function(self, root, name: str):
        """Find a function_declaration or generator_function_declaration by name."""
        for node in root.children:
            target = node
            # Unwrap export_statement
            if node.type == "export_statement":
                for child in node.children:
                    if child.type in ("function_declaration", "generator_function_declaration"):
                        target = child
                        break
                else:
                    continue

            if target.type in ("function_declaration", "generator_function_declaration"):
                name_node = target.child_by_field_name("name")
                if name_node and node_text(name_node) == name:
                    # Return the export_statement if exported, otherwise the function
                    return node
        return None

    def _find_variable(self, root, name: str):
        """Find a lexical_declaration (const/let/var) containing a variable declarator with the given name."""
        for node in root.children:
            target = node
            # Unwrap export_statement
            if node.type == "export_statement":
                for child in node.children:
                    if child.type == "lexical_declaration":
                        target = child
                        break
                else:
                    continue

            if target.type == "lexical_declaration":
                for child in target.children:
                    if child.type == "variable_declarator":
                        name_node = child.child_by_field_name("name")
                        if name_node and node_text(name_node) == name:
                            return node
        return None

    def _find_class(self, root, name: str):
        """Find a class_declaration by name."""
        for node in root.children:
            target = node
            if node.type == "export_statement":
                for child in node.children:
                    if child.type in ("class_declaration", "abstract_class_declaration"):
                        target = child
                        break
                else:
                    continue

            if target.type in ("class_declaration", "abstract_class_declaration"):
                name_node = target.child_by_field_name("name")
                if name_node and node_text(name_node) == name:
                    return node
        return None

    def _find_interface(self, root, name: str):
        """Find an interface_declaration by name."""
        for node in root.children:
            target = node
            if node.type == "export_statement":
                for child in node.children:
                    if child.type == "interface_declaration":
                        target = child
                        break
                else:
                    continue

            if target.type == "interface_declaration":
                name_node = target.child_by_field_name("name")
                if name_node and node_text(name_node) == name:
                    return node
        return None

    def _find_type_alias(self, root, name: str):
        """Find a type_alias_declaration by name."""
        for node in root.children:
            target = node
            if node.type == "export_statement":
                for child in node.children:
                    if child.type == "type_alias_declaration":
                        target = child
                        break
                else:
                    continue

            if target.type == "type_alias_declaration":
                name_node = target.child_by_field_name("name")
                if name_node and node_text(name_node) == name:
                    return node
        return None

    def _find_enum(self, root, name: str):
        """Find an enum_declaration by name."""
        for node in root.children:
            target = node
            if node.type == "export_statement":
                for child in node.children:
                    if child.type == "enum_declaration":
                        target = child
                        break
                else:
                    continue

            if target.type == "enum_declaration":
                name_node = target.child_by_field_name("name")
                if name_node and node_text(name_node) == name:
                    return node
        return None

    def _find_method_node(self, root, class_name: str, method_name: str):
        """Find a method within a class."""
        class_node = self._find_class(root, class_name)
        if class_node is None:
            return None

        # Find the class_body (may be inside export_statement)
        actual_class = class_node
        if class_node.type == "export_statement":
            for child in class_node.children:
                if child.type in ("class_declaration", "abstract_class_declaration"):
                    actual_class = child
                    break

        body = actual_class.child_by_field_name("body")
        if body is None:
            return None

        for child in body.children:
            if child.type == "method_definition":
                name_node = child.child_by_field_name("name")
                if name_node and node_text(name_node) == method_name:
                    return child
        return None

    def _extract_method(self, file_path, source, root, class_name: str, method_name: str) -> Tuple[str, int, int]:
        """Extract a method from a class."""
        node = self._find_method_node(root, class_name, method_name)
        if node is None:
            raise ValueError(f"Method '{class_name}.{method_name}' not found in {file_path}")

        text = node_text(node)
        start = node.start_point.row + 1
        end = node.end_point.row + 1
        return text, start, end

    def _collect_symbols(self, node, symbols: List[Dict], class_name: str = None):
        """Recursively collect all extractable symbols."""
        for child in node.children:
            target = child

            # Unwrap export_statement
            if child.type == "export_statement":
                for grandchild in child.children:
                    if grandchild.type in (
                        "function_declaration",
                        "generator_function_declaration",
                        "class_declaration",
                        "abstract_class_declaration",
                        "interface_declaration",
                        "type_alias_declaration",
                        "enum_declaration",
                        "lexical_declaration",
                    ):
                        target = grandchild
                        break

            if target.type in ("function_declaration", "generator_function_declaration"):
                name_node = target.child_by_field_name("name")
                if name_node:
                    symbols.append(
                        {
                            "name": node_text(name_node),
                            "kind": "function",
                            "param": "function",
                            "line": child.start_point.row + 1,
                            "end_line": child.end_point.row + 1,
                        }
                    )

            elif target.type in ("class_declaration", "abstract_class_declaration"):
                name_node = target.child_by_field_name("name")
                if name_node:
                    cname = node_text(name_node)
                    symbols.append(
                        {
                            "name": cname,
                            "kind": "class",
                            "param": "struct",
                            "line": child.start_point.row + 1,
                            "end_line": child.end_point.row + 1,
                        }
                    )
                    # Collect methods
                    body = target.child_by_field_name("body")
                    if body:
                        for member in body.children:
                            if member.type == "method_definition":
                                mname_node = member.child_by_field_name("name")
                                if mname_node:
                                    symbols.append(
                                        {
                                            "name": f"{cname}.{node_text(mname_node)}",
                                            "kind": "method",
                                            "param": "function",
                                            "line": member.start_point.row + 1,
                                            "end_line": member.end_point.row + 1,
                                        }
                                    )

            elif target.type == "interface_declaration":
                name_node = target.child_by_field_name("name")
                if name_node:
                    symbols.append(
                        {
                            "name": node_text(name_node),
                            "kind": "interface",
                            "param": "struct",
                            "line": child.start_point.row + 1,
                            "end_line": child.end_point.row + 1,
                        }
                    )

            elif target.type == "type_alias_declaration":
                name_node = target.child_by_field_name("name")
                if name_node:
                    symbols.append(
                        {
                            "name": node_text(name_node),
                            "kind": "type",
                            "param": "struct",
                            "line": child.start_point.row + 1,
                            "end_line": child.end_point.row + 1,
                        }
                    )

            elif target.type == "enum_declaration":
                name_node = target.child_by_field_name("name")
                if name_node:
                    symbols.append(
                        {
                            "name": node_text(name_node),
                            "kind": "enum",
                            "param": "enum",
                            "line": child.start_point.row + 1,
                            "end_line": child.end_point.row + 1,
                        }
                    )

            elif target.type == "lexical_declaration":
                for decl in target.children:
                    if decl.type == "variable_declarator":
                        name_node = decl.child_by_field_name("name")
                        if name_node:
                            symbols.append(
                                {
                                    "name": node_text(name_node),
                                    "kind": "variable",
                                    "param": "var",
                                    "line": child.start_point.row + 1,
                                    "end_line": child.end_point.row + 1,
                                }
                            )
