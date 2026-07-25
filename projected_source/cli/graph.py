"""graph command — show and check the chunk graph of a rendered document."""

import logging
import sys
from pathlib import Path

import click

from ..core.config import load_config
from ..core.graph import extract_graph
from ..core.renderer import TemplateRenderer
from .helpers import console


@click.command("graph")
@click.argument("template", type=click.Path(exists=True, path_type=Path))
@click.option(
    "-r",
    "--repo-path",
    type=click.Path(exists=True, path_type=Path),
    default=Path.cwd(),
    help="Repository root path",
)
@click.option("--topo", is_flag=True, help="Print a topological order of the chunks")
@click.option(
    "--strict",
    is_flag=True,
    help="Exit 1 on orphans, cycles, dangling edges, or a [graph] policy violation",
)
def graph(template: Path, repo_path: Path, topo: bool, strict: bool):
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

    console.print(
        f"[cyan]Chunk graph[/cyan] — {len(g.nodes)} node(s), {len(g.edges)} edge(s) "
        f"(density {g.density():.2f})"
    )

    dangling = g.dangling_edges()
    cycle = g.find_cycle()
    order, cyclic = g.topological_order()

    # [graph] policy from .projected-source.toml.
    min_edges = int(cfg.get("graph", "min_edges_per_node", 0) or 0)  # numeric dial; 1 == no orphans
    forbid_cycles = bool(cfg.get("graph", "forbid_cycles", False))
    min_density = cfg.get("graph", "min_edge_density", None)

    degree = g.degree()
    underconnected = sorted(n for n, d in degree.items() if d < min_edges) if min_edges else g.orphans()

    fail = False

    # A dangling edge is always a defect — it references a node that isn't there.
    if dangling:
        console.print(f"  [yellow]dangling edges ({len(dangling)}):[/yellow]")
        for e in dangling:
            console.print(f"    [yellow]{e.source} -> {e.target} (undeclared node)[/yellow]")
        fail = True

    # Under-connected nodes. With a dialed minimum they fail; otherwise orphans
    # (degree 0) are surfaced but not fatal.
    if underconnected:
        if min_edges:
            console.print(
                f"  [yellow]under-connected ({len(underconnected)}, need >= {min_edges} "
                f"edge(s)): {', '.join(underconnected)}[/yellow]"
            )
            fail = True
        else:
            console.print(f"  [dim]orphans ({len(underconnected)}): {', '.join(underconnected)}[/dim]")

    # Cycles are reported; fatal only if you opt in (they can be normalized —
    # topo condenses the strongly-connected part rather than crashing).
    if cycle:
        style = "red" if forbid_cycles else "dim"
        console.print(f"  [{style}]cycle: {' -> '.join(cycle)}[/{style}]")
        if forbid_cycles:
            fail = True

    if min_density is not None and g.density() < float(min_density):
        console.print(f"  [yellow]edge density {g.density():.2f} < min_edge_density {min_density}[/yellow]")
        fail = True

    if not (dangling or underconnected or cycle):
        console.print("  [green]✓ connected, acyclic, no dangling edges[/green]")

    if topo:
        if cyclic:
            console.print(f"  [yellow]no topological order (cycle involves: {', '.join(cyclic)})[/yellow]")
        else:
            console.print(f"  topological order: {' -> '.join(order) if order else '(empty)'}")

    if strict and fail:
        console.print("\n[red]✗ Graph check failed (--strict)[/red]")
        sys.exit(1)
