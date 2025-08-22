# Test Macro Definition Extraction

## Extract DEFINE_WASM_FUNCNARG definition

📍 [`examples/macro.h:240-265`](https://github.com/sublimator/projected-source/blob/975fbdeb3723558d160c1f98b411c30fe956a047/examples/macro.h#L240-L265)
```cpp
 240 #define DEFINE_WASM_FUNCNARG(R, F)                                           \
 241     WasmEdge_Result hook_api::WasmFunction##F(                               \
 242         void* data_ptr,                                                      \
 243         const WasmEdge_CallingFrameContext* frameCtx,                        \
 244         const WasmEdge_Value* in,                                            \
 245         WasmEdge_Value* out)                                                 \
 246     {                                                                        \
 247         hook::HookContext* hookCtx =                                         \
 248             reinterpret_cast<hook::HookContext*>(data_ptr);                  \
 249         R return_code = hook_api::F(                                         \
 250             *hookCtx, *const_cast<WasmEdge_CallingFrameContext*>(frameCtx)); \
 251         if (return_code == RC_ROLLBACK || return_code == RC_ACCEPT)          \
 252             return WasmEdge_Result_Terminate;                                \
 253         out[0] = CAT2(RET_, R(return_code));                                 \
 254         return WasmEdge_Result_Success;                                      \
 255     };                                                                       \
 256     WasmEdge_ValType hook_api::WasmFunctionResult##F[1] = {                  \
 257         WASM_VAL_TYPE(R, dummy)};                                            \
 258     WasmEdge_FunctionTypeContext* hook_api::WasmFunctionType##F =            \
 259         WasmEdge_FunctionTypeCreate({}, 0, WasmFunctionResult##F, 1);        \
 260     WasmEdge_String hook_api::WasmFunctionName##F =                          \
 261         WasmEdge_StringCreateByCString(#F);                                  \
 262     R hook_api::F(                                                           \
 263         hook::HookContext& hookCtx,                                          \
 264         WasmEdge_CallingFrameContext const& frameCtx)
```

## Extract DEFINE_JS_FUNCTION definition

📍 [`examples/macro.h:278-284`](https://github.com/sublimator/projected-source/blob/975fbdeb3723558d160c1f98b411c30fe956a047/examples/macro.h#L278-L284)
```cpp
 278 #define DEFINE_JS_FUNCTION(R, F, ...)                                        \
 279     JSValue hook_api::JSFunction##F(                                         \
 280         JSContext* ctx, JSValueConst this_val, int argc, JSValueConst* argv) \
 281     {                                                                        \
 282         int _stack = 0;                                                      \
 283         FOR_VARS(VAR_JSASSIGN, 2, __VA_ARGS__);
```

## Extract a simpler macro

📍 [`examples/macro.h:92-129`](https://github.com/sublimator/projected-source/blob/975fbdeb3723558d160c1f98b411c30fe956a047/examples/macro.h#L92-L129)
```cpp
  92 #define HALF_COUNT(...) \
  93     HALF_COUNT_IMPL(    \
  94         __VA_ARGS__,    \
  95         16,             \
  96         16,             \
  97         15,             \
  98         15,             \
  99         14,             \
 100         14,             \
 101         13,             \
 102         13,             \
 103         12,             \
 104         12,             \
 105         11,             \
 106         11,             \
 107         10,             \
 108         10,             \
 109         9,              \
 110         9,              \
 111         8,              \
 112         8,              \
 113         7,              \
 114         7,              \
 115         6,              \
 116         6,              \
 117         5,              \
 118         5,              \
 119         4,              \
 120         4,              \
 121         3,              \
 122         3,              \
 123         2,              \
 124         2,              \
 125         1,              \
 126         1,              \
 127         0,              \
 128         0)
```