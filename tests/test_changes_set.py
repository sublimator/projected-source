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
