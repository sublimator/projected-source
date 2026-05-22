"""Pure tree-sitter AST helpers for the C++ parser.

Stateless functions for navigating C++ syntax trees — name extraction,
qualifier matching, and node-to-result conversion. Separated from
``cpp_parser.py`` so the traversal logic and these reusable primitives stay
independently readable and testable.
"""

from typing import List, Optional, Tuple

from tree_sitter import Node

from .extraction_result import ExtractionResult
from .utils import node_text


def node_to_result(node: Node, qualified_name: str) -> ExtractionResult:
    """Create an ExtractionResult from a tree-sitter Node."""
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


def qualifier_base(qualifier: str) -> str:
    """Strip template args from a qualifier: ``Container<T>`` -> ``Container``."""
    idx = qualifier.find("<")
    return qualifier[:idx] if idx >= 0 else qualifier


def qualifiers_match(found: List[str], target: List[str]) -> bool:
    """Check if qualifier lists match (template args are compared flexibly)."""
    if not target:
        return True
    if found == target:
        return True
    if len(found) >= len(target) and found[-len(target) :] == target:
        return True
    # Compare stripping template args from both sides
    if len(found) >= len(target):
        found_tail = found[-len(target) :]
        if all(qualifier_base(f) == qualifier_base(t) for f, t in zip(found_tail, target)):
            return True
    return False


def find_following_body(decl_node: Node) -> Optional[Node]:
    """Find a compound_statement following a declaration node.

    Handles the pattern where tree-sitter splits a macro-attributed function:
        declaration ; expression_statement ; compound_statement
    Returns the compound_statement if found within a few siblings.
    """
    parent = decl_node.parent
    if not parent:
        return None

    found_decl = False
    siblings_after = 0
    for child in parent.children:
        if found_decl:
            siblings_after += 1
            if child.type == "compound_statement":
                return child
            # Allow skipping expression_statement (attribute macros) and
            # other noise, but don't look too far
            if siblings_after > 3:
                break
        elif child.id == decl_node.id:
            found_decl = True

    return None


def extract_operator_name(op_node: Node) -> str:
    """Extract an operator name like ``operator+``, ``operator==``, ``operator[]``."""
    parts: List[str] = []
    for child in op_node.children:
        if child.text:
            parts.append(node_text(child))
    return "".join(parts)


def extract_template_type_name(tt_node: Node) -> Optional[str]:
    """Extract the name from a ``template_type`` node like ``Container<T>``."""
    type_id = None
    template_args = None
    for child in tt_node.children:
        if child.type == "type_identifier":
            type_id = node_text(child)
        elif child.type == "template_argument_list":
            template_args = child.text.decode("utf8") if child.text else None
    if type_id and template_args:
        return f"{type_id}{template_args}"
    return type_id


def extract_qualified_parts(qnode: Node) -> List[str]:
    """Recursively extract the parts of a ``qualified_identifier``.

    Handles simple identifiers (``MyClass::method``), template types
    (``Container<T>::method``), and operator names (``MyClass::operator+``).
    """
    parts: List[str] = []
    current: Optional[Node] = qnode
    while current and current.type == "qualified_identifier":
        found_nested = False
        for child in current.children:
            if child.type in ("namespace_identifier", "identifier"):
                parts.append(node_text(child))
            elif child.type == "template_type":
                template_name = extract_template_type_name(child)
                if template_name:
                    parts.append(template_name)
            elif child.type == "operator_name":
                parts.append(extract_operator_name(child))
            elif child.type == "qualified_identifier":
                current = child
                found_nested = True
                break
        if not found_nested:
            break
    return parts


def extract_function_name_and_qualifiers(declarator: Node, context_stack: List[str]) -> Tuple[str, List[str]]:
    """Extract a function name and its qualifiers from a declarator node.

    Walks through pointer/reference declarator wrappers to reach the
    ``function_declarator`` and resolves the name node, which may be a plain
    identifier, a qualified identifier, an operator, or a template function.
    """
    found_name = ""
    found_qualifiers: List[str] = []

    current: Optional[Node] = declarator
    while current:
        if current.type == "function_declarator":
            name_node = current.child_by_field_name("declarator")
            if name_node:
                if name_node.type == "qualified_identifier":
                    all_parts = extract_qualified_parts(name_node)
                    if all_parts:
                        found_name = all_parts[-1]
                        found_qualifiers = all_parts[:-1]
                elif name_node.type == "template_function":
                    # Template specialization: templateAdd<int>(...)
                    found_name = node_text(name_node)
                    found_qualifiers = context_stack
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
