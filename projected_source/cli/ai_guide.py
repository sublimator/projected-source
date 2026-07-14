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

All extraction modes except `lines=` are **symbolic** — they survive
refactoring. The choice between them is about granularity, not stability:

- **Non-invasive symbols** (`function=`, `struct=`, `var=`, `message=`, etc.)
  read what's already there. Free, but extract whole units.
- **Invasive symbols** (`marker=`, `function='X', marker='Y'`) require adding
  `//@@start name` / `//@@end name` comments to the source. Costs a source
  edit, but lets you point at exactly the lines that matter.

Prefer the smallest extract that is both stable AND useful for the reader.
A 400-line orchestration function with one interesting decision point buries
the point — add a marker around the gate and reference that.

Extraction priority (best to worst):
1. `function='Name', marker='section-name'` - specific logic inside a large function
2. `function='Name'` - when the function is short enough to read as a unit
3. `struct=`, `message=`, `enum=`, `var=` - when the whole definition is relevant
4. `function_macro=` / `macro_definition=` - C/C++ macro-based code
5. `marker='section-name'` - cross-cutting or non-symbol regions
6. `lines=(start, end)` - last resort, fragile, breaks when code changes

## CLI Usage

```bash
# Render a single template
projected-source render template.md.j2

# Render to specific output
projected-source render template.md.j2 output.md

# Render Markdown into a self-contained readable HTML document
projected-source render template.md.j2 --html

# Re-render when templates, includes, or repository sources change
projected-source render template.md.j2 --html --watch

# Render directory of templates
projected-source render docs/

# Discover extractable symbols in a file
projected-source list-functions src/file.cpp

# Validate documentation covers code changes
projected-source render docs/ -V auto              # auto-detect base
projected-source render docs/ -V auto --strict     # exit 1 if uncovered
```

`--html` is only a final presentation transform. Template evaluation and
source projection still produce Markdown first; `--no-html` remains the
default. The generated HTML has embedded responsive styling and preserves raw
HTML such as `<details>` without requiring external assets.

`--watch` renders once, then regenerates after relevant filesystem changes.
Generated outputs are ignored to avoid loops. Watch mode requires file or
directory input/output and cannot be combined with `--commit`.

## Recipe: throwaway docs (PR descriptions, reviews)

Templates don't have to render to committed files. A common use is a
`pr-description.md.j2` (or `review.md.j2`, `report.md.j2`) kept in a gitignored
`.ai-docs/` folder: render it, pipe the output into the PR/comment, and keep the
repo diff clean — the analysis travels in the description, not the tree.

```bash
# .ai-docs/ is gitignored; the template + rendered output never get committed
projected-source render --no-header --enclosure-context 2 .ai-docs/pr-description.md.j2 .ai-docs/pr-description.md
gh pr edit 123 --body-file .ai-docs/pr-description.md
```

- Use `--no-header` so no render metadata leaks into the description.
- C/C++ extractor-backed marker extracts include first/last enclosing-symbol context by default.
  Use `--enclosure-context N` to change the global default, `--enclosure-context 0`
  to disable it globally, or per-call `enclosure_context=0` to opt out locally.
  Other languages currently keep exact marker output unless they add enclosed
  marker support.
- `code()` extracts become live GitHub permalinks. Pin them with `ref=` (or a
  block-level `set_code_context(ref=...)`) to a commit that actually contains the
  code you're quoting — handy when the PR branch has since changed those lines.
- Collapse long analysis behind `<details>` blocks so the description stays
  scannable.

## Template Functions

### code() - Extract code with GitHub permalinks

```jinja
{{{{ code('src/file.cpp', function='processTransaction') }}}}
{{{{ code('src/file.cpp', function='onMessage', signature='TMProposeSet') }}}}
{{{{ code('src/file.h', struct='Config') }}}}
{{{{ code('src/file.cpp', var='errorCodes') }}}}
{{{{ code('src/file.cpp', marker='example-usage') }}}}
{{{{ code('src/file.cpp', function='main', marker='init-section') }}}}
{{{{ code('src/file.cpp', function='share', signature='TxSetShare', marker='encode') }}}}
{{{{ code('src/file.cpp', function='main', marker='init-section', enclosure_context=2) }}}}
{{{{ code('src/file.cpp', marker='init-section', enclosure_context=0) }}}}

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

{{# Rust #}}
{{{{ code('src/node.rs', function='start') }}}}
{{{{ code('src/node.rs', function='NodeStore.store') }}}}  {{# method inside an impl block #}}
{{{{ code('src/key.rs', struct='Key') }}}}
{{{{ code('src/message.rs', enum='MessageType') }}}}
{{{{ code('src/config.rs', var='MAX_SIZE') }}}}

{{# Lean 4 — def, theorem, example, abbrev, instance all answer function= #}}
{{{{ code('Proofs.lean', function='selectEntropyTier') }}}}
{{{{ code('Proofs.lean', function='no_unl_report_selects_fallback') }}}}  {{# theorem #}}
{{{{ code('Proofs.lean', function='XahauConsensus.selectEntropyTier') }}}}  {{# namespace-qualified #}}
{{{{ code('Proofs.lean', function='Point.origin') }}}}  {{# dotted name is one identifier in Lean #}}
{{{{ code('Proofs.lean', struct='EntropyTier') }}}}  {{# inductive or structure #}}
{{{{ code('Proofs.lean', var='secret') }}}}  {{# axiom / opaque / constant / initialize #}}

{{# Options #}}
{{{{ code('src/file.cpp', function='foo', github=False) }}}}      {{# no permalink #}}
{{{{ code('src/file.cpp', function='foo', line_numbers=False) }}}} {{# no line nums #}}
{{{{ code('src/file.cpp', function='foo', blame=True) }}}}         {{# git blame #}}
{{{{ code('src/file.cpp', function='foo', ref='v1.0') }}}}         {{# from git ref #}}
{{{{ code('src/file.cpp', function='foo', root='/path/to/repo') }}}} {{# different root #}}
```

