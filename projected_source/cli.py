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
@click.option('--template-dir', '-t', type=click.Path(exists=True, path_type=Path),
              default=Path('templates'), help='Directory containing .j2 templates')
@click.option('--output-dir', '-o', type=click.Path(path_type=Path),
              default=Path('docs'), help='Output directory for rendered files')
@click.option('--repo-path', '-r', type=click.Path(exists=True, path_type=Path),
              default=Path.cwd(), help='Repository root path')
def generate(template_dir, output_dir, repo_path):
    """Process all .j2 templates in a directory."""
    templates = list(template_dir.glob('**/*.j2'))
    
    if not templates:
        console.print(f"[yellow]No .j2 templates found in {template_dir}[/yellow]")
        return
    
    console.print(f"[bold]Found {len(templates)} templates in {template_dir}[/bold]")
    
    # Create renderer
    renderer = TemplateRenderer(template_dir=template_dir, repo_path=repo_path)
    
    # Create output directory
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Process each template
    success_count = 0
    failed = []
    
    for template_path in templates:
        rel_path = template_path.relative_to(template_dir)
        output_path = output_dir / rel_path.with_suffix('')  # Remove .j2
        
        try:
            renderer.render_template_file(rel_path, output_path)
            console.print(f"[green]✓[/green] {rel_path} → {output_path}")
            success_count += 1
        except Exception as e:
            console.print(f"[red]✗[/red] {rel_path}: {e}")
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
@click.argument('template', type=click.Path(exists=True, path_type=Path))
@click.option('--output', '-o', type=click.Path(path_type=Path),
              help='Output file (default: stdout)')
@click.option('--repo-path', '-r', type=click.Path(exists=True, path_type=Path),
              default=Path.cwd(), help='Repository root path')
def render(template, output, repo_path):
    """Render a single template file."""
    # Determine template directory
    template_dir = template.parent
    template_name = template.name
    
    # Create renderer
    renderer = TemplateRenderer(template_dir=template_dir, repo_path=repo_path)
    
    try:
        rendered = renderer.render_template(template_name)
        
        if output:
            output.write_text(rendered)
            console.print(f"[green]✓[/green] Rendered {template} → {output}")
        else:
            # Output to stdout
            click.echo(rendered)
            
    except Exception as e:
        console.print(f"[red]✗ Failed to render {template}:[/red] {e}")
        sys.exit(1)


@cli.command()
@click.argument('file', type=click.Path(exists=True, path_type=Path))
@click.option('--repo-path', '-r', type=click.Path(exists=True, path_type=Path),
              default=Path.cwd(), help='Repository root path')
def markers(file, repo_path):
    """List all markers in a file."""
    from .languages import get_extractor
    
    try:
        extractor = get_extractor(file)
        markers_dict = extractor.find_markers_in_file(file)
        
        if not markers_dict:
            console.print(f"[yellow]No markers found in {file}[/yellow]")
            return
        
        # Display markers in a table
        table = Table(title=f"Markers in {file}")
        table.add_column("Marker", style="cyan")
        table.add_column("Start Line", style="green")
        table.add_column("End Line", style="green")
        table.add_column("Lines", style="yellow")
        
        for marker_name, (start, end) in sorted(markers_dict.items()):
            lines = end - start + 1
            table.add_row(marker_name, str(start), str(end), str(lines))
        
        console.print(table)
        
    except Exception as e:
        console.print(f"[red]✗ Failed to find markers:[/red] {e}")
        sys.exit(1)


@cli.command()
@click.argument('file', type=click.Path(exists=True, path_type=Path))
@click.option('--function', '-f', help='Extract a specific function')
@click.option('--marker', '-m', help='Extract between markers')
@click.option('--lines', '-l', help='Extract line range (e.g., "10-20")')
@click.option('--github/--no-github', default=True, help='Include GitHub permalink')
@click.option('--blame', '-b', is_flag=True, help='Include git blame')
@click.option('--line-numbers/--no-line-numbers', default=True, help='Show line numbers')
def extract(file, function, marker, lines, github, blame, line_numbers):
    """Extract code from a file and display it."""
    from .core.renderer import TemplateRenderer
    
    # Parse lines argument
    if lines:
        parts = lines.split('-')
        if len(parts) == 2:
            lines = (int(parts[0]), int(parts[1]))
        else:
            console.print(f"[red]Invalid lines format. Use 'start-end' (e.g., '10-20')[/red]")
            sys.exit(1)
    
    # Create renderer
    renderer = TemplateRenderer(repo_path=Path.cwd())
    
    # Extract code
    result = renderer._code_function(
        str(file),
        function=function,
        marker=marker,
        lines=lines,
        github=github,
        blame=blame,
        line_numbers=line_numbers
    )
    
    console.print(result)


def main():
    """Main entry point."""
    cli()


if __name__ == '__main__':
    main()