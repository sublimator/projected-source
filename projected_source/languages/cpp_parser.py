#!/usr/bin/env python3
"""
Simplified C++ parser using tree-sitter for extracting functions.
"""

import logging
from typing import List, Optional, Tuple

import tree_sitter_cpp as tscpp
from tree_sitter import Language, Node, Parser

from .extraction_result import ExtractionResult
from .utils import node_text


def _node_to_result(node: Node, qualified_name: str) -> ExtractionResult:
    """Helper to create ExtractionResult from a tree-sitter Node."""
    text = node.text.decode("utf8") if node.text else ""
    return ExtractionResult(
        text=text,
        start_line=node.start_point.row + 1,
        end_line=node.end_point.row + 1,
        start_column=node.start_point.column,
        end_column=node.end_point.column,
        node=node,
        node_type=node.type,
        qualified_name=qualified_name,
    )


# Configure logging
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)


class SimpleCppParser:
    """Simple parser for extracting C++ functions using tree-sitter."""

    def __init__(self):
        self.language = Language(tscpp.language())
        self.parser = Parser(self.language)

    def _find_node_by_qualified_name(self, source_code: bytes, target_name: str, node_types: list) -> Optional[Node]:
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
                    namespace_name = node_text(name_node)
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

            # Check for class, struct, or enum definitions
            elif node.type in ["class_specifier", "struct_specifier", "enum_specifier"]:
                # Get the class/struct/enum name
                class_name = None
                for child in node.children:
                    if child.type == "type_identifier":
                        class_name = node_text(child)
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

            # Check for variable/constant declarations
            elif node.type == "declaration" and "declaration" in node_types:
                # Find the variable name from init_declarator
                var_name = None
                for child in node.children:
                    if child.type == "init_declarator":
                        # Look for identifier in array_declarator, pointer_declarator, or direct
                        for subchild in child.children:
                            if subchild.type == "identifier":
                                var_name = subchild.text.decode("utf8") if subchild.text else None
                                break
                            elif subchild.type in ["array_declarator", "pointer_declarator"]:
                                for leaf in subchild.children:
                                    if leaf.type == "identifier":
                                        var_name = leaf.text.decode("utf8") if leaf.text else None
                                        break
                                if var_name:
                                    break
                        break

                logger.debug(f"{indent}Found declaration: {var_name}")

                if var_name == target_leaf_name:
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

            # Check for regular function definitions
            elif node.type == "function_definition" and "function_definition" in node_types:
                logger.debug(f"{indent}Found function_definition")
                # Try to find the function name
                declarator = node.child_by_field_name("declarator")
                if declarator:
                    logger.debug(f"{indent}  Declarator type: {declarator.type}")
                    found_name = None
                    found_qualifiers = []

                    def extract_operator_name(op_node):
                        """Extract operator name like 'operator+', 'operator==', 'operator[]'."""
                        # operator_name contains 'operator' keyword and the symbol(s)
                        parts = []
                        for child in op_node.children:
                            if child.text:
                                parts.append(node_text(child))
                        return "".join(parts)

                    def extract_template_type_name(tt_node):
                        """Extract name from template_type like 'Container<T>'."""
                        type_id = None
                        template_args = None
                        for child in tt_node.children:
                            if child.type == "type_identifier":
                                type_id = node_text(child)
                            elif child.type == "template_argument_list":
                                template_args = child.text.decode("utf8")
                        if type_id and template_args:
                            return f"{type_id}{template_args}"
                        return type_id

                    def extract_qualified_parts(qnode):
                        """Recursively extract parts from qualified_identifier.

                        Handles:
                        - Simple identifiers: MyClass::method
                        - Template types: Container<T>::method
                        - Operator names: MyClass::operator+
                        """
                        parts = []
                        current_node = qnode
                        while current_node and current_node.type == "qualified_identifier":
                            found_nested = False
                            for child in current_node.children:
                                if child.type in ["namespace_identifier", "identifier"]:
                                    parts.append(node_text(child))
                                elif child.type == "template_type":
                                    # Handle Container<T> in Container<T>::method
                                    parts.append(extract_template_type_name(child))
                                elif child.type == "operator_name":
                                    # Handle MyClass::operator+
                                    parts.append(extract_operator_name(child))
                                elif child.type == "qualified_identifier":
                                    # Nested qualified_identifier, continue loop
                                    current_node = child
                                    found_nested = True
                                    break
                            if not found_nested:
                                break
                        return parts

                    # Navigate through potential wrapper nodes
                    current = declarator
                    while current:
                        logger.debug(f"{indent}  Current node type: {current.type}")
                        if current.type == "function_declarator":
                            name_node = current.child_by_field_name("declarator")
                            if name_node:
                                logger.debug(f"{indent}    Name node type: {name_node.type}")
                                if name_node.type == "qualified_identifier":
                                    all_parts = extract_qualified_parts(name_node)
                                    if all_parts:
                                        found_name = all_parts[-1]
                                        found_qualifiers = all_parts[:-1]
                                        logger.debug(f"{indent}    Found qualified: {found_qualifiers}::{found_name}")
                                elif name_node.type == "identifier":
                                    found_name = node_text(name_node)
                                    found_qualifiers = context_stack
                                    logger.debug(f"{indent}    Found id: {found_name} ctx={found_qualifiers}")
                                elif name_node.type == "field_identifier":
                                    # Inline class/struct method
                                    found_name = node_text(name_node)
                                    found_qualifiers = context_stack
                                    logger.debug(f"{indent}    Found field_id: {found_name} ctx={found_qualifiers}")
                                elif name_node.type == "operator_name":
                                    # Operator overload like operator+
                                    found_name = extract_operator_name(name_node)
                                    found_qualifiers = context_stack
                                    logger.debug(f"{indent}    Found operator: {found_name} ctx={found_qualifiers}")
                                elif name_node.type == "template_function":
                                    # Template specialization like templateAdd<int>
                                    for child in name_node.children:
                                        if child.type == "identifier":
                                            base_name = node_text(child)
                                        elif child.type == "template_argument_list":
                                            template_args = node_text(child)
                                    # Store both forms for matching
                                    found_name = f"{base_name}{template_args}"
                                    found_qualifiers = context_stack
                                    logger.debug(f"{indent}    Found template_function: {found_name}")
                            else:
                                # Sometimes for inline methods, the name is directly a child
                                for child in current.children:
                                    if child.type == "field_identifier":
                                        found_name = node_text(child)
                                        found_qualifiers = context_stack
                                        logger.debug(f"{indent}    field_id: {found_name}")
                                        break
                                    elif child.type == "operator_name":
                                        found_name = extract_operator_name(child)
                                        found_qualifiers = context_stack
                                        logger.debug(f"{indent}    operator: {found_name}")
                                        break
                            break
                        elif current.type == "pointer_declarator":
                            # pointer_declarator has declarator as a named field
                            current = current.child_by_field_name("declarator")
                        elif current.type == "reference_declarator":
                            # reference_declarator has function_declarator as unnamed child
                            func_decl = None
                            for child in current.children:
                                if child.type == "function_declarator":
                                    func_decl = child
                                    break
                            current = func_decl
                        else:
                            logger.debug(f"{indent}    Unknown declarator type, stopping")
                            break

                    # Check if this is the function we're looking for
                    # For template functions, also match the base name without template args
                    name_matches = found_name == target_leaf_name
                    if not name_matches and found_name and "<" in found_name:
                        # Try matching base name for template functions
                        base_found = found_name.split("<")[0]
                        name_matches = base_found == target_leaf_name

                    if name_matches:
                        logger.info(f"{indent}  Checking: {found_name} vs {target_leaf_name}")
                        logger.info(f"{indent}  Qualifiers: {found_qualifiers} vs {qualifiers}")

                        def qualifiers_match(found_quals, target_quals):
                            """Check if qualifier lists match, handling template types.

                            Container<T> matches Container<T> (exact)
                            Container<T> matches Container (base name)
                            """
                            if len(found_quals) != len(target_quals):
                                return False
                            for found_q, target_q in zip(found_quals, target_quals):
                                if found_q == target_q:
                                    continue
                                # Try matching base name for templates
                                found_base = found_q.split("<")[0] if "<" in found_q else found_q
                                target_base = target_q.split("<")[0] if "<" in target_q else target_q
                                if found_base != target_base:
                                    return False
                            return True

                        # If no qualifiers requested, match any function with this name
                        if not qualifiers:
                            logger.info(f"{indent}  MATCH FOUND (no qualifiers required)")
                            return node
                        # Otherwise check if qualifiers match (with template handling)
                        elif qualifiers_match(found_qualifiers, qualifiers):
                            logger.info(f"{indent}  MATCH FOUND (qualifier match)")
                            return node
                        # Also check if the found qualifiers end with our requested qualifiers
                        elif len(found_qualifiers) >= len(qualifiers):
                            suffix = found_qualifiers[-len(qualifiers) :]
                            if qualifiers_match(suffix, qualifiers):
                                logger.info(f"{indent}  MATCH FOUND (suffix qualifier match)")
                                return node
                        logger.info(f"{indent}  No match - qualifiers don't match")

            # Check for field declarations (class method declarations in headers)
            elif node.type == "field_declaration" and "function_definition" in node_types:
                # field_declaration can contain a function_declarator for method declarations
                declarator = node.child_by_field_name("declarator")
                if declarator and declarator.type == "function_declarator":
                    found_name, found_qualifiers = self._extract_function_name_and_qualifiers(declarator, context_stack)
                    if found_name == target_leaf_name:
                        if not qualifiers:
                            logger.info(f"{indent}  MATCH FOUND (no qualifiers required)")
                            return node
                        elif self._qualifiers_match(found_qualifiers, qualifiers):
                            logger.info(f"{indent}  MATCH FOUND (qualifier match)")
                            return node

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
                    elif child.type in ["class_specifier", "struct_specifier", "enum_specifier"]:
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

    def _find_all_nodes_by_qualified_name(self, source_code: bytes, target_name: str, node_types: list) -> List[Node]:
        """
        Find ALL nodes matching a qualified name (for overloaded functions).

        Args:
            source_code: The C++ source code as bytes
            target_name: Qualified name to search for
            node_types: List of node types to match

        Returns:
            List of matching tree-sitter nodes
        """
        tree = self.parser.parse(source_code)
        root = tree.root_node

        parts = target_name.split("::")
        target_leaf_name = parts[-1]
        qualifiers = parts[:-1] if len(parts) > 1 else []

        results: List[Node] = []

        def collect_nodes(node, context_stack=None, depth=0):
            if context_stack is None:
                context_stack = []

            # Check for namespace definitions
            if node.type == "namespace_definition":
                name_node = node.child_by_field_name("name")
                namespace_name = None
                if name_node:
                    namespace_name = name_node.text.decode("utf8")
                    if namespace_name.endswith("::"):
                        namespace_name = namespace_name.rstrip(":")

                if namespace_name and "::" in namespace_name:
                    new_context = context_stack + namespace_name.split("::")
                else:
                    new_context = context_stack + ([namespace_name] if namespace_name else [])

                body = node.child_by_field_name("body")
                if body and body.type == "declaration_list":
                    for decl in body.children:
                        collect_nodes(decl, new_context, depth + 1)
                # Don't recurse via generic recursion - we already handled body with proper context
                return

            # Check for class/struct definitions
            elif node.type in ["class_specifier", "struct_specifier"]:
                class_name = None
                for child in node.children:
                    if child.type == "type_identifier":
                        class_name = node_text(child)
                        break

                if class_name:
                    new_context = context_stack + [class_name]
                    for child in node.children:
                        if child.type == "field_declaration_list":
                            for member in child.children:
                                collect_nodes(member, new_context, depth + 1)
                # Don't recurse into class children via generic recursion -
                # we already handled members with proper class context above
                return

            # Check for function definitions
            elif node.type == "function_definition" and "function_definition" in node_types:
                declarator = node.child_by_field_name("declarator")
                if declarator:
                    found_name, found_qualifiers = self._extract_function_name_and_qualifiers(declarator, context_stack)

                    if found_name == target_leaf_name:
                        if self._qualifiers_match(found_qualifiers, qualifiers):
                            results.append(node)

            # Check for field declarations (class method declarations in headers)
            elif node.type == "field_declaration" and "function_definition" in node_types:
                # field_declaration can contain a function_declarator for method declarations
                declarator = node.child_by_field_name("declarator")
                if declarator and declarator.type == "function_declarator":
                    found_name, found_qualifiers = self._extract_function_name_and_qualifiers(declarator, context_stack)

                    if found_name == target_leaf_name:
                        if self._qualifiers_match(found_qualifiers, qualifiers):
                            results.append(node)

            # Check for template declarations
            elif node.type == "template_declaration":
                for child in node.children:
                    if child.type == "function_definition":
                        declarator = child.child_by_field_name("declarator")
                        if declarator:
                            found_name, found_qualifiers = self._extract_function_name_and_qualifiers(
                                declarator, context_stack
                            )
                            # Match base name for template functions
                            base_found = found_name.split("<")[0] if "<" in found_name else found_name
                            if base_found == target_leaf_name or found_name == target_leaf_name:
                                if self._qualifiers_match(found_qualifiers, qualifiers):
                                    results.append(node)
                # Don't recurse into template children - we already handled the function
                return

            # Recurse into children
            for child in node.children:
                collect_nodes(child, context_stack, depth + 1)

        collect_nodes(root)
        return results

    def _extract_function_name_and_qualifiers(
        self, declarator: Node, context_stack: List[str]
    ) -> Tuple[str, List[str]]:
        """Extract function name and qualifiers from a declarator node."""
        found_name = ""
        found_qualifiers = []

        def extract_operator_name(op_node):
            parts = []
            for child in op_node.children:
                if child.text:
                    parts.append(node_text(child))
            return "".join(parts)

        def extract_qualified_parts(qnode):
            parts = []
            current_node = qnode
            while current_node and current_node.type == "qualified_identifier":
                found_nested = False
                for child in current_node.children:
                    if child.type in ["namespace_identifier", "identifier"]:
                        parts.append(node_text(child))
                    elif child.type == "template_type":
                        type_id = None
                        for tc in child.children:
                            if tc.type == "type_identifier":
                                type_id = tc.text.decode("utf8")
                        if type_id:
                            parts.append(type_id)
                    elif child.type == "operator_name":
                        parts.append(extract_operator_name(child))
                    elif child.type == "qualified_identifier":
                        current_node = child
                        found_nested = True
                        break
                if not found_nested:
                    break
            return parts

        current = declarator
        while current:
            if current.type == "function_declarator":
                name_node = current.child_by_field_name("declarator")
                if name_node:
                    if name_node.type == "qualified_identifier":
                        all_parts = extract_qualified_parts(name_node)
                        if all_parts:
                            found_name = all_parts[-1]
                            found_qualifiers = all_parts[:-1]
                    elif name_node.type == "identifier":
                        found_name = node_text(name_node)
                        found_qualifiers = context_stack
                    elif name_node.type == "field_identifier":
                        found_name = node_text(name_node)
                        found_qualifiers = context_stack
                    elif name_node.type == "operator_name":
                        found_name = extract_operator_name(name_node)
                        found_qualifiers = context_stack
                break
            elif current.type == "pointer_declarator":
                current = current.child_by_field_name("declarator")
            elif current.type == "reference_declarator":
                func_decl = None
                for child in current.children:
                    if child.type == "function_declarator":
                        func_decl = child
                        break
                current = func_decl
            else:
                break

        return found_name, found_qualifiers

    def _qualifiers_match(self, found: List[str], target: List[str]) -> bool:
        """Check if qualifier lists match."""
        if not target:
            return True
        if found == target:
            return True
        if len(found) >= len(target) and found[-len(target) :] == target:
            return True
        return False

    def _extract_parameter_signature(self, node: Node) -> str:
        """
        Extract parameter types from a function definition or field_declaration node.

        Returns a string like "int, std::string const&, TMProposeSet"
        containing the parameter types (without names).
        """
        # Handle template_declaration by descending to inner function_definition
        target_node = node
        if node.type == "template_declaration":
            for child in node.children:
                if child.type == "function_definition":
                    target_node = child
                    break

        # Handle field_declaration (class method declarations in headers)
        # These don't have a "declarator" field - function_declarator is a direct child
        if target_node.type == "field_declaration":
            for child in target_node.children:
                if child.type == "function_declarator":
                    params_node = child.child_by_field_name("parameters")
                    if params_node:
                        return node_text(params_node)
            return ""

        declarator = target_node.child_by_field_name("declarator")
        if not declarator:
            return ""

        # Navigate to function_declarator
        current = declarator
        while current and current.type != "function_declarator":
            if current.type == "pointer_declarator":
                current = current.child_by_field_name("declarator")
            elif current.type == "reference_declarator":
                for child in current.children:
                    if child.type == "function_declarator":
                        current = child
                        break
                else:
                    break
            else:
                break

        if not current or current.type != "function_declarator":
            return ""

        params_node = current.child_by_field_name("parameters")
        if not params_node:
            return ""

        # Extract the full parameter list text
        return node_text(params_node)

    def extract_function_by_name(
        self, source_code: bytes, function_name: str, signature: str = None
    ) -> Optional[ExtractionResult]:
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
            signature: Optional string to match against parameter types for overload disambiguation

        Returns:
            ExtractionResult with all the info, or None if not found
        """
        if signature is None:
            # Original behavior - find first match
            node = self._find_node_by_qualified_name(source_code, function_name, ["function_definition"])
            return _node_to_result(node, function_name) if node else None

        # Find all overloads and filter by signature
        nodes = self._find_all_nodes_by_qualified_name(source_code, function_name, ["function_definition"])

        if not nodes:
            return None

        # Filter by signature
        matching = []
        for node in nodes:
            param_sig = self._extract_parameter_signature(node)
            if signature in param_sig:
                matching.append(node)

        if not matching:
            # No match - provide helpful error info
            available = [self._extract_parameter_signature(n) for n in nodes]
            logger.warning(f"No overload of '{function_name}' matches signature '{signature}'. Available: {available}")
            return None

        if len(matching) > 1:
            # Multiple matches - need more specific signature
            sigs = [self._extract_parameter_signature(n) for n in matching]
            logger.warning(f"Multiple overloads of '{function_name}' match signature '{signature}': {sigs}")

        return _node_to_result(matching[0], function_name)

    def extract_struct_or_class_by_name(self, source_code: bytes, name: str) -> Optional[ExtractionResult]:
        """
        Extract a struct, class, enum, or variable declaration by name from C++ source code.
        Supports:
        - Simple structs/classes/enums: "MyStruct", "MyClass", "MyEnum"
        - Variable declarations: "myArray", "myConstant"
        - Namespaced: "namespace::MyClass"
        - Nested: "OuterClass::InnerClass"
        - Multiple nesting: "ns::OuterClass::InnerStruct"

        Args:
            source_code: The C++ source code as bytes
            name: Name of the struct/class/enum/variable to extract (can include :: for namespace/nesting)

        Returns:
            ExtractionResult with all the info, or None if not found
        """
        node = self._find_node_by_qualified_name(
            source_code, name, ["class_specifier", "struct_specifier", "enum_specifier", "declaration"]
        )
        return _node_to_result(node, name) if node else None


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
