"""
Bug report guide command - outputs instructions for reporting extraction bugs.
"""

import click

GUIDE = """\
# projected-source Bug Report Guide

When an extraction fails or returns wrong results, report it with the info below.

## What to include

1. **The extraction call that failed** - the exact `code()` call from your template:
   ```
   {{ code('path/to/file.cpp', function='ClassName::methodName') }}
   ```

2. **What happened** - error message, or description of wrong output (e.g. "got the
   declaration instead of the definition")

3. **What you expected** - which lines / which version of the function you wanted

4. **The source file path** - absolute or repo-relative path to the file being extracted

5. **Relevant source snippet** - if the file is large, include the ~50 lines around
   both the expected match and the wrong match

## Quick copy-paste template

```
## Bug: [short description]

**Template call:**
{{ code('path/to/file.ext', function='name', signature='...') }}

**Error / wrong output:**
[paste error or describe what was returned]

**Expected:**
[describe what should have been extracted, include line numbers if known]

**Source file:** path/to/file.ext
**Source snippet (around expected match):**
```
[paste relevant lines]
```
```

## Filing the bug

Option A: Create an issue at https://github.com/nicholasdudfield/projected-source/issues
Option B: Copy the source file to tests/fixtures/ and write a failing test

## Creating a test fixture (preferred)

If you can reproduce it:

1. Copy the minimal source needed to `tests/fixtures/your_bug.cpp` (or .py, .proto)
   - Strip to just the relevant declarations/definitions (~30-50 lines)
   - Keep enough context to reproduce (class declarations, namespaces, etc.)

2. Add a test to `tests/test_cpp_coverage.py` (or appropriate test file):
   ```python
   def test_your_bug_description(self, extractor):
       from projected_source.languages.cpp_parser import SimpleCppParser
       parser = SimpleCppParser()
       source = (FIXTURES / "your_bug.cpp").read_bytes()
       result = parser.extract_function_by_name(source, "ClassName::method")
       assert result is not None
       assert "expected_content" in result.text
   ```

3. Run: `uv run pytest tests/test_cpp_coverage.py::TestClass::test_your_bug -v`
"""


@click.command("bug-report")
def bug_report():
    """Output guide for reporting extraction bugs."""
    click.echo(GUIDE)
