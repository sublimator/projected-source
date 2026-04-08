"""
Bug report guide command - outputs instructions for reporting extraction bugs.

Dynamically locates the projected-source repo from the installed package
so fixture paths are always correct.
"""

from pathlib import Path

import click


def _find_repo_root() -> Path:
    """Find the projected-source repo root from the package location."""
    # Walk up from this file to find the repo root (contains pyproject.toml)
    current = Path(__file__).resolve().parent
    while current != current.parent:
        if (current / "pyproject.toml").exists() and (current / "tests").exists():
            return current
        current = current.parent
    return Path(__file__).resolve().parent.parent.parent


def _build_guide() -> str:
    repo = _find_repo_root()
    fixtures = repo / "tests" / "fixtures"
    tests = repo / "tests"

    return f"""\
# projected-source Bug Report Guide

When an extraction fails or returns wrong results, follow the steps below.

## 1. Gather the info

- **The extraction call that failed** — the exact `code()` call from your template
- **The error message** or description of wrong output
- **The source file** — absolute path to the file being extracted
- **What you expected** — which lines / which function you wanted

## 2. Check list-functions vs code()

```bash
# Does list-functions find the symbol?
projected-source list-functions /path/to/file.cpp

# Does code() fail on it?
echo "{{{{ code('/path/to/file.cpp', function='Name', github=False) }}}}" | projected-source render - - --no-header
```

If `list-functions` finds it but `code()` fails, that's a bug in the extraction path.

## 3. Create a fixture and failing test

**Repo root:** `{repo}`
**Fixtures directory:** `{fixtures}`
**Tests directory:** `{tests}`

### Copy the source file:

```bash
cp /path/to/problem-file.cpp {fixtures}/cpp/
# or for other languages:
# {fixtures}/python/
# {fixtures}/  (for .proto, .java, .ts, etc.)
```

### Write a failing test:

Create `{tests}/test_your_bug.py`:

```python
from pathlib import Path
from projected_source.languages.cpp import CppExtractor

FIXTURE = Path(__file__).parent / "fixtures" / "cpp" / "problem_file.cpp"

def test_extract_fails():
    ext = CppExtractor()
    text, start, end = ext.extract_function(FIXTURE, "ClassName::method")
    assert "expected_content" in text
```

### Run the test:

```bash
cd {repo}
uv run pytest {tests}/test_your_bug.py -v
```

## 4. Quick copy-paste bug template

```
## Bug: [short description]

**Template call:**
{{{{ code('path/to/file.ext', function='Name') }}}}

**Error:**
[paste error message]

**Expected:**
[what should have been extracted, with line numbers]

**Source file:** /absolute/path/to/file.ext

**list-functions output:**
[paste relevant lines from projected-source list-functions]

**Fixture copied to:** {fixtures}/cpp/filename.cpp
```
"""


@click.command("bug-report")
def bug_report():
    """Output guide for reporting extraction bugs."""
    click.echo(_build_guide())
