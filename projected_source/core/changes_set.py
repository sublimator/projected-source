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

import functools
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Glob patterns that match every path (a catch-all include never "matches
# nothing"), used to suppress a spurious unmatched-include warning on empty D.
# Patterns that match every path — a catch-all include never "matches nothing".
# `*` is NOT here: since real glob semantics landed it stops at the first
# separator, so `*` genuinely can match no changed file (N9).
_CATCH_ALL_GLOBS = frozenset({"**", "**/*"})


@functools.lru_cache(maxsize=512)
def _glob_regex(pattern: str) -> "re.Pattern":
    """Compile a POSIX-ish glob to a regex with real `**` vs `*` semantics.

    `**` matches any number of path segments (including zero); a leading `**/`
    also matches at the top level (so `**/test/**` matches `test/a.cpp`). `*`
    and `?` match within a single segment only — they do not cross `/`. This is
    proper glob, unlike fnmatch (where `*` spans separators).
    """
    # Collapse runs of **/ so the sequential (?:.*/)? groups can't backtrack
    # exponentially on a long non-matching path (N15).
    while "**/**/" in pattern:
        pattern = pattern.replace("**/**/", "**/")
    pattern = pattern.replace("**/**", "**")
    i, n, out = 0, len(pattern), []
    while i < n:
        if pattern[i : i + 3] == "**/":
            out.append("(?:.*/)?")  # zero or more leading segments
            i += 3
        elif pattern[i : i + 2] == "**":
            out.append(".*")
            i += 2
        elif pattern[i] == "*":
            out.append("[^/]*")
            i += 1
        elif pattern[i] == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(pattern[i]))
            i += 1
    return re.compile("^" + "".join(out) + r"\Z")  # \Z, not $, so a trailing newline can't match (N14)


@dataclass
class ChangeRegion:
    """A contiguous region of changed code in a file."""

    file_path: Path
    start_line: int
    end_line: int

    def __str__(self) -> str:
        return f"{self.file_path}:{self.start_line}-{self.end_line}"


# Coverage buckets in resolution priority: when claims overlap, the earlier
# bucket wins the shared lines, so each changed line is credited exactly once.
# code() (narrated) beats audit() (acknowledged) beats ignore_changes() (dropped).
BUCKET_PRIORITY = ("code", "audit", "ignore")


@dataclass
class ClaimRecord:
    """The settled result of one code()/audit()/ignore_changes() claim.

    A claim carries a *list* of regions (geometry such as "symbol minus marker"
    resolves to more than one), so the tally and reporting are region-set aware.
    """

    bucket: str
    file_path: Path
    regions: List[Tuple[int, int]]
    changed_lines: int  # |regions ∩ D| against the frozen snapshot (density / M3)
    credited_lines: int  # lines this claim actually removed from the residual
    chunk_id: Optional[str] = None  # stable node id (seed for the chunk graph)


def _count_in_intervals(intervals: List[Tuple[int, int]], start: int, end: int) -> int:
    """Number of lines in [start, end] covered by a sorted interval list."""
    if start > end:
        start, end = end, start
    total = 0
    for reg_start, reg_end in intervals:
        lo, hi = max(reg_start, start), min(reg_end, end)
        if lo <= hi:
            total += hi - lo + 1
    return total


def _first_region_overlap(
    a_regions: List[Tuple[int, int]], b_regions: List[Tuple[int, int]]
) -> Optional[Tuple[int, int]]:
    """First overlapping [lo, hi] between two region lists, or None."""
    for a_s, a_e in a_regions:
        for b_s, b_e in b_regions:
            lo, hi = max(a_s, b_s), min(a_e, b_e)
            if lo <= hi:
                return (lo, hi)
    return None


def code_display_overlaps(
    records: List["ClaimRecord"],
) -> List[Tuple["ClaimRecord", "ClaimRecord", Tuple[int, int]]]:
    """code() extracts that render overlapping source lines — the same lines
    shown to the reader more than once (a DRY smell worth linting), independent
    of what changed. Returns (later, earlier, overlap) per pair; `earlier` is the
    template-order-earlier extract, so the message can say "already shown above".

    This is distinct from the shadowed-claim report, which is about *changed*
    lines being double-claimed; two extracts can overlap on unchanged context and
    be invisible to that report while still duplicating what the reader sees.
    """
    code = [r for r in records if r.bucket == "code"]
    out: List[Tuple["ClaimRecord", "ClaimRecord", Tuple[int, int]]] = []
    for i, later in enumerate(code):
        for earlier in code[:i]:
            if earlier.file_path != later.file_path:
                continue
            overlap = _first_region_overlap(earlier.regions, later.regions)
            if overlap is not None:
                out.append((later, earlier, overlap))
    return out


