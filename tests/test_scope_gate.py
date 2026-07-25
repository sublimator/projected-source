"""Exit-code contract for the review_scope / --strict gate (N2, N3, N4, N7).

These pin the gate's promise — a --strict pass must mean something was actually
checked — which the round-1 F3 fix got half-right in both directions.
"""

import subprocess

import pytest
from click.testing import CliRunner

from projected_source.cli.render import render


def _git(repo, *args):
    return subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=True).stdout.strip()


@pytest.fixture
def repo(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    r = tmp_path / "repo"
    (r / "src").mkdir(parents=True)
    (r / "vendor").mkdir()
    (r / "docs").mkdir()
    _git(r, "init")
    _git(r, "config", "user.email", "t@t.com")
    _git(r, "config", "user.name", "t")
    return r


def _commit(repo, msg):
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", msg)
    return _git(repo, "rev-parse", "HEAD")


def _run(repo, *args):
    return CliRunner().invoke(render, ["--no-header", "-r", str(repo), *args])


def test_config_only_exclude_that_empties_D_passes_strict(repo):
    """N2: a repo-config exclude emptying D (a vendor-only bump) is legitimate."""
    (repo / "vendor" / "v.cpp").write_text("a\n")
    base = _commit(repo, "base")
    (repo / "vendor" / "v.cpp").write_text("a\nb\n")
    _commit(repo, "vbump")
    (repo / ".projected-source.toml").write_text('[scope]\nexclude = ["vendor/**"]\n')
    (repo / "docs" / "d.md.j2").write_text("plain prose, no scope\n")
    result = _run(repo, "-V", base, "--strict", str(repo / "docs" / "d.md.j2"), str(repo / "docs" / "d.md"))
    assert result.exit_code == 0, result.output   # config exclude must not fail the gate


def test_template_typo_include_fails_strict(repo):
    """N3: a template include glob that matched nothing fails --strict."""
    (repo / "src" / "a.cpp").write_text("int f() {\n  return 0;\n}\n")
    _commit(repo, "base")
    (repo / "src" / "a.cpp").write_text("int f() {\n  int x = 1;\n  return x;\n}\n")
    _commit(repo, "change")
    (repo / "docs" / "d.md.j2").write_text(
        '{% set review_scope = {"base": "HEAD~1", "include": ["src/**", "typooo/**"]} %}\n'
        '{{ audit("src/a.cpp", function="f", reason="all of it") }}\n'
    )
    result = _run(repo, "-V", "auto", "--strict", str(repo / "docs" / "d.md.j2"), str(repo / "docs" / "d.md"))
    assert result.exit_code == 1, result.output   # typooo/** matched nothing


def test_dir_mode_scoped_template_fails_strict(repo):
    """N4: directory mode can't apply a template's review_scope, so a --strict
    run that validated the whole diff instead must not pass green."""
    (repo / "src" / "a.cpp").write_text("int f() {\n  return 0;\n}\n")
    _commit(repo, "base")
    (repo / "src" / "a.cpp").write_text("int f() {\n  int x = 1;\n  return x;\n}\n")
    _commit(repo, "change")
    (repo / "docs" / "d.md.j2").write_text(
        '{% set review_scope = {"base": "HEAD~1", "include": ["src/**"]} %}\n'
        '{{ audit("src/a.cpp", function="f", reason="x") }}\n'
    )
    result = _run(repo, "-V", "auto", "--strict", str(repo / "docs"), str(repo / "docs"))
    assert result.exit_code == 1, result.output


def test_whole_file_audit_not_shown_as_sentinel(repo):
    """N7: a whole-file audit over max_changed_lines shows 'whole-file', not 1-999999."""
    (repo / "src" / "a.cpp").write_text("a\n")
    base = _commit(repo, "base")
    (repo / "src" / "a.cpp").write_text("a\nb\nc\n")
    _commit(repo, "change")
    (repo / ".projected-source.toml").write_text("[audit]\nmax_changed_lines = 1\n")
    (repo / "docs" / "d.md.j2").write_text('{{ audit("src/a.cpp", reason="whole file") }}\n')
    result = _run(repo, "-V", base, str(repo / "docs" / "d.md.j2"), str(repo / "docs" / "d.md"))
    assert "1-999999" not in result.output
    assert "whole-file" in result.output
