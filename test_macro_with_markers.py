#!/usr/bin/env python3
"""
Test that demonstrates the need to search for markers WITHIN macro nodes.
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
"""

def test_macro_with_markers():
    """
    We want to:
    1. Find the DEFINE_JS_FUNCTION macro
    2. Then search for markers WITHIN that macro's node
    3. Extract specific sections like "setup", "validation", "execution"
    
    Problem: Currently MacroFinder returns strings, not nodes!
    """
    from projected_source.languages.macro_finder_v3 import MacroFinder
    
    finder = MacroFinder()
    
    # This finds the macro but returns a dict with strings
    results = finder.find_by_name(test_code, "DEFINE_JS_FUNCTION")
    
    if results:
        result = results[0]
        print(f"Found macro at line {result['line']}")
        print(f"Text: {result['text'][:50]}...")
        print(f"But we have strings, not a Node!")
        print(f"We can't search for markers within the node!")
        
        # What we WANT to do:
        # node = result['node']  # <-- We don't have this!
        # markers = extractor.find_markers_in_node(node)
        # setup_code = extract_between_markers(node, "setup")

if __name__ == "__main__":
    test_macro_with_markers()