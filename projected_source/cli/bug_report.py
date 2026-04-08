"""
Bug report guide command - outputs instructions for reporting extraction bugs.

Dynamically locates the projected-source repo from the installed package
so fixture paths are always correct.
"""

from pathlib import Path

import click


def _find_repo_root() -> Path:
    """Find the projected-source repo root from the package location."""
    current = Path(__file__).resolve().parent
    while current != current.parent:
        if (current / "pyproject.toml").exists() and (current / "tests").exists():
            return current
        current = current.parent
    return Path(__file__).resolve().parent.parent.parent


def _build_guide() -> str:
    repo = _find_repo_root()
    fixtures = repo / "tests" / "fixtures"
    bugs = repo / "bugs"

    return f"""\
# projected-source Bug Report Guide

When an extraction fails or returns wrong results, follow the steps below.

## 1. Check list-functions vs code()

```bash
# Does list-functions find the symbol?
projected-source list-functions /path/to/file.cpp

# Does code() fail on it?
echo "{{{{ code('/path/to/file.cpp', function='Name', github=False) }}}}" | projected-source render - - --no-header
```

If `list-functions` finds it but `code()` fails, that's a bug in the extraction path.

## 2. Copy the source file to fixtures

```bash
cp /path/to/problem-file.cpp {fixtures}/cpp/
```

Other languages:
- `{fixtures}/python/` for .py files
- `{fixtures}/` for .proto, .java, .ts, etc.

## 3. Write a bug report

Create a markdown file in `{bugs}/`:

```bash
mkdir -p {bugs}
```

Save as `{bugs}/your-bug-name.md`:

```markdown
## Bug: [short description]

**Template call:**
\\```
{{{{ code('path/to/file.ext', function='Name') }}}}
\\```

**Error:**
[paste error message]

**Expected:**
[what should have been extracted, with line numbers]

**Source file:** /absolute/path/to/file.ext
**Fixture:** tests/fixtures/cpp/filename.cpp

**list-functions output:**
\\```
[paste relevant lines from projected-source list-functions]
\\```
```

## Paths

- **Repo root:** `{repo}`
- **Fixtures:** `{fixtures}`
- **Bug reports:** `{bugs}`
"""


@click.command("bug-report")
def bug_report():
    """Output guide for reporting extraction bugs."""
    click.echo(_build_guide())
