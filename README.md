# projected-source

Extract and project source code into documentation using tree-sitter for accurate parsing.

## Features

- **Tree-sitter powered** extraction of functions, markers, and code blocks
- **GitHub integration** with permalinks and git blame
- **Jinja2 templates** for flexible documentation generation
- **Language extensible** (starting with C++)
- **Comment directive parsing** using tree-sitter predicates

## Installation

```bash
pip install -e .
```

## Usage

### Command Line

```bash
# Process all templates in a directory
projected-source generate --template-dir templates --output-dir docs

# Process a single template
projected-source render template.md.j2 --output output.md
```

### In Templates

```jinja2
# Extract a function with GitHub permalink
{{ code('src/file.cpp', function='myFunction') }}

# Extract lines with line numbers
{{ code('src/file.cpp', lines=(10, 20), line_numbers=True) }}

# Extract between comment markers
{{ code('src/file.cpp', marker='example1') }}

# Without GitHub integration
{{ code('src/file.cpp', function='myFunction', github=False) }}

# With git blame
{{ code('src/file.cpp', lines=(10, 20), blame=True) }}
```

### Comment Markers

Mark code sections in your source files:

```cpp
//@@start example1
int example_code() {
    return 42;
}
//@@end example1
```

## Architecture

- **Tree-sitter queries** with predicates for finding comment directives
- **Modular language support** via language-specific extractors
- **GitHub permalink generation** with commit hash support
- **Per-module logging** for debugging

## Development

```bash
# Install with dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Format code
black projected_source
ruff check projected_source
```