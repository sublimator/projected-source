"""Compile the vendored Lean tree-sitter grammar into a Python C extension.

Julian/tree-sitter-lean's published pyproject ships ``binding.c`` but never
compiles it (its hatchling build has no C-extension hook). We vendor the
sources under ``projected_source/languages/lean_grammar/`` (pinned to upstream
rev ``30f05c80e``) and build the binding here as a hatchling custom build
hook.

The compiled artifact is written next to the vendored sources so that
``from projected_source.languages.lean_grammar._binding import language``
works under both wheel installs and editable (``uv sync``) installs — the
file ends up inside the source tree, which editable installs reference
directly and wheel builds package as data.
"""

from __future__ import annotations

import os
import platform
import subprocess
import sysconfig
from pathlib import Path

from hatchling.builders.hooks.plugin.interface import BuildHookInterface


class CustomBuildHook(BuildHookInterface):
    PLUGIN_NAME = "custom"

    def initialize(self, version: str, build_data: dict) -> None:
        root = Path(self.root)
        grammar = root / "projected_source" / "languages" / "lean_grammar"
        sources = [
            grammar / "binding.c",
            grammar / "src" / "parser.c",
            grammar / "src" / "scanner.c",
        ]
        missing = [str(s) for s in sources if not s.exists()]
        if missing:
            raise RuntimeError(f"missing vendored Lean grammar source: {missing}")

        suffix = sysconfig.get_config_var("EXT_SUFFIX") or ".so"
        output = grammar / f"_binding{suffix}"

        cmd = [
            os.environ.get("CC", "cc"),
            "-shared",
            "-fPIC",
            "-O2",
            "-std=c11",
            f"-I{grammar / 'src'}",
            f"-I{sysconfig.get_path('include')}",
            *(str(s) for s in sources),
            "-o",
            str(output),
        ]
        if platform.system() == "Darwin":
            cmd += ["-undefined", "dynamic_lookup"]

        print(f"[hatch_build] compiling Lean grammar -> {output.name}")
        subprocess.run(cmd, check=True)
