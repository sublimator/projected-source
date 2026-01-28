#!/usr/bin/env python3
"""
C++ parser using tree-sitter queries - much cleaner approach.
"""

import logging
from typing import Optional

import tree_sitter_cpp as tscpp
from tree_sitter import Language, Parser, Query, QueryCursor

from .extraction_result import ExtractionResult
from .utils import node_text

logger = logging.getLogger(__name__)


class QueryBasedCppParser:
    """C++ parser using tree-sitter queries for cleaner extraction."""

    def __init__(self):
        self.language = Language(tscpp.language())
        self.parser = Parser(self.language)

    def extract_struct_or_class_by_name(self, source_code: bytes, name: str) -> Optional[ExtractionResult]:
        """
        Extract a struct or class using tree-sitter queries.

        This is much cleaner than manual traversal!
        """
        tree = self.parser.parse(source_code)
        root = tree.root_node

        # Parse the qualified name
        parts = name.split("::")
        target_name = parts[-1]
        qualifiers = parts[:-1] if len(parts) > 1 else []

        # Build query based on whether we have qualifiers
        if not qualifiers:
            # Simple case - just find by name
            query_text = f'''
            [
              (struct_specifier
                name: (type_identifier) @name (#eq? @name "{target_name}")
              ) @result
              
              (class_specifier
                name: (type_identifier) @name (#eq? @name "{target_name}")
              ) @result
            ]
            '''
        elif len(qualifiers) == 1:
            # One level of nesting (namespace or class)
            query_text = f'''
            [
              ; Namespace case
              (namespace_definition
                name: (namespace_identifier) @ns (#eq? @ns "{qualifiers[0]}")
                body: (declaration_list
                  (struct_specifier
                    name: (type_identifier) @name (#eq? @name "{target_name}")
                  ) @result
                )
              )
              
              (namespace_definition
                name: (namespace_identifier) @ns (#eq? @ns "{qualifiers[0]}")
                body: (declaration_list
                  (class_specifier
                    name: (type_identifier) @name (#eq? @name "{target_name}")
                  ) @result
                )
              )
              
              ; Nested in class case
              (class_specifier
                name: (type_identifier) @outer (#eq? @outer "{qualifiers[0]}")
                body: (field_declaration_list
                  (access_specifier)?
                  (struct_specifier
                    name: (type_identifier) @name (#eq? @name "{target_name}")
                  ) @result
                )
              )
              
              (class_specifier
                name: (type_identifier) @outer (#eq? @outer "{qualifiers[0]}")
                body: (field_declaration_list
                  (access_specifier)?
                  (class_specifier
                    name: (type_identifier) @name (#eq? @name "{target_name}")
                  ) @result
                )
              )
              
              ; Nested in struct case
              (struct_specifier
                name: (type_identifier) @outer (#eq? @outer "{qualifiers[0]}")
                body: (field_declaration_list
                  (struct_specifier
                    name: (type_identifier) @name (#eq? @name "{target_name}")
                  ) @result
                )
              )
              
              (struct_specifier
                name: (type_identifier) @outer (#eq? @outer "{qualifiers[0]}")
                body: (field_declaration_list
                  (class_specifier
                    name: (type_identifier) @name (#eq? @name "{target_name}")
                  ) @result
                )
              )
            ]
            '''
        else:
            # Multiple levels - build a nested query
            # For now, handle the common case of namespace::class::inner
            if len(qualifiers) == 2:
                query_text = f'''
                (namespace_definition
                  name: (namespace_identifier) @ns (#eq? @ns "{qualifiers[0]}")
                  body: (declaration_list
                    [(class_specifier
                      name: (type_identifier) @outer (#eq? @outer "{qualifiers[1]}")
                      body: (field_declaration_list
                        [(struct_specifier
                          name: (type_identifier) @name (#eq? @name "{target_name}")
                        ) @result
                        
                        (class_specifier
                          name: (type_identifier) @name (#eq? @name "{target_name}")
                        ) @result]
                      )
                    )
                    
                    (struct_specifier
                      name: (type_identifier) @outer (#eq? @outer "{qualifiers[1]}")
                      body: (field_declaration_list
                        [(struct_specifier
                          name: (type_identifier) @name (#eq? @name "{target_name}")
                        ) @result
                        
                        (class_specifier
                          name: (type_identifier) @name (#eq? @name "{target_name}")
                        ) @result]
                      )
                    )]
                  )
                )
                '''
            else:
                # For deeper nesting, fall back to manual search for now
                logger.warning(f"Deep nesting ({len(qualifiers)} levels) not fully supported yet")
                return None

        try:
            query = Query(self.language, query_text)
            cursor = QueryCursor(query)
            matches = cursor.matches(root)

            for _, captures in matches:
                if "result" in captures:
                    node = captures["result"][0]
                    return ExtractionResult(
                        text=node_text(node),
                        start_line=node.start_point.row + 1,
                        end_line=node.end_point.row + 1,
                        start_column=node.start_point.column,
                        end_column=node.end_point.column,
                        node=node,
                        node_type=node.type,
                        qualified_name=name,
                    )
        except Exception as e:
            logger.error(f"Query failed: {e}")
            logger.debug(f"Query text was: {query_text}")

        return None

    def extract_function_by_name(self, source_code: bytes, name: str) -> Optional[ExtractionResult]:
        """
        Extract a function using tree-sitter queries.
        """
        tree = self.parser.parse(source_code)
        root = tree.root_node

        # Parse the qualified name
        parts = name.split("::")
        target_name = parts[-1]
        qualifiers = parts[:-1] if len(parts) > 1 else []

        if not qualifiers:
            # Simple function
            query_text = f'''
            (function_definition
              declarator: [
                (function_declarator
                  declarator: (identifier) @name (#eq? @name "{target_name}")
                )
                (pointer_declarator
                  declarator: (function_declarator
                    declarator: (identifier) @name (#eq? @name "{target_name}")
                  )
                )
              ]
            ) @result
            '''
        elif len(qualifiers) == 1:
            # Could be namespace::function or Class::method
            query_text = f'''
            [
              ; Namespace function
              (namespace_definition
                name: (namespace_identifier) @ns (#eq? @ns "{qualifiers[0]}")
                body: (declaration_list
                  (function_definition
                    declarator: (function_declarator
                      declarator: (identifier) @name (#eq? @name "{target_name}")
                    )
                  ) @result
                )
              )
              
              ; Class method (inline definition)
              (class_specifier
                name: (type_identifier) @class (#eq? @class "{qualifiers[0]}")
                body: (field_declaration_list
                  (function_definition
                    declarator: (function_declarator
                      declarator: (field_identifier) @name (#eq? @name "{target_name}")
                    )
                  ) @result
                )
              )
              
              ; Out-of-line class method definition
              (function_definition
                declarator: (function_declarator
                  declarator: (qualified_identifier
                    scope: (namespace_identifier) @class (#eq? @class "{qualifiers[0]}")
                    name: (identifier) @name (#eq? @name "{target_name}")
                  )
                )
              ) @result
            ]
            '''
        else:
            # Handle nested cases
            logger.warning("Multi-level function qualifiers not fully implemented yet")
            return None

        try:
            query = Query(self.language, query_text)
            cursor = QueryCursor(query)
            matches = cursor.matches(root)

            for _, captures in matches:
                if "result" in captures:
                    node = captures["result"][0]
                    return ExtractionResult(
                        text=node_text(node),
                        start_line=node.start_point.row + 1,
                        end_line=node.end_point.row + 1,
                        start_column=node.start_point.column,
                        end_column=node.end_point.column,
                        node=node,
                        node_type=node.type,
                        qualified_name=name,
                    )
        except Exception as e:
            logger.error(f"Query failed: {e}")
            logger.debug(f"Query text was: {query_text}")

        return None
