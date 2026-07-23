#!/usr/bin/env python3
"""
Comprehensive test suite for C++ code extraction.
Tests against a parser interface, not a specific implementation.
"""

from pathlib import Path

import pytest

from projected_source.core.changes_set import ChangesSet
from projected_source.core.renderer import TemplateRenderer
from projected_source.languages.cpp import CppExtractor
from projected_source.languages.cpp_parser import SimpleCppParser


class TestCppParsers:
    """Test C++ parser implementations against the interface."""

    @pytest.fixture
    def test_file(self):
        """Use the static fixture file."""
        return Path("tests/fixtures/complete.cpp")

    @pytest.fixture(
        params=[
            SimpleCppParser(),
            # QueryBasedCppParser(),  # Uncomment when query parser is fully working
        ]
    )
    def parser(self, request):
        """Provide different parser implementations to test."""
        return request.param

    def test_extract_simple_struct(self, parser, test_file):
        """Test extracting a simple struct."""
        source = test_file.read_bytes()
        result = parser.extract_struct_or_class_by_name(source, "SimpleStruct")

        assert result is not None
        assert "struct SimpleStruct" in result.text
        assert result.node_type == "struct_specifier"
        assert result.qualified_name == "SimpleStruct"

    def test_extract_simple_class(self, parser, test_file):
        """Test extracting a simple class."""
        source = test_file.read_bytes()
        result = parser.extract_struct_or_class_by_name(source, "SimpleClass")

        assert result is not None
        assert "class SimpleClass" in result.text
        assert result.node_type == "class_specifier"
        assert result.qualified_name == "SimpleClass"

    def test_extract_namespaced_struct(self, parser, test_file):
        """Test extracting a struct within a namespace."""
        source = test_file.read_bytes()
        result = parser.extract_struct_or_class_by_name(source, "MyNamespace::NamespacedStruct")

        assert result is not None
        assert "struct NamespacedStruct" in result.text
        assert result.node_type == "struct_specifier"

    def test_extract_namespaced_class(self, parser, test_file):
        """Test extracting a class within a namespace."""
        source = test_file.read_bytes()
        result = parser.extract_struct_or_class_by_name(source, "MyNamespace::NamespacedClass")

        assert result is not None
        assert "class NamespacedClass" in result.text
        assert "getValue" in result.text

    def test_extract_nested_struct(self, parser, test_file):
        """Test extracting a nested struct."""
        source = test_file.read_bytes()
        result = parser.extract_struct_or_class_by_name(source, "OuterClass::InnerStruct")

        assert result is not None
        assert "struct InnerStruct" in result.text

    def test_extract_nested_class(self, parser, test_file):
        """Test extracting a nested class."""
        source = test_file.read_bytes()
        result = parser.extract_struct_or_class_by_name(source, "OuterClass::InnerClass")

        assert result is not None
        assert "class InnerClass" in result.text
        assert "doSomething" in result.text

    def test_extract_deeply_nested(self, parser, test_file):
        """Test extracting deeply nested structures."""
        source = test_file.read_bytes()
        result = parser.extract_struct_or_class_by_name(source, "OuterClass::MiddleClass::DeepStruct")

        assert result is not None
        assert "struct DeepStruct" in result.text
        assert "deep_value" in result.text

    def test_extract_deep_namespace(self, parser, test_file):
        """Test extracting from nested namespaces."""
        source = test_file.read_bytes()
        result = parser.extract_struct_or_class_by_name(source, "MyNamespace::Inner::DeepStruct")

        assert result is not None
        assert "struct DeepStruct" in result.text
        assert "flag" in result.text

    def test_extract_simple_function(self, parser, test_file):
        """Test extracting a simple function."""
        source = test_file.read_bytes()
        result = parser.extract_function_by_name(source, "simpleFunction")

        assert result is not None
        assert "void simpleFunction()" in result.text

    def test_extract_namespaced_function(self, parser, test_file):
        """Test extracting a namespaced function."""
        source = test_file.read_bytes()
        result = parser.extract_function_by_name(source, "FunctionNamespace::namespacedFunction")

        assert result is not None
        assert "namespacedFunction" in result.text
        assert "return x * 2" in result.text

    def test_extract_class_method(self, parser, test_file):
        """Test extracting a class method."""
        source = test_file.read_bytes()
        result = parser.extract_function_by_name(source, "ClassWithMethods::simpleMethod")

        assert result is not None
        assert "simpleMethod" in result.text

    def test_extract_static_method(self, parser, test_file):
        """Test extracting a static class method."""
        source = test_file.read_bytes()
        result = parser.extract_function_by_name(source, "ClassWithMethods::staticMethod")

        assert result is not None
        assert "staticMethod" in result.text
        assert "return x" in result.text

    def test_extract_nested_class_method(self, parser, test_file):
        """Test extracting a method from a nested class."""
        source = test_file.read_bytes()
        result = parser.extract_function_by_name(source, "ClassWithMethods::Nested::nestedMethod")

        assert result is not None
        assert "nestedMethod" in result.text

    def test_nonexistent_struct(self, parser, test_file):
        """Test that nonexistent struct returns None."""
        source = test_file.read_bytes()
        result = parser.extract_struct_or_class_by_name(source, "NonexistentStruct")
        assert result is None

    def test_nonexistent_function(self, parser, test_file):
        """Test that nonexistent function returns None."""
        source = test_file.read_bytes()
        result = parser.extract_function_by_name(source, "nonexistentFunction")
        assert result is None

    def test_ambiguous_name_without_qualifier(self, parser, test_file):
        """Test that ambiguous names work without qualifiers."""
        source = test_file.read_bytes()
        # There are multiple "DeepStruct" in different scopes
        result = parser.extract_struct_or_class_by_name(source, "DeepStruct")
        # Should find at least one
        assert result is not None
        assert "struct DeepStruct" in result.text


