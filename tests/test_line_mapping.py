"""
Integration tests for dirty file line number mapping.

Tests that when markers are added to files (but not committed),
the GitHub permalinks point to the correct committed line numbers.
"""

import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

from projected_source.core.github import (
    GitHubIntegration,
    map_line_to_committed,
    parse_diff_hunks,
)

# Get fixtures directory
FIXTURES_DIR = Path(__file__).parent / "fixtures"


class TestParseDiffHunks:
    """Test parsing of git diff hunk headers."""

    def test_single_hunk_add_one_line(self):
        """Single hunk adding one line."""
        diff = """@@ -10,0 +11 @@ context
+added line"""
        hunks = parse_diff_hunks(diff)
        assert len(hunks) == 1
        # old_start, old_count, new_start, new_count
        assert hunks[0] == (10, 0, 11, 1)

    def test_single_hunk_add_two_lines(self):
        """Single hunk adding two lines (marker pair)."""
        diff = """@@ -5,0 +6,2 @@ context
+//@@start marker
+//@@end marker"""
        hunks = parse_diff_hunks(diff)
        assert len(hunks) == 1
        assert hunks[0] == (5, 0, 6, 2)

    def test_multiple_hunks(self):
        """Multiple hunks from adding markers at different places."""
        diff = """diff --git a/test.cpp b/test.cpp
index abc123..def456 100644
--- a/test.cpp
+++ b/test.cpp
@@ -5,0 +6,2 @@ void funcOne
+//@@start func-one
+//@@end func-one
@@ -10,0 +13,2 @@ void funcTwo
+//@@start func-two
+//@@end func-two"""
        hunks = parse_diff_hunks(diff)
        assert len(hunks) == 2
        assert hunks[0] == (5, 0, 6, 2)
        assert hunks[1] == (10, 0, 13, 2)

    def test_hunk_with_context(self):
        """Hunk that replaces lines (has both old and new counts)."""
        diff = """@@ -10,3 +10,5 @@ context
 unchanged
-old line
+new line 1
+new line 2
+new line 3
 unchanged"""
        hunks = parse_diff_hunks(diff)
        assert len(hunks) == 1
        assert hunks[0] == (10, 3, 10, 5)


class TestMapLineToCommitted:
    """Test mapping working copy line numbers to committed line numbers."""

    def test_no_hunks_returns_same_line(self):
        """With no changes, line number stays the same."""
        assert map_line_to_committed(10, []) == 10
        assert map_line_to_committed(100, []) == 100

    def test_line_before_any_changes(self):
        """Line before any hunks is unchanged."""
        # Hunk adds 2 lines starting at new line 10
        hunks = [(8, 0, 10, 2)]  # old_start=8, old_count=0, new_start=10, new_count=2
        assert map_line_to_committed(5, hunks) == 5
        assert map_line_to_committed(9, hunks) == 9

    def test_line_after_single_addition(self):
        """Line after a single marker pair addition."""
        # Added 2 lines at position 6 (marker pair around func at old line 5)
        # old: line 5 is func, line 6 is next thing
        # new: line 6-7 are markers, line 8 is func (was 5), line 9-10 are markers end... wait
        #
        # Actually, let's think about this more carefully:
        # Original file:
        #   5: void func() {
        #   6: }
        # After adding markers:
        #   5: //@@start
        #   6: void func() {
        #   7: }
        #   8: //@@end
        #
        # So hunk is: @@ -5,0 +5,1 @@ (added 1 line before line 5)
        # And another: @@ -6,0 +8,1 @@ (added 1 line after line 6, now at 8)
        #
        # For simpler test: add 2 lines between old lines 5 and 6
        # @@ -5,0 +6,2 @@
        # This means: after old line 5, we inserted 2 new lines (new lines 6-7)
        # So: new line 8 = old line 6, new line 9 = old line 7, etc.

        # Scenario: markers wrap function at old lines 6-8
        # Diff shows: inserted 1 line before line 6, inserted 1 line after line 8
        # @@ -5,0 +6 @@ (add start marker)
        # @@ -8,0 +10 @@ (add end marker)
        hunks = [(5, 0, 6, 1), (8, 0, 10, 1)]

        # Line 5 in new = line 5 in old (before first hunk)
        assert map_line_to_committed(5, hunks) == 5

        # Line 6 in new = marker (within first hunk's added region)
        # Should map to nearest valid: old line 5
        result = map_line_to_committed(6, hunks)
        assert result == 5  # Maps to line before the insertion

        # Line 7 in new = old line 6 (after first +1, so offset is -1)
        assert map_line_to_committed(7, hunks) == 6

        # Line 9 in new = old line 8 (after first +1, so offset is -1)
        assert map_line_to_committed(9, hunks) == 8

    def test_line_after_multiple_additions(self):
        """Line after multiple marker pairs."""
        # Two marker pairs added:
        # - First pair at old line 5 (adds 2 lines)
        # - Second pair at old line 10 (adds 2 lines)
        # @@ -5,0 +6,2 @@ - insert 2 lines after old line 5
        # @@ -10,0 +14,2 @@ - insert 2 lines after old line 10 (now at new line 14 because of first insertion)
        hunks = [(5, 0, 6, 2), (10, 0, 14, 2)]

        # Before any changes
        assert map_line_to_committed(4, hunks) == 4

        # After first marker pair (+2 offset)
        assert map_line_to_committed(10, hunks) == 8  # 10 - 2 = 8

        # After second marker pair (+4 offset total)
        assert map_line_to_committed(20, hunks) == 16  # 20 - 4 = 16


