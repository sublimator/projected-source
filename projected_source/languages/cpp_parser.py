#!/usr/bin/env python3
"""
Simplified C++ parser using tree-sitter for extracting functions.
"""

import logging
from typing import Optional

import tree_sitter_cpp as tscpp
from tree_sitter import Language, Parser

from .extraction_result import ExtractionResult

# Configure logging
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)


class SimpleCppParser:
    """Simple parser for extracting C++ functions using tree-sitter."""

    def __init__(self):
        self.language = Language(tscpp.language())
        self.parser = Parser(self.language)

    def _find_node_by_qualified_name(self, source_code: bytes, target_name: str, node_types: list) -> Optional[object]:
        """
        Generic traversal to find a node by qualified name.

        Args:
            source_code: The C++ source code as bytes
            target_name: Qualified name to search for (e.g., "MyClass", "ns::MyClass")
            node_types: List of node types to match (e.g., ["function_definition"])

        Returns:
            The matching tree-sitter node or None if not found
        """
        tree = self.parser.parse(source_code)
        root = tree.root_node

        # Parse the target name - could be "name" or "Class::name" or "ns::Class::name"
        parts = target_name.split("::")
        target_leaf_name = parts[-1]
        qualifiers = parts[:-1] if len(parts) > 1 else []

        logger.info(f"Searching for: {target_name}")
        logger.info(f"  Target name: {target_leaf_name}")
        logger.info(f"  Qualifiers: {qualifiers}")
        logger.info(f"  Looking for node types: {node_types}")

        # Walk the tree to find the target node
        def find_node(node, context_stack=None, depth=0):
            if context_stack is None:
                context_stack = []

            indent = "  " * depth
            logger.debug(f"{indent}Node type: {node.type}, Context: {context_stack}")

            # Check for namespace definitions
            if node.type == "namespace_definition":
                # Get namespace name using the field name
                name_node = node.child_by_field_name("name")
                namespace_name = None
                if name_node:
                    # The name field could be different node types
                    namespace_name = name_node.text.decode("utf8")
                    # Remove trailing :: if present
                    if namespace_name.endswith("::"):
                        namespace_name = namespace_name.rstrip(":")

                logger.debug(f"{indent}Found namespace: {namespace_name}")

                # Recurse into namespace body with updated context
                if namespace_name and "::" in namespace_name:
                    # Split nested namespace into parts
                    new_context = context_stack + namespace_name.split("::")
                else:
                    new_context = context_stack + ([namespace_name] if namespace_name else [])

                # Get the body field directly
                body = node.child_by_field_name("body")
                if body and body.type == "declaration_list":
                    for decl in body.children:
                        result = find_node(decl, new_context, depth + 1)
                        if result:
                            return result

            # Check for class or struct definitions
            elif node.type in ["class_specifier", "struct_specifier"]:
                # Get the class/struct name
                class_name = None
                for child in node.children:
                    if child.type == "type_identifier":
                        class_name = child.text.decode("utf8")
                        break

                logger.debug(f"{indent}Found {node.type}: {class_name}")

                # Check if this is the struct/class we're looking for
                if node.type in node_types and class_name == target_leaf_name:
                    # Check if qualifiers match
                    if not qualifiers:
                        logger.info(f"{indent}  MATCH FOUND (no qualifiers required)")
                        return node
                    elif context_stack == qualifiers:
                        logger.info(f"{indent}  MATCH FOUND (exact qualifier match)")
                        return node
                    elif len(context_stack) >= len(qualifiers):
                        if context_stack[-len(qualifiers) :] == qualifiers:
                            logger.info(f"{indent}  MATCH FOUND (suffix qualifier match)")
                            return node

                # Recurse into the class/struct body with updated context
                if class_name:
                    new_context = context_stack + [class_name]
                    for child in node.children:
                        if child.type == "field_declaration_list":
                            logger.debug(f"{indent}  Searching field_declaration_list...")
                            for member in child.children:
                                logger.debug(f"{indent}    Member type: {member.type}")
                                result = find_node(member, new_context, depth + 1)
                                if result:
                                    return result

            # Check for regular function definitions
            elif node.type == "function_definition" and "function_definition" in node_types:
                logger.debug(f"{indent}Found function_definition")
                # Try to find the function name
                declarator = node.child_by_field_name("declarator")
                if declarator:
                    logger.debug(f"{indent}  Declarator type: {declarator.type}")
                    found_name = None
                    found_qualifiers = []

                    # Navigate through potential wrapper nodes
                    current = declarator
                    while current:
                        logger.debug(f"{indent}  Current node type: {current.type}")
                        if current.type == "function_declarator":
                            name_node = current.child_by_field_name("declarator")
                            if name_node:
                                logger.debug(f"{indent}    Name node type: {name_node.type}")
                                if name_node.type == "qualified_identifier":
                                    # Extract all qualifiers from qualified_identifier
                                    # This can be nested for things like utils::Helper::cleanup
                                    def extract_qualified_parts(qnode):
                                        """Recursively extract parts from nested qualified_identifier."""
                                        parts = []
                                        current = qnode
                                        while current and current.type == "qualified_identifier":
                                            # Look for direct children that are identifiers or namespace_identifiers
                                            for child in current.children:
                                                if child.type in ["namespace_identifier", "identifier"]:
                                                    parts.append(child.text.decode("utf8"))
                                                elif child.type == "qualified_identifier":
                                                    # Nested qualified_identifier, recurse
                                                    current = child
                                                    break
                                            else:
                                                # No more nested qualified_identifiers
                                                break
                                        return parts

                                    all_parts = extract_qualified_parts(name_node)
                                    if all_parts:
                                        found_name = all_parts[-1]
                                        found_qualifiers = all_parts[:-1]
                                        logger.debug(f"{indent}    Found qualified: {found_qualifiers}::{found_name}")
                                elif name_node.type == "identifier":
                                    found_name = name_node.text.decode("utf8")
                                    found_qualifiers = context_stack
                                    logger.debug(f"{indent}    Found id: {found_name} ctx={found_qualifiers}")
                                elif name_node.type == "field_identifier":
                                    # Inline class/struct method
                                    found_name = name_node.text.decode("utf8")
                                    found_qualifiers = context_stack
                                    logger.debug(f"{indent}    Found field_id: {found_name} ctx={found_qualifiers}")
                            else:
                                # Sometimes for inline methods, the name is directly a child
                                for child in current.children:
                                    if child.type == "field_identifier":
                                        found_name = child.text.decode("utf8")
                                        found_qualifiers = context_stack
                                        logger.debug(f"{indent}    field_id: {found_name}")
                                        break
                            break
                        elif current.type == "pointer_declarator":
                            current = current.child_by_field_name("declarator")
                        elif current.type == "reference_declarator":
                            current = current.child_by_field_name("declarator")
                        else:
                            logger.debug(f"{indent}    Unknown declarator type, stopping")
                            break

                    # Check if this is the function we're looking for
                    if found_name == target_leaf_name:
                        logger.info(f"{indent}  Checking: {found_name} vs {target_leaf_name}")
                        logger.info(f"{indent}  Qualifiers: {found_qualifiers} vs {qualifiers}")
                        # If no qualifiers requested, match any function with this name
                        if not qualifiers:
                            logger.info(f"{indent}  MATCH FOUND (no qualifiers required)")
                            return node
                        # Otherwise check if qualifiers match
                        elif found_qualifiers == qualifiers:
                            logger.info(f"{indent}  MATCH FOUND (exact qualifier match)")
                            return node
                        # Also check if the found qualifiers end with our requested qualifiers
                        elif len(found_qualifiers) >= len(qualifiers):
                            if found_qualifiers[-len(qualifiers) :] == qualifiers:
                                logger.info(f"{indent}  MATCH FOUND (suffix qualifier match)")
                                return node
                        logger.info(f"{indent}  No match - qualifiers don't match")

            # Check for template declarations
            elif node.type == "template_declaration":
                logger.debug(f"{indent}Found template_declaration")
                # Look for function definition inside template
                for child in node.children:
                    if child.type == "function_definition":
                        result = find_node(child, context_stack, depth + 1)
                        if result:
                            # Return the whole template declaration
                            return node
                    elif child.type in ["class_specifier", "struct_specifier"]:
                        result = find_node(child, context_stack, depth + 1)
                        if result:
                            return result

            # Recurse into children
            for child in node.children:
                result = find_node(child, context_stack, depth + 1)
                if result:
                    return result

            return None

        return find_node(root)

    def extract_function_by_name(self, source_code: bytes, function_name: str) -> Optional[ExtractionResult]:
        """
        Extract a function by name from C++ source code.
        Supports:
        - Regular functions: "function_name"
        - Class/struct methods: "ClassName::method_name"
        - Namespace functions: "namespace::function_name"
        - Nested namespaces: "ns1::ns2::function_name"
        - Namespace + class: "namespace::ClassName::method_name"

        Args:
            source_code: The C++ source code as bytes
            function_name: Name of the function to extract (can include :: for class/namespace)

        Returns:
            ExtractionResult with all the info, or None if not found
        """
        node = self._find_node_by_qualified_name(source_code, function_name, ["function_definition"])
        if node:
            return ExtractionResult(
                text=node.text.decode("utf8"),
                start_line=node.start_point.row + 1,  # 1-based for humans
                end_line=node.end_point.row + 1,
                start_column=node.start_point.column,
                end_column=node.end_point.column,
                node=node,
                node_type=node.type,
                qualified_name=function_name,
            )
        return None

    def extract_struct_or_class_by_name(self, source_code: bytes, name: str) -> Optional[ExtractionResult]:
        """
        Extract a struct or class definition by name from C++ source code.
        Supports:
        - Simple structs/classes: "MyStruct" or "MyClass"
        - Namespaced: "namespace::MyClass"
        - Nested: "OuterClass::InnerClass"
        - Multiple nesting: "ns::OuterClass::InnerStruct"

        Args:
            source_code: The C++ source code as bytes
            name: Name of the struct/class to extract (can include :: for namespace/nesting)

        Returns:
            ExtractionResult with all the info, or None if not found
        """
        node = self._find_node_by_qualified_name(source_code, name, ["class_specifier", "struct_specifier"])
        if node:
            return ExtractionResult(
                text=node.text.decode("utf8"),
                start_line=node.start_point.row + 1,  # 1-based for humans
                end_line=node.end_point.row + 1,
                start_column=node.start_point.column,
                end_column=node.end_point.column,
                node=node,
                node_type=node.type,
                qualified_name=name,
            )
        return None


