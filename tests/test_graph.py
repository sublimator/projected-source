"""Tests for the chunk graph — extraction + orphan/cycle/topo analysis, and the
`graph` CLI command."""

from pathlib import Path

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


# ------------------------------------------------------------------ CLI

def _write_tour(tmp_path, body):
    tdir = tmp_path / "docs"
    tdir.mkdir(exist_ok=True)
    (tdir / "tour.md.j2").write_text(body)
    return tdir / "tour.md.j2"


def test_graph_command_clean_dag(tmp_path):
    tour = _write_tour(
        tmp_path,
        '{% chunk id="a" %}{{ relate("a", "feeds", "b") }}{% endchunk %}\n'
        '{% chunk id="b" %}b{% endchunk %}\n',
    )
    result = CliRunner().invoke(graph, ["-r", str(tmp_path), "--topo", "--strict", str(tour)])
    assert result.exit_code == 0, result.output
    assert "2 node(s), 1 edge(s)" in result.output
    assert "connected, acyclic" in result.output
    assert "topological order: a -> b" in result.output


def test_graph_command_strict_fails_on_orphan(tmp_path):
    tour = _write_tour(
        tmp_path,
        '{% chunk id="a" %}{{ relate("a", "feeds", "b") }}{% endchunk %}\n'
        '{% chunk id="b" %}b{% endchunk %}\n'
        '{% chunk id="loner" %}alone{% endchunk %}\n',
    )
    result = CliRunner().invoke(graph, ["-r", str(tmp_path), "--strict", str(tour)])
    assert result.exit_code == 1
    assert "orphans (1): loner" in result.output


def test_graph_command_reports_cycle_and_dangling(tmp_path):
    tour = _write_tour(
        tmp_path,
        '{% chunk id="a" %}{{ relate("a", "x", "b") }}{% endchunk %}\n'
        '{% chunk id="b" %}{{ relate("b", "x", "a") }}{{ relate("b", "x", "ghost") }}{% endchunk %}\n',
    )
    result = CliRunner().invoke(graph, ["-r", str(tmp_path), "--strict", str(tour)])
    assert result.exit_code == 1
    assert "cycle:" in result.output
    assert "ghost (undeclared node)" in result.output
