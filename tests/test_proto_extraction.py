"""Tests for the Protobuf extractor and its grammar dependency.

The proto grammar (coder3101/tree-sitter-proto) is installed as a pinned git
dependency and compiled from source at install time, so the loader path gets
its own coverage here alongside the extraction smoke tests.
"""

import warnings
from pathlib import Path

import pytest

from projected_source.languages.proto import ProtoExtractor

FIXTURE = Path(__file__).parent / "fixtures" / "ripple.proto"


class TestProtoGrammarDependency:
    """The tree-sitter-proto package must load cleanly on any platform."""

    def test_grammar_package_is_importable(self):
        """The git-installed grammar exposes the standard tree-sitter binding."""
        import tree_sitter_proto

        capsule = tree_sitter_proto.language()
        assert type(capsule).__name__ == "PyCapsule"

    def test_extractor_construction_is_warning_free(self):
        """Constructing the extractor loads the grammar without deprecation noise."""
        with warnings.catch_warnings():
            warnings.simplefilter("error", DeprecationWarning)
            ProtoExtractor()


class TestProtoExtraction:
    """Smoke coverage for message/enum extraction against a real .proto file."""

    @pytest.fixture
    def extractor(self):
        return ProtoExtractor()

    def test_extract_enum(self, extractor):
        text, start, end = extractor.extract_enum(FIXTURE, "MessageType")
        assert text.startswith("enum MessageType")
        assert "mtMANIFESTS" in text
        assert start < end

    def test_extract_message(self, extractor):
        text, start, end = extractor.extract_message(FIXTURE, "TMManifest")
        assert text.startswith("message TMManifest")
        assert start < end

    def test_extract_missing_message_raises(self, extractor):
        with pytest.raises(ValueError, match="NoSuchMessage"):
            extractor.extract_message(FIXTURE, "NoSuchMessage")

    def test_extract_missing_enum_raises(self, extractor):
        with pytest.raises(ValueError, match="NoSuchEnum"):
            extractor.extract_enum(FIXTURE, "NoSuchEnum")

    def test_parses_proto2_fixture_without_errors(self, extractor):
        """ripple.proto uses proto2 syntax — the grammar must handle it."""
        tree = extractor._parser.parse(FIXTURE.read_bytes())
        assert not tree.root_node.has_error
