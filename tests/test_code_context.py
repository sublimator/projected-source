"""Tests for {% code_context %} block extension and set_code_context()."""

import subprocess

from projected_source.core.changes_set import ChangesSet
from projected_source.core.renderer import TemplateRenderer


class TestCodeContext:
    def test_code_context_root_block(self, tmp_path):
        """{% code_context root='path' %} prepends path to code() file paths."""
        src_dir = tmp_path / "src" / "app"
        src_dir.mkdir(parents=True)
        (src_dir / "handler.py").write_text("def process():\n    return 42\n")

        template = tmp_path / "doc.md.j2"
        template.write_text(
            "{% code_context root='src/app' %}\n"
            "{{ code('handler.py', function='process', github=False) }}\n"
            "{% endcode_context %}\n"
        )

        renderer = TemplateRenderer(template_dir=tmp_path, repo_path=tmp_path)
        result = renderer.render_template("doc.md.j2")
        assert "def process():" in result
        assert "return 42" in result

    def test_code_context_scoping(self, tmp_path):
        """code_root reverts after {% endcode_context %}."""
        src_dir = tmp_path / "src" / "app"
        src_dir.mkdir(parents=True)
        (src_dir / "handler.py").write_text("def process():\n    return 42\n")
        (tmp_path / "top.py").write_text("def top_level():\n    pass\n")

        template = tmp_path / "doc.md.j2"
        template.write_text(
            "{% code_context root='src/app' %}\n"
            "{{ code('handler.py', function='process', github=False) }}\n"
            "{% endcode_context %}\n"
            "{{ code('top.py', function='top_level', github=False) }}\n"
        )

        renderer = TemplateRenderer(template_dir=tmp_path, repo_path=tmp_path)
        result = renderer.render_template("doc.md.j2")
        assert "def process():" in result
        assert "def top_level():" in result

    def test_code_context_nesting(self, tmp_path):
        """Nested {% code_context %} blocks override and restore correctly."""
        (tmp_path / "a").mkdir()
        (tmp_path / "a" / "b").mkdir()
        (tmp_path / "a" / "one.py").write_text("def one():\n    pass\n")
        (tmp_path / "a" / "b" / "two.py").write_text("def two():\n    pass\n")

        template = tmp_path / "doc.md.j2"
        template.write_text(
            "{% code_context root='a' %}\n"
            "{{ code('one.py', function='one', github=False) }}\n"
            "{% code_context root='a/b' %}\n"
            "{{ code('two.py', function='two', github=False) }}\n"
            "{% endcode_context %}\n"
            "{% endcode_context %}\n"
        )

        renderer = TemplateRenderer(template_dir=tmp_path, repo_path=tmp_path)
        result = renderer.render_template("doc.md.j2")
        assert "def one():" in result
        assert "def two():" in result

    def test_code_context_does_not_affect_absolute_paths(self, tmp_path):
        """Absolute paths bypass code_root."""
        (tmp_path / "example.py").write_text("def hello():\n    pass\n")

        abs_path = str(tmp_path / "example.py")
        template = tmp_path / "doc.md.j2"
        template.write_text(
            "{%% code_context root='nonexistent/dir' %%}\n"
            "{{ code('%s', function='hello', github=False) }}\n"
            "{%% endcode_context %%}\n" % abs_path
        )

        renderer = TemplateRenderer(template_dir=tmp_path, repo_path=tmp_path)
        result = renderer.render_template("doc.md.j2")
        assert "def hello():" in result

    def test_code_context_root_with_trailing_slash(self, tmp_path):
        """Trailing slash on root works fine."""
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "mod.py").write_text("x = 1\n")

        template = tmp_path / "doc.md.j2"
        template.write_text(
            "{% code_context root='src/' %}\n{{ code('mod.py', var='x', github=False) }}\n{% endcode_context %}\n"
        )

        renderer = TemplateRenderer(template_dir=tmp_path, repo_path=tmp_path)
        result = renderer.render_template("doc.md.j2")
        assert "x = 1" in result

    def test_without_code_context(self, tmp_path):
        """Without code_context, paths resolve from repo root as before."""
        (tmp_path / "example.py").write_text("def hello():\n    pass\n")

        template = tmp_path / "doc.md.j2"
        template.write_text("{{ code('example.py', function='hello', github=False) }}\n")

        renderer = TemplateRenderer(template_dir=tmp_path, repo_path=tmp_path)
        result = renderer.render_template("doc.md.j2")
        assert "def hello():" in result

    def test_set_code_context_root(self, tmp_path):
        """{{ set_code_context(root=...) }} sets the root globally."""
        src_dir = tmp_path / "src" / "app"
        src_dir.mkdir(parents=True)
        (src_dir / "handler.py").write_text("def process():\n    return 42\n")

        template = tmp_path / "doc.md.j2"
        template.write_text(
            "{{ set_code_context(root='src/app') }}\n{{ code('handler.py', function='process', github=False) }}\n"
        )

        renderer = TemplateRenderer(template_dir=tmp_path, repo_path=tmp_path)
        result = renderer.render_template("doc.md.j2")
        assert "def process():" in result

    def test_set_code_context_clear(self, tmp_path):
        """{{ set_code_context(root='') }} clears the root."""
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "a.py").write_text("def a():\n    pass\n")
        (tmp_path / "b.py").write_text("def b():\n    pass\n")

        template = tmp_path / "doc.md.j2"
        template.write_text(
            "{{ set_code_context(root='src') }}\n"
            "{{ code('a.py', function='a', github=False) }}\n"
            "{{ set_code_context(root='') }}\n"
            "{{ code('b.py', function='b', github=False) }}\n"
        )

        renderer = TemplateRenderer(template_dir=tmp_path, repo_path=tmp_path)
        result = renderer.render_template("doc.md.j2")
        assert "def a():" in result
        assert "def b():" in result

    def test_set_code_root_backward_compat(self, tmp_path):
        """{{ set_code_root() }} still works as backward-compatible alias."""
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "a.py").write_text("def a():\n    pass\n")

        template = tmp_path / "doc.md.j2"
        template.write_text("{{ set_code_root('src') }}\n{{ code('a.py', function='a', github=False) }}\n")

        renderer = TemplateRenderer(template_dir=tmp_path, repo_path=tmp_path)
        result = renderer.render_template("doc.md.j2")
        assert "def a():" in result

    def test_code_root_per_call(self, tmp_path):
        """root= on code() overrides context code_root."""
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "mod.py").write_text("def hello():\n    pass\n")
        other_dir = tmp_path / "other"
        other_dir.mkdir()
        (other_dir / "mod.py").write_text("def world():\n    pass\n")

        template = tmp_path / "doc.md.j2"
        template.write_text(
            "{%% code_context root='%s/src' %%}\n"
            "{{ code('mod.py', function='hello', github=False) }}\n"
            "{{ code('mod.py', function='world', github=False, root='%s/other') }}\n"
            "{%% endcode_context %%}\n" % (tmp_path, tmp_path)
        )

        renderer = TemplateRenderer(template_dir=tmp_path, repo_path=tmp_path)
        result = renderer.render_template("doc.md.j2")
        assert "def hello():" in result
        assert "def world():" in result

    def test_code_root_per_call_with_set_var(self, tmp_path):
        """root= works with {% set %} variables."""
        proj_a = tmp_path / "project_a" / "src"
        proj_a.mkdir(parents=True)
        (proj_a / "app.py").write_text("def run_a():\n    pass\n")
        proj_b = tmp_path / "project_b" / "src"
        proj_b.mkdir(parents=True)
        (proj_b / "app.py").write_text("def run_b():\n    pass\n")

        template = tmp_path / "doc.md.j2"
        template.write_text(
            "{%% set proj_a = '%s/project_a' %%}\n"
            "{%% set proj_b = '%s/project_b' %%}\n"
            "{{ code('src/app.py', function='run_a', github=False, root=proj_a) }}\n"
            "{{ code('src/app.py', function='run_b', github=False, root=proj_b) }}\n" % (tmp_path, tmp_path)
        )

        renderer = TemplateRenderer(template_dir=tmp_path, repo_path=tmp_path)
        result = renderer.render_template("doc.md.j2")
        assert "def run_a():" in result
        assert "def run_b():" in result

    def test_ignore_changes_respects_code_context(self, tmp_path):
        """ignore_changes() also resolves via code_context root."""
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        py_file = src_dir / "mod.py"
        py_file.write_text("def foo():\n    pass\n")

        changes = ChangesSet()
        changes.add(py_file, 1, 2)

        template = tmp_path / "doc.md.j2"
        template.write_text("{% code_context root='src' %}\n{{ ignore_changes('mod.py') }}\n{% endcode_context %}\n")

        renderer = TemplateRenderer(template_dir=tmp_path, repo_path=tmp_path, changes_set=changes)
        renderer.render_template("doc.md.j2")
        assert changes.is_complete()

    def test_ignore_changes_accepts_message_param(self, tmp_path):
        """ignore_changes(file, message='X') must not raise TypeError."""
        py_file = tmp_path / "mod.py"
        py_file.write_text("def foo():\n    pass\n")

        changes = ChangesSet()
        changes.add(py_file, 1, 2)

        # Use a proto-style call - we only care that it doesn't raise TypeError
        # at the function-signature level. The extractor may fail (no extractor
        # for .py with message=), but ignore_changes catches that internally.
        template = tmp_path / "doc.md.j2"
        template.write_text("{{ ignore_changes('mod.py', message='Foo') }}\n")

        renderer = TemplateRenderer(template_dir=tmp_path, repo_path=tmp_path, changes_set=changes)
        # Must not raise TypeError about unexpected keyword 'message'.
        renderer.render_template("doc.md.j2")

    def test_ignore_changes_accepts_signature_param(self, tmp_path):
        """ignore_changes(file, function='X', signature='Y') must not raise TypeError."""
        py_file = tmp_path / "mod.py"
        py_file.write_text("def foo():\n    pass\n")

        changes = ChangesSet()
        changes.add(py_file, 1, 2)

        template = tmp_path / "doc.md.j2"
        template.write_text(
            "{{ ignore_changes('mod.py', function='foo', signature='whatever') }}\n"
        )

        renderer = TemplateRenderer(template_dir=tmp_path, repo_path=tmp_path, changes_set=changes)
        # Must not raise TypeError about unexpected keyword 'signature'.
        renderer.render_template("doc.md.j2")
        # The function was extracted and subtracted, covering lines 1-2.
        assert changes.is_complete()


