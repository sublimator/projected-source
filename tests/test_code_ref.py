"""Tests for ref= support using this repo's own git history as fixtures.

Uses known commits from the projected-source repo itself.
These tests verify real git ref extraction against actual history.
"""

import subprocess
from pathlib import Path

import pytest

from projected_source.core.renderer import TemplateRenderer

REPO_ROOT = Path(__file__).resolve().parent.parent

# Known commits from this repo's history
# ce32faa: before header/code_root/typescript features were added
# 0ccc114: after typescript was added
# ee47d91: added {% code_root %} (before rename to code_context)
COMMIT_BEFORE_TS = "0ccc114"  # has TS
COMMIT_BEFORE_CODE_ROOT = "ce32faa"  # no code_root, no TS


def _ref_exists(ref: str) -> bool:
    """Check if a git ref is valid in the repo."""
    result = subprocess.run(
        ["git", "rev-parse", "--verify", ref],
        cwd=REPO_ROOT,
        capture_output=True,
    )
    return result.returncode == 0


@pytest.fixture(autouse=True)
def skip_if_shallow():
    """Skip tests if the repo is shallow (e.g. CI with shallow clone)."""
    if not _ref_exists(COMMIT_BEFORE_CODE_ROOT):
        pytest.skip(f"Commit {COMMIT_BEFORE_CODE_ROOT} not available (shallow clone?)")


