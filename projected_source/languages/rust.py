"""
Rust code extraction using tree-sitter.

Supports functions, structs, enums, unions, traits, type aliases,
const/static items, impl methods (including trait impls), modules, and markers.

Behavior notes:
    - Extraction includes contiguous leading ``#[...]`` attributes (derives,
      ``#[inline]``, ``#[cfg(...)]``, etc.). In Rust these are semantic, not
      decorative.
    - Extracted text is dedented uniformly so the signature, body, and closing
      brace align at column 0 even when the source lives inside an indented
      ``impl`` or ``mod`` block.
    - ``#[cfg(test)] mod tests { ... }`` contents are hidden from
      ``list_symbols`` by default. Pass ``include_tests=True`` (CLI:
      ``--include-tests``) to surface them.
"""

import logging
import re
import textwrap
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import tree_sitter_rust as ts_rust
from tree_sitter import Language, Node, Query, QueryCursor

from ..core.extractor import BaseExtractor
from .utils import node_text

logger = logging.getLogger(__name__)

_rust_language = None


def _get_rust_language():
    global _rust_language
    if _rust_language is None:
        _rust_language = Language(ts_rust.language())
    return _rust_language


class RustExtractor(BaseExtractor):
    """Rust extractor using tree-sitter.

    Methods live inside ``impl`` blocks, so ``Foo.bar`` looks up ``bar`` in any
    ``impl Foo`` or ``impl Trait for Foo`` block. ``::`` is also accepted as the
    separator to match Rust's idiomatic ``Foo::bar`` syntax.
    """

    _TYPE_DECL_TYPES = (
        "struct_item",
        "enum_item",
        "union_item",
        "trait_item",
        "type_item",
    )
    _FN_TYPES = ("function_item", "function_signature_item")

    def __init__(self):
        super().__init__(_get_rust_language())

    # --- Public extraction API ---

    def extract_function(self, file_path: Path, function_name: str, signature: str = None) -> Tuple[str, int, int]:
        """Extract a function or method by name."""
        source = file_path.read_bytes()
        root = self.parse_bytes(source)
        owner, fn_name = self._split_qualified(function_name)

        if owner is not None:
            located = self._find_method(root, owner, fn_name)
        else:
            located = self._find_function_anywhere(root, fn_name)
        if located is None:
            raise ValueError(f"Function '{function_name}' not found in {file_path}")

        parent, node = located
        return self._extract_with_attrs(source, parent, node)

    def extract_function_marker(self, file_path: Path, function_name: str, marker: str) -> Tuple[str, int, int]:
        """Extract a marker within a function or method."""
        source = file_path.read_bytes()
        root = self.parse_bytes(source)
        owner, fn_name = self._split_qualified(function_name)

        if owner is not None:
            located = self._find_method(root, owner, fn_name)
        else:
            located = self._find_function_anywhere(root, fn_name)
        if located is None:
            raise ValueError(f"Function '{function_name}' not found in {file_path}")

        _parent, node = located
        markers = self.find_markers_in_node(node)
        if marker not in markers:
            available = ", ".join(markers.keys()) if markers else "none"
            raise ValueError(f"Marker '{marker}' not found in '{function_name}'. Available: {available}")

        start_line, end_line = markers[marker]
        return self._extract_lines_dedented(source, start_line, end_line)

    def extract_struct(self, file_path: Path, name: str) -> Tuple[str, int, int]:
        """Extract a struct, enum, union, trait, or type alias by name."""
        source = file_path.read_bytes()
        root = self.parse_bytes(source)
        located = self._find_type_declaration(root, name)
        if located is None:
            raise ValueError(f"Type '{name}' not found in {file_path}")
        parent, node = located
        return self._extract_with_attrs(source, parent, node)

    def extract_struct_marker(self, file_path: Path, name: str, marker: str) -> Tuple[str, int, int]:
        """Extract a marker within a struct/enum/trait body."""
        source = file_path.read_bytes()
        root = self.parse_bytes(source)
        located = self._find_type_declaration(root, name)
        if located is None:
            raise ValueError(f"Type '{name}' not found in {file_path}")
        _parent, node = located
        markers = self.find_markers_in_node(node)
        if marker not in markers:
            available = ", ".join(markers.keys()) if markers else "none"
            raise ValueError(f"Marker '{marker}' not found in '{name}'. Available: {available}")

        start_line, end_line = markers[marker]
        return self._extract_lines_dedented(source, start_line, end_line)

    def extract_variable(self, file_path: Path, var_name: str) -> Tuple[str, int, int]:
        """Extract a const or static item by name."""
        source = file_path.read_bytes()
        root = self.parse_bytes(source)
        located = self._find_value_declaration(root, var_name)
        if located is None:
            raise ValueError(f"Const/static '{var_name}' not found in {file_path}")
        parent, node = located
        return self._extract_with_attrs(source, parent, node)

    def extract_enum(self, file_path: Path, enum_name: str) -> Tuple[str, int, int]:
        """Extract an enum declaration by name."""
        return self.extract_struct(file_path, enum_name)

    def extract_marker(self, file_path: Path, marker_name: str) -> Tuple[str, int, int]:
        """Extract code between marker comments."""
        source = file_path.read_bytes()
        markers = self.find_markers_in_file(file_path)
        if marker_name not in markers:
            available = ", ".join(markers.keys()) if markers else "none"
            raise ValueError(f"Marker '{marker_name}' not found. Available markers: {available}")
        start_line, end_line = markers[marker_name]
        return self._extract_lines_dedented(source, start_line, end_line)

    def list_symbols(self, file_path: Path, include_tests: bool = False) -> List[Dict]:
        """List all extractable symbols in a file.

        ``include_tests`` controls whether items inside ``#[cfg(test)]`` modules
        are included. Other modules are always recursed into.
        """
        root = self.parse_bytes(file_path.read_bytes())
        symbols: List[Dict] = []
        self._collect_symbols(root, symbols, prefix="", include_tests=include_tests)

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

    def find_markers_in_node(self, node: Node) -> Dict[str, Tuple[int, int]]:
        """Override: Rust grammar uses line_comment / block_comment, not comment."""
        query = Query(self.language, "[(line_comment) (block_comment)] @comment")
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

        for marker_name in active_markers:
            logger.warning(f"Marker '{marker_name}' was not closed with //@@end")

        return markers

    # --- Internal helpers ---

    @staticmethod
    def _split_qualified(name: str) -> Tuple[Optional[str], str]:
        """Split 'Foo.bar' or 'Foo::bar' into ('Foo', 'bar'). Bare 'bar' → (None, 'bar')."""
        for sep in ("::", "."):
            if sep in name:
                parts = name.split(sep)
                return sep.join(parts[:-1]), parts[-1]
        return None, name

    @staticmethod
    def _walk_back_attributes(parent: Optional[Node], node: Node) -> Node:
        """Return the first ``attribute_item`` in a contiguous run preceding ``node``,
        or ``node`` itself if there are no attached attributes.
        """
        if parent is None:
            return node
        siblings = list(parent.children)
        try:
            idx = siblings.index(node)
        except ValueError:
            return node
        first = node
        i = idx - 1
        while i >= 0 and siblings[i].type == "attribute_item":
            first = siblings[i]
            i -= 1
        return first

    @staticmethod
    def _extract_with_attrs(source: bytes, parent: Optional[Node], node: Node) -> Tuple[str, int, int]:
        """Extract a node's source text including leading attributes, dedented."""
        first = RustExtractor._walk_back_attributes(parent, node)

        # Anchor to the start of the first node's line so leading whitespace
        # is preserved — textwrap.dedent then strips it uniformly.
        line_start_byte = first.start_byte - first.start_point.column
        end_byte = node.end_byte
        raw = source[line_start_byte:end_byte].decode("utf-8", errors="replace")
        text = textwrap.dedent(raw)
        return text, first.start_point.row + 1, node.end_point.row + 1

    @staticmethod
    def _extract_lines_dedented(source: bytes, start_line: int, end_line: int) -> Tuple[str, int, int]:
        """Slice source by 1-based line range and dedent the result."""
        lines = source.decode("utf-8", errors="replace").splitlines()
        start = max(0, start_line - 1)
        end = min(len(lines), end_line)
        snippet = "\n".join(lines[start:end])
        return textwrap.dedent(snippet), start_line, end_line

    @staticmethod
    def _has_cfg_test_attribute(parent: Optional[Node], node: Node) -> bool:
        """True iff one of the attributes preceding ``node`` mentions ``cfg(test)``."""
        if parent is None:
            return False
        siblings = list(parent.children)
        try:
            idx = siblings.index(node)
        except ValueError:
            return False
        i = idx - 1
        while i >= 0 and siblings[i].type == "attribute_item":
            text = node_text(siblings[i])
            # Catch `#[cfg(test)]`, `#[cfg(any(test, ...))]`, `#[cfg(all(test, ...))]`.
            if re.search(r"\bcfg\b\s*\(\s*[^)]*\btest\b", text):
                return True
            i -= 1
        return False

    @staticmethod
    def _impl_targets(impl_node: Node) -> str:
        type_field = impl_node.child_by_field_name("type")
        if type_field is None:
            return ""
        return RustExtractor._trailing_identifier(type_field)

    @staticmethod
    def _trailing_identifier(type_node: Node) -> str:
        if type_node.type == "type_identifier":
            return node_text(type_node)
        base = type_node.child_by_field_name("type")
        if base is not None:
            return RustExtractor._trailing_identifier(base)
        name = type_node.child_by_field_name("name")
        if name is not None:
            return node_text(name)
        return node_text(type_node)

    # --- Lookup ---

    def _find_type_declaration(self, root: Node, name: str) -> Optional[Tuple[Node, Node]]:
        """Find a struct/enum/union/trait/type_item by name. Searches modules too.

        Returns ``(parent, node)`` so callers can locate leading attributes.
        """
        return self._search_type(root, name)

    def _search_type(self, container: Node, name: str) -> Optional[Tuple[Node, Node]]:
        for child in container.children:
            if child.type in self._TYPE_DECL_TYPES:
                name_node = child.child_by_field_name("name")
                if name_node and node_text(name_node) == name:
                    return container, child
            elif child.type == "mod_item":
                body = child.child_by_field_name("body")
                if body is not None:
                    found = self._search_type(body, name)
                    if found:
                        return found
        return None

    def _find_value_declaration(self, root: Node, name: str) -> Optional[Tuple[Node, Node]]:
        """Find a const_item or static_item by name. Searches modules too."""
        return self._search_value(root, name)

    def _search_value(self, container: Node, name: str) -> Optional[Tuple[Node, Node]]:
        for child in container.children:
            if child.type in ("const_item", "static_item"):
                name_node = child.child_by_field_name("name")
                if name_node and node_text(name_node) == name:
                    return container, child
            elif child.type == "mod_item":
                body = child.child_by_field_name("body")
                if body is not None:
                    found = self._search_value(body, name)
                    if found:
                        return found
        return None

    def _find_method(self, root: Node, owner: str, method_name: str) -> Optional[Tuple[Node, Node]]:
        """Find a method by walking impl blocks (and trait body) targeting ``owner``."""
        result = self._search_method(root, owner, method_name)
        if result:
            return result
        # Fallback: trait declarations themselves
        type_decl = self._find_type_declaration(root, owner)
        if type_decl is not None:
            parent, trait_node = type_decl
            if trait_node.type == "trait_item":
                body = trait_node.child_by_field_name("body")
                if body is not None:
                    for child in body.children:
                        if child.type in self._FN_TYPES:
                            name_node = child.child_by_field_name("name")
                            if name_node and node_text(name_node) == method_name:
                                return body, child
        return None

    def _search_method(self, container: Node, owner: str, method_name: str) -> Optional[Tuple[Node, Node]]:
        for child in container.children:
            if child.type == "impl_item" and self._impl_targets(child) == owner:
                body = child.child_by_field_name("body")
                if body is not None:
                    for member in body.children:
                        if member.type in self._FN_TYPES:
                            name_node = member.child_by_field_name("name")
                            if name_node and node_text(name_node) == method_name:
                                return body, member
            elif child.type == "mod_item":
                body = child.child_by_field_name("body")
                if body is not None:
                    found = self._search_method(body, owner, method_name)
                    if found:
                        return found
        return None

    def _find_function_anywhere(self, root: Node, fn_name: str) -> Optional[Tuple[Node, Node]]:
        """Search free fns first, then methods inside impls/traits, then module bodies."""
        # Top-level free fns
        for node in root.children:
            if node.type == "function_item":
                name_node = node.child_by_field_name("name")
                if name_node and node_text(name_node) == fn_name:
                    return root, node

        # Methods inside impls and traits
        for node in root.children:
            container_body = None
            if node.type in ("impl_item", "trait_item"):
                container_body = node.child_by_field_name("body")
            if container_body is None:
                continue
            for child in container_body.children:
                if child.type in self._FN_TYPES:
                    name_node = child.child_by_field_name("name")
                    if name_node and node_text(name_node) == fn_name:
                        return container_body, child

        # Recurse into modules (test or otherwise — caller has already named the symbol)
        for node in root.children:
            if node.type == "mod_item":
                body = node.child_by_field_name("body")
                if body is not None:
                    found = self._find_function_anywhere(body, fn_name)
                    if found:
                        return found
        return None

    # --- Symbol enumeration ---

    def _collect_symbols(self, container: Node, symbols: List[Dict], prefix: str, include_tests: bool) -> None:
        """Collect symbols from a container (root or module body)."""
        for child in container.children:
            if child.type == "function_item":
                name_node = child.child_by_field_name("name")
                if name_node:
                    symbols.append(
                        {
                            "name": self._qualified(prefix, node_text(name_node)),
                            "kind": "function",
                            "param": "function",
                            "line": child.start_point.row + 1,
                            "end_line": child.end_point.row + 1,
                        }
                    )

            elif child.type in self._TYPE_DECL_TYPES:
                name_node = child.child_by_field_name("name")
                if not name_node:
                    continue
                type_name = node_text(name_node)
                full_name = self._qualified(prefix, type_name)
                kind = {
                    "struct_item": "struct",
                    "enum_item": "enum",
                    "union_item": "union",
                    "trait_item": "trait",
                    "type_item": "type",
                }.get(child.type, "struct")
                param = "enum" if kind == "enum" else "struct"
                symbols.append(
                    {
                        "name": full_name,
                        "kind": kind,
                        "param": param,
                        "line": child.start_point.row + 1,
                        "end_line": child.end_point.row + 1,
                    }
                )

                if child.type == "trait_item":
                    body = child.child_by_field_name("body")
                    if body is not None:
                        for member in body.children:
                            if member.type in self._FN_TYPES:
                                mname = member.child_by_field_name("name")
                                if mname:
                                    symbols.append(
                                        {
                                            "name": f"{full_name}.{node_text(mname)}",
                                            "kind": "method",
                                            "param": "function",
                                            "line": member.start_point.row + 1,
                                            "end_line": member.end_point.row + 1,
                                        }
                                    )

            elif child.type in ("const_item", "static_item"):
                name_node = child.child_by_field_name("name")
                if name_node:
                    symbols.append(
                        {
                            "name": self._qualified(prefix, node_text(name_node)),
                            "kind": "const" if child.type == "const_item" else "static",
                            "param": "var",
                            "line": child.start_point.row + 1,
                            "end_line": child.end_point.row + 1,
                        }
                    )

            elif child.type == "impl_item":
                target = self._impl_targets(child)
                if not target:
                    continue
                body = child.child_by_field_name("body")
                if body is None:
                    continue
                for member in body.children:
                    if member.type in self._FN_TYPES:
                        mname = member.child_by_field_name("name")
                        if mname:
                            # Methods stay flat (Foo.method) regardless of module nesting.
                            symbols.append(
                                {
                                    "name": f"{target}.{node_text(mname)}",
                                    "kind": "method",
                                    "param": "function",
                                    "line": member.start_point.row + 1,
                                    "end_line": member.end_point.row + 1,
                                }
                            )

            elif child.type == "mod_item":
                if not include_tests and self._has_cfg_test_attribute(container, child):
                    continue
                mod_name_node = child.child_by_field_name("name")
                if mod_name_node is None:
                    continue
                mod_name = node_text(mod_name_node)
                body = child.child_by_field_name("body")
                if body is None:
                    continue
                inner_prefix = f"{prefix}::{mod_name}" if prefix else mod_name
                self._collect_symbols(body, symbols, inner_prefix, include_tests)

    @staticmethod
    def _qualified(prefix: str, name: str) -> str:
        return f"{prefix}::{name}" if prefix else name
