"""Tests for `projected-source check` — render validation + staleness detection.

Motivating incident (2026-07-11/12, xahaud): renaming //@@ markers silently
broke three templates; nothing noticed until a later render failed. `check`
exists so a whole tree of .md.j2 files can be validated recursively without
rewriting any rendered output.
"""

from click.testing import CliRunner

from projected_source.cli.check import _normalize, check

HEADER = (
    "<!--\n"
    "rendered_from: doc.md.j2\n"
    "rendered_at: 2026-07-12T00:00:00Z\n"
    "branch: some-branch\n"
    "commit: abc1234\n"
    "commit_message: some subject\n"
    "-->\n"
    "\n---\n"
    "\n<sub>Last updated: 2026-07-12 | branch: some-branch | commit: abc1234 (some subject)</sub>\n"
    "\n---\n"
)


def test_normalize_strips_header_and_keeps_frontmatter():
    body = "# Title\n\ncontent\n"
    frontmatter = "---\ntitle: x\n---\n"

    assert _normalize(HEADER + "\n" + body) == body.rstrip("\n")
    assert (
        _normalize(frontmatter + "\n" + HEADER + "\n" + body)
        == (frontmatter + body).rstrip("\n")
    )
    # Different volatile values normalize identically.
    other = HEADER.replace("abc1234", "def5678").replace(
        "2026-07-12", "2026-08-01"
    )
    assert _normalize(HEADER + "\n" + body) == _normalize(other + "\n" + body)


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def test_check_statuses_recursive(tmp_path):
    docs = tmp_path / "docs"

    # ok: rendered matches modulo the volatile header
    _write(docs / "good.md.j2", "hello {{ 1 + 1 }}\n")
    _write(docs / "good.md", HEADER + "\nhello 2\n")

    # stale: committed rendering differs in content (nested — recursion check)
    _write(docs / "nested/deep/stale.md.j2", "value {{ 2 + 2 }}\n")
    _write(docs / "nested/deep/stale.md", HEADER + "\nvalue 3\n")

    # broken: template no longer renders
    _write(docs / "broken.md.j2", "{{ no_such_function() }}\n")
    _write(docs / "broken.md", "whatever\n")

    # unrendered: template with no committed rendering
    _write(docs / "unrendered.md.j2", "orphan\n")

    # degraded: renders "successfully" but with an embedded extraction error
    _write(docs / "degraded.md.j2", "{{ code('no/such/file.cpp') }}\n")
    _write(docs / "degraded.md", "old content\n")

    runner = CliRunner()

    result = runner.invoke(check, [str(docs), "-r", str(tmp_path), "-j", "4"])
    assert "1 ok, 1 stale, 1 unrendered, 2 broken" in result.output
    assert "BROKEN" in result.output and "broken.md.j2" in result.output
    assert "degraded.md.j2" in result.output
    # stale files are counted but not listed by default
    assert "stale.md.j2" not in result.output
    assert result.exit_code == 1  # broken present

    # --show-stale lists them
    result = runner.invoke(
        check, [str(docs), "-r", str(tmp_path), "--show-stale"]
    )
    assert "stale.md.j2" in result.output

    # Without the broken templates, default mode passes despite stale/unrendered.
    (docs / "broken.md.j2").unlink()
    (docs / "degraded.md.j2").unlink()
    (docs / "degraded.md").unlink()
    result = runner.invoke(check, [str(docs), "-r", str(tmp_path)])
    assert result.exit_code == 0
    assert "1 ok, 1 stale, 1 unrendered, 0 broken" in result.output

    # --strict makes stale/unrendered fatal (and lists stale).
    result = runner.invoke(check, [str(docs), "-r", str(tmp_path), "--strict"])
    assert result.exit_code == 1
    assert "stale.md.j2" in result.output


def test_check_single_file(tmp_path):
    template = tmp_path / "one.md.j2"
    _write(template, "x {{ 40 + 2 }}\n")
    _write(tmp_path / "one.md", HEADER + "\nx 42\n")

    result = CliRunner().invoke(check, [str(template), "-r", str(tmp_path)])
    assert result.exit_code == 0
    assert "1 ok, 0 stale, 0 unrendered, 0 broken" in result.output
