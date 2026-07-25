"""
Regression tests for projected_source.cli.render.

Covers:
- FINDING 1: --collect-error-fixtures must write manifest.json even when
  rendering aborts via sys.exit(1) on a failed template.
- FINDING 4 (small CLI validation slice): bug-report rejects a directory
  argument with a Click usage error rather than crashing later.
- FINDING 5: rendering from stdin must surface render errors as a clean
  '[red]✗ Failed to render stdin' message + non-zero exit, not a traceback.
"""

import json
import subprocess

import pytest
from click.testing import CliRunner

from projected_source.cli import cli
from projected_source.core.renderer import TemplateRenderer


def _write_cpp_marker_source(path):
    path.write_text(
        "void f() {\n"
        "    int before = 0;\n"
        "    //@@start core\n"
        "    int shown = 1;\n"
        "    //@@end core\n"
        "    return;\n"
        "}\n"
    )


def test_line_numbers_do_not_add_trailing_space_to_blank_lines(tmp_path):
    renderer = TemplateRenderer(template_dir=tmp_path, repo_path=tmp_path)

    result = renderer._add_line_numbers("alpha\n\nbeta", 10)

    assert result.splitlines()[1] == "  11"


def test_collect_error_fixtures_writes_manifest_on_failure(tmp_path, monkeypatch):
    """
    When --collect-error-fixtures is on and a template fails to render,
    manifest.json must still be written (finalization runs in a finally block).
    """
    # Redirect the manifest output dir (which is package_dir/tests/fixtures/collected)
    # by pointing the package dir to tmp_path via the FixtureCollector module path.
    # Simpler: patch set_fixture_collector wiring by monkey-patching Path so the
    # write target is predictable — but easiest is to point render at a tmp dir
    # and inspect the package's default collection dir afterwards.
    #
    # Implementation note: the render command writes the manifest under
    # <package_root>/tests/fixtures/collected. Instead of fighting that path,
    # we patch Path(__file__).parent.parent.parent inside render via the
    # FixtureCollector itself.
    import importlib

    render_mod = importlib.import_module("projected_source.cli.render")

    fixtures_dir = tmp_path / "collected"

    real_set = render_mod.set_fixture_collector

    def fake_set(collector):
        if collector is not None:
            # Replace the output dir with our tmp dir so we don't pollute the repo.
            collector.output_dir = fixtures_dir
        real_set(collector)

    monkeypatch.setattr(render_mod, "set_fixture_collector", fake_set)

    # Create a template that will fail (references undefined macro).
    bad_template = tmp_path / "bad.md.j2"
    bad_template.write_text("{{ definitely_not_a_real_function() }}\n")

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "render",
            str(bad_template),
            "--collect-error-fixtures",
            "--repo-path",
            str(tmp_path),
        ],
    )

    # Render must have failed.
    assert result.exit_code != 0, result.output

    # Manifest must exist even though sys.exit fired in _render_file.
    manifest_path = fixtures_dir / "manifest.json"
    assert manifest_path.exists(), f"manifest not written; output:\n{result.output}"
    data = json.loads(manifest_path.read_text())
    assert "errors" in data
    assert "error_count" in data


def test_collect_error_fixtures_writes_manifest_with_zero_errors(tmp_path, monkeypatch):
    """Even with no errors, --collect-error-fixtures should leave a manifest behind."""
    import importlib

    render_mod = importlib.import_module("projected_source.cli.render")

    fixtures_dir = tmp_path / "collected"

    real_set = render_mod.set_fixture_collector

    def fake_set(collector):
        if collector is not None:
            collector.output_dir = fixtures_dir
        real_set(collector)

    monkeypatch.setattr(render_mod, "set_fixture_collector", fake_set)

    # A trivially-renderable template.
    good = tmp_path / "good.md.j2"
    good.write_text("hello world\n")

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "render",
            str(good),
            "--collect-error-fixtures",
            "--repo-path",
            str(tmp_path),
            "--no-header",
        ],
    )
    assert result.exit_code == 0, result.output

    manifest_path = fixtures_dir / "manifest.json"
    assert manifest_path.exists()
    data = json.loads(manifest_path.read_text())
    assert data["error_count"] == 0


