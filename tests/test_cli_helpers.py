"""
Regression tests for projected_source.cli.helpers.FixtureCollector.

Covers FINDING 2: repeat errors on the same source file should reuse the
deduped fixture name instead of pointing at the original (now-overwritten
or unrelated) filename.

Also covers FINDING 1 (partial): write_manifest() must produce manifest.json
even when there are zero errors so callers that always finalize can trust it.
"""

import json

from projected_source.cli.helpers import FixtureCollector


def test_repeat_errors_use_deduped_fixture_name(tmp_path):
    """Second error on the same source file should reference the deduped fixture."""
    fixtures_dir = tmp_path / "collected"

    # Pre-existing collision: a foo.cpp already in the output dir from a
    # previous run (or another source path with the same basename).
    fixtures_dir.mkdir(parents=True)
    (fixtures_dir / "foo.cpp").write_text("// previously collected\n")

    src = tmp_path / "src" / "foo.cpp"
    src.parent.mkdir()
    src.write_text("// my new source\n")

    collector = FixtureCollector(fixtures_dir)
    collector.collect(src, error="boom1", template_context="t1")
    collector.collect(src, error="boom2", template_context="t2")

    assert len(collector.errors) == 2

    # First error must point at the deduped name (foo_1.cpp).
    assert collector.errors[0]["fixture_file"] == "foo_1.cpp"
    # Second error MUST also point at the deduped name, not the colliding
    # foo.cpp left from another source.
    assert collector.errors[1]["fixture_file"] == "foo_1.cpp"

    # And the deduped file must actually exist with the new source contents.
    assert (fixtures_dir / "foo_1.cpp").read_text() == "// my new source\n"
    # Original colliding file must be untouched.
    assert (fixtures_dir / "foo.cpp").read_text() == "// previously collected\n"


def test_write_manifest_emits_file_when_no_errors(tmp_path):
    """write_manifest() must produce a manifest even with zero errors."""
    fixtures_dir = tmp_path / "collected"
    collector = FixtureCollector(fixtures_dir)

    manifest_path = collector.write_manifest()

    assert manifest_path is not None
    assert manifest_path.exists()

    data = json.loads(manifest_path.read_text())
    assert data["error_count"] == 0
    assert data["errors"] == []


def test_distinct_source_files_with_same_basename_get_unique_fixtures(tmp_path):
    """Independent sources with the same basename should both be copied uniquely."""
    fixtures_dir = tmp_path / "collected"

    src_a = tmp_path / "a" / "foo.cpp"
    src_b = tmp_path / "b" / "foo.cpp"
    src_a.parent.mkdir(parents=True)
    src_b.parent.mkdir(parents=True)
    src_a.write_text("// A\n")
    src_b.write_text("// B\n")

    collector = FixtureCollector(fixtures_dir)
    collector.collect(src_a, error="errA")
    collector.collect(src_b, error="errB")

    a_fixture = collector.errors[0]["fixture_file"]
    b_fixture = collector.errors[1]["fixture_file"]

    assert a_fixture != b_fixture
    assert (fixtures_dir / a_fixture).read_text() == "// A\n"
    assert (fixtures_dir / b_fixture).read_text() == "// B\n"
