#!/usr/bin/env python3
"""
Extract macro definitions using tree-sitter.
Focus on getting the full text of multi-line macros.
"""

import tree_sitter_cpp as tscpp
from tree_sitter import Language, Parser, Node, Query, QueryCursor
from pathlib import Path


def extract_macro_definitions(file_path: Path, macro_name: str = None):
    """
    Extract macro definitions from a C/C++ header file.

    Args:
        file_path: Path to the header file
        macro_name: Optional specific macro name to find
    """
    parser = Parser(Language(tscpp.language()))
    source = file_path.read_bytes()
    tree = parser.parse(source)

    # Query for macro definitions
    if macro_name:
        # Look for specific macro
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
    else:
        # Get all macros
        query_text = """
        [
          (preproc_def) @macro
          (preproc_function_def) @macro
        ]
        """

    query = Query(Language(tscpp.language()), query_text)
    cursor = QueryCursor(query)
    matches = cursor.matches(tree.root_node)

    results = []
    for pattern_index, captures in matches:
        for capture_name, nodes in captures.items():
            if capture_name == "macro":
                for node in nodes:
                    # Get the full text including backslash continuations
                    full_text = node.text.decode("utf8")

                    # Get the macro name
                    name_node = node.child_by_field_name("name")
                    name = name_node.text.decode("utf8") if name_node else "unknown"

                    # Get info about the macro
                    is_function = node.type == "preproc_function_def"
                    params = None
                    if is_function:
                        params_node = node.child_by_field_name("parameters")
                        if params_node:
                            params = params_node.text.decode("utf8")

                    # Count lines (multi-line if has backslash continuations)
                    lines = full_text.count("\n") + 1
                    is_multiline = "\\" in full_text and lines > 1

                    results.append(
                        {
                            "name": name,
                            "type": "function" if is_function else "object",
                            "parameters": params,
                            "text": full_text,
                            "lines": lines,
                            "multiline": is_multiline,
                            "start_line": node.start_point.row + 1,
                            "end_line": node.end_point.row + 1,
                        }
                    )

    return results


def demo():
    """Demo extracting macros from the test file."""
    macro_file = Path("../../examples/macro-truncated.h")

    print("=" * 60)
    print("All multi-line macros:")
    print("=" * 60)

    all_macros = extract_macro_definitions(macro_file)

    # Show multi-line macros
    for macro in all_macros:
        if macro["multiline"]:
            print(f"\n{macro['name']} ({macro['type']}) - {macro['lines']} lines")
            if macro["parameters"]:
                print(f"  Parameters: {macro['parameters']}")
            print(f"  Lines {macro['start_line']}-{macro['end_line']}")
            print("  Text:")
            # Show first few lines
            lines = macro["text"].split("\n")
            for i, line in enumerate(lines[:5]):
                print(f"    {line}")
            if len(lines) > 5:
                print(f"    ... ({len(lines) - 5} more lines)")

    print("\n" + "=" * 60)
    print("Extract specific macro: HALF_COUNT")
    print("=" * 60)

    specific = extract_macro_definitions(macro_file, "HALF_COUNT")
    if specific:
        macro = specific[0]
        print(f"\n{macro['name']} - Full text:")
        print(macro["text"])

    print("\n" + "=" * 60)
    print("Summary:")
    print("=" * 60)

    total = len(all_macros)
    multiline = sum(1 for m in all_macros if m["multiline"])
    function_like = sum(1 for m in all_macros if m["type"] == "function")

    print(f"Total macros: {total}")
    print(f"Multi-line macros: {multiline}")
    print(f"Function-like macros: {function_like}")
    print(f"Object-like macros: {total - function_like}")


if __name__ == "__main__":
    demo()
