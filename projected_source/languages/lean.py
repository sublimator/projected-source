"""Lean 4 code extraction using tree-sitter.

Uses the Julian/tree-sitter-lean grammar (Lean 4). Because upstream's
hatchling build does not compile the C extension that ships in its source
tree, the grammar is vendored under ``lean_grammar/`` (pinned to rev
``30f05c80e``) and built via ``hatch_build.py`` at install time.

Mapping summary
---------------
- ``function=`` → ``def`` | ``theorem`` | ``example`` | ``abbrev`` | ``instance``
  (the grammar treats ``lemma`` as a ``theorem`` variant and ``class`` as a
  ``structure`` variant, so they're covered without aliases)
- ``struct=`` → ``structure`` | ``inductive``
- ``var=`` → ``constant`` | ``axiom`` | ``opaque`` | ``initialize`` | ``builtin_initialize``
  (``variable`` is a scoping binder, not a value, so it's intentionally not
  exposed as ``var=``)
- ``marker=`` → Lean-comment markers ``-- @@start name`` / ``-- @@end name``

Namespace handling
------------------
In this grammar ``namespace Foo`` / ``end Foo`` are *siblings* of the
declarations between them, not parents. The extractor walks top-level
children sequentially and maintains a scope stack to build qualified names
like ``Foo.Bar.baz``.

Identifier handling
-------------------
Lean identifiers can themselves contain dots: ``def ExportGate.proceed``
declares a single function whose ``name`` field text is ``ExportGate.proceed``.
We do **not** split on dots (Rust-style). Lookups match the full qualified
name, then fall back to bare-name and suffix-of-qualified-name matches.

Modifier handling
-----------------
Attributes like ``@[simp]``, visibility (``private``, ``protected``,
``public``), and modifiers (``noncomputable``, ``partial``, ``unsafe``) live
on the wrapping ``declaration`` node, not the inner ``def``/``theorem``.
Extracted ranges always come from the outer ``declaration`` node so these
prefixes are preserved.
"""

from __future__ import annotations

import logging
import re
import textwrap
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from tree_sitter import Language, Node, Parser

from ..core.extractor import BaseExtractor
from .lean_grammar._binding import language as _lean_language
from .utils import node_text

logger = logging.getLogger(__name__)

# Inner-node kinds we expose, grouped by the code() kwarg they answer.
FUNCTION_KINDS: Tuple[str, ...] = ("def", "theorem", "example", "abbrev", "instance")
STRUCTURE_KINDS: Tuple[str, ...] = ("structure",)
INDUCTIVE_KINDS: Tuple[str, ...] = ("inductive",)
VARIABLE_KINDS: Tuple[str, ...] = (
    "constant",
    "axiom",
    "opaque",
    "initialize",
    "builtin_initialize",
)
_ALL_DEFINITION_KINDS: Tuple[str, ...] = (
    *FUNCTION_KINDS,
    *STRUCTURE_KINDS,
    *INDUCTIVE_KINDS,
    *VARIABLE_KINDS,
)

_KIND_TO_PARAM = {
    **{k: "function" for k in FUNCTION_KINDS},
    **{k: "struct" for k in STRUCTURE_KINDS},
    **{k: "struct" for k in INDUCTIVE_KINDS},
    **{k: "var" for k in VARIABLE_KINDS},
}


