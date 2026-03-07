"""Tests for Python code extraction."""

from pathlib import Path

import pytest

from projected_source.languages.python import PythonExtractor

FIXTURES = Path(__file__).parent / "fixtures" / "python"
FIXTURE = FIXTURES / "sample.py"
DECORATED_FIXTURE = FIXTURES / "decorated_classes.py"


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


class TestDecoratedClasses:
    def test_dataclass_includes_decorator(self, extractor):
        text, start, end = extractor.extract_struct(DECORATED_FIXTURE, "Config")
        assert "@dataclass" in text
        assert "class Config:" in text
        assert 'host: str = "localhost"' in text

    def test_decorated_class_in_list_symbols(self, extractor):
        symbols = extractor.list_symbols(DECORATED_FIXTURE)
        config = [s for s in symbols if s["name"] == "Config"]
        assert len(config) == 1
        # decorator line should be before class line
        assert config[0]["line"] < 10  # @dataclass is near top

    def test_inheriting_class(self, extractor):
        text, start, end = extractor.extract_struct(DECORATED_FIXTURE, "ChildConfig")
        assert "@dataclass" in text
        assert "class ChildConfig(Config):" in text

    def test_deeply_nested_class(self, extractor):
        text, start, end = extractor.extract_struct(DECORATED_FIXTURE, "Outer.Middle.Inner")
        assert "class Inner:" in text
        assert "def deep_method" in text
        assert "class Outer:" not in text
        assert "class Middle:" not in text

    def test_deeply_nested_method(self, extractor):
        text, start, end = extractor.extract_function(DECORATED_FIXTURE, "Outer.Middle.Inner.deep_method")
        assert "def deep_method(self):" in text
        assert 'return "deep"' in text


class TestDottedPathEdgeCases:
    def test_bad_first_segment(self, extractor):
        with pytest.raises(ValueError, match="not found"):
            extractor.extract_function(FIXTURE, "NonExistent.method")

    def test_bad_middle_segment(self, extractor):
        with pytest.raises(ValueError, match="not found"):
            extractor.extract_function(DECORATED_FIXTURE, "Outer.NonExistent.method")

    def test_deeply_nested_function(self, extractor):
        text, start, end = extractor.extract_function(
            DECORATED_FIXTURE, "valid_path.level_one.level_two"
        )
        assert "def level_two():" in text
        assert 'return "found"' in text

    def test_function_not_class_for_struct(self, extractor):
        """Searching for a function name with struct= should fail."""
        with pytest.raises(ValueError, match="not found"):
            extractor.extract_struct(FIXTURE, "simple_function")

    def test_class_not_function_for_function(self, extractor):
        """Searching for a class name with function= should fail."""
        with pytest.raises(ValueError, match="not found"):
            extractor.extract_function(FIXTURE, "SimpleClass")


class TestLineNumbers:
    def test_function_line_numbers(self, extractor):
        _, start, end = extractor.extract_function(FIXTURE, "simple_function")
        assert start == 14
        assert end == 16

    def test_decorated_function_starts_at_decorator(self, extractor):
        _, start, end = extractor.extract_function(FIXTURE, "SimpleClass.static_method")
        # @staticmethod line should be the start
        assert start == 62

    def test_class_line_numbers(self, extractor):
        _, start, end = extractor.extract_struct(FIXTURE, "SimpleClass")
        assert start == 50
        assert end == 76

    def test_variable_single_line(self, extractor):
        _, start, end = extractor.extract_variable(FIXTURE, "MAX_RETRIES")
        assert start == end  # single line

    def test_variable_multiline_span(self, extractor):
        _, start, end = extractor.extract_variable(FIXTURE, "LOOKUP_TABLE")
        assert start == 7
        assert end == 11

    def test_marker_excludes_marker_lines(self, extractor):
        text, start, end = extractor.extract_marker(FIXTURE, "config-section")
        source_lines = FIXTURE.read_text().splitlines()
        # start/end should point to content lines, not marker comment lines
        assert "#@@start" not in source_lines[start - 1]
        assert "#@@end" not in source_lines[end - 1]


class TestParseFileNotSupported:
    def test_parse_file_raises(self, extractor):
        with pytest.raises(NotImplementedError):
            extractor.parse_file(FIXTURE)


