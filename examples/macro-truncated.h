/**
 * RH NOTE:
 * This file contains macros for converting the hook api definitions into the
 * currently used wasm runtime. Web assembly runtimes are more or less fungible,
 * and at time of writing hooks has moved to WasmEdge from SSVM and before that
 * from wasmer. After the first move it was decided there should be a relatively
 * static interface for the definition and programming of the hook api itself,
 * with the runtime-specific behaviour hidden away by templates or macros.
 * Macros are more expressive and can themselves include templates so macros
 * were then used.
 */

#define LPAREN (
#define RPAREN )
#define COMMA ,
#define EXPAND(...) __VA_ARGS__
#define CAT(a, ...) PRIMITIVE_CAT(a, __VA_ARGS__)
#define CAT2(L, R) CAT2_(L, R)
#define CAT2_(L, R) L##R
#define PRIMITIVE_CAT(a, ...) a##__VA_ARGS__
#define EMPTY()
#define DEFER(id) id EMPTY()
#define OBSTRUCT(...) __VA_ARGS__ DEFER(EMPTY)()
#define VA_NARGS_IMPL(                                         \
    _1, _2, _3, _4, _5, _6, _7, _8, _9, _10, _11, _12, N, ...) \
    N
#define VA_NARGS(__drop, ...) \
    VA_NARGS_IMPL(__VA_ARGS__, 12, 11, 10, 9, 8, 7, 6, 5, 4, 3, 2, 1)
#define FIRST(a, b) a
#define SECOND(a, b) b
#define STRIP_TYPES(...) FOR_VARS(SECOND, 0, __VA_ARGS__)

#define DELIM_0 ,
#define DELIM_1
#define DELIM_2 ;
#define DELIM(S) DELIM_##S

#define FOR_VAR_1(T, S, D) SEP(T, D)
#define FOR_VAR_2(T, S, a, b) FOR_VAR_1(T, S, a) DELIM(S) FOR_VAR_1(T, S, b)
#define FOR_VAR_3(T, S, a, ...) \
    FOR_VAR_1(T, S, a) DELIM(S) FOR_VAR_2(T, S, __VA_ARGS__)
#define FOR_VAR_4(T, S, a, ...) \
    FOR_VAR_1(T, S, a) DELIM(S) FOR_VAR_3(T, S, __VA_ARGS__)
#define FOR_VAR_5(T, S, a, ...) \
    FOR_VAR_1(T, S, a) DELIM(S) FOR_VAR_4(T, S, __VA_ARGS__)
#define FOR_VAR_6(T, S, a, ...) \
    FOR_VAR_1(T, S, a) DELIM(S) FOR_VAR_5(T, S, __VA_ARGS__)
#define FOR_VAR_7(T, S, a, ...) \
    FOR_VAR_1(T, S, a) DELIM(S) FOR_VAR_6(T, S, __VA_ARGS__)
#define FOR_VAR_8(T, S, a, ...) \
    FOR_VAR_1(T, S, a) DELIM(S) FOR_VAR_7(T, S, __VA_ARGS__)
#define FOR_VAR_9(T, S, a, ...) \
    FOR_VAR_1(T, S, a) DELIM(S) FOR_VAR_8(T, S, __VA_ARGS__)
#define FOR_VAR_10(T, S, a, ...) \
    FOR_VAR_1(T, S, a) DELIM(S) FOR_VAR_9(T, S, __VA_ARGS__)
#define FOR_VAR_11(T, S, a, ...) \
    FOR_VAR_1(T, S, a) DELIM(S) FOR_VAR_10(T, S, __VA_ARGS__)
#define FOR_VAR_12(T, S, a, ...) \
    FOR_VAR_1(T, S, a) DELIM(S) FOR_VAR_11(T, S, __VA_ARGS__)
#define FOR_VARS(T, S, ...)                          \
    DEFER(CAT(FOR_VAR_, VA_NARGS(NULL, __VA_ARGS__)) \
              CAT(LPAREN T COMMA S COMMA OBSTRUCT(__VA_ARGS__) RPAREN))

#define SEP(OP, D) EXPAND(OP CAT2(SEP_, D) RPAREN)
#define SEP_uint32_t LPAREN uint32_t COMMA
#define SEP_int32_t LPAREN int32_t COMMA
#define SEP_uint64_t LPAREN uint64_t COMMA
#define SEP_int64_t LPAREN int64_t COMMA
#define SEP_JSValue LPAREN JSValue COMMA

