"""
projected-source: Extract and project source code into documentation.
"""

import logging
from rich.logging import RichHandler

__version__ = "0.1.0"

# Package-level logger
logger = logging.getLogger(__name__)


def setup_logging(level=logging.INFO, use_rich=True):
    """
    Setup logging for the entire package.
    
    Args:
        level: Logging level
        use_rich: Use rich handler for pretty output
    """
    root_logger = logging.getLogger("projected_source")
    root_logger.setLevel(level)
    
    # Clear existing handlers
    root_logger.handlers = []
    
    if use_rich:
        handler = RichHandler(
            rich_tracebacks=True,
            show_path=False,
            markup=True
        )
        handler.setFormatter(logging.Formatter("%(message)s"))
    else:
        handler = logging.StreamHandler()
        handler.setFormatter(
            logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        )
    
    root_logger.addHandler(handler)
    
    # Also configure for sub-modules
    for module in ["core", "languages", "cli"]:
        module_logger = logging.getLogger(f"projected_source.{module}")
        module_logger.setLevel(level)