class TestCppExtractor:
    """Test the full CppExtractor with all its features."""

    @pytest.fixture
    def extractor(self):
        """Create a CppExtractor instance."""
        return CppExtractor()

    @pytest.fixture
    def test_file(self):
        """Use the static fixture file."""
        return Path("tests/fixtures/complete.cpp")

    def test_extract_function_macro(self, extractor, test_file):
        """Test extracting a function defined by a macro."""
        text, start, end = extractor.extract_function_macro(
            test_file, {"name": "DEFINE_JS_FUNCTION", "arg1": "testFunc"}
        )

        assert "DEFINE_JS_FUNCTION" in text
        assert "testFunc" in text
        assert "value1 + value2" in text

    def test_extract_function_macro_marker(self, extractor, test_file):
        """Test extracting a marked section within a macro."""
        text, start, end = extractor.extract_function_macro_marker(
            test_file, {"name": "DEFINE_JS_FUNCTION", "arg1": "testFunc"}, "example1"
        )

        assert "int sum = value1 + value2;" in text
        assert "@@start" not in text
        assert "@@end" not in text

    def test_extract_macro_definition(self, extractor, test_file):
        """Test extracting macro definitions."""
        # Simple macro
        text, start, end = extractor.extract_macro_definition(test_file, "MAX_SIZE")
        assert "#define MAX_SIZE 1024" in text

        # Function-like macro
        text, start, end = extractor.extract_macro_definition(test_file, "MIN")
        assert "#define MIN(a, b)" in text
        assert "((a) < (b) ? (a) : (b))" in text

        # Multi-line macro
        text, start, end = extractor.extract_macro_definition(test_file, "COMPLEX_MACRO")
        assert "#define COMPLEX_MACRO" in text
        assert "do {" in text
        assert "while(0)" in text

    def test_extract_lines(self, extractor, test_file):
        """Test extracting specific line ranges."""
        text, start, end = extractor.extract_lines(test_file, 5, 8)

        assert "struct SimpleStruct" in text
        assert start == 5
        assert end == 8

    def test_extract_marker(self, extractor, test_file):
        """Test extracting marked sections."""
        text, start, end = extractor.extract_marker(test_file, "example1")

        assert "int sum = value1 + value2;" in text
        assert "@@start" not in text
        assert "@@end" not in text

    def test_extract_struct_through_extractor(self, extractor, test_file):
        """Test struct extraction through the main CppExtractor."""
        text, start, end = extractor.extract_struct(test_file, "SimpleStruct")

        assert "struct SimpleStruct" in text
        assert start == 5
        assert end == 8

    def test_extract_nested_struct_through_extractor(self, extractor, test_file):
        """Test nested struct extraction through the main CppExtractor."""
        text, start, end = extractor.extract_struct(test_file, "OuterClass::InnerStruct")

        assert "struct InnerStruct" in text
        assert "bool flag" in text

    def test_extract_function_marker(self, extractor, test_file):
        """Test extracting a marked section within a regular function."""
        # Test simple function with marker
        text, start, end = extractor.extract_function_marker(test_file, "functionWithMarkers", "calculation")

        assert "int result = temp * 2;" in text
        assert "@@start" not in text
        assert "@@end" not in text
        assert "setup" not in text  # Should not include other markers

        # Test another marker in the same function
        text, start, end = extractor.extract_function_marker(test_file, "functionWithMarkers", "setup")

        assert "int temp = a + b;" in text
        assert "calculation" not in text

        # Test hyphenated marker name
        text, start, end = extractor.extract_function_marker(test_file, "functionWithMarkers", "saving-ledger")

        assert "if (result > 0)" in text
        assert "save to ledger" in text
        assert "@@start" not in text

    def test_extract_namespaced_function_marker(self, extractor, test_file):
        """Test extracting marker from a namespaced function."""
        text, start, end = extractor.extract_function_marker(
            test_file, "FunctionNamespace::namespacedFunctionWithMarker", "processing"
        )

        assert "int processed = value * value;" in text
        assert "std::cout << processed" in text
        assert "@@start" not in text

    def test_extract_class_method_marker(self, extractor, test_file):
        """Test extracting marker from a class method."""
        # Test validation marker
        text, start, end = extractor.extract_function_marker(
            test_file, "ClassWithMethods::methodWithMarker", "validation"
        )

        assert "if (input < 0)" in text
        assert "return -1;" in text
        assert "computation" not in text

        # Test computation marker
        text, start, end = extractor.extract_function_marker(
            test_file, "ClassWithMethods::methodWithMarker", "computation"
        )

        assert "int output = input * input + input;" in text
        assert "validation" not in text

    def test_extract_function_marker_enclosed(self, extractor, test_file):
        """Enclosed marker extraction keeps both marker and enclosing function ranges."""
        result = extractor.extract_function_marker_enclosed(test_file, "functionWithMarkers", "calculation")

        assert result.marker_text.strip() == "int result = temp * 2;"
        assert result.marker_start_line == 71
        assert result.marker_end_line == 71
        assert result.enclosure_start_line == 65
        assert result.enclosure_end_line == 82
        assert "int functionWithMarkers(int a, int b)" in result.enclosure_text

    def test_extract_marker_enclosed_auto_chooses_closest_method(self, extractor, test_file):
        """Auto enclosure uses the nearest function-like node, not the outer class."""
        result = extractor.extract_marker_enclosed(test_file, "validation")

        assert "if (input < 0)" in result.marker_text
        assert result.enclosure_kind == "function_definition"
        assert result.enclosure_start_line == 102
        assert result.enclosure_end_line == 114
        assert "int methodWithMarker(int input)" in result.enclosure_text
        assert "class ClassWithMethods" not in result.enclosure_text

    def test_extract_function_macro_marker_enclosed(self, extractor, test_file):
        """Macro-defined functions also provide an enclosing range."""
        result = extractor.extract_function_macro_marker_enclosed(
            test_file, {"name": "DEFINE_JS_FUNCTION", "arg1": "testFunc"}, "example1"
        )

        assert result.marker_text.strip() == "int sum = value1 + value2;"
        assert "DEFINE_JS_FUNCTION(JSValue, testFunc" in result.enclosure_text
        assert "return JS_NewInt32(ctx, sum);" in result.enclosure_text


