"""Tests for review_scope: the declarative scope variable and D filtering.

The scope is a literal dict the CLI reads from the entry template *before*
from_diff, so include/exclude globs filter the obligation set D to the files a
review actually cares about. A non-literal or schema-invalid scope is a hard
error; an include that matches nothing is surfaced so an empty scope cannot pass
--strict silently.
"""

import subprocess
from pathlib import Path

import pytest

from projected_source.core.changes_set import ChangesSet
from projected_source.core.review_scope import ReviewScopeError, extract_review_scope


# ---------------------------------------------------------------- extractor

def test_extracts_literal_scope():
    scope = extract_review_scope(
        '{% set review_scope = {"base": "origin/main", '
        '"include": ["src/**"], "exclude": ["**/test/**"]} %}\n# doc\n'
    )
    assert scope == {"base": "origin/main", "include": ["src/**"], "exclude": ["**/test/**"]}


def test_absent_scope_returns_none():
    assert extract_review_scope("# just a doc\n{{ code('a.cpp', function='f') }}\n") is None


def test_defaults_applied():
    scope = extract_review_scope('{% set review_scope = {"base": "HEAD~1"} %}\n')
    assert scope == {"base": "HEAD~1", "include": ["**"], "exclude": []}


def test_non_literal_is_rejected():
    with pytest.raises(ReviewScopeError, match="literal"):
        extract_review_scope('{% set review_scope = {"base": some_var} %}\n')


@pytest.mark.parametrize("src, msg", [
    ('{% set review_scope = {"base": 5} %}\n', "base must be"),
    ('{% set review_scope = {"include": "src/**"} %}\n', "include must be"),
    ('{% set review_scope = {"exclude": [1, 2]} %}\n', "exclude must be"),
    ('{% set review_scope = {"nope": 1} %}\n', "unknown keys"),
    ('{% set review_scope = [1, 2, 3] %}\n', "must be a dict"),
])
def test_schema_violations_raise(src, msg):
    with pytest.raises(ReviewScopeError, match=msg):
        extract_review_scope(src)


def test_scope_in_included_child_is_invisible():
    # The entry template only {% include %}s; its own body declares no scope.
    assert extract_review_scope('{% include "child.md.j2" %}\n{{ code("a", "b") }}\n') is None


def test_parses_with_code_context_extension():
    # Templates using {% code_context %} must still parse for extraction.
    src = (
        '{% set review_scope = {"base": "main"} %}\n'
        "{% code_context root='src' %}\n{{ code('a.cpp', function='f') }}\n{% endcode_context %}\n"
    )
    assert extract_review_scope(src)["base"] == "main"


# ------------------------------------------------------------- D filtering

def _git(repo, *args):
    return subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=True).stdout.strip()


@pytest.fixture
def repo(tmp_path):
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "test").mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "t@t.com")
    _git(repo, "config", "user.name", "t")
    return repo


def _two_file_change(repo):
    (repo / "src" / "a.cpp").write_text("one\n")
    (repo / "test" / "a_test.cpp").write_text("one\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "base")
    base = _git(repo, "rev-parse", "HEAD")
    (repo / "src" / "a.cpp").write_text("one\ntwo\nthree\n")       # +2 lines
    (repo / "test" / "a_test.cpp").write_text("one\nx\ny\nz\n")    # +3 lines
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "change")
    return base


def _files(cs):
    return sorted(p.name for p in cs.files())


def test_include_filters_D(repo):
    base = _two_file_change(repo)
    cs = ChangesSet.from_diff(base=base, repo_path=repo, include=["src/**"])
    assert _files(cs) == ["a.cpp"]                     # only src/a.cpp in D
    assert cs.changed_line_count() == 2
    assert cs.out_of_scope_line_count() == 3           # test/a_test.cpp's 3 lines dropped


def test_exclude_filters_D(repo):
    base = _two_file_change(repo)
    # A single leading-`**/` pattern must match a TOP-LEVEL test/ too (F16).
    cs = ChangesSet.from_diff(base=base, repo_path=repo, exclude=["**/test/**"])
    assert _files(cs) == ["a.cpp"]
    assert cs.out_of_scope_line_count() == 3


def test_star_does_not_cross_separator(repo):
    """`*` matches within one segment; `**` crosses segments (F17)."""
    (repo / "src" / "deep").mkdir(parents=True)
    (repo / "src" / "top.cpp").write_text("x\n")
    (repo / "src" / "deep" / "nested.cpp").write_text("x\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "base")
    base = _git(repo, "rev-parse", "HEAD")
    (repo / "src" / "top.cpp").write_text("x\ny\n")
    (repo / "src" / "deep" / "nested.cpp").write_text("x\ny\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "change")

    star = ChangesSet.from_diff(base=base, repo_path=repo, include=["src/*.cpp"])
    assert _files(star) == ["top.cpp"]                       # src/* stops at the separator
    starstar = ChangesSet.from_diff(base=base, repo_path=repo, include=["src/**"])
    assert sorted(_files(starstar)) == ["nested.cpp", "top.cpp"]  # ** crosses


def test_no_scope_includes_everything(repo):
    base = _two_file_change(repo)
    cs = ChangesSet.from_diff(base=base, repo_path=repo)
    assert _files(cs) == ["a.cpp", "a_test.cpp"]
    assert cs.changed_line_count() == 5
    assert cs.out_of_scope_line_count() == 0


def test_unmatched_include_is_surfaced(repo):
    base = _two_file_change(repo)
    cs = ChangesSet.from_diff(base=base, repo_path=repo, include=["does/not/exist/**", "src/**"])
    assert cs.unmatched_includes() == ["does/not/exist/**"]   # H5: typo'd glob surfaced