class TestRefExtractFromHistory:
    """Extract code from known historical commits in this repo."""

    def test_extract_class_from_old_commit(self, tmp_path):
        """Extract ExtractionResult from a known old commit."""
        template = tmp_path / "doc.md.j2"
        template.write_text(
            "{%% code_context ref='%s' %%}\n"
            "{{ code('projected_source/languages/extraction_result.py', struct='ExtractionResult', github=False) }}\n"
            "{%% endcode_context %%}\n" % COMMIT_BEFORE_CODE_ROOT
        )

        renderer = TemplateRenderer(template_dir=tmp_path, repo_path=REPO_ROOT)
        result = renderer.render_template("doc.md.j2")
        assert "class ExtractionResult:" in result
        assert "text: str" in result
        assert "start_line: int" in result

    def test_extract_function_from_old_commit(self, tmp_path):
        """Extract get_extractor from before TypeScript was added."""
        template = tmp_path / "doc.md.j2"
        template.write_text(
            "{{ code('projected_source/languages/__init__.py', "
            "function='get_extractor', github=False, ref='%s') }}\n" % COMMIT_BEFORE_CODE_ROOT
        )

        renderer = TemplateRenderer(template_dir=tmp_path, repo_path=REPO_ROOT)
        result = renderer.render_template("doc.md.j2")
        assert "def get_extractor" in result
        # Old version didn't have TypeScript special case
        assert "TypeScriptExtractor" not in result

    def test_extract_var_from_old_commit(self, tmp_path):
        """Extract EXTRACTORS dict from before TypeScript was added."""
        template = tmp_path / "doc.md.j2"
        template.write_text(
            "{{ code('projected_source/languages/__init__.py', "
            "var='EXTRACTORS', github=False, ref='%s') }}\n" % COMMIT_BEFORE_CODE_ROOT
        )

        renderer = TemplateRenderer(template_dir=tmp_path, repo_path=REPO_ROOT)
        result = renderer.render_template("doc.md.j2")
        assert "EXTRACTORS" in result
        assert '".cpp"' in result or "'.cpp'" in result
        # No .ts in the old version
        assert ".ts" not in result

    def test_extract_from_commit_with_ts(self, tmp_path):
        """Extract EXTRACTORS from the commit that added TypeScript."""
        template = tmp_path / "doc.md.j2"
        template.write_text(
            "{{ code('projected_source/languages/__init__.py', "
            "var='EXTRACTORS', github=False, ref='%s') }}\n" % COMMIT_BEFORE_TS
        )

        renderer = TemplateRenderer(template_dir=tmp_path, repo_path=REPO_ROOT)
        result = renderer.render_template("doc.md.j2")
        assert "TypeScriptExtractor" in result
        assert '".ts"' in result or "'.ts'" in result

    def test_compare_two_commits(self, tmp_path):
        """Extract same symbol from two different commits to compare."""
        template = tmp_path / "doc.md.j2"
        template.write_text(
            "## Before TypeScript\n\n"
            "{{ code('projected_source/languages/__init__.py', "
            "var='EXTRACTORS', github=False, ref='%s') }}\n\n"
            "## After TypeScript\n\n"
            "{{ code('projected_source/languages/__init__.py', "
            "var='EXTRACTORS', github=False, ref='%s') }}\n" % (COMMIT_BEFORE_CODE_ROOT, COMMIT_BEFORE_TS)
        )

        renderer = TemplateRenderer(template_dir=tmp_path, repo_path=REPO_ROOT)
        result = renderer.render_template("doc.md.j2")
        # Both sections rendered
        assert "## Before TypeScript" in result
        assert "## After TypeScript" in result
        # Count EXTRACTORS appearances — should appear twice
        assert result.count("EXTRACTORS") >= 2

    def test_ref_header_shows_commit(self, tmp_path):
        """Header should show @ ref suffix."""
        template = tmp_path / "doc.md.j2"
        template.write_text(
            "{{ code('projected_source/languages/extraction_result.py', "
            "struct='ExtractionResult', github=False, ref='%s') }}\n" % COMMIT_BEFORE_CODE_ROOT
        )

        renderer = TemplateRenderer(template_dir=tmp_path, repo_path=REPO_ROOT)
        result = renderer.render_template("doc.md.j2")
        assert f"@ {COMMIT_BEFORE_CODE_ROOT}" in result

    def test_ref_with_root(self, tmp_path):
        """Combine root= and ref= in code_context block."""
        template = tmp_path / "doc.md.j2"
        template.write_text(
            "{%% code_context root='projected_source/languages', ref='%s' %%}\n"
            "{{ code('extraction_result.py', struct='ExtractionResult', github=False) }}\n"
            "{%% endcode_context %%}\n" % COMMIT_BEFORE_CODE_ROOT
        )

        renderer = TemplateRenderer(template_dir=tmp_path, repo_path=REPO_ROOT)
        result = renderer.render_template("doc.md.j2")
        assert "class ExtractionResult:" in result

    def test_ref_with_tag_or_branch_name(self, tmp_path):
        """Use HEAD as a ref (always valid)."""
        template = tmp_path / "doc.md.j2"
        template.write_text(
            "{{ code('projected_source/languages/extraction_result.py', "
            "struct='ExtractionResult', github=False, ref='HEAD') }}\n"
        )

        renderer = TemplateRenderer(template_dir=tmp_path, repo_path=REPO_ROOT)
        result = renderer.render_template("doc.md.j2")
        assert "class ExtractionResult:" in result

    def test_invalid_ref_gives_error(self, tmp_path):
        """Bad ref should produce an error, not crash."""
        template = tmp_path / "doc.md.j2"
        template.write_text(
            "{{ code('projected_source/languages/extraction_result.py', "
            "struct='ExtractionResult', github=False, ref='nonexistent-ref-abc123') }}\n"
        )

        renderer = TemplateRenderer(template_dir=tmp_path, repo_path=REPO_ROOT)
        result = renderer.render_template("doc.md.j2")
        assert "ERROR" in result

    def test_ref_file_that_no_longer_exists(self, tmp_path):
        """Extract from a file that existed at a ref but was later deleted."""
        # test_code_root.py was deleted and replaced with test_code_context.py
        # It existed at ee47d91
        if not _ref_exists("ee47d91"):
            pytest.skip("Commit ee47d91 not available")

        template = tmp_path / "doc.md.j2"
        template.write_text(
            "{{ code('tests/test_code_root.py', "
            "function='TestCodeRoot.test_code_root_block', github=False, ref='ee47d91') }}\n"
        )

        renderer = TemplateRenderer(template_dir=tmp_path, repo_path=REPO_ROOT)
        result = renderer.render_template("doc.md.j2")
        assert "def test_code_root_block" in result

    def test_set_code_context_with_ref(self, tmp_path):
        """set_code_context(ref=...) sets ref globally."""
        template = tmp_path / "doc.md.j2"
        template.write_text(
            "{{ set_code_context(ref='%s') }}\n"
            "{{ code('projected_source/languages/__init__.py', "
            "var='EXTRACTORS', github=False) }}\n"
            "{{ set_code_context(ref='') }}\n" % COMMIT_BEFORE_CODE_ROOT
        )

        renderer = TemplateRenderer(template_dir=tmp_path, repo_path=REPO_ROOT)
        result = renderer.render_template("doc.md.j2")
        assert "EXTRACTORS" in result
        assert "TypeScriptExtractor" not in result

    def test_no_changes_tracking_with_ref(self, tmp_path):
        """ChangesSet should NOT be affected by ref extractions."""
        from projected_source.core.changes_set import ChangesSet

        changes = ChangesSet()
        # Add a fake region
        changes.add(REPO_ROOT / "projected_source/languages/__init__.py", 1, 50)

        template = tmp_path / "doc.md.j2"
        template.write_text(
            "{{ code('projected_source/languages/__init__.py', "
            "var='EXTRACTORS', github=False, ref='%s') }}\n" % COMMIT_BEFORE_CODE_ROOT
        )

        renderer = TemplateRenderer(template_dir=tmp_path, repo_path=REPO_ROOT, changes_set=changes)
        renderer.render_template("doc.md.j2")
        # Changes should NOT be subtracted — ref extraction doesn't cover HEAD changes
        assert not changes.is_complete()