class TestCppRendererEnclosureContext:
    """Renderer integration for marker enclosure context."""

    @pytest.fixture
    def renderer(self):
        return TemplateRenderer(template_dir=Path("."), repo_path=Path("."))

    def test_function_marker_enclosure_context_keeps_marker_permalink(self, renderer):
        result = renderer._code_function(
            "tests/fixtures/complete.cpp",
            function="functionWithMarkers",
            marker="calculation",
            enclosure_context=2,
            github=False,
        )

        assert "`tests/fixtures/complete.cpp:71`" in result
        assert "  65 int functionWithMarkers(int a, int b) {" in result
        assert "  71     int result = temp * 2;" in result
        assert "  81     return result;" in result
        assert "  82 }" in result
        assert "int temp = a + b;" not in result
        assert "@@start" not in result
        assert "@@end" not in result
        assert "..." in result

    def test_auto_enclosure_context_uses_closest_function(self, renderer):
        result = renderer._code_function(
            "tests/fixtures/complete.cpp",
            marker="validation",
            enclosure="auto",
            enclosure_context=2,
            github=False,
        )

        assert "`tests/fixtures/complete.cpp:104-106`" in result
        assert " 102     int methodWithMarker(int input) {" in result
        assert " 104         if (input < 0) {" in result
        assert " 113         return output;" in result
        assert " 114     }" in result
        assert "class ClassWithMethods" not in result
        assert "int output = input * input + input;" not in result

    def test_marker_only_enclosure_context_implies_auto(self, renderer):
        result = renderer._code_function(
            "tests/fixtures/complete.cpp",
            marker="validation",
            enclosure_context=2,
            github=False,
        )

        assert "`tests/fixtures/complete.cpp:104-106`" in result
        assert " 102     int methodWithMarker(int input) {" in result
        assert " 104         if (input < 0) {" in result
        assert "class ClassWithMethods" not in result

    def test_marker_only_default_enclosure_context_implies_auto(self, renderer):
        result = renderer._code_function(
            "tests/fixtures/complete.cpp",
            marker="validation",
            github=False,
        )

        assert "`tests/fixtures/complete.cpp:104-106`" in result
        assert " 102     int methodWithMarker(int input) {" in result
        assert " 104         if (input < 0) {" in result
        assert "class ClassWithMethods" not in result

    def test_enclosure_context_coverage_claims_marker_not_display_segments(self, tmp_path):
        """Coverage claims the marker body plus its //@@ delimiters (3-5);
        the enclosure head/tail shown by enclosure_context is presentation
        only and must not claim the lines it displays."""
        src = tmp_path / "example.cpp"
        src.write_text(
            "void f() {\n"
            "    int before = 0;\n"
            "    //@@start core\n"
            "    int shown = 1;\n"
            "    //@@end core\n"
            "    int hidden = 2;\n"
            "    return;\n"
            "}\n"
        )

        changes = ChangesSet()
        changes.add(src, 1, 8)

        renderer = TemplateRenderer(template_dir=tmp_path, repo_path=tmp_path, changes_set=changes)
        rendered = renderer._code_function(
            "example.cpp",
            function="f",
            marker="core",
            enclosure_context=1,
            github=False,
        )

        assert "   1 void f() {" in rendered
        assert "   4     int shown = 1;" in rendered
        assert "   8 }" in rendered
        assert "int hidden" not in rendered
        assert [(r.start_line, r.end_line) for r in changes.uncovered()] == [(1, 2), (6, 8)]

    def test_function_marker_default_enclosure_context(self, renderer):
        result = renderer._code_function(
            "tests/fixtures/complete.cpp",
            function="functionWithMarkers",
            marker="calculation",
            github=False,
        )

        assert "`tests/fixtures/complete.cpp:71`" in result
        assert "  65 int functionWithMarkers(int a, int b) {" in result
        assert "  71     int result = temp * 2;" in result
        assert "  81     return result;" in result
        assert "saving-ledger" not in result

    def test_function_macro_marker_renderer_uses_enclosure_context(self, renderer):
        result = renderer._code_function(
            "tests/fixtures/complete.cpp",
            function_macro={"name": "DEFINE_JS_FUNCTION", "arg1": "testFunc"},
            marker="example1",
            github=False,
        )

        assert "`tests/fixtures/complete.cpp:129`" in result
        assert "DEFINE_JS_FUNCTION(JSValue, testFunc" in result
        assert " 129     int sum = value1 + value2;" in result
        assert "return JS_NewInt32(ctx, sum);" in result