def test_render_stdin_handles_template_error_cleanly(tmp_path):
    """
    A broken stdin template should produce a friendly error and exit non-zero,
    NOT raise a bare Jinja exception.
    """
    runner = CliRunner()
    bad_template = "{{ undefined_function_xyz() }}\n"

    result = runner.invoke(
        cli,
        [
            "render",
            "-",
            "-",
            "--repo-path",
            str(tmp_path),
            "--no-header",
        ],
        input=bad_template,
    )

    # Non-zero exit.
    assert result.exit_code != 0
    # Did not surface as an unhandled Python exception.
    assert result.exception is None or isinstance(result.exception, SystemExit), (
        f"stdin render raised uncaught exception: {result.exception!r}"
    )
    assert "Failed to render stdin" in result.output


def test_bug_report_rejects_directory_argument(tmp_path):
    """bug-report with a directory should fail at Click validation, not crash."""
    runner = CliRunner()
    result = runner.invoke(cli, ["bug-report", str(tmp_path), "Foo::bar"])

    assert result.exit_code != 0
    # Click's UsageError on a directory mentions "directory" or "file".
    assert "directory" in result.output.lower() or "is a directory" in result.output.lower()


def test_list_functions_rejects_directory_argument(tmp_path):
    """list-functions with a directory should fail at Click validation."""
    runner = CliRunner()
    result = runner.invoke(cli, ["list-functions", str(tmp_path)])

    assert result.exit_code != 0
    assert "directory" in result.output.lower() or "is a directory" in result.output.lower()


def _strip_ansi(text: str) -> str:
    import re

    return re.sub(r"\x1b\[[0-9;]*m", "", text)


def test_header_kept_after_yaml_frontmatter(tmp_path):
    """When the rendered body opens with YAML frontmatter, the metadata header
    must be inserted AFTER the closing `---`, leaving frontmatter on line 1."""
    runner = CliRunner()
    template = "---\ntitle: My Doc\ntags: [a, b]\n---\n\n# Heading\n\nbody text\n"

    result = runner.invoke(
        cli,
        ["render", "-", "-", "--repo-path", str(tmp_path)],
        input=template,
    )

    assert result.exit_code == 0, result.output
    out = _strip_ansi(result.output)
    lines = out.splitlines()

    # Frontmatter must still be first.
    assert lines[0] == "---", f"frontmatter not on line 1; got: {lines[:3]!r}"
    closing_idx = lines.index("---", 1)
    # The metadata header comment must appear AFTER the frontmatter's close.
    header_idx = next(i for i, ln in enumerate(lines) if ln.startswith("<!--"))
    assert header_idx > closing_idx, "metadata header leaked above/into frontmatter"
    # Frontmatter content stays intact and above the header.
    assert lines.index("title: My Doc") < closing_idx


def test_header_kept_after_included_frontmatter(tmp_path):
    """Top-level header handling runs after includes have rendered."""
    (tmp_path / "child.md").write_text("---\ntitle: Included\n---\n\n# Included\n")
    main = tmp_path / "main.md.j2"
    main.write_text("{{ include('child.md') }}\n\nBody\n")

    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["render", str(main), "-", "--repo-path", str(tmp_path)],
    )

    assert result.exit_code == 0, result.output
    out = _strip_ansi(result.output)
    lines = out.splitlines()

    assert lines[0] == "---"
    assert "title: Included" in lines
    closing_idx = lines.index("---", 1)
    header_idx = next(i for i, ln in enumerate(lines) if ln.startswith("<!--"))
    assert header_idx > closing_idx
    assert out.count("rendered_from: main.md.j2") == 1
    assert "rendered_from: child" not in out


def test_header_prepended_when_no_frontmatter(tmp_path):
    """A body that merely contains a `---` rule (but doesn't start with one) is
    not treated as frontmatter; the header is prepended at the very top."""
    runner = CliRunner()
    template = "# Title\n\nsome text\n\n---\n\nmore\n"

    result = runner.invoke(
        cli,
        ["render", "-", "-", "--repo-path", str(tmp_path)],
        input=template,
    )

    assert result.exit_code == 0, result.output
    out = _strip_ansi(result.output)
    assert out.lstrip().startswith("<!--"), f"header not prepended; got: {out[:40]!r}"


