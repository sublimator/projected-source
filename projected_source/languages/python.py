"""
Python code extraction using stdlib ast module.

Uses ast.parse() for zero-dependency Python parsing with full accuracy.
Supports dotted paths for nested lookups (e.g., 'MyClass.my_method').
"""

import ast
import io
import logging
import re
import tokenize
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from ..core.extractor import BaseExtractor

logger = logging.getLogger(__name__)


class PythonExtractor(BaseExtractor):
    """Python extractor using stdlib ast module.

    Falls back to BaseExtractor for lines= and inherits marker support.
    Markers use #@@start / #@@end syntax.
    """

    def __init__(self):
        # We don't use tree-sitter for Python, but BaseExtractor needs a language.
        # We override all methods that would use it.
        self._no_treesitter = True

    def parse_file(self, file_path: Path):
        raise NotImplementedError("PythonExtractor uses ast, not tree-sitter")

    def extract_lines(self, file_path: Path, start_line: int, end_line: int) -> Tuple[str, int, int]:
        """Extract lines from a file (reimplemented without tree-sitter).

        Returns the clamped ``(start_line, end_line)`` actually used so that
        callers' permalinks, change-set subtractions, and headers don't get
        out-of-bounds values when the request exceeds the file length.
        """
        lines = file_path.read_text().splitlines()
        start = max(0, start_line - 1)
        end = min(len(lines), end_line)
        code_lines = lines[start:end]
        clamped_start = max(1, start_line) if lines else start_line
        clamped_end = min(len(lines), end_line) if lines else end_line
        return "\n".join(code_lines), clamped_start, clamped_end

    def extract_function(
        self, file_path: Path, function_name: str, signature: str = None
    ) -> Tuple[str, int, int]:
        """
        Extract a Python function or method by name.

        Supports dotted paths for methods:
          - 'my_func' — top-level function
          - 'MyClass.my_method' — method inside a class
          - 'MyClass.InnerClass.method' — nested class method
          - 'outer_func.inner_func' — nested function (closure)

        Includes decorators when present.
        """
        source = file_path.read_text()
        tree = ast.parse(source, filename=str(file_path))

        node = self._find_by_dotted_path(tree, function_name, (ast.FunctionDef, ast.AsyncFunctionDef))
        if not node:
            raise ValueError(f"Function '{function_name}' not found in {file_path}")

        return self._extract_node_text(source, node)

    def extract_struct(self, file_path: Path, class_name: str) -> Tuple[str, int, int]:
        """
        Extract a Python class definition by name.

        Supports dotted paths for nested classes:
          - 'MyClass' — top-level class
          - 'Outer.Inner' — nested class
        """
        source = file_path.read_text()
        tree = ast.parse(source, filename=str(file_path))

        node = self._find_by_dotted_path(tree, class_name, (ast.ClassDef,))
        if not node:
            raise ValueError(f"Class '{class_name}' not found in {file_path}")

        return self._extract_node_text(source, node)

    def extract_variable(self, file_path: Path, var_name: str) -> Tuple[str, int, int]:
        """
        Extract a module-level variable assignment.

        Finds assignments like:
          - MY_CONST = 42
          - MY_CONST: int = 42
          - MY_DICT = { ... }  (multiline)
        """
        source = file_path.read_text()
        tree = ast.parse(source, filename=str(file_path))

        for node in ast.iter_child_nodes(tree):
            name = self._get_assignment_name(node)
            if name == var_name:
                assert isinstance(node, ast.stmt)
                return self._extract_node_text(source, node)

        raise ValueError(f"Variable '{var_name}' not found in {file_path}")

    def extract_marker(self, file_path: Path, marker_name: str) -> Tuple[str, int, int]:
        """Extract code between #@@start and #@@end markers."""
        markers = self.find_markers_in_file(file_path)

        if marker_name not in markers:
            available = ", ".join(markers.keys()) if markers else "none"
            raise ValueError(f"Marker '{marker_name}' not found. Available markers: {available}")

        start_line, end_line = markers[marker_name]
        return self.extract_lines(file_path, start_line, end_line)

    def find_markers_in_file(self, file_path: Path) -> Dict[str, Tuple[int, int]]:
        """Find all #@@start / #@@end markers in a Python file.

        Only standalone comment lines count. Matching raw lines would also
        hit marker-shaped lines inside string literals (truncating real
        markers), so candidate lines are confirmed as comments via tokenize.
        """
        content = file_path.read_text()
        lines = content.splitlines()
        comment_lines = self._standalone_comment_lines(content)

        markers: Dict[str, Tuple[int, int]] = {}
        start_pattern = re.compile(r"^\s*#@@start\s+([\w-]+)\s*$")
        end_pattern = re.compile(r"^\s*#@@end\s+([\w-]+)\s*$")

        open_markers: Dict[str, int] = {}

        for i, line in enumerate(lines):
            if comment_lines is not None and i + 1 not in comment_lines:
                continue
            start_match = start_pattern.match(line)
            if start_match:
                name = start_match.group(1)
                open_markers[name] = i + 2  # line after the marker (1-indexed)

            end_match = end_pattern.match(line)
            if end_match:
                name = end_match.group(1)
                if name in open_markers:
                    markers[name] = (open_markers[name], i)  # line before the marker
                    del open_markers[name]

        return markers

    @staticmethod
    def _standalone_comment_lines(content: str) -> Optional[Set[int]]:
        """1-based line numbers whose only content is a comment.

        Returns None when the file cannot be tokenized, in which case the
        caller falls back to matching raw lines.
        """
        try:
            comment_lines: Set[int] = set()
            for tok in tokenize.generate_tokens(io.StringIO(content).readline):
                if tok.type == tokenize.COMMENT and tok.line[: tok.start[1]].strip() == "":
                    comment_lines.add(tok.start[0])
            return comment_lines
        except (tokenize.TokenError, SyntaxError):
            return None

    def list_symbols(self, file_path: Path) -> List[dict]:
        """List all extractable symbols in a Python file."""
        source = file_path.read_text()
        tree = ast.parse(source, filename=str(file_path))
        symbols: List[dict] = []

        self._collect_symbols(tree, symbols, prefix="")

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

    # --- Internal helpers ---

    def _find_by_dotted_path(
        self, tree: ast.AST, dotted_name: str, target_types: tuple
    ) -> Optional[ast.stmt]:
        """
        Find a node by dotted path like 'MyClass.my_method'.

        Walks into containers (classes, functions) following the path segments,
        then matches the final segment against target_types.
        """
        parts = dotted_name.split(".")

        if len(parts) == 1:
            # Simple name — search top-level
            return self._find_direct_child(tree, parts[0], target_types)

        # Walk the path: each segment except the last is a container
        current: ast.AST = tree
        for segment in parts[:-1]:
            child = self._find_direct_child(
                current, segment, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
            )
            if not child:
                return None
            current = child

        # Find the final target in the container
        return self._find_direct_child(current, parts[-1], target_types)

    def _find_direct_child(
        self, parent: ast.AST, name: str, target_types: tuple
    ) -> Optional[ast.stmt]:
        """Find a direct child node by name and type."""
        for node in ast.iter_child_nodes(parent):
            if isinstance(node, target_types) and hasattr(node, "name") and node.name == name:
                return node
        return None

    def _get_assignment_name(self, node: ast.AST) -> Optional[str]:
        """Get the target name from an assignment node, if it's a simple name."""
        if isinstance(node, ast.Assign):
            if len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
                return node.targets[0].id
        elif isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name):
                return node.target.id
        return None

    def _extract_node_text(self, source: str, node: ast.stmt) -> Tuple[str, int, int]:
        """Extract source text for an AST node, including decorators."""
        lines = source.splitlines()

        # Start line: use decorator_list if present (decorators come before the def)
        if hasattr(node, "decorator_list") and node.decorator_list:
            start_line = node.decorator_list[0].lineno
        else:
            start_line = node.lineno

        end_line = node.end_lineno
        if end_line is None:
            # Fallback for very old Python (shouldn't happen with 3.10+)
            end_line = start_line

        code_lines = lines[start_line - 1 : end_line]
        text = "\n".join(code_lines)

        return text, start_line, end_line

    def _collect_symbols(self, node: ast.AST, symbols: List[dict], prefix: str) -> None:
        """Recursively collect symbols from AST nodes."""
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                name = f"{prefix}{child.name}" if not prefix else f"{prefix}.{child.name}"
                kind = "async function" if isinstance(child, ast.AsyncFunctionDef) else "function"

                # Build signature
                sig = self._build_signature(child)

                start_line = child.lineno
                if child.decorator_list:
                    start_line = child.decorator_list[0].lineno

                symbols.append({
                    "name": name,
                    "kind": kind,
                    "param": "function",
                    "line": start_line,
                    "signature": sig,
                })

                # Recurse into function body for nested functions/classes
                inner_prefix = name
                self._collect_symbols(child, symbols, inner_prefix)

            elif isinstance(child, ast.ClassDef):
                name = f"{prefix}{child.name}" if not prefix else f"{prefix}.{child.name}"

                start_line = child.lineno
                if child.decorator_list:
                    start_line = child.decorator_list[0].lineno

                symbols.append({
                    "name": name,
                    "kind": "class",
                    "param": "struct",
                    "line": start_line,
                })

                # Recurse into class body for methods and nested classes
                self._collect_symbols(child, symbols, name)

            elif isinstance(child, (ast.Assign, ast.AnnAssign)):
                var_name = self._get_assignment_name(child)
                if var_name and not prefix:
                    # Only collect module-level variables
                    symbols.append({
                        "name": var_name,
                        "kind": "variable",
                        "param": "var",
                        "line": child.lineno,
                    })

    def _build_signature(self, func_node: "ast.FunctionDef | ast.AsyncFunctionDef") -> str:
        """Build a function signature string from AST."""
        args = func_node.args
        parts = []

        # Positional-only args (before the '/' separator)
        for arg in args.posonlyargs:
            name = arg.arg
            if arg.annotation:
                name += f": {ast.unparse(arg.annotation)}"
            parts.append(name)
        if args.posonlyargs:
            parts.append("/")

        # Regular args
        for arg in args.args:
            name = arg.arg
            if arg.annotation:
                name += f": {ast.unparse(arg.annotation)}"
            parts.append(name)

        # *args
        if args.vararg:
            name = f"*{args.vararg.arg}"
            if args.vararg.annotation:
                name += f": {ast.unparse(args.vararg.annotation)}"
            parts.append(name)
        elif args.kwonlyargs:
            # bare * separator for keyword-only args without *args
            parts.append("*")

        # keyword-only args
        for arg in args.kwonlyargs:
            name = arg.arg
            if arg.annotation:
                name += f": {ast.unparse(arg.annotation)}"
            parts.append(name)

        # **kwargs
        if args.kwarg:
            name = f"**{args.kwarg.arg}"
            if args.kwarg.annotation:
                name += f": {ast.unparse(args.kwarg.annotation)}"
            parts.append(name)

        sig = f"({', '.join(parts)})"

        # Return annotation
        if func_node.returns:
            sig += f" -> {ast.unparse(func_node.returns)}"

        return sig