if __name__ == "__main__":
    import sys

    # Enable debug logging if --debug flag is passed
    if "--debug" in sys.argv:
        logger.setLevel(logging.DEBUG)
        # Also set root logger to see tree-sitter debug info
        logging.getLogger().setLevel(logging.DEBUG)
    elif "--info" in sys.argv:
        logger.setLevel(logging.INFO)

    # Test the parser
    parser = SimpleCppParser()

    test_code = b"""
    inline std::optional<std::vector<uint8_t>>
    FromJSIntArrayOrHexString(JSContext* ctx, JSValueConst v, int max_len)
    {
        return {};
    }
    
    static JSValue js_process_binary(JSContext *ctx, JSValueConst this_val,
                                     int argc, JSValueConst *argv) 
    {
        return JS_UNDEFINED;
    }
    
    class MyClass {
    public:
        void myMethod() {
            // Do something
        }
        
        int calculate(int x, int y) {
            return x + y;
        }
    };
    
    struct MyStruct {
        void structMethod() {
            // Struct method
        }
    };
    
    // Out-of-line definition
    void MyClass::anotherMethod() {
        // Out-of-line implementation
    }
    
    namespace utils {
        void helperFunction() {
            // Namespace function
        }
        
        class Helper {
        public:
            void process() {
                // Method in namespace class
            }
        };
        
        struct Data {
            void validate() {
                // Struct method in namespace
            }
        };
    }
    
    // Out-of-line namespace class method
    void utils::Helper::cleanup() {
        // Out-of-line namespace class method
    }
    
    namespace outer {
        namespace inner {
            void deepFunction() {
                // Nested namespace function
            }
        }
    }
    
    // Nested struct/class cases
    struct OuterStruct {
        struct InnerStruct {
            void nestedMethod() {
                // Method in struct in struct
            }
        };
        
        class InnerClass {
        public:
            void anotherNested() {
                // Method in class in struct
            }
        };
    };
    
    class OuterClass {
    public:
        struct InnerStruct {
            void methodInStructInClass() {
                // Method in struct in class
            }
        };
    };
    
    // Out-of-line nested struct method
    void OuterStruct::InnerStruct::outOfLineNested() {
        // Out-of-line nested struct method
    }
    """

    # Test regular functions
    result = parser.extract_function_by_name(test_code, "FromJSIntArrayOrHexString")
    if result:
        print("Found FromJSIntArrayOrHexString:")
        print(result)
        print()

    # Test class methods
    result = parser.extract_function_by_name(test_code, "MyClass::calculate")
    if result:
        print("Found MyClass::calculate:")
        print(result)
        print()
    else:
        print("NOT FOUND: MyClass::calculate")

    # Test struct methods
    result = parser.extract_function_by_name(test_code, "MyStruct::structMethod")
    if result:
        print("Found MyStruct::structMethod:")
        print(result)
        print()

    # Test out-of-line definitions
    result = parser.extract_function_by_name(test_code, "MyClass::anotherMethod")
    if result:
        print("Found MyClass::anotherMethod (out-of-line):")
        print(result)
        print()

    # Test namespace functions
    result = parser.extract_function_by_name(test_code, "utils::helperFunction")
    if result:
        print("Found utils::helperFunction:")
        print(result)
        print()

    # Test namespace class methods
    result = parser.extract_function_by_name(test_code, "utils::Helper::process")
    if result:
        print("Found utils::Helper::process:")
        print(result)
        print()

    # Test namespace struct methods
    result = parser.extract_function_by_name(test_code, "utils::Data::validate")
    if result:
        print("Found utils::Data::validate:")
        print(result)
        print()

    # Test out-of-line namespace class method
    result = parser.extract_function_by_name(test_code, "utils::Helper::cleanup")
    if result:
        print("Found utils::Helper::cleanup (out-of-line):")
        print(result)
        print()

    # Test nested namespace function
    result = parser.extract_function_by_name(test_code, "outer::inner::deepFunction")
    if result:
        print("Found outer::inner::deepFunction:")
        print(result)
        print()

    # Test nested struct methods
    print("\n--- Testing nested struct/class methods ---")

    result = parser.extract_function_by_name(test_code, "OuterStruct::InnerStruct::nestedMethod")
    if result:
        print("Found OuterStruct::InnerStruct::nestedMethod:")
        print(result)
        print()
    else:
        print("NOT FOUND: OuterStruct::InnerStruct::nestedMethod\n")

    result = parser.extract_function_by_name(test_code, "OuterStruct::InnerClass::anotherNested")
    if result:
        print("Found OuterStruct::InnerClass::anotherNested:")
        print(result)
        print()
    else:
        print("NOT FOUND: OuterStruct::InnerClass::anotherNested\n")

    result = parser.extract_function_by_name(test_code, "OuterClass::InnerStruct::methodInStructInClass")
    if result:
        print("Found OuterClass::InnerStruct::methodInStructInClass:")
        print(result)
        print()
    else:
        print("NOT FOUND: OuterClass::InnerStruct::methodInStructInClass\n")

    result = parser.extract_function_by_name(test_code, "OuterStruct::InnerStruct::outOfLineNested")
    if result:
        print("Found OuterStruct::InnerStruct::outOfLineNested (out-of-line):")
        print(result)
        print()
    else:
        print("NOT FOUND: OuterStruct::InnerStruct::outOfLineNested\n")
