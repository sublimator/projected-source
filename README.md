# projected-source

A hacky but useful tool for "projecting" C++ source code into documentation using tree-sitter.

## Why?

When you write documentation with code examples, those examples often rot. They become outdated, don't compile, or drift from reality. This tool flips that around:

1. Write your examples as **real, compilable code** in your codebase
2. Use markers or function extraction to **project fragments** into your docs
3. The docs stay in sync because they pull from actual source

It's particularly useful for:

- **AI context** - Hand-craft context to supply to AI for planning, coding, or debugging sessions
- **Bug reports** - Extract relevant code snippets with GitHub permalinks
- **Living documentation** - Examples that compile and stay current

The AI can even write templates itself as it explores your codebase, then render them later when you need the actual context.

## Installation

```bash
pip install -e .
# or with uv
uv pip install -e .
```

## Usage

### Command Line

```bash
# Render a template (foo.md.j2 -> foo.md)
projected-source render template.md.j2

# Render to stdout
projected-source render template.md.j2 -

# Render a directory of templates
projected-source render docs/
```

### In Templates

```jinja2
{# Extract a function by name #}
{{ code('src/file.cpp', function='processTransaction') }}

{# Extract a struct/class/enum #}
{{ code('src/file.h', struct='Config') }}

{# Extract between comment markers - for fragments of larger code #}
{{ code('src/file.cpp', marker='example-usage') }}

{# Extract a marker within a function #}
{{ code('src/file.cpp', function='main', marker='init-section') }}

{# Extract specific lines #}
{{ code('src/file.cpp', lines=(10, 50)) }}

{# Options #}
{{ code('src/file.cpp', function='foo', github=False) }}       {# no permalink #}
{{ code('src/file.cpp', function='foo', line_numbers=False) }} {# no line nums #}
{{ code('src/file.cpp', function='foo', blame=True) }}         {# git blame #}
```

### Comment Markers

The marker feature is the key to having compilable examples while only showing fragments in docs:

```cpp
// This whole file compiles and runs in your test suite
#include <iostream>

int main() {
    setup_stuff();

    //@@start example-usage
    auto result = doTheThing();
    if (result.ok()) {
        std::cout << "Success!" << std::endl;
    }
    //@@end example-usage

    cleanup_stuff();
    return 0;
}
```

Then in your template:
```jinja2
Here's how to use the thing:

{{ code('examples/demo.cpp', marker='example-usage') }}
```

The output includes GitHub permalinks so readers can see the full context.

## Output Format

```markdown
📍 [`src/main.cpp:42-58`](https://github.com/org/repo/blob/abc123/src/main.cpp#L42-L58)
```cpp
  42 void processTransaction() {
  43     // implementation
  44 }
```

## Validation Mode

Check that your documentation covers code changes:

```bash
projected-source render docs/ -V auto              # auto-detect base
projected-source render docs/ -V origin/main       # specific base
projected-source render docs/ -V auto --strict     # exit 1 if uncovered
```

## Development

```bash
uv sync
uv run pytest
uv run ruff check projected_source
```