class TestCppRendererEnclosureEdgeCases:
    """Stress tests for C++ auto enclosure selection."""

    @pytest.fixture
    def source_file(self, tmp_path):
        src = tmp_path / "enclosures.cpp"
        src.write_text(
            "struct ProposalShare { int value; };\n"
            "struct TxSetShare { int value; };\n"
            "\n"
            "namespace alpha {\n"
            "\n"
            "//@@start helper-around\n"
            "static int namespaceHelper(int input) {\n"
            "    int adjusted = input + 1;\n"
            "    return adjusted;\n"
            "}\n"
            "//@@end helper-around\n"
            "\n"
            "//@@start namespace-variable\n"
            "int namespaceCounter = 0;\n"
            "//@@end namespace-variable\n"
            "\n"
            "template <typename T>\n"
            "T templatedHelper(T value) {\n"
            "    //@@start template-core\n"
            "    return value;\n"
            "    //@@end template-core\n"
            "}\n"
            "\n"
            "class Box {\n"
            "public:\n"
            "    //@@start field-marker\n"
            "    int field = 0;\n"
            "    //@@end field-marker\n"
            "\n"
            "    int method(int value) {\n"
            "        //@@start method-core\n"
            "        return value + field;\n"
            "        //@@end method-core\n"
            "    }\n"
            "};\n"
            "\n"
            "//@@start whole-class\n"
            "class WrappedClass {\n"
            "public:\n"
            "    void run() {}\n"
            "};\n"
            "//@@end whole-class\n"
            "\n"
            "void lambdaOwner() {\n"
            "    auto fn = []() {\n"
            "        //@@start lambda-core\n"
            "        return 12;\n"
            "        //@@end lambda-core\n"
            "    };\n"
            "}\n"
            "\n"
            "void share(ProposalShare const& share) {\n"
            "    //@@start same-marker\n"
            "    int proposal = share.value;\n"
            "    //@@end same-marker\n"
            "}\n"
            "\n"
            "void share(TxSetShare const& share) {\n"
            "    //@@start same-marker\n"
            "    int txSet = share.value;\n"
            "    //@@end same-marker\n"
            "}\n"
            "\n"
            "} // namespace alpha\n"
        )
        return src

    @pytest.fixture
    def renderer(self, tmp_path):
        return TemplateRenderer(template_dir=tmp_path, repo_path=tmp_path)

    def test_auto_marker_around_namespace_helper_uses_wrapped_helper(self, renderer, source_file):
        result = renderer._code_function(
            "enclosures.cpp",
            marker="helper-around",
            enclosure_context=2,
            github=False,
        )

        assert "`enclosures.cpp:7-10`" in result
        assert "static int namespaceHelper(int input)" in result
        assert "int adjusted = input + 1;" in result
        assert "namespace alpha" not in result
        assert "@@start" not in result

    def test_auto_marker_around_namespace_variable_uses_wrapped_declaration(self, renderer, source_file):
        result = renderer._code_function(
            "enclosures.cpp",
            marker="namespace-variable",
            enclosure_context=2,
            github=False,
        )

        assert "`enclosures.cpp:14`" in result
        assert "int namespaceCounter = 0;" in result
        assert "namespace alpha" not in result

    def test_auto_marker_inside_template_uses_template_declaration(self, renderer, source_file):
        result = renderer._code_function(
            "enclosures.cpp",
            marker="template-core",
            enclosure_context=2,
            github=False,
        )

        assert "`enclosures.cpp:20`" in result
        assert "template <typename T>" in result
        assert "T templatedHelper(T value)" in result
        assert "return value;" in result

    def test_auto_marker_around_field_uses_wrapped_field_declaration(self, renderer, source_file):
        result = renderer._code_function(
            "enclosures.cpp",
            marker="field-marker",
            enclosure_context=2,
            github=False,
        )

        assert "`enclosures.cpp:27`" in result
        assert "int field = 0;" in result
        assert "class Box" not in result

    def test_struct_marker_renderer_uses_struct_enclosure(self, renderer, source_file):
        result = renderer._code_function(
            "enclosures.cpp",
            struct="Box",
            marker="field-marker",
            github=False,
        )

        assert "`enclosures.cpp:27`" in result
        assert "class Box" in result
        assert "int field = 0;" in result

    def test_var_marker_renderer_uses_declaration_enclosure(self, tmp_path):
        source = tmp_path / "var_marker.cpp"
        source.write_text(
            "int computed = []() {\n"
            "    int before = 0;\n"
            "    //@@start var-core\n"
            "    return before + 42;\n"
            "    //@@end var-core\n"
            "}();\n"
        )
        renderer = TemplateRenderer(template_dir=tmp_path, repo_path=tmp_path)

        result = renderer._code_function(
            "var_marker.cpp",
            var="computed",
            marker="var-core",
            github=False,
        )

        assert "`var_marker.cpp:4`" in result
        assert "int computed = []()" in result
        assert "return before + 42;" in result
        assert "}();" in result

    def test_auto_marker_inside_method_uses_method_not_class(self, renderer, source_file):
        result = renderer._code_function(
            "enclosures.cpp",
            marker="method-core",
            enclosure_context=2,
            github=False,
        )

        assert "`enclosures.cpp:32`" in result
        assert "int method(int value)" in result
        assert "return value + field;" in result
        assert "class Box" not in result

    def test_auto_marker_around_class_uses_wrapped_class(self, renderer, source_file):
        result = renderer._code_function(
            "enclosures.cpp",
            marker="whole-class",
            enclosure_context=2,
            github=False,
        )

        assert "`enclosures.cpp:38-41`" in result
        assert "class WrappedClass" in result
        assert "void run() {}" in result
        assert "namespace alpha" not in result

    def test_auto_marker_inside_lambda_uses_lambda_not_owner_function(self, renderer, source_file):
        result = renderer._code_function(
            "enclosures.cpp",
            marker="lambda-core",
            enclosure_context=2,
            github=False,
        )

        assert "`enclosures.cpp:47`" in result
        assert "auto fn = []()" in result
        assert "return 12;" in result
        assert "void lambdaOwner()" not in result

    def test_function_marker_signature_selects_matching_overload(self, renderer, source_file):
        result = renderer._code_function(
            "enclosures.cpp",
            function="share",
            signature="TxSetShare",
            marker="same-marker",
            enclosure_context=1,
            github=False,
        )

        assert "`enclosures.cpp:60`" in result
        assert "void share(TxSetShare const& share)" in result
        assert "int txSet = share.value;" in result
        assert "proposal" not in result

    def test_function_marker_without_signature_reports_ambiguous_overloads(self, renderer, source_file):
        result = renderer._code_function(
            "enclosures.cpp",
            function="share",
            marker="same-marker",
            enclosure_context=1,
            github=False,
        )

        assert "❌ **ERROR**" in result
        assert "multiple overloads" in result
        assert "signature=" in result

    def test_function_marker_without_signature_direct_extractor_reports_ambiguous_overloads(self, source_file):
        extractor = CppExtractor()

        with pytest.raises(ValueError, match="multiple overloads"):
            extractor.extract_function_marker(source_file, "share", "same-marker")

    def test_function_marker_signature_still_works_when_context_opted_out(self, renderer, source_file):
        result = renderer._code_function(
            "enclosures.cpp",
            function="share",
            signature="TxSetShare",
            marker="same-marker",
            enclosure_context=0,
            github=False,
        )

        assert "`enclosures.cpp:60`" in result
        assert "int txSet = share.value;" in result
        assert "void share(TxSetShare const& share)" not in result
        assert "proposal" not in result

    def test_marker_only_duplicate_marker_names_report_ambiguous(self, renderer, source_file):
        result = renderer._code_function(
            "enclosures.cpp",
            marker="same-marker",
            github=False,
        )

        assert "❌ **ERROR**" in result
        assert "ambiguous" in result
        assert "multiple ranges" in result

    def test_duplicate_marker_names_inside_selected_function_report_ambiguous(self, tmp_path):
        source = tmp_path / "duplicates.cpp"
        source.write_text(
            "void f() {\n"
            "    //@@start dup\n"
            "    int first = 1;\n"
            "    //@@end dup\n"
            "    //@@start dup\n"
            "    int second = 2;\n"
            "    //@@end dup\n"
            "}\n"
        )
        extractor = CppExtractor()

        with pytest.raises(ValueError, match="multiple times"):
            extractor.extract_function_marker(source, "f", "dup")

        with pytest.raises(ValueError, match="multiple times"):
            extractor.extract_function_marker_enclosed(source, "f", "dup")

    def test_auto_marker_spanning_sibling_functions_reports_no_containing_enclosure(self, tmp_path):
        source = tmp_path / "spanning.cpp"
        source.write_text(
            "//@@start two-functions\n"
            "int first() {\n"
            "    return 1;\n"
            "}\n"
            "int second() {\n"
            "    return 2;\n"
            "}\n"
            "//@@end two-functions\n"
        )
        extractor = CppExtractor()

        with pytest.raises(ValueError, match="contains marker"):
            extractor.extract_marker_enclosed(source, "two-functions")

    def test_auto_marker_wrapping_function_with_padding_selects_function(self, tmp_path):
        source = tmp_path / "padded.cpp"
        source.write_text(
            "//@@start whole-function\n"
            "\n"
            "int paddedFunction() {\n"
            "    return 1;\n"
            "}\n"
            "\n"
            "//@@end whole-function\n"
        )
        extractor = CppExtractor()

        result = extractor.extract_marker_enclosed(source, "whole-function")

        assert result.enclosure_kind == "function_definition"
        assert result.enclosure_name == "paddedFunction"
        assert result.enclosure_start_line == 3
        assert result.enclosure_end_line == 5
        assert result.marker_start_line == 2
        assert result.marker_end_line == 6

    def test_auto_marker_wrapping_function_with_lambda_selects_function(self, tmp_path):
        source = tmp_path / "wrapped.cpp"
        source.write_text(
            "//@@start whole-function\n"
            "int wrappedFunction() {\n"
            "    auto fn = []() {\n"
            "        return 1;\n"
            "    };\n"
            "    return fn();\n"
            "}\n"
            "//@@end whole-function\n"
        )
        extractor = CppExtractor()

        result = extractor.extract_marker_enclosed(source, "whole-function")

        assert result.enclosure_kind == "function_definition"
        assert result.enclosure_name == "wrappedFunction"
        assert result.enclosure_start_line == 2
        assert result.enclosure_end_line == 7

    def test_auto_enclosure_name_uses_function_name_not_return_type(self, tmp_path):
        source = tmp_path / "names.cpp"
        source.write_text(
            "struct Result {};\n"
            "Result makeResult() {\n"
            "    //@@start body\n"
            "    return Result{};\n"
            "    //@@end body\n"
            "}\n"
        )
        extractor = CppExtractor()

        result = extractor.extract_marker_enclosed(source, "body")

        assert result.enclosure_kind == "function_definition"
        assert result.enclosure_name == "makeResult"

    def test_auto_enclosure_name_preserves_destructor_spelling(self, tmp_path):
        source = tmp_path / "destructor.cpp"
        source.write_text(
            "struct Widget {\n"
            "    //@@start dtor\n"
            "    ~Widget() {}\n"
            "    //@@end dtor\n"
            "};\n"
        )
        extractor = CppExtractor()

        result = extractor.extract_marker_enclosed(source, "dtor")

        assert result.enclosure_kind == "function_definition"
        assert result.enclosure_name == "~Widget"

    def test_auto_enclosure_name_uses_template_function_name_not_type_parameter(self, tmp_path):
        source = tmp_path / "template_name.cpp"
        source.write_text(
            "template <typename T>\n"
            "T makeValue(T value) {\n"
            "    //@@start body\n"
            "    return value;\n"
            "    //@@end body\n"
            "}\n"
        )
        extractor = CppExtractor()

        result = extractor.extract_marker_enclosed(source, "body")

        assert result.enclosure_kind == "template_declaration"
        assert result.enclosure_name == "makeValue"

    def test_auto_enclosure_name_uses_variable_name_not_type(self, tmp_path):
        source = tmp_path / "variable_name.cpp"
        source.write_text(
            "struct Result {};\n"
            "//@@start variable\n"
            "Result value;\n"
            "//@@end variable\n"
        )
        extractor = CppExtractor()

        result = extractor.extract_marker_enclosed(source, "variable")

        assert result.enclosure_kind == "declaration"
        assert result.enclosure_name == "value"

    def test_auto_marker_around_using_alias_uses_alias_declaration(self, tmp_path):
        source = tmp_path / "alias.cpp"
        source.write_text(
            "namespace alpha {\n"
            "//@@start alias\n"
            "using Foo = int;\n"
            "//@@end alias\n"
            "}\n"
        )
        extractor = CppExtractor()

        result = extractor.extract_marker_enclosed(source, "alias")

        assert result.enclosure_kind == "alias_declaration"
        assert result.enclosure_name == "Foo"
        assert result.enclosure_start_line == 3
        assert "namespace alpha" not in result.enclosure_text

    def test_auto_marker_around_typedef_uses_type_definition(self, tmp_path):
        source = tmp_path / "typedef.cpp"
        source.write_text(
            "namespace alpha {\n"
            "//@@start typedef\n"
            "typedef int Bar;\n"
            "//@@end typedef\n"
            "}\n"
        )
        extractor = CppExtractor()

        result = extractor.extract_marker_enclosed(source, "typedef")

        assert result.enclosure_kind == "type_definition"
        assert result.enclosure_name == "Bar"
        assert result.enclosure_start_line == 3
        assert "namespace alpha" not in result.enclosure_text

    def test_auto_marker_wrapping_class_with_inline_method_selects_class(self, tmp_path):
        source = tmp_path / "wrapped_class.cpp"
        source.write_text(
            "//@@start whole-class\n"
            "class Outer {\n"
            "public:\n"
            "    int method() { return 1; }\n"
            "};\n"
            "//@@end whole-class\n"
        )
        extractor = CppExtractor()

        result = extractor.extract_marker_enclosed(source, "whole-class")

        assert result.enclosure_kind == "class_specifier"
        assert result.enclosure_name == "Outer"
        assert result.enclosure_start_line == 2
        assert result.enclosure_end_line == 5


