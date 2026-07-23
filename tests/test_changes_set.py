"""Tests for ChangesSet - code change tracking and coverage validation."""

from pathlib import Path

import pytest

from projected_source.core.changes_set import ChangeRegion, ChangesSet


class TestChangesSetAdd:
    """Test add() with region merging logic."""

    def test_add_single_region(self):
        """Adding a single region works."""
        cs = ChangesSet()
        cs.add(Path("test.cpp"), 10, 20)

        regions = cs.uncovered()
        assert len(regions) == 1
        assert regions[0].start_line == 10
        assert regions[0].end_line == 20

    def test_add_non_overlapping_regions(self):
        """Non-overlapping regions stay separate."""
        cs = ChangesSet()
        cs.add(Path("test.cpp"), 10, 20)
        cs.add(Path("test.cpp"), 30, 40)

        regions = cs.uncovered()
        assert len(regions) == 2
        assert regions[0].start_line == 10
        assert regions[0].end_line == 20
        assert regions[1].start_line == 30
        assert regions[1].end_line == 40

    def test_add_overlapping_regions_merge(self):
        """Overlapping regions are merged."""
        cs = ChangesSet()
        cs.add(Path("test.cpp"), 10, 20)
        cs.add(Path("test.cpp"), 15, 25)

        regions = cs.uncovered()
        assert len(regions) == 1
        assert regions[0].start_line == 10
        assert regions[0].end_line == 25

    def test_add_adjacent_regions_merge(self):
        """Adjacent regions (end+1 == start) are merged."""
        cs = ChangesSet()
        cs.add(Path("test.cpp"), 10, 20)
        cs.add(Path("test.cpp"), 21, 30)

        regions = cs.uncovered()
        assert len(regions) == 1
        assert regions[0].start_line == 10
        assert regions[0].end_line == 30

    def test_add_contained_region_no_change(self):
        """Adding a region inside an existing one doesn't change anything."""
        cs = ChangesSet()
        cs.add(Path("test.cpp"), 10, 30)
        cs.add(Path("test.cpp"), 15, 25)

        regions = cs.uncovered()
        assert len(regions) == 1
        assert regions[0].start_line == 10
        assert regions[0].end_line == 30

    def test_add_containing_region_expands(self):
        """Adding a region that contains existing ones merges them all."""
        cs = ChangesSet()
        cs.add(Path("test.cpp"), 15, 20)
        cs.add(Path("test.cpp"), 25, 30)
        cs.add(Path("test.cpp"), 10, 35)

        regions = cs.uncovered()
        assert len(regions) == 1
        assert regions[0].start_line == 10
        assert regions[0].end_line == 35

    def test_add_reversed_range_normalized(self):
        """Adding (end, start) normalizes to (start, end)."""
        cs = ChangesSet()
        cs.add(Path("test.cpp"), 20, 10)

        regions = cs.uncovered()
        assert len(regions) == 1
        assert regions[0].start_line == 10
        assert regions[0].end_line == 20

    def test_add_multiple_files_separate(self):
        """Regions in different files stay separate."""
        cs = ChangesSet()
        cs.add(Path("a.cpp"), 10, 20)
        cs.add(Path("b.cpp"), 10, 20)

        regions = cs.uncovered()
        assert len(regions) == 2
        assert regions[0].file_path == Path("a.cpp")
        assert regions[1].file_path == Path("b.cpp")


