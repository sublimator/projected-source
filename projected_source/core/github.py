"""
GitHub integration for permalinks and git blame.
Adapted from rwdb-online-delete-fix.py
"""

import datetime
import logging
import re
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


def parse_diff_hunks(diff_output: str) -> List[Tuple[int, int, int, int]]:
    """
    Parse git diff output to extract hunk information.

    Returns list of tuples: (old_start, old_count, new_start, new_count)
    """
    hunks = []
    hunk_pattern = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")

    for line in diff_output.split("\n"):
        match = hunk_pattern.match(line)
        if match:
            old_start = int(match.group(1))
            old_count = int(match.group(2)) if match.group(2) else 1
            new_start = int(match.group(3))
            new_count = int(match.group(4)) if match.group(4) else 1
            hunks.append((old_start, old_count, new_start, new_count))

    return hunks


def build_line_mapping(diff_output: str) -> Dict[int, Optional[int]]:
    """
    Build a mapping from new line numbers to old line numbers by parsing diff content.

    Returns a dict where:
    - key: new line number
    - value: old line number, or None if the line was added (doesn't exist in old)
    """
    mapping: Dict[int, Optional[int]] = {}
    hunk_pattern = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")

    old_line = 0
    new_line = 0
    in_hunk = False

    for line in diff_output.split("\n"):
        # Check for hunk header
        match = hunk_pattern.match(line)
        if match:
            old_line = int(match.group(1))
            new_line = int(match.group(3))
            in_hunk = True
            continue

        if not in_hunk:
            continue

        if line.startswith("+++") or line.startswith("---"):
            continue

        if line.startswith("+"):
            # Added line - exists in new file only
            mapping[new_line] = None
            new_line += 1
        elif line.startswith("-"):
            # Removed line - exists in old file only
            old_line += 1
        elif line.startswith(" ") or line == "":
            # Context line - exists in both
            mapping[new_line] = old_line
            old_line += 1
            new_line += 1
        elif line.startswith("\\"):
            # "\ No newline at end of file" - ignore
            continue

    return mapping


def map_line_to_committed(new_line: int, hunks: List[Tuple[int, int, int, int]]) -> int:
    """
    Map a line number in the working copy to the corresponding line in HEAD.

    This is a simplified version using only hunk headers. For more accurate mapping
    when lines are added within hunks, use map_line_to_committed_full().

    Args:
        new_line: Line number in the working copy (1-based)
        hunks: List of (old_start, old_count, new_start, new_count) tuples

    Returns:
        Corresponding line number in HEAD
    """
    if not hunks:
        return new_line

    offset = 0

    for old_start, old_count, new_start, new_count in hunks:
        new_end = new_start + new_count

        if new_line < new_start:
            # Line is before this hunk
            break
        elif new_line < new_end:
            # Line is within this hunk
            # Assume additions are at the start of the hunk (common for markers)
            added_lines = new_count - old_count
            if added_lines > 0:
                # Lines were added to this hunk
                lines_into_hunk = new_line - new_start
                if lines_into_hunk < added_lines:
                    # This line is one of the added lines, map to start of old region
                    return old_start
                else:
                    # This line existed before, calculate its old position
                    return old_start + (lines_into_hunk - added_lines)
            else:
                # Lines were removed or replaced, direct mapping
                lines_into_hunk = new_line - new_start
                if lines_into_hunk < old_count:
                    return old_start + lines_into_hunk
                else:
                    return old_start + old_count - 1 if old_count > 0 else old_start
        else:
            # Line is after this hunk
            offset += old_count - new_count

    return new_line + offset


def map_line_to_committed_full(new_line: int, diff_output: str) -> int:
    """
    Map a line number using full diff parsing for accurate results.

    Args:
        new_line: Line number in the working copy (1-based)
        diff_output: Full git diff output

    Returns:
        Corresponding line number in HEAD
    """
    mapping = build_line_mapping(diff_output)

    # If we have a direct mapping for this line
    if new_line in mapping:
        old = mapping[new_line]
        if old is not None:
            return old
        # Line was added, find nearest non-added line before it
        for check_line in range(new_line - 1, 0, -1):
            if check_line in mapping and mapping[check_line] is not None:
                result = mapping[check_line]
                assert result is not None  # For type narrowing
                return result
        # Fall back to line 1
        return 1

    # Line not in any hunk - calculate offset from hunks before it
    hunks = parse_diff_hunks(diff_output)
    offset = 0
    for old_start, old_count, new_start, new_count in hunks:
        if new_line < new_start:
            break
        offset += old_count - new_count

    return new_line + offset


