"""
Tests for the extractor module.
"""

import tempfile
from pathlib import Path

from projected_source.languages.cpp import CppExtractor


def test_find_markers():
    """Test finding comment markers in C++ code."""
    extractor = CppExtractor()

    test_code = b"""
#include <stdio.h>

//@@start example1
int add(int a, int b) {
    return a + b;
}
//@@end example1

//@@start example2
void print_hello() {
    printf("Hello, World!\\n");
}
//@@end example2

int main() {
    //@@start main_body
    int result = add(1, 2);
    print_hello();
    //@@end main_body
    return 0;
}
"""

    # Create a temporary file
    with tempfile.NamedTemporaryFile(suffix=".cpp", delete=False) as f:
        f.write(test_code)
        temp_path = Path(f.name)

    try:
        # Find markers
        markers = extractor.find_markers_in_file(temp_path)

        # Verify markers were found
        assert "example1" in markers
        assert "example2" in markers
        assert "main_body" in markers

        # Verify line ranges
        example1_start, example1_end = markers["example1"]
        # Lines are 1-based, and we want the content between markers
        assert example1_start == 5  # Line after //@@start (line 4 is the marker)
        assert example1_end == 7  # Line before //@@end (line 8 is the marker)

    finally:
        temp_path.unlink()


def test_extract_function():
    """Test extracting a function by name."""
    extractor = CppExtractor()

    test_code = b"""
#include <stdio.h>

int calculate(int x) {
    return x * 2;
}

void display(int value) {
    printf("Value: %d\\n", value);
}
"""

    with tempfile.NamedTemporaryFile(suffix=".cpp", delete=False) as f:
        f.write(test_code)
        temp_path = Path(f.name)

    try:
        # Extract function
        code_text, start_line, end_line = extractor.extract_function(temp_path, "calculate")

        assert "int calculate" in code_text
        assert "return x * 2" in code_text
        assert start_line == 4
        assert end_line == 6

    finally:
        temp_path.unlink()


def test_extract_lines():
    """Test extracting specific line ranges."""
    extractor = CppExtractor()

    test_code = """line 1
line 2
line 3
line 4
line 5
"""

    with tempfile.NamedTemporaryFile(mode="w", suffix=".cpp", delete=False) as f:
        f.write(test_code)
        temp_path = Path(f.name)

    try:
        # Extract lines 2-4
        code_text, start_line, end_line = extractor.extract_lines(temp_path, 2, 4)

        assert code_text == "line 2\nline 3\nline 4"
        assert start_line == 2
        assert end_line == 4

    finally:
        temp_path.unlink()


if __name__ == "__main__":
    test_find_markers()
    test_extract_function()
    test_extract_lines()
    print("✓ All tests passed!")
