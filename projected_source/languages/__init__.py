"""
Language-specific extractors.
"""

import logging
from pathlib import Path

from .cpp import CppExtractor

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
    return extractor_class()


__all__ = ["get_extractor", "CppExtractor"]