def _subtract_interval(
    intervals: List[Tuple[int, int]], start: int, end: int
) -> List[Tuple[int, int]]:
    """Remove [start, end] from an interval list, splitting on partial overlap.

    Pure counterpart of ChangesSet.subtract(); used by partition() to replay
    claims against a copy of D without touching the live residual.
    """
    if start > end:
        start, end = end, start
    out: List[Tuple[int, int]] = []
    for reg_start, reg_end in intervals:
        if end < reg_start or start > reg_end:
            out.append((reg_start, reg_end))
        elif start <= reg_start and end >= reg_end:
            continue
        else:
            if reg_start < start:
                out.append((reg_start, start - 1))
            if reg_end > end:
                out.append((end + 1, reg_end))
    return out


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
        # claim() subtracts immediately (so uncovered()/is_complete() stay live
        # and order-independent for the residual) AND records the claim here.
        # The disjoint per-bucket partition is a separate pure computation
        # (partition()) over the frozen snapshot of D plus these records, so it
        # is order-independent without changing the residual semantics.
        self._claims: List[Tuple[str, Path, List[Tuple[int, int]], Optional[str]]] = []
        # Frozen snapshot of D (the full obligation set), captured once the diff
        # is parsed — before any claim erodes _regions — so |D| and the partition
        # denominators stay recoverable.
        self._d_snapshot: Dict[Path, List[Tuple[int, int]]] = {}
        self._d_line_count: int = 0
        self._frozen: bool = False
        # review_scope: globs restricting which files' changes are obligations.
        # Matched against the diff-relative POSIX path (never the absolute
        # _regions key, which can raise for an out-of-repo root — M1). The
        # defaults include everything, so an unscoped ChangesSet is unchanged.
        self._include: List[str] = ["**"]
        self._exclude: List[str] = []
        self._include_hits: Dict[str, int] = {}
        self._out_of_scope_lines: int = 0
        self._current_out_of_scope: bool = False

    @classmethod
    def from_diff(
        cls,
        base: Optional[str] = None,
        repo_path: Optional[Path] = None,
        include: Optional[List[str]] = None,
        exclude: Optional[List[str]] = None,
    ) -> "ChangesSet":
        """
        Build a ChangesSet from git diff against a base commit or range.

        Args:
            base: Base commit/branch, or a range like "HEAD~5..HEAD~2".
                  If no ".." present, diffs against HEAD. Auto-detected if None.
            repo_path: Path to git repository. Uses cwd if None.
            include: review_scope globs; only changed files whose diff-relative
                     POSIX path matches one are obligations (default: all).
            exclude: review_scope globs applied after include.

        Returns:
            ChangesSet populated with all changed regions in scope.
        """
        repo_path = repo_path or Path.cwd()
        base = base or cls.detect_base(repo_path)

        # Support commit ranges (e.g., "HEAD~5..HEAD~2") or simple base (e.g., "HEAD~5")
        diff_range = base if ".." in base else f"{base}..HEAD"

        changes = cls()
        if include is not None:
            changes._include = list(include)
        if exclude is not None:
            changes._exclude = list(exclude)
        changes._include_hits = {p: 0 for p in changes._include}

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
        changes._freeze_d()
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

    _HUNK_HEADER_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")

    def _parse_diff(self, diff_output: str, repo_path: Path) -> None:
        """Parse unified diff output and populate regions.

        Only '+' lines become required coverage. Unchanged hunk context
        advances the new-file cursor without creating an obligation.
        Deletion-only hunks therefore produce no obligation: a deletion has
        no new-version line to anchor to, and proxying it through unchanged
        neighbors would make coverage depend on diff presentation.

        Hunk bodies are bounded by the @@ header's line counts. Inside a
        body, lines are classified only by their first character — source
        content that *looks* like a header (an added '++ b/x' renders as
        the diff line '+++ b/x') must not switch files or get dropped.
        """
        current_file: Optional[Path] = None
        current_new_line = 0
        old_remaining = 0
        new_remaining = 0

        for line in diff_output.splitlines():
            if old_remaining > 0 or new_remaining > 0:
                # Inside a hunk body.
                if line.startswith("\\"):
                    continue  # '\ No newline at end of file' — meta line
                if line.startswith("+"):
                    # Added/replacement line - needs coverage
                    if current_file:
                        self.add(current_file, current_new_line, current_new_line)
                    elif self._current_out_of_scope:
                        # A real change we dropped because review_scope excluded
                        # its file — tallied so the report can say how much scope
                        # removed (H5), rather than passing --strict silently.
                        self._out_of_scope_lines += 1
                    current_new_line += 1
                    new_remaining -= 1
                elif line.startswith("-"):
                    # Deleted line - doesn't advance the new-file cursor
                    old_remaining -= 1
                else:
                    # Unchanged context line - advances position only
                    current_new_line += 1
                    old_remaining -= 1
                    new_remaining -= 1
                continue

            # New file header: +++ b/path/to/file
            if line.startswith("+++ b/"):
                current_file = self._scoped_file(repo_path, line[6:])  # Strip "+++ b/"
            # C-quoted header: +++ "b/path with \303\251scapes". Git quotes
            # paths with control characters even under quotePath=false.
            elif line.startswith('+++ "b/'):
                current_file = self._scoped_file(repo_path, self._unquote_git_path(line[4:]))
            # Anything else ('+++ /dev/null' for a deleted file, or an
            # unrecognized header form) must never attribute the following
            # hunk lines to the previous file.
            elif line.startswith("+++ "):
                current_file = None
                self._current_out_of_scope = False

            # Hunk header: @@ -old_start,old_count +new_start,new_count @@
            else:
                match = self._HUNK_HEADER_RE.match(line)
                if match:
                    current_new_line = int(match.group(3))
                    old_remaining = int(match.group(2)) if match.group(2) else 1
                    new_remaining = int(match.group(4)) if match.group(4) else 1

    def _scoped_file(self, repo_path: Path, rel: str) -> Optional[Path]:
        """Absolute path if `rel` is in review_scope, else None.

        Matches the diff-relative POSIX path against the include/exclude globs
        with real glob semantics (see _glob_regex: `**` crosses separators, `*`
        does not). Updates the per-pattern hit tally and the in-scope flag used
        to count out-of-scope changed lines.
        """
        rel_posix = Path(rel).as_posix()
        matched = [p for p in self._include if _glob_regex(p).match(rel_posix)]
        for p in matched:
            self._include_hits[p] = self._include_hits.get(p, 0) + 1
        excluded = any(_glob_regex(p).match(rel_posix) for p in self._exclude)
        if matched and not excluded:
            self._current_out_of_scope = False
            return repo_path / rel
        self._current_out_of_scope = True
        return None

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
            #@@start region-split
            else:
                # Left remainder
                if reg_start < start:
                    new_regions.append((reg_start, start - 1))
                # Right remainder
                if reg_end > end:
                    new_regions.append((end + 1, reg_end))
            #@@end region-split

        if new_regions:
            self._regions[file_path] = new_regions
        else:
            del self._regions[file_path]

    def _freeze_d(self) -> None:
        """Snapshot D before any claim erodes _regions (see __init__)."""
        self._d_snapshot = {p: list(regs) for p, regs in self._regions.items()}
        self._d_line_count = sum(e - s + 1 for regs in self._d_snapshot.values() for s, e in regs)
        self._frozen = True

    def claim(
        self,
        bucket: str,
        file_path: Path,
        regions: List[Tuple[int, int]],
        chunk_id: Optional[str] = None,
    ) -> None:
        """Claim coverage for one or more line spans.

        `bucket` is one of BUCKET_PRIORITY. `regions` is a list of (start, end)
        spans — one for an ordinary selector, several for geometry such as
        "symbol minus marker". Each span is subtracted immediately (so the
        residual and uncovered()/is_complete() stay live and order-independent)
        and recorded, so partition() can attribute lines to buckets disjointly.
        `chunk_id` is an optional stable node id carried through to the record
        (the seed for the chunk graph).
        """
        # Freeze D on the first claim if from_diff did not (a directly built
        # ChangesSet is the library API), so partition()/changed_line_count()
        # are meaningful on every construction path (F13).
        if not self._frozen:
            self._freeze_d()
        norm = [(min(s, e), max(s, e)) for s, e in regions]
        self._claims.append((bucket, file_path, norm, chunk_id))
        for s, e in norm:
            self.subtract(file_path, s, e)

    def partition(self) -> Tuple[Dict[str, int], List[ClaimRecord]]:
        """Attribute every changed line to exactly one bucket, order-independently.

        Replays the recorded claims against a fresh copy of the frozen D in
        bucket-priority order (code > audit > ignore): the first bucket to claim
        a line is credited it; later overlapping claims get nothing for it. The
        live residual (_regions) is untouched — this is a pure report-time
        computation. Returns (bucket -> line count, per-claim records).
        """
        residual = {p: list(regs) for p, regs in self._d_snapshot.items()}
        bucket_lines = {b: 0 for b in BUCKET_PRIORITY}
        records: List[ClaimRecord] = []
        for bucket in BUCKET_PRIORITY:
            for claim_bucket, path, regions, chunk_id in self._claims:
                if claim_bucket != bucket:
                    continue
                changed = sum(_count_in_intervals(self._d_snapshot.get(path, []), s, e) for s, e in regions)
                credited = 0
                for s, e in regions:
                    credited += _count_in_intervals(residual.get(path, []), s, e)
                    residual[path] = _subtract_interval(residual.get(path, []), s, e)
                bucket_lines[bucket] += credited
                records.append(ClaimRecord(bucket, path, regions, changed, credited, chunk_id))
        return bucket_lines, records

    def changed_line_count(self) -> int:
        """Total changed lines in D (the obligation set, after scope)."""
        return self._d_line_count

    def out_of_scope_line_count(self) -> int:
        """Changed lines dropped because review_scope excluded their file (H5)."""
        return self._out_of_scope_lines

    def unmatched_includes(self) -> List[str]:
        """review_scope include globs that matched no changed file (H5).

        A non-default include that matches nothing usually means a typo'd glob
        silently narrowing the gate to nothing — worth surfacing so an empty
        scope cannot pass --strict having verified nothing.
        """
        return [p for p, hits in self._include_hits.items() if hits == 0 and p not in _CATCH_ALL_GLOBS]

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
