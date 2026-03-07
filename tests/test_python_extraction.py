"""Tests for Python code extraction."""

from pathlib import Path

import pytest

from projected_source.languages.python import PythonExtractor

FIXTURE = Path(__file__).parent / "fixtures" / "python" / "sample.py"


@pytest.fixture
def extractor():
    return PythonExtractor()


class TestExtractFunction:
    def test_simple_function(self, extractor):
        text, start, end = extractor.extract_function(FIXTURE, "simple_function")
        assert "def simple_function():" in text
        assert "return 42" in text

    def test_function_with_args(self, extractor):
        text, start, end = extractor.extract_function(FIXTURE, "function_with_args")
        assert "def function_with_args(x: int, y: str" in text
        assert "-> bool" in text

    def test_async_function(self, extractor):
        text, start, end = extractor.extract_function(FIXTURE, "async_handler")
        assert "async def async_handler" in text

    def test_nested_function(self, extractor):
        text, start, end = extractor.extract_function(FIXTURE, "outer_function.inner_function")
        assert "def inner_function():" in text
        assert "return \"inner\"" in text
        # Should NOT include outer_function
        assert "def outer_function" not in text

    def test_class_method(self, extractor):
        text, start, end = extractor.extract_function(FIXTURE, "SimpleClass.get_value")
        assert "def get_value(self) -> int:" in text
        assert "return self.value" in text

    def test_class_init(self, extractor):
        text, start, end = extractor.extract_function(FIXTURE, "SimpleClass.__init__")
        assert "def __init__(self, value: int):" in text

    def test_decorated_static_method(self, extractor):
        text, start, end = extractor.extract_function(FIXTURE, "SimpleClass.static_method")
        assert "@staticmethod" in text
        assert "def static_method():" in text

    def test_decorated_classmethod(self, extractor):
        text, start, end = extractor.extract_function(FIXTURE, "SimpleClass.from_string")
        assert "@classmethod" in text
        assert "def from_string(cls, s: str)" in text

    def test_nested_class_method(self, extractor):
        text, start, end = extractor.extract_function(FIXTURE, "SimpleClass.InnerClass.inner_method")
        assert "def inner_method(self):" in text

    def test_async_method(self, extractor):
        text, start, end = extractor.extract_function(FIXTURE, "AsyncProcessor.process")
        assert "async def process" in text

    def test_decorated_top_level(self, extractor):
        text, start, end = extractor.extract_function(FIXTURE, "my_property")
        assert "@property" in text
        assert "def my_property(self):" in text

    def test_nonexistent_function(self, extractor):
        with pytest.raises(ValueError, match="not found"):
            extractor.extract_function(FIXTURE, "nonexistent")

    def test_nonexistent_method(self, extractor):
        with pytest.raises(ValueError, match="not found"):
            extractor.extract_function(FIXTURE, "SimpleClass.nonexistent")

    def test_complex_signature(self, extractor):
        text, start, end = extractor.extract_function(FIXTURE, "function_with_complex_sig")
        assert "*args" in text
        assert "**kwargs" in text
        assert "-> list[dict]" in text


class TestExtractClass:
    def test_simple_class(self, extractor):
        text, start, end = extractor.extract_struct(FIXTURE, "SimpleClass")
        assert "class SimpleClass:" in text
        assert "def __init__" in text
        assert "def get_value" in text
        assert "class InnerClass:" in text

    def test_nested_class(self, extractor):
        text, start, end = extractor.extract_struct(FIXTURE, "SimpleClass.InnerClass")
        assert "class InnerClass:" in text
        assert "def inner_method" in text
        # Should NOT include the outer class def
        assert "class SimpleClass:" not in text

    def test_async_class(self, extractor):
        text, start, end = extractor.extract_struct(FIXTURE, "AsyncProcessor")
        assert "class AsyncProcessor:" in text
        assert "async def process" in text

    def test_nonexistent_class(self, extractor):
        with pytest.raises(ValueError, match="not found"):
            extractor.extract_struct(FIXTURE, "NonExistent")


