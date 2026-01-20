"""
C++ specific code extraction using tree-sitter.
"""

import logging
from pathlib import Path
from typing import Dict, Optional, Tuple

import tree_sitter_cpp as tscpp
from tree_sitter import Language, Node, Query, QueryCursor

from ..core.extractor import BaseExtractor
from .cpp_parser import SimpleCppParser
from .macro_definition_finder import MacroDefinitionFinder
from .macro_finder_v3 import MacroFinder

logger = logging.getLogger(__name__)


class CppExtractor(BaseExtractor):
    """C++ specific extractor with function extraction support."""

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
            # Find markers within the node
            markers = self.find_markers_in_node(node)

            if marker not in markers:
                available = ", ".join(markers.keys()) if markers else "none"
                raise ValueError(f"Marker '{marker}' not found in {context_name}. Available: {available}")

            marker_start, marker_end = markers[marker]

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

            markers = self.find_markers_in_node(node)

            if marker not in markers:
                available = ", ".join(markers.keys()) if markers else "none"
                raise ValueError(f"Marker '{marker}' not found in {context_name}. Available: {available}")

            marker_start, marker_end = markers[marker]

            # Adjust line numbers to be relative to the file
            actual_start_line = result.start_line + marker_start - 1
            actual_end_line = result.start_line + marker_end - 1

            node_lines = node_text.splitlines()
            marker_lines = node_lines[marker_start - 1 : marker_end]
            marker_text = "\n".join(marker_lines)

        logger.debug(f"Found marker '{marker}' in {context_name} at lines {actual_start_line}-{actual_end_line}")
        return marker_text, actual_start_line, actual_end_line

    def extract_function_marker(self, file_path: Path, function_name: str, marker: str) -> Tuple[str, int, int]:
        """Extract a marked section from within a function.

        When multiple overloads exist (including template vs non-template),
        searches all of them to find the one containing the marker.
        """
        source = file_path.read_bytes()

        # Find ALL functions with this name (handles template vs non-template, overloads)
        nodes = self.cpp_parser._find_all_nodes_by_qualified_name(source, function_name, ["function_definition"])

        if not nodes:
            raise ValueError(f"Function '{function_name}' not found in {file_path}")

        # Search each overload for the marker
        from .extraction_result import ExtractionResult

        for node in nodes:
            text = node.text.decode("utf8") if node.text else ""
            result = ExtractionResult(
                text=text,
                start_line=node.start_point.row + 1,
                end_line=node.end_point.row + 1,
                start_column=node.start_point.column,
                end_column=node.end_point.column,
                node=node,
                node_type=node.type,
                qualified_name=function_name,
            )

            # Check if this overload has the marker
            markers = self.find_markers_in_node(node)
            if marker in markers:
                return self._extract_node_marker(file_path, result, marker, f"function '{function_name}'")

        # No overload had the marker
        raise ValueError(
            f"Marker '{marker}' not found in any overload of function '{function_name}'. "
            f"Found {len(nodes)} overload(s) but none contain the marker."
        )

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
