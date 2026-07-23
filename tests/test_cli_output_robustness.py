"""CLI output robustness regressions.

Source lines, signatures, and error text are arbitrary text; printing them
through Rich must not interpret them as markup (silently eating
`[bracketed]` content, or crashing on dangling `[/]` tags). The -V
uncovered-region report must also work under --commit, whose temporary
worktree disappears when its context exits.
"""

import subprocess
from pathlib import Path

import pytest
from click.testing import CliRunner

from projected_source.cli import cli


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, capture_output=True, check=True)


@pytest.fixture
def repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "test@test.com")
    _git(repo, "config", "user.name", "Test")
    return repo


def _seed_validation_repo(repo: Path, undocumented_line: str) -> None:
    """Base commit documents a(); second commit adds an uncovered b()."""
    (repo / "code.py").write_text("def a():\n    return 1\n")
    (repo / "doc.md.j2").write_text("{{ code('code.py', function='a', github=False) }}\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "base")
    (repo / "code.py").write_text(
        f"def a():\n    return 1\n\ndef b():\n    {undocumented_line}\n"
    )
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "add b")


class TestValidationDiagnosticsMarkup:
    def test_bracketed_source_lines_print_verbatim(self, repo):
        _seed_validation_repo(repo, "return arr[i] + fix[notarealtag]")

        result = CliRunner().invoke(
            cli,
            ["render", str(repo / "doc.md.j2"), "-", "--no-header", "-V", "HEAD~1", "-r", str(repo)],
        )

        assert result.exit_code == 0, result.output
        assert "arr[i] + fix[notarealtag]" in result.output

    def test_dangling_close_tag_does_not_crash(self, repo):
        _seed_validation_repo(repo, 's = "close[/]here"')

        result = CliRunner().invoke(
            cli,
            ["render", str(repo / "doc.md.j2"), "-", "--no-header", "-V", "HEAD~1", "-r", str(repo)],
        )

        assert result.exit_code == 0, result.output
        assert result.exception is None
        assert 'close[/]here' in result.output


class TestValidationUnderCommit:
    def test_uncovered_report_reads_worktree_before_cleanup(self, repo):
        _seed_validation_repo(repo, "return 2")
        _git(repo, "tag", "v1")
        _git(repo, "tag", "v0", "HEAD~1")

        result = CliRunner().invoke(
            cli,
            [
                "render",
                str(repo / "doc.md.j2"),
                "-",
                "--no-header",
                "--commit",
                "v1",
                "-V",
                "v0",
                "-r",
                str(repo),
            ],
        )

        assert result.exit_code == 0, result.output
        assert "Could not read file" not in result.output
        # File header is worktree-relative, and the uncovered source shows.
        assert "━━━ code.py ━━━" in result.output
        assert "def b():" in result.output


class TestListFunctionsRobustness:
    def test_signature_brackets_survive(self, tmp_path):
        source = tmp_path / "ovl.cpp"
        source.write_text(
            "void h(int x) {}\n"
            "void h(double y) {}\n"
            "void h(char buf[size]) {}\n"
        )

        result = CliRunner().invoke(cli, ["list-functions", str(source)])

        assert result.exit_code == 0, result.output
        assert "(char buf[size])" in result.output

    def test_non_utf8_file_fails_cleanly(self, tmp_path):
        source = tmp_path / "bad.py"
        source.write_bytes(b"def ok():\n    pass\n# \xff bad\n")

        result = CliRunner().invoke(cli, ["list-functions", str(source)])

        assert result.exit_code == 1
        assert "Could not read symbols" in result.output
        assert not isinstance(result.exception, UnicodeDecodeError)
