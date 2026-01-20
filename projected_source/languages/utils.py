"""
Utility functions for language extractors.
"""

from tree_sitter import Node


def node_text(node: Node) -> str:
    """
    Get node text as a decoded string.

    Args:
        node: A tree-sitter Node

    Returns:
        The node's text content as a string, or empty string if text is None.
    """
    return node.text.decode("utf8") if node.text else ""
