"""Tests for `projected-source check` — render validation + staleness detection.

Motivating incident (2026-07-11/12, xahaud): renaming //@@ markers silently
broke three templates; nothing noticed until a later render failed. `check`
exists so a whole tree of .md.j2 files can be validated recursively without
rewriting any rendered output.
"""

from click.testing import CliRunner

from projected_source.cli.check import _normalize, check
from projected_source.core.renderer import TemplateRenderer

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


def test_normalize_ignores_leading_blank_lines_from_no_output_statements():
    """A document opening with no-output statements is not stale.

    {{ ignore_changes(...) }} at the top of a template renders to a blank line.
    The committed document keeps those blanks tucked behind the metadata header,
    a fresh render carries them at the front. Normalizing only the committed
    side made every such document — including this project's own overview —
    report stale on every run.
    """
    body = "# Title\n\ncontent\n"
    fresh = "\n\n\n" + body  # three ignore_changes() calls rendered to nothing

    assert _normalize(fresh) == _normalize(HEADER + "\n" + body)


def test_normalize_ignores_permalink_commit_churn():
    """Re-pinned permalinks are not staleness.

    Permalinks pin to HEAD at render time, so every commit rewrites every
    permalink in every document. Counting that as a content change makes a
    document stale the moment it is committed — and re-rendering only re-pins
    it to the next commit, so it never converges. The pre-push hook has always
    normalized these away; check agrees.
    """
    link = "📍 [`a.py:1-2`](https://github.com/o/r/blob/{}/a.py#L1-L2)\n"
    old = HEADER + "\n" + link.format("5d71911a86153a2016334c48ca43fff7cab3d41f")
    new = HEADER + "\n" + link.format("2245518a7c26223597cb8c9ed9d6b4c203dde35e")

    assert _normalize(old) == _normalize(new)


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


# Quoting error-handling code is not an error.
#
# check used to decide a render was broken by scanning the output for
# "❌ **ERROR**:". projected-source documents its own renderer, whose source is
# full of `return "❌ **ERROR**: ..."` — so the extracted code tripped the
# detector and check declared this project's own docs broken. Failures are now
# reported structurally by render_result(); nothing scans the text.
QUOTED_ERROR_SOURCE = 'def handler():\n    return "❌ **ERROR**: not supported"\n'


def test_quoted_error_source_is_not_broken(tmp_path):
    docs = tmp_path / "docs"
    _write(tmp_path / "src.py", QUOTED_ERROR_SOURCE)
    _write(docs / "quotes.md.j2", "{{ code('src.py', function='handler', github=False) }}\n")

    result = CliRunner().invoke(check, [str(docs / "quotes.md.j2"), "-r", str(tmp_path)])

    assert result.exit_code == 0
    assert "0 broken" in result.output
    assert "BROKEN" not in result.output


def test_render_result_separates_real_failures_from_quoted_ones(tmp_path):
    _write(tmp_path / "src.py", QUOTED_ERROR_SOURCE)

    # Quoting the error string is healthy: it lands in the text, not in errors.
    _write(tmp_path / "quotes.md.j2", "{{ code('src.py', function='handler', github=False) }}\n")
    quoted = TemplateRenderer(template_dir=tmp_path, repo_path=tmp_path).render_result("quotes.md.j2")
    assert quoted.ok
    assert quoted.errors == []
    assert "❌ **ERROR**:" in quoted.text  # the marker IS present — as quoted source

    # A genuine extraction failure is reported, with the template's own words
    # for what it asked for, and still degrades into the text.
    _write(tmp_path / "missing.md.j2", "{{ code('src.py', function='nope', github=False) }}\n")
    missing = TemplateRenderer(template_dir=tmp_path, repo_path=tmp_path).render_result("missing.md.j2")
    assert not missing.ok
    assert len(missing.errors) == 1
    assert missing.errors[0].file_path == "src.py"
    assert "function=nope" in missing.errors[0].target
    assert "❌ **ERROR**:" in missing.text


def test_render_result_collects_errors_from_includes(tmp_path):
    """Failures inside included partials surface on the parent's result.

    system-overview.md.j2 is a shell of include()s; if errors did not propagate
    up, checking the parent would report a healthy document.
    """
    _write(tmp_path / "partial.md.j2", "{{ code('src.py', function='nope', github=False) }}\n")
    _write(tmp_path / "parent.md.j2", "{{ include('partial.md.j2') }}\n")
    _write(tmp_path / "src.py", QUOTED_ERROR_SOURCE)

    result = TemplateRenderer(template_dir=tmp_path, repo_path=tmp_path).render_result("parent.md.j2")

    assert not result.ok
    assert len(result.errors) == 1
    assert "function=nope" in result.errors[0].target
