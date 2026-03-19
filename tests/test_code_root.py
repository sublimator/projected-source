"""Tests for {% code_root %} block extension."""

from projected_source.core.changes_set import ChangesSet
from projected_source.core.renderer import TemplateRenderer


class TestCodeRoot:
    def test_code_root_block(self, tmp_path):
        """{% code_root %} prepends path to code() file paths."""
        src_dir = tmp_path / "src" / "app"
        src_dir.mkdir(parents=True)
        (src_dir / "handler.py").write_text("def process():\n    return 42\n")

        template = tmp_path / "doc.md.j2"
        template.write_text(
            "{% code_root 'src/app' %}\n"
            "{{ code('handler.py', function='process', github=False) }}\n"
            "{% endcode_root %}\n"
        )

        renderer = TemplateRenderer(template_dir=tmp_path, repo_path=tmp_path)
        result = renderer.render_template("doc.md.j2")
        assert "def process():" in result
        assert "return 42" in result

    def test_code_root_scoping(self, tmp_path):
        """code_root reverts after {% endcode_root %}."""
        src_dir = tmp_path / "src" / "app"
        src_dir.mkdir(parents=True)
        (src_dir / "handler.py").write_text("def process():\n    return 42\n")
        (tmp_path / "top.py").write_text("def top_level():\n    pass\n")

        template = tmp_path / "doc.md.j2"
        template.write_text(
            "{% code_root 'src/app' %}\n"
            "{{ code('handler.py', function='process', github=False) }}\n"
            "{% endcode_root %}\n"
            "{{ code('top.py', function='top_level', github=False) }}\n"
        )

        renderer = TemplateRenderer(template_dir=tmp_path, repo_path=tmp_path)
        result = renderer.render_template("doc.md.j2")
        assert "def process():" in result
        assert "def top_level():" in result

    def test_code_root_nesting(self, tmp_path):
        """Nested {% code_root %} blocks override and restore correctly."""
        (tmp_path / "a").mkdir()
        (tmp_path / "a" / "b").mkdir()
        (tmp_path / "a" / "one.py").write_text("def one():\n    pass\n")
        (tmp_path / "a" / "b" / "two.py").write_text("def two():\n    pass\n")

        template = tmp_path / "doc.md.j2"
        template.write_text(
            "{% code_root 'a' %}\n"
            "{{ code('one.py', function='one', github=False) }}\n"
            "{% code_root 'a/b' %}\n"
            "{{ code('two.py', function='two', github=False) }}\n"
            "{% endcode_root %}\n"
            "{% endcode_root %}\n"
        )

        renderer = TemplateRenderer(template_dir=tmp_path, repo_path=tmp_path)
        result = renderer.render_template("doc.md.j2")
        assert "def one():" in result
        assert "def two():" in result

    def test_code_root_does_not_affect_absolute_paths(self, tmp_path):
        """Absolute paths bypass code_root."""
        (tmp_path / "example.py").write_text("def hello():\n    pass\n")

        abs_path = str(tmp_path / "example.py")
        template = tmp_path / "doc.md.j2"
        template.write_text(
            "{%% code_root 'nonexistent/dir' %%}\n"
            "{{ code('%s', function='hello', github=False) }}\n"
            "{%% endcode_root %%}\n" % abs_path
        )

        renderer = TemplateRenderer(template_dir=tmp_path, repo_path=tmp_path)
        result = renderer.render_template("doc.md.j2")
        assert "def hello():" in result

    def test_code_root_with_trailing_slash(self, tmp_path):
        """Trailing slash on code_root works fine."""
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "mod.py").write_text("x = 1\n")

        template = tmp_path / "doc.md.j2"
        template.write_text("{% code_root 'src/' %}\n{{ code('mod.py', var='x', github=False) }}\n{% endcode_root %}\n")

        renderer = TemplateRenderer(template_dir=tmp_path, repo_path=tmp_path)
        result = renderer.render_template("doc.md.j2")
        assert "x = 1" in result

    def test_without_code_root(self, tmp_path):
        """Without code_root, paths resolve from repo root as before."""
        (tmp_path / "example.py").write_text("def hello():\n    pass\n")

        template = tmp_path / "doc.md.j2"
        template.write_text("{{ code('example.py', function='hello', github=False) }}\n")

        renderer = TemplateRenderer(template_dir=tmp_path, repo_path=tmp_path)
        result = renderer.render_template("doc.md.j2")
        assert "def hello():" in result

    def test_set_code_root_function(self, tmp_path):
        """{{ set_code_root() }} sets the root globally."""
        src_dir = tmp_path / "src" / "app"
        src_dir.mkdir(parents=True)
        (src_dir / "handler.py").write_text("def process():\n    return 42\n")

        template = tmp_path / "doc.md.j2"
        template.write_text(
            "{{ set_code_root('src/app') }}\n{{ code('handler.py', function='process', github=False) }}\n"
        )

        renderer = TemplateRenderer(template_dir=tmp_path, repo_path=tmp_path)
        result = renderer.render_template("doc.md.j2")
        assert "def process():" in result

    def test_set_code_root_clear(self, tmp_path):
        """{{ set_code_root('') }} clears the root."""
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "a.py").write_text("def a():\n    pass\n")
        (tmp_path / "b.py").write_text("def b():\n    pass\n")

        template = tmp_path / "doc.md.j2"
        template.write_text(
            "{{ set_code_root('src') }}\n"
            "{{ code('a.py', function='a', github=False) }}\n"
            "{{ set_code_root('') }}\n"
            "{{ code('b.py', function='b', github=False) }}\n"
        )

        renderer = TemplateRenderer(template_dir=tmp_path, repo_path=tmp_path)
        result = renderer.render_template("doc.md.j2")
        assert "def a():" in result
        assert "def b():" in result

    def test_ignore_changes_respects_code_root(self, tmp_path):
        """ignore_changes() also resolves via code_root."""
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        py_file = src_dir / "mod.py"
        py_file.write_text("def foo():\n    pass\n")

        changes = ChangesSet()
        changes.add(py_file, 1, 2)

        template = tmp_path / "doc.md.j2"
        template.write_text("{% code_root 'src' %}\n{{ ignore_changes('mod.py') }}\n{% endcode_root %}\n")

        renderer = TemplateRenderer(template_dir=tmp_path, repo_path=tmp_path, changes_set=changes)
        renderer.render_template("doc.md.j2")
        assert changes.is_complete()
