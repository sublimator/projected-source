"""
Command-line interface for projected-source.
"""

import json
import logging
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import click
from rich.console import Console
from rich.table import Table

from . import setup_logging
from .core.changes_set import ChangesSet
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
            from collections import defaultdict

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
    if _fixture_collector:
        manifest_path = _fixture_collector.write_manifest()
        if manifest_path:
            console.print(
                f"\n[yellow]Collected {len(_fixture_collector.errors)} errors "
                f"({len(_fixture_collector.copied_files)} files) → {manifest_path}[/yellow]"
            )
        else:
            console.print("[green]No errors to collect[/green]")


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


@cli.command("ai-guide")
def ai_guide():
    """Output comprehensive guide for AI assistants."""
    guide = """# projected-source AI Guide

## Overview
projected-source extracts code from C/C++ source files into Jinja2 templates,
creating documentation that stays in sync with the codebase. Uses tree-sitter
for accurate parsing.

## IMPORTANT: Prefer Symbolic References

**Always prefer symbolic extraction over markers or line ranges.**

Extraction priority (best to worst):
1. `function='Name'` - functions, methods (use `signature=` for overloads)
2. `struct='Name'` / `var='Name'` - types, constants, variables
3. `function_macro=` / `macro_definition=` - macro-based code
4. `function='X', marker='Y'` - subsection within a function (when needed)
5. `marker='X'` - standalone markers (last resort)
6. `lines=(start, end)` - fragile, breaks when code changes

**Why?** Symbolic refs survive refactoring. If someone renames a function,
you get a clear error. With line numbers, you silently get wrong code.

**Markers are for:** Extracting a specific subsection of a larger construct,
e.g., just the initialization part of a 200-line function. Not for extracting
whole functions - use `function=` for that.

## CLI Usage

```bash
# Render a single template
projected-source render template.md.j2

# Render to specific output
projected-source render template.md.j2 output.md

# Render directory of templates
projected-source render docs/

# Validate documentation covers code changes
projected-source render docs/ -V auto              # auto-detect base
projected-source render docs/ -V origin/main       # specific base
projected-source render docs/ -V HEAD~5..HEAD~2    # commit range
projected-source render docs/ -V auto --strict     # exit 1 if uncovered
```

## Template Functions

### code() - Extract code with GitHub permalinks

```jinja
{# Extract a function #}
{{ code('src/file.cpp', function='processTransaction') }}

{# Extract overloaded function by signature #}
{{ code('src/file.cpp', function='onMessage', signature='TMProposeSet') }}

{# Extract a struct/class/enum #}
{{ code('src/file.h', struct='Config') }}

{# Extract a variable/constant declaration #}
{{ code('src/file.cpp', var='errorCodes') }}

{# Extract lines by range #}
{{ code('src/file.cpp', lines=(10, 50)) }}

{# Extract between markers #}
{{ code('src/file.cpp', marker='example-usage') }}
{# In source: //@@start example-usage ... //@@end example-usage #}

{# Extract marker within a function #}
{{ code('src/file.cpp', function='main', marker='init-section') }}

{# Extract macro-defined function #}
{{ code('src/file.cpp', function_macro={'name': 'DEFINE_HANDLER', 'arg0': 'onConnect'}) }}

{# Extract macro definition #}
{{ code('src/file.h', macro_definition='MAX_BUFFER_SIZE') }}

{# Options #}
{{ code('src/file.cpp', function='foo', github=False) }}      {# no permalink #}
{{ code('src/file.cpp', function='foo', line_numbers=False) }} {# no line nums #}
{{ code('src/file.cpp', function='foo', blame=True) }}         {# git blame #}
{{ code('src/file.cpp', function='foo', language='cpp') }}     {# force language #}
```

### ignore_changes() - Exclude regions from validation

When using `-V` to validate documentation coverage, use `ignore_changes()` to
exclude files or regions that don't need documentation:

```jinja
{# Ignore entire file #}
{{ ignore_changes('Builds/CMake/config.cmake') }}

{# Ignore specific constructs (same syntax as code()) #}
{{ ignore_changes('src/file.cpp', function='internalHelper') }}
{{ ignore_changes('src/file.cpp', struct='PrivateImpl') }}
{{ ignore_changes('src/file.cpp', lines=(1, 100)) }}
{{ ignore_changes('src/test/Test.cpp') }}  {# ignore test files #}
```

## Marker Syntax in Source Files

```cpp
//@@start section-name
code here
//@@end section-name
```

## Output Format

code() outputs markdown with:
1. GitHub permalink header (clickable link to source)
2. Fenced code block with syntax highlighting
3. Line numbers matching the source file

Example output:
```
📍 [`src/main.cpp:42-58`](https://github.com/org/repo/blob/abc123/src/main.cpp#L42-L58)
```cpp
  42 void processTransaction() {
  43     // implementation
  44 }
```

## Validation Mode (-V)

Shows uncovered code changes with actual source:

```
⚠ 3 uncovered regions:

━━━ src/handlers/Submit.cpp ━━━
230-261:
   230 void handleSubmit() {
   231     // new code not documented
   ...
```

## Tips for AI Assistants

1. **Prefer symbolic refs** - Use `function=`, `struct=`, `var=` instead of markers
2. **Use `signature=` for overloads** - e.g., `function='onMessage', signature='TMProposeSet'`
3. **Markers only for subsections** - When you need part of a function, not the whole thing
4. **Never use line ranges** unless absolutely necessary - they break on any edit
5. **Use relative paths** from repo root in code() calls
6. **Use ignore_changes()** at the top of templates for test files, build configs
7. **Check -V output** to ensure all changes are documented
"""
    click.echo(guide)


def main():
    """Main entry point for the CLI."""
    cli()


if __name__ == "__main__":
    main()
