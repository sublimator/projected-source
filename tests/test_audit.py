"""Tests for audit() — the third change-handling verb.

audit() acknowledges a changed region in a persistent, reader-invisible
`<!-- audit ... -->` note carrying a mandatory reason, and claims -V coverage
the same way ignore_changes() does. Unlike ignore_changes(): the note is always
emitted and its coordinates never depend on -V (so `check` stays stable), the
reason is mandatory (empty -> a visible failure, never a silent drop), and the
note carries the symbolic selector so it survives refactoring.
"""

import re
import subprocess
from pathlib import Path

import pytest

from projected_source.core.changes_set import ChangesSet
from projected_source.core.renderer import TemplateRenderer


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True, check=True
    ).stdout.strip()


def _commit(repo: Path, message: str) -> str:
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", message)
    return _git(repo, "rev-parse", "HEAD")


@pytest.fixture
def repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "test@test.com")
    _git(repo, "config", "user.name", "Test")
    return repo


def _render(repo: Path, tmp_path: Path, template_text: str, changes: ChangesSet = None):
    template_dir = tmp_path / "templates"
    template_dir.mkdir(exist_ok=True)
    (template_dir / "doc.md.j2").write_text(template_text)
    renderer = TemplateRenderer(
        template_dir=template_dir, repo_path=repo, changes_set=changes
    )
    return renderer.render_result("doc.md.j2")


def _first_note(text: str) -> str:
    m = re.search(r"<!-- audit(?:-error)?\b.*?-->", text, re.DOTALL)
    assert m, f"no audit note in: {text!r}"
    return m.group(0)


# --------------------------------------------------------------------- shape

def test_note_shape_and_selector(repo, tmp_path):
    (repo / "f.cpp").write_text("int foo() {\n    return 1;\n}\n")
    _commit(repo, "init")
    result = _render(
        repo, tmp_path,
        '{{ audit("f.cpp", function="foo", reason="boilerplate, covered elsewhere") }}',
    )
    assert result.ok
    note = _first_note(result.text)
    assert note.startswith("<!-- audit ")
    assert note.endswith(" -->")
    assert 'file="f.cpp"' in note
    assert re.search(r'lines="\d+-\d+"', note)
    assert 'function="foo"' in note              # H7: selector carried
    assert 'reason="boilerplate, covered elsewhere"' in note


def test_lines_selector_has_no_duplicate_attr(repo, tmp_path):
    (repo / "f.cpp").write_text("a\nb\nc\nd\ne\n")
    _commit(repo, "init")
    note = _first_note(
        _render(repo, tmp_path, '{{ audit("f.cpp", lines=(2, 4), reason="x") }}').text
    )
    assert 'lines="2-4"' in note
    # lines= is its own selector; no second selector attribute is emitted
    assert note.count("lines=") == 1


def test_whole_file_audit(repo, tmp_path):
    (repo / "gen.txt").write_text("one\ntwo\n")
    _commit(repo, "init")
    note = _first_note(
        _render(repo, tmp_path, '{{ audit("gen.txt", reason="generated file") }}').text
    )
    assert 'scope="whole-file"' in note
    assert "lines=" not in note


# ----------------------------------------------------------------- sanitize

def test_reason_is_html_comment_safe(repo, tmp_path):
    (repo / "f.cpp").write_text("a\nb\nc\n")
    _commit(repo, "init")
    nasty = 'drain loop -- see PR --> follow-up; while (n --> 0); tag <x> "q" & z'
    note = _first_note(
        _render(repo, tmp_path, f'{{{{ audit("f.cpp", lines=(1, 2), reason={nasty!r}) }}}}').text
    )
    assert note.startswith("<!-- ") and note.endswith(" -->")
    inner = note[len("<!-- "): -len(" -->")]   # content between opener and terminator
    assert "-->" not in inner                  # cannot terminate the comment early
    assert '"q"' not in note and "&quot;q&quot;" in note   # the attribute quote is escaped
    # everything else stays byte-exact and greppable (H1 fidelity, F1):
    assert "loop -- see" in note               # a bare -- in prose is preserved
    assert "<x>" in note and "& z" in note      # <, >, & are not entity-mangled


def test_id_is_emitted_in_note(repo, tmp_path):
    """audit(id=...) carries the node id into the note (chunk-graph seed)."""
    (repo / "f.cpp").write_text("int foo() {\n  return 1;\n}\n")
    _commit(repo, "init")
    note = _first_note(
        _render(repo, tmp_path, '{{ audit("f.cpp", function="foo", id="admit", reason="x") }}').text
    )
    assert 'id="admit"' in note


