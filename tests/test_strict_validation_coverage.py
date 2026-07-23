"""Acceptance tests for strict change validation coverage.

Pins the contract from .ai-docs/issues: `render -V --strict` requires
acknowledgement of actual added/replacement lines only. Unchanged diff
context is never an obligation, marker extractions claim their //@@
delimiter lines, enclosure_context is presentation-only, and extractions
pinned at the range's destination commit claim coverage without
coordinate drift.
"""

import subprocess
from pathlib import Path

import pytest

from projected_source.core.changes_set import ChangesSet
from projected_source.core.renderer import TemplateRenderer


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True, check=True
    )
    return result.stdout.strip()


def _commit_all(repo: Path, message: str) -> str:
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


def _render(repo: Path, tmp_path: Path, template_text: str, changes: ChangesSet, enclosure_context: int = 3):
    """Render a one-off template against repo, asserting extraction health."""
    template_dir = tmp_path / "templates"
    template_dir.mkdir(exist_ok=True)
    (template_dir / "doc.md.j2").write_text(template_text)
    renderer = TemplateRenderer(
        template_dir=template_dir,
        repo_path=repo,
        changes_set=changes,
        default_enclosure_context=enclosure_context,
    )
    result = renderer.render_result("doc.md.j2")
    assert result.ok, f"extraction failed: {[str(e) for e in result.errors]}"
    return result.text


def _uncovered_ranges(changes: ChangesSet):
    return [(r.start_line, r.end_line) for r in changes.uncovered()]


class TestMarkerCoverage:
    def test_marker_body_change_passes_with_zero_context(self, repo, tmp_path):
        """One changed statement inside an existing marker passes with
        enclosure_context=0; unchanged neighbors are not required."""
        source = repo / "file.cpp"
        source.write_text(
            "void f() {\n"
            "    int before = 0;\n"
            "    //@@start core\n"
            "    int value = 1;\n"
            "    //@@end core\n"
            "    int after = 2;\n"
            "}\n"
        )
        _commit_all(repo, "base")
        source.write_text(source.read_text().replace("int value = 1;", "int value = 42;"))
        _commit_all(repo, "change marker body")

        changes = ChangesSet.from_diff(base="HEAD~1", repo_path=repo)
        # Only the replaced line is required — not the hunk's context halo.
        assert _uncovered_ranges(changes) == [(4, 4)]

        _render(
            repo,
            tmp_path,
            "{{ code('file.cpp', marker='core', enclosure_context=0, github=False) }}\n",
            changes,
        )
        assert changes.is_complete()

    def test_marker_introduced_with_change_passes(self, repo, tmp_path):
        """New //@@ delimiter lines plus body pass without lines= or a
        whole-file exemption — marker coverage claims its delimiters."""
        source = repo / "file.cpp"
        source.write_text(
            "void f() {\n"
            "    int a = 0;\n"
            "    int b = 1;\n"
            "}\n"
        )
        _commit_all(repo, "base")
        source.write_text(
            "void f() {\n"
            "    int a = 0;\n"
            "    //@@start added\n"
            "    int c = 2;\n"
            "    //@@end added\n"
            "    int b = 1;\n"
            "}\n"
        )
        _commit_all(repo, "introduce marker with change")

        changes = ChangesSet.from_diff(base="HEAD~1", repo_path=repo)
        assert _uncovered_ranges(changes) == [(3, 5)]

        # Default enclosure context (3) exercises the enclosed-marker path.
        _render(
            repo,
            tmp_path,
            "{{ code('file.cpp', marker='added', github=False) }}\n",
            changes,
        )
        assert changes.is_complete()

    def test_file_scope_include_marker_passes(self, repo, tmp_path):
        """A marker around one added include passes even though no AST
        symbol encloses it."""
        source = repo / "file.cpp"
        source.write_text(
            "#include <string>\n"
            "\n"
            "int main() {\n"
            "    return 0;\n"
            "}\n"
        )
        _commit_all(repo, "base")
        source.write_text(
            "#include <string>\n"
            "//@@start deps\n"
            "#include <vector>\n"
            "//@@end deps\n"
            "\n"
            "int main() {\n"
            "    return 0;\n"
            "}\n"
        )
        _commit_all(repo, "add include dependency")

        changes = ChangesSet.from_diff(base="HEAD~1", repo_path=repo)
        assert _uncovered_ranges(changes) == [(2, 4)]

        _render(
            repo,
            tmp_path,
            "{{ code('file.cpp', marker='deps', enclosure_context=0, github=False) }}\n",
            changes,
        )
        assert changes.is_complete()

    def test_ignore_changes_marker_claims_delimiters(self, repo, tmp_path):
        """ignore_changes(marker=...) also claims the //@@ delimiter lines."""
        source = repo / "file.cpp"
        source.write_text(
            "void f() {\n"
            "    int a = 0;\n"
            "    int b = 1;\n"
            "}\n"
        )
        _commit_all(repo, "base")
        source.write_text(
            "void f() {\n"
            "    int a = 0;\n"
            "    //@@start added\n"
            "    int c = 2;\n"
            "    //@@end added\n"
            "    int b = 1;\n"
            "}\n"
        )
        _commit_all(repo, "introduce marker with change")

        changes = ChangesSet.from_diff(base="HEAD~1", repo_path=repo)
        _render(
            repo,
            tmp_path,
            "{{ ignore_changes('file.cpp', marker='added') }}\n",
            changes,
        )
        assert changes.is_complete()