class TestInlineFunctions:
    """Test extraction of inline functions."""

    @pytest.fixture
    def parser(self):
        return SimpleCppParser()

    @pytest.fixture
    def test_file(self):
        return Path("tests/fixtures/complete.cpp")

    def test_simple_inline_function(self, parser, test_file):
        """Test extracting a simple inline function."""
        source = test_file.read_bytes()
        result = parser.extract_function_by_name(source, "inlineAdd")

        assert result is not None
        assert "inline int inlineAdd" in result.text
        assert "return a + b" in result.text

    def test_static_inline_function(self, parser, test_file):
        """Test extracting a static inline function."""
        source = test_file.read_bytes()
        result = parser.extract_function_by_name(source, "staticInlineFunc")

        assert result is not None
        assert "static inline void staticInlineFunc" in result.text

    def test_inline_complex_return_type(self, parser, test_file):
        """Test extracting inline function with complex return type."""
        source = test_file.read_bytes()
        result = parser.extract_function_by_name(source, "inlineComplexReturn")

        assert result is not None
        assert "inline" in result.text
        assert "std::optional" in result.text


class TestTemplateFunctions:
    """Test extraction of template functions."""

    @pytest.fixture
    def parser(self):
        return SimpleCppParser()

    @pytest.fixture
    def test_file(self):
        return Path("tests/fixtures/complete.cpp")

    def test_simple_template_function(self, parser, test_file):
        """Test extracting a simple template function."""
        source = test_file.read_bytes()
        result = parser.extract_function_by_name(source, "templateAdd")

        assert result is not None
        assert "template<typename T>" in result.text
        assert "T templateAdd(T a, T b)" in result.text
        assert result.node_type == "template_declaration"

    def test_template_function_multiple_params(self, parser, test_file):
        """Test extracting template function with multiple type parameters."""
        source = test_file.read_bytes()
        result = parser.extract_function_by_name(source, "templateMulti")

        assert result is not None
        assert "template<typename T, typename U>" in result.text
        assert "decltype(a + b)" in result.text

    def test_template_class_method(self, parser, test_file):
        """Test extracting a method from a template class."""
        source = test_file.read_bytes()
        result = parser.extract_function_by_name(source, "TemplateClass::getValue")

        assert result is not None
        assert "getValue" in result.text

    def test_template_class_another_method(self, parser, test_file):
        """Test extracting another method from template class."""
        source = test_file.read_bytes()
        result = parser.extract_function_by_name(source, "TemplateClass::setValue")

        assert result is not None
        assert "setValue" in result.text

    def test_template_specialization(self, parser, test_file):
        """Test extracting a template specialization."""
        source = test_file.read_bytes()
        # Supports templateAdd<int> syntax for specializations
        result = parser.extract_function_by_name(source, "templateAdd<int>")

        assert result is not None
        assert "template<>" in result.text
        assert "a + b + 1" in result.text

    def test_out_of_line_template_method(self, parser, test_file):
        """Test extracting an out-of-line template method."""
        source = test_file.read_bytes()
        # Supports Container<T>::add syntax for out-of-line template methods
        result = parser.extract_function_by_name(source, "Container<T>::add")

        assert result is not None
        assert "items.push_back" in result.text