def test_render_html_uses_frontmatter_title_and_preserves_markdown_features(tmp_path):
    template = tmp_path / "design.md.j2"
    template.write_text(
        '---\ntitle: "Readable Design"\n---\n\n'
        "# Visible heading\n\n"
        "| A | B |\n|---|---|\n| 1 | 2 |\n\n"
        "```cpp\nint main() {}\n```\n\n"
        "<details><summary>Proof</summary>Body</details>\n"
    )

    result = CliRunner().invoke(
        cli,
        ["render", str(template), "--html", "--repo-path", str(tmp_path)],
    )

    assert result.exit_code == 0, result.output
    output = tmp_path / "design.html"
    rendered = output.read_text()
    assert rendered.startswith("<!doctype html>")
    assert "<title>Readable Design</title>" in rendered
    assert 'title: "Readable Design"' not in rendered
    assert '<h1 id="visible-heading">Visible heading</h1>' in rendered
    assert "<table>" in rendered
    assert '<code class="language-cpp">' in rendered
    assert "<details><summary>Proof</summary>Body</details>" in rendered
    assert "Last updated:" in rendered


def test_render_html_stdout_does_not_change_markdown_default(tmp_path):
    runner = CliRunner()
    template = "# Hello\n\nA **small** document.\n"

    markdown = runner.invoke(
        cli,
        ["render", "-", "-", "--repo-path", str(tmp_path), "--no-header"],
        input=template,
    )
    html_result = runner.invoke(
        cli,
        ["render", "-", "-", "--repo-path", str(tmp_path), "--no-header", "--html"],
        input=template,
    )
    explicit_markdown = runner.invoke(
        cli,
        ["render", "-", "-", "--repo-path", str(tmp_path), "--no-header", "--no-html"],
        input=template,
    )

    assert markdown.exit_code == 0, markdown.output
    assert markdown.output == template
    assert explicit_markdown.exit_code == 0, explicit_markdown.output
    assert explicit_markdown.output == markdown.output
    assert html_result.exit_code == 0, html_result.output
    assert "<title>Hello</title>" in html_result.output
    assert '<h1 id="hello">Hello</h1>' in html_result.output
    assert "<strong>small</strong>" in html_result.output


def test_render_html_directory_maps_markdown_templates_to_html(tmp_path):
    templates = tmp_path / "templates"
    output = tmp_path / "site"
    templates.mkdir()
    (templates / "guide.md.j2").write_text("# Guide\n")
    (templates / "notes.j2").write_text("# Notes\n")

    result = CliRunner().invoke(
        cli,
        [
            "render",
            str(templates),
            str(output),
            "--html",
            "--no-header",
            "--repo-path",
            str(tmp_path),
        ],
    )

    assert result.exit_code == 0, result.output
    assert (output / "guide.html").exists()
    assert (output / "notes.html").exists()
    assert not (output / "guide.md").exists()


def test_render_watch_renders_initially_and_after_change(tmp_path, monkeypatch):
    import importlib

    render_mod = importlib.import_module("projected_source.cli.render")
    template = tmp_path / "watched.md.j2"
    output = tmp_path / "watched.md"
    source = tmp_path / "source.txt"
    source.write_text("first")
    template.write_text("{{ include('source.txt') }}\n")

    def fake_watch(*roots, **kwargs):
        assert tmp_path.resolve() in roots
        source.write_text("second")
        yield {(1, str(source))}

    monkeypatch.setattr(render_mod, "watch", fake_watch)
    result = CliRunner().invoke(
        cli,
        ["render", str(template), "--watch", "--no-header", "--repo-path", str(tmp_path)],
    )

    assert result.exit_code == 0, result.output
    assert output.read_text() == "second"
    assert "Watching" in result.output
    assert "1 change(s); rendering" in _strip_ansi(result.output)


def test_render_watch_recovers_after_render_error(tmp_path, monkeypatch):
    import importlib

    render_mod = importlib.import_module("projected_source.cli.render")
    template = tmp_path / "broken.md.j2"
    output = tmp_path / "broken.md"
    template.write_text("{{ missing_function() }}\n")

    def fake_watch(*roots, **kwargs):
        template.write_text("recovered\n")
        yield {(1, str(template))}

    monkeypatch.setattr(render_mod, "watch", fake_watch)
    result = CliRunner().invoke(
        cli,
        ["render", str(template), "--watch", "--no-header", "--repo-path", str(tmp_path)],
    )

    assert result.exit_code == 0, result.output
    assert "Failed to render" in result.output
    assert output.read_text() == "recovered"


