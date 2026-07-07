#!/usr/bin/env python3
"""
Test suite for the include() template function.
"""

import pytest

from projected_source.core.renderer import TemplateRenderer


class TestIncludeRaw:
    """Test raw .md file inclusion."""

    def test_include_raw_md(self, tmp_path):
        """Test including a raw markdown file."""
        (tmp_path / "section.md").write_text("# Hello World\n\nSome content.")
        (tmp_path / "main.md.j2").write_text("Before\n{{ include('section.md') }}\nAfter")

        renderer = TemplateRenderer(template_dir=tmp_path, repo_path=tmp_path)
        result = renderer.render_template("main.md.j2")

        assert "Before" in result
        assert "# Hello World" in result
        assert "Some content." in result
        assert "After" in result

    def test_include_raw_preserves_content(self, tmp_path):
        """Test that raw include does not process Jinja2 syntax."""
        (tmp_path / "raw.md").write_text("{{ this_is_not_a_variable }}")
        (tmp_path / "main.md.j2").write_text("{{ include('raw.md') }}")

        renderer = TemplateRenderer(template_dir=tmp_path, repo_path=tmp_path)
        result = renderer.render_template("main.md.j2")

        assert "{{ this_is_not_a_variable }}" in result

    def test_include_raw_txt(self, tmp_path):
        """Test including a non-markdown file."""
        (tmp_path / "data.txt").write_text("line1\nline2")
        (tmp_path / "main.md.j2").write_text("{{ include('data.txt') }}")

        renderer = TemplateRenderer(template_dir=tmp_path, repo_path=tmp_path)
        result = renderer.render_template("main.md.j2")

        assert "line1\nline2" in result


class TestIncludeTemplate:
    """Test .j2 template inclusion."""

    def test_include_j2_rendered(self, tmp_path):
        """Test that .j2 files are rendered as templates."""
        (tmp_path / "part.md.j2").write_text("Value: {{ 1 + 1 }}")
        (tmp_path / "main.md.j2").write_text("{{ include('part.md.j2') }}")

        renderer = TemplateRenderer(template_dir=tmp_path, repo_path=tmp_path)
        result = renderer.render_template("main.md.j2")

        assert "Value: 2" in result

    def test_include_j2_has_code_function(self, tmp_path):
        """Test that included .j2 templates can use code()."""
        # Create a source file to extract from
        (tmp_path / "test.cpp").write_text("void hello() {\n    return;\n}\n")

        (tmp_path / "part.md.j2").write_text("{{ code('test.cpp', function='hello', github=False) }}")
        (tmp_path / "main.md.j2").write_text("{{ include('part.md.j2') }}")

        renderer = TemplateRenderer(template_dir=tmp_path, repo_path=tmp_path)
        result = renderer.render_template("main.md.j2")

        assert "void hello()" in result

    def test_include_j2_nested(self, tmp_path):
        """Test nested includes (a.j2 includes b.j2 includes c.md)."""
        (tmp_path / "c.md").write_text("leaf content")
        (tmp_path / "b.md.j2").write_text("middle {{ include('c.md') }}")
        (tmp_path / "a.md.j2").write_text("top {{ include('b.md.j2') }}")

        renderer = TemplateRenderer(template_dir=tmp_path, repo_path=tmp_path)
        result = renderer.render_template("a.md.j2")

        assert "top middle leaf content" in result

    def test_include_j2_gets_caller_context(self, tmp_path):
        """Included templates can see variables from the parent render."""
        (tmp_path / "part.md.j2").write_text("{{ title }} / {{ local_title }}")
        (tmp_path / "main.md.j2").write_text(
            "{% set local_title = 'Local' %}{{ include('part.md.j2') }}"
        )

        renderer = TemplateRenderer(template_dir=tmp_path, repo_path=tmp_path)
        result = renderer.render_template("main.md.j2", title="Outer")

        assert result == "Outer / Local"

    def test_include_preserves_included_frontmatter(self, tmp_path):
        """include() preserves standalone-doc wrappers verbatim."""
        (tmp_path / "part.md.j2").write_text("---\ntitle: Included\n---\n\n# Body")
        (tmp_path / "main.md.j2").write_text("{{ include('part.md.j2') }}")

        renderer = TemplateRenderer(template_dir=tmp_path, repo_path=tmp_path)
        result = renderer.render_template("main.md.j2")

        assert result.startswith("---\ntitle: Included\n---")
        assert "# Body" in result

    def test_include_preserves_projected_source_header(self, tmp_path):
        """Raw include() does not strip a previously rendered projected-source header."""
        rendered = (
            "<!--\n"
            "rendered_from: child.md.j2\n"
            "rendered_at: 2026-07-07T00:00:00Z\n"
            "branch: main\n"
            "commit: abc123\n"
            "commit_message: msg\n"
            "-->\n\n"
            "---\n\n"
            "<sub>Last updated: 2026-07-07 | branch: main | commit: abc123 (msg)</sub>\n\n"
            "---\n\n"
            "# Child\n"
        )
        (tmp_path / "child.md").write_text(rendered)
        (tmp_path / "main.md.j2").write_text("{{ include('child.md') }}")

        renderer = TemplateRenderer(template_dir=tmp_path, repo_path=tmp_path)
        result = renderer.render_template("main.md.j2")

        assert "rendered_from: child.md.j2" in result
        assert "Last updated: 2026-07-07" in result
        assert "# Child" in result


