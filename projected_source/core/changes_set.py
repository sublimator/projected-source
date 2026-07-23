"""
ChangesSet - Track and validate documentation coverage of code changes.

Provides a set-like data structure for managing changed code regions,
with support for merging overlapping regions and tracking which regions
have been "claimed" by documentation.

Only actual added/replacement lines become required coverage. The unchanged
context lines Git prints around each hunk are presentation, not part of the
change — requiring them would force documentation to match the shape of the
unified diff rather than the edit itself.
"""

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple


@dataclass
class ChangeRegion:
    """A contiguous region of changed code in a file."""

    file_path: Path
    start_line: int
    end_line: int

    def __str__(self) -> str:
        return f"{self.file_path}:{self.start_line}-{self.end_line}"


class ChangesSet:
    """
    Set-like structure for tracking changed code regions.

    Supports adding regions (with automatic merging of overlapping/adjacent),
    subtracting regions (when claimed by documentation), and querying
    uncovered regions.
    """

    def __init__(self):
        # Dict[Path, List[Tuple[start, end]]] - sorted, non-overlapping regions
        self._regions: Dict[Path, List[Tuple[int, int]]] = {}
        # Destination commit of the validated range (set by from_diff).
        # Extractions pinned with ref= at exactly this commit share its line
        # coordinate space, so they may claim coverage directly.
        self.target_sha: Optional[str] = None

    @classmethod
    def from_diff(cls, base: Optional[str] = None, repo_path: Optional[Path] = None) -> "ChangesSet":
        """
        Build a ChangesSet from git diff against a base commit or range.

        Args:
            base: Base commit/branch, or a range like "HEAD~5..HEAD~2".
                  If no ".." present, diffs against HEAD. Auto-detected if None.
            repo_path: Path to git repository. Uses cwd if None.

        Returns:
            ChangesSet populated with all changed regions.
        """
        repo_path = repo_path or Path.cwd()
        base = base or cls.detect_base(repo_path)

        # Support commit ranges (e.g., "HEAD~5..HEAD~2") or simple base (e.g., "HEAD~5")
        diff_range = base if ".." in base else f"{base}..HEAD"

        changes = cls()

        # Get diff with file names and line numbers. quotePath=false keeps
        # non-ASCII paths as raw UTF-8 instead of C-quoted octal escapes,
        # so '+++ b/<path>' parsing sees the real path.
        result = subprocess.run(
            ["git", "-c", "core.quotePath=false", "diff", diff_range, "--unified=3"],
            capture_output=True,
            cwd=repo_path,
            text=True,
        )

        if result.returncode != 0:
            raise RuntimeError(f"git diff failed: {result.stderr}")

        changes._parse_diff(result.stdout, repo_path)
        target = diff_range.rsplit("..", 1)[-1].lstrip(".") or "HEAD"
        changes.target_sha = cls._resolve_commit(target, repo_path)
        return changes

    @staticmethod
    def _resolve_commit(ref: str, repo_path: Path) -> Optional[str]:
        """Resolve a ref to a full commit SHA, or None if it doesn't resolve."""
        result = subprocess.run(
            ["git", "rev-parse", f"{ref}^{{commit}}"],
            capture_output=True,
            cwd=repo_path,
            text=True,
        )
        if result.returncode != 0:
            return None
        return result.stdout.strip()

    @staticmethod
    def detect_base(repo_path: Path) -> str:
        """
        Auto-detect the base commit for diffing.

        Tries merge-base with main, then master, falls back to HEAD~1.
        """
        # Try main
        result = subprocess.run(
            ["git", "merge-base", "HEAD", "main"],
            capture_output=True,
            cwd=repo_path,
            text=True,
        )
        if result.returncode == 0:
            return result.stdout.strip()

        # Try master
        result = subprocess.run(
            ["git", "merge-base", "HEAD", "master"],
            capture_output=True,
            cwd=repo_path,
            text=True,
        )
        if result.returncode == 0:
            return result.stdout.strip()

        # Fall back to parent commit
        return "HEAD~1"

    def _parse_diff(self, diff_output: str, repo_path: Path) -> None:
        """Parse unified diff output and populate regions.

        Only '+' lines become required coverage. Unchanged hunk context
        advances the new-file cursor without creating an obligation.
        Deletion-only hunks therefore produce no obligation: a deletion has
        no new-version line to anchor to, and proxying it through unchanged
        neighbors would make coverage depend on diff presentation.
        """
        current_file: Optional[Path] = None
        current_new_line = 0

        for line in diff_output.splitlines():
            # New file header: +++ b/path/to/file
            if line.startswith("+++ b/"):
                file_path = line[6:]  # Strip "+++ b/"
                current_file = repo_path / file_path
            # C-quoted header: +++ "b/path with \303\251scapes". Git quotes
            # paths with control characters even under quotePath=false.
            elif line.startswith('+++ "b/'):
                current_file = repo_path / self._unquote_git_path(line[4:])
            # Anything else ('+++ /dev/null' for a deleted file, or an
            # unrecognized header form) must never attribute the following
            # hunk lines to the previous file.
            elif line.startswith("+++ "):
                current_file = None

            # Hunk header: @@ -old_start,old_count +new_start,new_count @@
            elif line.startswith("@@"):
                # Parse new file position
                parts = line.split()
                if len(parts) >= 3:
                    new_range = parts[2]  # e.g., "+10,5" or "+10"
                    if new_range.startswith("+"):
                        new_range = new_range[1:]
                        if "," in new_range:
                            current_new_line = int(new_range.split(",")[0])
                        else:
                            current_new_line = int(new_range)

            # Added or context line - track position
            elif current_file and not line.startswith("-"):
                if line.startswith("+"):
                    # Added/replacement line - needs coverage
                    self.add(current_file, current_new_line, current_new_line)
                    current_new_line += 1
                elif line.startswith(" "):
                    # Unchanged context line - advances position only
                    current_new_line += 1

            # Deleted line - doesn't increment new line counter
            elif line.startswith("-") and not line.startswith("---"):
                pass  # Deletion - surrounding context already captured

    _GIT_PATH_ESCAPES = {
        "a": "\a",
        "b": "\b",
        "f": "\f",
        "n": "\n",
        "r": "\r",
        "t": "\t",
        "v": "\v",
        '"': '"',
        "\\": "\\",
    }

    @classmethod
    def _unquote_git_path(cls, quoted: str) -> str:
        """Decode a git C-style quoted path: '"b/na\\303\\257ve.h"' -> 'b/naïve.h'.

        Octal escapes are raw bytes of the UTF-8 encoding, so unescape to
        bytes first and decode at the end.
        """
        inner = quoted.strip()
        if inner.startswith('"') and inner.endswith('"'):
            inner = inner[1:-1]
        out = bytearray()
        i = 0
        while i < len(inner):
            ch = inner[i]
            if ch == "\\" and i + 1 < len(inner):
                nxt = inner[i + 1]
                if nxt.isdigit():
                    out.append(int(inner[i + 1 : i + 4], 8))
                    i += 4
                    continue
                out.extend(cls._GIT_PATH_ESCAPES.get(nxt, nxt).encode("utf8"))
                i += 2
                continue
            out.extend(ch.encode("utf8"))
            i += 1
        path = out.decode("utf8", errors="surrogateescape")
        return path[2:] if path.startswith("b/") else path

    def add(self, file_path: Path, start: int, end: int) -> None:
        """
        Add a region, merging with overlapping or adjacent regions.

        Args:
            file_path: Path to the file
            start: Start line (1-based, inclusive)
            end: End line (1-based, inclusive)
        """
        if start > end:
            start, end = end, start

        regions = self._regions.setdefault(file_path, [])

        # Add new region and re-merge everything
        regions.append((start, end))
        self._regions[file_path] = self._merge_sorted(sorted(regions))

    def _merge_sorted(self, regions: List[Tuple[int, int]]) -> List[Tuple[int, int]]:
        """Merge a sorted list of potentially overlapping regions."""
        if not regions:
            return []

        result = [regions[0]]
        for start, end in regions[1:]:
            last_start, last_end = result[-1]
            if start <= last_end + 1:
                # Overlapping or adjacent - merge
                result[-1] = (last_start, max(last_end, end))
            else:
                result.append((start, end))
        return result

    def subtract(self, file_path: Path, start: int, end: int) -> None:
        """
        Remove a region (mark as covered by documentation).

        May split existing regions if the subtracted region is in the middle.

        Args:
            file_path: Path to the file
            start: Start line (1-based, inclusive)
            end: End line (1-based, inclusive)
        """
        if file_path not in self._regions:
            return

        if start > end:
            start, end = end, start

        new_regions: List[Tuple[int, int]] = []

        for reg_start, reg_end in self._regions[file_path]:
            # No overlap - keep as is
            if end < reg_start or start > reg_end:
                new_regions.append((reg_start, reg_end))

            # Full coverage - remove entirely
            elif start <= reg_start and end >= reg_end:
                pass  # Don't add it

            # Partial overlap - may need to split
            else:
                # Left remainder
                if reg_start < start:
                    new_regions.append((reg_start, start - 1))
                # Right remainder
                if reg_end > end:
                    new_regions.append((end + 1, reg_end))

        if new_regions:
            self._regions[file_path] = new_regions
        else:
            del self._regions[file_path]

    def uncovered(self) -> List[ChangeRegion]:
        """Return list of regions not yet claimed by documentation."""
        result = []
        for file_path, regions in sorted(self._regions.items()):
            for start, end in regions:
                result.append(ChangeRegion(file_path, start, end))
        return result

    def is_complete(self) -> bool:
        """Return True if all regions have been claimed."""
        return len(self._regions) == 0

    def files(self) -> List[Path]:
        """Return list of files with uncovered changes."""
        return list(self._regions.keys())

    def __len__(self) -> int:
        """Return total number of uncovered regions."""
        return sum(len(regions) for regions in self._regions.values())

    def __bool__(self) -> bool:
        """Return True if there are uncovered regions."""
        return len(self._regions) > 0

    def __repr__(self) -> str:
        total = len(self)
        files = len(self._regions)
        return f"ChangesSet({total} regions in {files} files)"