class TestChangesSetSubtract:
    """Test subtract() for claiming regions."""

    def test_subtract_exact_match_removes(self):
        """Subtracting exact region removes it completely."""
        cs = ChangesSet()
        cs.add(Path("test.cpp"), 10, 20)
        cs.subtract(Path("test.cpp"), 10, 20)

        assert cs.is_complete()
        assert len(cs.uncovered()) == 0

    def test_subtract_larger_removes(self):
        """Subtracting larger region removes contained region."""
        cs = ChangesSet()
        cs.add(Path("test.cpp"), 10, 20)
        cs.subtract(Path("test.cpp"), 5, 25)

        assert cs.is_complete()

    def test_subtract_left_portion_shrinks(self):
        """Subtracting left portion shrinks region."""
        cs = ChangesSet()
        cs.add(Path("test.cpp"), 10, 20)
        cs.subtract(Path("test.cpp"), 10, 15)

        regions = cs.uncovered()
        assert len(regions) == 1
        assert regions[0].start_line == 16
        assert regions[0].end_line == 20

    def test_subtract_right_portion_shrinks(self):
        """Subtracting right portion shrinks region."""
        cs = ChangesSet()
        cs.add(Path("test.cpp"), 10, 20)
        cs.subtract(Path("test.cpp"), 15, 20)

        regions = cs.uncovered()
        assert len(regions) == 1
        assert regions[0].start_line == 10
        assert regions[0].end_line == 14

    def test_subtract_middle_splits(self):
        """Subtracting middle portion splits into two regions."""
        cs = ChangesSet()
        cs.add(Path("test.cpp"), 10, 30)
        cs.subtract(Path("test.cpp"), 15, 25)

        regions = cs.uncovered()
        assert len(regions) == 2
        assert regions[0].start_line == 10
        assert regions[0].end_line == 14
        assert regions[1].start_line == 26
        assert regions[1].end_line == 30

    def test_subtract_no_overlap_no_change(self):
        """Subtracting non-overlapping region does nothing."""
        cs = ChangesSet()
        cs.add(Path("test.cpp"), 10, 20)
        cs.subtract(Path("test.cpp"), 30, 40)

        regions = cs.uncovered()
        assert len(regions) == 1
        assert regions[0].start_line == 10
        assert regions[0].end_line == 20

    def test_subtract_nonexistent_file_no_error(self):
        """Subtracting from nonexistent file doesn't error."""
        cs = ChangesSet()
        cs.add(Path("a.cpp"), 10, 20)
        cs.subtract(Path("b.cpp"), 10, 20)

        # a.cpp should still have its region
        regions = cs.uncovered()
        assert len(regions) == 1

    def test_subtract_multiple_regions(self):
        """Subtraction affects multiple overlapping regions."""
        cs = ChangesSet()
        cs.add(Path("test.cpp"), 10, 15)
        cs.add(Path("test.cpp"), 20, 25)
        cs.add(Path("test.cpp"), 30, 35)
        cs.subtract(Path("test.cpp"), 12, 32)

        regions = cs.uncovered()
        assert len(regions) == 2
        assert regions[0].start_line == 10
        assert regions[0].end_line == 11
        assert regions[1].start_line == 33
        assert regions[1].end_line == 35


class TestChangesSetQueries:
    """Test query methods."""

    def test_is_complete_empty(self):
        """Empty set is complete."""
        cs = ChangesSet()
        assert cs.is_complete()

    def test_is_complete_with_regions(self):
        """Set with regions is not complete."""
        cs = ChangesSet()
        cs.add(Path("test.cpp"), 10, 20)
        assert not cs.is_complete()

    def test_files_returns_affected_files(self):
        """files() returns list of files with changes."""
        cs = ChangesSet()
        cs.add(Path("a.cpp"), 10, 20)
        cs.add(Path("b.cpp"), 10, 20)

        files = cs.files()
        assert len(files) == 2
        assert Path("a.cpp") in files
        assert Path("b.cpp") in files

    def test_len_counts_regions(self):
        """len() returns total region count across all files."""
        cs = ChangesSet()
        cs.add(Path("a.cpp"), 10, 20)
        cs.add(Path("a.cpp"), 30, 40)
        cs.add(Path("b.cpp"), 10, 20)

        assert len(cs) == 3

    def test_bool_true_with_regions(self):
        """bool() is True when there are uncovered regions."""
        cs = ChangesSet()
        cs.add(Path("test.cpp"), 10, 20)
        assert bool(cs) is True

    def test_bool_false_when_empty(self):
        """bool() is False when no uncovered regions."""
        cs = ChangesSet()
        assert bool(cs) is False


class TestChangeRegion:
    """Test ChangeRegion dataclass."""

    def test_str_format(self):
        """String representation is file:start-end."""
        region = ChangeRegion(Path("src/main.cpp"), 10, 20)
        assert str(region) == "src/main.cpp:10-20"


