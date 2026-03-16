---
name: narrative
description: Build narrative-style documentation for a feature or subsystem using projected-source Jinja2 templates. Use when asked to document code, create a guided tour, or explain a feature with living code references.
argument-hint: [feature or topic to document]
allowed-tools: Read, Grep, Glob, Bash(projected-source *)
---

# Task: Build Narrative Documentation

Create a **narrative-style** documentation template for: **$ARGUMENTS**

## Philosophy

You are not writing an API reference. You are writing a **guided tour** — a narrative that walks the reader through the code in a sequence that builds understanding. Think of it like explaining the feature to a smart colleague who just joined the team.

**Key principles:**

1. **Narrative flow over completeness** — Don't dump every function. Tell the story of how the feature works, in the order that makes sense to understand it.
2. **Code snippets serve the narrative** — Pull in code to illustrate the point you're making, not gratuitously. Every snippet should earn its place.
3. **Symbolic references always** — Use `function=`, `struct=`, `message=`, `enum=` etc. Never line numbers. These survive refactoring.
4. **Living documentation** — The templates re-render when code changes. Write prose that describes *what* and *why*, let the code() calls show the *how*.

## projected-source Template Syntax

Templates are Jinja2 markdown files (`.md.j2`) that use these functions:

### code() — Extract code with GitHub permalinks

```jinja
{# Extract by symbol name (ALWAYS prefer this) #}
{{ code('src/file.cpp', function='processTransaction') }}
{{ code('src/file.h', struct='Config') }}
{{ code('src/file.cpp', var='errorCodes') }}

{# Overloaded functions — disambiguate by signature #}
{{ code('src/file.cpp', function='onMessage', signature='TMProposeSet') }}

{# Protobuf definitions #}
{{ code('proto/messages.proto', message='Transaction') }}
{{ code('proto/messages.proto', enum='MessageType') }}
{{ code('proto/messages.proto', service='PeerService') }}

{# Subsection of a function (use markers for this, not the whole function) #}
{{ code('src/file.cpp', function='main', marker='init-section') }}

{# Macros #}
{{ code('src/file.cpp', function_macro={'name': 'DEFINE_HANDLER', 'arg0': 'onConnect'}) }}
{{ code('src/file.h', macro_definition='MAX_BUFFER_SIZE') }}

{# Options #}
{{ code('src/file.cpp', function='foo', github=False) }}      {# no permalink #}
{{ code('src/file.cpp', function='foo', line_numbers=False) }} {# no line nums #}
{{ code('src/file.cpp', function='foo', blame=True) }}         {# git blame #}
```

### include() — Include peer files

```jinja
{{ include('background.md') }}       {# raw markdown, no template processing #}
{{ include('details.md.j2') }}       {# rendered as Jinja2 template #}
```

### ignore_changes() — Exclude from validation

```jinja
{{ ignore_changes('src/test/Test.cpp') }}
{{ ignore_changes('src/file.cpp', function='internalHelper') }}
```

### Marker syntax in source files

```cpp
//@@start section-name
code here
//@@end section-name
```

## Extraction Priority (best to worst)

1. `function='Name'` — functions, methods
2. `struct='Name'` / `var='Name'` — types, constants
3. `message='Name'` / `enum='Name'` / `service='Name'` — protobuf
4. `function_macro=` / `macro_definition=` — macro-based code
5. `function='X', marker='Y'` — subsection within a function
6. `marker='X'` — standalone markers (last resort)
7. `lines=(start, end)` — NEVER use this

## How to Build the Narrative

1. **Explore the code** — Read the relevant source files. Understand the feature before writing about it.
2. **Find the entry point** — Where does the reader's journey start? A main function? A message handler? A struct definition?
3. **Plan the sequence** — What order builds understanding? Usually: data structures first, then flow, then edge cases.
4. **Write prose, insert code** — Write the narrative in markdown. Use `{{ code() }}` calls to pull in the specific symbols that illustrate each point. Don't over-extract.
5. **Use `include()` for structure** — Break large docs into sections with `.md.j2` includes.
6. **Use `ignore_changes()`** — At the top, exclude test files, build configs, anything that doesn't need documentation.
7. **Render and verify** — Run `projected-source render template.md.j2` to check it works.

## CLI Commands

```bash
# Discover extractable symbols in a file
projected-source list-functions src/file.cpp

# Render a template
projected-source render template.md.j2

# Render to specific output
projected-source render template.md.j2 output.md

# Validate documentation covers code changes
projected-source render docs/ -V auto --strict
```

## Output

Create the template file(s) in the appropriate location. The output should be a `.md.j2` file that renders to clean, readable markdown with embedded code snippets linked to their source.
