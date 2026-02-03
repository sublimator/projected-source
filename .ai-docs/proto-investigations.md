# Proto Parser Investigation

## Goal
Add `.proto` file support to projected-source for extracting protobuf definitions.

## Target File
- `/Users/nicholasdudfield/projects/xahaud-worktrees/xahaud-tt-rng/src/ripple/proto/ripple.proto`
- Uses `syntax = "proto2"` (not proto3!)
- 471 lines

## Tree-sitter Proto Grammars Found

| Grammar | URL | Proto Version | Status |
|---------|-----|---------------|--------|
| **coder3101/tree-sitter-proto** | https://github.com/coder3101/tree-sitter-proto | proto2 + proto3 | **WORKS!** |
| treywood/tree-sitter-proto | https://github.com/treywood/tree-sitter-proto | proto2 + proto3 | Not tested |
| mitchellh/tree-sitter-proto | https://github.com/mitchellh/tree-sitter-proto | proto3 only | Wrong version |
| Clement-Jean/tree-sitter-proto | https://github.com/Clement-Jean/tree-sitter-proto | proto3 only | Build failed |
| 90-008/tree-sitter-protobuf | https://github.com/90-008/tree-sitter-protobuf | proto3 only | Wrong version |

## Technical Details

### Python tree-sitter setup
- tree-sitter Python: v0.25.2
- ABI version: 15 (min compatible: 13)
- No pre-built `tree-sitter-proto` package on PyPI
- `tree-sitter-languages` has no wheels for Python 3.14
- `tree-sitter-language-pack` doesn't include proto

### Building from source (WORKING - coder3101)
```bash
cd /tmp
git clone https://github.com/coder3101/tree-sitter-proto.git
cd tree-sitter-proto
npm install tree-sitter-cli@latest
npx tree-sitter generate
cc -shared -o proto.so -fPIC -I src src/parser.c
```

### Loading in Python
```python
import ctypes
from tree_sitter import Language, Parser

lib = ctypes.CDLL("/tmp/tree-sitter-proto/proto.so")
lib.tree_sitter_proto.restype = ctypes.c_void_p
PROTO = Language(lib.tree_sitter_proto())
parser = Parser(PROTO)
```

### Test results
- **coder3101 grammar: WORKS with proto2!**
  - ripple.proto: 36 messages, 13 enums, no errors
- mitchellh grammar: proto3 only, fails on proto2
- 90-008 grammar: proto3 only, fails on proto2

## Next Steps
1. [x] Find/test a proto2-compatible grammar - **coder3101 works!**
2. [ ] Create proper Python binding package for coder3101/tree-sitter-proto
3. [ ] Add ProtoExtractor to projected-source
4. [ ] Support extracting: messages, enums, services, fields

## Resources
- Blog post: https://relistan.com/parsing-protobuf-files-with-treesitter
- py-tree-sitter docs: https://tree-sitter.github.io/py-tree-sitter/
