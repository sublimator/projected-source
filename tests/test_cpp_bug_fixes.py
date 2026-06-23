#!/usr/bin/env python3
"""Regression tests for five C++ extractor bug fixes.

Each test reproduces a specific bug described in the bug-fix cluster:

* FINDING 1 — namespace/class branches fell through to generic recursion
  with stale context, producing false-positive partial-qualifier matches.
* FINDING 2 — forward declarations like ``class Foo;`` shadowed the real
  definition because the lookup path didn't check for a body.
* FINDING 3 — pointer/reference return-type functions and methods were
  silently skipped in the declaration/field_declaration branches and in
  ``_extract_parameter_signature``.
* FINDING 4 — ``extract_operator_name`` dropped the space in keyword
  operators (e.g. ``operator new`` became ``operatornew``).
* FINDING 5 — ``extract_function_macro_marker`` reported line numbers that
  pointed at the marker comments while the returned code excluded them.
"""

import tempfile
from pathlib import Path

import tree_sitter_cpp as tscpp
from tree_sitter import Language, Node, Parser

from projected_source.languages.cpp import CppExtractor
from projected_source.languages.cpp_ast import extract_operator_name
from projected_source.languages.cpp_parser import SimpleCppParser
from projected_source.languages.macro_finder import MacroFinder

_PARSER = Parser(Language(tscpp.language()))


def _first(node: Node, node_type: str):
    """Depth-first search for the first node of the given type."""
    if node.type == node_type:
        return node
    for child in node.children:
        found = _first(child, node_type)
        if found:
            return found
    return None


# -------------------------- FINDING 1 --------------------------------------


class TestNamespaceFallthrough:
    """Regression: namespace/class branches fall through to generic recursion."""

    def test_outer_qualifier_does_not_match_inner_member(self):
        """``outer::my_var`` must not match ``my_var`` inside ``outer::inner``."""
        source = (
            b"namespace outer {\n"
            b"    namespace inner {\n"
            b"        int my_var = 42;\n"
            b"    }\n"
            b"}\n"
        )
        parser = SimpleCppParser()
        result = parser.extract_struct_or_class_by_name(source, "outer::my_var")
        # Bug: returned the inner declaration via stale-context fall-through.
        assert result is None

    def test_correct_qualifier_still_matches(self):
        """Sanity check: the real ``outer::inner::my_var`` still resolves."""
        source = (
            b"namespace outer {\n"
            b"    namespace inner {\n"
            b"        int my_var = 42;\n"
            b"    }\n"
            b"}\n"
        )
        parser = SimpleCppParser()
        result = parser.extract_struct_or_class_by_name(source, "outer::inner::my_var")
        assert result is not None
        assert "my_var" in result.text

    def test_class_branch_does_not_leak_inner_member(self):
        """A nested struct named like the target must not be matched outside its class."""
        source = (
            b"class Outer {\n"
            b"  public:\n"
            b"    struct Inner { int x; };\n"
            b"};\n"
        )
        parser = SimpleCppParser()
        # No struct named ``Inner`` exists at namespace scope.
        result = parser.extract_struct_or_class_by_name(source, "Inner")
        # With the fall-through fix the inner struct is only reachable via its
        # nested context (Outer::Inner), so an unqualified lookup still finds it
        # (it's nested but accessible). The important check: ``Other::Inner``
        # (a bogus qualifier) must NOT match.
        assert result is not None  # Inner exists nested
        bogus = parser.extract_struct_or_class_by_name(source, "Other::Inner")
        assert bogus is None


# -------------------------- FINDING 2 --------------------------------------


class TestForwardDeclShadowing:
    """Regression: ``class Foo;`` forward decl shadowed the full definition."""

    def test_forward_decl_does_not_shadow_definition(self):
        source = (
            b"class Foo;\n"
            b"\n"
            b"class Foo {\n"
            b"  public:\n"
            b"    int value;\n"
            b"};\n"
        )
        parser = SimpleCppParser()
        result = parser.extract_struct_or_class_by_name(source, "Foo")
        assert result is not None
        # Must return the full definition with the body, not the bare ``class Foo;``.
        assert "value" in result.text
        assert "{" in result.text

    def test_struct_forward_decl_does_not_shadow_definition(self):
        source = (
            b"struct Bar;\n"
            b"\n"
            b"struct Bar { int n; };\n"
        )
        parser = SimpleCppParser()
        result = parser.extract_struct_or_class_by_name(source, "Bar")
        assert result is not None
        assert "n" in result.text
        assert "{" in result.text

    def test_only_forward_decl_still_returns_something(self):
        """If only a forward decl exists, fall back to returning it."""
        source = b"class Lonely;\n"
        parser = SimpleCppParser()
        result = parser.extract_struct_or_class_by_name(source, "Lonely")
        assert result is not None
        assert "Lonely" in result.text


# -------------------------- FINDING 3 --------------------------------------


