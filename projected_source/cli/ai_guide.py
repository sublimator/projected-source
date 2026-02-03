"""
AI guide command - outputs comprehensive guide for AI assistants.
"""

import click


@click.command("ai-guide")
def ai_guide():
    """Output comprehensive guide for AI assistants."""
    guide = """# projected-source AI Guide

## Overview
projected-source extracts code from C/C++ and Protocol Buffer (.proto) files
into Jinja2 templates, creating documentation that stays in sync with the
codebase. Uses tree-sitter for accurate parsing.

## IMPORTANT: Prefer Symbolic References

**Always prefer symbolic extraction over markers or line ranges.**

Extraction priority (best to worst):
1. `function='Name'` - functions, methods (use `signature=` for overloads)
2. `struct='Name'` / `var='Name'` - types, constants, variables (C/C++)
3. `message='Name'` / `enum='Name'` / `service='Name'` - protobuf definitions
4. `function_macro=` / `macro_definition=` - macro-based code
5. `function='X', marker='Y'` - subsection within a function (when needed)
6. `marker='X'` - standalone markers (last resort)
7. `lines=(start, end)` - fragile, breaks when code changes

**Why?** Symbolic refs survive refactoring. If someone renames a function,
you get a clear error. With line numbers, you silently get wrong code.

**Markers are for:** Extracting a specific subsection of a larger construct,
e.g., just the initialization part of a 200-line function. Not for extracting
whole functions - use `function=` for that.

## CLI Usage

```bash
# Render a single template
projected-source render template.md.j2

# Render to specific output
projected-source render template.md.j2 output.md

# Render directory of templates
projected-source render docs/

# Validate documentation covers code changes
projected-source render docs/ -V auto              # auto-detect base
projected-source render docs/ -V origin/main       # specific base
projected-source render docs/ -V HEAD~5..HEAD~2    # commit range
projected-source render docs/ -V auto --strict     # exit 1 if uncovered
```

## Template Functions

### code() - Extract code with GitHub permalinks

```jinja
{# Extract a function #}
{{ code('src/file.cpp', function='processTransaction') }}

{# Extract overloaded function by signature #}
{{ code('src/file.cpp', function='onMessage', signature='TMProposeSet') }}

{# Extract a struct/class/enum #}
{{ code('src/file.h', struct='Config') }}

{# Extract a variable/constant declaration #}
{{ code('src/file.cpp', var='errorCodes') }}

{# Extract lines by range #}
{{ code('src/file.cpp', lines=(10, 50)) }}

{# Extract between markers #}
{{ code('src/file.cpp', marker='example-usage') }}
{# In source: //@@start example-usage ... //@@end example-usage #}

{# Extract marker within a function #}
{{ code('src/file.cpp', function='main', marker='init-section') }}

{# Extract macro-defined function #}
{{ code('src/file.cpp', function_macro={'name': 'DEFINE_HANDLER', 'arg0': 'onConnect'}) }}

{# Extract macro definition #}
{{ code('src/file.h', macro_definition='MAX_BUFFER_SIZE') }}

{# Protocol Buffers (.proto) #}
{{ code('src/proto/messages.proto', message='Transaction') }}
{{ code('src/proto/messages.proto', enum='MessageType') }}
{{ code('src/proto/messages.proto', service='PeerService') }}
{{ code('src/proto/messages.proto', message='Transaction', marker='key-fields') }}

{# Options #}
{{ code('src/file.cpp', function='foo', github=False) }}      {# no permalink #}
{{ code('src/file.cpp', function='foo', line_numbers=False) }} {# no line nums #}
{{ code('src/file.cpp', function='foo', blame=True) }}         {# git blame #}
{{ code('src/file.cpp', function='foo', language='cpp') }}     {# force language #}
```

### ignore_changes() - Exclude regions from validation

When using `-V` to validate documentation coverage, use `ignore_changes()` to
exclude files or regions that don't need documentation:

```jinja
{# Ignore entire file #}
{{ ignore_changes('Builds/CMake/config.cmake') }}

{# Ignore specific constructs (same syntax as code()) #}
{{ ignore_changes('src/file.cpp', function='internalHelper') }}
{{ ignore_changes('src/file.cpp', struct='PrivateImpl') }}
{{ ignore_changes('src/file.cpp', lines=(1, 100)) }}
{{ ignore_changes('src/test/Test.cpp') }}  {# ignore test files #}
```

## Marker Syntax in Source Files

Works in both C/C++ and .proto files:

```cpp
//@@start section-name
code here
//@@end section-name
```

## Output Format

code() outputs markdown with:
1. GitHub permalink header (clickable link to source)
2. Fenced code block with syntax highlighting
3. Line numbers matching the source file

Example output:
```
📍 [`src/main.cpp:42-58`](https://github.com/org/repo/blob/abc123/src/main.cpp#L42-L58)
```cpp
  42 void processTransaction() {
  43     // implementation
  44 }
```

## Validation Mode (-V)

Shows uncovered code changes with actual source:

```
⚠ 3 uncovered regions:

━━━ src/handlers/Submit.cpp ━━━
230-261:
   230 void handleSubmit() {
   231     // new code not documented
   ...
```

## Tips for AI Assistants

1. **Prefer symbolic refs** - Use `function=`, `struct=`, `message=`, `enum=` instead of markers
2. **Use `signature=` for overloads** - e.g., `function='onMessage', signature='TMProposeSet'`
3. **Markers only for subsections** - When you need part of a function/message, not the whole thing
4. **Never use line ranges** unless absolutely necessary - they break on any edit
5. **Use relative paths** from repo root in code() calls
6. **Use ignore_changes()** at the top of templates for test files, build configs
7. **Check -V output** to ensure all changes are documented
8. **Proto files** - Use `message=`, `enum=`, `service=` for .proto extraction
"""
    click.echo(guide)
