#!/usr/bin/env python3
"""
Test suite for list_symbols functionality across extractors.
"""

from pathlib import Path

import pytest

from projected_source.languages.cpp import CppExtractor
from projected_source.languages.cpp_parser import SimpleCppParser
from projected_source.languages.proto import ProtoExtractor


class TestCppParserListSymbols:
    """Test SimpleCppParser.list_symbols()."""

    @pytest.fixture
    def parser(self):
        return SimpleCppParser()

    @pytest.fixture
    def complete_file(self):
        return Path("tests/fixtures/complete.cpp")

    @pytest.fixture
    def overloads_file(self):
        return Path("tests/fixtures/overloads.cpp")

    @pytest.fixture
    def header_file(self):
        return Path("tests/fixtures/class_methods.h")

    def test_finds_simple_function(self, parser, complete_file):
        """Test that simple top-level functions are found."""
        source = complete_file.read_bytes()
        symbols = parser.list_symbols(source)
        names = [s["name"] for s in symbols if s["param"] == "function"]

        assert "simpleFunction" in names

    def test_finds_class_methods(self, parser, complete_file):
        """Test that class methods are found with qualified names."""
        source = complete_file.read_bytes()
        symbols = parser.list_symbols(source)
        names = [s["name"] for s in symbols if s["param"] == "function"]

        assert "SimpleClass::method" in names
        assert "ClassWithMethods::simpleMethod" in names
        assert "ClassWithMethods::staticMethod" in names

    def test_finds_namespaced_functions(self, parser, complete_file):
        """Test that namespaced functions are found."""
        source = complete_file.read_bytes()
        symbols = parser.list_symbols(source)
        names = [s["name"] for s in symbols if s["param"] == "function"]

        assert "FunctionNamespace::namespacedFunction" in names
        assert "FunctionNamespace::namespacedFunctionWithMarker" in names

    def test_finds_namespaced_class_methods(self, parser, complete_file):
        """Test that methods in namespaced classes are found."""
        source = complete_file.read_bytes()
        symbols = parser.list_symbols(source)
        names = [s["name"] for s in symbols if s["param"] == "function"]

        assert "MyNamespace::NamespacedClass::getValue" in names

    def test_finds_structs_and_classes(self, parser, complete_file):
        """Test that structs and classes are found."""
        source = complete_file.read_bytes()
        symbols = parser.list_symbols(source)
        struct_symbols = [s for s in symbols if s["param"] == "struct"]
        names = [s["name"] for s in struct_symbols]

        assert "SimpleStruct" in names
        assert "SimpleClass" in names
        assert "OuterClass" in names

    def test_struct_vs_class_kind(self, parser, complete_file):
        """Test that kind correctly distinguishes struct from class."""
        source = complete_file.read_bytes()
        symbols = parser.list_symbols(source)

        simple_struct = next(s for s in symbols if s["name"] == "SimpleStruct")
        assert simple_struct["kind"] == "struct"

        simple_class = next(s for s in symbols if s["name"] == "SimpleClass")
        assert simple_class["kind"] == "class"

    def test_finds_enums(self, parser, complete_file):
        """Test that enums are found with param='struct'."""
        source = complete_file.read_bytes()
        symbols = parser.list_symbols(source)

        # MyNamespace::NamespacedClass contains an enum via the class_specifier
        # Look for any enum in the symbols
        enum_symbols = [s for s in symbols if s["kind"] == "enum"]
        # All C++ enums should use param='struct'
        for sym in enum_symbols:
            assert sym["param"] == "struct"

    def test_finds_namespaced_structs(self, parser, complete_file):
        """Test that namespaced structs are found."""
        source = complete_file.read_bytes()
        symbols = parser.list_symbols(source)
        names = [s["name"] for s in symbols if s["param"] == "struct"]

        assert "MyNamespace::NamespacedStruct" in names
        assert "MyNamespace::NamespacedClass" in names

    def test_finds_template_functions(self, parser, complete_file):
        """Test that template functions are found."""
        source = complete_file.read_bytes()
        symbols = parser.list_symbols(source)
        names = [s["name"] for s in symbols if s["param"] == "function"]

        assert "templateAdd" in names
        assert "templateMulti" in names

    def test_finds_operator_overloads(self, parser, complete_file):
        """Test that operator overloads are found."""
        source = complete_file.read_bytes()
        symbols = parser.list_symbols(source)
        names = [s["name"] for s in symbols if s["param"] == "function"]

        assert "Vector2D::operator+" in names
        assert "Vector2D::operator+=" in names
        assert "Vector2D::operator==" in names
        assert "Vector2D::operator[]" in names
        assert "operator*" in names

    def test_functions_have_signatures(self, parser, complete_file):
        """Test that functions include parameter signatures."""
        source = complete_file.read_bytes()
        symbols = parser.list_symbols(source)
        func_symbols = [s for s in symbols if s["param"] == "function"]

        # Every function symbol should have a 'signature' key
        for sym in func_symbols:
            assert "signature" in sym, f"Function {sym['name']} missing signature"

    def test_overloaded_functions_have_different_signatures(self, parser, overloads_file):
        """Test that overloaded functions report different signatures."""
        source = overloads_file.read_bytes()
        symbols = parser.list_symbols(source)

        on_message = [s for s in symbols if s["name"] == "PeerImp::onMessage"]
        assert len(on_message) == 4

        sigs = [s["signature"] for s in on_message]
        assert len(set(sigs)) == 4, "Each overload should have a unique signature"

    def test_finds_field_declarations(self, parser, header_file):
        """Test that class method declarations (field_declaration) are found."""
        source = header_file.read_bytes()
        symbols = parser.list_symbols(source)
        names = [s["name"] for s in symbols if s["param"] == "function"]

        assert "ripple::ShuffleService::addProposal" in names
        assert "ripple::ShuffleService::getProposals" in names
        assert "ripple::ShuffleService::reset" in names

    def test_symbols_have_line_numbers(self, parser, complete_file):
        """Test that all symbols have positive line numbers."""
        source = complete_file.read_bytes()
        symbols = parser.list_symbols(source)

        for sym in symbols:
            assert "line" in sym
            assert sym["line"] > 0, f"Symbol {sym['name']} has invalid line {sym['line']}"

    def test_all_symbols_have_required_fields(self, parser, complete_file):
        """Test that all symbols have name, kind, param, line."""
        source = complete_file.read_bytes()
        symbols = parser.list_symbols(source)

        for sym in symbols:
            assert "name" in sym, f"Missing 'name': {sym}"
            assert "kind" in sym, f"Missing 'kind': {sym}"
            assert "param" in sym, f"Missing 'param': {sym}"
            assert "line" in sym, f"Missing 'line': {sym}"

    def test_skips_forward_declarations(self, parser):
        """Test that forward declarations without bodies are skipped."""
        source = b"""
        class ForwardDeclared;
        struct AlsoForward;

        class HasBody {
        public:
            void method() {}
        };
        """
        symbols = parser.list_symbols(source)
        names = [s["name"] for s in symbols if s["param"] == "struct"]

        assert "ForwardDeclared" not in names
        assert "AlsoForward" not in names
        assert "HasBody" in names


