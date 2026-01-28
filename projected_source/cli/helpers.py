"""
Shared helpers for CLI commands.
"""

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Set

from rich.console import Console

# Shared console instance
console = Console()

# Global fixture collector for error collection mode
_fixture_collector = None


class FixtureCollector:
    """Collects error-causing files as test fixtures."""

    def __init__(self, output_dir: Path):
        self.output_dir = output_dir
        self.errors: List[Dict[str, Any]] = []
        self.copied_files: Set[Path] = set()

    def collect(self, source_file: Path, error: str, template_context: str = None):
        """
        Collect a file that caused an error.

        Args:
            source_file: Path to the file that caused the error
            error: Error message
            template_context: Template that triggered the error
        """
        if not source_file.exists():
            return

        # Create a unique fixture name
        fixture_name = source_file.name
        fixture_path = self.output_dir / fixture_name

        # Handle duplicates by adding a suffix
        counter = 1
        while fixture_path.exists() and source_file not in self.copied_files:
            stem = source_file.stem
            suffix = source_file.suffix
            fixture_path = self.output_dir / f"{stem}_{counter}{suffix}"
            counter += 1

        # Copy the file if not already copied
        if source_file not in self.copied_files:
            self.output_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_file, fixture_path)
            self.copied_files.add(source_file)

        self.errors.append(
            {
                "source_file": str(source_file),
                "fixture_file": fixture_path.name,
                "error": error,
                "template_context": template_context,
            }
        )

    def write_manifest(self):
        """Write manifest.json with all collected errors."""
        if not self.errors:
            return

        manifest = {
            "collected_at": datetime.now().isoformat(),
            "error_count": len(self.errors),
            "unique_files": len(self.copied_files),
            "errors": self.errors,
        }

        manifest_path = self.output_dir / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2))

        return manifest_path


def get_fixture_collector():
    """Get the global fixture collector if in collection mode."""
    return _fixture_collector


def set_fixture_collector(collector: FixtureCollector | None):
    """Set the global fixture collector."""
    global _fixture_collector
    _fixture_collector = collector
