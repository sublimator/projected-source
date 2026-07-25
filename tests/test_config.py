"""Tests for layered configuration (.projected-source.toml + user config)."""

import subprocess
import textwrap
from pathlib import Path

import pytest
from click.testing import CliRunner

from projected_source.cli.render import render
from projected_source.core.config import load_config


def _write(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(text))


# --------------------------------------------------------------- loader

def test_defaults_when_no_config(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))  # empty
    cfg = load_config(tmp_path)
    assert cfg.min_density is None
    assert cfg.max_audit_ratio is None
    assert cfg.max_audit_changed_lines is None
    assert cfg.scope_exclude == []


def test_repo_config_found_walking_up(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    _write(
        tmp_path / ".projected-source.toml",
        """
        [validation]
        min_density = 0.4
        [audit]
        max_changed_lines = 25
        [scope]
        exclude = ["**/vendor/**"]
        """,
    )
    sub = tmp_path / "a" / "b"
    sub.mkdir(parents=True)
    cfg = load_config(sub)
    assert cfg.min_density == 0.4
    assert cfg.max_audit_changed_lines == 25
    assert cfg.scope_exclude == ["**/vendor/**"]


def test_repo_overrides_user_but_keeps_unshadowed_keys(tmp_path, monkeypatch):
    xdg = tmp_path / "xdg"
    monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg))
    _write(
        xdg / "projected-source" / "config.toml",
        """
        [validation]
        min_density = 0.2
        max_audit_ratio = 0.5
        """,
    )
    _write(
        tmp_path / ".projected-source.toml",
        """
        [validation]
        min_density = 0.6
        """,
    )
    cfg = load_config(tmp_path)
    assert cfg.min_density == 0.6        # repo wins
    assert cfg.max_audit_ratio == 0.5    # user value survives (repo did not touch it)


def test_unknown_sections_preserved(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    _write(tmp_path / ".projected-source.toml", '[experimental]\nwidget = "on"\n')
    cfg = load_config(tmp_path)
    assert cfg.get("experimental", "widget") == "on"


# -------------------------------------------------- policy wiring (CLI)

def _git(repo, *args):
    return subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=True).stdout.strip()


def test_max_changed_lines_warns_in_report(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "t@t.com")
    _git(repo, "config", "user.name", "t")
    (repo / "f.cpp").write_text("int f(){\n  return 0;\n}\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "base")
    base = _git(repo, "rev-parse", "HEAD")
    # a big change, all acknowledged by one audit()
    body = "int f(){\n" + "".join(f"  int x{i} = {i};\n" for i in range(10)) + "  return 0;\n}\n"
    (repo / "f.cpp").write_text(body)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "big")
    _write(repo / ".projected-source.toml", "[audit]\nmax_changed_lines = 3\n")
    (repo / "doc.md.j2").write_text('{{ audit("f.cpp", function="f", reason="all trivial") }}\n')

    result = CliRunner().invoke(
        render, ["--no-header", "-V", base, "-r", str(repo), str(repo / "doc.md.j2"), str(tmp_path / "out.md")]
    )
    assert result.exit_code == 0, result.output
    assert "max_changed_lines" in result.output          # policy warning surfaced
    assert "too much per audit" in result.output


def test_non_numeric_config_degrades_not_crashes(tmp_path, monkeypatch):
    """A malformed numeric knob is logged and treated as absent, never a
    traceback that aborts the render (config robustness)."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    _write(
        tmp_path / ".projected-source.toml",
        """
        [validation]
        min_density = "half"
        max_code_lines = "twenty"
        min_density_span = "lots"
        """,
    )
    cfg = load_config(tmp_path)
    assert cfg.min_density is None        # not a crash
    assert cfg.max_code_lines is None
    assert cfg.min_density_span == 0      # default floor