class TestCodeContextExceptionSafety:
    def test_code_context_restores_globals_on_exception(self, tmp_path):
        """{% code_context %} must restore code_root even if caller() raises."""
        (tmp_path / "outer.py").write_text("def outer():\n    pass\n")

        # The inner code() raises (function does not exist), which surfaces an
        # ERROR string in the rendered output rather than an exception. To
        # trigger a real raise inside the block, we use a Jinja construct
        # that raises during template execution: division by zero.
        template = tmp_path / "doc.md.j2"
        template.write_text(
            "{% code_context root='nested/path' %}\n"
            "{{ 1 / 0 }}\n"
            "{% endcode_context %}\n"
        )

        renderer = TemplateRenderer(template_dir=tmp_path, repo_path=tmp_path)
        try:
            renderer.render_template("doc.md.j2")
        except Exception:
            pass  # expected — we just need the finally clause to have run

        # If the bug exists, code_root remains 'nested/path' and the next
        # code() call resolves outer.py incorrectly.
        template2 = tmp_path / "doc2.md.j2"
        template2.write_text("{{ code('outer.py', function='outer', github=False) }}\n")
        result = renderer.render_template("doc2.md.j2")
        assert "def outer():" in result, (
            f"code_root leaked from prior code_context block; result:\n{result}"
        )

    def test_code_context_restores_ref_on_exception(self, tmp_path):
        """{% code_context ref=... %} must restore code_ref even if caller() raises."""
        (tmp_path / "outer.py").write_text("def outer():\n    pass\n")

        template = tmp_path / "doc.md.j2"
        template.write_text(
            "{% code_context ref='nonexistent-ref' %}\n"
            "{{ 1 / 0 }}\n"
            "{% endcode_context %}\n"
        )

        renderer = TemplateRenderer(template_dir=tmp_path, repo_path=tmp_path)
        try:
            renderer.render_template("doc.md.j2")
        except Exception:
            pass

        # If the bug exists, code_ref leaks and the next code() call tries
        # 'git show nonexistent-ref:outer.py'.
        template2 = tmp_path / "doc2.md.j2"
        template2.write_text("{{ code('outer.py', function='outer', github=False) }}\n")
        result = renderer.render_template("doc2.md.j2")
        assert "def outer():" in result, (
            f"code_ref leaked from prior code_context block; result:\n{result}"
        )