#define VAL_uint32_t WasmEdge_ValueGetI32(in[_stack++])
#define VAL_int32_t WasmEdge_ValueGetI32(in[_stack++])
#define VAL_uint64_t WasmEdge_ValueGetI64(in[_stack++])
#define VAL_int64_t WasmEdge_ValueGetI64(in[_stack++])

#define VAR_ASSIGN(T, V) T V = CAT(VAL_##T)

#define RET_uint32_t(return_code) WasmEdge_ValueGenI32(return_code)
#define RET_int32_t(return_code) WasmEdge_ValueGenI32(return_code)
#define RET_uint64_t(return_code) WasmEdge_ValueGenI64(return_code)
#define RET_int64_t(return_code) WasmEdge_ValueGenI64(return_code)

#define RET_ASSIGN(T, return_code) CAT2(RET_, T(return_code))

#define TYP_uint32_t WasmEdge_ValType_I32
#define TYP_int32_t WasmEdge_ValType_I32
#define TYP_uint64_t WasmEdge_ValType_I64
#define TYP_int64_t WasmEdge_ValType_I64

#define WASM_VAL_TYPE(T, b) CAT2(TYP_, T)

#define HALF_COUNT(...) \
    HALF_COUNT_IMPL(    \
        __VA_ARGS__,    \
        16,             \
        16,             \
        15,             \
        15,             \
        14,             \
        14,             \
        13,             \
        13,             \
        12,             \
        12,             \
        11,             \
        11,             \
        10,             \
        10,             \
        9,              \
        9,              \
        8,              \
        8,              \
        7,              \
        7,              \
        6,              \
        6,              \
        5,              \
        5,              \
        4,              \
        4,              \
        3,              \
        3,              \
        2,              \
        2,              \
        1,              \
        1,              \
        0,              \
        0)

#define HALF_COUNT_IMPL( \
    _1,                  \
    _2,                  \
    _3,                  \
    _4,                  \
    _5,                  \
    _6,                  \
    _7,                  \
    _8,                  \
    _9,                  \
    _10,                 \
    _11,                 \
    _12,                 \
    _13,                 \
    _14,                 \
    _15,                 \
    _16,                 \
    _17,                 \
    _18,                 \
    _19,                 \
    _20,                 \
    _21,                 \
    _22,                 \
    _23,                 \
    _24,                 \
    _25,                 \
    _26,                 \
    _27,                 \
    _28,                 \
    _29,                 \
    _30,                 \
    _31,                 \
    _32,                 \
    N,                   \
    ...)                 \
    N

#define DECLARE_WASM_FUNCTION(R, F, ...)                      \
    R F(hook::HookContext& hookCtx,                           \
        WasmEdge_CallingFrameContext const& frameCtx,         \
        __VA_ARGS__);                                         \
    extern WasmEdge_Result WasmFunction##F(                   \
        void* data_ptr,                                       \
        const WasmEdge_CallingFrameContext* frameCtx,         \
        const WasmEdge_Value* in,                             \
        WasmEdge_Value* out);                                 \
    extern WasmEdge_ValType WasmFunctionParams##F[];          \
    extern WasmEdge_ValType WasmFunctionResult##F[];          \
    extern WasmEdge_FunctionTypeContext* WasmFunctionType##F; \
    extern WasmEdge_String WasmFunctionName##F;

#define DECLARE_JS_FUNCNARG(R, F, ...)                                        \
    extern JSValue JSFunction##F(                                             \
        JSContext* ctx, JSValueConst this_val, int argc, JSValueConst* argv); \
    const int JSFunctionParamCount##F = 0;

#define DECLARE_JS_FUNCTION(R, F, ...)                                        \
    extern JSValue JSFunction##F(                                             \
        JSContext* ctx, JSValueConst this_val, int argc, JSValueConst* argv); \
    const int JSFunctionParamCount##F = HALF_COUNT(__VA_ARGS__);

#define DECLARE_WASM_FUNCNARG(R, F)                           \
    R F(hook::HookContext& hookCtx,                           \
        WasmEdge_CallingFrameContext const& frameCtx);        \
    extern WasmEdge_Result WasmFunction##F(                   \
        void* data_ptr,                                       \
        const WasmEdge_CallingFrameContext* frameCtx,         \
        const WasmEdge_Value* in,                             \
        WasmEdge_Value* out);                                 \
    extern WasmEdge_ValType WasmFunctionResult##F[];          \
    extern WasmEdge_FunctionTypeContext* WasmFunctionType##F; \
    extern WasmEdge_String WasmFunctionName##F;
