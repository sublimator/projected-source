#!/usr/bin/env python3
"""
Test the enhanced MacroFinder that returns nodes and can find markers within them.
"""

test_code = b"""
DEFINE_JS_FUNCTION(example, ctx, data) {
    //@@start setup
    JS_HOOK_SETUP();
    auto context = get_context();
    //@@end setup
    
    //@@start validation
    if (!validate_input(data)) {
        return JS_ERROR;
    }
    //@@end validation
    
    //@@start execution
    perform_operation();
    //@@end execution
    
    return JS_SUCCESS;
}

DEFINE_JS_FUNCTION(another, env, args) {
    //@@start init
    initialize();
    //@@end init
    
    return JS_OK;
}
"""

def test_macro_with_markers():
    """Test finding markers within macros."""
    from projected_source.languages.macro_finder_nodes import MacroFinderWithNodes
    
    finder = MacroFinderWithNodes()
    
    print("=" * 60)
    print("Test 1: Find macro with nodes")
    print("=" * 60)
    
    results = finder.find_by_name_with_nodes(test_code, "DEFINE_JS_FUNCTION")
    
    for r in results:
        print(f"\nFound macro: {r['macro']} at line {r['line']}")
        print(f"  Arguments: {r['arguments']}")
        print(f"  Has node: {r['node'] is not None}")
        print(f"  Node type: {r['node'].type}")
    
    print("\n" + "=" * 60)
    print("Test 2: Find markers within specific macro")
    print("=" * 60)
    
    # Find markers in the 'example' function
    info = finder.find_markers_in_macro(
        test_code, 
        "DEFINE_JS_FUNCTION",
        {'arg0': 'example'}  # Filter by first argument
    )
    
    print(f"\nMacro: {info['macro']['macro']}({', '.join(info['macro']['arguments'])})")
    print(f"Markers found: {list(info['markers'].keys())}")
    for marker, (start, end) in info['markers'].items():
        print(f"  - {marker}: lines {start}-{end}")
    
    print("\n" + "=" * 60)
    print("Test 3: Extract specific marker section")
    print("=" * 60)
    
    setup_code = finder.extract_macro_section(
        test_code,
        "DEFINE_JS_FUNCTION",
        "validation",
        {'arg0': 'example'}
    )
    
    print("\nExtracted 'validation' section:")
    print(setup_code)
    
    print("\n" + "=" * 60)
    print("Test 4: Find markers in 'another' function")
    print("=" * 60)
    
    info2 = finder.find_markers_in_macro(
        test_code,
        "DEFINE_JS_FUNCTION", 
        {'arg0': 'another'}
    )
    
    print(f"\nMacro: {info2['macro']['macro']}({', '.join(info2['macro']['arguments'])})")
    print(f"Markers found: {list(info2['markers'].keys())}")

if __name__ == "__main__":
    test_macro_with_markers()