"""
Regression tests for projected_source.cli.find_markers.

Covers FINDING 3: --remove must preserve original line endings rather than
collapsing CRLF -> LF when rewriting a file.
"""

import subprocess

from click.testing import CliRunner

from projected_source.cli import cli


def _init_repo(path):
    """Create a minimal git repo at ``path`` with an initial empty commit."""
    env = {
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@example.com",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@example.com",
        "PATH": __import__("os").environ.get("PATH", ""),
    }

    def git(*args):
        subprocess.run(["git", *args], cwd=path, check=True, env=env, capture_output=True)

    git("init", "-q")
    git("config", "commit.gpgsign", "false")
    (path / ".gitkeep").write_text("")
    git("add", ".gitkeep")
    git("commit", "-q", "-m", "init")
    return git


def test_remove_preserves_crlf_line_endings(tmp_path):
    """Files written with CRLF must still have CRLF after --remove."""
    git = _init_repo(tmp_path)

    # Initial commit baseline so the file shows up in diff vs HEAD.
    baseline = tmp_path / "baseline.cpp"
    baseline.write_text("// baseline\n")
    git("add", "baseline.cpp")
    git("commit", "-q", "-m", "baseline")

    # Capture base before modification.
    base_rev = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=tmp_path, check=True, capture_output=True, text=True
    ).stdout.strip()

    crlf_file = tmp_path / "with_crlf.cpp"
    content = (
        "int main() {\r\n"
        "    //@@start foo\r\n"
        "    return 0;\r\n"
        "    //@@end foo\r\n"
        "}\r\n"
    )
    crlf_file.write_bytes(content.encode("utf-8"))
    git("add", "with_crlf.cpp")
    git("commit", "-q", "-m", "add crlf")

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "find-markers",
            "--since",
            base_rev,
            "--remove",
            "--repo-path",
            str(tmp_path),
        ],
    )

    assert result.exit_code == 0, result.output

    rewritten = crlf_file.read_bytes()
    # Markers must be gone.
    assert b"//@@start" not in rewritten
    assert b"//@@end" not in rewritten
    # CRLF endings on the surviving lines must be preserved.
    assert b"int main() {\r\n" in rewritten
    assert b"    return 0;\r\n" in rewritten
    assert b"}\r\n" in rewritten
    # And no bare LF on those lines (i.e. \n not preceded by \r).
    # Build a set of all bare-LF positions; none should exist.
    for i, byte in enumerate(rewritten):
        if byte == 0x0A:  # LF
            assert i > 0 and rewritten[i - 1] == 0x0D, (
                f"bare LF at offset {i}: surrounding={rewritten[max(0, i - 4): i + 2]!r}"
            )


def test_remove_preserves_lf_line_endings(tmp_path):
    """Sanity: LF files stay LF after --remove."""
    git = _init_repo(tmp_path)

    baseline = tmp_path / "baseline.cpp"
    baseline.write_text("// baseline\n")
    git("add", "baseline.cpp")
    git("commit", "-q", "-m", "baseline")

    base_rev = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=tmp_path, check=True, capture_output=True, text=True
    ).stdout.strip()

    lf_file = tmp_path / "lf.cpp"
    content = "int main() {\n    //@@start bar\n    return 0;\n    //@@end bar\n}\n"
    lf_file.write_bytes(content.encode("utf-8"))
    git("add", "lf.cpp")
    git("commit", "-q", "-m", "add lf")

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "find-markers",
            "--since",
            base_rev,
            "--remove",
            "--repo-path",
            str(lf_file.parent),
        ],
    )

    assert result.exit_code == 0, result.output
    rewritten = lf_file.read_bytes()
    assert b"//@@" not in rewritten
    assert b"\r\n" not in rewritten
    assert rewritten.endswith(b"\n")
