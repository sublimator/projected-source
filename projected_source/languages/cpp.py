"""
C++ specific code extraction using tree-sitter.
"""

import logging
from pathlib import Path
from typing import Dict, Optional, Tuple

import tree_sitter_cpp as tscpp
from tree_sitter import Language, Node, Query, QueryCursor

from ..core.extractor import BaseExtractor
from .cpp_parser import SimpleCppParser
from .macro_finder_v3 import MacroFinder
from .macro_finder_nodes import MacroFinderWithNodes

logger = logging.getLogger(__name__)


class CppExtractor(BaseExtractor):
    """C++ specific extractor with function extraction support."""
    
    def __init__(self):
        super().__init__(Language(tscpp.language()))
        self.cpp_parser = SimpleCppParser()
        self.macro_finder = MacroFinder()
        self.macro_finder_nodes = MacroFinderWithNodes()
    
    def extract_function(self, file_path: Path, function_name: str) -> Tuple[str, int, int]:
        """
        Extract a C++ function by name using tree-sitter.
        
        Supports:
        - Regular functions: "function_name"
        - Class/struct methods: "ClassName::method_name"
        - Namespace functions: "namespace::function_name"
        - Nested namespaces: "ns1::ns2::function_name"
        - Namespace + class: "namespace::ClassName::method_name"
        - Nested classes/structs: "OuterClass::InnerClass::method"
        
        Returns:
            Tuple of (code_text, start_line, end_line)
        """
        source = file_path.read_bytes()
        
        # Use the SimpleCppParser to extract function
        func_text = self.cpp_parser.extract_function_by_name(source, function_name)
        
        if not func_text:
            raise ValueError(f"Function '{function_name}' not found in {file_path}")
        
        # Calculate line numbers
        # Find where this function appears in the source
        func_start = source.find(func_text.encode('utf8'))
        if func_start == -1:
            # Shouldn't happen, but handle it
            raise ValueError(f"Could not locate function '{function_name}' in source")
        
        # Count lines up to the start
        start_line = source[:func_start].count(b'\n') + 1
        
        # Count lines in the function
        func_lines = func_text.count('\n')
        end_line = start_line + func_lines
        
        logger.debug(f"Found function '{function_name}' at lines {start_line}-{end_line}")
        return func_text, start_line, end_line
    
    def extract_function_macro(self, file_path: Path, macro_spec: Dict) -> Tuple[str, int, int]:
        """
        Extract a function defined by a macro (like DEFINE_JS_FUNCTION).
        
        Args:
            file_path: Path to the file
            macro_spec: Dict with:
                - 'name': Macro name (required)
                - 'arg0', 'arg1', etc: Filter by argument at position
                
        Returns:
            Tuple of (code_text, start_line, end_line)
            
        Raises:
            ValueError: If no match or multiple matches found
        """
        source = file_path.read_bytes()
        
        macro_name = macro_spec.get('name')
        if not macro_name:
            raise ValueError("macro spec must include 'name'")
        
        # Find all instances of the macro
        results = self.macro_finder.find_by_name(source, macro_name)
        
        # Filter by any specified arguments
        for key, value in macro_spec.items():
            if key.startswith('arg'):
                position = int(key[3:])
                results = [r for r in results 
                          if position < len(r['arguments']) 
                          and r['arguments'][position].strip() == value]
        
        # Check we have exactly one match
        if not results:
            filters = [f"{k}={v}" for k, v in macro_spec.items() if k != 'name']
            raise ValueError(f"No {macro_name} found with {', '.join(filters)}")
        
        if len(results) > 1:
            raise ValueError(
                f"Multiple {macro_name} instances found ({len(results)} matches). "
                f"Please be more specific. Found at lines: "
                f"{', '.join(str(r['line']) for r in results[:5])}"
                f"{'...' if len(results) > 5 else ''}"
            )
        
        # Return the single match - need to get FULL text with body
        result = results[0]
        
        # Get the full text directly from the node (result['text'] is truncated)
        # We need to re-extract with full_body=True
        macro_node_start = result['start_byte']
        macro_node_end = result['end_byte']
        full_text = source[macro_node_start:macro_node_end].decode('utf8')
        
        start_line = result['line']
        # Calculate end line from the full text
        end_line = start_line + full_text.count('\n')
        
        logger.debug(f"Found {macro_name} at lines {start_line}-{end_line}")
        return full_text, start_line, end_line
    
    def extract_function_macro_marker(self, file_path: Path, macro_spec: Dict, marker: str) -> Tuple[str, int, int]:
        """
        Extract a marked section from within a function-defining macro.
        
        Args:
            file_path: Path to the file
            macro_spec: Dict with macro name and optional argument filters
            marker: Marker name to extract
            
        Returns:
            Tuple of (code_text, start_line, end_line)
        """
        source = file_path.read_bytes()
        
        macro_name = macro_spec.get('name')
        if not macro_name:
            raise ValueError("macro spec must include 'name'")
        
        # Build macro_args dict for filtering
        macro_args = {}
        for key, value in macro_spec.items():
            if key.startswith('arg'):
                macro_args[key] = value
        
        # Use the nodes version to find and extract
        section_code = self.macro_finder_nodes.extract_macro_section(
            source, macro_name, marker, macro_args if macro_args else None
        )
        
        # Get line info for the section
        info = self.macro_finder_nodes.find_markers_in_macro(
            source, macro_name, macro_args if macro_args else None
        )
        
        if marker not in info['markers']:
            raise ValueError(f"Marker '{marker}' not found in macro")
        
        start_line, end_line = info['markers'][marker]
        
        logger.debug(f"Found marker '{marker}' in {macro_name} at lines {start_line}-{end_line}")
        return section_code, start_line, end_line
    
    def find_class_or_namespace(self, file_path: Path, name: str) -> Optional[Node]:
        """
        Find a class or namespace by name.
        
        Returns:
            The node representing the class/namespace, or None if not found
        """
        root = self.parse_file(file_path)
        
        # Query for classes and namespaces
        query_text = f'''
        [
          ((class_specifier
            name: (type_identifier) @class_name (#eq? @class_name "{name}")
          ) @class)
          
          ((namespace_definition
            name: (identifier) @ns_name (#eq? @ns_name "{name}")
          ) @namespace)
        ]
        '''
        
        try:
            query = Query(self.language, query_text)
            cursor = QueryCursor(query)
            matches = cursor.matches(root)
            
            for _, captures in matches:
                # Check for class
                class_nodes = captures.get('class', [])
                if class_nodes:
                    return class_nodes[0]
                
                # Check for namespace
                ns_nodes = captures.get('namespace', [])
                if ns_nodes:
                    return ns_nodes[0]
        
        except Exception as e:
            logger.error(f"Query failed: {e}")
        
        return None