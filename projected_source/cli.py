"""
Command-line interface for projected-source.
"""

import logging
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from . import setup_logging
from .core.renderer import TemplateRenderer

logger = logging.getLogger(__name__)
console = Console()


@click.group()
@click.option('--verbose', '-v', is_flag=True, help='Enable verbose logging')
@click.option('--debug', '-d', is_flag=True, help='Enable debug logging')
def cli(verbose, debug):
    """Extract and project source code into documentation."""
    if debug:
        setup_logging(logging.DEBUG)
    elif verbose:
        setup_logging(logging.INFO)
    else:
        setup_logging(logging.WARNING)


@cli.command()
@click.argument('input_path', type=click.Path(path_type=Path))
@click.argument('output_path', type=click.Path(path_type=Path), required=False)
@click.option('--repo-path', '-r', type=click.Path(exists=True, path_type=Path),
              default=Path.cwd(), help='Repository root path')
def render(input_path, output_path, repo_path):
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
    # Check for stdin input
    if str(input_path) == '-':
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
            if input_path.suffix == '.j2':
                output_path = input_path.with_suffix('')
            else:
                console.print(f"[red]✗ Input file must have .j2 extension for in-place rendering[/red]")
                sys.exit(1)
            output_is_dir = False
            output_to_stdout = False
    elif str(output_path) == '-':
        # Stdout (only valid for single files)
        if input_is_dir:
            console.print(f"[red]✗ Cannot output directory to stdout[/red]")
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
        console.print(f"[red]✗ Input and output types must match (both files or both directories)[/red]")
        sys.exit(1)
    
    # Process based on input type
    if input_is_stdin:
        _render_stdin(output_path, repo_path, output_to_stdout)
    elif input_is_dir:
        _render_directory(input_path, output_path, repo_path)
    else:
        _render_file(input_path, output_path, repo_path, output_to_stdout)


def _render_stdin(output_file, repo_path, output_to_stdout):
    """Render template from stdin."""
    # Read template from stdin
    template_content = sys.stdin.read()
    
    # Use current directory as template directory for relative paths
    renderer = TemplateRenderer(template_dir=Path.cwd(), repo_path=repo_path)
    
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


def _render_file(input_file, output_file, repo_path, output_to_stdout):
    """Render a single template file."""
    # Determine template directory
    template_dir = input_file.parent
    template_name = input_file.name
    
    # Create renderer
    renderer = TemplateRenderer(template_dir=template_dir, repo_path=repo_path)
    
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


def _render_directory(input_dir, output_dir, repo_path):
    """Render all templates in a directory."""
    templates = list(input_dir.glob('**/*.j2'))
    
    if not templates:
        console.print(f"[yellow]No .j2 templates found in {input_dir}[/yellow]")
        return
    
    console.print(f"[bold]Processing {len(templates)} templates from {input_dir}[/bold]")
    
    # Create renderer
    renderer = TemplateRenderer(template_dir=input_dir, repo_path=repo_path)
    
    # Track results
    success_count = 0
    failed = []
    
    # Process each template
    for template_path in templates:
        rel_path = template_path.relative_to(input_dir)
        
        # Determine output path (strip .j2 extension)
        if rel_path.suffix == '.j2':
            output_rel_path = rel_path.with_suffix('')
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
    console.print(f"\n[bold]Summary:[/bold]")
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


if __name__ == '__main__':
    main()