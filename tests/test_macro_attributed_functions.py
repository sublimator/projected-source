"""Tests for macro-attributed function extraction (e.g. EXCLUSIVE_LOCKS_REQUIRED).

When a function has attribute macros between the signature and body,
tree-sitter splits it into:
  declaration + expression_statement + compound_statement
instead of a single function_definition.
"""

from pathlib import Path

from projected_source.languages.cpp import CppExtractor

FIXTURE = Path(__file__).parent / "fixtures" / "cpp" / "spend.cpp"


class TestMacroAttributedFunction:
    def test_extract_function_includes_body(self):
        ext = CppExtractor()
        text, start, end = ext.extract_function(FIXTURE, "wallet::CreateTransactionInternal")
        assert start == 1063
        assert end == 1466
        assert "CreateTransactionInternal" in text
        assert "tesSUCCESS" not in text  # bitcoin uses different patterns
        assert "coin_control" in text

    def test_extract_function_marker_coin_selection(self):
        ext = CppExtractor()
        text, start, end = ext.extract_function_marker(
            FIXTURE, "wallet::CreateTransactionInternal", "coin-selection-params"
        )
        assert start == 1078
        assert end == 1091

    def test_extract_function_marker_recipient_validation(self):
        ext = CppExtractor()
        text, start, end = ext.extract_function_marker(
            FIXTURE, "wallet::CreateTransactionInternal", "recipient-validation"
        )
        assert start == 1095

    def test_extract_function_marker_choose_coins(self):
        ext = CppExtractor()
        text, start, end = ext.extract_function_marker(FIXTURE, "wallet::CreateTransactionInternal", "choose-coins")
        assert start == 1229

    def test_extract_function_marker_all_six(self):
        ext = CppExtractor()
        markers = [
            "coin-selection-params",
            "recipient-validation",
            "choose-coins",
            "assemble-outputs",
            "fill-inputs",
            "sign-and-finalize",
        ]
        for marker in markers:
            text, start, end = ext.extract_function_marker(FIXTURE, "wallet::CreateTransactionInternal", marker)
            assert start > 0
            assert end > start

    def test_list_symbols_finds_function(self):
        ext = CppExtractor()
        symbols = ext.list_symbols(FIXTURE)
        names = [s["name"] for s in symbols]
        assert "wallet::CreateTransactionInternal" in names