class LeanExtractor(BaseExtractor):
    """Lean 4 extractor — definitions, structures, inductives, instances."""

    def __init__(self) -> None:
        self._language = Language(_lean_language())
        super().__init__(self._language)
        self._parser = Parser(self._language)

    # --- public extraction API -------------------------------------------------

    def extract_function(
        self, file_path: Path, function_name: str, signature: Optional[str] = None
    ) -> Tuple[str, int, int]:
        """Extract a ``def`` / ``theorem`` / ``example`` / ``abbrev`` / ``instance`` by name."""
        return self._extract_named(file_path, function_name, FUNCTION_KINDS)

    def extract_function_marker(
        self, file_path: Path, function_name: str, marker: str
    ) -> Tuple[str, int, int]:
        """Extract a marker region inside a specific function definition."""
        source = file_path.read_bytes()
        tree = self._parser.parse(source)
        match = self._find(tree.root_node, function_name, FUNCTION_KINDS)
        if not match:
            raise ValueError(f"Function '{function_name}' not found in {file_path}")
        return _extract_marker_in_node(source, match[0], marker)

    def extract_struct(self, file_path: Path, name: str) -> Tuple[str, int, int]:
        """Extract a ``structure`` (incl. ``class``) or ``inductive`` by name."""
        return self._extract_named(file_path, name, STRUCTURE_KINDS + INDUCTIVE_KINDS)

    def extract_variable(self, file_path: Path, var_name: str) -> Tuple[str, int, int]:
        """Extract a ``constant`` / ``axiom`` / ``opaque`` / ``initialize`` by name."""
        return self._extract_named(file_path, var_name, VARIABLE_KINDS)

    def extract_marker(self, file_path: Path, marker_name: str) -> Tuple[str, int, int]:
        """Extract content between ``-- @@start name`` and ``-- @@end name`` comments."""
        content = file_path.read_text()
        return _extract_marker_in_text(content, marker_name)

    def list_symbols(self, file_path: Path) -> List[Dict]:
        """List every top-level definition with its qualified name."""
        source = file_path.read_bytes()
        tree = self._parser.parse(source)
        symbols: List[Dict] = []
        for _decl, inner, qualified in self._walk_declarations(tree.root_node):
            symbols.append(
                {
                    "name": qualified,
                    "kind": inner.type,
                    "param": _KIND_TO_PARAM.get(inner.type, "function"),
                    "line": _outer_decl_for(inner).start_point.row + 1,
                }
            )
        return symbols

    # --- internals -------------------------------------------------------------

    def _extract_named(
        self, file_path: Path, target: str, kinds: Tuple[str, ...]
    ) -> Tuple[str, int, int]:
        source = file_path.read_bytes()
        tree = self._parser.parse(source)
        match = self._find(tree.root_node, target, kinds)
        if not match:
            raise ValueError(f"Lean {kinds} '{target}' not found in {file_path}")
        decl_node, _qualified = match
        return _slice_dedented(source, decl_node)

    def _find(self, root: Node, target: str, kinds: Tuple[str, ...]) -> Optional[Tuple[Node, str]]:
        """Find the declaration whose inner kind matches and whose qualified name matches ``target``."""
        for decl, inner, qualified in self._walk_declarations(root):
            if inner.type not in kinds:
                continue
            name = _name_text(inner)
            if name is None:
                continue
            if qualified == target or name == target or qualified.endswith("." + target):
                return decl, qualified
        return None

    def _walk_declarations(self, root: Node):
        """Yield ``(declaration_node, inner_node, qualified_name)`` triples.

        Maintains a scope stack across sibling ``namespace`` / ``section`` / ``end``
        nodes so qualified names reflect lexical nesting.

        The vendored grammar does not recognize ``mutual`` blocks — they appear
        as a top-level ``ERROR`` node containing just the keyword ``mutual``,
        followed by the mutual's declarations as siblings, then a bare ``end``.
        We track those pending mutual-ends and swallow them so the mutual's
        closing ``end`` doesn't get mistaken for a ``namespace`` / ``section``
        terminator and prematurely pop the scope stack.
        """
        scope: List[str] = []
        pending_mutual_ends = 0
        for child in root.children:
            ctype = child.type
            if ctype == "namespace":
                scope.append(_name_text(child) or "")
            elif ctype == "section":
                # sections may be anonymous; push a placeholder either way so end pops cleanly
                scope.append(_name_text(child) or "")
            elif ctype == "ERROR" and _is_mutual_marker(child):
                pending_mutual_ends += 1
            elif ctype == "end":
                if pending_mutual_ends > 0 and _is_bare_end(child):
                    pending_mutual_ends -= 1
                elif scope:
                    scope.pop()
            elif ctype == "declaration":
                inner = _declaration_inner(child)
                if inner is None:
                    continue
                name = _name_text(inner)
                if name is None:
                    continue
                qualified = ".".join([s for s in scope if s] + [name]) if scope else name
                yield child, inner, qualified


# --- module-level helpers ------------------------------------------------------


_MUTUAL_MARKER = re.compile(r"^\s*mutual\b")


def _is_mutual_marker(node: Node) -> bool:
    """True if an ``ERROR`` node represents an unrecognized ``mutual`` keyword.

    The vendored grammar doesn't know about Lean's ``mutual`` blocks, so the
    keyword shows up as a top-level ``ERROR`` whose text starts with ``mutual``.
    """
    text = node.text.decode("utf-8", errors="replace") if node.text else ""
    return bool(_MUTUAL_MARKER.match(text))


def _is_bare_end(node: Node) -> bool:
    """True if an ``end`` node has no trailing identifier (i.e. ``end`` not ``end Foo``)."""
    for child in node.children:
        if child.type == "identifier":
            return False
    return True


def _declaration_inner(decl: Node) -> Optional[Node]:
    """The first child of a ``declaration`` whose type is a Lean definition kind."""
    for child in decl.children:
        if child.type in _ALL_DEFINITION_KINDS:
            return child
    return None


def _outer_decl_for(inner: Node) -> Node:
    """Walk up to the wrapping ``declaration`` node, or return the node itself."""
    cur: Optional[Node] = inner.parent
    while cur is not None:
        if cur.type == "declaration":
            return cur
        cur = cur.parent
    return inner


def _name_text(node: Node) -> Optional[str]:
    name = node.child_by_field_name("name")
    return node_text(name) if name else None


def _slice_dedented(source: bytes, node: Node) -> Tuple[str, int, int]:
    snippet = source[node.start_byte : node.end_byte].decode("utf-8", errors="replace")
    return textwrap.dedent(snippet), node.start_point.row + 1, node.end_point.row + 1


_MARKER_START = re.compile(r"--\s*@@start\s+(\S+)")
_MARKER_END = re.compile(r"--\s*@@end\s+(\S+)")


def _extract_marker_in_text(content: str, marker_name: str) -> Tuple[str, int, int]:
    lines = content.splitlines()
    start_idx = end_idx = None
    for idx, line in enumerate(lines):
        if start_idx is None:
            m = _MARKER_START.search(line)
            if m and m.group(1) == marker_name:
                start_idx = idx
                continue
        else:
            m = _MARKER_END.search(line)
            if m and m.group(1) == marker_name:
                end_idx = idx
                break
    if start_idx is None or end_idx is None:
        raise ValueError(f"Marker '{marker_name}' not found")
    body = lines[start_idx + 1 : end_idx]
    return textwrap.dedent("\n".join(body)), start_idx + 2, end_idx


def _extract_marker_in_node(source: bytes, node: Node, marker_name: str) -> Tuple[str, int, int]:
    snippet = source[node.start_byte : node.end_byte].decode("utf-8", errors="replace")
    text, rel_start, rel_end = _extract_marker_in_text(snippet, marker_name)
    base = node.start_point.row + 1
    return text, base + rel_start - 1, base + rel_end - 1
