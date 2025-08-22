#!/usr/bin/env python3
"""
Test extracting specific macros from macro.h
"""

from pathlib import Path
from extract_macro_def import extract_macro_definitions


def test_specific_macros():
    """Test extracting specific macro definitions."""
    macro_file = Path("../../examples/macro.h")
    
    print("=" * 80)
    print("Extracting DEFINE_WASM_FUNCNARG (the big one you showed)")
    print("=" * 80)
    
    results = extract_macro_definitions(macro_file, "DEFINE_WASM_FUNCNARG")
    
    if results:
        for macro in results:
            print(f"\nFound: {macro['name']}")
            print(f"Type: {macro['type']}")
            print(f"Lines: {macro['start_line']}-{macro['end_line']} ({macro['lines']} lines)")
            if macro['parameters']:
                print(f"Parameters: {macro['parameters']}")
            print("\nFull text:")
            print("-" * 40)
            print(macro['text'])
            print("-" * 40)
    else:
        print("Not found!")
    
    print("\n" + "=" * 80)
    print("Extracting DEFINE_JS_FUNCTION")
    print("=" * 80)
    
    results = extract_macro_definitions(macro_file, "DEFINE_JS_FUNCTION")
    
    if results:
        for macro in results:
            print(f"\nFound: {macro['name']}")
            print(f"Type: {macro['type']}")
            print(f"Lines: {macro['start_line']}-{macro['end_line']} ({macro['lines']} lines)")
            if macro['parameters']:
                print(f"Parameters: {macro['parameters']}")
            print("\nFirst 10 lines:")
            print("-" * 40)
            lines = macro['text'].split('\n')
            for line in lines[:10]:
                print(line)
            if len(lines) > 10:
                print(f"... ({len(lines) - 10} more lines)")
            print("-" * 40)
    
    print("\n" + "=" * 80)
    print("All DEFINE_* macros summary")
    print("=" * 80)
    
    all_macros = extract_macro_definitions(macro_file)
    define_macros = [m for m in all_macros if m['name'].startswith('DEFINE_')]
    
    for macro in define_macros:
        params = f"({macro['parameters']})" if macro['parameters'] else ""
        print(f"{macro['name']}{params} - {macro['lines']} lines at {macro['start_line']}-{macro['end_line']}")


if __name__ == "__main__":
    test_specific_macros()