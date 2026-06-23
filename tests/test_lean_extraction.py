"""Tests for the Lean 4 extractor.

The grammar is a static parser for Lean 4 — it cannot model Lean's dynamic
macro/notation system, so some advanced syntax will produce parse errors.
These tests stick to features the static grammar handles.
"""

from pathlib import Path

import pytest

from projected_source.languages.lean import LeanExtractor

FIXTURE = Path(__file__).parent / "fixtures" / "sample.lean"


@pytest.fixture
def extractor() -> LeanExtractor:
    return LeanExtractor()


class TestParsing:
    def test_grammar_loads_and_parses_fixture(self, extractor):
        source = FIXTURE.read_bytes()
        tree = extractor._parser.parse(source)
        assert tree.root_node.type == "module"


class TestListSymbols:
    def test_namespace_qualified_names(self, extractor):
        names = {s["name"] for s in extractor.list_symbols(FIXTURE)}
        # Items inside `namespace SampleNs` get the prefix.
        assert "SampleNs.greet" in names
        assert "SampleNs.add_zero" in names
        assert "SampleNs.Point" in names
        assert "SampleNs.Color" in names
        assert "SampleNs.Age" in names
        assert "SampleNs.natHasZero" in names

    def test_anonymous_section_does_not_prefix(self, extractor):
        names = {s["name"] for s in extractor.list_symbols(FIXTURE)}
        assert "topLevel" in names

    def test_nested_namespaces_concatenate(self, extractor):
        names = {s["name"] for s in extractor.list_symbols(FIXTURE)}
        assert "Outer.Inner.deeplyNested" in names

    def test_each_symbol_has_expected_param_kwarg(self, extractor):
        by_name = {s["name"]: s for s in extractor.list_symbols(FIXTURE)}
        assert by_name["SampleNs.greet"]["param"] == "function"
        assert by_name["SampleNs.add_zero"]["param"] == "function"
        assert by_name["SampleNs.Point"]["param"] == "struct"
        assert by_name["SampleNs.Color"]["param"] == "struct"
        assert by_name["SampleNs.truth"]["param"] == "var"
        assert by_name["SampleNs.secret"]["param"] == "var"


class TestExtractFunction:
    def test_by_bare_name(self, extractor):
        text, _, _ = extractor.extract_function(FIXTURE, "greet")
        assert text.startswith("def greet")

    def test_by_qualified_name(self, extractor):
        text, _, _ = extractor.extract_function(FIXTURE, "SampleNs.greet")
        assert text.startswith("def greet")

    def test_attribute_is_included_in_extraction(self, extractor):
        # The wrapping `declaration` node carries the @[simp] attribute —
        # extraction must use that outer range so the attribute is preserved.
        text, _, _ = extractor.extract_function(FIXTURE, "add_zero")
        assert "@[simp]" in text
        assert "theorem add_zero" in text

    def test_instance(self, extractor):
        text, _, _ = extractor.extract_function(FIXTURE, "natHasZero")
        assert text.startswith("instance natHasZero")

    def test_abbrev(self, extractor):
        text, _, _ = extractor.extract_function(FIXTURE, "Age")
        assert text.startswith("abbrev Age")

    def test_dotted_identifier_is_one_name(self, extractor):
        # `def Point.origin` is a single dotted identifier in Lean — not split.
        text, _, _ = extractor.extract_function(FIXTURE, "Point.origin")
        assert "Point.origin" in text

    def test_not_found_raises(self, extractor):
        with pytest.raises(ValueError, match="doesNotExist"):
            extractor.extract_function(FIXTURE, "doesNotExist")


class TestExtractStruct:
    def test_structure(self, extractor):
        text, _, _ = extractor.extract_struct(FIXTURE, "Point")
        assert text.startswith("structure Point")

    def test_inductive(self, extractor):
        text, _, _ = extractor.extract_struct(FIXTURE, "Color")
        assert text.startswith("inductive Color")

    def test_class_is_structure_variant(self, extractor):
        # `class Foo` parses as a `structure` node in this grammar.
        text, _, _ = extractor.extract_struct(FIXTURE, "HasZero")
        assert text.startswith("class HasZero")


class TestExtractVariable:
    def test_axiom(self, extractor):
        text, _, _ = extractor.extract_variable(FIXTURE, "truth")
        assert text.startswith("axiom truth")

    def test_opaque(self, extractor):
        text, _, _ = extractor.extract_variable(FIXTURE, "secret")
        assert text.startswith("opaque secret")


class TestMarkers:
    def test_extract_marker_block(self, extractor):
        text, _, _ = extractor.extract_marker(FIXTURE, "example-block")
        assert "def withMarker" in text
        # Sentinel comments themselves are excluded.
        assert "@@start" not in text
        assert "@@end" not in text


class TestNamespaceWalk:
    def test_extract_via_fully_qualified_name(self, extractor):
        text, _, _ = extractor.extract_function(FIXTURE, "Outer.Inner.deeplyNested")
        assert "deeplyNested" in text

    def test_suffix_match_finds_inside_namespace(self, extractor):
        # Caller writes `Inner.deeplyNested`; should match
        # `Outer.Inner.deeplyNested` by suffix.
        text, _, _ = extractor.extract_function(FIXTURE, "Inner.deeplyNested")
        assert "deeplyNested" in text


class TestMutualBlock:
    """The vendored grammar doesn't recognize ``mutual ... end`` blocks — they
    appear as a top-level ERROR + bare ``end`` sibling pair. Without special
    handling, the mutual's closing ``end`` would pop the enclosing namespace
    scope, so declarations inside *and after* the mutual would lose their
    namespace prefix.
    """

    def test_mutual_members_keep_namespace_prefix(self, extractor):
        names = {s["name"] for s in extractor.list_symbols(FIXTURE)}
        assert "MutualNs.evenN" in names
        assert "MutualNs.oddN" in names

    def test_post_mutual_decl_keeps_namespace_prefix(self, extractor):
        names = {s["name"] for s in extractor.list_symbols(FIXTURE)}
        assert "MutualNs.afterMutual" in names

    def test_mutual_member_extractable_by_qualified_name(self, extractor):
        text, _, _ = extractor.extract_function(FIXTURE, "MutualNs.evenN")
        assert "def evenN" in text

    def test_post_mutual_decl_extractable_by_qualified_name(self, extractor):
        text, _, _ = extractor.extract_function(FIXTURE, "MutualNs.afterMutual")
        assert "def afterMutual" in text
