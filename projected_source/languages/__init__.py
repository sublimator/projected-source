"""
Language-specific extractors.
"""

import logging
from pathlib import Path

from .cpp import CppExtractor
from .java import JavaExtractor
from .lean import LeanExtractor
from .proto import ProtoExtractor
from .python import PythonExtractor
from .rust import RustExtractor
from .typescript import TypeScriptExtractor

logger = logging.getLogger(__name__)

# Map file extensions to extractors
EXTRACTORS = {
    ".cpp": CppExtractor,
    ".cc": CppExtractor,
    ".cxx": CppExtractor,
    ".c++": CppExtractor,
    ".hpp": CppExtractor,
    ".h": CppExtractor,
    ".hxx": CppExtractor,
    ".h++": CppExtractor,
    ".c": CppExtractor,  # C is close enough to C++ for our purposes
    ".ipp": CppExtractor,  # Inline implementation files
    ".macro": CppExtractor,  # C preprocessor macro files (e.g., rippled sfields.macro)
    ".proto": ProtoExtractor,  # Protocol Buffers
    ".py": PythonExtractor,  # Python
    ".pyi": PythonExtractor,  # Python type stubs
    ".ts": TypeScriptExtractor,  # TypeScript
    ".tsx": TypeScriptExtractor,  # TSX (React) — tsx=True set via get_extractor
    ".mts": TypeScriptExtractor,  # TypeScript ES module
    ".cts": TypeScriptExtractor,  # TypeScript CommonJS module
    ".java": JavaExtractor,  # Java
    ".rs": RustExtractor,  # Rust
    ".lean": LeanExtractor,  # Lean 4
}


def get_extractor(file_path: Path):
    """
    Get the appropriate extractor for a file based on its extension.

    Args:
        file_path: Path to the file

    Returns:
        An extractor instance

    Raises:
        ValueError: If no extractor is available for the file type
    """
    suffix = file_path.suffix.lower()

    if suffix not in EXTRACTORS:
        supported = ", ".join(EXTRACTORS.keys())
        raise ValueError(f"No extractor for {suffix} files. Supported: {supported}")

    extractor_class = EXTRACTORS[suffix]
    if extractor_class is TypeScriptExtractor and suffix == ".tsx":
        return extractor_class(tsx=True)
    return extractor_class()


__all__ = ["get_extractor", "CppExtractor"]
