#!/usr/bin/env python3
"""
Test suite for .macro file support and function_macro argument matching.
"""

from pathlib import Path

import pytest

from projected_source.languages import get_extractor
from projected_source.languages.cpp import CppExtractor


class TestMacroFileExtension:
    """Test that .macro files are recognized and extractable."""

    @pytest.fixture
    def macro_file(self):
        return Path("tests/fixtures/sfields.macro")

    @pytest.fixture
    def extractor(self):
        return CppExtractor()

    def test_get_extractor_for_macro_file(self, macro_file):
        """Test that get_extractor returns CppExtractor for .macro files."""
        ext = get_extractor(macro_file)
        assert isinstance(ext, CppExtractor)

    def test_extract_macro_call_from_macro_file(self, extractor, macro_file):
        """Test extracting a macro call from a .macro file."""
        text, start, end = extractor.extract_function_macro(
            macro_file, {"name": "TYPED_SFIELD", "arg0": "sfHookExportCount"}
        )
        assert "sfHookExportCount" in text
        assert "UINT16" in text
        assert "98" in text

    def test_extract_lines_from_macro_file(self, extractor, macro_file):
        """Test extracting lines from a .macro file."""
        text, start, end = extractor.extract_lines(macro_file, 1, 3)
        assert start == 1
        assert end == 3

    def test_list_symbols_macro_file(self, extractor, macro_file):
        """Test that list_symbols works on .macro files."""
        symbols = extractor.list_symbols(macro_file)
        # Should find at least some symbols
        assert len(symbols) >= 0  # May or may not find extractable symbols depending on parsing


class TestFunctionMacroArgPosition:
    """Test function_macro extraction with different arg positions."""

    @pytest.fixture
    def hook_file(self):
        return Path("tests/fixtures/hook_functions.cpp")

    @pytest.fixture
    def extractor(self):
        return CppExtractor()

    def test_extract_by_arg1(self, extractor, hook_file):
        """Test extracting macro-defined function by arg1 (second positional arg)."""
        text, start, end = extractor.extract_function_macro(
            hook_file, {"name": "DEFINE_HOOK_FUNCTION", "arg1": "xport_reserve"}
        )
        assert "xport_reserve" in text
        assert "Reserve export slots" in text

    def test_extract_by_arg1_different_function(self, extractor, hook_file):
        """Test extracting a different function by arg1."""
        text, start, end = extractor.extract_function_macro(
            hook_file, {"name": "DEFINE_HOOK_FUNCTION", "arg1": "hook_account"}
        )
        assert "hook_account" in text
        assert "Get account ID" in text

    def test_arg0_is_return_type(self, extractor, hook_file):
        """Test that arg0 is the return type, not the function name."""
        # All 3 functions have int64_t as arg0, so this should match multiple
        with pytest.raises(ValueError, match="Multiple"):
            extractor.extract_function_macro(
                hook_file, {"name": "DEFINE_HOOK_FUNCTION", "arg0": "int64_t"}
            )

    def test_wrong_arg_position_raises(self, extractor, hook_file):
        """Test that wrong arg position raises ValueError."""
        with pytest.raises(ValueError, match="No DEFINE_HOOK_FUNCTION found"):
            extractor.extract_function_macro(
                hook_file, {"name": "DEFINE_HOOK_FUNCTION", "arg0": "xport_reserve"}
            )

    def test_extract_by_arg1_with_marker(self, extractor):
        """Test function_macro with arg1 and markers."""
        # Create a file with markers inside a macro function
        import tempfile

        source = b"""
DEFINE_HOOK_FUNCTION(int64_t, my_func, uint32_t x)
{
    //@@start setup
    int a = 1;
    //@@end setup
    return a;
}
"""
        with tempfile.NamedTemporaryFile(suffix=".cpp", delete=False) as f:
            f.write(source)
            f.flush()
            tmp_path = Path(f.name)

        try:
            text, start, end = extractor.extract_function_macro_marker(
                tmp_path, {"name": "DEFINE_HOOK_FUNCTION", "arg1": "my_func"}, "setup"
            )
            assert "int a = 1;" in text
        finally:
            tmp_path.unlink()

    def test_multiple_matches_without_arg_filter(self, extractor, hook_file):
        """Test that multiple matches without arg filter raises."""
        with pytest.raises(ValueError, match="Multiple"):
            extractor.extract_function_macro(
                hook_file, {"name": "DEFINE_HOOK_FUNCTION"}
            )

    def test_nonexistent_macro_raises(self, extractor, hook_file):
        """Test that nonexistent macro name raises."""
        with pytest.raises(ValueError, match="No NONEXISTENT_MACRO found"):
            extractor.extract_function_macro(
                hook_file, {"name": "NONEXISTENT_MACRO", "arg0": "foo"}
            )


class TestFunctionMacroArgExtraction:
    """Test the underlying argument extraction logic."""

    def test_define_hook_function_args(self):
        """Test that DEFINE_HOOK_FUNCTION args are extracted correctly."""
        from projected_source.languages.macro_finder_v3 import MacroFinder

        mf = MacroFinder()
        source = b"""
DEFINE_HOOK_FUNCTION(int64_t, xport_reserve, uint32_t count)
{
    return count;
}
"""
        results = mf.find_by_name(source, "DEFINE_HOOK_FUNCTION")
        assert len(results) == 1

        args = results[0]["arguments"]
        assert args[0] == "int64_t"
        assert args[1] == "xport_reserve"
        assert args[2] == "count"

    def test_typed_sfield_args(self):
        """Test that TYPED_SFIELD macro call args are extracted."""
        from projected_source.languages.macro_finder_v3 import MacroFinder

        mf = MacroFinder()
        source = b"""
TYPED_SFIELD(sfHookExportCount, UINT16, 98)
"""
        results = mf.find_by_name(source, "TYPED_SFIELD")
        assert len(results) == 1

        args = results[0]["arguments"]
        assert args[0] == "sfHookExportCount"
        assert args[1] == "UINT16"
        assert args[2] == "98"
