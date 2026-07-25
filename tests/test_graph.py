"""Tests for the chunk graph — extraction + orphan/cycle/topo analysis, and the
`graph` CLI command."""

from pathlib import Path

import pytest
from click.testing import CliRunner

from projected_source.cli.graph import graph
from projected_source.core.graph import extract_graph


def test_extract_nodes_and_edges():
    doc = (
        '<!-- chunk id="a" -->\n'
        '<!-- audit file="f" lines="1" id="b" reason="x" -->\n'
        '<!-- edge from="a" type="calls" to="b" -->\n'
        '<!-- /chunk id="a" -->\n'
    )
    g = extract_graph(doc)
    assert g.nodes == {"a", "b"}
    assert len(g.edges) == 1
    e = g.edges[0]
    assert (e.source, e.kind, e.target) == ("a", "calls", "b")


def test_end_anchor_is_not_a_second_node():
    g = extract_graph('<!-- chunk id="a" -->body<!-- /chunk id="a" -->')
    assert g.nodes == {"a"}


def test_orphans():
    doc = (
        '<!-- chunk id="a" --><!-- chunk id="b" --><!-- chunk id="c" -->'
        '<!-- edge from="a" to="b" -->'
    )
    assert extract_graph(doc).orphans() == ["c"]


def test_dangling_edge():
    doc = '<!-- chunk id="a" --><!-- edge from="a" to="ghost" -->'
    dangling = extract_graph(doc).dangling_edges()
    assert [e.target for e in dangling] == ["ghost"]


def test_document_order_is_first_appearance_across_both_anchor_kinds():
    doc = (
        '<!-- chunk id="c" -->'
        '<!-- audit file="f" lines="1" id="a" reason="x" -->'
        '<!-- chunk id="b" -->'
        '<!-- chunk id="c" -->'  # re-mention keeps c at its first position
    )
    assert extract_graph(doc).document_order == ["c", "a", "b"]


def test_document_order_survives_tag_slice():
    doc = (
        '<!-- chunk id="a" tags="t" --><!-- chunk id="x" --><!-- chunk id="b" tags="t" -->'
    )
    g = extract_graph(doc)
    assert g.subgraph(g.nodes_with_tag("t")).document_order == ["a", "b"]


def test_document_order_uses_earliest_offset_across_anchor_kinds():
    """Regression: an id whose first appearance is an audit anchor but which is
    also a later chunk anchor must keep the audit (earlier) position."""
    doc = (
        '<!-- audit file="f" lines="1" id="x" reason="r" -->'
        '<!-- chunk id="y" -->'
        '<!-- chunk id="x" -->'
    )
    assert extract_graph(doc).document_order == ["x", "y"]


# ------------------------------------------------------------------ links

def test_dangling_link_detected():
    doc = (
        '<!-- chunk id="a" -->'
        'see [b](#chunk-b)<!-- link to="chunk-b" --> and '
        '[ghost](#chunk-ghost)<!-- link to="chunk-ghost" -->'
    )
    assert extract_graph(doc).dangling_links() == ["chunk-b", "chunk-ghost"]


def test_link_to_existing_chunk_is_not_dangling():
    doc = '<!-- chunk id="app-owner" -->x [see it](#chunk-app-owner)<!-- link to="chunk-app-owner" -->'
    assert extract_graph(doc).dangling_links() == []


def test_shown_link_href_without_marker_is_not_a_dangling_link():
    """A `](#chunk-ghost)` merely shown in extracted source or a code block must
    NOT be treated as an authored link() target (regression)."""
    doc = (
        '<!-- chunk id="a" -->\n'
        '```markdown\nsee [the owner](#chunk-ghost) for details.\n```\n'
    )
    assert extract_graph(doc).dangling_links() == []


def test_graph_slug_matches_renderer_anchor_slug():
    """The dangling-link lint compares link() targets to renderer anchors; the
    two slug functions must not drift. The graph receives the id AFTER
    comment-escaping (as _ATTR_RE parses it back), so the real invariant is
    _slug(comment_safe(raw)) == _anchor_slug(raw) — including degenerate ids."""
    from projected_source.core.graph import _slug
    from projected_source.core.renderer import _anchor_slug, _comment_safe
    for raw in ["app-owner", "a b c", "weird/id!", "x", "Mixed_Case-1", 'a"b', "x-->y"]:
        assert _slug(_comment_safe(raw)) == _anchor_slug(raw), raw


def test_graph_command_flags_dangling_link(tmp_path):
    tour = _write_tour(
        tmp_path,
        '{% chunk id="a" %}see {{ link("ghost") }}{{ relate("a","x","a") }}{% endchunk %}\n',
    )
    result = CliRunner().invoke(graph, ["-r", str(tmp_path), "--strict", str(tour)])
    assert result.exit_code == 1
    assert "dangling links" in result.output and "chunk-ghost" in result.output


