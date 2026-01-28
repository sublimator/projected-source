"""
Find markers command - locate and optionally remove markers in changed files.
"""

import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Tuple

import click

from .helpers import console


@click.command("find-markers")
@click.option(
    "--since",
    type=str,
    required=True,
    help="Git ref to diff against (e.g., origin/dev, HEAD~5, commit hash)",
)
@click.option(
    "--remove",
    is_flag=True,
    help="Remove marker comments that are on their own line",
)
@click.option(
    "--repo-path",
    "-r",
    type=click.Path(exists=True, path_type=Path),
    default=Path.cwd(),
    help="Repository root path",
)
def find_markers(since: str, remove: bool, repo_path: Path):
    """
    Find //@@start and //@@end markers in changed C/C++ files.

    Scans files changed since <ref> for marker comments used by projected-source.
    Useful for cleaning up markers after documentation is finalized.

    Examples:
        projected-source find-markers --since origin/dev
        projected-source find-markers --since HEAD~5 --remove
    """
    # Get changed files from git
    diff_range = since if ".." in since else f"{since}..HEAD"

    result = subprocess.run(
        ["git", "diff", diff_range, "--name-only"],
        capture_output=True,
        cwd=repo_path,
        text=True,
    )

    if result.returncode != 0:
        console.print(f"[red]✗ git diff failed: {result.stderr}[/red]")
        sys.exit(1)

    # Filter for C/C++ files
    cpp_extensions = {".h", ".hpp", ".cpp", ".cc", ".cxx", ".c", ".hxx", ".ipp"}
    changed_files = []
    for line in result.stdout.strip().split("\n"):
        if line:
            path = Path(line)
            if path.suffix.lower() in cpp_extensions:
                changed_files.append(repo_path / path)

    if not changed_files:
        console.print(f"[yellow]No C/C++ files changed since {since}[/yellow]")
        return

    console.print(f"[cyan]Scanning {len(changed_files)} file(s) for markers...[/cyan]\n")

    # Pattern for marker comments on their own line
    marker_pattern = re.compile(r"^(\s*)//@@(start|end)\s+([\w-]+)\s*$")

    # Collect all markers
    all_markers: List[Tuple[Path, int, str, str, str]] = []  # (file, line, type, name, full_line)

    for file_path in changed_files:
        if not file_path.exists():
            continue

        try:
            lines = file_path.read_text().splitlines()
        except Exception as e:
            console.print(f"[red]Could not read {file_path}: {e}[/red]")
            continue

        for line_num, line in enumerate(lines, 1):
            match = marker_pattern.match(line)
            if match:
                indent, marker_type, marker_name = match.groups()
                all_markers.append((file_path, line_num, marker_type, marker_name, line))

    if not all_markers:
        console.print("[green]No markers found in changed files[/green]")
        return

    # Group by file for display
    by_file: Dict[Path, List[Tuple[int, str, str, str]]] = defaultdict(list)
    for file_path, line_num, marker_type, marker_name, full_line in all_markers:
        by_file[file_path].append((line_num, marker_type, marker_name, full_line))

    # Display markers
    console.print(f"[bold]Found {len(all_markers)} marker(s):[/bold]\n")

    for file_path, markers in sorted(by_file.items()):
        try:
            rel_path = file_path.relative_to(repo_path)
        except ValueError:
            rel_path = file_path
        console.print(f"[cyan]{rel_path}:[/cyan]")
        for line_num, marker_type, marker_name, full_line in markers:
            type_color = "green" if marker_type == "start" else "yellow"
            console.print(f"  {line_num:4}: [{type_color}]//@@{marker_type} {marker_name}[/{type_color}]")
        console.print()

    # Remove markers if requested
    if remove:
        console.print("[bold]Removing markers...[/bold]\n")

        removed_count = 0
        for file_path, markers in by_file.items():
            lines_to_remove = {m[0] for m in markers}  # line numbers (1-based)

            try:
                original_lines = file_path.read_text().splitlines()
                new_lines = [line for i, line in enumerate(original_lines, 1) if i not in lines_to_remove]

                if len(new_lines) < len(original_lines):
                    file_path.write_text("\n".join(new_lines) + "\n")
                    count = len(original_lines) - len(new_lines)
                    removed_count += count

                    try:
                        rel_path = file_path.relative_to(repo_path)
                    except ValueError:
                        rel_path = file_path
                    console.print(f"  [green]✓[/green] {rel_path}: removed {count} marker(s)")

            except Exception as e:
                console.print(f"  [red]✗[/red] {file_path}: {e}")

        console.print(f"\n[bold green]Removed {removed_count} marker(s) total[/bold green]")