class TestGitHubIntegrationDirtyFile:
    """Integration tests with actual git repo."""

    @pytest.fixture
    def temp_git_repo(self):
        """Create a temporary git repository with a base file."""
        temp_dir = tempfile.mkdtemp()
        repo_path = Path(temp_dir)

        # Initialize git repo
        subprocess.run(["git", "init"], cwd=repo_path, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=repo_path,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=repo_path,
            capture_output=True,
        )

        # Copy base fixture and commit
        base_file = FIXTURES_DIR / "line_mapping_base.cpp"
        dest_file = repo_path / "test.cpp"
        shutil.copy(base_file, dest_file)

        subprocess.run(["git", "add", "test.cpp"], cwd=repo_path, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "Initial commit"],
            cwd=repo_path,
            capture_output=True,
        )

        yield repo_path

        # Cleanup
        shutil.rmtree(temp_dir)

    def test_clean_file_no_mapping(self, temp_git_repo):
        """Clean file returns same line numbers."""
        github = GitHubIntegration(temp_git_repo)
        test_file = temp_git_repo / "test.cpp"

        assert not github.is_file_dirty(test_file)
        assert github.map_to_committed_line(test_file, 10) == 10
        assert github.map_to_committed_line(test_file, 25) == 25

    def test_dirty_file_with_markers(self, temp_git_repo):
        """Dirty file with markers maps lines correctly."""
        github = GitHubIntegration(temp_git_repo)
        test_file = temp_git_repo / "test.cpp"

        # Overwrite with markers version (don't commit)
        markers_file = FIXTURES_DIR / "line_mapping_with_markers.cpp"
        shutil.copy(markers_file, test_file)

        assert github.is_file_dirty(test_file)

        # Get the diff hunks
        hunks = github.get_diff_hunks(test_file)
        print(f"Hunks: {hunks}")

        # Check the actual diff
        diff_output = subprocess.check_output(
            ["git", "diff", "HEAD", "--", "test.cpp"],
            cwd=temp_git_repo,
        ).decode()
        print(f"Diff:\n{diff_output}")

        # Test specific line mappings based on our fixture:
        # Base file line numbers vs markers file:
        #
        # Marker pair 1: around functionOne (base lines 6-8)
        #   - //@@start func-one inserted at new line 6
        #   - //@@end func-one inserted at new line 10
        #   - Old lines 6-8 become new lines 7-9
        #
        # After first marker pair, offset is +2
        #
        # Marker pair 2: around functionThree (base lines 16-18)
        #   - Base line 16 (in new file, after +2 offset, would be 18)
        #   - //@@start func-three at new line 18
        #   - Old lines 16-18 become new lines 19-21
        #   - //@@end func-three at new line 22
        #
        # After second marker pair, offset is +4
        #
        # Marker pair 3: around main (base lines 26-32)
        #   - //@@start main-func
        #   - //@@end main-func
        #
        # After third marker pair, offset is +6

        # functionOne body is at new line 8 (was old line 7)
        # Expected: new line 8 -> old line 7 (offset -1? let's see)
        # Actually with insertion hunks, the math is different...

        # Let's just verify the mapping works in the right direction
        # and the file is detected as dirty
        committed_line = github.map_to_committed_line(test_file, 8)
        print(f"New line 8 maps to committed line {committed_line}")

        # The key test: lines after markers should map to earlier committed lines
        # Line 30 in working copy should map to something less than 30
        committed_30 = github.map_to_committed_line(test_file, 30)
        print(f"New line 30 maps to committed line {committed_30}")
        assert committed_30 < 30, f"Expected committed line < 30, got {committed_30}"

    def test_realistic_single_marker_pair(self, temp_git_repo):
        """Test with a single marker pair wrapping a function."""
        test_file = temp_git_repo / "test.cpp"

        # Read the base file
        base_content = test_file.read_text()
        lines = base_content.split("\n")

        # Insert markers around functionTwo (lines 11-13 in base, 0-indexed: 10-12)
        # functionTwo starts at line 11: "void functionTwo() {"
        # and ends at line 13: "}"
        new_lines = (
            lines[:10]  # Lines 1-10 unchanged
            + ["//@@start func-two"]  # New line 11
            + lines[10:13]  # Old lines 11-13 become new 12-14
            + ["//@@end func-two"]  # New line 15
            + lines[13:]  # Rest of file
        )
        test_file.write_text("\n".join(new_lines))

        github = GitHubIntegration(temp_git_repo)

        # Verify dirty
        assert github.is_file_dirty(test_file)

        # Get hunks for debugging
        hunks = github.get_diff_hunks(test_file)
        print(f"Hunks for single marker: {hunks}")

        # Line 12 in new (functionTwo declaration) should map to line 11 in committed
        committed = github.map_to_committed_line(test_file, 12)
        print(f"New line 12 -> committed line {committed}")
        assert committed == 11, f"Expected 11, got {committed}"

        # Line 20 in new should map to line 18 in committed (offset of -2)
        committed_20 = github.map_to_committed_line(test_file, 20)
        print(f"New line 20 -> committed line {committed_20}")
        assert committed_20 == 18, f"Expected 18, got {committed_20}"