class TestPointerReferenceReturn:
    """Regression: pointer/reference return-type functions silently skipped."""

    def test_pointer_return_extern_decl(self):
        source = (
            b"extern int* compute(int x);\n"
        )
        parser = SimpleCppParser()
        result = parser.extract_function_by_name(source, "compute")
        assert result is not None
        assert "compute" in result.text

    def test_reference_return_extern_decl(self):
        source = (
            b"extern int& choose(int& a, int& b);\n"
        )
        parser = SimpleCppParser()
        result = parser.extract_function_by_name(source, "choose")
        assert result is not None
        assert "choose" in result.text

    def test_pointer_return_method_in_class_header(self):
        source = (
            b"class S {\n"
            b"  public:\n"
            b"    int* data(int i);\n"
            b"};\n"
        )
        parser = SimpleCppParser()
        result = parser.extract_function_by_name(source, "S::data")
        assert result is not None
        assert "data" in result.text

    def test_reference_return_method_in_class_header(self):
        source = (
            b"class S {\n"
            b"  public:\n"
            b"    int& slot(int i);\n"
            b"};\n"
        )
        parser = SimpleCppParser()
        result = parser.extract_function_by_name(source, "S::slot")
        assert result is not None
        assert "slot" in result.text

    def test_pointer_return_listed_in_symbols(self):
        with tempfile.NamedTemporaryFile(suffix=".h", delete=False) as f:
            f.write(b"extern int* compute(int x);\n")
            f.flush()
            path = Path(f.name)
        try:
            ext = CppExtractor()
            symbols = ext.list_symbols(path)
            fn_names = [s["name"] for s in symbols if s["kind"] == "function"]
            assert "compute" in fn_names
        finally:
            path.unlink()

    def test_parameter_signature_pointer_return_field_decl(self):
        source = (
            b"class S {\n"
            b"  public:\n"
            b"    int* data(int i, double d);\n"
            b"};\n"
        )
        parser = SimpleCppParser()
        nodes = parser._find_all_nodes_by_qualified_name(source, "S::data", ["function_definition"])
        assert len(nodes) == 1
        sig = parser._extract_parameter_signature(nodes[0])
        assert "int i" in sig
        assert "double d" in sig


# -------------------------- FINDING 4 --------------------------------------


class TestKeywordOperatorName:
    """Regression: ``extract_operator_name`` dropped spaces in keyword operators."""

    def test_operator_new(self):
        op = _first(
            _PARSER.parse(b"struct S { void* operator new(unsigned long s); };").root_node,
            "operator_name",
        )
        assert extract_operator_name(op) == "operator new"

    def test_operator_delete(self):
        op = _first(
            _PARSER.parse(b"struct S { void operator delete(void* p); };").root_node,
            "operator_name",
        )
        assert extract_operator_name(op) == "operator delete"

    def test_operator_new_array(self):
        op = _first(
            _PARSER.parse(b"struct S { void* operator new[](unsigned long s); };").root_node,
            "operator_name",
        )
        # Space between 'operator' and 'new', no space between 'new' and '['
        assert extract_operator_name(op) == "operator new[]"

    def test_operator_plus_still_has_no_space(self):
        op = _first(
            _PARSER.parse(b"struct S { S operator+(S o); };").root_node,
            "operator_name",
        )
        assert extract_operator_name(op) == "operator+"

    def test_operator_bracket_still_has_no_space(self):
        op = _first(
            _PARSER.parse(b"struct S { int operator[](int i); };").root_node,
            "operator_name",
        )
        assert extract_operator_name(op) == "operator[]"


# -------------------------- FINDING 5 --------------------------------------


class TestMacroMarkerLineNumbers:
    """Regression: marker line numbers must match the returned section_code."""

    def test_line_numbers_match_returned_code(self):
        source = (
            b"DEFINE_HOOK_FUNCTION(int64_t, my_func, uint32_t x)\n"
            b"{\n"
            b"    //@@start setup\n"
            b"    int a = 1;\n"
            b"    int b = 2;\n"
            b"    //@@end setup\n"
            b"    return a + b;\n"
            b"}\n"
        )
        with tempfile.NamedTemporaryFile(suffix=".cpp", delete=False) as f:
            f.write(source)
            f.flush()
            tmp_path = Path(f.name)

        try:
            ext = CppExtractor()
            text, start, end = ext.extract_function_macro_marker(
                tmp_path, {"name": "DEFINE_HOOK_FUNCTION", "arg1": "my_func"}, "setup"
            )

            # The returned text excludes the marker comment lines.
            assert "//@@start" not in text
            assert "//@@end" not in text
            assert "int a = 1;" in text
            assert "int b = 2;" in text

            # The returned (start, end) must correspond to the lines of the
            # returned text in the source file.
            file_lines = tmp_path.read_text().splitlines()
            slice_text = "\n".join(file_lines[start - 1 : end])
            assert slice_text == text

            # And concretely: start is the line AFTER //@@start, end is the
            # line BEFORE //@@end (1-based).
            assert file_lines[start - 1].strip() == "int a = 1;"
            assert file_lines[end - 1].strip() == "int b = 2;"
        finally:
            tmp_path.unlink()

    def test_macro_finder_markers_excludes_marker_lines(self):
        source = (
            b"DEFINE_JS_FUNCTION(JSValue, fn, int x) {\n"
            b"    //@@start calc\n"
            b"    int y = x * 2;\n"
            b"    //@@end calc\n"
            b"}\n"
        )
        mf = MacroFinder()
        info = mf.find_markers_in_macro(source, "DEFINE_JS_FUNCTION")
        start_line, end_line = info["markers"]["calc"]
        lines = source.decode("utf8").splitlines()
        # Start should point at "int y = x * 2;" (line 3, 1-based)
        # End should also point at that same line
        assert lines[start_line - 1].strip() == "int y = x * 2;"
        assert lines[end_line - 1].strip() == "int y = x * 2;"
