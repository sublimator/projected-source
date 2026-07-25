"""Tests for the audit-stubs CLI verb.

Renders a template with -V, then prints paste-ready `{{ audit(...) }}` lines for
the residual (changed lines nothing narrated/audited/ignored) — the correct
post-render leftover the audit_remaining() template directive could not compute.
"""

import re
import subprocess

import pytest
from click.testing import CliRunner

from projected_source.cli.audit_stubs import audit_stubs
from projected_source.cli.render import render


def _git(repo, *args):
    return subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=True).stdout.strip()


@pytest.fixture
def repo(tmp_path):
    repo = tmp_path / "repo"
    (repo / "docs").mkdir(parents=True)
    _git(repo, "init")
    _git(repo, "config", "user.email", "t@t.com")
    _git(repo, "config", "user.name", "t")
    return repo


def _two_func_change(repo):
    (repo / "f.cpp").write_text("int foo(){\n  return 0;\n}\nint bar(){\n  return 0;\n}\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "base")
    base = _git(repo, "rev-parse", "HEAD")
    (repo / "f.cpp").write_text(
        "int foo(){\n  int a = 1;\n  return a;\n}\nint bar(){\n  int b = 2;\n  return b;\n}\n"
    )
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "change")
    return base


def _run(repo, template_body, base):
    (repo / "docs" / "r.md.j2").write_text(template_body)
    return CliRunner().invoke(
        audit_stubs, ["-V", base, "-r", str(repo), str(repo / "docs" / "r.md.j2")]
    )


def _stub_line_ranges(stdout):
    return [(int(a), int(b)) for a, b in re.findall(r"lines=\((\d+),\s*(\d+)\)", stdout)]


def test_stubs_only_the_residual(repo):
    base = _two_func_change(repo)
    # narrate foo; bar is the residual
    result = _run(repo, '{{ code("f.cpp", function="foo") }}\n', base)
    assert result.exit_code == 0, result.output
    assert "{# audit stubs" in result.stdout
    ranges = _stub_line_ranges(result.stdout)
    assert len(ranges) == 1                      # exactly one uncovered region (bar)
    (start, end) = ranges[0]
    assert start >= 4                            # bar's half of the file, not foo's
    assert 'reason=""' in result.stdout


def test_nothing_to_stub_when_fully_covered(repo):
    base = _two_func_change(repo)
    result = _run(repo, '{{ ignore_changes("f.cpp") }}\n', base)   # whole-file ignore
    assert result.exit_code == 0
    assert _stub_line_ranges(result.stdout) == []
    assert "No uncovered changes" in result.stderr


def test_all_changes_stubbed_when_nothing_narrated(repo):
    base = _two_func_change(repo)
    result = _run(repo, "# empty doc, nothing claimed\n", base)
    assert result.exit_code == 0
    ranges = _stub_line_ranges(result.stdout)
    assert ranges                                # foo and bar regions both stubbed
    assert all('audit("f.cpp"' in line for line in result.stdout.splitlines() if "audit(" in line)


def test_stub_round_trip_in_dirty_tree(repo):
    """A stub pasted back covers its region even in a dirty tree — committed=True
    stops audit() re-mapping the already-committed coordinates (F4)."""
    base = _two_func_change(repo)
    # Dirty the tree: uncommitted lines above the functions shift working-tree
    # line numbers away from the committed (D) ones.
    (repo / "f.cpp").write_text("// uncommitted\n// lines\n" + (repo / "f.cpp").read_text())

    result = _run(repo, '{{ code("f.cpp", function="foo") }}\n', base)  # narrate foo, stub bar
    stubs = [ln for ln in result.stdout.splitlines() if ln.startswith("{{ audit")]
    assert stubs and "committed=True" in stubs[0]

    doc2 = (
        '{{ code("f.cpp", function="foo") }}\n'
        + "\n".join(ln.replace('reason=""', 'reason="boilerplate"') for ln in stubs)
        + "\n"
    )
    (repo / "docs" / "r2.md.j2").write_text(doc2)
    result2 = CliRunner().invoke(
        render,
        ["--no-header", "-V", base, "--strict", "-r", str(repo),
         str(repo / "docs" / "r2.md.j2"), str(repo / "docs" / "r2.md")],
    )
    assert result2.exit_code == 0, result2.output   # residual is fully claimed


def test_stdout_is_paste_ready(repo):
    """Only Jinja (comment + audit calls) on stdout; status goes to stderr."""
    base = _two_func_change(repo)
    result = _run(repo, '{{ code("f.cpp", function="foo") }}\n', base)
    for line in result.stdout.splitlines():
        if line.strip():
            assert line.startswith("{{") or line.startswith("{#"), f"non-paste-ready: {line!r}"
