"""Check that templates render and their committed renderings are current."""

import concurrent.futures
import os
import re
import sys
from pathlib import Path

import click
from rich.console import Console

from ..core.renderer import (
    FRONTMATTER_RE,
    PROJECTED_SOURCE_HEADER_RE,
    TemplateRenderer,
)

console = Console()

# Statuses, in increasing severity.
OK = "ok"
STALE = "stale"
UNRENDERED = "unrendered"
BROKEN = "broken"

# Permalinks pin to the commit that was HEAD when the document was rendered, so
# every commit rewrites every permalink in every document. That is not a content
# change — the link still resolves, to a commit where the code was identical —
# and treating it as one would make each document stale the instant it was
# committed, which never converges. The pre-push hook has always normalized
# these away; check must agree with it.
PERMALINK_COMMIT_RE = re.compile(r"/blob/[0-9a-f]{7,40}/")


def _normalize(text: str) -> str:
    """Strip the volatile metadata header and permalink SHAs for comparison.

    Frontmatter is real content and is preserved; only projected-source's
    generated header (rendered_at/branch/commit lines and the last-updated
    banner) is removed, wherever _apply_header placed it.
    """
    front = ""
    match = FRONTMATTER_RE.match(text)
    if match:
        front = text[: match.end()]
        text = text[match.end() :].lstrip("\r\n")

    header = PROJECTED_SOURCE_HEADER_RE.match(text)
    if header:
        text = text[header.end() :]

    # Leading blank lines are an artifact of template statements that render to
    # nothing ({{ ignore_changes(...) }} and friends at the top of a document).
    # Strip them from BOTH sides: a freshly rendered document still carries
    # them, while a committed one has them tucked behind the metadata header —
    # stripping only the latter makes every such document look permanently
    # stale. Trailing-newline differences (Jinja's keep_trailing_newline vs
    # editors) are not staleness either.
    text = PERMALINK_COMMIT_RE.sub("/blob/COMMIT/", text)
    return (front + text.lstrip("\r\n")).rstrip("\r\n")


def _check_template(template: Path, repo_path: Path) -> tuple[str, str]:
    """Return (status, detail) for one template."""
    renderer = TemplateRenderer(
        template_dir=template.parent,
        repo_path=repo_path,
    )
    try:
        result = renderer.render_result(template.name)
    except Exception as e:  # render errors are the finding, not a crash
        return BROKEN, re.sub(r"\s+", " ", str(e))[:300]

    # The renderer degrades extraction failures into the output instead of
    # raising (missing markers, moved functions, deleted files). A render that
    # "succeeds" with failed extractions is broken, not stale. render_result
    # reports them structurally — do not scan the text, or a document quoting
    # error-handling source (as ours does) would report itself broken.
    if result.errors:
        first = re.sub(r"\s+", " ", str(result.errors[0]))
        more = f" (+{len(result.errors) - 1} more)" if len(result.errors) > 1 else ""
        return BROKEN, f"{first[:200]}{more}"

    rendered = result.text
    rendered_path = template.with_suffix("") if template.suffix == ".j2" else None
    if rendered_path is None or not rendered_path.exists():
        return UNRENDERED, "no committed rendering beside the template"

    committed = rendered_path.read_text()
    if _normalize(rendered) != _normalize(committed):
        return STALE, "rendered output differs from the committed document"

    return OK, ""


@click.command()
@click.argument("input_path", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--repo-path",
    "-r",
    type=click.Path(exists=True, path_type=Path),
    default=".",
    help="Repository root path",
)
@click.option(
    "--jobs",
    "-j",
    type=int,
    default=None,
    help="Parallel render jobs (default: CPU count)",
)
@click.option(
    "--strict",
    is_flag=True,
    default=False,
    help="Also fail (exit 1) on stale or unrendered documents",
)
@click.option(
    "--show-stale",
    "-s",
    is_flag=True,
    default=False,
    help="List stale documents individually (always counted in the summary)",
)
def check(input_path, repo_path, jobs, strict, show_stale):
    """Check templates render, and committed renderings are current.

    INPUT_PATH is a .j2 file or a directory searched recursively.

    Statuses: broken (template no longer renders — e.g. a moved or renamed
    //@@ marker), stale (renders, but differs from the committed .md after
    ignoring the volatile metadata header), unrendered (no committed .md
    beside the template), ok. Exit 1 on any broken template; with --strict,
    also on stale/unrendered.

    Note: this --strict is about rendered-artifact freshness. Validating
    that code changes are documented is 'render -V <base> --strict'.
    """
    repo_path = repo_path.resolve()

    if input_path.is_dir():
        templates = sorted(input_path.glob("**/*.j2"))
    else:
        templates = [input_path]

    if not templates:
        console.print(f"[yellow]No .j2 templates found in {input_path}[/yellow]")
        return

    workers = jobs or os.cpu_count() or 1
    results: list[tuple[Path, str, str]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(_check_template, template, repo_path): template
            for template in templates
        }
        for future in concurrent.futures.as_completed(futures):
            template = futures[future]
            status, detail = future.result()
            results.append((template, status, detail))

    base = input_path if input_path.is_dir() else input_path.parent
    results.sort(key=lambda item: str(item[0]))
    counts = {OK: 0, STALE: 0, UNRENDERED: 0, BROKEN: 0}
    style = {STALE: "yellow", UNRENDERED: "yellow", BROKEN: "red"}
    for template, status, detail in results:
        counts[status] += 1
        if status == OK or (status == STALE and not show_stale and not strict):
            continue
        try:
            display = template.relative_to(base)
        except ValueError:
            display = template
        suffix = f": {detail}" if detail else ""
        console.print(
            f"[{style[status]}]{status.upper()}[/{style[status]}] "
            f"{display}{suffix}"
        )

    console.print(
        f"{len(results)} template(s): {counts[OK]} ok, {counts[STALE]} stale, "
        f"{counts[UNRENDERED]} unrendered, {counts[BROKEN]} broken"
    )

    if counts[BROKEN] or (strict and (counts[STALE] or counts[UNRENDERED])):
        sys.exit(1)
