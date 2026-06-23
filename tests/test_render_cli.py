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

from click.testing import CliRunner

from projected_source.cli import cli


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
