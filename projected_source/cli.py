"""
Command-line interface for projected-source.
"""

import json
import logging
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Set

import click
from rich.console import Console
from rich.table import Table

from . import setup_logging
from .core.renderer import TemplateRenderer

logger = logging.getLogger(__name__)
console = Console()

# Global fixture collector for error collection mode
_fixture_collector = None


class FixtureCollector:
    """Collects error-causing files as test fixtures."""

    def __init__(self, output_dir: Path):
        self.output_dir = output_dir
        self.errors: List[Dict[str, Any]] = []
        self.copied_files: Set[Path] = set()

    def collect(self, source_file: Path, error: str, template_context: str = None):
        """
        Collect a file that caused an error.

        Args:
            source_file: Path to the file that caused the error
            error: Error message
            template_context: Template that triggered the error
        """
        if not source_file.exists():
            return

        # Create a unique fixture name
        fixture_name = source_file.name
        fixture_path = self.output_dir / fixture_name

        # Handle duplicates by adding a suffix
        counter = 1
        while fixture_path.exists() and source_file not in self.copied_files:
            stem = source_file.stem
            suffix = source_file.suffix
            fixture_path = self.output_dir / f"{stem}_{counter}{suffix}"
            counter += 1

        # Copy the file if not already copied
        if source_file not in self.copied_files:
            self.output_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_file, fixture_path)
            self.copied_files.add(source_file)

        self.errors.append(
            {
                "source_file": str(source_file),
                "fixture_file": fixture_path.name,
                "error": error,
                "template_context": template_context,
            }
        )

    def write_manifest(self):
        """Write manifest.json with all collected errors."""
        if not self.errors:
            return

        manifest = {
            "collected_at": datetime.now().isoformat(),
            "error_count": len(self.errors),
            "unique_files": len(self.copied_files),
            "errors": self.errors,
        }

        manifest_path = self.output_dir / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2))

        return manifest_path


def get_fixture_collector():
    """Get the global fixture collector if in collection mode."""
    return _fixture_collector


@click.group()
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose logging")
@click.option("--debug", "-d", is_flag=True, help="Enable debug logging")
def cli(verbose, debug):
    """Extract and project source code into documentation."""
    if debug:
        setup_logging(logging.DEBUG)
    elif verbose:
        setup_logging(logging.INFO)
    else:
        setup_logging(logging.WARNING)


@cli.command()
@click.argument("input_path", type=click.Path(path_type=Path))
@click.argument("output_path", type=click.Path(path_type=Path), required=False)
@click.option(
    "--repo-path", "-r", type=click.Path(exists=True, path_type=Path), default=Path.cwd(), help="Repository root path"
)
@click.option(
    "--collect-error-fixtures", is_flag=True, help="Collect files that cause errors into tests/fixtures/collected/"
)
@click.option(
    "--remap-dirty-lines",
    is_flag=True,
    help="Remap line numbers in dirty files to match committed version (for sharing)",
)
def render(input_path, output_path, repo_path, collect_error_fixtures, remap_dirty_lines):
    """
    Render Jinja2 templates to markdown.

    INPUT_PATH can be a .j2 file, a directory containing .j2 files, or '-' for stdin.
    OUTPUT_PATH can be a file, directory, or '-' for stdout.

    If OUTPUT_PATH is not specified:
      - Files are rendered in-place (foo.md.j2 -> foo.md)
      - Directories are processed in-place (all .j2 files have extension stripped)
      - Stdin defaults to stdout

    Examples:
        projected-source render template.md.j2           # Creates template.md
        projected-source render template.md.j2 -         # Output to stdout
        projected-source render template.md.j2 out.md    # Output to out.md
        projected-source render templates/               # Process directory in-place
        projected-source render templates/ docs/         # Output to docs/
        echo "{{ code('file.cpp', function='main') }}" | projected-source render - -
        cat template.j2 | projected-source render -      # Output to stdout
    """
    global _fixture_collector

    # Set up fixture collection if requested
    if collect_error_fixtures:
        # Find the projected-source package directory
        package_dir = Path(__file__).parent.parent
        fixtures_dir = package_dir / "tests" / "fixtures" / "collected"
        _fixture_collector = FixtureCollector(fixtures_dir)
        console.print(f"[yellow]Fixture collection enabled → {fixtures_dir}[/yellow]")

    # Check for stdin input
    if str(input_path) == "-":
        input_is_stdin = True
        input_is_dir = False
    else:
        input_is_stdin = False
        input_is_dir = input_path.is_dir()

    # Determine output path
    if output_path is None:
        if input_is_stdin:
            # Default stdin to stdout
            output_path = None
            output_is_dir = False
            output_to_stdout = True
        elif input_is_dir:
            # Default: in-place for directories
            output_path = input_path
            output_is_dir = True
            output_to_stdout = False
        else:
            # Strip .j2 extension for in-place file rendering
            if input_path.suffix == ".j2":
                output_path = input_path.with_suffix("")
            else:
                console.print("[red]✗ Input file must have .j2 extension for in-place rendering[/red]")
                sys.exit(1)
            output_is_dir = False
            output_to_stdout = False
    elif str(output_path) == "-":
        # Stdout (only valid for single files)
        if input_is_dir:
            console.print("[red]✗ Cannot output directory to stdout[/red]")
            sys.exit(1)
        output_path = None
        output_is_dir = False
        output_to_stdout = True
    else:
        # Explicit output path - determine if it's a directory
        if input_is_dir:
            # Input is dir, output must be dir
            output_is_dir = True
        else:
            # Input is file, output must be file
            output_is_dir = False
        output_to_stdout = False

    # Validate input/output type matching
    if not output_to_stdout and not input_is_stdin and input_is_dir != output_is_dir:
        console.print("[red]✗ Input and output types must match (both files or both directories)[/red]")
        sys.exit(1)

    # Process based on input type
    if input_is_stdin:
        _render_stdin(output_path, repo_path, output_to_stdout, remap_dirty_lines)
    elif input_is_dir:
        _render_directory(input_path, output_path, repo_path, remap_dirty_lines)
    else:
        _render_file(input_path, output_path, repo_path, output_to_stdout, remap_dirty_lines)

    # Finalize fixture collection
    if _fixture_collector:
        manifest_path = _fixture_collector.write_manifest()
        if manifest_path:
            console.print(
                f"\n[yellow]Collected {len(_fixture_collector.errors)} errors "
                f"({len(_fixture_collector.copied_files)} files) → {manifest_path}[/yellow]"
            )
        else:
            console.print("[green]No errors to collect[/green]")


