"""Tests for the ``ai-guide`` command.

The guide is one big f-string with heavily doubled braces, and its language
list must stay in sync with the extractor registry — both are easy to break
silently, so they get explicit coverage.
"""

from click.testing import CliRunner

from projected_source.cli import cli
from projected_source.cli.ai_guide import _build_supported_languages
from projected_source.languages import EXTRACTORS


def _guide_output() -> str:
    result = CliRunner().invoke(cli, ["ai-guide"])
    assert result.exit_code == 0, result.output
    return result.output


def test_guide_renders():
    """The f-string must not have stray unbalanced braces."""
    output = _guide_output()
    assert output.startswith("# projected-source AI Guide")
    # Doubled braces in the f-string must collapse to single literal braces.
    assert "{{ code(" in output
    assert "{{{{" not in output


def test_every_registered_language_is_listed():
    """Adding an extractor to EXTRACTORS must surface it in the guide."""
    output = _guide_output()
    for cls in set(EXTRACTORS.values()):
        label = cls.__name__.replace("Extractor", "")
        assert label in output, f"{label} missing from ai-guide output"


def test_every_registered_extension_is_listed():
    """Every file extension in the registry appears in the Supported Languages block."""
    languages_block = _build_supported_languages()
    for ext in EXTRACTORS:
        assert ext in languages_block, f"extension {ext} missing from language list"


def test_guide_documents_rust():
    """Rust is a supported language and needs its own usage examples."""
    output = _guide_output()
    assert ".rs" in output
    assert "code('src/node.rs'" in output


def test_guide_documents_enclosure_context_controls():
    """The marker-context default and opt-outs are important authoring contract."""
    output = _guide_output()
    assert "--enclosure-context N" in output
    assert "--enclosure-context 0" in output
    assert "enclosure_context=0" in output
    assert "C/C++ extractor-backed marker extracts" in output


def test_guide_documents_include_body():
    """Embedding standalone walkthroughs should use include_body(), not include()."""
    output = _guide_output()
    assert "include_body('walkthrough.md.j2')" in output
    assert "frontmatter and projected-source metadata headers" in output
    assert "caller variables" in output
