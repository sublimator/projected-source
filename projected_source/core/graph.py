"""Extract and analyze the chunk graph from a rendered document.

The graph is derived from the rendered artifact — no side state:
  nodes  ← `<!-- chunk id=".." -->` (code() id= and {% chunk %}) and the
           `id=".."` attribute on `<!-- audit .. -->` notes
  edges  ← `<!-- edge from=".." type=".." to=".." -->` (the relate() directive)

Forcing authors to write the relationships is the point: it turns a dump into a
structure you can check (orphans, cycles) and reorder (topological).
"""

import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple

_CHUNK_RE = re.compile(r'<!--\s*chunk\s+id="([^"]*)"')
_AUDIT_ID_RE = re.compile(r'<!--\s*audit\b[^>]*?\bid="([^"]*)"')
_EDGE_RE = re.compile(r"<!--\s*edge\s+(.*?)-->")
_ATTR_RE = re.compile(r'(\w+)="([^"]*)"')


@dataclass(frozen=True)
class Edge:
    source: str
    target: str
    kind: str = ""
    label: str = ""


class ChunkGraph:
    def __init__(self, nodes: Set[str], edges: List[Edge]):
        self.nodes = set(nodes)
        self.edges = list(edges)

    # -- degrees / orphans --

    def degree(self) -> Dict[str, int]:
        """Undirected degree per node (self-loops count once)."""
        deg = {n: 0 for n in self.nodes}
        for e in self.edges:
            if e.source in deg:
                deg[e.source] += 1
            if e.target in deg and e.target != e.source:
                deg[e.target] += 1
        return deg

    def orphans(self) -> List[str]:
        """Nodes with no edge at all — the floating dump fragments."""
        return sorted(n for n, d in self.degree().items() if d == 0)

    def dangling_edges(self) -> List[Edge]:
        """Edges whose endpoints aren't declared nodes (a broken reference)."""
        return [e for e in self.edges if e.source not in self.nodes or e.target not in self.nodes]

    def density(self) -> float:
        return (len(self.edges) / len(self.nodes)) if self.nodes else 0.0

    # -- ordering / cycles (directed) --

    def _directed_adjacency(self) -> Dict[str, List[str]]:
        adj: Dict[str, List[str]] = {n: [] for n in self.nodes}
        for e in self.edges:
            if e.source in self.nodes and e.target in self.nodes:
                adj[e.source].append(e.target)
        return adj

    def topological_order(self) -> Tuple[List[str], List[str]]:
        """Kahn's algorithm. Returns (order, cyclic_nodes); cyclic non-empty ⇒ a cycle."""
        adj = self._directed_adjacency()
        indeg = {n: 0 for n in self.nodes}
        for src, tos in adj.items():
            for t in tos:
                indeg[t] += 1
        queue = sorted(n for n in self.nodes if indeg[n] == 0)
        order: List[str] = []
        while queue:
            n = queue.pop(0)
            order.append(n)
            for m in sorted(adj[n]):
                indeg[m] -= 1
                if indeg[m] == 0:
                    queue.append(m)
            queue.sort()
        cyclic = sorted(n for n in self.nodes if n not in order)
        return order, cyclic

    def find_cycle(self) -> Optional[List[str]]:
        """One directed cycle as a node path (…→x→…→x), or None."""
        adj = self._directed_adjacency()
        WHITE, GRAY, BLACK = 0, 1, 2
        color = {n: WHITE for n in self.nodes}
        stack: List[str] = []

        def dfs(u: str) -> Optional[List[str]]:
            color[u] = GRAY
            stack.append(u)
            for v in sorted(adj[u]):
                if color[v] == GRAY:
                    return stack[stack.index(v):] + [v]
                if color[v] == WHITE:
                    found = dfs(v)
                    if found:
                        return found
            stack.pop()
            color[u] = BLACK
            return None

        for n in sorted(self.nodes):
            if color[n] == WHITE:
                found = dfs(n)
                if found:
                    return found
        return None


def extract_graph(rendered: str) -> ChunkGraph:
    """Build the ChunkGraph from a rendered document's anchors and edges."""
    nodes: Set[str] = set(_CHUNK_RE.findall(rendered)) | set(_AUDIT_ID_RE.findall(rendered))
    nodes.discard("")
    edges: List[Edge] = []
    for match in _EDGE_RE.finditer(rendered):
        attrs = dict(_ATTR_RE.findall(match.group(1)))
        if attrs.get("from") and attrs.get("to"):
            edges.append(Edge(attrs["from"], attrs["to"], attrs.get("type", ""), attrs.get("label", "")))
    return ChunkGraph(nodes, edges)