class TestCodeErrorHandling:
    def test_code_with_invalid_file_path_returns_error_not_crash(self, tmp_path):
        """A bad file_path argument must surface an ERROR string, not crash with UnboundLocalError."""
        template = tmp_path / "doc.md.j2"
        # Pass a non-string value (a list) for file_path. Path(file_path)
        # will raise TypeError, which fires before resolved_path is assigned.
        # The except handler must not itself raise UnboundLocalError.
        template.write_text("{{ code(some_list, function='foo', github=False) }}\n")

        renderer = TemplateRenderer(template_dir=tmp_path, repo_path=tmp_path)
        # Pass a list as the file_path - Path() chokes on it during is_absolute().
        result = renderer.render_template("doc.md.j2", some_list=["not", "a", "path"])
        # Should produce an ERROR string from the except block, no UnboundLocalError.
        assert "ERROR" in result


def _init_remote_git_repo(path):
    """Init a git repo with a fake github origin so permalinks work."""
    _init_git_repo(path)
    subprocess.check_call(
        ["git", "remote", "add", "origin", "https://github.com/test/test.git"],
        cwd=path,
    )


class TestChangesSetCoverageRespectsDirtyLines:
    def test_subtract_uses_committed_line_numbers(self, tmp_path):
        """code() must translate working-tree lines to HEAD lines before subtracting.

        changes_set is built from HEAD-relative diff. When a file has uncommitted
        edits above the extracted region, the working-tree line numbers differ
        from HEAD line numbers — subtract() with raw working-tree lines removes
        the wrong rows.
        """
        _init_git_repo(tmp_path)

        py_file = tmp_path / "mod.py"
        # Committed version: helper() at lines 1-2
        py_file.write_text("def helper():\n    return 42\n")
        _git_commit(tmp_path, "initial")

        # Build the changes_set BEFORE any working-tree edits. We synthesize
        # a coverage entry against HEAD lines 1-2 to mirror what from_diff
        # would produce for these committed lines.
        changes = ChangesSet()
        changes.add(py_file, 1, 2)

        # Now make uncommitted edits ABOVE helper(): add 3 blank/comment lines.
        # helper() now lives at working-tree lines 4-5, while it's still at
        # HEAD lines 1-2 in the changes_set.
        py_file.write_text(
            "# new comment 1\n"
            "# new comment 2\n"
            "# new comment 3\n"
            "def helper():\n"
            "    return 42\n"
        )

        template = tmp_path / "doc.md.j2"
        template.write_text("{{ code('mod.py', function='helper', github=False) }}\n")

        renderer = TemplateRenderer(template_dir=tmp_path, repo_path=tmp_path, changes_set=changes)
        renderer.render_template("doc.md.j2")

        # The bug: subtract(file, 4, 5) leaves HEAD lines 1-2 uncovered.
        # The fix: subtract maps working-tree 4-5 back to HEAD 1-2 and covers them.
        assert changes.is_complete(), (
            f"Coverage didn't cover the HEAD region; uncovered={changes.uncovered()}"
        )


