# Test Custom Tags

Testing the custom tags defined in .projected-source.py

## Using accept_hook() tag

📍 [`examples/applyHook.cpp:2864-2869`](https://github.com/sublimator/projected-source/blob/975fbdeb3723558d160c1f98b411c30fe956a047/examples/applyHook.cpp#L2864-L2869)
```cpp
2864 DEFINE_JS_FUNCTION(int64_t, accept, JSValue error_msg, JSValue error_code)
2865 {
2866     JS_HOOK_SETUP();
2867     HOOK_EXIT_JS(error_msg, error_code, hook_api::ExitType::ACCEPT);
2868     JS_HOOK_TEARDOWN();
2869 }
```

## Using state_hook() tag  

📍 [`examples/applyHook.cpp:2095-2104`](https://github.com/sublimator/projected-source/blob/975fbdeb3723558d160c1f98b411c30fe956a047/examples/applyHook.cpp#L2095-L2104)
```cpp
2095 DEFINE_JS_FUNCTION(JSValue, state_set, JSValue data, JSValue key)
2096 {
2097     JS_HOOK_SETUP();
2098 
2099     JSValueConst argv2[] = {argv[0], argv[1], JS_UNDEFINED, JS_UNDEFINED};
2100 
2101     return FORWARD_JS_FUNCTION_CALL(state_foreign_set, 4, argv2);
2102 
2103     JS_HOOK_TEARDOWN();
2104 }
```

## Using parameterized hook() tag

### hook('rollback')
📍 [`examples/applyHook.cpp:2885-2890`](https://github.com/sublimator/projected-source/blob/975fbdeb3723558d160c1f98b411c30fe956a047/examples/applyHook.cpp#L2885-L2890)
```cpp
2885 DEFINE_JS_FUNCTION(int64_t, rollback, JSValue error_msg, JSValue error_code)
2886 {
2887     JS_HOOK_SETUP();
2888     HOOK_EXIT_JS(error_msg, error_code, hook_api::ExitType::ROLLBACK);
2889     JS_HOOK_TEARDOWN();
2890 }
```

### hook('trace')
📍 [`examples/applyHook.cpp:1719-1808`](https://github.com/sublimator/projected-source/blob/975fbdeb3723558d160c1f98b411c30fe956a047/examples/applyHook.cpp#L1719-L1808)
```cpp
1719 DEFINE_JS_FUNCTION(int64_t, trace, JSValue msg, JSValue data, JSValue as_hex)
1720 {
1721     JS_HOOK_SETUP();
1722 
1723     std::string out;
1724     if (JS_IsString(msg))
1725     {
1726         // RH TODO: check if there's a way to ensure the string isn't
1727         // arbitrarily long before calling ToCStringLen
1728         size_t len;
1729         const char* cstr = JS_ToCStringLen(ctx, &len, msg);
1730         if (len > 256)
1731             len = 256;
1732         out = std::string(cstr, len);
1733         JS_FreeCString(ctx, cstr);
1734     }
1735 
1736     out += ": ";
1737 
1738     if (JS_IsBool(as_hex) && !!JS_ToBool(ctx, as_hex))
1739     {
1740         auto in = FromJSIntArrayOrHexString(ctx, data, 64 * 1024);
1741         if (in.has_value())
1742         {
1743             if (in->size() > 1024)
1744                 in->resize(1024);
1745             out += strHex(*in);
1746         }
1747         else
1748             out += "<could not display hex>";
1749     }
1750     else if (JS_IsBigInt(ctx, data))
1751     {
1752         size_t len;
1753         const char* cstr = JS_ToCStringLen(ctx, &len, data);
1754         out += std::string(cstr, len);
1755         JS_FreeCString(ctx, cstr);
1756     }
1757     else
1758     {
1759         // replacer function that converts BigInts to strings
1760         JSValueConst replacer = JS_NewCFunction(
1761             ctx,
1762             [](JSContext* ctx,
1763                JSValueConst this_val,
1764                int argc,
1765                JSValueConst* argv) -> JSValue {
1766                 if (argc < 2)
1767                     return JS_DupValue(ctx, argv[1]);
1768                 if (JS_IsBigInt(ctx, argv[1]))
1769                 {
1770                     size_t len;
1771                     const char* str = JS_ToCStringLen(ctx, &len, argv[1]);
1772                     JSValue ret = JS_NewStringLen(ctx, str, len);
1773                     JS_FreeCString(ctx, str);
1774                     return ret;
1775                 }
1776                 return JS_DupValue(ctx, argv[1]);
1777             },
1778             "replacer",
1779             2);
1780 
1781         JSValue sdata = JS_JSONStringify(ctx, data, replacer, JS_UNDEFINED);
1782         JS_FreeValue(ctx, replacer);
1783 
1784         if (JS_IsString(sdata))
1785         {
1786             assert(JS_IsString(sdata));
1787             size_t len;
1788             const char* cstr = JS_ToCStringLen(ctx, &len, sdata);
1789             if (len > 1023)
1790                 len = 1023;
1791             out += std::string(cstr, len);
1792             JS_FreeCString(ctx, cstr);
1793             JS_FreeValue(ctx, sdata);
1794         }
1795         else
1796         {
1797             out += "<could not display data>";
1798         }
1799     }
1800 
1801     if (out.size() > 0)
1802         j.trace() << "HookTrace[" << HC_ACC() << "]: " << out;
1803 
1804     return JS_NewInt64(ctx, 0);
1805     //    return JS_NewString(ctx, out.c_str());
1806 
1807     JS_HOOK_TEARDOWN();
1808 }
```

## Using uppercase filter
HELLO WORLD