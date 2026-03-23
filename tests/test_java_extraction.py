"""Tests for Java extraction."""

from pathlib import Path

import pytest

from projected_source.languages import get_extractor
from projected_source.languages.java import JavaExtractor

SAMPLE_JAVA = """\
package com.example;

import java.util.List;

public class Handler {
    private final String name;
    public static final int MAX_SIZE = 100;

    public Handler(String name) {
        this.name = name;
    }

    public void process(List<String> items) {
        for (String item : items) {
            System.out.println(item);
        }
    }

    private int getCount() {
        return 42;
    }
}

public interface Service {
    void start();
    void stop();
}

public enum Status {
    ACTIVE,
    INACTIVE,
    PENDING
}

public record Point(int x, int y) {}

//@@start example-section
int a = 1;
int b = 2;
//@@end example-section
"""


class TestJavaExtractorMethods:
    def test_extract_qualified_method(self, tmp_path):
        f = tmp_path / "Test.java"
        f.write_text(SAMPLE_JAVA)
        ext = JavaExtractor()
        text, start, end = ext.extract_function(f, "Handler.process")
        assert "public void process" in text
        assert "System.out.println" in text

    def test_extract_constructor(self, tmp_path):
        f = tmp_path / "Test.java"
        f.write_text(SAMPLE_JAVA)
        ext = JavaExtractor()
        text, start, end = ext.extract_function(f, "Handler.Handler")
        assert "public Handler(String name)" in text

    def test_extract_unqualified_method(self, tmp_path):
        f = tmp_path / "Test.java"
        f.write_text(SAMPLE_JAVA)
        ext = JavaExtractor()
        text, start, end = ext.extract_function(f, "process")
        assert "public void process" in text

    def test_extract_private_method(self, tmp_path):
        f = tmp_path / "Test.java"
        f.write_text(SAMPLE_JAVA)
        ext = JavaExtractor()
        text, start, end = ext.extract_function(f, "Handler.getCount")
        assert "private int getCount" in text
        assert "return 42" in text

    def test_method_not_found(self, tmp_path):
        f = tmp_path / "Test.java"
        f.write_text(SAMPLE_JAVA)
        ext = JavaExtractor()
        with pytest.raises(ValueError, match="not found"):
            ext.extract_function(f, "nonExistent")

    def test_interface_method(self, tmp_path):
        f = tmp_path / "Test.java"
        f.write_text(SAMPLE_JAVA)
        ext = JavaExtractor()
        text, start, end = ext.extract_function(f, "Service.start")
        assert "void start()" in text


class TestJavaExtractorTypes:
    def test_extract_class(self, tmp_path):
        f = tmp_path / "Test.java"
        f.write_text(SAMPLE_JAVA)
        ext = JavaExtractor()
        text, start, end = ext.extract_struct(f, "Handler")
        assert "public class Handler" in text
        assert "process" in text
        assert "getCount" in text

    def test_extract_interface(self, tmp_path):
        f = tmp_path / "Test.java"
        f.write_text(SAMPLE_JAVA)
        ext = JavaExtractor()
        text, start, end = ext.extract_struct(f, "Service")
        assert "public interface Service" in text
        assert "void start()" in text

    def test_extract_enum(self, tmp_path):
        f = tmp_path / "Test.java"
        f.write_text(SAMPLE_JAVA)
        ext = JavaExtractor()
        text, start, end = ext.extract_enum(f, "Status")
        assert "public enum Status" in text
        assert "ACTIVE" in text

    def test_extract_record(self, tmp_path):
        f = tmp_path / "Test.java"
        f.write_text(SAMPLE_JAVA)
        ext = JavaExtractor()
        text, start, end = ext.extract_struct(f, "Point")
        assert "public record Point" in text

    def test_struct_not_found(self, tmp_path):
        f = tmp_path / "Test.java"
        f.write_text(SAMPLE_JAVA)
        ext = JavaExtractor()
        with pytest.raises(ValueError, match="not found"):
            ext.extract_struct(f, "NonExistent")


class TestJavaExtractorFields:
    def test_extract_qualified_field(self, tmp_path):
        f = tmp_path / "Test.java"
        f.write_text(SAMPLE_JAVA)
        ext = JavaExtractor()
        text, start, end = ext.extract_variable(f, "Handler.MAX_SIZE")
        assert "MAX_SIZE" in text
        assert "100" in text

    def test_extract_unqualified_field(self, tmp_path):
        f = tmp_path / "Test.java"
        f.write_text(SAMPLE_JAVA)
        ext = JavaExtractor()
        text, start, end = ext.extract_variable(f, "MAX_SIZE")
        assert "MAX_SIZE" in text

    def test_field_not_found(self, tmp_path):
        f = tmp_path / "Test.java"
        f.write_text(SAMPLE_JAVA)
        ext = JavaExtractor()
        with pytest.raises(ValueError, match="not found"):
            ext.extract_variable(f, "NONEXISTENT")


class TestJavaExtractorMarkers:
    def test_extract_marker(self, tmp_path):
        f = tmp_path / "Test.java"
        f.write_text(SAMPLE_JAVA)
        ext = JavaExtractor()
        text, start, end = ext.extract_marker(f, "example-section")
        assert "int a = 1" in text
        assert "int b = 2" in text

    def test_marker_not_found(self, tmp_path):
        f = tmp_path / "Test.java"
        f.write_text(SAMPLE_JAVA)
        ext = JavaExtractor()
        with pytest.raises(ValueError, match="not found"):
            ext.extract_marker(f, "nonexistent")


class TestJavaListSymbols:
    def test_lists_all_symbols(self, tmp_path):
        f = tmp_path / "Test.java"
        f.write_text(SAMPLE_JAVA)
        ext = JavaExtractor()
        symbols = ext.list_symbols(f)
        names = [s["name"] for s in symbols]
        assert "Handler" in names
        assert "Handler.Handler" in names
        assert "Handler.process" in names
        assert "Handler.getCount" in names
        assert "Handler.name" in names
        assert "Handler.MAX_SIZE" in names
        assert "Service" in names
        assert "Service.start" in names
        assert "Service.stop" in names
        assert "Status" in names
        assert "Point" in names
        assert "example-section" in names

    def test_symbol_params(self, tmp_path):
        f = tmp_path / "Test.java"
        f.write_text(SAMPLE_JAVA)
        ext = JavaExtractor()
        symbols = ext.list_symbols(f)
        by_name = {s["name"]: s for s in symbols}
        assert by_name["Handler"]["param"] == "struct"
        assert by_name["Handler.process"]["param"] == "function"
        assert by_name["Handler.Handler"]["param"] == "function"
        assert by_name["Handler.MAX_SIZE"]["param"] == "var"
        assert by_name["Service"]["param"] == "struct"
        assert by_name["Status"]["param"] == "enum"
        assert by_name["Point"]["param"] == "struct"


class TestJavaRegistry:
    def test_java_extension(self):
        ext = get_extractor(Path("Test.java"))
        assert isinstance(ext, JavaExtractor)


class TestJavaRendererIntegration:
    def test_code_function_java(self, tmp_path):
        from projected_source.core.renderer import TemplateRenderer

        java_file = tmp_path / "Example.java"
        java_file.write_text('public class Example {\n    public String greet() {\n        return "hello";\n    }\n}\n')

        renderer = TemplateRenderer(template_dir=tmp_path, repo_path=tmp_path)
        result = renderer._code_function("Example.java", function="Example.greet", github=False)
        assert "public String greet()" in result
        assert "```java" in result