class TestChangesSetFromDiff:
    """Integration tests for from_diff() with real git repos."""

    import shutil
    import subprocess
    import tempfile

    @pytest.fixture
    def temp_git_repo(self):
        """Create a temporary git repo with an initial commit."""
        temp_dir = self.tempfile.mkdtemp()
        repo_path = Path(temp_dir) / "repo"
        repo_path.mkdir()

        # Initialize git repo
        self.subprocess.run(["git", "init"], cwd=repo_path, capture_output=True)
        self.subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=repo_path,
            capture_output=True,
        )
        self.subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=repo_path,
            capture_output=True,
        )

        # Create initial file
        test_file = repo_path / "test.cpp"
        test_file.write_text(
            """int main() {
    return 0;
}
"""
        )

        # Initial commit
        self.subprocess.run(["git", "add", "."], cwd=repo_path, capture_output=True)
        self.subprocess.run(
            ["git", "commit", "-m", "Initial"],
            cwd=repo_path,
            capture_output=True,
        )

        yield repo_path

        # Cleanup
        self.shutil.rmtree(temp_dir)

    def test_from_diff_detects_additions(self, temp_git_repo):
        """from_diff() detects added lines."""
        test_file = temp_git_repo / "test.cpp"

        # Add lines
        test_file.write_text(
            """int main() {
    int x = 42;
    return x;
}
"""
        )

        # Commit
        self.subprocess.run(["git", "add", "."], cwd=temp_git_repo, capture_output=True)
        self.subprocess.run(
            ["git", "commit", "-m", "Add variable"],
            cwd=temp_git_repo,
            capture_output=True,
        )

        # Get changes against initial commit
        cs = ChangesSet.from_diff(base="HEAD~1", repo_path=temp_git_repo)

        assert not cs.is_complete()
        regions = cs.uncovered()
        assert len(regions) >= 1

        # Should have changes in test.cpp
        files = cs.files()
        assert any("test.cpp" in str(f) for f in files)

    def test_from_diff_context_lines_not_required(self, temp_git_repo):
        """Unchanged hunk context is diagnostic, never a coverage obligation."""
        test_file = temp_git_repo / "test.cpp"

        # Replace only the middle line; the surrounding lines become
        # unified-diff context and must NOT be recorded as required.
        test_file.write_text(
            """int main() {
    return 42;
}
"""
        )
        self.subprocess.run(["git", "add", "."], cwd=temp_git_repo, capture_output=True)
        self.subprocess.run(
            ["git", "commit", "-m", "Change return value"],
            cwd=temp_git_repo,
            capture_output=True,
        )

        cs = ChangesSet.from_diff(base="HEAD~1", repo_path=temp_git_repo)

        regions = cs.uncovered()
        assert len(regions) == 1
        assert regions[0].start_line == 2
        assert regions[0].end_line == 2

    def test_from_diff_deletion_only_hunk_no_obligation(self, temp_git_repo):
        """A deletion-only hunk has no new-version line to require.

        Deletions are not yet modeled; unchanged neighbors must not proxy
        for them.
        """
        test_file = temp_git_repo / "test.cpp"
        test_file.write_text(
            """int main() {
    int x = 1;
    return 0;
}
"""
        )
        self.subprocess.run(["git", "add", "."], cwd=temp_git_repo, capture_output=True)
        self.subprocess.run(
            ["git", "commit", "-m", "Add x"], cwd=temp_git_repo, capture_output=True
        )

        test_file.write_text(
            """int main() {
    return 0;
}
"""
        )
        self.subprocess.run(["git", "add", "."], cwd=temp_git_repo, capture_output=True)
        self.subprocess.run(
            ["git", "commit", "-m", "Remove x"], cwd=temp_git_repo, capture_output=True
        )

        cs = ChangesSet.from_diff(base="HEAD~1", repo_path=temp_git_repo)
        assert cs.is_complete()
        assert cs.uncovered() == []

    def test_from_diff_records_target_sha(self, temp_git_repo):
        """from_diff() resolves and stores the destination commit of the range."""
        test_file = temp_git_repo / "test.cpp"
        test_file.write_text("int main() { return 1; }\n")
        self.subprocess.run(["git", "add", "."], cwd=temp_git_repo, capture_output=True)
        self.subprocess.run(
            ["git", "commit", "-m", "Change"], cwd=temp_git_repo, capture_output=True
        )

        head_sha = (
            self.subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=temp_git_repo,
                capture_output=True,
                text=True,
            )
            .stdout.strip()
        )
        prev_sha = (
            self.subprocess.run(
                ["git", "rev-parse", "HEAD~1"],
                cwd=temp_git_repo,
                capture_output=True,
                text=True,
            )
            .stdout.strip()
        )

        cs = ChangesSet.from_diff(base="HEAD~1", repo_path=temp_git_repo)
        assert cs.target_sha == head_sha

        cs_range = ChangesSet.from_diff(
            base=f"{prev_sha}..{head_sha}", repo_path=temp_git_repo
        )
        assert cs_range.target_sha == head_sha

    def test_from_diff_on_feature_branch(self, temp_git_repo):
        """from_diff() works on a feature branch against main."""
        # Create a feature branch
        self.subprocess.run(
            ["git", "checkout", "-b", "feature"],
            cwd=temp_git_repo,
            capture_output=True,
        )

        test_file = temp_git_repo / "test.cpp"

        # Add lines
        test_file.write_text(
            """int main() {
    int y = 100;
    return y;
}
"""
        )

        # Commit on feature branch
        self.subprocess.run(["git", "add", "."], cwd=temp_git_repo, capture_output=True)
        self.subprocess.run(
            ["git", "commit", "-m", "Change return"],
            cwd=temp_git_repo,
            capture_output=True,
        )

        # Should auto-detect base as merge-base with main
        cs = ChangesSet.from_diff(repo_path=temp_git_repo)

        assert not cs.is_complete()
        files = cs.files()
        assert any("test.cpp" in str(f) for f in files)

    def test_detect_base_finds_main(self, temp_git_repo):
        """detect_base() finds merge-base with main branch."""
        # Create a feature branch with a commit
        self.subprocess.run(
            ["git", "checkout", "-b", "feature"],
            cwd=temp_git_repo,
            capture_output=True,
        )

        test_file = temp_git_repo / "test.cpp"
        test_file.write_text("// modified\n")
        self.subprocess.run(["git", "add", "."], cwd=temp_git_repo, capture_output=True)
        self.subprocess.run(
            ["git", "commit", "-m", "Feature change"],
            cwd=temp_git_repo,
            capture_output=True,
        )

        base = ChangesSet.detect_base(temp_git_repo)
        # Should be a commit SHA (the initial commit on main)
        assert len(base) == 40  # Git SHA length
        assert base != "HEAD~1"

    def test_subtract_claims_region(self, temp_git_repo):
        """Subtracting extracted region marks it as documented."""
        test_file = temp_git_repo / "test.cpp"

        # Add a function
        test_file.write_text(
            """int main() {
    return 0;
}

int helper() {
    return 42;
}
"""
        )

        # Commit
        self.subprocess.run(["git", "add", "."], cwd=temp_git_repo, capture_output=True)
        self.subprocess.run(
            ["git", "commit", "-m", "Add helper"],
            cwd=temp_git_repo,
            capture_output=True,
        )

        cs = ChangesSet.from_diff(base="HEAD~1", repo_path=temp_git_repo)

        # Claim the helper function (lines 5-7)
        cs.subtract(test_file, 5, 8)

        # Should have fewer or no uncovered regions
        remaining = cs.uncovered()
        # The helper function region should be claimed
        for region in remaining:
            if "test.cpp" in str(region.file_path):
                # Any remaining regions shouldn't be in 5-8
                assert not (region.start_line >= 5 and region.end_line <= 8)

    def test_parse_diff_with_deleted_file_skips_dev_null(self, temp_git_repo):
        """A '+++ /dev/null' header (deleted file) must not record adds against the previous file."""
        # Name files so the kept (modified) file sorts BEFORE the deleted file
        # in git's alphabetical diff output. The bug only manifests when the
        # '+++ /dev/null' line appears AFTER current_file was set by a prior
        # '+++ b/...' header — then the '+' prefix of '/dev/null' falls through
        # to the addition branch and phantom-records against the prior file.
        kept_file = temp_git_repo / "a_kept.cpp"
        kept_file.write_text(
            "int kept() {\n"
            "    return 1;\n"
            "}\n"
        )
        gone_file = temp_git_repo / "z_gone.cpp"
        gone_file.write_text(
            "int gone() {\n"
            "    return 2;\n"
            "}\n"
        )
        self.subprocess.run(["git", "add", "."], cwd=temp_git_repo, capture_output=True)
        self.subprocess.run(
            ["git", "commit", "-m", "add two files"],
            cwd=temp_git_repo,
            capture_output=True,
        )

        # Now modify kept.cpp AND delete gone.cpp in a single commit. git diff
        # will emit gone.cpp with '+++ /dev/null'. The buggy parser would
        # treat the '+' lines of the deletion hunk as additions to kept.cpp.
        kept_file.write_text(
            "int kept() {\n"
            "    return 99;\n"
            "}\n"
        )
        gone_file.unlink()
        self.subprocess.run(["git", "add", "-A"], cwd=temp_git_repo, capture_output=True)
        self.subprocess.run(
            ["git", "commit", "-m", "modify kept, delete gone"],
            cwd=temp_git_repo,
            capture_output=True,
        )

        cs = ChangesSet.from_diff(base="HEAD~1", repo_path=temp_git_repo)
        regions = cs.uncovered()

        # All recorded regions must belong to a_kept.cpp - no phantom rows from
        # the deleted-file hunk getting attributed to it.
        for region in regions:
            assert "z_gone.cpp" not in str(region.file_path), f"deleted file regions leaked: {region}"
            # a_kept.cpp only has 3 lines, so no region should reference lines > 3
            if "a_kept.cpp" in str(region.file_path):
                assert region.end_line <= 3, (
                    f"phantom add recorded for a_kept.cpp beyond its length: {region}"
                )