@pytest.mark.parametrize(
    "args,input_text,error",
    [
        (["-", "-", "--watch"], "hello\n", "requires a file or directory input"),
        (["template.md.j2", "-", "--watch"], None, "requires file or directory output"),
        (["template.md.j2", "--watch", "--commit", "HEAD"], None, "cannot be combined with --commit"),
    ],
)
def test_render_watch_rejects_incompatible_modes(tmp_path, args, input_text, error):
    (tmp_path / "template.md.j2").write_text("hello\n")
    result = CliRunner().invoke(
        cli,
        ["render", *args, "--repo-path", str(tmp_path)],
        input=input_text,
    )

    assert result.exit_code != 0
    assert error in result.output


def test_render_enclosure_context_default(tmp_path):
    """Marker-only code() calls get enclosure context by default."""
    source = tmp_path / "example.cpp"
    _write_cpp_marker_source(source)

    template = "{{ code('example.cpp', marker='core', github=False) }}\n"
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "render",
            "-",
            "-",
            "--repo-path",
            str(tmp_path),
            "--no-header",
        ],
        input=template,
    )

    assert result.exit_code == 0, result.output
    assert "   1 void f() {" in result.output
    assert "   2     int before = 0;" in result.output
    assert "   4     int shown = 1;" in result.output
    assert "   6     return;" in result.output
    assert "   7 }" in result.output


def test_render_enclosure_context_cli_default_can_be_overridden(tmp_path):
    """Per-call enclosure_context=0 opts out of the default."""
    source = tmp_path / "example.cpp"
    _write_cpp_marker_source(source)

    template = "{{ code('example.cpp', marker='core', enclosure_context=0, github=False) }}\n"
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "render",
            "-",
            "-",
            "--repo-path",
            str(tmp_path),
            "--no-header",
        ],
        input=template,
    )

    assert result.exit_code == 0, result.output
    assert "void f()" not in result.output
    assert "   4     int shown = 1;" in result.output


def test_render_enclosure_context_cli_option_can_change_default(tmp_path):
    """--enclosure-context overrides the built-in marker context default."""
    source = tmp_path / "example.cpp"
    _write_cpp_marker_source(source)

    template = "{{ code('example.cpp', marker='core', github=False) }}\n"
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "render",
            "-",
            "-",
            "--repo-path",
            str(tmp_path),
            "--no-header",
            "--enclosure-context",
            "1",
        ],
        input=template,
    )

    assert result.exit_code == 0, result.output
    assert "   1 void f() {" in result.output
    assert "   2     int before = 0;" not in result.output
    assert "   4     int shown = 1;" in result.output
    assert "   6     return;" not in result.output
    assert "   7 }" in result.output


def test_render_enclosure_context_cli_zero_disables_default(tmp_path):
    """--enclosure-context 0 globally disables default marker enclosure context."""
    source = tmp_path / "example.cpp"
    _write_cpp_marker_source(source)

    template = "{{ code('example.cpp', marker='core', github=False) }}\n"
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "render",
            "-",
            "-",
            "--repo-path",
            str(tmp_path),
            "--no-header",
            "--enclosure-context",
            "0",
        ],
        input=template,
    )

    assert result.exit_code == 0, result.output
    assert "void f()" not in result.output
    assert "int before" not in result.output
    assert "   4     int shown = 1;" in result.output
    assert "return;" not in result.output


def test_render_enclosure_context_cli_option_applies_to_file_render(tmp_path):
    """The CLI option is threaded through single-file rendering."""
    source = tmp_path / "example.cpp"
    _write_cpp_marker_source(source)
    template = tmp_path / "doc.md.j2"
    output = tmp_path / "doc.md"
    template.write_text("{{ code('example.cpp', marker='core', github=False) }}\n")

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "render",
            str(template),
            str(output),
            "--repo-path",
            str(tmp_path),
            "--no-header",
            "--enclosure-context",
            "1",
        ],
    )

    assert result.exit_code == 0, result.output
    rendered = output.read_text()
    assert "   1 void f() {" in rendered
    assert "   2     int before = 0;" not in rendered
    assert "   4     int shown = 1;" in rendered
    assert "   7 }" in rendered


def test_render_enclosure_context_cli_option_applies_to_directory_render(tmp_path):
    """The CLI option is threaded through directory rendering."""
    source = tmp_path / "example.cpp"
    _write_cpp_marker_source(source)
    templates = tmp_path / "templates"
    outputs = tmp_path / "out"
    templates.mkdir()
    (templates / "doc.md.j2").write_text("{{ code('example.cpp', marker='core', github=False) }}\n")

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "render",
            str(templates),
            str(outputs),
            "--repo-path",
            str(tmp_path),
            "--no-header",
            "--enclosure-context",
            "0",
        ],
    )

    assert result.exit_code == 0, result.output
    rendered = (outputs / "doc.md").read_text()
    assert "void f()" not in rendered
    assert "int before" not in rendered
    assert "   4     int shown = 1;" in rendered
    assert "return;" not in rendered