class TestExtractVariable:
    def test_simple_constant(self, extractor):
        text, start, end = extractor.extract_variable(FIXTURE, "MAX_RETRIES")
        assert "MAX_RETRIES = 3" in text

    def test_annotated_variable(self, extractor):
        text, start, end = extractor.extract_variable(FIXTURE, "DEFAULT_TIMEOUT")
        assert "DEFAULT_TIMEOUT: int = 30" in text

    def test_multiline_dict(self, extractor):
        text, start, end = extractor.extract_variable(FIXTURE, "LOOKUP_TABLE")
        assert "LOOKUP_TABLE = {" in text
        assert '"c": 3,' in text
        assert end > start  # multiline

    def test_nonexistent_variable(self, extractor):
        with pytest.raises(ValueError, match="not found"):
            extractor.extract_variable(FIXTURE, "NONEXISTENT")


class TestExtractMarker:
    def test_marker(self, extractor):
        text, start, end = extractor.extract_marker(FIXTURE, "config-section")
        assert "MAX_POOL_SIZE = 10" in text
        assert "MIN_POOL_SIZE = 1" in text
        # Marker comments themselves should not be in the extracted text
        assert "#@@start" not in text
        assert "#@@end" not in text

    def test_nonexistent_marker(self, extractor):
        with pytest.raises(ValueError, match="not found"):
            extractor.extract_marker(FIXTURE, "nonexistent")


class TestExtractLines:
    def test_extract_lines(self, extractor):
        text, start, end = extractor.extract_lines(FIXTURE, 1, 3)
        assert '"""A sample Python module for testing extraction."""' in text
        assert start == 1
        assert end == 3


class TestListSymbols:
    def test_finds_functions(self, extractor):
        symbols = extractor.list_symbols(FIXTURE)
        func_names = [s["name"] for s in symbols if s["param"] == "function"]
        assert "simple_function" in func_names
        assert "function_with_args" in func_names
        assert "async_handler" in func_names

    def test_finds_methods(self, extractor):
        symbols = extractor.list_symbols(FIXTURE)
        func_names = [s["name"] for s in symbols if s["param"] == "function"]
        assert "SimpleClass.get_value" in func_names
        assert "SimpleClass.__init__" in func_names
        assert "SimpleClass.static_method" in func_names

    def test_finds_nested(self, extractor):
        symbols = extractor.list_symbols(FIXTURE)
        func_names = [s["name"] for s in symbols if s["param"] == "function"]
        assert "outer_function.inner_function" in func_names
        assert "SimpleClass.InnerClass.inner_method" in func_names

    def test_finds_classes(self, extractor):
        symbols = extractor.list_symbols(FIXTURE)
        class_names = [s["name"] for s in symbols if s["param"] == "struct"]
        assert "SimpleClass" in class_names
        assert "SimpleClass.InnerClass" in class_names
        assert "AsyncProcessor" in class_names

    def test_finds_variables(self, extractor):
        symbols = extractor.list_symbols(FIXTURE)
        var_names = [s["name"] for s in symbols if s["param"] == "var"]
        assert "MAX_RETRIES" in var_names
        assert "DEFAULT_TIMEOUT" in var_names
        assert "LOOKUP_TABLE" in var_names

    def test_finds_markers(self, extractor):
        symbols = extractor.list_symbols(FIXTURE)
        marker_names = [s["name"] for s in symbols if s["param"] == "marker"]
        assert "config-section" in marker_names

    def test_async_function_kind(self, extractor):
        symbols = extractor.list_symbols(FIXTURE)
        async_syms = [s for s in symbols if s["name"] == "async_handler"]
        assert len(async_syms) == 1
        assert async_syms[0]["kind"] == "async function"

    def test_functions_have_signatures(self, extractor):
        symbols = extractor.list_symbols(FIXTURE)
        func_with_args = [s for s in symbols if s["name"] == "function_with_args"]
        assert len(func_with_args) == 1
        sig = func_with_args[0]["signature"]
        assert "x: int" in sig
        assert "y: str" in sig
        assert "-> bool" in sig

    def test_all_symbols_have_required_fields(self, extractor):
        symbols = extractor.list_symbols(FIXTURE)
        for sym in symbols:
            assert "name" in sym
            assert "kind" in sym
            assert "param" in sym
            assert "line" in sym


class TestExtractorRegistration:
    def test_py_extension(self):
        from projected_source.languages import get_extractor
        ext = get_extractor(Path("test.py"))
        assert isinstance(ext, PythonExtractor)

    def test_pyi_extension(self):
        from projected_source.languages import get_extractor
        ext = get_extractor(Path("test.pyi"))
        assert isinstance(ext, PythonExtractor)
