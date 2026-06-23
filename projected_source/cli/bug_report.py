"""
Bug report command - creates a bug report folder with fixture and report template.

Copies the problem source file into the projected-source repo and generates
a pre-filled markdown report. The resulting folder can be handed directly
to an AI agent to investigate and fix.
"""

import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import click

from .helpers import console


def _find_repo_root() -> Path:
    """Find the projected-source repo root from the package location."""
    current = Path(__file__).resolve().parent
    while current != current.parent:
        if (current / "pyproject.toml").exists() and (current / "tests").exists():
            return current
        current = current.parent
    return Path(__file__).resolve().parent.parent.parent


def _run_list_functions(source_file: Path) -> str:
    """Run list-functions on the source file and capture output."""
    try:
        result = subprocess.run(
            ["projected-source", "list-functions", str(source_file)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        return result.stdout.strip() if result.returncode == 0 else f"(failed: {result.stderr.strip()})"
    except Exception as e:
        return f"(failed: {e})"


@click.command("bug-report")
@click.argument("source_file", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.argument("symbol", required=False)
@click.option("--error", "-e", help="Error message or description of what went wrong")
@click.option("--expected", help="What you expected to be extracted")
def bug_report(source_file: Path, symbol: str, error: str, expected: str):
    """Create a bug report folder with fixture and report.

    SOURCE_FILE is the file that fails extraction.
    SYMBOL is the symbol that fails (e.g. 'ClassName::method').

    Examples:

        projected-source bug-report /path/to/file.cpp 'MyClass::method'
        projected-source bug-report /path/to/file.cpp 'MyClass::method' -e 'not found'
    """
    repo = _find_repo_root()
    source_file = source_file.resolve()

    # Generate bug name from filename and symbol
    stem = source_file.stem
    slug = symbol.replace("::", "-").replace(".", "-").lower() if symbol else "unknown"
    bug_name = f"{stem}-{slug}"
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    bug_dir = repo / "bugs" / f"{timestamp}-{bug_name}"

    # Create the bug directory
    bug_dir.mkdir(parents=True, exist_ok=True)

    # Copy the source file
    fixture_dest = bug_dir / source_file.name
    shutil.copy2(source_file, fixture_dest)

    # Run list-functions
    list_output = _run_list_functions(source_file)

    # Build the report
    error_text = error or "[paste error message here]"
    expected_text = expected or "[describe what should have been extracted, with line numbers]"
    symbol_text = symbol or "Unknown"

    code_call = f"{{{{ code('{source_file.name}', function='{symbol_text}') }}}}" if symbol else "[fill in]"

    report = f"""## Bug: extraction fails for `{symbol_text}` in `{source_file.name}`

**Template call:**
```
{code_call}
```

**Error:**
{error_text}

**Expected:**
{expected_text}

**Source file:** `{source_file}`
**Fixture:** `{fixture_dest.relative_to(repo)}`

**list-functions output:**
```
{list_output}
```
"""

    report_path = bug_dir / "report.md"
    report_path.write_text(report)

    console.print(f"\n[green]Bug report created:[/green] {bug_dir}")
    console.print(f"  [dim]fixture:[/dim]  {fixture_dest.relative_to(repo)}")
    console.print(f"  [dim]report:[/dim]   {report_path.relative_to(repo)}")
    console.print("\n[cyan]Hand this folder to an agent to investigate:[/cyan]")
    console.print(f"  {bug_dir}")
