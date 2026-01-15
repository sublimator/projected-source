#!/usr/bin/env python3
"""
Comprehensive test suite for C++ code extraction.
Tests against a parser interface, not a specific implementation.
"""

from pathlib import Path

import pytest

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
