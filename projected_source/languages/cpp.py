"""
C++ specific code extraction using tree-sitter.
"""

import logging
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import tree_sitter_cpp as tscpp
from tree_sitter import Language, Node, Query, QueryCursor

from ..core.extractor import BaseExtractor
from .cpp_ast import extract_function_name_and_qualifiers, find_following_body, node_to_result
from .cpp_parser import SimpleCppParser
from .extraction_result import EnclosedMarkerResult, ExtractionResult
from .macro_definition_finder import MacroDefinitionFinder
from .macro_finder import MacroFinder
from .utils import node_text

logger = logging.getLogger(__name__)


class CppExtractor(BaseExtractor):
    """C++ specific extractor with function extraction support."""

    _AUTO_ENCLOSURE_NODE_TYPES = {
        "declaration",
        "field_declaration",
        "function_definition",
        "lambda_expression",
        "template_declaration",
        "class_specifier",
        "struct_specifier",
        "enum_specifier",
        "namespace_definition",
        "alias_declaration",
        "type_definition",
    }
    _NAME_NODE_TYPES = {
        "identifier",
        "field_identifier",
        "namespace_identifier",
        "type_identifier",
    }

    def __init__(self):
        super().__init__(Language(tscpp.language()))
        self.cpp_parser = SimpleCppParser()
        self.macro_finder = MacroFinder()
        self.macro_def_finder = MacroDefinitionFinder()

    def extract_function(self, file_path: Path, function_name: str, signature: str = None) -> Tuple[str, int, int]:
        """
        Extract a C++ function by name using tree-sitter.

        Supports:
        - Regular functions: "function_name"
        - Class/struct methods: "ClassName::method_name"
        - Namespace functions: "namespace::function_name"
        - Nested namespaces: "ns1::ns2::function_name"
        - Namespace + class: "namespace::ClassName::method_name"
        - Nested classes/structs: "OuterClass::InnerClass::method"

        Args:
            file_path: Path to the source file
            function_name: Name of the function to extract
            signature: Optional string to match against parameter types for overload
                       disambiguation. Use partial type names like "TMProposeSet"
                       to select a specific overload.

        Returns:
            Tuple of (code_text, start_line, end_line)
        """
        source = file_path.read_bytes()

        # Use the SimpleCppParser to extract function - returns ExtractionResult
        result = self.cpp_parser.extract_function_by_name(source, function_name, signature)

        if not result:
            if signature:
                raise ValueError(
                    f"Function '{function_name}' with signature matching '{signature}' not found in {file_path}"
                )
            raise ValueError(f"Function '{function_name}' not found in {file_path}")

        logger.debug(f"Found function '{function_name}' at {result.location}")
        return result.to_tuple()  # For backwards compatibility

    def _extract_node_marker(self, file_path: Path, result, marker: str, context_name: str) -> Tuple[str, int, int]:
        """
        Extract a marked section from within any extracted node.

        Args:
            file_path: Path to the file
            result: ExtractionResult containing the node
            marker: Marker name to extract
            context_name: Name for error messages (e.g., "function 'foo'" or "variable 'bar'")

        Returns:
            Tuple of (code_text, start_line, end_line)
        """
        node = result.node

        if node:
            marker_start, marker_end = self._single_marker_range_in_node(node, marker, context_name)

            # Extract the marked section from the file
            lines = file_path.read_text().splitlines()
            marker_lines = lines[marker_start - 1 : marker_end]
            marker_text = "\n".join(marker_lines)

            actual_start_line = marker_start
            actual_end_line = marker_end
        else:
            # Fallback: parse just the text as a standalone tree
            node_text = result.text
            node_tree = self.parser.parse(node_text.encode("utf8"))
            node = node_tree.root_node

            marker_start, marker_end = self._single_marker_range_in_node(node, marker, context_name)

            # Adjust line numbers to be relative to the file
            actual_start_line = result.start_line + marker_start - 1
            actual_end_line = result.start_line + marker_end - 1

            node_lines = node_text.splitlines()
            marker_lines = node_lines[marker_start - 1 : marker_end]
            marker_text = "\n".join(marker_lines)

        logger.debug(f"Found marker '{marker}' in {context_name} at lines {actual_start_line}-{actual_end_line}")
        return marker_text, actual_start_line, actual_end_line

    def _extract_enclosed_node_marker(
        self, file_path: Path, result: ExtractionResult, marker: str, context_name: str
    ) -> EnclosedMarkerResult:
        """Extract a marker and keep the enclosing node range."""
        marker_text, marker_start, marker_end = self._extract_node_marker(
            file_path, result, marker, context_name
        )
        return EnclosedMarkerResult(
            marker_text=marker_text,
            marker_start_line=marker_start,
            marker_end_line=marker_end,
            enclosure_text=result.text,
            enclosure_start_line=result.start_line,
            enclosure_end_line=result.end_line,
            enclosure_kind=result.node_type,
            enclosure_name=result.qualified_name,
        )

    def _find_function_marker_result(
        self, file_path: Path, function_name: str, marker: str, signature: str = None
    ) -> ExtractionResult:
        """Find the overload/function node that contains a marker."""
        source = file_path.read_bytes()

        nodes = self.cpp_parser._find_all_nodes_by_qualified_name(source, function_name, ["function_definition"])
        if not nodes:
            raise ValueError(f"Function '{function_name}' not found in {file_path}")

        if signature is not None:
            matching = [node for node in nodes if signature in self.cpp_parser._extract_parameter_signature(node)]
            if not matching:
                available = [self.cpp_parser._extract_parameter_signature(node) for node in nodes]
                raise ValueError(
                    f"No overload of function '{function_name}' matches signature '{signature}'. "
                    f"Available: {available}"
                )
            nodes = matching

        matching_results: List[ExtractionResult] = []

        for node in nodes:
            # For each node, build an ExtractionResult covering the full function
            # (including body for macro-attributed functions)
            if node.type == "declaration":
                body_node = find_following_body(node)
                if body_node:
                    text = source[node.start_byte : body_node.end_byte].decode("utf8")
                    search_node = body_node
                    start = node.start_point.row + 1
                    end = body_node.end_point.row + 1
                else:
                    continue  # Declaration-only, no body to search
            else:
                text = node.text.decode("utf8") if node.text else ""
                search_node = node
                start = node.start_point.row + 1
                end = node.end_point.row + 1

            marker_ranges = self._find_marker_ranges_in_node(search_node).get(marker, [])
            if len(marker_ranges) > 1:
                locations = ", ".join(f"{start}-{end}" for start, end in marker_ranges)
                raise ValueError(
                    f"Marker '{marker}' found multiple times in function '{function_name}': {locations}"
                )
            if marker_ranges:
                result = ExtractionResult(
                    text=text,
                    start_line=start,
                    end_line=end,
                    node=search_node,
                    node_type=node.type,
                    qualified_name=function_name,
                )
                matching_results.append(result)

        if len(matching_results) == 1:
            return matching_results[0]

        if len(matching_results) > 1:
            if signature is None:
                signatures = [self.cpp_parser._extract_parameter_signature(node) for node in nodes]
                raise ValueError(
                    f"Marker '{marker}' found in multiple overloads of function '{function_name}'. "
                    f"Use signature= to disambiguate. Available signatures: {signatures}"
                )
            raise ValueError(
                f"Marker '{marker}' matched multiple overloads of function '{function_name}' "
                f"with signature '{signature}'"
            )

        raise ValueError(
            f"Marker '{marker}' not found in any overload of function '{function_name}'. "
            f"Found {len(nodes)} overload(s) but none contain the marker."
        )

    def _normalize_auto_enclosure_node(self, node: Node) -> Node:
        """Prefer attached template_declaration nodes over their inner declaration."""
        parent = node.parent
        if parent and parent.type == "template_declaration":
            return parent
        return node

    def _is_auto_enclosure_candidate(self, node: Node) -> bool:
        """Return True for C++ nodes that make useful standalone context."""
        if node.type not in self._AUTO_ENCLOSURE_NODE_TYPES:
            return False
        if node.type == "declaration" and node.parent and node.parent.type == "compound_statement":
            return False
        return True

    def _find_closest_enclosing_node(self, root: Node, start_line: int, end_line: int) -> Optional[Node]:
        """Find the smallest useful C++ node that fully contains a line range."""
        best: Optional[Node] = None
        best_score: Optional[Tuple[int, ...]] = None

        def touches_marker(node: Node) -> bool:
            node_start = node.start_point.row + 1
            node_end = node.end_point.row + 1
            return node_start <= start_line and end_line <= node_end

        def is_inside_marker(node: Node) -> bool:
            node_start = node.start_point.row + 1
            node_end = node.end_point.row + 1
            return start_line <= node_start and node_end <= end_line

        def consider(node: Node) -> None:
            nonlocal best, best_score
            enclosure = self._normalize_auto_enclosure_node(node)
            if not self._is_auto_enclosure_candidate(enclosure):
                return

            node_start = enclosure.start_point.row + 1
            node_end = enclosure.end_point.row + 1
            span = (node_end - node_start, enclosure.end_byte - enclosure.start_byte)

            score: Tuple[int, ...]
            if node_start == start_line and node_end == end_line:
                score = (0, span[0], span[1])
            elif is_inside_marker(enclosure):
                slack = (node_start - start_line) + (end_line - node_end)
                # If a marker wraps a larger construct that contains smaller
                # constructs, prefer the wrapped construct nearest the marker
                # bounds instead of diving into the smallest nested node.
                score = (1, slack, -span[0], -span[1])
            elif touches_marker(enclosure):
                score = (2, span[0], span[1])
            else:
                return

            if best is None or best_score is None or score < best_score:
                best = enclosure
                best_score = score

        def walk(node: Node) -> None:
            if not (touches_marker(node) or is_inside_marker(node)):
                return
            consider(node)
            for child in node.children:
                walk(child)

        walk(root)
        return best

    def _same_node_range(self, left: Node, right: Node) -> bool:
        """Return True when two nodes refer to the same source span."""
        return (
            left.start_byte == right.start_byte
            and left.end_byte == right.end_byte
            and left.type == right.type
        )

    def _top_level_auto_enclosures_inside_range(
        self, root: Node, start_line: int, end_line: int
    ) -> List[Node]:
        """Find top-level useful C++ constructs fully wrapped by a marker range."""
        candidates: List[Node] = []
        seen = set()

        def is_inside(node: Node) -> bool:
            node_start = node.start_point.row + 1
            node_end = node.end_point.row + 1
            return start_line <= node_start and node_end <= end_line

        def walk(node: Node) -> None:
            if node.end_point.row + 1 < start_line or node.start_point.row + 1 > end_line:
                return

            enclosure = self._normalize_auto_enclosure_node(node)
            if self._is_auto_enclosure_candidate(enclosure) and is_inside(enclosure):
                key = (enclosure.start_byte, enclosure.end_byte, enclosure.type)
                if key not in seen:
                    seen.add(key)
                    candidates.append(enclosure)

            for child in node.children:
                walk(child)

        walk(root)

        top_level: List[Node] = []
        for node in candidates:
            contained_by_other = False
            for other in candidates:
                if self._same_node_range(node, other):
                    continue
                if (
                    other.start_byte <= node.start_byte
                    and node.end_byte <= other.end_byte
                    and (other.start_byte, other.end_byte) != (node.start_byte, node.end_byte)
                ):
                    contained_by_other = True
                    break
            if not contained_by_other:
                top_level.append(node)

        return top_level

    def _find_marker_ranges_in_node(self, node: Node) -> Dict[str, List[Tuple[int, int]]]:
        """Find all marker ranges, preserving duplicate marker names."""
        comment_query = Query(self.language, "(comment) @comment")
        cursor = QueryCursor(comment_query)
        matches = cursor.matches(node)

        markers: Dict[str, List[Tuple[int, int]]] = {}
        active_markers: Dict[str, List[int]] = {}

        for _, captures in matches:
            comments = captures.get("comment", [])
            for comment in comments:
                if not comment or not comment.text:
                    continue

                text = comment.text.decode("utf8")
                line_num = comment.start_point.row + 1

                if "//@@start" in text:
                    match = re.search(r"//@@start\s+([\w-]+)", text)
                    if match:
                        active_markers.setdefault(match.group(1), []).append(line_num + 1)
                elif "//@@end" in text:
                    match = re.search(r"//@@end\s+([\w-]+)", text)
                    if match:
                        marker_name = match.group(1)
                        starts = active_markers.get(marker_name)
                        if starts:
                            start_line = starts.pop()
                            markers.setdefault(marker_name, []).append((start_line, line_num - 1))
                            if not starts:
                                del active_markers[marker_name]
                        else:
                            logger.warning(f"Found //@@end {marker_name} without matching //@@start")

        for marker_name in active_markers:
            logger.warning(f"Marker '{marker_name}' was not closed with //@@end")

        return markers

    def _single_marker_range_in_node(self, node: Node, marker: str, context_name: str) -> Tuple[int, int]:
        """Return a single marker range or raise on missing/ambiguous markers."""
        markers = self._find_marker_ranges_in_node(node)

        if marker not in markers:
            available = ", ".join(markers.keys()) if markers else "none"
            raise ValueError(f"Marker '{marker}' not found in {context_name}. Available: {available}")

        marker_ranges = markers[marker]
        if len(marker_ranges) > 1:
            locations = ", ".join(f"{start}-{end}" for start, end in marker_ranges)
            raise ValueError(f"Marker '{marker}' is ambiguous in {context_name}. Found multiple ranges: {locations}")

        return marker_ranges[0]

    def _first_name_token(self, node: Node, last: bool = False) -> Optional[str]:
        """Best-effort name extraction for auto-enclosure metadata."""
        if node.type in self._NAME_NODE_TYPES and node.text:
            return node.text.decode("utf8")
        children = reversed(node.children) if last else node.children
        for child in children:
            name = self._first_name_token(child, last=last)
            if name:
                return name
        return None

    def _declarator_name(self, node: Node) -> Optional[str]:
        """Extract a variable/declaration name without taking the type token."""
        declarator = node.child_by_field_name("declarator")
        if declarator is not None:
            function_name, qualifiers = extract_function_name_and_qualifiers(declarator, [])
            if function_name:
                return "::".join(qualifiers + [function_name]) if qualifiers else function_name
            return self._first_name_token(declarator, last=True)
        return None

    def _auto_enclosure_name(self, node: Node) -> Optional[str]:
        """Return a human-readable name for an auto-selected enclosure."""
        if node.type == "template_declaration":
            for child in node.children:
                if child.type == "template_parameter_list":
                    continue
                name = self._auto_enclosure_name(child)
                if name:
                    return name
            return None
        if node.type == "lambda_expression":
            return "lambda"
        if node.type == "function_definition":
            name = self._declarator_name(node)
            if name:
                return name
        if node.type in {"declaration", "field_declaration"}:
            name = self._declarator_name(node)
            if name:
                return name
        if node.type in {"class_specifier", "struct_specifier", "enum_specifier"}:
            name_node = node.child_by_field_name("name")
            if name_node is not None:
                return node_text(name_node)
        if node.type == "alias_declaration":
            name_node = node.child_by_field_name("name")
            if name_node is not None:
                return node_text(name_node)
        if node.type == "type_definition":
            name = self._declarator_name(node)
            if name:
                return name
            declarator = node.child_by_field_name("declarator")
            if declarator is not None:
                return node_text(declarator)
        if node.type == "namespace_definition":
            name_node = node.child_by_field_name("name")
            if name_node is not None:
                return node_text(name_node)
        return self._first_name_token(node)

    def extract_marker(self, file_path: Path, marker: str) -> Tuple[str, int, int]:
        """Extract a marker, preserving duplicate-marker ambiguity."""
        source = file_path.read_bytes()
        root = self.parse_bytes(source)
        marker_start, marker_end = self._single_marker_range_in_node(root, marker, "file")
        marker_text = "\n".join(source.decode("utf8").splitlines()[marker_start - 1 : marker_end])
        return marker_text, marker_start, marker_end

    def extract_marker_enclosed(self, file_path: Path, marker: str) -> EnclosedMarkerResult:
        """Extract a marker with the closest enclosing function/class-like C++ node."""
        source = file_path.read_bytes()
        root = self.parse_bytes(source)
        markers = self._find_marker_ranges_in_node(root)

        if marker not in markers:
            available = ", ".join(markers.keys()) if markers else "none"
            raise ValueError(f"Marker '{marker}' not found. Available markers: {available}")

        marker_ranges = markers[marker]
        if len(marker_ranges) > 1:
            locations = ", ".join(f"{start}-{end}" for start, end in marker_ranges)
            raise ValueError(f"Marker '{marker}' is ambiguous. Found multiple ranges: {locations}")

        marker_start, marker_end = marker_ranges[0]
        enclosing_node = self._find_closest_enclosing_node(root, marker_start, marker_end)
        if enclosing_node is None:
            raise ValueError(f"No enclosing function/class found for marker '{marker}'")

        enclosure_start = enclosing_node.start_point.row + 1
        enclosure_end = enclosing_node.end_point.row + 1
        enclosure_contains_marker = enclosure_start <= marker_start and marker_end <= enclosure_end
        marker_wraps_enclosure = marker_start <= enclosure_start and enclosure_end <= marker_end
        if not enclosure_contains_marker:
            top_level_wrapped = self._top_level_auto_enclosures_inside_range(
                root, marker_start, marker_end
            )
            if not (
                marker_wraps_enclosure
                and len(top_level_wrapped) == 1
                and self._same_node_range(top_level_wrapped[0], enclosing_node)
            ):
                raise ValueError(f"No enclosing function/class contains marker '{marker}'")

        result = node_to_result(enclosing_node, self._auto_enclosure_name(enclosing_node) or "")
        marker_text = "\n".join(source.decode("utf8").splitlines()[marker_start - 1 : marker_end])
        return EnclosedMarkerResult(
            marker_text=marker_text,
            marker_start_line=marker_start,
            marker_end_line=marker_end,
            enclosure_text=result.text,
            enclosure_start_line=result.start_line,
            enclosure_end_line=result.end_line,
            enclosure_kind=result.node_type,
            enclosure_name=result.qualified_name,
        )

    def extract_function_marker(
        self, file_path: Path, function_name: str, marker: str, signature: str = None
    ) -> Tuple[str, int, int]:
        """Extract a marked section from within a function.

        When multiple overloads exist, searches all of them for the marker.
        Also handles macro-attributed functions via extract_function.
        """
        result = self._find_function_marker_result(file_path, function_name, marker, signature)
        return self._extract_node_marker(file_path, result, marker, f"function '{function_name}'")

    def extract_function_marker_enclosed(
        self, file_path: Path, function_name: str, marker: str, signature: str = None
    ) -> EnclosedMarkerResult:
        """Extract a function marker with its enclosing function range."""
        result = self._find_function_marker_result(file_path, function_name, marker, signature)
        return self._extract_enclosed_node_marker(file_path, result, marker, f"function '{function_name}'")

    def extract_struct(self, file_path: Path, struct_name: str) -> Tuple[str, int, int]:
        """
        Extract a C++ struct or class definition by name.

        Supports:
        - Simple structs/classes: "MyStruct" or "MyClass"
        - Namespaced: "namespace::MyClass"
        - Nested: "OuterClass::InnerClass"

        Args:
            file_path: Path to the file
            struct_name: Name of the struct/class (can include :: for namespace/nesting)

        Returns:
            Tuple of (struct_text, start_line, end_line)

        Raises:
            ValueError: If struct/class not found
        """
        source = file_path.read_bytes()

        # Use the SimpleCppParser to extract struct/class - returns ExtractionResult
        result = self.cpp_parser.extract_struct_or_class_by_name(source, struct_name)

        if not result:
            raise ValueError(f"Struct/class '{struct_name}' not found in {file_path}")

        logger.debug(f"Found struct/class '{struct_name}' at {result.location}")
        return result.to_tuple()  # For backwards compatibility

    def extract_struct_marker(self, file_path: Path, struct_name: str, marker: str) -> Tuple[str, int, int]:
        """Extract a marked section from within a struct/class/enum/variable declaration."""
        source = file_path.read_bytes()
        result = self.cpp_parser.extract_struct_or_class_by_name(source, struct_name)

        if not result:
            raise ValueError(f"Struct/class/variable '{struct_name}' not found in {file_path}")

        return self._extract_node_marker(file_path, result, marker, f"'{struct_name}'")

    def extract_struct_marker_enclosed(
        self, file_path: Path, struct_name: str, marker: str
    ) -> EnclosedMarkerResult:
        """Extract a struct/class marker with its enclosing declaration range."""
        source = file_path.read_bytes()
        result = self.cpp_parser.extract_struct_or_class_by_name(source, struct_name)

        if not result:
            raise ValueError(f"Struct/class/variable '{struct_name}' not found in {file_path}")

        return self._extract_enclosed_node_marker(file_path, result, marker, f"'{struct_name}'")

    def extract_function_macro(self, file_path: Path, macro_spec: Dict) -> Tuple[str, int, int]:
        """
        Extract a function defined by a macro (like DEFINE_JS_FUNCTION).

        Args:
            file_path: Path to the file
            macro_spec: Dict with:
                - 'name': Macro name (required)
                - 'arg0', 'arg1', etc: Filter by argument at position

        Returns:
            Tuple of (code_text, start_line, end_line)

        Raises:
            ValueError: If no match or multiple matches found
        """
        source = file_path.read_bytes()

        macro_name = macro_spec.get("name")
        if not macro_name:
            raise ValueError("macro spec must include 'name'")

        # Find all instances of the macro
        results = self.macro_finder.find_by_name(source, macro_name)

        # Filter by any specified arguments
        for key, value in macro_spec.items():
            if key.startswith("arg"):
                position = int(key[3:])
                results = [
                    r for r in results if position < len(r["arguments"]) and r["arguments"][position].strip() == value
                ]

        # Check we have exactly one match
        if not results:
            filters = [f"{k}={v}" for k, v in macro_spec.items() if k != "name"]
            raise ValueError(f"No {macro_name} found with {', '.join(filters)}")

        if len(results) > 1:
            raise ValueError(
                f"Multiple {macro_name} instances found ({len(results)} matches). "
                f"Please be more specific. Found at lines: "
                f"{', '.join(str(r['line']) for r in results[:5])}"
                f"{'...' if len(results) > 5 else ''}"
            )

        # Return the single match - need to get FULL text with body
        result = results[0]

        # Get the full text directly from the node (result['text'] is truncated)
        # We need to re-extract with full_body=True
        macro_node_start = result["start_byte"]
        macro_node_end = result["end_byte"]
        full_text = source[macro_node_start:macro_node_end].decode("utf8")

        start_line = result["line"]
        # Calculate end line from the full text
        end_line = start_line + full_text.count("\n")

        logger.debug(f"Found {macro_name} at lines {start_line}-{end_line}")
        return full_text, start_line, end_line

    def extract_function_macro_marker(self, file_path: Path, macro_spec: Dict, marker: str) -> Tuple[str, int, int]:
        """
        Extract a marked section from within a function-defining macro.

        Args:
            file_path: Path to the file
            macro_spec: Dict with macro name and optional argument filters
            marker: Marker name to extract

        Returns:
            Tuple of (code_text, start_line, end_line)
        """
        source = file_path.read_bytes()

        macro_name = macro_spec.get("name")
        if not macro_name:
            raise ValueError("macro spec must include 'name'")

        # Build macro_args dict for filtering
        macro_args = {}
        for key, value in macro_spec.items():
            if key.startswith("arg"):
                macro_args[key] = value

        # Use the unified macro_finder to find and extract
        section_code = self.macro_finder.extract_macro_section(
            source, macro_name, marker, macro_args if macro_args else None
        )

        # Get line info for the section
        info = self.macro_finder.find_markers_in_macro(source, macro_name, macro_args if macro_args else None)

        if marker not in info["markers"]:
            raise ValueError(f"Marker '{marker}' not found in macro")

        start_line, end_line = info["markers"][marker]

        logger.debug(f"Found marker '{marker}' in {macro_name} at lines {start_line}-{end_line}")
        return section_code, start_line, end_line

    def extract_function_macro_marker_enclosed(
        self, file_path: Path, macro_spec: Dict, marker: str
    ) -> EnclosedMarkerResult:
        """Extract a macro-defined function marker with the full macro function range."""
        source = file_path.read_bytes()

        macro_name = macro_spec.get("name")
        if not macro_name:
            raise ValueError("macro spec must include 'name'")

        macro_args = {}
        for key, value in macro_spec.items():
            if key.startswith("arg"):
                macro_args[key] = value

        info = self.macro_finder.find_markers_in_macro(source, macro_name, macro_args if macro_args else None)
        if marker not in info["markers"]:
            raise ValueError(f"Marker '{marker}' not found in macro")

        macro = info["macro"]
        node = macro["node"]
        if node is None:
            raise ValueError(f"Macro {macro_name} has no associated node")

        result = ExtractionResult(
            text=source[macro["start_byte"] : macro["end_byte"]].decode("utf8"),
            start_line=macro["line"],
            end_line=macro["end_point"][0] + 1,
            start_column=macro["start_point"][1],
            end_column=macro["end_point"][1],
            node=node,
            node_type=node.type,
            qualified_name=macro_name,
        )
        return self._extract_enclosed_node_marker(file_path, result, marker, f"macro '{macro_name}'")

    def extract_macro_definition(self, file_path: Path, macro_name: str) -> Tuple[str, int, int]:
        """
        Extract a C/C++ macro definition (#define statement).

        Args:
            file_path: Path to the file
            macro_name: Name of the macro to extract

        Returns:
            Tuple of (macro_text, start_line, end_line)

        Raises:
            ValueError: If macro definition not found
        """
        source = file_path.read_bytes()

        # Use the macro definition finder to extract
        text, start_line, end_line = self.macro_def_finder.extract_definition_text(source, macro_name)

        logger.debug(f"Found macro definition '{macro_name}' at lines {start_line}-{end_line}")
        return text, start_line, end_line

    def list_symbols(self, file_path: Path) -> List[dict]:
        """List all extractable symbols in a C++ file."""
        source = file_path.read_bytes()
        symbols = self.cpp_parser.list_symbols(source)

        # Also find markers
        root = self.parse_file(file_path)
        markers = self.find_markers_in_node(root)
        for marker_name, (start_line, end_line) in markers.items():
            symbols.append(
                {
                    "name": marker_name,
                    "kind": "marker",
                    "param": "marker",
                    "line": start_line,
                    "end_line": end_line,
                }
            )

        return symbols

    def find_class_or_namespace(self, file_path: Path, name: str) -> Optional[Node]:
        """
        Find a class or namespace by name.

        Returns:
            The node representing the class/namespace, or None if not found
        """
        root = self.parse_file(file_path)

        # Query for classes and namespaces
        query_text = f'''
        [
          ((class_specifier
            name: (type_identifier) @class_name (#eq? @class_name "{name}")
          ) @class)
          
          ((namespace_definition
            name: (identifier) @ns_name (#eq? @ns_name "{name}")
          ) @namespace)
        ]
        '''

        try:
            query = Query(self.language, query_text)
            cursor = QueryCursor(query)
            matches = cursor.matches(root)

            for _, captures in matches:
                # Check for class
                class_nodes = captures.get("class", [])
                if class_nodes:
                    return class_nodes[0]

                # Check for namespace
                ns_nodes = captures.get("namespace", [])
                if ns_nodes:
                    return ns_nodes[0]

        except Exception as e:
            logger.error(f"Query failed: {e}")

        return None
