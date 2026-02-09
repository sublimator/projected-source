"""
Command-line interface for projected-source.
"""

import logging

import click

from .. import setup_logging
from .ai_guide import ai_guide
from .find_markers import find_markers
from .list_symbols import list_functions
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
cli.add_command(list_functions)


def main():
    """Main entry point for the CLI."""
    cli()


if __name__ == "__main__":
    main()
