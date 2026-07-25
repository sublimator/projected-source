"""audit-stubs command — print paste-ready audit() lines for the residual.

Renders a template fully with change validation, then emits one `{{ audit(...) }}`
stub per uncovered changed region. This is the correct home for the "acknowledge
the leftovers" workflow: the audit_remaining() template directive could never
work — the render that would emit the list fails on the mandatory empty reasons,
and a mid-render residual is only partial. Post-render, the residual is exact.

Stubs go to stdout (paste-ready); status and warnings go to stderr.
"""

import logging
import sys
from pathlib import Path

import click

from ..core.changes_set import ChangesSet
from ..core.renderer import TemplateRenderer
from ..core.review_scope import ReviewScopeError, read_template_scope


@click.command("audit-stubs")
@click.argument("template", type=click.Path(exists=True, path_type=Path))
@click.option(
    "-V",
    "--validate-changes",
    "base",
    default="auto",
    help="Diff base (commit/branch/range, or 'auto'). review_scope.base overrides 'auto'.",
)
@click.option(
    "-r",
    "--repo-path",
    type=click.Path(exists=True, path_type=Path),
    default=Path.cwd(),
    help="Repository root path",
)
def audit_stubs(template: Path, base: str, repo_path: Path):
    """Print paste-ready audit() stubs for a template's uncovered changes.

    Renders TEMPLATE with change validation, then emits one `{{ audit(...) }}`
    line per uncovered changed region for you to paste in and give a reason.
    Narrate the interesting changes with code(), run this, and the residual
    becomes a fill-in-the-reasons checklist.

    Example:
        projected-source audit-stubs -V origin/main docs/review.md.j2
    """
    repo_path = repo_path.resolve()

    # review_scope from the template; base precedence: explicit -V > template > auto.
    resolved_base = None if base == "auto" else base
    include = exclude = None
    try:
        scope = read_template_scope(template)
    except ReviewScopeError as e:
        click.echo(f"✗ Invalid review_scope: {e}", err=True)
        sys.exit(1)
    if scope:
        include, exclude = scope["include"], scope["exclude"]
        if resolved_base is None and scope["base"]:
            resolved_base = scope["base"]

    try:
        changes = ChangesSet.from_diff(
            base=resolved_base, repo_path=repo_path, include=include, exclude=exclude
        )
    except RuntimeError as e:
        click.echo(f"✗ Failed to get diff: {e}", err=True)
        sys.exit(1)

    # Render fully so every code()/audit()/ignore_changes() claim lands first;
    # whatever remains uncovered is the residual we stub.
    # stdout is a paste-ready contract, so keep diagnostic logging (e.g. the
    # RichHandler's "no origin remote" warning, emitted while the renderer sets
    # up GitHub integration) off it. logging.disable is a global threshold that
    # overrides individual logger levels, so it holds regardless of how logging
    # was configured elsewhere. Extraction failures still surface via
    # result.errors, which is structured, not logged.
    prev_disable = logging.root.manager.disable
    logging.disable(logging.WARNING)
    try:
        renderer = TemplateRenderer(
            template_dir=template.parent, repo_path=repo_path, changes_set=changes
        )
        result = renderer.render_result(template.name)
    finally:
        logging.disable(prev_disable)
    if not result.ok:
        click.echo(
            f"⚠ {len(result.errors)} extraction error(s) while rendering; stubs may be incomplete",
            err=True,
        )

    uncovered = changes.uncovered()
    if not uncovered:
        click.echo("✓ No uncovered changes — nothing to stub", err=True)
        return

    click.echo(
        f"# {len(uncovered)} uncovered region(s) — paste into {template.name} and fill each reason",
        err=True,
    )
    # Everything on stdout is paste-ready: a Jinja comment header + audit() calls.
    print("{# audit stubs for uncovered changes — replace each empty reason #}")
    for region in uncovered:
        try:
            rel = region.file_path.relative_to(repo_path)
        except ValueError:
            rel = region.file_path
        rel_posix = rel.as_posix()
        start, end = region.start_line, region.end_line
        # committed=True: these are D (committed) coordinates, so audit() must
        # claim them as-is rather than re-mapping working -> committed (F4).
        print(f'{{{{ audit("{rel_posix}", lines=({start}, {end}), committed=True, reason="") }}}}')