class TestCppExtractorListSymbols:
    """Test CppExtractor.list_symbols() including markers."""

    @pytest.fixture
    def extractor(self):
        return CppExtractor()

    @pytest.fixture
    def complete_file(self):
        return Path("tests/fixtures/complete.cpp")

    def test_includes_markers(self, extractor, complete_file):
        """Test that markers are included in the symbol list."""
        symbols = extractor.list_symbols(complete_file)
        marker_symbols = [s for s in symbols if s["param"] == "marker"]

        assert len(marker_symbols) > 0
        marker_names = [s["name"] for s in marker_symbols]
        assert "saving-ledger" in marker_names

    def test_markers_have_end_line(self, extractor, complete_file):
        """Test that markers have end_line."""
        symbols = extractor.list_symbols(complete_file)
        marker_symbols = [s for s in symbols if s["param"] == "marker"]

        for sym in marker_symbols:
            assert "end_line" in sym
            assert sym["end_line"] >= sym["line"]

    def test_includes_both_functions_and_markers(self, extractor, complete_file):
        """Test that result includes both tree-sitter symbols and markers."""
        symbols = extractor.list_symbols(complete_file)
        params = {s["param"] for s in symbols}

        assert "function" in params
        assert "struct" in params
        assert "marker" in params

    def test_listed_functions_are_extractable(self, extractor, complete_file):
        """Test that listed function names actually work with extract_function."""
        symbols = extractor.list_symbols(complete_file)
        func_symbols = [s for s in symbols if s["param"] == "function"]

        # Test a sample of functions are actually extractable
        for sym in func_symbols[:5]:
            text, start, end = extractor.extract_function(complete_file, sym["name"])
            assert text, f"Failed to extract function '{sym['name']}'"

    def test_listed_structs_are_extractable(self, extractor, complete_file):
        """Test that listed struct names actually work with extract_struct."""
        symbols = extractor.list_symbols(complete_file)
        struct_symbols = [s for s in symbols if s["param"] == "struct"]

        for sym in struct_symbols[:5]:
            text, start, end = extractor.extract_struct(complete_file, sym["name"])
            assert text, f"Failed to extract struct '{sym['name']}'"


