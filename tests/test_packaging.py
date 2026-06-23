"""Regression guards for packaging configuration in pyproject.toml.

Background:
- The Lean grammar binding is compiled by ``hatch_build.py`` into
  ``projected_source/languages/lean_grammar/_binding<EXT_SUFFIX>.so`` and is
  gitignored. Hatchling honors .gitignore by default, so without an explicit
  ``artifacts`` entry the file is silently dropped from the wheel, breaking
  ``from projected_source.languages.lean_grammar._binding import language``
  on non-editable installs.
- ``tree-sitter-cmake`` was never used by any extractor, so it should not be
  declared as a runtime dependency.
"""

from __future__ import annotations

import sys
import tomllib
from pathlib import Path

PYPROJECT = Path(__file__).resolve().parent.parent / "pyproject.toml"


def _load_pyproject() -> dict:
    with PYPROJECT.open("rb") as fh:
        return tomllib.load(fh)


def test_wheel_includes_compiled_lean_binding_artifact() -> None:
    cfg = _load_pyproject()
    wheel_cfg = cfg["tool"]["hatch"]["build"]["targets"]["wheel"]
    artifacts = wheel_cfg.get("artifacts", [])
    assert any(
        "lean_grammar/_binding" in pattern and pattern.endswith(".so")
        for pattern in artifacts
    ), (
        "wheel target must declare the compiled Lean binding as an artifact "
        "(it is gitignored, so hatchling drops it from the wheel otherwise)"
    )


def test_tree_sitter_cmake_not_a_runtime_dependency() -> None:
    cfg = _load_pyproject()
    deps = cfg["project"]["dependencies"]
    assert not any(
        dep.split(">=")[0].split("==")[0].split("<")[0].strip() == "tree-sitter-cmake"
        for dep in deps
    ), "tree-sitter-cmake is not used by any extractor; do not ship it as a runtime dep"


if sys.version_info < (3, 11):  # pragma: no cover - guard for older interpreters
    raise RuntimeError("tomllib requires Python 3.11+; this project pins >=3.11")
