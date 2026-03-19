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
