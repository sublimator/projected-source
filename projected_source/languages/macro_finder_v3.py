#!/usr/bin/env python3
"""
Library for finding and extracting C/C++ macros using tree-sitter.
Version 3: Ultra-DRY implementation with TypedDict and modern patterns.
"""

import logging
from enum import Enum
from functools import lru_cache
from typing import Any, Callable, Dict, List, Optional, Tuple, TypedDict

import tree_sitter_cpp as tscpp
from tree_sitter import Language, Node, Parser, Query, QueryCursor

logger = logging.getLogger(__name__)

# Type definitions
Point = Tuple[int, int]  # (row, column)


class MacroResult(TypedDict):
    """Type definition for macro search results."""

    macro: str
    arguments: List[str]
    text: str
    start_byte: int
    end_byte: int
    start_point: Point
    end_point: Point
    line: int
    type: Optional[str]  # 'call' or 'definition'
    node: Optional[Node]  # The actual tree-sitter node
    args_node: Optional[Node]  # The arguments node


class PredicateType(Enum):
    """Query predicate types."""

    EQUALS = "#eq?"
    MATCH = "#match?"
    NOT_EQUALS = "#not-eq?"
    NOT_MATCH = "#not-match?"


class MacroFinder:
    """
    Ultra-DRY macro finder using tree-sitter.
    Focuses on code reuse and clean architecture.
    """

    __slots__ = ("language", "parser", "_query_cache")

    # Single query template for all macro searches
    QUERY_TEMPLATE = """
    [
      ((call_expression
        function: (identifier) @macro_name {predicate}
        arguments: (argument_list) @args
      ) @macro_usage)
      
      ((function_definition
        declarator: (function_declarator
          declarator: (identifier) @macro_name {predicate}
          parameters: (parameter_list) @args
        )
      ) @macro_usage)
    ]
    """

    def __init__(self):
        self.language = Language(tscpp.language())
        self.parser = Parser(self.language)
        self._query_cache = {}

    # ==================== Public API ====================

    def find_by_name(self, source: bytes, name: str) -> List[MacroResult]:
        """Find all macros with exact name match."""
        return self._execute_query(source, self._build_query(PredicateType.EQUALS, name))

    def find_by_pattern(self, source: bytes, pattern: str) -> List[MacroResult]:
        """Find all macros matching regex pattern."""
        return self._execute_query(source, self._build_query(PredicateType.MATCH, pattern))

    def find_by_argument(self, source: bytes, name: str, arg_pos: int, arg_val: str) -> List[MacroResult]:
        """Find macros where specific argument has specific value."""

        def arg_filter(result: MacroResult) -> bool:
            args = result["arguments"]
            return arg_pos < len(args) and args[arg_pos].strip() == arg_val

        return self._execute_query(source, self._build_query(PredicateType.EQUALS, name), filter_fn=arg_filter)

    def find_all(self, source: bytes, names: List[str]) -> List[MacroResult]:
        """Find all occurrences of multiple macro names."""
        # Use regex alternation for efficiency
        pattern = "|".join(f"^{name}$" for name in names)
        return self.find_by_pattern(source, pattern)

    def walk_tree(self, source: bytes, names: List[str]) -> List[MacroResult]:
        """Alternative tree-walking approach for simple searches."""
        tree = self.parser.parse(source)
        names_set = set(names)
        results = []

        def visit(node: Node):
            result = self._check_node_for_macro(node, names_set)
            if result:
                results.append(result)

            for child in node.children:
                visit(child)

        visit(tree.root_node)
        return results

    # ==================== Private DRY Methods ====================

    def _build_query(self, predicate_type: PredicateType, value: str) -> str:
        """Build query string with specified predicate."""
        predicate = f'({predicate_type.value} @macro_name "{value}")'
        return self.QUERY_TEMPLATE.format(predicate=predicate)

    @lru_cache(maxsize=32)
    def _get_query(self, query_text: str) -> Query:
        """Get or create cached Query object."""
        return Query(self.language, query_text)

    def _execute_query(
        self, source: bytes, query_text: str, filter_fn: Optional[Callable[[MacroResult], bool]] = None
    ) -> List[MacroResult]:
        """Execute query and process results with optional filtering."""
        tree = self.parser.parse(source)

        try:
            query = self._get_query(query_text)
            cursor = QueryCursor(query)
            matches = cursor.matches(tree.root_node)

            return self._process_matches(matches, filter_fn)
        except Exception as e:
            logger.error(f"Query failed: {e}")
            return []

    def _process_matches(self, matches, filter_fn: Optional[Callable[[MacroResult], bool]] = None) -> List[MacroResult]:
        """Process query matches into results with optional filtering."""
        results = []

        for pattern_index, captures in matches:
            macro_nodes = captures.get("macro_usage", [])
            macro_name_nodes = captures.get("macro_name", [])
            args_nodes = captures.get("args", [])

            if not (macro_nodes and args_nodes):
                continue

            # Build result
            result = self._build_result(
                macro_nodes[0], args_nodes[0], macro_name_nodes[0] if macro_name_nodes else None
            )

            # Apply filter if provided
            if filter_fn is None or filter_fn(result):
                results.append(result)

        return results

    def _build_result(self, macro_node: Node, args_node: Node, name_node: Optional[Node] = None) -> MacroResult:
        """Build a MacroResult from nodes."""
        # Extract macro name
        if name_node:
            macro_name = name_node.text.decode("utf8")
        else:
            # Fallback: extract from macro_node
            macro_name = self._extract_macro_name(macro_node)

        # Determine type
        node_type = "definition" if macro_node.type == "function_definition" else "call"

        return MacroResult(
            macro=macro_name,
            arguments=self._extract_arguments(args_node),
            text=self._extract_text(macro_node, full_body=False),
            start_byte=macro_node.start_byte,
            end_byte=macro_node.end_byte,
            start_point=(macro_node.start_point.row, macro_node.start_point.column),
            end_point=(macro_node.end_point.row, macro_node.end_point.column),
            line=macro_node.start_point.row + 1,
            type=node_type,
            node=macro_node,
            args_node=args_node,
        )

    def _extract_text(self, node: Node, full_body: bool = False) -> str:
        """Extract text from node with optional body truncation."""
        text = node.text.decode("utf8")

        if not full_body and node.type == "function_definition":
            # Truncate at first brace for function definitions
            brace_pos = text.find("{")
            if brace_pos > 0:
                text = text[:brace_pos].strip()

        return text

    def _extract_macro_name(self, node: Node) -> str:
        """Extract macro name from a macro usage node."""
        if node.type == "call_expression":
            func_node = node.child_by_field_name("function")
            if func_node:
                return func_node.text.decode("utf8")
        elif node.type == "function_definition":
            declarator = node.child_by_field_name("declarator")
            if declarator and declarator.type == "function_declarator":
                func_id = declarator.child_by_field_name("declarator")
                if func_id:
                    return func_id.text.decode("utf8")
        return ""

    def _extract_arguments(self, args_node: Optional[Node]) -> List[str]:
        """Extract arguments from argument_list or parameter_list node."""
        if not args_node:
            return []

        args = []

        if args_node.type == "parameter_list":
            # Handle function definition parameters
            for child in args_node.children:
                if child.type == "parameter_declaration":
                    # Extract parameter name (last identifier)
                    tokens = child.text.decode("utf8").split()
                    if tokens:
                        args.append(tokens[-1])
                elif child.type not in ("(", ")", ","):
                    args.append(child.text.decode("utf8").strip())

        elif args_node.type == "argument_list":
            # Handle function call arguments
            current_arg = []
            for child in args_node.children:
                if child.type == "(":
                    continue
                elif child.type == ",":
                    if current_arg:
                        args.append("".join(current_arg).strip())
                        current_arg = []
                elif child.type == ")":
                    if current_arg:
                        args.append("".join(current_arg).strip())
                else:
                    current_arg.append(child.text.decode("utf8"))

        return args

    def _check_node_for_macro(self, node: Node, names: set) -> Optional[MacroResult]:
        """Check if node is a macro call/definition matching any of the names."""
        if node.type == "call_expression":
            func_node = node.child_by_field_name("function")
            if func_node and func_node.type == "identifier":
                name = func_node.text.decode("utf8")
                if name in names:
                    args_node = node.child_by_field_name("arguments")
                    return self._build_result(node, args_node, func_node)

        elif node.type == "function_definition":
            declarator = node.child_by_field_name("declarator")
            if declarator and declarator.type == "function_declarator":
                func_id = declarator.child_by_field_name("declarator")
                if func_id and func_id.type == "identifier":
                    name = func_id.text.decode("utf8")
                    if name in names:
                        params_node = declarator.child_by_field_name("parameters")
                        return self._build_result(node, params_node, func_id)

        return None

    def find_markers_in_node(self, node: Node) -> Dict[str, Tuple[int, int]]:
        """Find comment markers within a node."""
        markers = {}

        # Query for comments
        comment_query = Query(self.language, "(comment) @comment")
        cursor = QueryCursor(comment_query)
        matches = cursor.matches(node)

        current_marker = None
        start_line = None

        for _, captures in matches:
            for comment_node in captures.get("comment", []):
                text = comment_node.text.decode("utf8")

                # Check for start marker
                if "//@@start" in text:
                    parts = text.split("//@@start")
                    if len(parts) > 1:
                        marker_name = parts[1].strip()
                        current_marker = marker_name
                        start_line = comment_node.start_point.row + 1

                # Check for end marker
                elif "//@@end" in text and current_marker:
                    parts = text.split("//@@end")
                    if len(parts) > 1:
                        end_marker = parts[1].strip()
                        if end_marker == current_marker:
                            end_line = comment_node.start_point.row + 1
                            markers[current_marker] = (start_line, end_line)
                            current_marker = None
                            start_line = None

        return markers

    def find_markers_in_macro(
        self, source: bytes, name: str, arg_filters: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """
        Find a macro and extract markers within it.

        Returns dict with:
        - 'macro': The macro info
        - 'markers': Dict of marker_name -> (start_line, end_line) within the macro
        """
        results = self.find_by_name(source, name)

        # Filter by arguments if specified
        if arg_filters:
            filtered = []
            for r in results:
                match = True
                for key, value in arg_filters.items():
                    if key.startswith("arg"):
                        pos = int(key[3:])
                        if pos >= len(r["arguments"]) or r["arguments"][pos].strip() != value:
                            match = False
                            break
                if match:
                    filtered.append(r)
            results = filtered

        if not results:
            raise ValueError(f"Macro {name} not found")
        if len(results) > 1:
            raise ValueError("Multiple macros found, be more specific")

        result = results[0]

        # Now find markers within this node
        markers = self.find_markers_in_node(result["node"])

        return {"macro": result, "markers": markers}

    def extract_macro_section(
        self, source: bytes, macro_name: str, marker_name: str, arg_filters: Optional[Dict[str, str]] = None
    ) -> str:
        """
        Extract a specific marked section from within a macro.

        Args:
            source: Source code bytes
            macro_name: Name of the macro to find
            marker_name: Name of the marker section to extract
            arg_filters: Optional dict to filter by macro arguments (e.g. {'arg0': 'value'})

        Returns:
            The code between the markers
        """
        info = self.find_markers_in_macro(source, macro_name, arg_filters)

        if marker_name not in info["markers"]:
            available = ", ".join(info["markers"].keys())
            raise ValueError(f"Marker '{marker_name}' not found. Available: {available}")

        start_line, end_line = info["markers"][marker_name]

        # Convert to source-relative lines
        lines = source.decode("utf8").splitlines()

        # Extract the marked section
        section_lines = lines[start_line - 1 : end_line]

        # Remove the marker comments themselves
        if section_lines and "//@@start" in section_lines[0]:
            section_lines = section_lines[1:]
        if section_lines and "//@@end" in section_lines[-1]:
            section_lines = section_lines[:-1]

        return "\n".join(section_lines)

    # ==================== Context Manager Support ====================

    def __enter__(self):
        """Support for context manager usage."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Clear cache on exit."""
        self._get_query.cache_clear()
        return False


# ==================== Demo/Test ====================


def demo():
    """Demo the ultra-DRY MacroFinder v3."""
    sample_code = b"""
    #include <stdio.h>
    
    DEFINE_JS_FUNCTION(TestFunc, ctx, data) {
        printf("Test function\n");
        return JS_UNDEFINED;
    }
    
    DEFINE_JS_FUNCTION(AnotherFunc, env, args) {
        printf("Another function\n");
        return JS_NULL;
    }
    
    DEFINE_HOOK_FUNCTION(HookFunc, ctx, data) {
        return 0;
    }
    
    void normal_function() {
        SOME_MACRO(arg1, arg2, arg3);
        DEBUG_LOG("message");
        ASSERT_EQ(a, b);
    }
    """

    print("=" * 80)
    print("Demo: Ultra-DRY MacroFinder v3 with TypedDict")
    print("=" * 80)

    with MacroFinder() as finder:
        # Test 1: Find by exact name
        print("\n1. Find by exact name (DEFINE_JS_FUNCTION):")
        results = finder.find_by_name(sample_code, "DEFINE_JS_FUNCTION")
        for r in results:
            print(f"  Line {r['line']}: {r['macro']}({', '.join(r['arguments'])}) [{r['type']}]")

        # Test 2: Find by pattern
        print("\n2. Find by pattern (^DEFINE_):")
        results = finder.find_by_pattern(sample_code, "^DEFINE_")
        for r in results:
            print(f"  Line {r['line']}: {r['macro']}({', '.join(r['arguments'])}) [{r['type']}]")

        # Test 3: Find by argument value
        print("\n3. Find DEFINE_* with 'data' as 3rd argument:")
        results = finder.find_by_argument(sample_code, "DEFINE_JS_FUNCTION", 2, "data")
        for r in results:
            print(f"  Line {r['line']}: {r['macro']}({', '.join(r['arguments'])})")

        # Test 4: Find multiple macros
        print("\n4. Find multiple specific macros:")
        results = finder.find_all(sample_code, ["SOME_MACRO", "DEBUG_LOG", "ASSERT_EQ"])
        for r in results:
            print(f"  Line {r['line']}: {r['macro']}({', '.join(r['arguments'])}) [{r['type']}]")

        # Test 5: Tree walking
        print("\n5. Tree walking for DEFINE_JS_FUNCTION:")
        results = finder.walk_tree(sample_code, ["DEFINE_JS_FUNCTION"])
        for r in results:
            print(f"  Line {r['line']}: {r['macro']}({', '.join(r['arguments'])}) [{r['type']}]")

        # Show result structure
        if results:
            print("\n6. Example MacroResult structure:")
            import json

            print(json.dumps(results[0], indent=2))


if __name__ == "__main__":
    demo()