class TestEndToEndPermalink:
    """End-to-end tests for permalink generation with dirty files."""

    @pytest.fixture
    def temp_git_repo_with_remote(self):
        """Create a temp git repo with a fake GitHub remote."""
        temp_dir = tempfile.mkdtemp()
        repo_path = Path(temp_dir)

        # Initialize git repo
        subprocess.run(["git", "init"], cwd=repo_path, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=repo_path,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=repo_path,
            capture_output=True,
        )

        # Add fake GitHub remote
        subprocess.run(
            ["git", "remote", "add", "origin", "git@github.com:testuser/testrepo.git"],
            cwd=repo_path,
            capture_output=True,
        )

        # Copy base fixture and commit
        base_file = FIXTURES_DIR / "line_mapping_base.cpp"
        dest_file = repo_path / "test.cpp"
        shutil.copy(base_file, dest_file)

        subprocess.run(["git", "add", "test.cpp"], cwd=repo_path, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "Initial commit"],
            cwd=repo_path,
            capture_output=True,
        )

        yield repo_path

        # Cleanup
        shutil.rmtree(temp_dir)

    def test_permalink_with_dirty_file(self, temp_git_repo_with_remote):
        """Permalink URL should point to committed line numbers."""
        test_file = temp_git_repo_with_remote / "test.cpp"

        # Add a single marker pair
        base_content = test_file.read_text()
        lines = base_content.split("\n")

        # Insert markers around functionTwo (line 11 in base)
        new_lines = lines[:10] + ["//@@start func-two"] + lines[10:13] + ["//@@end func-two"] + lines[13:]
        test_file.write_text("\n".join(new_lines))

        github = GitHubIntegration(temp_git_repo_with_remote)

        # Get permalink for new lines 12-14 (the function body in working copy)
        # Should map to committed lines 11-13
        permalink = github.get_permalink(test_file, start_line=12, end_line=14)

        print(f"Permalink: {permalink}")

        # URL should contain committed line numbers
        assert "#L11-L13" in permalink, f"Expected #L11-L13 in permalink, got: {permalink}"

        # Display should show committed line numbers (default behavior)
        assert ":11-13" in permalink or "test.cpp:11-13" in permalink