class TestNearbyChangesStayVisible:
    def _repo_with_two_nearby_changes(self, repo):
        source = repo / "file.cpp"
        source.write_text(
            "void f() {\n"
            "    int a = 0;\n"
            "    //@@start one\n"
            "    int m = 1;\n"
            "    //@@end one\n"
            "    int b = 2;\n"
            "}\n"
        )
        _commit_all(repo, "base")
        text = source.read_text()
        text = text.replace("int m = 1;", "int m = 10;")
        text = text.replace("int b = 2;", "int b = 20;")
        source.write_text(text)
        _commit_all(repo, "two nearby changes")

    def test_undocumented_neighbor_stays_uncovered(self, repo, tmp_path):
        """Documenting one of two nearby additions leaves the other
        uncovered, even though Git places both in one hunk."""
        self._repo_with_two_nearby_changes(repo)

        changes = ChangesSet.from_diff(base="HEAD~1", repo_path=repo)
        assert _uncovered_ranges(changes) == [(4, 4), (6, 6)]

        _render(
            repo,
            tmp_path,
            "{{ code('file.cpp', marker='one', enclosure_context=0, github=False) }}\n",
            changes,
        )
        assert _uncovered_ranges(changes) == [(6, 6)]

    def test_enclosure_context_does_not_change_coverage(self, repo, tmp_path):
        """The rendered enclosure head/tail must never claim coverage: the
        same document leaves the same line uncovered at context 0, 3, 5."""
        self._repo_with_two_nearby_changes(repo)

        outcomes = []
        for context in (0, 3, 5):
            changes = ChangesSet.from_diff(base="HEAD~1", repo_path=repo)
            _render(
                repo,
                tmp_path,
                "{{ code('file.cpp', marker='one', enclosure_context=%d, github=False) }}\n" % context,
                changes,
            )
            outcomes.append(_uncovered_ranges(changes))

        # Line 6 (int b = 20;) sits inside the enclosure tail that context=3/5
        # displays — presentation must not silently consume it.
        assert outcomes == [[(6, 6)], [(6, 6)], [(6, 6)]]


