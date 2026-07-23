"""
List extractable symbols in a source file.
"""

import inspect
from collections import Counter
from pathlib import Path

import click
from rich.markup import escape

from ..languages import get_extractor
from .helpers import console


@click.command("list-functions")
@click.argument("file", required=False, type=click.Path(exists=True, dir_okay=False))
@click.option(
    "--include-tests",
    is_flag=True,
    default=False,
    help="Rust only: include items inside #[cfg(test)] modules (hidden by default).",
)
def list_functions(file, include_tests):
    """List extractable symbols in a file.

    When FILE is given, lists all functions, classes, structs, enums,
    variables, and markers that can be extracted with code() calls.

    When no FILE is given, shows available extraction parameters.
    """
    if not file:
        _show_params_table()
        return

    file_path = Path(file).resolve()

    try:
        extractor = get_extractor(file_path)
    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        raise SystemExit(1)

    if not hasattr(extractor, "list_symbols"):
        console.print(f"[red]Symbol listing not supported for {file_path.suffix} files[/red]")
        raise SystemExit(1)

    list_kwargs = {}
    if include_tests and "include_tests" in inspect.signature(extractor.list_symbols).parameters:
        list_kwargs["include_tests"] = True

    try:
        symbols = extractor.list_symbols(file_path, **list_kwargs)
    except Exception as e:
        console.print(f"[red]Could not read symbols from {file}: {escape(str(e))}[/red]")
        raise SystemExit(1)

    if not symbols:
        console.print(f"[yellow]No extractable symbols found in {file}[/yellow]")
        return

    # Detect overloaded functions
    func_names = [s["name"] for s in symbols if s["param"] == "function"]
    name_counts = Counter(func_names)
    overloaded = {name for name, count in name_counts.items() if count > 1}

    # Group by param
    groups = {}
    for sym in symbols:
        param = sym["param"]
        if param not in groups:
            groups[param] = []
        groups[param].append(sym)

    # Display
    console.print(f"\n[bold]{file}[/bold]\n")

    display_order = ["function", "struct", "var", "message", "enum", "service", "marker"]

    for param in display_order:
        if param not in groups:
            continue

        syms = groups[param]
        count = len(syms)
        console.print(f"  [bold]{param}=[/bold] [dim]({count})[/dim]")

        for sym in syms:
            name = sym["name"]
            line = sym["line"]
            kind = sym["kind"]

            parts = []

            # Show kind if it differs from param (e.g. class vs struct param)
            if kind != param:
                parts.append(f"[dim]{kind}[/dim]")

            # Line info
            if sym.get("end_line"):
                parts.append(f"[dim]lines {line}-{sym['end_line']}[/dim]")
            else:
                parts.append(f"[dim]line {line}[/dim]")

            # Show signature hint for overloaded functions
            if name in overloaded and sym.get("signature"):
                # Signatures are raw source text (e.g. '(char buf[size])')
                # — escape so Rich doesn't eat brackets as markup.
                parts.append(f"[dim]signature='{escape(sym['signature'])}'[/dim]")

            extra = "  ".join(parts)
            console.print(f"    [cyan]'{escape(name)}'[/cyan]  {extra}")

        console.print()


def _show_params_table():
    """Show the extraction parameters reference table."""
    from rich.table import Table

    table = Table(title="Available Extraction Functions")
    table.add_column("Function", style="cyan")
    table.add_column("Description", style="green")

    table.add_row("code()", "Universal code extraction function")
    table.add_row("  function=", "Extract a function by name")
    table.add_row("  struct=", "Extract a struct/class/enum by name (C/C++)")
    table.add_row("  var=", "Extract a variable declaration (C/C++)")
    table.add_row("  function_macro=", "Extract function defined by macro")
    table.add_row("  macro_definition=", "Extract macro definition (#define)")
    table.add_row("  message=", "Extract a message definition (protobuf)")
    table.add_row("  enum=", "Extract an enum definition (protobuf, C++, TypeScript, Java, Rust)")
    table.add_row("  service=", "Extract a service definition (protobuf)")
    table.add_row("  marker=", "Extract between comment markers")
    table.add_row("  lines=", "Extract specific line range")

    console.print(table)
    console.print("\n[dim]Tip: run [cyan]list-functions <file>[/cyan] to see extractable symbols[/dim]")
