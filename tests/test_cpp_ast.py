"""Unit tests for the pure C++ AST helpers in cpp_ast.py.

These functions were extracted from cpp_parser.py; the wider C++ suite covers
them indirectly, but testing the module boundary directly keeps the pure
helpers honest.
"""

import tree_sitter_cpp as tscpp
from tree_sitter import Language, Node, Parser

from projected_source.languages.cpp_ast import (
    extract_function_name_and_qualifiers,
    extract_operator_name,
    extract_qualified_parts,
    extract_template_type_name,
    find_following_body,
    node_to_result,
    qualifier_base,
    qualifiers_match,
)

_PARSER = Parser(Language(tscpp.language()))


def _parse(code: str) -> Node:
    return _PARSER.parse(code.encode("utf8")).root_node


def _first(node: Node, node_type: str):
    """Depth-first search for the first node of the given type."""
    if node.type == node_type:
        return node
    for child in node.children:
        found = _first(child, node_type)
        if found:
            return found
    return None


class TestQualifierBase:
    def test_strips_template_args(self):
        assert qualifier_base("Container<T>") == "Container"

    def test_passes_through_plain_name(self):
        assert qualifier_base("MyClass") == "MyClass"

    def test_strips_multi_arg_template(self):
        assert qualifier_base("Map<K, V>") == "Map"


class TestQualifiersMatch:
    def test_empty_target_matches_anything(self):
        assert qualifiers_match(["ns", "Class"], []) is True

    def test_exact_match(self):
        assert qualifiers_match(["ns", "Class"], ["ns", "Class"]) is True

    def test_suffix_match(self):
        assert qualifiers_match(["outer", "inner", "Class"], ["inner", "Class"]) is True

    def test_template_args_stripped_when_comparing(self):
        assert qualifiers_match(["Container<int>"], ["Container"]) is True

    def test_non_match(self):
        assert qualifiers_match(["Foo"], ["Bar"]) is False

    def test_target_longer_than_found(self):
        assert qualifiers_match(["Class"], ["ns", "Class"]) is False


class TestNameExtraction:
    def test_operator_name(self):
        op = _first(_parse("struct S { S operator+(S o); };"), "operator_name")
        assert extract_operator_name(op) == "operator+"

    def test_qualified_parts(self):
        qid = _first(_parse("void Outer::Inner::method() {}"), "qualified_identifier")
        assert extract_qualified_parts(qid) == ["Outer", "Inner", "method"]

    def test_template_type_name(self):
        tt = _first(_parse("Container<int> x;"), "template_type")
        assert extract_template_type_name(tt) == "Container<int>"

    def test_function_name_and_qualifiers_plain(self):
        fn = _first(_parse("void freeFn() {}"), "function_definition")
        name, quals = extract_function_name_and_qualifiers(fn.child_by_field_name("declarator"), ["ns"])
        assert name == "freeFn"
        assert quals == ["ns"]

    def test_function_name_and_qualifiers_qualified(self):
        fn = _first(_parse("void MyClass::method() {}"), "function_definition")
        name, quals = extract_function_name_and_qualifiers(fn.child_by_field_name("declarator"), [])
        assert name == "method"
        assert quals == ["MyClass"]

    def test_function_name_and_qualifiers_destructor(self):
        fn = _first(_parse("struct Widget { ~Widget() {} };"), "function_definition")
        name, quals = extract_function_name_and_qualifiers(fn.child_by_field_name("declarator"), ["Widget"])
        assert name == "~Widget"
        assert quals == ["Widget"]


class TestFindFollowingBody:
    def test_returns_none_for_plain_declaration(self):
        decl = _first(_parse("int x;"), "declaration")
        assert find_following_body(decl) is None


class TestNodeToResult:
    def test_carries_position_text_and_metadata(self):
        decl = _first(_parse("int x = 1;"), "declaration")
        result = node_to_result(decl, "x")
        assert result.qualified_name == "x"
        assert result.start_line == 1
        assert result.node_type == "declaration"
        assert "int x" in result.text
