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

    orphans = g.orphans()
    dangling = g.dangling_edges()
    cycle = g.find_cycle()
    order, cyclic = g.topological_order()

    problems = 0
    if orphans:
        console.print(f"  [yellow]orphans ({len(orphans)}): {', '.join(orphans)}[/yellow]")
        problems += 1
    if dangling:
        console.print(f"  [yellow]dangling edges ({len(dangling)}):[/yellow]")
        for e in dangling:
            console.print(f"    [yellow]{e.source} -> {e.target} (undeclared node)[/yellow]")
        problems += 1
    if cycle:
        console.print(f"  [red]cycle: {' -> '.join(cycle)}[/red]")
        problems += 1
    if not problems:
        console.print("  [green]✓ connected, acyclic, no dangling edges[/green]")

    if topo:
        if cyclic:
            console.print(f"  [yellow]no topological order (cycle involves: {', '.join(cyclic)})[/yellow]")
        else:
            console.print(f"  topological order: {' -> '.join(order) if order else '(empty)'}")

    # [graph] policy from .projected-source.toml (the configurable edge-density dial).
    require_connected = bool(
        cfg.get("graph", "require_edge_per_node", False) or cfg.get("graph", "require_connected", False)
    )
    forbid_cycles = bool(cfg.get("graph", "forbid_cycles", False))
    min_density = cfg.get("graph", "min_edge_density", None)

    policy_violated = bool(dangling)  # a dangling edge is always a defect
    if require_connected and orphans:
        policy_violated = True
    if forbid_cycles and cycle:
        policy_violated = True
    if min_density is not None and g.density() < float(min_density):
        console.print(
            f"  [yellow]edge density {g.density():.2f} < min_edge_density {min_density}[/yellow]"
        )
        policy_violated = True

    if strict and (problems or policy_violated):
        console.print("\n[red]✗ Graph check failed (--strict)[/red]")
        sys.exit(1)
