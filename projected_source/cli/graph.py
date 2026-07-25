"""graph command — show and check the chunk graph of a rendered document."""

import logging
import sys
from pathlib import Path

import click
from rich.markup import escape

from ..core.config import load_config
from ..core.graph import extract_graph
from ..core.renderer import TemplateRenderer
from .helpers import console


def _join(items) -> str:
    """Escape author-controlled ids/tags before they hit Rich markup, so a `[`
    in a name can't crash the command or silently vanish."""
    return ", ".join(escape(str(i)) for i in items)


def _arrow(items) -> str:
    return " -> ".join(escape(str(i)) for i in items)


@click.command("graph")
@click.argument("template", type=click.Path(exists=True, path_type=Path))
@click.option(
    "-r",
    "--repo-path",
    type=click.Path(exists=True, path_type=Path),
    default=Path.cwd(),
    help="Repository root path",
)
@click.option("--topo", is_flag=True, help="Print a topological (dependency) order of the chunks")
@click.option("--doc", is_flag=True, help="Print the document (reading) order of the chunks")
@click.option(
    "--tag",
    "tags",
    multiple=True,
    help="Slice to chunks carrying any of these tags (induced subgraph). Repeatable.",
)
@click.option(
    "--strict",
    is_flag=True,
    help="Exit 1 on orphans, cycles, dangling edges, or a [graph] policy violation",
)
def graph(template: Path, repo_path: Path, topo: bool, doc: bool, tags: tuple, strict: bool):
    """Show the chunk graph of a rendered document.

    Nodes are chunk ids — code(id=..), {% chunk %}, audit(id=..); edges are
    relate() declarations. Reports orphans (chunks that connect to nothing),
    cycles, dangling edges, density, and a topological order. --strict fails on
    a structural problem or a [graph] policy in .projected-source.toml.
    """
    repo_path = repo_path.resolve()

    # Keep diagnostic logging off the render (as audit-stubs does).
    prev_disable = logging.root.manager.disable
    logging.disable(logging.WARNING)
    try:
        renderer = TemplateRenderer(template_dir=template.parent, repo_path=repo_path)
        result = renderer.render_result(template.name)
    finally:
        logging.disable(prev_disable)
    if not result.ok:
        console.print(f"[yellow]⚠ {len(result.errors)} extraction error(s) while rendering[/yellow]")

    g = extract_graph(result.text)
    cfg = load_config(template)

    # A tag census names the themes before any slicing — a quick read on whether
    # the tour is balanced or lopsided.
    census = g.tags_census()
    if census:
        summary = ", ".join(f"{escape(t)}×{n}" for t, n in sorted(census.items(), key=lambda kv: (-kv[1], kv[0])))
        console.print(f"[cyan]tags[/cyan] — {summary}")

    # --tag slices to the induced subgraph so orphan/cycle/topo apply to the theme.
    if tags:
        keep = set().union(*(g.nodes_with_tag(t) for t in tags))
        g = g.subgraph(keep)
        console.print(f"[cyan]slice[/cyan] — tag(s) {_join(tags)}: {len(g.nodes)} node(s)")

    console.print(
        f"[cyan]Chunk graph[/cyan] — {len(g.nodes)} node(s), {len(g.edges)} edge(s) "
        f"(density {g.density():.2f})"
    )

    dangling = g.dangling_edges()
    dangling_links = g.dangling_links()
    cycle = g.find_cycle()
    order, cyclic = g.topological_order()

    # [graph] policy from .projected-source.toml.
    min_edges = int(cfg.get("graph", "min_edges_per_node", 0) or 0)  # numeric dial; 1 == no orphans
    forbid_cycles = bool(cfg.get("graph", "forbid_cycles", False))
    min_density = cfg.get("graph", "min_edge_density", None)

    degree = g.degree()
    underconnected = sorted(n for n, d in degree.items() if d < min_edges) if min_edges else g.orphans()
    density_bad = min_density is not None and g.density() < float(min_density)

    fail = False

    # A dangling edge is always a defect — it references a node that isn't there.
    if dangling:
        console.print(f"  [yellow]dangling edges ({len(dangling)}):[/yellow]")
        for e in dangling:
            console.print(f"    [yellow]{escape(e.source)} -> {escape(e.target)} (undeclared node)[/yellow]")
        fail = True

    # A link() to a chunk that doesn't exist is a broken intra-doc hyperlink —
    # the lint that makes link() safe to use expressively (always a defect).
    if dangling_links:
        console.print(f"  [yellow]dangling links ({len(dangling_links)}):[/yellow]")
        for slug in dangling_links:
            console.print(f"    [yellow]{escape(slug)} (no such chunk)[/yellow]")
        fail = True

    # Under-connected nodes. With a dialed minimum they fail; otherwise orphans
    # (degree 0) are surfaced but not fatal.
    if underconnected:
        if min_edges:
            console.print(
                f"  [yellow]under-connected ({len(underconnected)}, need >= {min_edges} "
                f"edge(s)): {_join(underconnected)}[/yellow]"
            )
            fail = True
        else:
            console.print(f"  [dim]orphans ({len(underconnected)}): {_join(underconnected)}[/dim]")

    # Cycles are reported; fatal only if you opt in (they can be normalized —
    # topo condenses the strongly-connected part rather than crashing).
    if cycle:
        style = "red" if forbid_cycles else "dim"
        console.print(f"  [{style}]cycle: {_arrow(cycle)}[/{style}]")
        if forbid_cycles:
            fail = True

    if density_bad:
        console.print(f"  [yellow]edge density {g.density():.2f} < min_edge_density {min_density}[/yellow]")
        fail = True

    if not (dangling or dangling_links or underconnected or cycle or density_bad):
        console.print("  [green]✓ connected, acyclic, no dangling edges or links[/green]")

    if doc:
        console.print(f"  document order: {_arrow(g.document_order) if g.document_order else '(empty)'}")

    if topo:
        if cyclic:
            console.print(f"  [yellow]no topological order (cycle involves: {_join(cyclic)})[/yellow]")
        else:
            console.print(f"  topological order: {_arrow(order) if order else '(empty)'}")

    if strict and fail:
        console.print("\n[red]✗ Graph check failed (--strict)[/red]")
        sys.exit(1)
