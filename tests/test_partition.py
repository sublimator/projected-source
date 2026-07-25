"""Tests for the disjoint change partition (code > audit > ignore).

claim() subtracts immediately (keeping the residual live), while partition()
attributes every changed line to exactly one bucket by replaying the recorded
claims against a frozen snapshot of D in priority order. The partition is
therefore disjoint (no double-counting) and independent of the order claims
were made — the property immediate first-claim-wins subtraction cannot give.
"""

from pathlib import Path

from projected_source.core.changes_set import ChangesSet


def _cs_with_d(path: Path, *spans):
    """A ChangesSet whose D is `spans`, frozen and ready for claims."""
    cs = ChangesSet()
    for s, e in spans:
        cs.add(path, s, e)
    cs._freeze_d()
    return cs


def test_overlap_credited_to_higher_priority_bucket():
    p = Path("f.cpp")
    cs = _cs_with_d(p, (1, 10))                 # 10 changed lines
    cs.claim("code", p, [(1, 6)])
    cs.claim("audit", p, [(4, 10)])             # overlaps 4-6 with code
    buckets, _ = cs.partition()
    assert buckets == {"code": 6, "audit": 4, "ignore": 0}   # 4-6 credited to code
    assert sum(buckets.values()) == cs.changed_line_count()  # disjoint, exhaustive
    assert cs.is_complete()                     # residual empty (both claimed)


def test_partition_is_order_independent():
    p = Path("f.cpp")
    forward = _cs_with_d(p, (1, 10))
    forward.claim("code", p, [(1, 6)])
    forward.claim("audit", p, [(4, 10)])

    reverse = _cs_with_d(p, (1, 10))
    reverse.claim("audit", p, [(4, 10)])        # audit recorded first this time
    reverse.claim("code", p, [(1, 6)])
    assert forward.partition()[0] == reverse.partition()[0] == {"code": 6, "audit": 4, "ignore": 0}


def test_three_buckets_disjoint():
    p = Path("f.cpp")
    cs = _cs_with_d(p, (1, 30))
    cs.claim("ignore", p, [(1, 30)])            # lowest priority, claims all
    cs.claim("audit", p, [(11, 20)])
    cs.claim("code", p, [(1, 10)])
    buckets, _ = cs.partition()
    assert buckets == {"code": 10, "audit": 10, "ignore": 10}
    assert sum(buckets.values()) == 30


def test_whole_file_ignore_counts_only_changed_lines():
    p = Path("gen.txt")
    cs = _cs_with_d(p, (5, 5), (10, 10))        # 2 changed lines, far apart
    cs.claim("ignore", p, [(1, 999999)])        # whole-file magic span
    buckets, records = cs.partition()
    assert buckets["ignore"] == 2               # not 999999 (M4)
    assert records[0].credited_lines == 2


def test_zero_claim_is_visible_in_records():
    p = Path("f.cpp")
    cs = _cs_with_d(p, (1, 3))
    cs.claim("audit", p, [(50, 60)])            # points at no changed line (typo / stale)
    cs.claim("code", p, [(1, 3)])
    buckets, records = cs.partition()
    assert buckets == {"code": 3, "audit": 0, "ignore": 0}
    zero = [r for r in records if r.changed_lines == 0]
    assert len(zero) == 1 and zero[0].bucket == "audit"   # M3 signal available


def test_partition_freezes_d_lazily_on_first_claim():
    """A directly-built ChangesSet (no from_diff, no manual _freeze_d) still
    reports |D| and the partition correctly — freeze happens on first claim (F13)."""
    p = Path("f.cpp")
    cs = ChangesSet()
    cs.add(p, 1, 10)
    cs.claim("code", p, [(1, 5)])
    assert cs.changed_line_count() == 10
    buckets, _ = cs.partition()
    assert buckets["code"] == 5
    assert not cs.is_complete()          # 6-10 residual


def test_geometry_multi_region_claim():
    """A single claim carrying two regions (symbol minus marker) is credited
    for both pieces — the region-set claim API geometry will use."""
    p = Path("f.cpp")
    cs = _cs_with_d(p, (1, 20))
    cs.claim("audit", p, [(1, 5), (16, 20)])    # function minus a narrated 6-15 marker
    buckets, records = cs.partition()
    assert buckets["audit"] == 10               # 5 + 5
    assert records[0].regions == [(1, 5), (16, 20)]
    assert not cs.is_complete()                 # 6-15 still uncovered (would be narrated)
