#!/usr/bin/env python3
"""
Simplified C++ parser using tree-sitter for extracting functions.

Pure AST helpers (name extraction, qualifier matching, node conversion) live
in ``cpp_ast.py``; this module holds the traversal and the public extraction
API.
"""

import logging
from typing import List, Optional

import tree_sitter_cpp as tscpp
from tree_sitter import Language, Node, Parser

from .cpp_ast import (
    extract_function_name_and_qualifiers,
    extract_operator_name,
    extract_qualified_parts,
    find_following_body,
    node_to_result,
    qualifiers_match,
    unwrap_to_function_declarator,
)
from .extraction_result import ExtractionResult
from .utils import node_text

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

        # Forward-declaration fallback: if the only match is a bare
        # ``class Foo;`` / ``struct Foo;`` / ``enum Foo;`` (no body), remember it
        # but keep searching for a real definition. Returned only if nothing
        # with a body matched. See FINDING 2 in the bug list.
        forward_decl_fallback: List[Node] = []

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
                # Do NOT fall through to the generic recursion below — the
                # body was already searched with the correct context.
                return None

            # Check for class, struct, or enum definitions
            elif node.type in ["class_specifier", "struct_specifier", "enum_specifier"]:
                # Get the class/struct/enum name
                class_name = None
                class_qualifiers = []
                has_body = False
                for child in node.children:
                    if class_name is None:
                        if child.type == "type_identifier":
                            class_name = node_text(child)
                        elif child.type == "qualified_identifier":
                            # Handle class HttpServer::Impl pattern
                            parts = []
                            current_qi = child
                            while current_qi and current_qi.type == "qualified_identifier":
                                found_nested = False
                                for qi_child in current_qi.children:
                                    if qi_child.type in ["namespace_identifier", "identifier"]:
                                        parts.append(node_text(qi_child))
                                    elif qi_child.type == "type_identifier":
                                        parts.append(node_text(qi_child))
                                    elif qi_child.type == "qualified_identifier":
                                        current_qi = qi_child
                                        found_nested = True
                                        break
                                if not found_nested:
                                    break
                            if parts:
                                class_name = parts[-1]
                                class_qualifiers = parts[:-1]
                    if child.type in ("field_declaration_list", "enumerator_list"):
                        has_body = True

                logger.debug(f"{indent}Found {node.type}: {class_name} has_body={has_body}")

                # Check if this is the struct/class we're looking for
                full_context = context_stack + class_qualifiers
                if node.type in node_types and class_name == target_leaf_name:
                    qualifier_ok = (
                        not qualifiers
                        or full_context == qualifiers
                        or (
                            len(full_context) >= len(qualifiers)
                            and full_context[-len(qualifiers) :] == qualifiers
                        )
                    )
                    if qualifier_ok:
                        if has_body:
                            logger.info(f"{indent}  MATCH FOUND (with body)")
                            return node
                        else:
                            # Forward declaration: remember as fallback but
                            # keep searching for the real definition.
                            if not forward_decl_fallback:
                                forward_decl_fallback.append(node)
                            logger.debug(
                                f"{indent}  Forward-decl match recorded; continuing search"
                            )

                # Recurse into the class/struct body with updated context
                if class_name and has_body:
                    new_context = full_context + [class_name]
                    for child in node.children:
                        if child.type == "field_declaration_list":
                            logger.debug(f"{indent}  Searching field_declaration_list...")
                            for member in child.children:
                                logger.debug(f"{indent}    Member type: {member.type}")
                                result = find_node(member, new_context, depth + 1)
                                if result:
                                    return result
                # Do NOT fall through to the generic recursion below — we
                # already searched the body with the correct context.
                return None

            # Check for extern function declarations (declaration with function_declarator)
            elif node.type == "declaration" and "function_definition" in node_types:
                for child in node.children:
                    # tree-sitter-cpp wraps function_declarator inside
                    # pointer_declarator/reference_declarator when the return
                    # type is a pointer/reference — accept both.
                    if child.type in ("function_declarator", "pointer_declarator", "reference_declarator"):
                        if unwrap_to_function_declarator(child) is None:
                            continue
                        found_name, found_qualifiers = extract_function_name_and_qualifiers(child, context_stack)
                        if found_name and found_name == target_leaf_name:
                            if not qualifiers:
                                return node
                            elif qualifiers_match(found_qualifiers, qualifiers):
                                return node
                        break

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

                        def strict_qualifiers_match(found_quals, target_quals):
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
                        elif strict_qualifiers_match(found_qualifiers, qualifiers):
                            logger.info(f"{indent}  MATCH FOUND (qualifier match)")
                            return node
                        # Also check if the found qualifiers end with our requested qualifiers
                        elif len(found_qualifiers) >= len(qualifiers):
                            suffix = found_qualifiers[-len(qualifiers) :]
                            if strict_qualifiers_match(suffix, qualifiers):
                                logger.info(f"{indent}  MATCH FOUND (suffix qualifier match)")
                                return node
                        logger.info(f"{indent}  No match - qualifiers don't match")

            # Check for field declarations (class method declarations in headers)
            elif node.type == "field_declaration" and "function_definition" in node_types:
                # field_declaration can contain a function_declarator for method declarations,
                # possibly wrapped in pointer_declarator/reference_declarator when the return
                # type is a pointer/reference (e.g. ``int* method()``, ``Foo& method()``).
                declarator = node.child_by_field_name("declarator")
                if declarator and unwrap_to_function_declarator(declarator) is not None:
                    found_name, found_qualifiers = extract_function_name_and_qualifiers(declarator, context_stack)
                    if found_name and found_name == target_leaf_name:
                        if not qualifiers:
                            logger.info(f"{indent}  MATCH FOUND (no qualifiers required)")
                            return node
                        elif qualifiers_match(found_qualifiers, qualifiers):
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

        result = find_node(root)
        if result is not None:
            return result
        # Fall back to a forward declaration only when no full definition was found.
        return forward_decl_fallback[0] if forward_decl_fallback else None

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
                class_qualifiers = []
                for child in node.children:
                    if child.type == "type_identifier":
                        class_name = node_text(child)
                        break
                    elif child.type == "qualified_identifier":
                        parts = []
                        current_qi = child
                        while current_qi and current_qi.type == "qualified_identifier":
                            found_nested = False
                            for qi_child in current_qi.children:
                                if qi_child.type in ["namespace_identifier", "identifier"]:
                                    parts.append(node_text(qi_child))
                                elif qi_child.type == "type_identifier":
                                    parts.append(node_text(qi_child))
                                elif qi_child.type == "qualified_identifier":
                                    current_qi = qi_child
                                    found_nested = True
                                    break
                            if not found_nested:
                                break
                        if parts:
                            class_name = parts[-1]
                            class_qualifiers = parts[:-1]
                        break

                if class_name:
                    new_context = context_stack + class_qualifiers + [class_name]
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
                    found_name, found_qualifiers = extract_function_name_and_qualifiers(declarator, context_stack)

                    if found_name == target_leaf_name:
                        if qualifiers_match(found_qualifiers, qualifiers):
                            results.append(node)

            # Check for extern function declarations (declaration with function_declarator)
            elif node.type == "declaration" and "function_definition" in node_types:
                for child in node.children:
                    # Accept function_declarator wrapped in pointer/reference declarators
                    # for pointer/reference return types.
                    if child.type in ("function_declarator", "pointer_declarator", "reference_declarator"):
                        if unwrap_to_function_declarator(child) is None:
                            continue
                        found_name, found_qualifiers = extract_function_name_and_qualifiers(child, context_stack)
                        if found_name and found_name == target_leaf_name:
                            if qualifiers_match(found_qualifiers, qualifiers):
                                results.append(node)
                        break

            # Check for field declarations (class method declarations in headers)
            elif node.type == "field_declaration" and "function_definition" in node_types:
                # field_declaration can contain a function_declarator for method declarations,
                # possibly wrapped in pointer/reference declarators for pointer/reference returns.
                declarator = node.child_by_field_name("declarator")
                if declarator and unwrap_to_function_declarator(declarator) is not None:
                    found_name, found_qualifiers = extract_function_name_and_qualifiers(declarator, context_stack)

                    if found_name and found_name == target_leaf_name:
                        if qualifiers_match(found_qualifiers, qualifiers):
                            results.append(node)

            # Check for template declarations
            elif node.type == "template_declaration":
                for child in node.children:
                    if child.type == "function_definition":
                        declarator = child.child_by_field_name("declarator")
                        if declarator:
                            found_name, found_qualifiers = extract_function_name_and_qualifiers(
                                declarator, context_stack
                            )
                            # Match base name for template functions (e.g. templateAdd<int> -> templateAdd)
                            base_found = found_name.split("<")[0] if "<" in found_name else found_name
                            base_target = (
                                target_leaf_name.split("<")[0] if "<" in target_leaf_name else target_leaf_name
                            )
                            if base_found == base_target or found_name == target_leaf_name:
                                if qualifiers_match(found_qualifiers, qualifiers):
                                    results.append(node)
                    elif child.type in ["class_specifier", "struct_specifier"]:
                        # Template class - recurse into its members with class context
                        class_name = None
                        for cc in child.children:
                            if cc.type == "type_identifier":
                                class_name = node_text(cc)
                                break
                        if class_name:
                            new_context = context_stack + [class_name]
                            for cc in child.children:
                                if cc.type == "field_declaration_list":
                                    for member in cc.children:
                                        collect_nodes(member, new_context, depth + 1)
                # Don't recurse into template children - we already handled them
                return

            # Recurse into children
            for child in node.children:
                collect_nodes(child, context_stack, depth + 1)

        collect_nodes(root)
        return results

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

        # Handle field_declaration and declaration (extern/forward declarations).
        # function_declarator may be a direct child OR wrapped in pointer/reference
        # declarators when the return type is a pointer/reference.
        if target_node.type in ("field_declaration", "declaration"):
            for child in target_node.children:
                func_decl = unwrap_to_function_declarator(child)
                if func_decl is not None:
                    params_node = func_decl.child_by_field_name("parameters")
                    if params_node:
                        return node_text(params_node)
            return ""

        declarator = target_node.child_by_field_name("declarator")
        if not declarator:
            return ""

        # Navigate to function_declarator
        current: Optional[Node] = declarator
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

        When both a declaration and definition exist, prefers the definition
        (the one with a body).

        Args:
            source_code: The C++ source code as bytes
            function_name: Name of the function to extract (can include :: for class/namespace)
            signature: Optional string to match against parameter types for overload disambiguation

        Returns:
            ExtractionResult with all the info, or None if not found
        """
        # Find all matches (definitions + declarations)
        nodes = self._find_all_nodes_by_qualified_name(source_code, function_name, ["function_definition"])

        if not nodes:
            return None

        # Filter by signature BEFORE the prefer-definitions dedup below. A
        # declaration-only overload that uniquely matches the requested
        # signature must not be discarded just because some *other* overload
        # happens to have a body — e.g. a defaulted ``Foo(Foo&&) = default``
        # (a function_definition) competing with a declared-but-not-defined
        # ``Foo(clock_type const&, ...)`` (a declaration). Deduping first would
        # drop the matching declaration and make signature= return nothing.
        if signature is not None:
            # Filter by signature
            matching = []
            for node in nodes:
                param_sig = self._extract_parameter_signature(node)
                if signature in param_sig:
                    matching.append(node)

            if not matching:
                available = [self._extract_parameter_signature(n) for n in nodes]
                logger.warning(
                    f"No overload of '{function_name}' matches signature '{signature}'. Available: {available}"
                )
                return None

            if len(matching) > 1:
                sigs = [self._extract_parameter_signature(n) for n in matching]
                logger.warning(f"Multiple overloads of '{function_name}' match signature '{signature}': {sigs}")

            nodes = matching

        # Deduplicate: prefer definitions over declarations (declaration in .h + definition in .cpp)
        definitions = [n for n in nodes if n.type in ("function_definition", "template_declaration")]
        if definitions:
            nodes = definitions

        # If target has template args (e.g. templateAdd<int>), prefer exact specialization
        # over generic template match
        if "<" in function_name:
            target_leaf = function_name.split("::")[-1]
            exact = [n for n in nodes if target_leaf in node_text(n)]
            if exact:
                nodes = exact

        # Return the first (best) match
        if nodes and nodes[0].type in ("function_definition", "template_declaration"):
            return node_to_result(nodes[0], function_name)

        # Handle macro-attributed functions where tree-sitter splits the signature
        # and body into: declaration + expression_statement + compound_statement
        for node in nodes:
            if node.type == "declaration":
                body_node = find_following_body(node)
                if body_node:
                    # Combine declaration and body into a single result
                    text = source_code[node.start_byte : body_node.end_byte].decode("utf8")
                    return ExtractionResult(
                        text=text,
                        start_line=node.start_point.row + 1,
                        end_line=body_node.end_point.row + 1,
                        start_column=node.start_point.column,
                        end_column=body_node.end_point.column,
                        node=None,  # Synthetic — spans multiple nodes
                        node_type="function_definition",
                        qualified_name=function_name,
                    )

        # Fall back to declaration (e.g., header-only code, extern declarations)
        return node_to_result(nodes[0], function_name)

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
        return node_to_result(node, name) if node else None

    def list_symbols(self, source_code: bytes) -> List[dict]:
        """
        List all extractable symbols in C++ source code.

        Returns a list of dicts with:
            - name: qualified name to use in code() calls
            - kind: human-readable kind (function, class, struct, enum, variable)
            - param: the code() parameter to use (function, struct, var)
            - line: 1-based start line number
            - signature: parameter signature (functions only)
        """
        tree = self.parser.parse(source_code)
        root = tree.root_node
        symbols = []

        def collect(node, context_stack=None):
            if context_stack is None:
                context_stack = []

            if node.type == "namespace_definition":
                name_node = node.child_by_field_name("name")
                ns_name = None
                if name_node:
                    ns_name = node_text(name_node)
                    if ns_name.endswith("::"):
                        ns_name = ns_name.rstrip(":")
                if ns_name and "::" in ns_name:
                    new_context = context_stack + ns_name.split("::")
                else:
                    new_context = context_stack + ([ns_name] if ns_name else [])
                body = node.child_by_field_name("body")
                if body and body.type == "declaration_list":
                    for decl in body.children:
                        collect(decl, new_context)
                return

            if node.type in ["class_specifier", "struct_specifier", "enum_specifier"]:
                type_name = None
                type_qualifiers = []
                has_body = False
                for child in node.children:
                    if child.type == "type_identifier":
                        type_name = node_text(child)
                    elif child.type == "qualified_identifier":
                        parts = []
                        current_qi = child
                        while current_qi and current_qi.type == "qualified_identifier":
                            found_nested = False
                            for qi_child in current_qi.children:
                                if qi_child.type in ["namespace_identifier", "identifier"]:
                                    parts.append(node_text(qi_child))
                                elif qi_child.type == "type_identifier":
                                    parts.append(node_text(qi_child))
                                elif qi_child.type == "qualified_identifier":
                                    current_qi = qi_child
                                    found_nested = True
                                    break
                            if not found_nested:
                                break
                        if parts:
                            type_name = parts[-1]
                            type_qualifiers = parts[:-1]
                    if child.type in ["field_declaration_list", "enumerator_list"]:
                        has_body = True
                if type_name and has_body:
                    kind_map = {
                        "class_specifier": "class",
                        "struct_specifier": "struct",
                        "enum_specifier": "enum",
                    }
                    qualified = "::".join(context_stack + type_qualifiers + [type_name])
                    symbols.append(
                        {
                            "name": qualified,
                            "kind": kind_map[node.type],
                            "param": "enum" if node.type == "enum_specifier" else "struct",
                            "line": node.start_point.row + 1,
                        }
                    )
                    new_context = context_stack + type_qualifiers + [type_name]
                    for child in node.children:
                        if child.type == "field_declaration_list":
                            for member in child.children:
                                collect(member, new_context)
                return

            if node.type == "function_definition":
                declarator = node.child_by_field_name("declarator")
                if declarator:
                    name, qualifiers = extract_function_name_and_qualifiers(declarator, context_stack)
                    if name:
                        qualified = "::".join(qualifiers + [name]) if qualifiers else name
                        sig = self._extract_parameter_signature(node)
                        symbols.append(
                            {
                                "name": qualified,
                                "kind": "function",
                                "param": "function",
                                "line": node.start_point.row + 1,
                                "signature": sig,
                            }
                        )
                return

            if node.type == "field_declaration":
                declarator = node.child_by_field_name("declarator")
                # Accept function_declarator possibly wrapped in pointer/reference
                # declarators for pointer/reference return types.
                if declarator and unwrap_to_function_declarator(declarator) is not None:
                    name, qualifiers = extract_function_name_and_qualifiers(declarator, context_stack)
                    if name:
                        qualified = "::".join(qualifiers + [name]) if qualifiers else name
                        sig = self._extract_parameter_signature(node)
                        symbols.append(
                            {
                                "name": qualified,
                                "kind": "function",
                                "param": "function",
                                "line": node.start_point.row + 1,
                                "signature": sig,
                            }
                        )
                    return
                # field_declaration can also wrap nested class/struct definitions
                for child in node.children:
                    if child.type in ["class_specifier", "struct_specifier", "enum_specifier"]:
                        collect(child, context_stack)
                return

            if node.type == "template_declaration":
                for child in node.children:
                    if child.type == "function_definition":
                        declarator = child.child_by_field_name("declarator")
                        if declarator:
                            name, qualifiers = extract_function_name_and_qualifiers(declarator, context_stack)
                            if name:
                                qualified = "::".join(qualifiers + [name]) if qualifiers else name
                                sig = self._extract_parameter_signature(node)
                                symbols.append(
                                    {
                                        "name": qualified,
                                        "kind": "function",
                                        "param": "function",
                                        "line": node.start_point.row + 1,
                                        "signature": sig,
                                    }
                                )
                        return
                    elif child.type in ["class_specifier", "struct_specifier"]:
                        collect(child, context_stack)
                        return
                return

            if node.type == "declaration":
                # Check for extern/forward function declarations. The function_declarator
                # may be a direct child OR wrapped in pointer/reference declarators when
                # the return type is a pointer/reference (e.g. ``extern int* foo();``).
                for child in node.children:
                    if child.type in ("function_declarator", "pointer_declarator", "reference_declarator"):
                        if unwrap_to_function_declarator(child) is None:
                            continue
                        name, qualifiers = extract_function_name_and_qualifiers(child, context_stack)
                        if name:
                            qualified = "::".join(qualifiers + [name]) if qualifiers else name
                            sig = self._extract_parameter_signature(node)
                            symbols.append(
                                {
                                    "name": qualified,
                                    "kind": "function",
                                    "param": "function",
                                    "line": node.start_point.row + 1,
                                    "signature": sig,
                                }
                            )
                        return

                # Check for variable declarations (init_declarator child)
                var_name = None
                for child in node.children:
                    if child.type == "init_declarator":
                        for subchild in child.children:
                            if subchild.type == "identifier":
                                var_name = node_text(subchild)
                                break
                            elif subchild.type in ["array_declarator", "pointer_declarator"]:
                                for leaf in subchild.children:
                                    if leaf.type == "identifier":
                                        var_name = node_text(leaf)
                                        break
                                if var_name:
                                    break
                        break
                if var_name:
                    qualified = "::".join(context_stack + [var_name]) if context_stack else var_name
                    symbols.append(
                        {
                            "name": qualified,
                            "kind": "variable",
                            "param": "var",
                            "line": node.start_point.row + 1,
                        }
                    )

            for child in node.children:
                collect(child, context_stack)

        collect(root)
        return symbols
