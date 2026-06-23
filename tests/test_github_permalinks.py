"""
Regression tests for GitHubIntegration permalink/dirty-detection bugs.

Covers two specific issues:
  1. Untracked files were not detected as dirty (because `git diff` ignores them),
     so permalinks pointed at HEAD (404) without an "uncommitted" marker.
  2. When display_committed_lines=False, the display label collapsed to a single
     line whenever the *committed* range collapsed — even though the *working
     copy* range spanned multiple lines.
"""

import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

from projected_source.core.github import GitHubIntegration


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=repo, capture_output=True, check=True)


@pytest.fixture
def repo_with_remote():
    """A temp git repo with a fake github.com remote and one committed file."""
    temp_dir = tempfile.mkdtemp()
    repo_path = Path(temp_dir)
    try:
        _git(repo_path, "init")
        _git(repo_path, "config", "user.email", "test@test.com")
        _git(repo_path, "config", "user.name", "Test")
        _git(repo_path, "remote", "add", "origin", "git@github.com:testuser/testrepo.git")

        # Seed one committed file so HEAD exists.
        (repo_path / "tracked.txt").write_text("seed\n")
        _git(repo_path, "add", "tracked.txt")
        _git(repo_path, "commit", "-m", "seed")

        yield repo_path
    finally:
        shutil.rmtree(temp_dir)


class TestUntrackedFileDirtyDetection:
    """Finding 1: untracked-but-existing files must be reported dirty."""

    def test_untracked_file_is_dirty(self, repo_with_remote):
        untracked = repo_with_remote / "new_file.py"
        untracked.write_text("print('hello')\n")

        github = GitHubIntegration(repo_with_remote)
        assert github.is_file_dirty(untracked) is True

    def test_nonexistent_untracked_file_is_not_dirty(self, repo_with_remote):
        """Sanity: a path that doesn't exist at all is not dirty."""
        ghost = repo_with_remote / "does_not_exist.py"
        github = GitHubIntegration(repo_with_remote)
        assert github.is_file_dirty(ghost) is False

    def test_untracked_file_permalink_has_uncommitted_marker(self, repo_with_remote):
        """get_permalink must surface the *(uncommitted)* suffix for untracked files."""
        untracked = repo_with_remote / "new_file.py"
        untracked.write_text("a\nb\nc\n")

        github = GitHubIntegration(repo_with_remote)
        permalink = github.get_permalink(untracked, start_line=1, end_line=2)

        assert "*(uncommitted)*" in permalink, (
            f"Expected uncommitted marker in untracked-file permalink, got: {permalink}"
        )


class TestDisplayBranchCollapse:
    """Finding 2: display range must follow display line numbers, not committed ones."""

    def test_display_spans_range_when_committed_collapses(self, repo_with_remote):
        """
        Working copy lines 1-3 are all newly added (no committed counterpart),
        so map_to_committed_line walks each back to the same fallback line.
        With display_committed_lines=False the displayed label must still show
        the working-copy range "1-3", not collapse to "1".
        """
        new_file = repo_with_remote / "added.py"
        # The file is tracked-but-modified — start from an empty committed
        # version and add several lines so all working-copy lines are "added".
        new_file.write_text("")
        _git(repo_with_remote, "add", "added.py")
        _git(repo_with_remote, "commit", "-m", "add empty")
        new_file.write_text("line1\nline2\nline3\n")

        github = GitHubIntegration(repo_with_remote)
        assert github.is_file_dirty(new_file)

        # All three working-copy lines should map to the same committed line
        # (the fallback for added lines with no prior context).
        c1 = github.map_to_committed_line(new_file, 1)
        c3 = github.map_to_committed_line(new_file, 3)
        assert c1 == c3, (
            f"Test precondition: expected lines 1 and 3 to collapse to same committed line, got {c1} vs {c3}"
        )

        permalink = github.get_permalink(
            new_file, start_line=1, end_line=3, display_committed_lines=False
        )

        # Display must show the working-copy range, not collapse to a single line.
        assert "added.py:1-3" in permalink, (
            f"Expected display 'added.py:1-3' when display_committed_lines=False, got: {permalink}"
        )
