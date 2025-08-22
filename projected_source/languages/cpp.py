"""
C++ specific code extraction using tree-sitter.
"""

import logging
from pathlib import Path
from typing import Optional, Tuple

import tree_sitter_cpp as tscpp
from tree_sitter import Language, Node, Query, QueryCursor

from ..core.extractor import BaseExtractor
from .cpp_parser import SimpleCppParser

logger = logging.getLogger(__name__)


class CppExtractor(BaseExtractor):
    """C++ specific extractor with function extraction support."""
    
    def __init__(self):
        super().__init__(Language(tscpp.language()))
        self.cpp_parser = SimpleCppParser()
    
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