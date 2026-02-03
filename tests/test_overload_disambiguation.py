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


class TestTemplateFunctionSignatures:
    """Test signature extraction from template functions."""

    @pytest.fixture
    def header_file(self):
        return Path("tests/fixtures/class_methods.h")

    @pytest.fixture
    def parser(self):
        return SimpleCppParser()

    def test_template_function_signatures_extracted(self, parser, header_file):
        """Test that template function signatures are not empty."""
        source = header_file.read_bytes()
        nodes = parser._find_all_nodes_by_qualified_name(source, "inUNLReport", ["function_definition"])

        # Should find 2 overloads
        assert len(nodes) == 2

        # Signatures should NOT be empty (this was the bug)
        signatures = [parser._extract_parameter_signature(n) for n in nodes]
        assert all(sig != "" for sig in signatures), f"Got empty signatures: {signatures}"

    def test_template_function_disambiguate_by_signature(self, parser, header_file):
        """Test disambiguating template function overloads by signature."""
        source = header_file.read_bytes()

        # Extract by AccountID signature
        result = parser.extract_function_by_name(source, "inUNLReport", signature="AccountID")
        assert result is not None
        assert "AccountID" in result.text

        # Extract by PublicKey signature
        result = parser.extract_function_by_name(source, "inUNLReport", signature="PublicKey")
        assert result is not None
        assert "PublicKey" in result.text
        assert "Application" in result.text  # Second overload also has Application

    def test_template_declaration_returns_template_node(self, parser, header_file):
        """Test that we return the template_declaration node, not inner function_definition."""
        source = header_file.read_bytes()
        nodes = parser._find_all_nodes_by_qualified_name(source, "inUNLReport", ["function_definition"])

        # All nodes should be template_declaration
        for node in nodes:
            assert node.type == "template_declaration", f"Expected template_declaration, got {node.type}"


class TestClassMethodDeclarations:
    """Test extraction of class method declarations from headers."""

    @pytest.fixture
    def header_file(self):
        return Path("tests/fixtures/class_methods.h")

    @pytest.fixture
    def parser(self):
        return SimpleCppParser()

    @pytest.fixture
    def extractor(self):
        return CppExtractor()

    def test_find_method_declaration_by_simple_name(self, parser, header_file):
        """Test finding method by simple name (without class qualifier)."""
        source = header_file.read_bytes()
        nodes = parser._find_all_nodes_by_qualified_name(source, "addProposal", ["function_definition"])

        # Should find exactly 1
        assert len(nodes) == 1
        assert nodes[0].type == "field_declaration"

    def test_find_method_declaration_by_qualified_name(self, parser, header_file):
        """Test finding method by qualified name (ClassName::method)."""
        source = header_file.read_bytes()
        nodes = parser._find_all_nodes_by_qualified_name(source, "ShuffleService::addProposal", ["function_definition"])

        assert len(nodes) == 1

    def test_field_declaration_signature_extraction(self, parser, header_file):
        """Test that signatures can be extracted from field_declaration nodes."""
        source = header_file.read_bytes()
        nodes = parser._find_all_nodes_by_qualified_name(source, "addProposal", ["function_definition"])

        assert len(nodes) == 1
        sig = parser._extract_parameter_signature(nodes[0])

        # Signature should contain the parameter types
        assert "prevLedger" in sig
        assert "txSetHash" in sig
        assert "signingPubKey" in sig

    def test_disambiguate_overloaded_class_methods(self, parser, header_file):
        """Test disambiguating overloaded class method declarations."""
        source = header_file.read_bytes()

        # computeCombinedEntropy has two overloads
        nodes = parser._find_all_nodes_by_qualified_name(source, "computeCombinedEntropy", ["function_definition"])
        assert len(nodes) == 2

        # Extract const member version
        result = parser.extract_function_by_name(source, "computeCombinedEntropy", signature="Digest const&")
        assert result is not None
        assert "optional" in result.text

        # Extract static version with vector
        result = parser.extract_function_by_name(source, "computeCombinedEntropy", signature="vector")
        assert result is not None
        assert "contributions" in result.text

    def test_find_multiple_methods_same_class(self, parser, header_file):
        """Test finding multiple different methods from same class."""
        source = header_file.read_bytes()

        methods = ["addProposal", "getProposals", "proposalCount", "reset"]
        for method in methods:
            nodes = parser._find_all_nodes_by_qualified_name(source, method, ["function_definition"])
            assert len(nodes) >= 1, f"Method {method} not found"

    def test_extract_function_without_signature(self, parser, header_file):
        """Test that extract_function_by_name works without signature for class methods."""
        source = header_file.read_bytes()

        # This uses _find_node_by_qualified_name (singular) internally
        result = parser.extract_function_by_name(source, "addProposal")
        assert result is not None
        assert "addProposal" in result.text
        assert "prevLedger" in result.text

    def test_extract_function_with_qualified_name_no_signature(self, parser, header_file):
        """Test extract_function_by_name with qualified name but no signature."""
        source = header_file.read_bytes()

        result = parser.extract_function_by_name(source, "ShuffleService::addProposal")
        assert result is not None
        assert "addProposal" in result.text


class TestTemplateVsNonTemplateMarkers:
    """Test finding markers in non-template when template exists with same name."""

    @pytest.fixture
    def fixture_file(self):
        return Path("tests/fixtures/overloads.cpp")

    @pytest.fixture
    def extractor(self):
        return CppExtractor()

    def test_marker_in_non_template_overload(self, extractor, fixture_file):
        """Test that we can find marker in non-template when template version exists."""
        # invoke_handler has both template and non-template versions
        # The marker is only in the non-template version
        text, start, end = extractor.extract_function_marker(fixture_file, "invoke_handler", "special-case")

        assert "case 42:" in text
        assert "invoke_handler<PeerImp>" in text
        assert start > 0
        assert end >= start

    def test_find_both_template_and_non_template(self, extractor, fixture_file):
        """Test that _find_all_nodes finds both template and non-template versions."""
        source = fixture_file.read_bytes()
        nodes = extractor.cpp_parser._find_all_nodes_by_qualified_name(
            source, "invoke_handler", ["function_definition"]
        )

        # Should find both versions
        assert len(nodes) == 2

        # One should be template, one not
        node_types = [n.type for n in nodes]
        texts = [n.text.decode("utf8") if n.text else "" for n in nodes]

        # Check we got both versions
        has_template = any("template" in t for t in texts)
        has_non_template = any("switch" in t for t in texts)
        assert has_template, "Should find template version"
        assert has_non_template, "Should find non-template version"
