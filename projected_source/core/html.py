"""Convert rendered Markdown into a self-contained readable HTML document."""

from __future__ import annotations

import html
import re
from pathlib import Path

from markdown_it import MarkdownIt

from .renderer import FRONTMATTER_RE, PROJECTED_SOURCE_HEADER_RE

_TITLE_RE = re.compile(r"^title:[ \t]*(.+?)[ \t]*$", re.MULTILINE)
_UPDATED_RE = re.compile(r"<sub>(Last updated:.*?)</sub>", re.DOTALL)
_NON_SLUG_RE = re.compile(r"[^\w\s-]", re.UNICODE)
_SPACE_RE = re.compile(r"[\s_-]+")


def _frontmatter_title(frontmatter: str) -> str | None:
    match = _TITLE_RE.search(frontmatter)
    if not match:
        return None
    value = match.group(1).strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        value = value[1:-1]
    return value or None


def _strip_document_wrappers(markdown: str) -> tuple[str, str | None, str | None]:
    """Remove YAML and projected-source wrappers, retaining useful metadata."""
    title = None
    frontmatter = FRONTMATTER_RE.match(markdown)
    if frontmatter:
        title = _frontmatter_title(frontmatter.group(0))
        markdown = markdown[frontmatter.end() :].lstrip("\r\n")

    updated = None
    header = PROJECTED_SOURCE_HEADER_RE.match(markdown)
    if header:
        updated_match = _UPDATED_RE.search(header.group(0))
        if updated_match:
            updated = re.sub(r"\s+", " ", updated_match.group(1)).strip()
        markdown = markdown[header.end() :].lstrip("\r\n")

    return markdown, title, updated


def _heading_text(token) -> str:
    if token.children:
        return "".join(child.content for child in token.children if child.type in {"text", "code_inline"}).strip()
    return token.content.strip()


def _slug(value: str, fallback: str, used: dict[str, int]) -> str:
    base = _SPACE_RE.sub("-", _NON_SLUG_RE.sub("", value.casefold())).strip("-") or fallback
    count = used.get(base, 0) + 1
    used[base] = count
    return base if count == 1 else f"{base}-{count}"


def _markdown_parser() -> MarkdownIt:
    parser = MarkdownIt(
        "commonmark",
        {"html": True, "linkify": False, "typographer": True},
    )
    parser.enable(["table", "strikethrough"])
    return parser


def markdown_to_html(markdown: str, *, title_hint: str | None = None) -> str:
    """Render Markdown as a complete HTML document with embedded CSS."""
    markdown, frontmatter_title, updated = _strip_document_wrappers(markdown)
    parser = _markdown_parser()
    tokens = parser.parse(markdown)

    first_h1 = None
    used_slugs: dict[str, int] = {}
    for index, token in enumerate(tokens):
        if token.type != "heading_open":
            continue
        inline = tokens[index + 1] if index + 1 < len(tokens) else None
        heading = _heading_text(inline) if inline and inline.type == "inline" else ""
        if token.tag == "h1" and first_h1 is None and heading:
            first_h1 = heading
        token.attrSet("id", _slug(heading, f"section-{index}", used_slugs))

    title = frontmatter_title or first_h1 or title_hint or "Document"
    body = parser.renderer.render(tokens, parser.options, {})
    footer = f'<footer class="document-meta">{html.escape(updated)}</footer>' if updated else ""

    return _HTML_SHELL.format(
        title=html.escape(title),
        body=body,
        footer=footer,
    )


def default_html_output(path: Path) -> Path:
    """Map ``name.md.j2`` or ``name.j2`` to ``name.html``."""
    without_j2 = path.with_suffix("") if path.suffix == ".j2" else path
    return without_j2.with_suffix(".html")


_HTML_SHELL = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title}</title>
  <style>
    :root {{
      color-scheme: light dark;
      --page: #f7f8fa;
      --surface: #ffffff;
      --text: #20242a;
      --muted: #66717d;
      --line: #d9dee5;
      --accent: #087f73;
      --code: #161b22;
      --code-text: #e6edf3;
      --quote: #eef7f5;
    }}
    * {{ box-sizing: border-box; }}
    html {{ scroll-behavior: smooth; }}
    body {{
      margin: 0;
      background: var(--page);
      color: var(--text);
      font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      font-size: 17px;
      line-height: 1.68;
      letter-spacing: 0;
    }}
    main {{
      width: min(100% - 32px, 900px);
      margin: 32px auto;
      padding: 48px 64px 64px;
      background: var(--surface);
      border: 1px solid var(--line);
      border-radius: 6px;
    }}
    h1, h2, h3, h4, h5, h6 {{
      margin: 2em 0 0.65em;
      line-height: 1.24;
      letter-spacing: 0;
      scroll-margin-top: 24px;
    }}
    h1 {{ margin-top: 0; font-size: 2.25rem; }}
    h2 {{ padding-top: 0.7em; border-top: 1px solid var(--line); font-size: 1.55rem; }}
    h3 {{ font-size: 1.25rem; }}
    p, ul, ol, blockquote, table, pre, details {{ margin: 1em 0; }}
    a {{ color: var(--accent); text-underline-offset: 0.16em; }}
    a:hover {{ text-decoration-thickness: 2px; }}
    code {{
      padding: 0.14em 0.35em;
      border: 1px solid var(--line);
      border-radius: 4px;
      background: var(--page);
      font: 0.88em ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    }}
    pre {{
      overflow: auto;
      padding: 18px 20px;
      border-radius: 6px;
      background: var(--code);
      color: var(--code-text);
      line-height: 1.5;
    }}
    pre code {{ padding: 0; border: 0; background: transparent; color: inherit; }}
    blockquote {{
      margin-left: 0;
      padding: 0.45em 1.1em;
      border-left: 4px solid var(--accent);
      background: var(--quote);
      color: var(--muted);
    }}
    table {{ width: 100%; border-collapse: collapse; font-size: 0.95em; }}
    th, td {{ padding: 0.6em 0.75em; border: 1px solid var(--line); text-align: left; vertical-align: top; }}
    th {{ background: var(--page); }}
    hr {{ margin: 2.5em 0; border: 0; border-top: 1px solid var(--line); }}
    img {{ max-width: 100%; height: auto; }}
    details {{ padding: 0.8em 1em; border: 1px solid var(--line); border-radius: 6px; }}
    summary {{ cursor: pointer; font-weight: 650; }}
    .document-meta {{
      margin-top: 4em;
      padding-top: 1em;
      border-top: 1px solid var(--line);
      color: var(--muted);
      font-size: 0.82em;
    }}
    @media (prefers-color-scheme: dark) {{
      :root {{
        --page: #111418;
        --surface: #191d22;
        --text: #e7e9ec;
        --muted: #a8b0ba;
        --line: #363d46;
        --accent: #55c8b9;
        --quote: #172724;
      }}
    }}
    @media (max-width: 680px) {{
      body {{ font-size: 16px; }}
      main {{ width: 100%; margin: 0; padding: 28px 20px 48px; border: 0; border-radius: 0; }}
      h1 {{ font-size: 1.85rem; }}
      h2 {{ font-size: 1.4rem; }}
    }}
    @media print {{
      :root {{ --page: #fff; --surface: #fff; --text: #000; --line: #bbb; }}
      main {{ width: 100%; margin: 0; padding: 0; border: 0; }}
      a {{ color: inherit; }}
      pre {{ white-space: pre-wrap; }}
    }}
  </style>
</head>
<body>
  <main>
{body}
{footer}
  </main>
</body>
</html>
"""
