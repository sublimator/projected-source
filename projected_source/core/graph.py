"""Extract and analyze the chunk graph from a rendered document.

The graph is derived from the rendered artifact — no side state:
  nodes  ← `<!-- chunk id=".." -->` (code() id= and {% chunk %}) and the
           `id=".."` attribute on `<!-- audit .. -->` notes
  tags   ← the optional `tags=".."` attribute on either anchor
  edges  ← `<!-- edge from=".." type=".." to=".." -->` (the relate() directive)

Forcing authors to write the relationships is the point: it turns a dump into a
structure you can check (orphans, cycles), reorder (topological), and slice by
theme (tags).
"""

import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple

# Opening anchors only — `chunk\s+` and `audit\b` never match the `/chunk` /
# `/audit` end anchors. `.*?` is safe because the renderer neutralizes any `-->`
# inside an attribute value before it reaches the document.
_CHUNK_OPEN_RE = re.compile(r"<!--\s*chunk\s+(.*?)-->")
_AUDIT_OPEN_RE = re.compile(r"<!--\s*audit\s+(.*?)-->")
_EDGE_RE = re.compile(r"<!--\s*edge\s+(.*?)-->")
_ATTR_RE = re.compile(r'(\w+)="([^"]*)"')
# The reader-invisible marker link() emits next to its visible href. Reading the
# marker (not the `](#chunk-..)` href) means a link merely SHOWN in extracted
# source or a code block is never mistaken for an authored link() target.
_LINK_RE = re.compile(r'<!--\s*link\s+to="(chunk-[A-Za-z0-9_-]+)"\s*-->')


def _parse_tags(raw: str) -> Set[str]:
    return {t.strip() for t in raw.split(",") if t.strip()}


def _slug(chunk_id: str) -> str:
    """Anchor slug for a chunk id. MUST match renderer._anchor_slug — the
    dangling-link lint compares link targets against these (a drift test pins
    the two together)."""
    s = re.sub(r"[^A-Za-z0-9_-]+", "-", str(chunk_id)).strip("-")
    return f"chunk-{s}"


@dataclass(frozen=True)
class Edge:
    source: str
    target: str
    kind: str = ""
    label: str = ""


class ChunkGraph:
    def __init__(
        self,
        nodes: Set[str],
        edges: List[Edge],
        node_tags: Optional[Dict[str, Set[str]]] = None,
        document_order: Optional[List[str]] = None,
        link_targets: Optional[Set[str]] = None,
    ):
        self.nodes = set(nodes)
        self.edges = list(edges)
        self.node_tags: Dict[str, Set[str]] = {n: set(node_tags.get(n, set())) for n in self.nodes} if node_tags else {n: set() for n in self.nodes}
        # Reading order — the sequence anchors appear in the document. Falls back
        # to a stable sort so callers always get every node exactly once.
        seen = [n for n in (document_order or []) if n in self.nodes]
        self.document_order: List[str] = seen + sorted(self.nodes - set(seen))
        # Anchor slugs that link() pointed at — whole-document concern, so an
        # induced subgraph carries none (a slice can't judge cross-slice links).
        self.link_targets: Set[str] = set(link_targets or set())

    # -- tags --

    def tags_census(self) -> Dict[str, int]:
        """tag → number of nodes carrying it, for a quick thematic overview."""
        census: Dict[str, int] = {}
        for tags in self.node_tags.values():
            for t in tags:
                census[t] = census.get(t, 0) + 1
        return census

    def nodes_with_tag(self, tag: str) -> Set[str]:
        return {n for n, tags in self.node_tags.items() if tag in tags}

    def subgraph(self, keep: Set[str]) -> "ChunkGraph":
        """Induced subgraph over `keep` — edges are retained only when both
        endpoints survive, so a tag slice stays internally consistent."""
        keep = keep & self.nodes
        edges = [e for e in self.edges if e.source in keep and e.target in keep]
        order = [n for n in self.document_order if n in keep]
        return ChunkGraph(keep, edges, {n: self.node_tags[n] for n in keep}, order, link_targets=set())

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

    def dangling_links(self) -> List[str]:
        """link() targets that resolve to no declared chunk — a broken intra-doc
        hyperlink. Returned as the offending anchor slugs, sorted."""
        declared = {_slug(n) for n in self.nodes}
        return sorted(t for t in self.link_targets if t not in declared)

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
    nodes: Set[str] = set()
    node_tags: Dict[str, Set[str]] = {}
    first_offset: Dict[str, int] = {}  # id → earliest offset across BOTH anchor kinds
    for anchor_re in (_CHUNK_OPEN_RE, _AUDIT_OPEN_RE):
        for match in anchor_re.finditer(rendered):
            attrs = dict(_ATTR_RE.findall(match.group(1)))
            nid = attrs.get("id", "")
            if not nid:
                continue
            nodes.add(nid)
            off = match.start()
            if nid not in first_offset or off < first_offset[nid]:
                first_offset[nid] = off  # true first appearance, even if an audit anchor precedes a chunk one
            if attrs.get("tags"):
                node_tags.setdefault(nid, set()).update(_parse_tags(attrs["tags"]))
    document_order = sorted(nodes, key=lambda n: first_offset[n])
    edges: List[Edge] = []
    for match in _EDGE_RE.finditer(rendered):
        attrs = dict(_ATTR_RE.findall(match.group(1)))
        if attrs.get("from") and attrs.get("to"):
            edges.append(Edge(attrs["from"], attrs["to"], attrs.get("type", ""), attrs.get("label", "")))
    link_targets = set(_LINK_RE.findall(rendered))
    return ChunkGraph(nodes, edges, node_tags, document_order, link_targets=link_targets)