class TestPinnedRefCoverage:
    def _repo_with_history(self, repo):
        """A(base) -> B(marker change) -> C(HEAD, lines shifted above)."""
        source = repo / "file.cpp"
        source.write_text(
            "void f() {\n"
            "    int a = 0;\n"
            "    int b = 1;\n"
            "}\n"
        )
        sha_a = _commit_all(repo, "A: base")
        source.write_text(
            "void f() {\n"
            "    int a = 0;\n"
            "    //@@start core\n"
            "    int c = 2;\n"
            "    //@@end core\n"
            "    int b = 1;\n"
            "}\n"
        )
        sha_b = _commit_all(repo, "B: marker change")
        source.write_text("// header comment\n// more header\n" + source.read_text())
        sha_c = _commit_all(repo, "C: shift lines")
        return sha_a, sha_b, sha_c

    def test_ref_at_range_destination_claims_coverage(self, repo, tmp_path):
        """A marker pinned at the range's destination commit covers the
        changed lines without coordinate drift, even when HEAD moved on."""
        sha_a, sha_b, _ = self._repo_with_history(repo)

        changes = ChangesSet.from_diff(base=f"{sha_a}..{sha_b}", repo_path=repo)
        assert changes.target_sha == sha_b
        assert _uncovered_ranges(changes) == [(3, 5)]

        _render(
            repo,
            tmp_path,
            "{{ code('file.cpp', marker='core', enclosure_context=0, "
            "ref='%s', github=False) }}\n" % sha_b,
            changes,
        )
        assert changes.is_complete()

    def test_ref_elsewhere_claims_nothing(self, repo, tmp_path):
        """A pin at any commit other than the range destination lives in a
        different coordinate space and must not subtract coverage."""
        sha_a, sha_b, sha_c = self._repo_with_history(repo)

        changes = ChangesSet.from_diff(base=f"{sha_a}..{sha_b}", repo_path=repo)
        _render(
            repo,
            tmp_path,
            "{{ code('file.cpp', marker='core', enclosure_context=0, "
            "ref='%s', github=False) }}\n" % sha_c,
            changes,
        )
        assert _uncovered_ranges(changes) == [(3, 5)]


class TestCppEnumSelector:
    def _repo_with_enum_change(self, repo):
        source = repo / "state.h"
        source.write_text(
            "enum class State {\n"
            "    Idle,\n"
            "    Running\n"
            "};\n"
            "\n"
            "class Widget {\n"
            "public:\n"
            "    int x = 0;\n"
            "};\n"
        )
        _commit_all(repo, "base")
        source.write_text(source.read_text().replace(
            "    Running\n", "    Running,\n    Stopped\n"
        ))
        _commit_all(repo, "add enum member")

    def test_enum_selector_covers_changed_members(self, repo, tmp_path):
        """code(enum=...) finds a C++ enum; the blank line and neighboring
        class declaration are not independently required."""
        self._repo_with_enum_change(repo)

        changes = ChangesSet.from_diff(base="HEAD~1", repo_path=repo)
        assert _uncovered_ranges(changes) == [(3, 4)]

        text = _render(
            repo,
            tmp_path,
            "{{ code('state.h', enum='State', github=False) }}\n",
            changes,
        )
        assert changes.is_complete()
        assert "Stopped" in text

    def test_ignore_changes_enum_selector(self, repo, tmp_path):
        self._repo_with_enum_change(repo)

        changes = ChangesSet.from_diff(base="HEAD~1", repo_path=repo)
        _render(
            repo,
            tmp_path,
            "{{ ignore_changes('state.h', enum='State') }}\n",
            changes,
        )
        assert changes.is_complete()

    def test_enum_selector_rejects_non_enum_with_actionable_message(self, repo, tmp_path):
        self._repo_with_enum_change(repo)

        template_dir = tmp_path / "templates"
        template_dir.mkdir(exist_ok=True)
        (template_dir / "doc.md.j2").write_text(
            "{{ code('state.h', enum='Widget', github=False) }}\n"
        )
        renderer = TemplateRenderer(template_dir=template_dir, repo_path=repo)
        result = renderer.render_result("doc.md.j2")

        assert not result.ok
        assert "not an enum" in result.errors[0].message
        assert "struct=" in result.errors[0].message
