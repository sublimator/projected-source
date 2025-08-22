# Test Documentation

This demonstrates the `projected-source` package capabilities.

## Extract Function by Name

Here's the `calculate` function:

📍 [`examples/example.cpp:17-26`](https://github.com/sublimator/projected-source/blob/975fbdeb3723558d160c1f98b411c30fe956a047/examples/example.cpp#L17-L26)
```cpp
  17 int calculate(int x, int y, int operation) {
  18     switch(operation) {
  19         case 0:
  20             return add(x, y);
  21         case 1:
  22             return multiply(x, y);
  23         default:
  24             return 0;
  25     }
  26 }
```

## Extract Using Markers

### Add Function
📍 [`examples/example.cpp:4-7`](https://github.com/sublimator/projected-source/blob/975fbdeb3723558d160c1f98b411c30fe956a047/examples/example.cpp#L4-L7)
```cpp
   4 int add(int a, int b) {
   5     // Simple addition function
   6     return a + b;
   7 }
```

### Main Example
📍 [`examples/example.cpp:29-34`](https://github.com/sublimator/projected-source/blob/975fbdeb3723558d160c1f98b411c30fe956a047/examples/example.cpp#L29-L34)
```cpp
  29 int main() {
  30     printf("2 + 3 = %d\n", add(2, 3));
  31     printf("4 * 5 = %d\n", multiply(4, 5));
  32     printf("Calculate: %d\n", calculate(10, 20, 0));
  33     return 0;
  34 }
```

## Extract Line Range

Here are lines 5-7:
📍 [`examples/example.cpp:5-7`](https://github.com/sublimator/projected-source/blob/975fbdeb3723558d160c1f98b411c30fe956a047/examples/example.cpp#L5-L7)
```cpp
   5     // Simple addition function
   6     return a + b;
   7 }
```

## Without GitHub Integration

📍 `examples/example.cpp:1-3`
```cpp
   1 #include <stdio.h>
   2 
   3 //@@start add_function
```

## With Different Options

### No Line Numbers
📍 [`examples/example.cpp:11-14`](https://github.com/sublimator/projected-source/blob/975fbdeb3723558d160c1f98b411c30fe956a047/examples/example.cpp#L11-L14)
```cpp
int multiply(int a, int b) {
    // Simple multiplication
    return a * b;
}
```