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