class GitHubIntegration:
    """Handle GitHub permalinks and git operations."""

    def __init__(self, repo_path: Optional[Path] = None):
        self.repo_path = repo_path or Path.cwd()
        self._github_url: Optional[str] = None
        self._commit_hash: Optional[str] = None
        self._initialized = False
        self._diff_cache: Dict[str, str] = {}  # Cache diff output per file

    def _init_repo_info(self):
        """Lazy initialization of repository information."""
        if self._initialized:
            return

        try:
            # Get the remote origin URL
            origin_url = (
                subprocess.check_output(
                    ["git", "remote", "get-url", "origin"], cwd=self.repo_path, stderr=subprocess.DEVNULL
                )
                .decode()
                .strip()
            )

            # Get current commit hash
            self._commit_hash = (
                subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=self.repo_path, stderr=subprocess.DEVNULL)
                .decode()
                .strip()
            )

            # Convert SSH/HTTPS URL to GitHub web URL
            if origin_url.startswith("git@github.com:"):
                # SSH format: git@github.com:user/repo.git
                repo_path = origin_url.replace("git@github.com:", "").replace(".git", "")
            elif "github.com" in origin_url:
                # HTTPS format: https://github.com/user/repo.git
                repo_path = re.sub(r"https?://github\.com/", "", origin_url).replace(".git", "")
            else:
                logger.warning(f"Non-GitHub repository: {origin_url}")
                self._initialized = True
                return

            self._github_url = f"https://github.com/{repo_path}"
            logger.debug(f"GitHub URL: {self._github_url}, Commit: {self._commit_hash[:8]}")

        except subprocess.CalledProcessError as e:
            logger.warning(f"Git command failed: {e}")
        except Exception as e:
            logger.warning(f"Failed to get GitHub info: {e}")

        self._initialized = True

    @property
    def github_url(self) -> Optional[str]:
        """Get the GitHub repository URL."""
        self._init_repo_info()
        return self._github_url

    @property
    def commit_hash(self) -> Optional[str]:
        """Get the current commit hash."""
        self._init_repo_info()
        return self._commit_hash

    def is_file_dirty(self, file_path: Path) -> bool:
        """Check if a file has uncommitted changes."""
        try:
            # Get path relative to repo
            if file_path.is_absolute():
                rel_path = file_path.relative_to(self.repo_path)
            else:
                rel_path = file_path

            # Check if file has changes (staged or unstaged)
            result = subprocess.run(
                ["git", "diff", "--quiet", "HEAD", "--", str(rel_path)], cwd=self.repo_path, capture_output=True
            )
            return result.returncode != 0
        except Exception as e:
            logger.debug(f"Could not check dirty status for {file_path}: {e}")
            return False

    def get_diff_output(self, file_path: Path) -> str:
        """
        Get the full diff output for a file (cached).

        Returns the raw git diff output string.
        """
        cache_key = str(file_path.resolve()) + "_diff"

        if cache_key in self._diff_cache:
            return self._diff_cache[cache_key]

        try:
            if file_path.is_absolute():
                rel_path = file_path.relative_to(self.repo_path)
            else:
                rel_path = file_path

            diff_output = subprocess.check_output(
                ["git", "diff", "HEAD", "--", str(rel_path)], cwd=self.repo_path, stderr=subprocess.DEVNULL
            ).decode()

            self._diff_cache[cache_key] = diff_output
            return diff_output

        except Exception as e:
            logger.debug(f"Could not get diff for {file_path}: {e}")
            return ""

    def get_diff_hunks(self, file_path: Path) -> List[Tuple[int, int, int, int]]:
        """
        Get diff hunks for a file (cached).

        Returns list of (old_start, old_count, new_start, new_count) tuples.
        """
        diff_output = self.get_diff_output(file_path)
        return parse_diff_hunks(diff_output)

    def map_to_committed_line(self, file_path: Path, line: int) -> int:
        """
        Map a line number in working copy to the committed version.

        If file is clean, returns the same line number.
        If file is dirty, adjusts for added/removed lines using full diff parsing.
        """
        if not self.is_file_dirty(file_path):
            return line

        diff_output = self.get_diff_output(file_path)
        if not diff_output:
            return line

        return map_line_to_committed_full(line, diff_output)

    def get_permalink(
        self, file_path: Path, start_line: int = None, end_line: int = None, display_committed_lines: bool = True
    ) -> str:
        """
        Generate a GitHub permalink for a file or line range.

        Args:
            file_path: Path to the file
            start_line: Optional start line number (1-based)
            end_line: Optional end line number (1-based)
            display_committed_lines: If True, display shows committed line numbers (matches link).
                                     If False, display shows working copy line numbers.

        Returns:
            Formatted markdown link or plain text reference
        """
        # Make path relative to repo root
        try:
            if file_path.is_absolute():
                rel_path = file_path.relative_to(self.repo_path)
            else:
                rel_path = file_path
        except ValueError:
            rel_path = file_path

        if self.github_url and self.commit_hash:
            # Map line numbers if file is dirty (has uncommitted changes like markers)
            committed_start = None
            committed_end = None
            is_dirty = False

            if start_line is not None:
                committed_start = self.map_to_committed_line(file_path, start_line)
                is_dirty = committed_start != start_line
                if end_line is not None:
                    committed_end = self.map_to_committed_line(file_path, end_line)

            # Build GitHub URL with committed line numbers
            url = f"{self.github_url}/blob/{self.commit_hash}/{rel_path}"

            # Add line anchors if specified (using committed line numbers for URL)
            if committed_start is not None:
                # Choose which line numbers to display
                if display_committed_lines or not is_dirty:
                    display_start = committed_start
                    display_end = committed_end
                else:
                    # start_line must be set if committed_start was computed
                    assert start_line is not None
                    display_start = start_line
                    display_end = end_line

                if committed_end and committed_end != committed_start:
                    url += f"#L{committed_start}-L{committed_end}"
                    display = f"{rel_path}:{display_start}-{display_end}"
                    if is_dirty:
                        logger.debug(
                            f"Dirty file: mapped lines {start_line}-{end_line} → {committed_start}-{committed_end}"
                        )
                else:
                    url += f"#L{committed_start}"
                    display = f"{rel_path}:{display_start}"
            else:
                display = str(rel_path)

            # Return as markdown link
            return f"📍 [`{display}`]({url})"
        else:
            # No GitHub info, return plain text
            if start_line is not None:
                if end_line and end_line != start_line:
                    return f"📍 `{rel_path}:{start_line}-{end_line}`"
                else:
                    return f"📍 `{rel_path}:{start_line}`"
            else:
                return f"📍 `{rel_path}`"

    def get_blame(self, file_path: Path, start_line: int, end_line: int) -> Dict[int, Dict]:
        """
        Get git blame information for a line range.

        Args:
            file_path: Path to the file
            start_line: Start line number (1-based)
            end_line: End line number (1-based)

        Returns:
            Dict mapping line numbers to blame info
        """
        try:
            blame_output = subprocess.check_output(
                ["git", "blame", "-L", f"{start_line},{end_line}", "--porcelain", str(file_path)],
                cwd=self.repo_path,
                stderr=subprocess.DEVNULL,
            ).decode()

            blame_info = {}
            lines = blame_output.split("\n")
            i = 0

            while i < len(lines):
                line = lines[i]
                if line and not line.startswith("\t"):
                    parts = line.split(" ")
                    if len(parts) >= 3:
                        commit_hash = parts[0]
                        int(parts[1])
                        final_line = int(parts[2])

                        # Extract commit metadata
                        author = ""
                        date = ""
                        i += 1

                        while i < len(lines) and not lines[i].startswith("\t"):
                            if lines[i].startswith("author "):
                                author = lines[i][7:]
                            elif lines[i].startswith("author-time "):
                                timestamp = int(lines[i][12:])
                                date = datetime.datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d")
                            i += 1

                        blame_info[final_line] = {
                            "commit": commit_hash[:8],
                            "author": author[:20],  # Truncate long names
                            "date": date,
                        }
                i += 1

            return blame_info

        except subprocess.CalledProcessError as e:
            logger.warning(f"Git blame failed: {e}")
            return {}
        except Exception as e:
            logger.error(f"Error getting blame info: {e}")
            return {}

    def format_with_blame(self, code_text: str, start_line: int, file_path: Path) -> str:
        """
        Format code with git blame information.

        Args:
            code_text: The code to format
            start_line: Starting line number
            file_path: Path to the file

        Returns:
            Formatted code with blame info
        """
        lines = code_text.splitlines()
        end_line = start_line + len(lines) - 1

        blame_info = self.get_blame(file_path, start_line, end_line)

        formatted_lines = []
        for i, line in enumerate(lines):
            line_num = start_line + i

            if line_num in blame_info:
                blame = blame_info[line_num]
                # Format: line_num | commit | author | date | code
                formatted_line = f"{line_num:4} │ {blame['commit']} │ {blame['author']:<20} │ {blame['date']} │ {line}"
            else:
                formatted_line = f"{line_num:4} │ {line}"

            formatted_lines.append(formatted_line)

        return "\n".join(formatted_lines)
