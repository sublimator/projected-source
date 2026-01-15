#!/usr/bin/env python3
"""
Test suite for overloaded function disambiguation using signature matching.
"""

from pathlib import Path

import pytest

from projected_source.languages.cpp import CppExtractor
from projected_source.languages.cpp_parser import SimpleCppParser


class TestOverloadDisambiguation:
    """Test overload disambiguation using signature parameter."""

    @pytest.fixture
    def fixture_file(self):
        """Use the overloads fixture file."""
        return Path("tests/fixtures/overloads.cpp")

    @pytest.fixture
    def parser(self):
        """Provide the parser."""
        return SimpleCppParser()

    @pytest.fixture
    def extractor(self):
        """Provide the extractor."""
        return CppExtractor()

    # === Parser-level tests ===

    def test_find_all_overloads(self, parser, fixture_file):
        """Test that we can find all overloads of a function."""
        source = fixture_file.read_bytes()
        nodes = parser._find_all_nodes_by_qualified_name(source, "PeerImp::onMessage", ["function_definition"])

        # Should find 4 onMessage overloads
        assert len(nodes) == 4

    def test_extract_by_signature_proposal(self, parser, fixture_file):
        """Test extracting specific overload by signature - TMProposeSet."""
        source = fixture_file.read_bytes()
        result = parser.extract_function_by_name(source, "PeerImp::onMessage", signature="TMProposeSet")

        assert result is not None
        assert "TMProposeSet" in result.text
        assert "processProposal" in result.text

    def test_extract_by_signature_transaction(self, parser, fixture_file):
        """Test extracting specific overload by signature - TMTransaction."""
        source = fixture_file.read_bytes()
        result = parser.extract_function_by_name(source, "PeerImp::onMessage", signature="TMTransaction")

        assert result is not None
        assert "TMTransaction" in result.text
        assert "processTransaction" in result.text

    def test_extract_by_signature_ledger(self, parser, fixture_file):
        """Test extracting specific overload by signature - TMGetLedger."""
        source = fixture_file.read_bytes()
        result = parser.extract_function_by_name(source, "PeerImp::onMessage", signature="TMGetLedger")

        assert result is not None
        assert "TMGetLedger" in result.text
        assert "processLedgerRequest" in result.text

    def test_extract_by_signature_validation(self, parser, fixture_file):
        """Test extracting specific overload by signature - TMValidation."""
        source = fixture_file.read_bytes()
        result = parser.extract_function_by_name(source, "PeerImp::onMessage", signature="TMValidation")

        assert result is not None
        assert "TMValidation" in result.text
        assert "processValidation" in result.text

    def test_extract_without_signature_returns_first(self, parser, fixture_file):
        """Test that without signature, first overload is returned."""
        source = fixture_file.read_bytes()
        result = parser.extract_function_by_name(source, "PeerImp::onMessage")

        # Should get the first one (TMProposeSet)
        assert result is not None
        assert "onMessage" in result.text

    def test_extract_primitive_overload_int(self, parser, fixture_file):
        """Test extracting overload with int parameter."""
        source = fixture_file.read_bytes()
        result = parser.extract_function_by_name(source, "PeerImp::process", signature="int value")

        assert result is not None
        assert "handleInt" in result.text

    def test_extract_primitive_overload_string(self, parser, fixture_file):
        """Test extracting overload with string parameter."""
        source = fixture_file.read_bytes()
        result = parser.extract_function_by_name(source, "PeerImp::process", signature="std::string")

        assert result is not None
        assert "handleString" in result.text

    def test_extract_primitive_overload_two_ints(self, parser, fixture_file):
        """Test extracting overload with two int parameters."""
        source = fixture_file.read_bytes()
        result = parser.extract_function_by_name(source, "PeerImp::process", signature="int a, int b")

        assert result is not None
        assert "handleIntPair" in result.text

    def test_no_match_returns_none(self, parser, fixture_file):
        """Test that non-matching signature returns None."""
        source = fixture_file.read_bytes()
        result = parser.extract_function_by_name(source, "PeerImp::onMessage", signature="NonExistent")

        assert result is None

    def test_free_function_overloads(self, parser, fixture_file):
        """Test extracting overloaded free functions."""
        source = fixture_file.read_bytes()

        # By int
        result = parser.extract_function_by_name(source, "handleEvent", signature="int code")
        assert result is not None
        assert "Handle by code" in result.text

        # By string
        result = parser.extract_function_by_name(source, "handleEvent", signature="std::string")
        assert result is not None
        assert "Handle by name" in result.text

        # By both
        result = parser.extract_function_by_name(source, "handleEvent", signature="int code, const std::string")
        assert result is not None
        assert "Handle with code and message" in result.text

    # === Extractor-level tests ===

    def test_extractor_with_signature(self, extractor, fixture_file):
        """Test CppExtractor with signature parameter."""
        text, start, end = extractor.extract_function(fixture_file, "PeerImp::onMessage", signature="TMTransaction")

        assert "TMTransaction" in text
        assert "processTransaction" in text
        assert start > 0
        assert end >= start

    def test_extractor_no_match_raises(self, extractor, fixture_file):
        """Test that CppExtractor raises on no match."""
        with pytest.raises(ValueError) as exc_info:
            extractor.extract_function(fixture_file, "PeerImp::onMessage", signature="NonExistent")

        assert "NonExistent" in str(exc_info.value)

    # === Parameter signature extraction tests ===

    def test_extract_parameter_signature(self, parser, fixture_file):
        """Test that parameter signatures are correctly extracted."""
        source = fixture_file.read_bytes()
        nodes = parser._find_all_nodes_by_qualified_name(source, "PeerImp::onMessage", ["function_definition"])

        signatures = [parser._extract_parameter_signature(n) for n in nodes]

        # Each should contain the parameter type
        assert any("TMProposeSet" in sig for sig in signatures)
        assert any("TMTransaction" in sig for sig in signatures)
        assert any("TMGetLedger" in sig for sig in signatures)
        assert any("TMValidation" in sig for sig in signatures)