class TestIncludeBody:
    """Test body-only document inclusion."""

    def test_include_body_renders_j2_and_strips_frontmatter(self, tmp_path):
        (tmp_path / "part.md.j2").write_text("---\ntitle: Included\n---\n\n# Body {{ 2 + 2 }}")
        (tmp_path / "main.md.j2").write_text("Before\n{{ include_body('part.md.j2') }}\nAfter")

        renderer = TemplateRenderer(template_dir=tmp_path, repo_path=tmp_path)
        result = renderer.render_template("main.md.j2")

        assert "Before" in result
        assert "title: Included" not in result
        assert "# Body 4" in result
        assert "After" in result

    def test_include_body_j2_gets_caller_context(self, tmp_path):
        (tmp_path / "part.md.j2").write_text("---\ntitle: Included\n---\n\n# {{ title }}")
        (tmp_path / "main.md.j2").write_text("{{ include_body('part.md.j2') }}")

        renderer = TemplateRenderer(template_dir=tmp_path, repo_path=tmp_path)
        result = renderer.render_template("main.md.j2", title="Rendered")

        assert result == "# Rendered"

    def test_include_body_raw_preserves_jinja_syntax(self, tmp_path):
        (tmp_path / "part.md").write_text(
            "---\ntitle: Included\n---\n\n{{ this_is_not_rendered }}\n"
        )
        (tmp_path / "main.md.j2").write_text("{{ include_body('part.md') }}")

        renderer = TemplateRenderer(template_dir=tmp_path, repo_path=tmp_path)
        result = renderer.render_template("main.md.j2")

        assert "title: Included" not in result
        assert "{{ this_is_not_rendered }}" in result

    def test_include_body_strips_projected_source_header(self, tmp_path):
        rendered = (
            "<!--\n"
            "rendered_from: child.md.j2\n"
            "rendered_at: 2026-07-07T00:00:00Z\n"
            "branch: main\n"
            "commit: abc123\n"
            "commit_message: msg\n"
            "-->\n\n"
            "---\n\n"
            "<sub>Last updated: 2026-07-07 | branch: main | commit: abc123 (msg)</sub>\n\n"
            "---\n\n"
            "# Child\n"
        )
        (tmp_path / "child.md").write_text(rendered)
        (tmp_path / "main.md.j2").write_text("{{ include_body('child.md') }}")

        renderer = TemplateRenderer(template_dir=tmp_path, repo_path=tmp_path)
        result = renderer.render_template("main.md.j2")

        assert "rendered_from:" not in result
        assert "Last updated:" not in result
        assert result == "# Child\n"

    def test_include_body_strips_only_one_frontmatter_and_one_header(self, tmp_path):
        rendered = (
            "---\n"
            "title: Standalone\n"
            "---\n\n"
            "<!--\n"
            "rendered_from: child.md.j2\n"
            "rendered_at: 2026-07-07T00:00:00Z\n"
            "-->\n\n"
            "---\n\n"
            "<sub>Last updated: 2026-07-07</sub>\n\n"
            "---\n\n"
            "---\n"
            "body: keep\n"
            "---\n\n"
            "# Child\n"
        )
        (tmp_path / "child.md").write_text(rendered)
        (tmp_path / "main.md.j2").write_text("{{ include_body('child.md') }}")

        renderer = TemplateRenderer(template_dir=tmp_path, repo_path=tmp_path)
        result = renderer.render_template("main.md.j2")

        assert result == "---\nbody: keep\n---\n\n# Child\n"

    def test_include_body_strips_frontmatter_before_projected_source_header(self, tmp_path):
        rendered = (
            "---\n"
            "title: Standalone\n"
            "---\n\n"
            "<!--\n"
            "rendered_from: child.md.j2\n"
            "rendered_at: 2026-07-07T00:00:00Z\n"
            "-->\n\n"
            "---\n\n"
            "<sub>Last updated: 2026-07-07</sub>\n\n"
            "---\n\n"
            "# Child\n"
        )
        (tmp_path / "child.md").write_text(rendered)
        (tmp_path / "main.md.j2").write_text("{{ include_body('child.md') }}")

        renderer = TemplateRenderer(template_dir=tmp_path, repo_path=tmp_path)
        result = renderer.render_template("main.md.j2")

        assert "title: Standalone" not in result
        assert "rendered_from:" not in result
        assert "Last updated:" not in result
        assert result == "# Child\n"


