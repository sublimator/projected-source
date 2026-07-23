"""Tests for the Protobuf extractor and its grammar dependency.

The proto grammar (coder3101/tree-sitter-proto) is installed as a pinned git
dependency and compiled from source at install time, so the loader path gets
its own coverage here alongside the extraction smoke tests.
"""

import tempfile
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

    def test_marker_line_range_excludes_marker_comments(self, extractor):
        """list_symbols must report marker ranges that exclude the //@@ comment lines."""
        proto_source = b"""syntax = "proto3";

//@@start example1
message Foo {
  string name = 1;
}
//@@end example1
"""
        with tempfile.NamedTemporaryFile(suffix=".proto", delete=False) as f:
            f.write(proto_source)
            temp_path = Path(f.name)

        try:
            symbols = extractor.list_symbols(temp_path)
            markers = [s for s in symbols if s["kind"] == "marker"]
            by_name = {m["name"]: m for m in markers}
            assert "example1" in by_name
            # Lines are 1-based, and we want the content between markers.
            # Line 3 is //@@start, line 7 is //@@end, so content is lines 4-6.
            assert by_name["example1"]["line"] == 4
            assert by_name["example1"]["end_line"] == 6
        finally:
            temp_path.unlink()


class TestProtoMarkersIgnoreStrings:
    """Markers come from comment nodes, never from string literal contents."""

    @pytest.fixture
    def extractor(self):
        return ProtoExtractor()

    def test_marker_extraction_with_marker_shaped_strings(self, extractor, tmp_path):
        target = tmp_path / "strings.proto"
        target.write_text(
            'syntax = "proto3";\n'
            "\n"
            "//@@start fields\n"
            "message M {\n"
            '  string a = 1 [(doc) = "//@@end fields"];\n'
            "  string b = 2;\n"
            "}\n"
            "//@@end fields\n"
        )

        text, start, end = extractor.extract_marker(target, "fields")

        assert (start, end) == (4, 7)
        assert "string b = 2;" in text

    def test_message_marker_via_comment_nodes(self, extractor, tmp_path):
        target = tmp_path / "msg_marker.proto"
        target.write_text(
            'syntax = "proto3";\n'
            "\n"
            "message M {\n"
            "  //@@start core\n"
            "  string a = 1;\n"
            "  //@@end core\n"
            "  string b = 2;\n"
            "}\n"
        )

        text, start, end = extractor.extract_message_marker(target, "M", "core")

        assert (start, end) == (5, 5)
        assert text.strip() == "string a = 1;"
