#!/usr/bin/env python3
"""
Find and extract C/C++ macro DEFINITIONS (#define statements) using tree-sitter.

This is different from macro_finder_v3.py which finds macro USAGES.
This module finds the actual #define statements themselves.
"""

from .utils import node_text

import logging
from typing import List, Optional, Tuple, TypedDict

import tree_sitter_cpp as tscpp
from tree_sitter import Language, Node, Parser, Query, QueryCursor

logger = logging.getLogger(__name__)


class MacroDefinition(TypedDict):
    """Type definition for macro definition results."""

    name: str
    type: str  # 'object' or 'function'
    parameters: Optional[str]  # For function-like macros
    text: str  # Full text including continuations
    lines: int  # Number of lines
    multiline: bool  # Has backslash continuations
    start_byte: int
    end_byte: int
    start_line: int
    end_line: int


class MacroDefinitionFinder:
    """
    Find C/C++ macro definitions (#define statements) using tree-sitter.
    """

    def __init__(self):
        self.language = Language(tscpp.language())
        self.parser = Parser(self.language)

    def find_definition(self, source: bytes, macro_name: str) -> Optional[MacroDefinition]:
        """
        Find a specific macro definition by name.

        Args:
            source: Source code bytes
            macro_name: Name of the macro to find

        Returns:
            MacroDefinition if found, None otherwise
        """
        tree = self.parser.parse(source)

        # Query for specific macro definition
        query_text = f'''
        [
          (preproc_def
            name: (identifier) @name (#eq? @name "{macro_name}")
          ) @macro
          
          (preproc_function_def
            name: (identifier) @name (#eq? @name "{macro_name}")
          ) @macro
        ]
        '''

        query = Query(self.language, query_text)
        cursor = QueryCursor(query)
        matches = cursor.matches(tree.root_node)

        for pattern_index, captures in matches:
            macro_nodes = captures.get("macro", [])
            if macro_nodes:
                return self._build_result(macro_nodes[0])

        return None

    def find_all_definitions(self, source: bytes, prefix: str = None) -> List[MacroDefinition]:
        """
        Find all macro definitions, optionally filtered by prefix.

        Args:
            source: Source code bytes
            prefix: Optional prefix to filter by (e.g. "DEFINE_")

        Returns:
            List of MacroDefinition objects
        """
        tree = self.parser.parse(source)

        # Query for all macro definitions
        query_text = """
        [
          (preproc_def) @macro
          (preproc_function_def) @macro
        ]
        """

        query = Query(self.language, query_text)
        cursor = QueryCursor(query)
        matches = cursor.matches(tree.root_node)

        results = []
        for pattern_index, captures in matches:
            macro_nodes = captures.get("macro", [])
            for node in macro_nodes:
                result = self._build_result(node)
                if result:
                    # Filter by prefix if specified
                    if prefix and not result["name"].startswith(prefix):
                        continue
                    results.append(result)

        return results

    def _build_result(self, node: Node) -> Optional[MacroDefinition]:
        """
        Build a MacroDefinition from a tree-sitter node.

        Args:
            node: A preproc_def or preproc_function_def node

        Returns:
            MacroDefinition object
        """
        # Get the full text including backslash continuations
        full_text = node_text(node)

        # Get the macro name
        name_node = node.child_by_field_name("name")
        if not name_node:
            return None
        name = node_text(name_node)

        # Determine if it's a function-like macro
        is_function = node.type == "preproc_function_def"
        parameters = None
        if is_function:
            params_node = node.child_by_field_name("parameters")
            if params_node:
                parameters = node_text(params_node)

        # Count lines and check for multi-line
        lines = full_text.count("\n") + 1
        is_multiline = "\\" in full_text and lines > 1

        return MacroDefinition(
            name=name,
            type="function" if is_function else "object",
            parameters=parameters,
            text=full_text,
            lines=lines,
            multiline=is_multiline,
            start_byte=node.start_byte,
            end_byte=node.end_byte,
            start_line=node.start_point.row + 1,
            end_line=node.end_point.row + 1,
        )

    def extract_definition_text(self, source: bytes, macro_name: str) -> Tuple[str, int, int]:
        """
        Extract macro definition text with line numbers.

        Args:
            source: Source code bytes
            macro_name: Name of the macro

        Returns:
            Tuple of (text, start_line, end_line)

        Raises:
            ValueError: If macro not found
        """
        result = self.find_definition(source, macro_name)
        if not result:
            raise ValueError(f"Macro definition '{macro_name}' not found")

        return result["text"], result["start_line"], result["end_line"]


# Demo/test
if __name__ == "__main__":
    test_code = b"""
#define SIMPLE_MACRO 42

#define FUNCTION_MACRO(x, y) ((x) + (y))

#define MULTI_LINE_MACRO \\
    do { \\
        something(); \\
    } while(0)

#define COMPLEX_MACRO(a, b, c) \\
    if (a) { \\
        process(b); \\
        handle(c); \\
    }
"""

    finder = MacroDefinitionFinder()

    # Find specific macro
    result = finder.find_definition(test_code, "MULTI_LINE_MACRO")
    if result:
        print(f"Found {result['name']}:")
        print(f"  Type: {result['type']}")
        print(f"  Lines: {result['start_line']}-{result['end_line']}")
        print(f"  Text:\n{result['text']}")

    print("\nAll macros:")
    for macro in finder.find_all_definitions(test_code):
        print(f"  {macro['name']} ({macro['type']}) - {macro['lines']} lines")