class TestSignatures:
    def test_kwonly_args_signature(self, extractor):
        symbols = extractor.list_symbols(DECORATED_FIXTURE)
        func = [s for s in symbols if s["name"] == "has_kwonly_args"]
        assert len(func) == 1
        sig = func[0]["signature"]
        assert "key: str" in sig
        assert "value: int" in sig
        assert "-> dict" in sig

    def test_self_in_method_signature(self, extractor):
        symbols = extractor.list_symbols(FIXTURE)
        init = [s for s in symbols if s["name"] == "SimpleClass.__init__"]
        assert len(init) == 1
        assert "self" in init[0]["signature"]
        assert "value: int" in init[0]["signature"]

    def test_no_args_signature(self, extractor):
        symbols = extractor.list_symbols(FIXTURE)
        simple = [s for s in symbols if s["name"] == "simple_function"]
        assert len(simple) == 1
        assert simple[0]["signature"] == "()"

    def test_complex_sig_in_list(self, extractor):
        symbols = extractor.list_symbols(FIXTURE)
        func = [s for s in symbols if s["name"] == "function_with_complex_sig"]
        assert len(func) == 1
        sig = func[0]["signature"]
        assert "*args: int" in sig
        assert "**kwargs: str" in sig


class TestRendererIntegration:
    """Test that code() dispatches correctly for Python files."""

    def test_code_function_python(self, tmp_path):
        """Test code() with function= on a .py file."""
        from projected_source.core.renderer import TemplateRenderer

        py_file = tmp_path / "example.py"
        py_file.write_text("def hello():\n    return 42\n")

        renderer = TemplateRenderer(template_dir=tmp_path, repo_path=tmp_path)
        result = renderer._code_function("example.py", function="hello", github=False)
        assert "def hello():" in result
        assert "return 42" in result
        assert "```python" in result

    def test_code_struct_python(self, tmp_path):
        """Test code() with struct= on a .py file."""
        from projected_source.core.renderer import TemplateRenderer

        py_file = tmp_path / "example.py"
        py_file.write_text("class Foo:\n    x = 1\n")

        renderer = TemplateRenderer(template_dir=tmp_path, repo_path=tmp_path)
        result = renderer._code_function("example.py", struct="Foo", github=False)
        assert "class Foo:" in result
        assert "x = 1" in result

    def test_code_var_python(self, tmp_path):
        """Test code() with var= on a .py file."""
        from projected_source.core.renderer import TemplateRenderer

        py_file = tmp_path / "example.py"
        py_file.write_text("MY_VAR = 42\n")

        renderer = TemplateRenderer(template_dir=tmp_path, repo_path=tmp_path)
        result = renderer._code_function("example.py", var="MY_VAR", github=False)
        assert "MY_VAR = 42" in result

    def test_code_marker_python(self, tmp_path):
        """Test code() with marker= on a .py file."""
        from projected_source.core.renderer import TemplateRenderer

        py_file = tmp_path / "example.py"
        py_file.write_text("#@@start section\nx = 1\ny = 2\n#@@end section\n")

        renderer = TemplateRenderer(template_dir=tmp_path, repo_path=tmp_path)
        result = renderer._code_function("example.py", marker="section", github=False)
        assert "x = 1" in result
        assert "y = 2" in result

    def test_code_lines_python(self, tmp_path):
        """Test code() with lines= on a .py file."""
        from projected_source.core.renderer import TemplateRenderer

        py_file = tmp_path / "example.py"
        py_file.write_text("line1\nline2\nline3\n")

        renderer = TemplateRenderer(template_dir=tmp_path, repo_path=tmp_path)
        result = renderer._code_function("example.py", lines=(1, 2), github=False)
        assert "line1" in result
        assert "line2" in result


class TestExtractorRegistration:
    def test_py_extension(self):
        from projected_source.languages import get_extractor
        ext = get_extractor(Path("test.py"))
        assert isinstance(ext, PythonExtractor)

    def test_pyi_extension(self):
        from projected_source.languages import get_extractor
        ext = get_extractor(Path("test.pyi"))
        assert isinstance(ext, PythonExtractor)