class TestOperatorOverloads:
    """Test extraction of operator overloads."""

    @pytest.fixture
    def parser(self):
        return SimpleCppParser()

    @pytest.fixture
    def test_file(self):
        return Path("tests/fixtures/complete.cpp")

    def test_operator_plus(self, parser, test_file):
        """Test extracting operator+ overload."""
        source = test_file.read_bytes()
        result = parser.extract_function_by_name(source, "Vector2D::operator+")

        assert result is not None
        assert "operator+" in result.text
        assert "x + other.x" in result.text

    def test_operator_plus_equals(self, parser, test_file):
        """Test extracting operator+= overload."""
        source = test_file.read_bytes()
        result = parser.extract_function_by_name(source, "Vector2D::operator+=")

        assert result is not None
        assert "operator+=" in result.text

    def test_operator_equals(self, parser, test_file):
        """Test extracting operator== overload."""
        source = test_file.read_bytes()
        result = parser.extract_function_by_name(source, "Vector2D::operator==")

        assert result is not None
        assert "operator==" in result.text

    def test_operator_subscript(self, parser, test_file):
        """Test extracting operator[] overload."""
        source = test_file.read_bytes()
        result = parser.extract_function_by_name(source, "Vector2D::operator[]")

        assert result is not None
        assert "operator[]" in result.text

    def test_free_operator(self, parser, test_file):
        """Test extracting free operator* overload."""
        source = test_file.read_bytes()
        result = parser.extract_function_by_name(source, "operator*")

        assert result is not None
        assert "operator*" in result.text
        assert "v.x * scalar" in result.text


