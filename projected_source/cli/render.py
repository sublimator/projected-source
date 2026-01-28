"""
Render command for processing Jinja2 templates.
"""

import sys
from collections import defaultdict
from pathlib import Path
from typing import Optional

import click

from ..core.changes_set import ChangesSet
from ..core.renderer import TemplateRenderer
from .helpers import FixtureCollector, console, get_fixture_collector, set_fixture_collector


@click.command()
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
@click.option(
    "-V",
    "--validate-changes",
    "changes_base",
    default=None,
    metavar="BASE",
    help="Validate changes are documented. BASE: commit/branch/range, or 'auto' to detect.",
)
@click.option(
    "--strict",
    is_flag=True,
    help="Exit with error code 1 if validation fails (use with -V)",
)
def render(
    input_path,
    output_path,
    repo_path,
    collect_error_fixtures,
    remap_dirty_lines,
    changes_base,
    strict,
):
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
    # Set up fixture collection if requested
    if collect_error_fixtures:
        # Find the projected-source package directory
        package_dir = Path(__file__).parent.parent.parent
        fixtures_dir = package_dir / "tests" / "fixtures" / "collected"
        set_fixture_collector(FixtureCollector(fixtures_dir))
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

    # Set up ChangesSet for validation if requested (-V / --validate-changes)
    changes_set: Optional[ChangesSet] = None
    if changes_base:
        # "auto" means auto-detect base
        base = None if changes_base == "auto" else changes_base
        try:
            changes_set = ChangesSet.from_diff(base=base, repo_path=repo_path)
            if base and ".." in base:
                range_display = base
            else:
                detected = ChangesSet.detect_base(repo_path) if base is None else base
                range_display = f"{detected[:12]}..HEAD"
            console.print(f"[cyan]Validating changes: {range_display}[/cyan]")
        except RuntimeError as e:
            console.print(f"[red]✗ Failed to get diff: {e}[/red]")
            sys.exit(1)

    # Process based on input type
    if input_is_stdin:
        _render_stdin(output_path, repo_path, output_to_stdout, remap_dirty_lines, changes_set)
    elif input_is_dir:
        _render_directory(input_path, output_path, repo_path, remap_dirty_lines, changes_set)
    else:
        _render_file(input_path, output_path, repo_path, output_to_stdout, remap_dirty_lines, changes_set)

    # Report validation results
    if changes_set is not None:
        uncovered = changes_set.uncovered()
        if uncovered:
            console.print(f"\n[yellow]⚠ {len(uncovered)} uncovered regions:[/yellow]")
            # Group by file
            by_file = defaultdict(list)
            for region in uncovered:
                by_file[region.file_path].append((region.start_line, region.end_line))

            for abs_path, ranges in by_file.items():
                try:
                    rel_path = abs_path.relative_to(repo_path)
                except ValueError:
                    rel_path = abs_path
                console.print(f"\n[cyan]━━━ {rel_path} ━━━[/cyan]")

                # Read file once, show each range
                try:
                    lines = abs_path.read_text().splitlines()
                    for start, end in ranges:
                        console.print(f"[dim]{start}-{end}:[/dim]")
                        for i in range(start - 1, min(end, len(lines))):
                            console.print(f"  [dim]{i + 1:4}[/dim] {lines[i]}")
                except Exception as e:
                    console.print(f"  [red]Could not read file: {e}[/red]")

            if strict:
                console.print("\n[red]✗ Validation failed (--strict mode)[/red]")
                sys.exit(1)
        else:
            console.print("[green]✓ All changes documented[/green]")

    # Finalize fixture collection
    collector = get_fixture_collector()
    if collector:
        manifest_path = collector.write_manifest()
        if manifest_path:
            console.print(
                f"\n[yellow]Collected {len(collector.errors)} errors "
                f"({len(collector.copied_files)} files) → {manifest_path}[/yellow]"
            )
        else:
            console.print("[green]No errors to collect[/green]")
        set_fixture_collector(None)


def _render_stdin(output_file, repo_path, output_to_stdout, remap_dirty_lines=False, changes_set=None):
    """Render template from stdin."""
    # Read template from stdin
    template_content = sys.stdin.read()

    # Use current directory as template directory for relative paths
    renderer = TemplateRenderer(
        template_dir=Path.cwd(), repo_path=repo_path, remap_dirty_lines=remap_dirty_lines, changes_set=changes_set
    )

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


def _render_file(input_file, output_file, repo_path, output_to_stdout, remap_dirty_lines=False, changes_set=None):
    """Render a single template file."""
    # Determine template directory
    template_dir = input_file.parent
    template_name = input_file.name

    # Create renderer
    renderer = TemplateRenderer(
        template_dir=template_dir, repo_path=repo_path, remap_dirty_lines=remap_dirty_lines, changes_set=changes_set
    )

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


def _render_directory(input_dir, output_dir, repo_path, remap_dirty_lines=False, changes_set=None):
    """Render all templates in a directory."""
    templates = list(input_dir.glob("**/*.j2"))

    if not templates:
        console.print(f"[yellow]No .j2 templates found in {input_dir}[/yellow]")
        return

    console.print(f"[bold]Processing {len(templates)} templates from {input_dir}[/bold]")

    # Create renderer
    renderer = TemplateRenderer(
        template_dir=input_dir, repo_path=repo_path, remap_dirty_lines=remap_dirty_lines, changes_set=changes_set
    )

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