class TestProtoExtractorListSymbols:
    """Test ProtoExtractor.list_symbols()."""

    @pytest.fixture
    def extractor(self):
        return ProtoExtractor()

    @pytest.fixture
    def proto_file(self):
        return Path("tests/fixtures/ripple.proto")

    def test_finds_messages(self, extractor, proto_file):
        """Test that proto messages are found."""
        symbols = extractor.list_symbols(proto_file)
        messages = [s for s in symbols if s["param"] == "message"]

        assert len(messages) > 0
        names = [s["name"] for s in messages]
        assert "TMTransaction" in names
        assert "TMProposeSet" in names

    def test_finds_enums(self, extractor, proto_file):
        """Test that proto enums are found with param='enum'."""
        symbols = extractor.list_symbols(proto_file)
        enums = [s for s in symbols if s["param"] == "enum"]

        assert len(enums) > 0
        names = [s["name"] for s in enums]
        assert "MessageType" in names

    def test_message_param_is_message(self, extractor, proto_file):
        """Test that proto messages use param='message' (not 'struct')."""
        symbols = extractor.list_symbols(proto_file)
        messages = [s for s in symbols if s["kind"] == "message"]

        for sym in messages:
            assert sym["param"] == "message"

    def test_enum_param_is_enum(self, extractor, proto_file):
        """Test that proto enums use param='enum' (not 'struct')."""
        symbols = extractor.list_symbols(proto_file)
        enums = [s for s in symbols if s["kind"] == "enum"]

        for sym in enums:
            assert sym["param"] == "enum"

    def test_all_symbols_have_required_fields(self, extractor, proto_file):
        """Test that all proto symbols have required fields."""
        symbols = extractor.list_symbols(proto_file)

        for sym in symbols:
            assert "name" in sym
            assert "kind" in sym
            assert "param" in sym
            assert "line" in sym
            assert sym["line"] > 0

    def test_listed_messages_are_extractable(self, extractor, proto_file):
        """Test that listed message names actually work with extract_message."""
        symbols = extractor.list_symbols(proto_file)
        messages = [s for s in symbols if s["param"] == "message"]

        for sym in messages[:5]:
            text, start, end = extractor.extract_message(proto_file, sym["name"])
            assert text, f"Failed to extract message '{sym['name']}'"

    def test_listed_enums_are_extractable(self, extractor, proto_file):
        """Test that listed enum names actually work with extract_enum."""
        symbols = extractor.list_symbols(proto_file)
        enums = [s for s in symbols if s["param"] == "enum"]

        for sym in enums[:5]:
            text, start, end = extractor.extract_enum(proto_file, sym["name"])
            assert text, f"Failed to extract enum '{sym['name']}'"


class TestListSymbolsCLI:
    """Test the CLI command integration."""

    def test_cli_no_args_shows_table(self):
        """Test that list-functions with no args shows the params table."""
        from click.testing import CliRunner

        from projected_source.cli import cli

        runner = CliRunner()
        result = runner.invoke(cli, ["list-functions"])

        assert result.exit_code == 0
        assert "code()" in result.output
        assert "function=" in result.output
        assert "marker=" in result.output

    def test_cli_with_cpp_file(self):
        """Test list-functions with a C++ file."""
        from click.testing import CliRunner

        from projected_source.cli import cli

        runner = CliRunner()
        result = runner.invoke(cli, ["list-functions", "tests/fixtures/complete.cpp"])

        assert result.exit_code == 0
        assert "simpleFunction" in result.output
        assert "function=" in result.output

    def test_cli_with_proto_file(self):
        """Test list-functions with a proto file."""
        from click.testing import CliRunner

        from projected_source.cli import cli

        runner = CliRunner()
        result = runner.invoke(cli, ["list-functions", "tests/fixtures/ripple.proto"])

        assert result.exit_code == 0
        assert "TMTransaction" in result.output
        assert "message=" in result.output

    def test_cli_with_nonexistent_file(self):
        """Test list-functions with a non-existent file."""
        from click.testing import CliRunner

        from projected_source.cli import cli

        runner = CliRunner()
        result = runner.invoke(cli, ["list-functions", "nonexistent.cpp"])

        assert result.exit_code != 0

    def test_cli_with_unsupported_file(self, tmp_path):
        """Test list-functions with an unsupported file type."""
        from click.testing import CliRunner

        from projected_source.cli import cli

        # Create a .txt file
        txt_file = tmp_path / "test.txt"
        txt_file.write_text("hello")

        runner = CliRunner()
        result = runner.invoke(cli, ["list-functions", str(txt_file)])

        assert result.exit_code != 0
