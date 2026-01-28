"""
Command-line interface for projected-source.
"""

import logging

import click
from rich.table import Table

from .. import setup_logging
from .ai_guide import ai_guide
from .find_markers import find_markers
from .helpers import console
from .render import render

logger = logging.getLogger(__name__)


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


# Register commands
cli.add_command(render)
cli.add_command(ai_guide)
cli.add_command(find_markers)


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
