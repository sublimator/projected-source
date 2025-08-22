# Helpers

## data_as_int64

📍 [`examples/applyHook.cpp:1281-1294`](https://github.com/sublimator/projected-source/blob/975fbdeb3723558d160c1f98b411c30fe956a047/examples/applyHook.cpp#L1281-L1294)
```cpp
1281 inline int64_t
1282 data_as_int64(void const* ptr_raw, uint32_t len)
1283 {
1284     if (len > 8)
1285         return hook_api::hook_return_code::TOO_BIG;
1286 
1287     uint8_t const* ptr = reinterpret_cast<uint8_t const*>(ptr_raw);
1288     uint64_t output = 0;
1289     for (int i = 0, j = (len - 1) * 8; i < len; ++i, j -= 8)
1290         output += (((uint64_t)ptr[i]) << j);
1291     if ((1ULL << 63U) & output)
1292         return hook_api::hook_return_code::TOO_BIG;
1293     return (int64_t)output;
1294 }
```
