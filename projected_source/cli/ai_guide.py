"""
AI guide command - outputs comprehensive guide for AI assistants.
"""

import click

from ..languages import EXTRACTORS


def _build_supported_languages() -> str:
    """Build a dynamic list of supported languages from the extractor registry."""
    # Group extensions by extractor class name
    by_extractor: dict[str, list[str]] = {}
    for ext, cls in EXTRACTORS.items():
        name = cls.__name__ if hasattr(cls, "__name__") else str(cls)
        by_extractor.setdefault(name, []).append(ext)

    lines = []
    for name, exts in by_extractor.items():
        label = name.replace("Extractor", "")
        lines.append(f"- **{label}**: {', '.join(sorted(exts))}")
    return "\n".join(lines)


@click.command("ai-guide")
def ai_guide():
    """Output comprehensive guide for AI assistants."""
    supported = _build_supported_languages()

    guide = f"""# projected-source AI Guide

## Overview
projected-source extracts code from source files into Jinja2 templates,
creating documentation that stays in sync with the codebase. Uses tree-sitter
for accurate AST-based parsing.

### Supported Languages

{supported}

## IMPORTANT: Prefer the Smallest Stable Reference

Do not blindly prefer whole-symbol extraction. Prefer the smallest extract that
is both stable AND useful for the reader. Pulling in a 400-line orchestration
function when you're documenting one decision point buries the point.

Extraction priority (best to worst):
1. `function='Name', marker='section-name'` - specific logic inside a large function
2. `function='Name'` - when the function is short enough to read as a unit
3. `struct=`, `message=`, `enum=`, `var=` - when the whole definition is relevant
4. `function_macro=` / `macro_definition=` - C/C++ macro-based code
5. `marker='section-name'` - cross-cutting or non-symbol regions
6. `lines=(start, end)` - last resort, fragile, breaks when code changes

**Why symbolic refs?** They survive refactoring. If someone renames a function,
you get a clear error. With line numbers, you silently get wrong code.

**Why not always whole-symbol?** A 400-line function with one interesting
gate buries the gate. Add a named marker (`//@@start gate-check` /
`//@@end gate-check`) around the decision point and reference that. The
reader sees just the relevant code in context of the function name.

## CLI Usage

```bash
# Render a single template
projected-source render template.md.j2

# Render to specific output
projected-source render template.md.j2 output.md

# Render directory of templates
projected-source render docs/

# Discover extractable symbols in a file
projected-source list-functions src/file.cpp

# Validate documentation covers code changes
projected-source render docs/ -V auto              # auto-detect base
projected-source render docs/ -V auto --strict     # exit 1 if uncovered
```

## Template Functions

### code() - Extract code with GitHub permalinks

```jinja
{{{{ code('src/file.cpp', function='processTransaction') }}}}
{{{{ code('src/file.cpp', function='onMessage', signature='TMProposeSet') }}}}
{{{{ code('src/file.h', struct='Config') }}}}
{{{{ code('src/file.cpp', var='errorCodes') }}}}
{{{{ code('src/file.cpp', marker='example-usage') }}}}
{{{{ code('src/file.cpp', function='main', marker='init-section') }}}}

{{# C/C++ macros #}}
{{{{ code('src/file.cpp', function_macro={{'name': 'DEFINE_HANDLER', 'arg0': 'onConnect'}}) }}}}
{{{{ code('src/file.h', macro_definition='MAX_BUFFER_SIZE') }}}}

{{# Protocol Buffers #}}
{{{{ code('src/messages.proto', message='Transaction') }}}}
{{{{ code('src/messages.proto', enum='MessageType') }}}}
{{{{ code('src/messages.proto', service='PeerService') }}}}

{{# Java #}}
{{{{ code('src/Handler.java', function='Handler.process') }}}}
{{{{ code('src/Handler.java', struct='Handler') }}}}
{{{{ code('src/Handler.java', var='Handler.MAX_SIZE') }}}}

{{# TypeScript #}}
{{{{ code('src/api.ts', function='handleRequest') }}}}
{{{{ code('src/api.ts', function='Service.process') }}}}
{{{{ code('src/api.ts', struct='Config') }}}}        {{# class, interface, or type alias #}}
{{{{ code('src/api.ts', enum='Status') }}}}

{{# Python #}}
{{{{ code('src/app.py', function='process') }}}}
{{{{ code('src/app.py', function='Handler.run') }}}}
{{{{ code('src/app.py', struct='Handler') }}}}
{{{{ code('src/app.py', var='MAX_SIZE') }}}}

{{# Options #}}
{{{{ code('src/file.cpp', function='foo', github=False) }}}}      {{# no permalink #}}
{{{{ code('src/file.cpp', function='foo', line_numbers=False) }}}} {{# no line nums #}}
{{{{ code('src/file.cpp', function='foo', blame=True) }}}}         {{# git blame #}}
{{{{ code('src/file.cpp', function='foo', ref='v1.0') }}}}         {{# from git ref #}}
{{{{ code('src/file.cpp', function='foo', root='/path/to/repo') }}}} {{# different root #}}
```

### include() - Include peer files

```jinja
{{{{ include('background.md') }}}}       {{# raw markdown, no template processing #}}
{{{{ include('details.md.j2') }}}}       {{# rendered as Jinja2 template #}}
```

Paths are relative to the template directory. `.j2` files are rendered as
templates with full access to `code()` and other functions.

### code_context - Set root path and git ref for a block

```jinja
{{# Scoped block - root and ref revert after endcode_context #}}
{{% code_context root='src/app', ref='develop' %}}
  {{{{ code('Handler.cpp', function='process') }}}}
{{% endcode_context %}}

{{# Global - persists until changed #}}
{{{{ set_code_context(root='src/app', ref='v1.0') }}}}
{{{{ code('Handler.cpp', function='process') }}}}
{{{{ set_code_context(root='', ref='') }}}}
```

### Multi-repo documentation

Use `{{% set %}}` to define repo paths, then use `root=` on code() or code_context:

```jinja
{{% set backend = '/path/to/backend' %}}
{{% set frontend = '/path/to/frontend' %}}

{{% code_context root=backend %}}
  {{{{ code('src/api/handler.cpp', function='process') }}}}
{{% endcode_context %}}

{{{{ code('src/App.tsx', struct='App', root=frontend) }}}}
```

## Marker Syntax in Source Files

```cpp
// C/C++, Java, TypeScript, Protobuf
//@@start section-name
code here
//@@end section-name
```

```python
# Python
#@@start section-name
code here
#@@end section-name
```

## Output Format

code() outputs markdown with:
1. GitHub permalink header (clickable link to source)
2. Fenced code block with syntax highlighting
3. Line numbers matching the source file

Example:
```
📍 [`src/main.cpp:42-58`](https://github.com/org/repo/blob/abc123/src/main.cpp#L42-L58)
\\```cpp
  42 void processTransaction() {{
  43     // implementation
  44 }}
\\```
```

## Tips for AI Assistants

1. **Prefer symbolic refs** - `function=`, `struct=`, `message=`, `enum=` over markers/lines
2. **Use `signature=` for C++ overloads** - e.g., `function='onMessage', signature='TMProposeSet'`
3. **Dotted paths for methods** - `function='Class.method'` works in Java, TypeScript, Python
4. **Use `list-functions`** to discover extractable symbols in any supported file
5. **Use `ref=`** to extract code from any git branch, tag, or commit
6. **Use `root=`** with absolute paths for multi-repo documentation
"""
    click.echo(guide)