### Comments - Author notes that don't render

Jinja2 `{{# ... #}}` comments are stripped at render time. Use them for
template-author notes that shouldn't appear in the output `.md`:

```jinja
{{# This entire block is gone in the rendered output #}}
{{# TODO: also document the caller of this function #}}
{{# Multi-line works too:
   notes for whoever maintains this template
   that nobody downstream sees #}}

{{{{ code('src/file.cpp', function='foo') }}}}
```

Distinct from markdown `<!-- ... -->` comments, which persist in the output.
Use Jinja2 comments for "why I extracted this" notes; use markdown comments
when you want the comment to survive into the rendered file.

### include() / include_body() - Include peer files

```jinja
{{{{ include('background.md') }}}}       {{# raw markdown, no template processing #}}
{{{{ include('details.md.j2') }}}}       {{# rendered as Jinja2 template #}}
{{{{ include_body('walkthrough.md.j2') }}}} {{# render, then strip doc wrappers #}}
```

Paths are relative to the template directory. `.j2` files are rendered as
templates with full access to `code()`, caller variables, and other functions.
`include()` preserves frontmatter and projected-source metadata headers verbatim;
use `include_body()` when embedding a standalone rendered/walkthrough document
inside another doc.

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

## Disambiguating Overloaded C++ Functions (signature=)

C++ functions are often overloaded (same name, different parameters) and many
appear twice — once as an in-class **declaration** and once as an out-of-line
**definition**. Use this workflow instead of falling back to `lines=`:

1. Run `list-functions <file>` and find the symbol. Overloads share a name and
   each is printed with a `signature='...'` hint, e.g.:

   ```
   'xrpl::Consensus::Consensus'  line 316  signature='(Consensus&&)'
   'xrpl::Consensus::Consensus'  line 324  signature='(clock_type const& clock,
   Adaptor& adaptor, beast::Journal j)'
   ```

2. Pick a **distinctive substring** of the parameters and pass it as `signature=`:

   ```jinja
   {{{{ code('Consensus.h', function='Consensus::Consensus', signature='clock_type') }}}}
   ```

Key facts about `signature=`:
- It is a **case-sensitive substring match** against the parameter-list text
  (including parameter names), not an exact signature. `signature='clock_type'`,
  `signature='Adaptor&'`, or `signature='Journal j'` all select the same overload.
- Pick the shortest substring that is unique to the overload you want — usually a
  distinctive parameter **type** (`'TMProposeSet'`, `'std::string'`, `'int a, int b'`).
- It correctly selects a **declaration-only** overload even when another overload
  of the same name has a body (e.g. a defaulted `Foo(Foo&&) = default`).
- Without `signature=`, the first/with-body match wins — which may not be the one
  you want for overloaded or defaulted symbols, so prefer `signature=` for overloads.

## Marker Syntax in Source Files

```cpp
// C/C++, Rust, Java, TypeScript, Protobuf
//@@start section-name
code here
//@@end section-name
```

```lean
-- Lean 4
-- @@start section-name
code here
-- @@end section-name
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
2. **Use `signature=` for C++ overloads** - substring match on the parameter list,
   e.g. `function='onMessage', signature='TMProposeSet'`. See "Disambiguating
   Overloaded C++ Functions" above for the full workflow — use it instead of `lines=`.
3. **Dotted paths for methods** - `function='Class.method'` works in Java, TypeScript, Python, Rust.
   In Lean, dotted names are single identifiers (`def Point.origin`) — same syntax, different mechanism.
4. **Use `list-functions`** to discover extractable symbols in any supported file
   (add `--include-tests` to surface items inside Rust `#[cfg(test)]` modules)
5. **Use `ref=`** to extract code from any git branch, tag, or commit
6. **Use `root=`** with absolute paths for multi-repo documentation
7. **Untracked files** - extracting from a new, uncommitted file works, but its
   GitHub permalink would 404, so it is auto-suppressed and rendered as a plain
   `*(untracked — no permalink)*` reference. Commit the file to get a live link.
8. **YAML frontmatter is preserved** - if a template renders to a body that starts
   with a `---` frontmatter block, the metadata header is inserted *after* the
   closing `---` so frontmatter stays on line 1. Use `--no-header` to omit the
   metadata header entirely.
9. **Includes are not automatically body-only** - `include()` keeps included
   frontmatter and projected-source metadata headers. Use `include_body()` for
   PR descriptions or nested walkthroughs where only the document body should
   appear.
"""
    click.echo(guide)
