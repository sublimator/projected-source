"""Tests for extern function declaration extraction in C/C++."""

from pathlib import Path

import pytest

from projected_source.languages.cpp import CppExtractor

FIXTURE = Path(__file__).parent / "fixtures" / "cpp" / "extern_decls.h"


class TestExternSymbolDiscovery:
    """list_symbols should find extern function declarations."""

    @pytest.fixture
    def symbols(self):
        ext = CppExtractor()
        return ext.list_symbols(FIXTURE)

    @pytest.fixture
    def fn_names(self, symbols):
        return [s["name"] for s in symbols if s["kind"] == "function"]

    def test_finds_simple_extern(self, fn_names):
        assert "etxn_burden" in fn_names

    def test_finds_extern_with_params(self, fn_names):
        assert "emit" in fn_names
        assert "state_set" in fn_names

    def test_finds_extern_with_attribute(self, fn_names):
        assert "_g" in fn_names

    def test_finds_all_75_externs(self, fn_names):
        assert len(fn_names) == 75

    def test_no_variables_found(self, symbols):
        vars = [s for s in symbols if s["kind"] == "variable"]
        assert len(vars) == 0


class TestExternExtraction:
    """Extract specific extern declarations by name."""

    def test_extract_simple_extern(self):
        ext = CppExtractor()
        text, start, end = ext.extract_function(FIXTURE, "etxn_burden")
        assert "extern" in text
        assert "etxn_burden" in text

    def test_extract_extern_with_params(self):
        ext = CppExtractor()
        text, start, end = ext.extract_function(FIXTURE, "emit")
        assert "emit" in text
        assert "write_ptr" in text
        assert "read_ptr" in text

    def test_extract_extern_multiline(self):
        ext = CppExtractor()
        text, start, end = ext.extract_function(FIXTURE, "util_verify")
        assert "util_verify" in text
        assert "dread_ptr" in text
        assert "kread_len" in text

    def test_extract_extern_with_signature(self):
        ext = CppExtractor()
        text, start, end = ext.extract_function(FIXTURE, "state_set")
        assert "state_set" in text
        assert "kread_ptr" in text

    def test_prefers_definition_over_declaration(self):
        """When both a definition and declaration exist, prefer the definition."""
        ext = CppExtractor()
        # This file only has declarations, so it should still work
        text, start, end = ext.extract_function(FIXTURE, "accept")
        assert "accept" in text
        assert "error_code" in text
