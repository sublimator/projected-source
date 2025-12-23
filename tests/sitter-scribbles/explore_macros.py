#!/usr/bin/env python3
"""
Explore tree-sitter's handling of C/C++ macro definitions.
Let's see what the AST looks like for #define macros.
"""

import tree_sitter_cpp as tscpp
from tree_sitter import Language, Parser, Node
from pathlib import Path


def print_node(node: Node, indent: int = 0):
    """Pretty print a node and its children."""
    spaces = "  " * indent
    text_preview = node.text.decode("utf8")[:50].replace("\n", "\\n")
    if len(node.text) > 50:
        text_preview += "..."

    print(
        f"{spaces}{node.type} [{node.start_point.row}:{node.start_point.column}-{node.end_point.row}:{node.end_point.column}] '{text_preview}'"
    )

    # Print children
    for child in node.children:
        print_node(child, indent + 1)


def explore_macros(file_path: Path):
    """Explore how tree-sitter parses macro definitions."""
    print(f"\n{'=' * 60}")
    print(f"Exploring: {file_path}")
    print(f"{'=' * 60}\n")

    # Parse the file
    parser = Parser(Language(tscpp.language()))
    source = file_path.read_bytes()
    tree = parser.parse(source)

    # Walk the tree looking for preproc nodes
    def find_macros(node: Node, depth: int = 0):
        # Look for preprocessor directives
        if node.type.startswith("preproc_"):
            print(f"\nFound {node.type}:")

            # Show the node structure
            print_node(node)

            # For macro definitions, show details
            if node.type == "preproc_def":
                # Get the name
                name_node = node.child_by_field_name("name")
                if name_node:
                    print(f"  Macro name: {name_node.text.decode('utf8')}")

                # Get the value/body
                value_node = node.child_by_field_name("value")
                if value_node:
                    value_text = value_node.text.decode("utf8")
                    print(f"  Value type: {value_node.type}")
                    print(f"  Value preview: {value_text[:100]}...")

                # Check for parameters (function-like macros)
                params_node = node.child_by_field_name("parameters")
                if params_node:
                    print(f"  Parameters: {params_node.text.decode('utf8')}")

            elif node.type == "preproc_function_def":
                # Function-like macro
                name_node = node.child_by_field_name("name")
                params_node = node.child_by_field_name("parameters")
                value_node = node.child_by_field_name("value")

                if name_node:
                    print(f"  Function macro: {name_node.text.decode('utf8')}")
                if params_node:
                    print(f"  Parameters: {params_node.text.decode('utf8')}")
                if value_node:
                    print(f"  Body preview: {value_node.text.decode('utf8')[:100]}...")

        # Recurse
        for child in node.children:
            find_macros(child, depth + 1)

    find_macros(tree.root_node)

    print(f"\n{'=' * 60}")
    print("Let's look at the first few nodes in detail:")
    print(f"{'=' * 60}\n")

    # Show first few top-level nodes
    for i, child in enumerate(tree.root_node.children[:5]):
        print(f"\nTop-level node {i}:")
        print_node(child, indent=1)


if __name__ == "__main__":
    # Test on the macro file
    macro_file = Path("../../examples/macro-truncated.h")
    if not macro_file.exists():
        print(f"File not found: {macro_file}")
        print(f"Looking from: {Path.cwd()}")
    else:
        explore_macros(macro_file)