# ------------------------------------------------------------------ cold-review fixes

def test_graph_command_escapes_markup_in_tag_and_does_not_crash(tmp_path):
    """Author data (ids/tags) with Rich-markup metacharacters must be escaped —
    not crash the command, not silently vanish."""
    tour = _write_tour(
        tmp_path,
        '{% chunk id="a" tags=["[wip]"] %}{{ relate("a","x","b") }}{% endchunk %}\n'
        '{% chunk id="b" %}b{% endchunk %}\n',
    )
    result = CliRunner().invoke(graph, ["-r", str(tmp_path), str(tour)])
    assert result.exit_code == 0, result.output
    assert result.exception is None
    assert "[wip]" in result.output  # preserved, not swallowed


def test_no_green_allclear_when_density_below_min(tmp_path):
    """Regression: the green all-clear must not print when min_edge_density fails."""
    tour = _write_tour(
        tmp_path,
        '{% chunk id="a" %}{{ relate("a","x","b") }}{% endchunk %}\n'
        '{% chunk id="b" %}b{% endchunk %}\n',
        config="[graph]\nmin_edge_density = 5.0\n",
    )
    result = CliRunner().invoke(graph, ["-r", str(tmp_path), "--strict", str(tour)])
    assert result.exit_code == 1
    assert "edge density" in result.output
    assert "connected, acyclic" not in result.output


def test_graph_command_prints_document_order(tmp_path):
    tour = _write_tour(
        tmp_path,
        '{% chunk id="c" %}{{ relate("a", "feeds", "b") }}{% endchunk %}\n'
        '{% chunk id="a" %}a{% endchunk %}\n'
        '{% chunk id="b" %}b{% endchunk %}\n',
    )
    result = CliRunner().invoke(graph, ["-r", str(tmp_path), "--doc", str(tour)])
    assert result.exit_code == 0, result.output
    assert "document order: c -> a -> b" in result.output


def test_topological_order_dag():
    doc = (
        '<!-- chunk id="a" --><!-- chunk id="b" --><!-- chunk id="c" -->'
        '<!-- edge from="a" to="b" --><!-- edge from="b" to="c" -->'
    )
    g = extract_graph(doc)
    order, cyclic = g.topological_order()
    assert order == ["a", "b", "c"] and cyclic == []
    assert g.find_cycle() is None


def test_cycle_detected():
    doc = (
        '<!-- chunk id="a" --><!-- chunk id="b" -->'
        '<!-- edge from="a" to="b" --><!-- edge from="b" to="a" -->'
    )
    g = extract_graph(doc)
    _, cyclic = g.topological_order()
    assert set(cyclic) == {"a", "b"}
    assert g.find_cycle() is not None


def test_density():
    doc = '<!-- chunk id="a" --><!-- chunk id="b" --><!-- edge from="a" to="b" -->'
    assert extract_graph(doc).density() == 0.5


# ------------------------------------------------------------------ tags

def test_tags_parsed_from_chunk_and_audit_anchors():
    doc = (
        '<!-- chunk id="a" tags="overview,transport" -->\n'
        '<!-- audit file="f" lines="1" id="b" reason="x" tags="transport" -->\n'
        '<!-- chunk id="c" -->\n'
    )
    g = extract_graph(doc)
    assert g.node_tags["a"] == {"overview", "transport"}
    assert g.node_tags["b"] == {"transport"}
    assert g.node_tags["c"] == set()  # untagged node has an empty set, not KeyError


def test_tags_census_counts_nodes_per_tag():
    doc = (
        '<!-- chunk id="a" tags="x,y" -->'
        '<!-- chunk id="b" tags="x" -->'
        '<!-- chunk id="c" -->'
    )
    assert extract_graph(doc).tags_census() == {"x": 2, "y": 1}


def test_subgraph_by_tag_keeps_only_internal_edges():
    doc = (
        '<!-- chunk id="a" tags="t" --><!-- chunk id="b" tags="t" --><!-- chunk id="c" -->'
        '<!-- edge from="a" to="b" --><!-- edge from="b" to="c" -->'
    )
    g = extract_graph(doc)
    sub = g.subgraph(g.nodes_with_tag("t"))
    assert sub.nodes == {"a", "b"}
    # the a→b edge survives; b→c is dropped because c is outside the slice
    assert [(e.source, e.target) for e in sub.edges] == [("a", "b")]


