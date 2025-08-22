#!/usr/bin/env python3
"""
Extended MacroFinder that can return tree-sitter nodes for further processing.
"""

import logging
from typing import List, Optional, Dict, Any, TypedDict, Tuple
from tree_sitter import Node, Parser, Language
import tree_sitter_cpp as tscpp

from .macro_finder_v3 import MacroFinder, MacroResult, PredicateType

logger = logging.getLogger(__name__)


class MacroNodeResult(TypedDict):
    """Extended result that includes the actual node."""
    macro: str
    arguments: List[str]
    text: str
    start_byte: int
    end_byte: int
    start_point: Tuple[int, int]
    end_point: Tuple[int, int]
    line: int
    type: Optional[str]
    node: Node  # The actual tree-sitter node
    args_node: Node  # The arguments node


class MacroFinderWithNodes(MacroFinder):
    """
    Extended MacroFinder that returns tree-sitter nodes.
    This allows for further processing like finding markers within the node.
    """
    
    def find_by_name_with_nodes(self, source: bytes, name: str) -> List[MacroNodeResult]:
        """Find macros and return with their tree-sitter nodes."""
        tree = self.parser.parse(source)
        results = []
        
        # Use the parent's query mechanism
        query_text = self._build_query(PredicateType.EQUALS, name)
        
        try:
            from tree_sitter import Query, QueryCursor
            query = self._get_query(query_text)
            cursor = QueryCursor(query)
            matches = cursor.matches(tree.root_node)
            
            for pattern_index, captures in matches:
                macro_nodes = captures.get("macro_usage", [])
                macro_name_nodes = captures.get("macro_name", [])
                args_nodes = captures.get("args", [])
                
                if not (macro_nodes and args_nodes):
                    continue
                
                macro_node = macro_nodes[0]
                args_node = args_nodes[0]
                name_node = macro_name_nodes[0] if macro_name_nodes else None
                
                # Build the standard result
                base_result = self._build_result(macro_node, args_node, name_node)
                
                # Add the nodes
                result = MacroNodeResult(
                    **base_result,
                    node=macro_node,
                    args_node=args_node
                )
                results.append(result)
                
        except Exception as e:
            logger.error(f"Query failed: {e}")
            
        return results
    
    def find_markers_in_macro(self, source: bytes, macro_name: str, 
                             macro_args: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        """
        Find a macro and extract markers within it.
        
        Returns dict with:
        - 'macro': The macro info
        - 'markers': Dict of marker_name -> (start_line, end_line) within the macro
        """
        # Find the macro with nodes
        results = self.find_by_name_with_nodes(source, macro_name)
        
        # Filter by arguments if specified
        if macro_args:
            filtered = []
            for r in results:
                match = True
                for key, value in macro_args.items():
                    if key.startswith('arg'):
                        pos = int(key[3:])
                        if pos >= len(r['arguments']) or r['arguments'][pos].strip() != value:
                            match = False
                            break
                if match:
                    filtered.append(r)
            results = filtered
        
        if not results:
            raise ValueError(f"Macro {macro_name} not found")
        if len(results) > 1:
            raise ValueError(f"Multiple macros found, be more specific")
        
        result = results[0]
        macro_node = result['node']
        
        # Now find markers within this node
        markers = self._find_markers_in_node(macro_node)
        
        return {
            'macro': result,
            'markers': markers
        }
    
    def _find_markers_in_node(self, node: Node) -> Dict[str, Tuple[int, int]]:
        """Find comment markers within a node."""
        from tree_sitter import Query, QueryCursor
        
        markers = {}
        
        # Query for comments
        comment_query = Query(self.language, '(comment) @comment')
        cursor = QueryCursor(comment_query)
        matches = cursor.matches(node)
        
        current_marker = None
        start_line = None
        
        for _, captures in matches:
            for comment_node in captures.get('comment', []):
                text = comment_node.text.decode('utf8')
                
                # Check for start marker
                if '//@@start' in text:
                    parts = text.split('//@@start')
                    if len(parts) > 1:
                        marker_name = parts[1].strip()
                        current_marker = marker_name
                        start_line = comment_node.start_point.row + 1
                
                # Check for end marker
                elif '//@@end' in text and current_marker:
                    parts = text.split('//@@end')
                    if len(parts) > 1:
                        end_marker = parts[1].strip()
                        if end_marker == current_marker:
                            end_line = comment_node.start_point.row + 1
                            markers[current_marker] = (start_line, end_line)
                            current_marker = None
                            start_line = None
        
        return markers
    
    def extract_macro_section(self, source: bytes, macro_name: str,
                             marker_name: str, macro_args: Optional[Dict[str, str]] = None) -> str:
        """
        Extract a specific marked section from within a macro.
        
        Args:
            source: Source code bytes
            macro_name: Name of the macro to find
            marker_name: Name of the marker section to extract
            macro_args: Optional dict to filter by macro arguments
            
        Returns:
            The code between the markers
        """
        info = self.find_markers_in_macro(source, macro_name, macro_args)
        
        if marker_name not in info['markers']:
            available = ', '.join(info['markers'].keys())
            raise ValueError(f"Marker '{marker_name}' not found. Available: {available}")
        
        start_line, end_line = info['markers'][marker_name]
        macro_start_line = info['macro']['line']
        
        # Convert to source-relative lines
        lines = source.decode('utf8').splitlines()
        
        # Extract the marked section
        section_lines = lines[start_line-1:end_line]
        
        # Remove the marker comments themselves
        if section_lines and '//@@start' in section_lines[0]:
            section_lines = section_lines[1:]
        if section_lines and '//@@end' in section_lines[-1]:
            section_lines = section_lines[:-1]
        
        return '\n'.join(section_lines)