class TestIncludeSubdirectory:
    """Test includes from subdirectories."""

    def test_include_from_subdir(self, tmp_path):
        """Test including a file from a subdirectory."""
        sub = tmp_path / "sections"
        sub.mkdir()
        (sub / "intro.md").write_text("# Introduction")
        (tmp_path / "main.md.j2").write_text("{{ include('sections/intro.md') }}")

        renderer = TemplateRenderer(template_dir=tmp_path, repo_path=tmp_path)
        result = renderer.render_template("main.md.j2")

        assert "# Introduction" in result

    def test_include_j2_from_subdir(self, tmp_path):
        """Test including a .j2 template from a subdirectory."""
        sub = tmp_path / "parts"
        sub.mkdir()
        (sub / "header.md.j2").write_text("Header: {{ 2 + 2 }}")
        (tmp_path / "main.md.j2").write_text("{{ include('parts/header.md.j2') }}")

        renderer = TemplateRenderer(template_dir=tmp_path, repo_path=tmp_path)
        result = renderer.render_template("main.md.j2")

        assert "Header: 4" in result


class TestIncludeErrors:
    """Test error handling."""

    def test_include_missing_file(self, tmp_path):
        """Test that including a missing file raises an error."""
        (tmp_path / "main.md.j2").write_text("{{ include('nonexistent.md') }}")

        renderer = TemplateRenderer(template_dir=tmp_path, repo_path=tmp_path)
        with pytest.raises(Exception):
            renderer.render_template("main.md.j2")

    def test_include_missing_j2(self, tmp_path):
        """Test that including a missing .j2 file raises an error."""
        (tmp_path / "main.md.j2").write_text("{{ include('nonexistent.md.j2') }}")

        renderer = TemplateRenderer(template_dir=tmp_path, repo_path=tmp_path)
        with pytest.raises(Exception):
            renderer.render_template("main.md.j2")


class TestIncludeMultiple:
    """Test multiple includes in one template."""

    def test_multiple_includes(self, tmp_path):
        """Test including multiple files in one template."""
        (tmp_path / "header.md").write_text("# Header")
        (tmp_path / "body.md.j2").write_text("Body: {{ 3 * 3 }}")
        (tmp_path / "footer.md").write_text("---\nFooter")
        (tmp_path / "main.md.j2").write_text(
            "{{ include('header.md') }}\n\n{{ include('body.md.j2') }}\n\n{{ include('footer.md') }}"
        )

        renderer = TemplateRenderer(template_dir=tmp_path, repo_path=tmp_path)
        result = renderer.render_template("main.md.j2")

        assert "# Header" in result
        assert "Body: 9" in result
        assert "Footer" in result