def test_graph_command_reports_tag_census_and_slices(tmp_path):
    tour = _write_tour(
        tmp_path,
        '{% chunk id="a" tags=["overview"] %}{{ relate("a", "feeds", "b") }}{% endchunk %}\n'
        '{% chunk id="b" tags=["transport"] %}{{ relate("b", "feeds", "c") }}{% endchunk %}\n'
        '{% chunk id="c" tags=["transport"] %}c{% endchunk %}\n',
    )
    full = CliRunner().invoke(graph, ["-r", str(tmp_path), str(tour)])
    assert full.exit_code == 0, full.output
    assert "transport×2" in full.output and "overview×1" in full.output

    sliced = CliRunner().invoke(graph, ["-r", str(tmp_path), "--tag", "transport", "--topo", str(tour)])
    assert sliced.exit_code == 0, sliced.output
    assert "tag(s) transport: 2 node(s)" in sliced.output
    assert "topological order: b -> c" in sliced.output


# ------------------------------------------------------------------ CLI

def _write_tour(tmp_path, body, config=None):
    (tmp_path / "docs").mkdir(exist_ok=True)
    (tmp_path / "docs" / "tour.md.j2").write_text(body)
    if config is not None:
        (tmp_path / ".projected-source.toml").write_text(config)
    return tmp_path / "docs" / "tour.md.j2"


@pytest.fixture(autouse=True)
def _isolate_config(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))  # no developer user config


def test_graph_command_clean_dag(tmp_path):
    tour = _write_tour(
        tmp_path,
        '{% chunk id="a" %}{{ relate("a", "feeds", "b") }}{% endchunk %}\n'
        '{% chunk id="b" %}b{% endchunk %}\n',
    )
    result = CliRunner().invoke(graph, ["-r", str(tmp_path), "--topo", "--strict", str(tour)])
    assert result.exit_code == 0, result.output
    assert "2 node(s), 1 edge(s)" in result.output
    assert "topological order: a -> b" in result.output


def test_min_edges_per_node_dial(tmp_path):
    """min_edges_per_node is a numeric dial: 1 = no orphans, 2 = richer links."""
    body = (
        '{% chunk id="a" %}{{ relate("a", "feeds", "b") }}{% endchunk %}\n'
        '{% chunk id="b" %}b{% endchunk %}\n'
        '{% chunk id="loner" %}alone{% endchunk %}\n'
    )
    # min=1 fails on the orphan
    tour = _write_tour(tmp_path, body, config="[graph]\nmin_edges_per_node = 1\n")
    r1 = CliRunner().invoke(graph, ["-r", str(tmp_path), "--strict", str(tour)])
    assert r1.exit_code == 1
    assert "under-connected" in r1.output and "loner" in r1.output

    # min=2 also fails a/b (they have only one edge each)
    tour2 = _write_tour(tmp_path, body, config="[graph]\nmin_edges_per_node = 2\n")
    r2 = CliRunner().invoke(graph, ["-r", str(tmp_path), "--strict", str(tour2)])
    assert r2.exit_code == 1
    assert "need >= 2 edge(s)" in r2.output


def test_orphan_is_informational_without_the_dial(tmp_path):
    """No min_edges configured → an orphan is surfaced but not fatal."""
    tour = _write_tour(
        tmp_path,
        '{% chunk id="a" %}{{ relate("a", "feeds", "b") }}{% endchunk %}\n'
        '{% chunk id="b" %}b{% endchunk %}\n'
        '{% chunk id="loner" %}alone{% endchunk %}\n',
    )
    result = CliRunner().invoke(graph, ["-r", str(tmp_path), "--strict", str(tour)])
    assert result.exit_code == 0, result.output
    assert "orphans (1): loner" in result.output


def test_cycle_is_reported_but_not_fatal_by_default(tmp_path):
    body = (
        '{% chunk id="a" %}{{ relate("a", "x", "b") }}{% endchunk %}\n'
        '{% chunk id="b" %}{{ relate("b", "x", "a") }}{% endchunk %}\n'
    )
    # default: cycle reported, --strict still passes
    tour = _write_tour(tmp_path, body)
    r1 = CliRunner().invoke(graph, ["-r", str(tmp_path), "--strict", str(tour)])
    assert r1.exit_code == 0, r1.output
    assert "cycle:" in r1.output

    # opt in: forbid_cycles makes it fatal
    tour2 = _write_tour(tmp_path, body, config="[graph]\nforbid_cycles = true\n")
    r2 = CliRunner().invoke(graph, ["-r", str(tmp_path), "--strict", str(tour2)])
    assert r2.exit_code == 1


def test_dangling_edge_is_always_fatal(tmp_path):
    tour = _write_tour(
        tmp_path,
        '{% chunk id="a" %}{{ relate("a", "x", "ghost") }}{% endchunk %}\n',
    )
    result = CliRunner().invoke(graph, ["-r", str(tmp_path), "--strict", str(tour)])
    assert result.exit_code == 1
    assert "ghost (undeclared node)" in result.output
