"""Regression test for SetTrust::doApply extraction.

Bug: list-functions found SetTrust::doApply but code() extraction failed.
File has anonymous namespace at top and ~380 line function near EOF.
"""

from pathlib import Path

from projected_source.languages.cpp import CppExtractor

FIXTURE = Path(__file__).parent / "fixtures" / "cpp" / "SetTrust.cpp"


class TestSetTrustRegression:
    def test_extract_doApply(self):
        ext = CppExtractor()
        text, start, end = ext.extract_function(FIXTURE, "SetTrust::doApply")
        assert start == 286
        assert "SetTrust::doApply()" in text
        assert "tesSUCCESS" in text

    def test_extract_preflight(self):
        ext = CppExtractor()
        text, start, end = ext.extract_function(FIXTURE, "SetTrust::preflight")
        assert "preflight" in text

    def test_extract_preclaim(self):
        ext = CppExtractor()
        text, start, end = ext.extract_function(FIXTURE, "SetTrust::preclaim")
        assert "preclaim" in text

    def test_extract_anonymous_namespace_function(self):
        """computeFreezeFlags lives in an anonymous namespace."""
        ext = CppExtractor()
        text, start, end = ext.extract_function(FIXTURE, "computeFreezeFlags")
        assert "computeFreezeFlags" in text

    def test_list_symbols_finds_all(self):
        ext = CppExtractor()
        symbols = ext.list_symbols(FIXTURE)
        names = [s["name"] for s in symbols]
        assert "SetTrust::doApply" in names
        assert "SetTrust::preflight" in names
        assert "SetTrust::preclaim" in names
        assert "computeFreezeFlags" in names