def test_double_dash_paths_and_markers_are_byte_exact(repo, tmp_path):
    """A `--` in a path or selector must survive verbatim so the note resolves (F1)."""
    (repo / "o--dd.cpp").write_text(
        "int a() {\n  //@@start we--ird\n  int x = 1;\n  //@@end we--ird\n}\n"
    )
    _commit(repo, "init")
    note = _first_note(
        _render(
            repo, tmp_path,
            '{{ audit("o--dd.cpp", marker="we--ird", reason="double dashes everywhere") }}',
        ).text
    )
    assert 'file="o--dd.cpp"' in note            # path -- preserved, not o-dd.cpp
    assert 'marker="we--ird"' in note            # marker -- preserved, not we-ird


def test_reason_collapses_newlines(repo, tmp_path):
    (repo / "f.cpp").write_text("a\nb\n")
    _commit(repo, "init")
    note = _first_note(
        _render(repo, tmp_path, '{{ audit("f.cpp", lines=(1, 1), reason="line one\\nline two") }}').text
    )
    assert "\n" not in note
    assert 'reason="line one line two"' in note


# ---------------------------------------------------------- mandatory reason

@pytest.mark.parametrize("call", [
    '{{ audit("f.cpp", lines=(1, 1)) }}',                 # absent
    '{{ audit("f.cpp", lines=(1, 1), reason="") }}',      # empty
    '{{ audit("f.cpp", lines=(1, 1), reason="   ") }}',   # whitespace only
])
def test_mandatory_reason_fails_visibly(repo, tmp_path, call):
    (repo / "f.cpp").write_text("a\nb\n")
    _commit(repo, "init")
    result = _render(repo, tmp_path, call)
    assert not result.ok                                  # structural CodeError -> check reports broken
    assert "audit-error" in result.text                   # visible, not a silent drop
    assert any("non-empty reason" in str(e) for e in result.errors)


def test_failed_extraction_is_visible_not_silent(repo, tmp_path):
    (repo / "f.cpp").write_text("int foo() {\n    return 1;\n}\n")
    _commit(repo, "init")
    result = _render(
        repo, tmp_path,
        '{{ audit("f.cpp", function="does_not_exist", reason="x") }}',
    )
    assert not result.ok
    assert "audit-error" in result.text                   # contrast: ignore_changes swallows silently


# ------------------------------------------------------- check-stable (B5)

def test_extents_identical_with_and_without_V(repo, tmp_path):
    """The note must be byte-identical whether or not a ChangesSet is present,
    so `check`'s no-`-V` re-render never reports the doc stale (B5)."""
    (repo / "f.cpp").write_text("int foo() {\n    int x = 1;\n    return x;\n}\n")
    base = _commit(repo, "init")
    (repo / "f.cpp").write_text("int foo() {\n    int x = 2;\n    return x;\n}\n")
    _commit(repo, "change")
    # Dirty the tree with an UNCOMMITTED edit above the audited symbol, so the
    # working-tree line numbers differ from the committed ones. Without this the
    # tree is clean, map_to_committed_line is the identity, and a -V-dependent
    # note (the B5 bug) would look identical anyway — the test could not detect it.
    (repo / "f.cpp").write_text(
        "// uncommitted line 1\n// uncommitted line 2\n"
        "int foo() {\n    int x = 2;\n    return x;\n}\n"
    )

    tmpl = '{{ audit("f.cpp", function="foo", reason="tweak") }}'
    without_v = _first_note(_render(repo, tmp_path, tmpl, changes=None).text)
    with_v = _first_note(
        _render(repo, tmp_path, tmpl, changes=ChangesSet.from_diff(base=base, repo_path=repo)).text
    )
    assert without_v == with_v


# ----------------------------------------------------------- coverage claim

def test_audit_claims_coverage(repo, tmp_path):
    (repo / "f.cpp").write_text("int foo() {\n    return 0;\n}\n")
    base = _commit(repo, "init")
    (repo / "f.cpp").write_text("int foo() {\n    int x = 1;\n    return x;\n}\n")
    _commit(repo, "change")

    changes = ChangesSet.from_diff(base=base, repo_path=repo)
    assert not changes.is_complete()                      # there are changed lines
    result = _render(
        repo, tmp_path,
        '{{ audit("f.cpp", function="foo", reason="trivial refactor") }}',
        changes,
    )
    assert result.ok
    assert changes.is_complete()                          # audit() claimed the changed region