def _init_git_repo(path):
    """Initialize a git repo and make an initial commit."""
    subprocess.check_call(["git", "init"], cwd=path, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.check_call(["git", "config", "user.email", "test@test.com"], cwd=path)
    subprocess.check_call(["git", "config", "user.name", "Test"], cwd=path)


def _git_commit(path, message="commit"):
    """Stage all and commit."""
    subprocess.check_call(["git", "add", "-A"], cwd=path, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.check_call(
        ["git", "commit", "-m", message], cwd=path, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )


def _git_rev(path, ref="HEAD"):
    """Get the commit hash for a ref."""
    return subprocess.check_output(["git", "rev-parse", ref], cwd=path).decode().strip()


class TestCodeContextRef:
    def test_code_ref_block(self, tmp_path):
        """{% code_context ref='...' %} extracts code from a git ref."""
        _init_git_repo(tmp_path)

        # First commit: v1 of the file
        py_file = tmp_path / "example.py"
        py_file.write_text("def hello():\n    return 'v1'\n")
        _git_commit(tmp_path, "v1")
        v1_hash = _git_rev(tmp_path)

        # Second commit: v2 of the file
        py_file.write_text("def hello():\n    return 'v2'\n")
        _git_commit(tmp_path, "v2")

        template = tmp_path / "doc.md.j2"
        template.write_text(
            "{%% code_context ref='%s' %%}\n"
            "{{ code('example.py', function='hello', github=False) }}\n"
            "{%% endcode_context %%}\n" % v1_hash
        )

        renderer = TemplateRenderer(template_dir=tmp_path, repo_path=tmp_path)
        result = renderer.render_template("doc.md.j2")
        assert "return 'v1'" in result
        assert "return 'v2'" not in result

    def test_code_ref_per_call(self, tmp_path):
        """code(..., ref='...') overrides on a per-call basis."""
        _init_git_repo(tmp_path)

        py_file = tmp_path / "example.py"
        py_file.write_text("def hello():\n    return 'v1'\n")
        _git_commit(tmp_path, "v1")
        v1_hash = _git_rev(tmp_path)

        py_file.write_text("def hello():\n    return 'v2'\n")
        _git_commit(tmp_path, "v2")

        template = tmp_path / "doc.md.j2"
        template.write_text("{{ code('example.py', function='hello', github=False, ref='%s') }}\n" % v1_hash)

        renderer = TemplateRenderer(template_dir=tmp_path, repo_path=tmp_path)
        result = renderer.render_template("doc.md.j2")
        assert "return 'v1'" in result
        assert "return 'v2'" not in result

    def test_code_ref_scoping(self, tmp_path):
        """code_ref reverts after {% endcode_context %}."""
        _init_git_repo(tmp_path)

        py_file = tmp_path / "example.py"
        py_file.write_text("def hello():\n    return 'v1'\n")
        _git_commit(tmp_path, "v1")
        v1_hash = _git_rev(tmp_path)

        py_file.write_text("def hello():\n    return 'v2'\n")
        _git_commit(tmp_path, "v2")

        template = tmp_path / "doc.md.j2"
        template.write_text(
            "{%% code_context ref='%s' %%}\n"
            "{{ code('example.py', function='hello', github=False) }}\n"
            "{%% endcode_context %%}\n"
            "{{ code('example.py', function='hello', github=False) }}\n" % v1_hash
        )

        renderer = TemplateRenderer(template_dir=tmp_path, repo_path=tmp_path)
        result = renderer.render_template("doc.md.j2")
        assert "return 'v1'" in result
        assert "return 'v2'" in result

    def test_code_ref_with_root(self, tmp_path):
        """{% code_context root='...' ref='...' %} combines both."""
        _init_git_repo(tmp_path)

        src_dir = tmp_path / "src"
        src_dir.mkdir()
        py_file = src_dir / "mod.py"
        py_file.write_text("def greet():\n    return 'old'\n")
        _git_commit(tmp_path, "v1")
        v1_hash = _git_rev(tmp_path)

        py_file.write_text("def greet():\n    return 'new'\n")
        _git_commit(tmp_path, "v2")

        template = tmp_path / "doc.md.j2"
        template.write_text(
            "{%% code_context root='src', ref='%s' %%}\n"
            "{{ code('mod.py', function='greet', github=False) }}\n"
            "{%% endcode_context %%}\n" % v1_hash
        )

        renderer = TemplateRenderer(template_dir=tmp_path, repo_path=tmp_path)
        result = renderer.render_template("doc.md.j2")
        assert "return 'old'" in result
        assert "return 'new'" not in result

    def test_code_ref_header_includes_ref(self, tmp_path):
        """When ref is active, header shows '@ ref' suffix."""
        _init_git_repo(tmp_path)

        py_file = tmp_path / "example.py"
        py_file.write_text("def hello():\n    pass\n")
        _git_commit(tmp_path, "v1")
        v1_hash = _git_rev(tmp_path)

        template = tmp_path / "doc.md.j2"
        template.write_text("{{ code('example.py', function='hello', github=False, ref='%s') }}\n" % v1_hash)

        renderer = TemplateRenderer(template_dir=tmp_path, repo_path=tmp_path)
        result = renderer.render_template("doc.md.j2")
        assert f"@ {v1_hash}" in result

    def test_set_code_context_ref(self, tmp_path):
        """{{ set_code_context(ref='...') }} sets ref globally."""
        _init_git_repo(tmp_path)

        py_file = tmp_path / "example.py"
        py_file.write_text("def hello():\n    return 'v1'\n")
        _git_commit(tmp_path, "v1")
        v1_hash = _git_rev(tmp_path)

        py_file.write_text("def hello():\n    return 'v2'\n")
        _git_commit(tmp_path, "v2")

        template = tmp_path / "doc.md.j2"
        template.write_text(
            "{{ set_code_context(ref='%s') }}\n{{ code('example.py', function='hello', github=False) }}\n" % v1_hash
        )

        renderer = TemplateRenderer(template_dir=tmp_path, repo_path=tmp_path)
        result = renderer.render_template("doc.md.j2")
        assert "return 'v1'" in result
        assert "return 'v2'" not in result

    def test_code_ref_per_call_overrides_context(self, tmp_path):
        """Per-call ref= overrides the context ref."""
        _init_git_repo(tmp_path)

        py_file = tmp_path / "example.py"
        py_file.write_text("def hello():\n    return 'v1'\n")
        _git_commit(tmp_path, "v1")
        v1_hash = _git_rev(tmp_path)

        py_file.write_text("def hello():\n    return 'v2'\n")
        _git_commit(tmp_path, "v2")
        v2_hash = _git_rev(tmp_path)

        py_file.write_text("def hello():\n    return 'v3'\n")
        _git_commit(tmp_path, "v3")

        template = tmp_path / "doc.md.j2"
        template.write_text(
            # Context sets v2, but per-call overrides to v1
            "{%% code_context ref='%s' %%}\n"
            "{{ code('example.py', function='hello', github=False, ref='%s') }}\n"
            "{%% endcode_context %%}\n" % (v2_hash, v1_hash)
        )

        renderer = TemplateRenderer(template_dir=tmp_path, repo_path=tmp_path)
        result = renderer.render_template("doc.md.j2")
        assert "return 'v1'" in result
        assert "return 'v2'" not in result