class TestSpecialFunctions:
    """Test extraction of special function types."""

    @pytest.fixture
    def parser(self):
        return SimpleCppParser()

    @pytest.fixture
    def test_file(self):
        return Path("tests/fixtures/complete.cpp")

    def test_constexpr_function(self, parser, test_file):
        """Test extracting a constexpr function."""
        source = test_file.read_bytes()
        result = parser.extract_function_by_name(source, "constexprFactorial")

        assert result is not None
        assert "constexpr int constexprFactorial" in result.text
        assert "n * constexprFactorial(n - 1)" in result.text

    def test_virtual_function(self, parser, test_file):
        """Test extracting a virtual function."""
        source = test_file.read_bytes()
        result = parser.extract_function_by_name(source, "Base::virtualFunc")

        assert result is not None
        assert "virtual void virtualFunc()" in result.text

    def test_override_function(self, parser, test_file):
        """Test extracting an override function."""
        source = test_file.read_bytes()
        result = parser.extract_function_by_name(source, "Derived::virtualFunc")

        assert result is not None
        assert "void virtualFunc() override" in result.text

    def test_pure_virtual_implementation(self, parser, test_file):
        """Test extracting implementation of pure virtual."""
        source = test_file.read_bytes()
        result = parser.extract_function_by_name(source, "Derived::pureVirtual")

        assert result is not None
        assert "pureVirtual() override" in result.text
        assert "return 42" in result.text

    def test_extern_c_function(self, parser, test_file):
        """Test extracting extern C function."""
        source = test_file.read_bytes()
        result = parser.extract_function_by_name(source, "externCFunc")

        assert result is not None
        assert "void externCFunc()" in result.text

    def test_extern_c_function_with_return(self, parser, test_file):
        """Test extracting extern C function with return."""
        source = test_file.read_bytes()
        result = parser.extract_function_by_name(source, "externCWithReturn")

        assert result is not None
        assert "int externCWithReturn" in result.text
        assert "return x * 2" in result.text

    def test_friend_function(self, parser, test_file):
        """Test extracting a friend function (definition, not declaration)."""
        source = test_file.read_bytes()
        result = parser.extract_function_by_name(source, "revealSecret")

        assert result is not None
        assert "void revealSecret" in result.text
        assert "holder.secret = 0" in result.text

    def test_noexcept_function(self, parser, test_file):
        """Test extracting a noexcept function."""
        source = test_file.read_bytes()
        result = parser.extract_function_by_name(source, "noexceptFunc")

        assert result is not None
        assert "noexcept" in result.text

    def test_nodiscard_function(self, parser, test_file):
        """Test extracting a [[nodiscard]] function."""
        source = test_file.read_bytes()
        result = parser.extract_function_by_name(source, "nodiscardFunc")

        assert result is not None
        assert "[[nodiscard]]" in result.text

    def test_deprecated_function(self, parser, test_file):
        """Test extracting a [[deprecated]] function."""
        source = test_file.read_bytes()
        result = parser.extract_function_by_name(source, "deprecatedFunc")

        assert result is not None
        assert "[[deprecated" in result.text
