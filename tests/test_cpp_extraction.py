#!/usr/bin/env python3
"""
Comprehensive test suite for C++ code extraction.
Tests against a parser interface, not a specific implementation.
"""

import pytest
from pathlib import Path
from projected_source.languages.cpp import CppExtractor
from projected_source.languages.cpp_parser import SimpleCppParser
from projected_source.languages.cpp_parser_query import QueryBasedCppParser


class TestCppParsers:
    """Test C++ parser implementations against the interface."""
    
    @pytest.fixture
    def test_file(self):
        """Use the static fixture file."""
        return Path("tests/fixtures/complete.cpp")
    
    @pytest.fixture(params=[
        SimpleCppParser(),
        # QueryBasedCppParser(),  # Uncomment when query parser is fully working
    ])
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
            test_file, 
            {'name': 'DEFINE_JS_FUNCTION', 'arg1': 'testFunc'}
        )
        
        assert "DEFINE_JS_FUNCTION" in text
        assert "testFunc" in text
        assert "value1 + value2" in text
    
    def test_extract_function_macro_marker(self, extractor, test_file):
        """Test extracting a marked section within a macro."""
        text, start, end = extractor.extract_function_macro_marker(
            test_file,
            {'name': 'DEFINE_JS_FUNCTION', 'arg1': 'testFunc'},
            'example1'
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