@pytest.mark.parametrize(
    ("filename", "source", "inside", "outside"),
    [
        ("example.py", "# before\n#@@start section\nx = 1\n#@@end section\n# after\n", "x = 1", "# before"),
        (
            "Example.java",
            "class Example {\n"
            "  int before = 0;\n"
            "  //@@start section\n"
            "  int value = 1;\n"
            "  //@@end section\n"
            "  int after = 2;\n"
            "}\n",
            "int value = 1;",
            "int before = 0;",
        ),
        (
            "example.ts",
            "const before = 0;\n"
            "//@@start section\n"
            "const value = 1;\n"
            "//@@end section\n"
            "const after = 2;\n",
            "const value = 1;",
            "const before = 0;",
        ),
        (
            "example.rs",
            "fn main() {\n"
            "    let before = 0;\n"
            "    //@@start section\n"
            "    let value = 1;\n"
            "    //@@end section\n"
            "    let after = 2;\n"
            "}\n",
            "let value = 1;",
            "let before = 0;",
        ),
        (
            "Example.lean",
            "def before := 0\n"
            "-- @@start section\n"
            "def value := 1\n"
            "-- @@end section\n"
            "def after := 2\n",
            "def value := 1",
            "def before := 0",
        ),
        (
            "example.proto",
            'syntax = "proto3";\n'
            "message Before { string value = 1; }\n"
            "//@@start section\n"
            "message Value { string value = 1; }\n"
            "//@@end section\n"
            "message After { string value = 1; }\n",
            "message Value",
            "message Before",
        ),
    ],
)
def test_default_enclosure_context_falls_back_to_exact_marker_for_non_cpp(
    tmp_path, filename, source, inside, outside
):
    """The built-in default is C++-only today; other languages keep exact markers."""
    path = tmp_path / filename
    path.write_text(source)
    renderer = TemplateRenderer(template_dir=tmp_path, repo_path=tmp_path)

    result = renderer._code_function(filename, marker="section", github=False)

    assert "❌ **ERROR**" not in result
    assert inside in result
    assert outside not in result
    assert "@@start" not in result
    assert "@@end" not in result


def test_explicit_enclosure_context_errors_for_unsupported_marker_language(tmp_path):
    source = tmp_path / "example.py"
    source.write_text("#@@start section\nx = 1\n#@@end section\n")
    renderer = TemplateRenderer(template_dir=tmp_path, repo_path=tmp_path)

    result = renderer._code_function("example.py", marker="section", enclosure_context=1, github=False)

    assert "❌ **ERROR**" in result
    assert "Auto marker enclosure not supported" in result


def test_explicit_auto_enclosure_errors_for_unsupported_marker_language(tmp_path):
    source = tmp_path / "example.py"
    source.write_text("#@@start section\nx = 1\n#@@end section\n")
    renderer = TemplateRenderer(template_dir=tmp_path, repo_path=tmp_path)

    result = renderer._code_function("example.py", marker="section", enclosure="auto", github=False)

    assert "❌ **ERROR**" in result
    assert "Auto marker enclosure not supported" in result


def test_explicit_auto_enclosure_errors_even_when_context_is_zero_for_unsupported_language(tmp_path):
    source = tmp_path / "example.py"
    source.write_text("#@@start section\nx = 1\n#@@end section\n")
    renderer = TemplateRenderer(template_dir=tmp_path, repo_path=tmp_path)

    result = renderer._code_function(
        "example.py",
        marker="section",
        enclosure="auto",
        enclosure_context=0,
        github=False,
    )

    assert "❌ **ERROR**" in result
    assert "Auto marker enclosure not supported" in result


def test_explicit_auto_enclosure_with_zero_context_uses_cpp_enclosure_support(tmp_path):
    source = tmp_path / "example.cpp"
    source.write_text(
        "void f() {\n"
        "    //@@start core\n"
        "    int shown = 1;\n"
        "    //@@end core\n"
        "}\n"
    )
    renderer = TemplateRenderer(template_dir=tmp_path, repo_path=tmp_path)

    result = renderer._code_function(
        "example.cpp",
        marker="core",
        enclosure="auto",
        enclosure_context=0,
        github=False,
    )

    assert "❌ **ERROR**" not in result
    assert "`example.cpp:3`" in result
    assert "   3     int shown = 1;" in result
    assert "void f()" not in result


