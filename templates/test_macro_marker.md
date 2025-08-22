# Test Macro + Marker Combination

## Full DEFINE_JS_FUNCTION(example)

📍 [`test_files/macro_example.cpp:3-20`](https://github.com/sublimator/projected-source/blob/975fbdeb3723558d160c1f98b411c30fe956a047/test_files/macro_example.cpp#L3-L20)
```cpp
   3 DEFINE_JS_FUNCTION(example, ctx, data) {
   4     //@@start setup
   5     JS_HOOK_SETUP();
   6     auto context = get_context();
   7     //@@end setup
   8     
   9     //@@start validation
  10     if (!validate_input(data)) {
  11         return JS_ERROR;
  12     }
  13     //@@end validation
  14     
  15     //@@start execution
  16     perform_operation();
  17     //@@end execution
  18     
  19     return JS_SUCCESS;
  20 }
```

## Just the 'validation' section from DEFINE_JS_FUNCTION(example)

📍 [`test_files/macro_example.cpp:9-13`](https://github.com/sublimator/projected-source/blob/975fbdeb3723558d160c1f98b411c30fe956a047/test_files/macro_example.cpp#L9-L13)
```cpp
   9     if (!validate_input(data)) {
  10         return JS_ERROR;
  11     }
```

## Just the 'setup' section from DEFINE_JS_FUNCTION(example)  

📍 [`test_files/macro_example.cpp:4-7`](https://github.com/sublimator/projected-source/blob/975fbdeb3723558d160c1f98b411c30fe956a047/test_files/macro_example.cpp#L4-L7)
```cpp
   4     JS_HOOK_SETUP();
   5     auto context = get_context();
```