def test_whole_file_audit_claims_all(repo, tmp_path):
    (repo / "f.cpp").write_text("a\n")
    base = _commit(repo, "init")
    (repo / "f.cpp").write_text("a\nb\nc\n")
    _commit(repo, "change")
    changes = ChangesSet.from_diff(base=base, repo_path=repo)
    assert not changes.is_complete()
    _render(repo, tmp_path, '{{ audit("f.cpp", reason="all boilerplate") }}', changes)
    assert changes.is_complete()


_MARKED_FUNC_BASE = (
    "void f() {\n"
    "    int before = 0;\n"
    "    //@@start core\n"
    "    int inside = 0;\n"
    "    //@@end core\n"
    "    int after = 0;\n"
    "}\n"
)
_MARKED_FUNC_CHANGED = (
    "void f() {\n"
    "    int before = 1;\n"          # changed, outside marker
    "    //@@start core\n"
    "    int inside = 1;\n"          # changed, inside marker
    "    //@@end core\n"
    "    int after = 1;\n"           # changed, outside marker
    "}\n"
)


def test_minus_yields_multiple_regions(repo, tmp_path):
    (repo / "f.cpp").write_text(_MARKED_FUNC_BASE)
    _commit(repo, "init")
    (repo / "f.cpp").write_text(_MARKED_FUNC_CHANGED)
    _commit(repo, "change")
    note = _first_note(
        _render(
            repo, tmp_path,
            '{{ audit("f.cpp", function="f", minus={"marker": "core"}, reason="frame around the narrated core") }}',
        ).text
    )
    # two ranges (before + after the marker), and the geometry is recorded
    assert note.count(",") >= 1 or re.search(r'lines="\d+-\d+,\d+-\d+"', note)
    assert 'minus="marker=core"' in note
    assert 'function="f"' in note


def test_narrate_marker_audit_the_rest_covers_the_function(repo, tmp_path):
    """code() the marker, audit() the function minus the marker -> the whole
    function's changes are accounted for, split across the two buckets."""
    (repo / "f.cpp").write_text(_MARKED_FUNC_BASE)
    base = _commit(repo, "init")
    (repo / "f.cpp").write_text(_MARKED_FUNC_CHANGED)
    _commit(repo, "change")
    changes = ChangesSet.from_diff(base=base, repo_path=repo)
    result = _render(
        repo, tmp_path,
        '{{ code("f.cpp", function="f", marker="core") }}\n'
        '{{ audit("f.cpp", function="f", minus={"marker": "core"}, reason="rest is trivial") }}\n',
        changes,
    )
    assert result.ok
    assert changes.is_complete()                 # every changed line in f covered
    buckets, _ = changes.partition()
    assert buckets["code"] >= 1 and buckets["audit"] >= 1   # split across both


def test_minus_removing_everything_is_visible_error(repo, tmp_path):
    (repo / "f.cpp").write_text(_MARKED_FUNC_BASE)
    _commit(repo, "init")
    (repo / "f.cpp").write_text(_MARKED_FUNC_CHANGED)
    _commit(repo, "change")
    result = _render(
        repo, tmp_path,
        '{{ audit("f.cpp", marker="core", minus={"marker": "core"}, reason="x") }}',
    )
    assert not result.ok
    assert "audit-error" in result.text


def test_partition_through_render(repo, tmp_path):
    """The renderer routes code/audit/ignore into disjoint buckets end to end."""
    (repo / "f.cpp").write_text(
        "int foo() {\n    return 0;\n}\n"
        "int bar() {\n    return 0;\n}\n"
        "int baz() {\n    return 0;\n}\n"
        "int qux() {\n    return 0;\n}\n"
    )
    base = _commit(repo, "init")
    (repo / "f.cpp").write_text(
        "int foo() {\n    int a = 1;\n    return a;\n}\n"
        "int bar() {\n    int b = 2;\n    return b;\n}\n"
        "int baz() {\n    int c = 3;\n    return c;\n}\n"
        "int qux() {\n    int d = 4;\n    return d;\n}\n"
    )
    _commit(repo, "change")
    changes = ChangesSet.from_diff(base=base, repo_path=repo)
    result = _render(
        repo, tmp_path,
        '{{ code("f.cpp", function="foo") }}\n'
        '{{ audit("f.cpp", function="bar", reason="mirrors foo") }}\n'
        '{{ ignore_changes("f.cpp", function="baz") }}\n',
        changes,
    )
    assert result.ok
    buckets, _ = changes.partition()
    assert buckets == {"code": 2, "audit": 2, "ignore": 2}   # each function: 2 changed lines
    assert changes.changed_line_count() == 8                 # qux (2 lines) is the residual
    assert not changes.is_complete()