def test_default_enclosure_context_falls_back_for_non_cpp_function_marker(tmp_path):
    source = tmp_path / "example.rs"
    source.write_text(
        "fn worker() {\n"
        "    let before = 0;\n"
        "    //@@start inner\n"
        "    let payload = 1;\n"
        "    //@@end inner\n"
        "    let after = 2;\n"
        "}\n"
    )
    renderer = TemplateRenderer(template_dir=tmp_path, repo_path=tmp_path)

    result = renderer._code_function("example.rs", function="worker", marker="inner", github=False)

    assert "❌ **ERROR**" not in result
    assert "let payload = 1;" in result
    assert "fn worker()" not in result
    assert "let before" not in result
    assert "let after" not in result


def test_explicit_enclosure_context_errors_for_non_cpp_function_marker(tmp_path):
    source = tmp_path / "example.rs"
    source.write_text(
        "fn worker() {\n"
        "    //@@start inner\n"
        "    let payload = 1;\n"
        "    //@@end inner\n"
        "}\n"
    )
    renderer = TemplateRenderer(template_dir=tmp_path, repo_path=tmp_path)

    result = renderer._code_function(
        "example.rs",
        function="worker",
        marker="inner",
        enclosure_context=1,
        github=False,
    )

    assert "❌ **ERROR**" in result
    assert "Function marker enclosure not supported" in result


def test_explicit_message_marker_enclosure_errors_for_proto(tmp_path):
    source = tmp_path / "example.proto"
    source.write_text(
        'syntax = "proto3";\n'
        "message Envelope {\n"
        "  //@@start field\n"
        "  string value = 1;\n"
        "  //@@end field\n"
        "}\n"
    )
    renderer = TemplateRenderer(template_dir=tmp_path, repo_path=tmp_path)

    result = renderer._code_function(
        "example.proto",
        message="Envelope",
        marker="field",
        enclosure_context=1,
        github=False,
    )

    assert "❌ **ERROR**" in result
    assert "Message marker enclosure not supported" in result


def test_enclosure_auto_requires_marker(tmp_path):
    source = tmp_path / "example.cpp"
    _write_cpp_marker_source(source)
    renderer = TemplateRenderer(template_dir=tmp_path, repo_path=tmp_path)

    result = renderer._code_function("example.cpp", function="f", enclosure="auto", github=False)

    assert "❌ **ERROR**" in result
    assert "enclosure requires marker=" in result


def _git(repo, *args):
    import subprocess
    subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=True)


def test_min_density_span_floor_exempts_small_extracts(tmp_path, monkeypatch):
    """The density gate must not flag extracts too small to be dumps.

    A 4-line extract at 25% is one changed line, not padding; only the large
    mostly-unchanged extract should be reported once min_density_span is set."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))  # isolate user config
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "t@t.com")
    _git(repo, "config", "user.name", "T")

    big_body = "\n".join(f"    int a{i} = {i};" for i in range(30))
    src = repo / "file.cpp"
    src.write_text(
        f"int big() {{\n{big_body}\n    return a0;\n}}\n\n"
        "int small() {\n    int s = 0;\n    return s;\n}\n"
    )
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "base")
    base = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True, check=True
    ).stdout.strip()
    # one changed line in each function → big ~3% density (span 32), small 25% (span 4)
    src.write_text(
        src.read_text().replace("int a0 = 0;", "int a0 = 999;").replace("int s = 0;", "int s = 7;")
    )
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "change")

    (repo / ".projected-source.toml").write_text(
        "[validation]\nmin_density = 0.5\nmin_density_span = 10\n"
    )
    tpl = repo / "doc.md.j2"
    tpl.write_text(
        "{{ code('file.cpp', function='big', github=False) }}\n"
        "{{ code('file.cpp', function='small', github=False) }}\n"
    )

    result = CliRunner().invoke(
        cli, ["render", str(tpl), str(tmp_path / "out.md"), "-r", str(repo), "--no-header", "-V", base]
    )
    out = _strip_ansi(result.output)
    assert "below min_density" in out, out
    assert "file.cpp:1-33 (3%)" in out  # the large mostly-unchanged extract is flagged
    # the tiny small() extract (span 4 < 10) must NOT appear as a dump
    assert "(25%)" not in out, out