def _render_stdin(output_file, repo_path, output_to_stdout, remap_dirty_lines=False):
    """Render template from stdin."""
    # Read template from stdin
    template_content = sys.stdin.read()

    # Use current directory as template directory for relative paths
    renderer = TemplateRenderer(template_dir=Path.cwd(), repo_path=repo_path, remap_dirty_lines=remap_dirty_lines)

    # Render the template directly from string
    rendered = renderer.env.from_string(template_content).render()

    if output_to_stdout:
        # Output to stdout
        click.echo(rendered)
    else:
        # Output to file
        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_file.write_text(rendered)
        console.print(f"[green]✓[/green] stdin → {output_file}")


def _render_file(input_file, output_file, repo_path, output_to_stdout, remap_dirty_lines=False):
    """Render a single template file."""
    # Determine template directory
    template_dir = input_file.parent
    template_name = input_file.name

    # Create renderer
    renderer = TemplateRenderer(template_dir=template_dir, repo_path=repo_path, remap_dirty_lines=remap_dirty_lines)

    try:
        rendered = renderer.render_template(template_name)

        if output_to_stdout:
            # Output to stdout
            click.echo(rendered)
        else:
            # Output to file
            output_file.parent.mkdir(parents=True, exist_ok=True)
            output_file.write_text(rendered)
            console.print(f"[green]✓[/green] {input_file} → {output_file}")

    except Exception as e:
        console.print(f"[red]✗ Failed to render {input_file}:[/red] {e}")
        sys.exit(1)


def _render_directory(input_dir, output_dir, repo_path, remap_dirty_lines=False):
    """Render all templates in a directory."""
    templates = list(input_dir.glob("**/*.j2"))

    if not templates:
        console.print(f"[yellow]No .j2 templates found in {input_dir}[/yellow]")
        return

    console.print(f"[bold]Processing {len(templates)} templates from {input_dir}[/bold]")

    # Create renderer
    renderer = TemplateRenderer(template_dir=input_dir, repo_path=repo_path, remap_dirty_lines=remap_dirty_lines)

    # Track results
    success_count = 0
    failed = []

    # Process each template
    for template_path in templates:
        rel_path = template_path.relative_to(input_dir)

        # Determine output path (strip .j2 extension)
        if rel_path.suffix == ".j2":
            output_rel_path = rel_path.with_suffix("")
        else:
            output_rel_path = rel_path

        output_path_full = output_dir / output_rel_path

        try:
            # Render template
            rendered = renderer.render_template(str(rel_path))

            # Write output
            output_path_full.parent.mkdir(parents=True, exist_ok=True)
            output_path_full.write_text(rendered)

            console.print(f"  [green]✓[/green] {rel_path} → {output_rel_path}")
            success_count += 1

        except Exception as e:
            console.print(f"  [red]✗[/red] {rel_path}: {e}")
            failed.append((rel_path, str(e)))

    # Summary
    console.print("\n[bold]Summary:[/bold]")
    console.print(f"  [green]{success_count} templates rendered successfully[/green]")

    if failed:
        console.print(f"  [red]{len(failed)} templates failed:[/red]")
        for template, error in failed:
            console.print(f"    • {template}: {error}")
        sys.exit(1)


@cli.command()
def list_functions():
    """List available extraction functions."""
    table = Table(title="Available Extraction Functions")
    table.add_column("Function", style="cyan")
    table.add_column("Description", style="green")

    table.add_row("code()", "Universal code extraction function")
    table.add_row("  function=", "Extract a function by name")
    table.add_row("  function_macro=", "Extract function defined by macro")
    table.add_row("  macro_definition=", "Extract macro definition (#define)")
    table.add_row("  marker=", "Extract between comment markers")
    table.add_row("  lines=", "Extract specific line range")

    console.print(table)


def main():
    """Main entry point for the CLI."""
    cli()


if __name__ == "__main__":
    main()
