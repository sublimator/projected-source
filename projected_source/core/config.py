"""Layered configuration for projected-source.

Precedence (later wins): built-in defaults < user config < repo config, with CLI
flags overriding at the call site.

  user:  $XDG_CONFIG_HOME/projected-source/config.toml (default ~/.config/...)
  repo:  the nearest .projected-source.toml walking up from the working path

This sits beside the existing .projected-source.py custom-tags convention and is
read with the stdlib tomllib (Python >= 3.11). Unknown sections/keys are kept
verbatim, so a project can encode policy this module does not yet interpret.
"""

import os
import tomllib
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO_CONFIG_NAME = ".projected-source.toml"

# Built-in defaults. `None` means "no policy" — the knob is inert until set.
DEFAULTS: Dict[str, Dict[str, Any]] = {
    "validation": {"min_density": None, "max_audit_ratio": None},
    "audit": {"max_changed_lines": None, "min_reason_length": 0},
    "scope": {"exclude": []},
    "render": {"enclosure_context": None},
}


def user_config_path() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "projected-source" / "config.toml"


def find_repo_config(start: Path) -> Optional[Path]:
    """Nearest .projected-source.toml walking up from `start` (a file or dir)."""
    current = start.resolve()
    if current.is_file():
        current = current.parent
    for directory in [current, *current.parents]:
        candidate = directory / REPO_CONFIG_NAME
        if candidate.is_file():
            return candidate
    return None


def _read_toml(path: Path) -> Dict[str, Any]:
    try:
        with open(path, "rb") as handle:
            return tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError):
        return {}


def _deep_merge(base: Dict[str, Any], over: Dict[str, Any]) -> Dict[str, Any]:
    out = {k: (dict(v) if isinstance(v, dict) else v) for k, v in base.items()}
    for key, value in over.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


class Config:
    """Merged configuration with typed accessors for the known policy knobs."""

    def __init__(self, data: Dict[str, Any], sources: List[Path]):
        self._data = data
        self.sources = sources  # config files that contributed, low-to-high priority

    def get(self, section: str, key: str, default: Any = None) -> Any:
        return self._data.get(section, {}).get(key, default)

    # -- typed convenience for the wired knobs --
    @property
    def min_density(self) -> Optional[float]:
        return self.get("validation", "min_density")

    @property
    def max_audit_ratio(self) -> Optional[float]:
        return self.get("validation", "max_audit_ratio")

    @property
    def max_audit_changed_lines(self) -> Optional[int]:
        return self.get("audit", "max_changed_lines")

    @property
    def min_reason_length(self) -> int:
        return self.get("audit", "min_reason_length", 0) or 0

    @property
    def scope_exclude(self) -> List[str]:
        return list(self.get("scope", "exclude", []) or [])


def load_config(start_path: Optional[Path] = None) -> Config:
    """Load and merge the config layers for a working path (a template or dir)."""
    start = Path(start_path) if start_path else Path.cwd()
    data: Dict[str, Any] = _deep_merge({}, DEFAULTS)
    sources: List[Path] = []

    user = user_config_path()
    if user.is_file():
        data = _deep_merge(data, _read_toml(user))
        sources.append(user)

    repo = find_repo_config(start)
    if repo:
        data = _deep_merge(data, _read_toml(repo))
        sources.append(repo)

    return Config(data, sources)
