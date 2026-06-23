<!--
rendered_from: system-overview.md.j2
rendered_at: 2026-06-23T05:30:14Z
branch: main
commit: 1a63693
commit_message: test: replace tautology + non-detecting regression assertions
-->

---

<sub>Last updated: 2026-06-23 | branch: main | commit: 1a63693 (test: replace tautology + non-detecting regression assertions)</sub>

---






# projected-source: System Overview

**projected-source** is a documentation tool that extracts code from source files and injects it into Jinja2 templates, creating documentation that stays synchronized with the codebase. It uses tree-sitter for accurate AST-based parsing and supports C/C++, Protocol Buffers, and Python.

The core idea: write narrative documentation in Markdown templates (`.md.j2`), use `{{ code() }}` calls to pull in the exact code you're describing, and the rendered output always reflects the current state of the source.

---

## Data Structures

Before diving into how extraction works, let's look at the types that flow through the system.

### ExtractionResult

Every time code is extracted from a source file — whether a function, struct, or marker region — the result is packaged as an `ExtractionResult`. This dataclass carries the extracted text along with precise location metadata:

📍 [`projected_source/languages/extraction_result.py:9-36`](https://github.com/sublimator/projected-source/blob/1a63693f86b67f7cbfe9bfb603a20e8bcd892b38/projected_source/languages/extraction_result.py#L9-L36)
```python
   9 @dataclass
  10 class ExtractionResult:
  11     """Result from extracting code elements."""
  12 
  13     text: str
  14     start_line: int
  15     end_line: int
  16     start_column: int = 0
  17     end_column: int = 0
  18     node: Optional[Any] = None  # tree-sitter Node
  19     node_type: Optional[str] = None
  20     qualified_name: Optional[str] = None
  21 
  22     @property
  23     def line_count(self) -> int:
  24         """Number of lines in the extracted text."""
  25         return self.end_line - self.start_line + 1
  26 
  27     @property
  28     def location(self) -> str:
  29         """Human-readable location string."""
  30         if self.start_line == self.end_line:
  31             return f"line {self.start_line}"
  32         return f"lines {self.start_line}-{self.end_line}"
  33 
  34     def to_tuple(self) -> tuple:
  35         """For backwards compatibility."""
  36         return (self.text, self.start_line, self.end_line)
```

The `to_tuple()` method exists for backwards compatibility — most of the extraction API still returns `(text, start_line, end_line)` tuples directly, but the internal parsers work with `ExtractionResult` objects that carry richer metadata like the tree-sitter node and qualified name.

### ChangeRegion

When validating that documentation covers code changes, individual changed regions are represented as `ChangeRegion` — a simple dataclass tying a file path to a line range:

📍 [`projected_source/core/changes_set.py:15-24`](https://github.com/sublimator/projected-source/blob/1a63693f86b67f7cbfe9bfb603a20e8bcd892b38/projected_source/core/changes_set.py#L15-L24)
```python
  15 @dataclass
  16 class ChangeRegion:
  17     """A contiguous region of changed code in a file."""
  18 
  19     file_path: Path
  20     start_line: int
  21     end_line: int
  22 
  23     def __str__(self) -> str:
  24         return f"{self.file_path}:{self.start_line}-{self.end_line}"
```

---

## The Extractor Registry

The system supports multiple languages through a simple registry pattern. Each file extension maps to an extractor class:

📍 [`projected_source/languages/__init__.py:19-41`](https://github.com/sublimator/projected-source/blob/1a63693f86b67f7cbfe9bfb603a20e8bcd892b38/projected_source/languages/__init__.py#L19-L41)
```python
  19 EXTRACTORS = {
  20     ".cpp": CppExtractor,
  21     ".cc": CppExtractor,
  22     ".cxx": CppExtractor,
  23     ".c++": CppExtractor,
  24     ".hpp": CppExtractor,
  25     ".h": CppExtractor,
  26     ".hxx": CppExtractor,
  27     ".h++": CppExtractor,
  28     ".c": CppExtractor,  # C is close enough to C++ for our purposes
  29     ".ipp": CppExtractor,  # Inline implementation files
  30     ".macro": CppExtractor,  # C preprocessor macro files (e.g., rippled sfields.macro)
  31     ".proto": ProtoExtractor,  # Protocol Buffers
  32     ".py": PythonExtractor,  # Python
  33     ".pyi": PythonExtractor,  # Python type stubs
  34     ".ts": TypeScriptExtractor,  # TypeScript
  35     ".tsx": TypeScriptExtractor,  # TSX (React) — tsx=True set via get_extractor
  36     ".mts": TypeScriptExtractor,  # TypeScript ES module
  37     ".cts": TypeScriptExtractor,  # TypeScript CommonJS module
  38     ".java": JavaExtractor,  # Java
  39     ".rs": RustExtractor,  # Rust
  40     ".lean": LeanExtractor,  # Lean 4
  41 }
```

When a `code()` call needs to extract from a file, it calls `get_extractor()` which looks up the right class by file extension and instantiates it:

📍 [`projected_source/languages/__init__.py:44-66`](https://github.com/sublimator/projected-source/blob/1a63693f86b67f7cbfe9bfb603a20e8bcd892b38/projected_source/languages/__init__.py#L44-L66)
```python
  44 def get_extractor(file_path: Path):
  45     """
  46     Get the appropriate extractor for a file based on its extension.
  47 
  48     Args:
  49         file_path: Path to the file
  50 
  51     Returns:
  52         An extractor instance
  53 
  54     Raises:
  55         ValueError: If no extractor is available for the file type
  56     """
  57     suffix = file_path.suffix.lower()
  58 
  59     if suffix not in EXTRACTORS:
  60         supported = ", ".join(EXTRACTORS.keys())
  61         raise ValueError(f"No extractor for {suffix} files. Supported: {supported}")
  62 
  63     extractor_class = EXTRACTORS[suffix]
  64     if extractor_class is TypeScriptExtractor and suffix == ".tsx":
  65         return extractor_class(tsx=True)
  66     return extractor_class()
```

### BaseExtractor

All language extractors inherit from `BaseExtractor`, which provides the tree-sitter parser setup, line extraction, and the marker system. The marker system lets you tag regions of source code with `//@@start name` and `//@@end name` comments, then extract just that region:

📍 [`projected_source/core/extractor.py:17-134`](https://github.com/sublimator/projected-source/blob/1a63693f86b67f7cbfe9bfb603a20e8bcd892b38/projected_source/core/extractor.py#L17-L134)
```python
  17 class BaseExtractor:
  18     """Base class for language-specific extractors."""
  19 
  20     def __init__(self, language):
  21         self.language = language
  22         self.parser = Parser(language)
  23 
  24     def parse_file(self, file_path: Path) -> Node:
  25         """Parse a file and return the root node."""
  26         source = file_path.read_bytes()
  27         tree = self.parser.parse(source)
  28         return tree.root_node
  29 
  30     def parse_bytes(self, source: bytes) -> Node:
  31         """Parse source bytes and return the root node."""
  32         tree = self.parser.parse(source)
  33         return tree.root_node
  34 
  35     def extract_lines(self, file_path: Path, start_line: int, end_line: int) -> Tuple[str, int, int]:
  36         """
  37         Extract lines from a file.
  38 
  39         Returns:
  40             Tuple of (code_text, start_line, end_line)
  41         """
  42         lines = file_path.read_text().splitlines()
  43         # Convert to 0-based indexing
  44         start = max(0, start_line - 1)
  45         end = min(len(lines), end_line)
  46 
  47         code_lines = lines[start:end]
  48         return "\n".join(code_lines), max(1, start_line), min(len(lines), end_line)
  49 
  50     def find_markers_in_node(self, node: Node) -> Dict[str, Tuple[int, int]]:
  51         """
  52         Find comment markers within a given node.
  53 
  54         Uses tree-sitter queries with predicates to find //@@start and //@@end markers.
  55 
  56         Args:
  57             node: The node to search within (e.g., function body or root)
  58 
  59         Returns:
  60             Dict mapping marker names to (start_line, end_line) tuples
  61         """
  62         # Query for ALL comments first (no predicate)
  63         comment_query = Query(self.language, "(comment) @comment")
  64         cursor = QueryCursor(comment_query)
  65         matches = cursor.matches(node)
  66 
  67         markers = {}
  68         active_markers = {}  # Track open markers
  69 
  70         for _, captures in matches:
  71             comments = captures.get("comment", [])
  72             for comment in comments:
  73                 if not comment or not comment.text:
  74                     continue
  75 
  76                 text = node_text(comment)
  77                 line_num = comment.start_point.row + 1
  78 
  79                 # Check for marker patterns in the comment text
  80                 # Using Python regex since tree-sitter regex can be tricky
  81                 if "//@@start" in text:
  82                     match = re.search(r"//@@start\s+([\w-]+)", text)
  83                     if match:
  84                         marker_name = match.group(1)
  85                         # Store the line AFTER the comment
  86                         active_markers[marker_name] = line_num + 1
  87                         logger.debug(f"Found start marker '{marker_name}' at line {line_num}")
  88 
  89                 elif "//@@end" in text:
  90                     match = re.search(r"//@@end\s+([\w-]+)", text)
  91                     if match:
  92                         marker_name = match.group(1)
  93                         if marker_name in active_markers:
  94                             start_line = active_markers.pop(marker_name)
  95                             # End at line BEFORE the comment
  96                             end_line = line_num - 1
  97                             markers[marker_name] = (start_line, end_line)
  98                             logger.debug(f"Found end marker '{marker_name}' at line {line_num}")
  99                         else:
 100                             logger.warning(f"Found //@@end {marker_name} without matching //@@start")
 101 
 102         # Warn about unclosed markers
 103         for marker_name in active_markers:
 104             logger.warning(f"Marker '{marker_name}' was not closed with //@@end")
 105 
 106         return markers
 107 
 108     def find_markers_in_file(self, file_path: Path) -> Dict[str, Tuple[int, int]]:
 109         """Find all markers in a file."""
 110         root = self.parse_file(file_path)
 111         return self.find_markers_in_node(root)
 112 
 113     def extract_marker(self, file_path: Path, marker_name: str) -> Tuple[str, int, int]:
 114         """
 115         Extract code between marker comments.
 116 
 117         Returns:
 118             Tuple of (code_text, start_line, end_line)
 119         """
 120         markers = self.find_markers_in_file(file_path)
 121 
 122         if marker_name not in markers:
 123             available = ", ".join(markers.keys()) if markers else "none"
 124             raise ValueError(f"Marker '{marker_name}' not found. Available markers: {available}")
 125 
 126         start_line, end_line = markers[marker_name]
 127         return self.extract_lines(file_path, start_line, end_line)
 128 
 129     def extract_function(self, file_path: Path, function_name: str) -> Tuple[str, int, int]:
 130         """
 131         Extract a function by name.
 132         Must be implemented by language-specific subclasses.
 133         """
 134         raise NotImplementedError("Subclasses must implement extract_function")
```

The `find_markers_in_node` method is particularly interesting — it uses tree-sitter queries to find comments, then applies regex to identify marker directives. This two-step approach handles the fact that tree-sitter's predicate support varies across language grammars.

Each language subclass must implement `extract_function()` at minimum, but the C++ extractor goes much further with support for namespaces, templates, overloads, macros, and nested classes.

---

## The Rendering Pipeline

The `TemplateRenderer` is the heart of the system. It creates a Jinja2 environment and registers three template functions — `code()`, `include()`, and `ignore_changes()` — that templates use to pull in live code.

### Initialization

When a renderer is created, it sets up the Jinja2 environment with the template directory as the loader root, and registers the extraction functions as globals:

📍 [`projected_source/core/renderer.py:75-115`](https://github.com/sublimator/projected-source/blob/1a63693f86b67f7cbfe9bfb603a20e8bcd892b38/projected_source/core/renderer.py#L75-L115)
```python
  75     def __init__(
  76         self,
  77         template_dir: Path = None,
  78         repo_path: Path = None,
  79         remap_dirty_lines: bool = False,
  80         changes_set: "ChangesSet" = None,
  81     ):
  82         """
  83         Initialize the renderer.
  84 
  85         Args:
  86             template_dir: Directory containing templates (default: current dir)
  87             repo_path: Repository root path (default: current dir)
  88             remap_dirty_lines: If True, remap line numbers in dirty files to match
  89                                committed version (for sharing). Affects permalinks
  90                                and code block line numbers.
  91             changes_set: Optional ChangesSet for tracking documentation coverage.
  92                          When provided, each code() call will mark its region as
  93                          covered. Check changes_set.uncovered() after rendering.
  94         """
  95         self.template_dir = template_dir or Path.cwd()
  96         self.repo_path = repo_path or Path.cwd()
  97         self.remap_dirty_lines = remap_dirty_lines
  98         self.changes_set = changes_set
  99         self.github = GitHubIntegration(self.repo_path)
 100 
 101         # Create Jinja2 environment
 102         self.env = jinja2.Environment(
 103             loader=jinja2.FileSystemLoader(str(self.template_dir)),
 104             trim_blocks=True,
 105             lstrip_blocks=True,
 106             extensions=[CodeContextExtension],
 107         )
 108 
 109         # Register custom functions
 110         self.env.globals["code"] = self._code_function
 111         self.env.globals["ghc"] = self._code_function  # Alias for compatibility
 112         self.env.globals["ignore_changes"] = self._ignore_changes_function
 113         self.env.globals["include"] = self._include_function
 114         self.env.globals["set_code_context"] = self._set_code_context_function
 115         self.env.globals["set_code_root"] = self._set_code_root_function
```

### The code() Function

This is the workhorse. Every `{{ code('file.cpp', function='foo') }}` call in a template invokes `_code_function`. It resolves the file path, picks the right extractor, extracts the requested symbol, optionally generates a GitHub permalink, adds line numbers, and returns formatted markdown:

📍 [`projected_source/core/renderer.py:120-404`](https://github.com/sublimator/projected-source/blob/1a63693f86b67f7cbfe9bfb603a20e8bcd892b38/projected_source/core/renderer.py#L120-L404)
```python
 120     def _code_function(
 121         self,
 122         file_path: str,
 123         function: str = None,
 124         struct: str = None,
 125         var: str = None,
 126         function_macro: Union[str, Dict] = None,
 127         macro_definition: str = None,
 128         lines: Tuple[int, int] = None,
 129         marker: str = None,
 130         signature: str = None,
 131         message: str = None,
 132         enum: str = None,
 133         service: str = None,
 134         github: bool = True,
 135         blame: bool = False,
 136         line_numbers: bool = True,
 137         language: str = None,
 138         ref: str = None,
 139         root: str = None,
 140     ) -> str:
 141         """
 142         Universal code extraction function for templates.
 143 
 144         Args:
 145             file_path: Path to the source file
 146             function: Function name to extract
 147             struct: Struct/class/enum name to extract (C/C++)
 148             var: Variable/constant declaration to extract (C/C++)
 149             function_macro: Macro that defines a function (dict with 'name' and optional 'arg0', 'arg1', etc)
 150             macro_definition: Macro definition name to extract (#define statement)
 151             lines: Tuple of (start_line, end_line) to extract
 152             marker: Marker name to extract between //@@start and //@@end
 153             signature: String to match against parameter types for overload disambiguation.
 154                        Use partial type names like "TMProposeSet" to select a specific overload.
 155             message: Message name to extract (protobuf)
 156             enum: Enum name to extract (protobuf)
 157             service: Service name to extract (protobuf)
 158             github: Include GitHub permalink (default: True)
 159             blame: Include git blame info (default: False)
 160             line_numbers: Show line numbers (default: True)
 161             language: Language for syntax highlighting (auto-detected if None)
 162 
 163         Returns:
 164             Formatted markdown with code block
 165 
 166         Examples in templates:
 167             {{ code('src/file.cpp', function='myFunc') }}
 168             {{ code('src/file.cpp', function='onMessage', signature='TMProposeSet') }}
 169             {{ code('src/file.cpp', struct='MyClass') }}
 170             {{ code('src/file.cpp', var='errorInfos') }}
 171             {{ code('src/file.cpp', lines=(10, 20)) }}
 172             {{ code('src/file.cpp', marker='example1') }}
 173             {{ code('src/proto/file.proto', message='MyMessage') }}
 174             {{ code('src/proto/file.proto', enum='MyEnum') }}
 175         """
 176         tmp_file = None
 177         resolved_path: Optional[Path] = None
 178         try:
 179             # Apply root prefix: per-call root= overrides context code_root
 180             code_root = root or str(self.env.globals.get("code_root", ""))
 181             if code_root and not Path(file_path).is_absolute():
 182                 file_path = str(Path(code_root) / file_path)
 183 
 184             # Determine active ref (per-call overrides context)
 185             active_ref = ref or str(self.env.globals.get("code_ref", ""))
 186 
 187             # Resolve file path relative to repo
 188             resolved_path = Path(file_path)
 189             if not resolved_path.is_absolute():
 190                 resolved_path = self.repo_path / resolved_path
 191 
 192             # If a git ref is active, fetch file content from that ref
 193             if active_ref:
 194                 rel_path = file_path
 195                 # Ensure relative path for git show
 196                 try:
 197                     rel_path = str(Path(file_path).relative_to(self.repo_path))
 198                 except ValueError:
 199                     # Already relative
 200                     rel_path = file_path
 201                 content = subprocess.check_output(
 202                     ["git", "show", f"{active_ref}:{rel_path}"],
 203                     cwd=self.repo_path,
 204                     stderr=subprocess.DEVNULL,
 205                 )
 206                 tmp_file = Path(tempfile.mktemp(suffix=resolved_path.suffix))
 207                 tmp_file.write_bytes(content)
 208                 resolved_path = tmp_file
 209 
 210             # Get the appropriate extractor
 211             extractor = get_extractor(resolved_path)
 212 
 213             # Extract code based on parameters
 214             if function:
 215                 # Check if we also have a marker - extract marker within function
 216                 if marker:
 217                     if hasattr(extractor, "extract_function_marker"):
 218                         code_text, start_line, end_line = extractor.extract_function_marker(
 219                             resolved_path, function, marker
 220                         )
 221                         logger.info(f"Extracted marker '{marker}' from function '{function}' in {file_path}")
 222                     else:
 223                         return "❌ **ERROR**: Function marker extraction not supported for this file type"
 224                 else:
 225                     code_text, start_line, end_line = extractor.extract_function(resolved_path, function, signature)
 226                     logger.info(f"Extracted function '{function}' from {file_path}")
 227             elif function_macro:
 228                 # Handle function_macro parameter
 229                 if isinstance(function_macro, str):
 230                     # Simple string -> convert to dict
 231                     macro_spec = {"name": function_macro}
 232                 else:
 233                     macro_spec = function_macro
 234 
 235                 # Check if we also have a marker - extract marker within macro
 236                 if marker:
 237                     code_text, start_line, end_line = extractor.extract_function_macro_marker(
 238                         resolved_path, macro_spec, marker
 239                     )
 240                     logger.info(f"Extracted marker '{marker}' from function_macro '{macro_spec}' in {file_path}")
 241                 else:
 242                     code_text, start_line, end_line = extractor.extract_function_macro(resolved_path, macro_spec)
 243                     logger.info(f"Extracted function_macro '{macro_spec}' from {file_path}")
 244             elif macro_definition:
 245                 code_text, start_line, end_line = extractor.extract_macro_definition(resolved_path, macro_definition)
 246                 logger.info(f"Extracted macro_definition '{macro_definition}' from {file_path}")
 247             elif var:
 248                 # Extract variable/constant declaration
 249                 if hasattr(extractor, "extract_variable"):
 250                     code_text, start_line, end_line = extractor.extract_variable(resolved_path, var)
 251                     logger.info(f"Extracted variable '{var}' from {file_path}")
 252                 elif hasattr(extractor, "extract_struct"):
 253                     # C/C++ uses extract_struct for var= (finds declarations)
 254                     if marker:
 255                         if hasattr(extractor, "extract_struct_marker"):
 256                             code_text, start_line, end_line = extractor.extract_struct_marker(
 257                                 resolved_path, var, marker
 258                             )
 259                             logger.info(f"Extracted marker '{marker}' from variable '{var}' in {file_path}")
 260                         else:
 261                             return "❌ **ERROR**: Marker extraction in variable not supported"
 262                     else:
 263                         code_text, start_line, end_line = extractor.extract_struct(resolved_path, var)
 264                         logger.info(f"Extracted variable '{var}' from {file_path}")
 265                 else:
 266                     return "❌ **ERROR**: Variable extraction not supported for this file type"
 267             elif struct:
 268                 # Extract struct/class/enum definition
 269                 if hasattr(extractor, "extract_struct"):
 270                     if marker:
 271                         if hasattr(extractor, "extract_struct_marker"):
 272                             code_text, start_line, end_line = extractor.extract_struct_marker(
 273                                 resolved_path, struct, marker
 274                             )
 275                             logger.info(f"Extracted marker '{marker}' from struct '{struct}' in {file_path}")
 276                         else:
 277                             return "❌ **ERROR**: Marker extraction in struct not supported"
 278                     else:
 279                         code_text, start_line, end_line = extractor.extract_struct(resolved_path, struct)
 280                         logger.info(f"Extracted struct/class '{struct}' from {file_path}")
 281                 else:
 282                     return "❌ **ERROR**: Struct/class extraction not supported for this file type"
 283             elif message:
 284                 # Extract protobuf message
 285                 if hasattr(extractor, "extract_message"):
 286                     if marker:
 287                         code_text, start_line, end_line = extractor.extract_message_marker(
 288                             resolved_path, message, marker
 289                         )
 290                         logger.info(f"Extracted marker '{marker}' from message '{message}' in {file_path}")
 291                     else:
 292                         code_text, start_line, end_line = extractor.extract_message(resolved_path, message)
 293                         logger.info(f"Extracted message '{message}' from {file_path}")
 294                 else:
 295                     return "❌ **ERROR**: Message extraction not supported for this file type"
 296             elif enum:
 297                 # Extract protobuf enum
 298                 if hasattr(extractor, "extract_enum"):
 299                     code_text, start_line, end_line = extractor.extract_enum(resolved_path, enum)
 300                     logger.info(f"Extracted enum '{enum}' from {file_path}")
 301                 else:
 302                     return "❌ **ERROR**: Enum extraction not supported for this file type"
 303             elif service:
 304                 # Extract protobuf service
 305                 if hasattr(extractor, "extract_service"):
 306                     code_text, start_line, end_line = extractor.extract_service(resolved_path, service)
 307                     logger.info(f"Extracted service '{service}' from {file_path}")
 308                 else:
 309                     return "❌ **ERROR**: Service extraction not supported for this file type"
 310             elif marker:
 311                 code_text, start_line, end_line = extractor.extract_marker(resolved_path, marker)
 312                 logger.info(f"Extracted marker '{marker}' from {file_path}")
 313             elif lines:
 314                 start_line, end_line = lines
 315                 code_text, start_line, end_line = extractor.extract_lines(resolved_path, start_line, end_line)
 316                 logger.info(f"Extracted lines {start_line}-{end_line} from {file_path}")
 317             else:
 318                 return (
 319                     f"❌ **ERROR**: Must specify function, struct, var, function_macro, "
 320                     f"macro_definition, lines, or marker for {file_path}"
 321                 )
 322 
 323             # Use original file path for display (not temp file)
 324             display_path = self.repo_path / file_path if not Path(file_path).is_absolute() else Path(file_path)
 325 
 326             # Track this region as covered if we have a ChangesSet
 327             if self.changes_set is not None and not active_ref:
 328                 # changes_set holds HEAD-relative line numbers (built from
 329                 # 'git diff base..HEAD'), but start_line/end_line came from
 330                 # the working tree. Translate before subtracting so uncommitted
 331                 # edits above the extracted region don't shift the wrong rows.
 332                 committed_start = self.github.map_to_committed_line(display_path, start_line)
 333                 committed_end = self.github.map_to_committed_line(display_path, end_line)
 334                 self.changes_set.subtract(display_path, committed_start, committed_end)
 335 
 336             # Remap line numbers if requested (for sharing docs from dirty files)
 337             display_start = start_line
 338             display_end = end_line
 339             if self.remap_dirty_lines and not active_ref:
 340                 display_start = self.github.map_to_committed_line(display_path, start_line)
 341                 display_end = self.github.map_to_committed_line(display_path, end_line)
 342 
 343             # Build header with GitHub permalink if requested
 344             if github and not active_ref:
 345                 header = self.github.get_permalink(
 346                     display_path, start_line, end_line, display_committed_lines=self.remap_dirty_lines
 347                 )
 348             else:
 349                 display_rel = display_path.relative_to(self.repo_path) if display_path.is_absolute() else display_path
 350                 ref_suffix = f" @ {active_ref}" if active_ref else ""
 351                 if display_start == display_end:
 352                     header = f"📍 `{display_rel}:{display_start}{ref_suffix}`"
 353                 else:
 354                     header = f"📍 `{display_rel}:{display_start}-{display_end}{ref_suffix}`"
 355 
 356             # Format code with line numbers and/or blame
 357             # Use remapped line numbers for display if remap_dirty_lines is enabled
 358             code_start_line = display_start if self.remap_dirty_lines else start_line
 359             if blame and not active_ref:
 360                 code_text = self.github.format_with_blame(code_text, code_start_line, display_path)
 361             elif line_numbers:
 362                 code_text = self._add_line_numbers(code_text, code_start_line)
 363 
 364             # Auto-detect language if not specified
 365             if not language:
 366                 suffix = display_path.suffix.lower()
 367                 language_map = {
 368                     ".cpp": "cpp",
 369                     ".cc": "cpp",
 370                     ".cxx": "cpp",
 371                     ".hpp": "cpp",
 372                     ".h": "cpp",
 373                     ".hxx": "cpp",
 374                     ".ipp": "cpp",  # Inline implementation files
 375                     ".macro": "cpp",  # C preprocessor macro files
 376                     ".c": "c",
 377                     ".py": "python",
 378                     ".js": "javascript",
 379                     ".ts": "typescript",
 380                     ".tsx": "tsx",
 381                     ".mts": "typescript",
 382                     ".cts": "typescript",
 383                     ".java": "java",
 384                     ".rs": "rust",
 385                     ".go": "go",
 386                     ".proto": "protobuf",
 387                 }
 388                 language = language_map.get(suffix, "text")
 389 
 390             # Build final output
 391             return f"{header}\n```{language}\n{code_text}\n```"
 392 
 393         except Exception as e:
 394             error_msg = f"❌ **ERROR**: {e}"
 395             logger.error(f"Code extraction failed: {e}")
 396             # Collect file as fixture if collection is enabled
 397             if resolved_path is not None:
 398                 _collect_error_fixture(resolved_path, str(e))
 399             return error_msg
 400 
 401         finally:
 402             # Clean up temp file if we created one
 403             if tmp_file and tmp_file.exists():
 404                 tmp_file.unlink()
```

The function handles a wide variety of extraction types — functions, structs, variables, macros, protobuf messages, enums, services, markers, and raw line ranges. It also supports nesting: you can extract a marker *within* a function by passing both `function=` and `marker=`.

When a `ChangesSet` is provided (validation mode), each extraction automatically calls `subtract()` to mark those lines as documented.

### The include() Function

Templates can compose by including other files. Plain markdown files are included verbatim; `.j2` files are rendered as templates with full access to `code()` and other functions:

📍 [`projected_source/core/renderer.py:516-539`](https://github.com/sublimator/projected-source/blob/1a63693f86b67f7cbfe9bfb603a20e8bcd892b38/projected_source/core/renderer.py#L516-L539)
```python
 516     def _include_function(self, path: str) -> str:
 517         """
 518         Include a file into the template output.
 519 
 520         .j2 files are rendered as Jinja2 templates (with access to code() etc).
 521         All other files are included as raw text.
 522 
 523         Args:
 524             path: Path relative to the template directory
 525 
 526         Returns:
 527             File contents (rendered if .j2)
 528 
 529         Examples:
 530             {{ include('background.md') }}
 531             {{ include('details.md.j2') }}
 532             {{ include('sections/intro.md') }}
 533         """
 534         if path.endswith(".j2"):
 535             template = self.env.get_template(path)
 536             return template.render()
 537         else:
 538             full_path = self.template_dir / path
 539             return full_path.read_text()
```

### Custom Tags

Projects can extend the template environment by placing a `.projected-source.py` file in the project. The renderer discovers it by walking up from the template directory to the git root:

📍 [`projected_source/core/renderer.py:574-602`](https://github.com/sublimator/projected-source/blob/1a63693f86b67f7cbfe9bfb603a20e8bcd892b38/projected_source/core/renderer.py#L574-L602)
```python
 574     def _find_custom_tags_file(self, start_path: Path) -> Optional[Path]:
 575         """
 576         Find .projected-source.py file by walking up from start_path.
 577         Stops at git root to avoid escaping the repository.
 578 
 579         Args:
 580             start_path: Path to start searching from (usually template dir)
 581 
 582         Returns:
 583             Path to .projected-source.py if found, None otherwise
 584         """
 585         current = start_path.resolve()
 586 
 587         # Use repo_path as the boundary (it's already the git root)
 588         git_root = self.repo_path
 589 
 590         while current >= git_root:
 591             custom_file = current / ".projected-source.py"
 592             if custom_file.exists():
 593                 logger.info(f"Found custom tags file at {custom_file}")
 594                 return custom_file
 595 
 596             # Move up one directory
 597             parent = current.parent
 598             if parent == current:  # Reached filesystem root
 599                 break
 600             current = parent
 601 
 602         return None
```

### Rendering

The public API is straightforward — `render_template()` for named templates and `render_template_file()` for file paths:

📍 [`projected_source/core/renderer.py:652-675`](https://github.com/sublimator/projected-source/blob/1a63693f86b67f7cbfe9bfb603a20e8bcd892b38/projected_source/core/renderer.py#L652-L675)
```python
 652     def render_template(self, template_name: str, **context) -> str:
 653         """
 654         Render a template with the given context.
 655 
 656         Args:
 657             template_name: Name of the template file
 658             **context: Additional context variables
 659 
 660         Returns:
 661             Rendered template as string
 662         """
 663         try:
 664             # Load custom tags from .projected-source.py if available
 665             template_path = self.template_dir / template_name
 666             self._load_custom_tags(template_path)
 667 
 668             template = self.env.get_template(template_name)
 669             return template.render(**context)
 670         except jinja2.TemplateNotFound:
 671             logger.error(f"Template not found: {template_name}")
 672             raise
 673         except Exception as e:
 674             logger.error(f"Template rendering failed: {e}")
 675             raise
```

---

## GitHub Integration

Every extracted code block can include a clickable GitHub permalink. The `GitHubIntegration` class handles the git plumbing — detecting the repository URL, mapping line numbers in dirty files to their committed counterparts, and generating blame annotations.

### Lazy Initialization

Repository info is loaded on first access. The class auto-detects the GitHub URL from the git remote, handling both SSH and HTTPS formats:

📍 [`projected_source/core/github.py:186-228`](https://github.com/sublimator/projected-source/blob/1a63693f86b67f7cbfe9bfb603a20e8bcd892b38/projected_source/core/github.py#L186-L228)
```python
 186     def _init_repo_info(self):
 187         """Lazy initialization of repository information."""
 188         if self._initialized:
 189             return
 190 
 191         try:
 192             # Get the remote origin URL
 193             origin_url = (
 194                 subprocess.check_output(
 195                     ["git", "remote", "get-url", "origin"], cwd=self.repo_path, stderr=subprocess.DEVNULL
 196                 )
 197                 .decode()
 198                 .strip()
 199             )
 200 
 201             # Get current commit hash
 202             self._commit_hash = (
 203                 subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=self.repo_path, stderr=subprocess.DEVNULL)
 204                 .decode()
 205                 .strip()
 206             )
 207 
 208             # Convert SSH/HTTPS URL to GitHub web URL
 209             if origin_url.startswith("git@github.com:"):
 210                 # SSH format: git@github.com:user/repo.git
 211                 repo_path = origin_url.replace("git@github.com:", "").replace(".git", "")
 212             elif "github.com" in origin_url:
 213                 # HTTPS format: https://github.com/user/repo.git
 214                 repo_path = re.sub(r"https?://github\.com/", "", origin_url).replace(".git", "")
 215             else:
 216                 logger.warning(f"Non-GitHub repository: {origin_url}")
 217                 self._initialized = True
 218                 return
 219 
 220             self._github_url = f"https://github.com/{repo_path}"
 221             logger.debug(f"GitHub URL: {self._github_url}, Commit: {self._commit_hash[:8]}")
 222 
 223         except subprocess.CalledProcessError as e:
 224             logger.warning(f"Git command failed: {e}")
 225         except Exception as e:
 226             logger.warning(f"Failed to get GitHub info: {e}")
 227 
 228         self._initialized = True
```

### Dirty File Line Mapping

When you're working on a file with uncommitted changes, the line numbers in your working copy won't match the committed version. The permalink needs to point to committed lines (which GitHub knows about), so the system maps working copy lines back to HEAD.

The full-diff parser builds a line-by-line mapping from new to old positions:

📍 [`projected_source/core/github.py:37-83`](https://github.com/sublimator/projected-source/blob/1a63693f86b67f7cbfe9bfb603a20e8bcd892b38/projected_source/core/github.py#L37-L83)
```python
  37 def build_line_mapping(diff_output: str) -> Dict[int, Optional[int]]:
  38     """
  39     Build a mapping from new line numbers to old line numbers by parsing diff content.
  40 
  41     Returns a dict where:
  42     - key: new line number
  43     - value: old line number, or None if the line was added (doesn't exist in old)
  44     """
  45     mapping: Dict[int, Optional[int]] = {}
  46     hunk_pattern = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
  47 
  48     old_line = 0
  49     new_line = 0
  50     in_hunk = False
  51 
  52     for line in diff_output.split("\n"):
  53         # Check for hunk header
  54         match = hunk_pattern.match(line)
  55         if match:
  56             old_line = int(match.group(1))
  57             new_line = int(match.group(3))
  58             in_hunk = True
  59             continue
  60 
  61         if not in_hunk:
  62             continue
  63 
  64         if line.startswith("+++") or line.startswith("---"):
  65             continue
  66 
  67         if line.startswith("+"):
  68             # Added line - exists in new file only
  69             mapping[new_line] = None
  70             new_line += 1
  71         elif line.startswith("-"):
  72             # Removed line - exists in old file only
  73             old_line += 1
  74         elif line.startswith(" ") or line == "":
  75             # Context line - exists in both
  76             mapping[new_line] = old_line
  77             old_line += 1
  78             new_line += 1
  79         elif line.startswith("\\"):
  80             # "\ No newline at end of file" - ignore
  81             continue
  82 
  83     return mapping
```

This mapping is used by `map_to_committed_line()`, which falls back gracefully — if a line was newly added, it finds the nearest existing line before it:

📍 [`projected_source/core/github.py:138-173`](https://github.com/sublimator/projected-source/blob/1a63693f86b67f7cbfe9bfb603a20e8bcd892b38/projected_source/core/github.py#L138-L173)
```python
 138 def map_line_to_committed_full(new_line: int, diff_output: str) -> int:
 139     """
 140     Map a line number using full diff parsing for accurate results.
 141 
 142     Args:
 143         new_line: Line number in the working copy (1-based)
 144         diff_output: Full git diff output
 145 
 146     Returns:
 147         Corresponding line number in HEAD
 148     """
 149     mapping = build_line_mapping(diff_output)
 150 
 151     # If we have a direct mapping for this line
 152     if new_line in mapping:
 153         old = mapping[new_line]
 154         if old is not None:
 155             return old
 156         # Line was added, find nearest non-added line before it
 157         for check_line in range(new_line - 1, 0, -1):
 158             if check_line in mapping and mapping[check_line] is not None:
 159                 result = mapping[check_line]
 160                 assert result is not None  # For type narrowing
 161                 return result
 162         # Fall back to line 1
 163         return 1
 164 
 165     # Line not in any hunk - calculate offset from hunks before it
 166     hunks = parse_diff_hunks(diff_output)
 167     offset = 0
 168     for old_start, old_count, new_start, new_count in hunks:
 169         if new_line < new_start:
 170             break
 171         offset += old_count - new_count
 172 
 173     return new_line + offset
```

### Permalink Generation

The `get_permalink()` method ties it all together — it maps lines, builds the URL with line anchors, and returns a markdown link:

📍 [`projected_source/core/github.py:324-409`](https://github.com/sublimator/projected-source/blob/1a63693f86b67f7cbfe9bfb603a20e8bcd892b38/projected_source/core/github.py#L324-L409)
```python
 324     def get_permalink(
 325         self, file_path: Path, start_line: int = None, end_line: int = None, display_committed_lines: bool = True
 326     ) -> str:
 327         """
 328         Generate a GitHub permalink for a file or line range.
 329 
 330         Args:
 331             file_path: Path to the file
 332             start_line: Optional start line number (1-based)
 333             end_line: Optional end line number (1-based)
 334             display_committed_lines: If True, display shows committed line numbers (matches link).
 335                                      If False, display shows working copy line numbers.
 336 
 337         Returns:
 338             Formatted markdown link or plain text reference
 339         """
 340         # Make path relative to repo root
 341         try:
 342             if file_path.is_absolute():
 343                 rel_path = file_path.relative_to(self.repo_path)
 344             else:
 345                 rel_path = file_path
 346         except ValueError:
 347             rel_path = file_path
 348 
 349         if self.github_url and self.commit_hash:
 350             # Map line numbers if file is dirty (has uncommitted changes like markers)
 351             committed_start = None
 352             committed_end = None
 353             # Track dirty state authoritatively, not via line-number drift —
 354             # a file can be edited without shifting the lines we render.
 355             is_dirty = self.is_file_dirty(file_path)
 356 
 357             if start_line is not None:
 358                 committed_start = self.map_to_committed_line(file_path, start_line)
 359                 if end_line is not None:
 360                     committed_end = self.map_to_committed_line(file_path, end_line)
 361 
 362             # Build GitHub URL with committed line numbers
 363             url = f"{self.github_url}/blob/{self.commit_hash}/{rel_path}"
 364 
 365             # Add line anchors if specified (using committed line numbers for URL)
 366             if committed_start is not None:
 367                 # Choose which line numbers to display
 368                 if display_committed_lines or not is_dirty:
 369                     display_start = committed_start
 370                     display_end = committed_end
 371                 else:
 372                     # start_line must be set if committed_start was computed
 373                     assert start_line is not None
 374                     display_start = start_line
 375                     display_end = end_line
 376 
 377                 # URL anchor must use committed line numbers
 378                 if committed_end and committed_end != committed_start:
 379                     url += f"#L{committed_start}-L{committed_end}"
 380                     if is_dirty:
 381                         logger.debug(
 382                             f"Dirty file: mapped lines {start_line}-{end_line} → {committed_start}-{committed_end}"
 383                         )
 384                 else:
 385                     url += f"#L{committed_start}"
 386 
 387                 # Display label uses whichever line space we're showing — when
 388                 # display_committed_lines=False, working-copy lines may span a
 389                 # range even if their committed counterparts collapse to one.
 390                 if display_end is not None and display_end != display_start:
 391                     display = f"{rel_path}:{display_start}-{display_end}"
 392                 else:
 393                     display = f"{rel_path}:{display_start}"
 394             else:
 395                 display = str(rel_path)
 396 
 397             # Surface dirty state so readers know the link points at HEAD content,
 398             # which may differ from what's rendered above.
 399             suffix = " *(uncommitted)*" if is_dirty else ""
 400             return f"📍 [`{display}`]({url}){suffix}"
 401         else:
 402             # No GitHub info, return plain text
 403             if start_line is not None:
 404                 if end_line and end_line != start_line:
 405                     return f"📍 `{rel_path}:{start_line}-{end_line}`"
 406                 else:
 407                     return f"📍 `{rel_path}:{start_line}`"
 408             else:
 409                 return f"📍 `{rel_path}`"
```

### Blame Support

For deeper code archaeology, `blame=True` annotates each line with its author, date, and commit hash:

📍 [`projected_source/core/github.py:472-502`](https://github.com/sublimator/projected-source/blob/1a63693f86b67f7cbfe9bfb603a20e8bcd892b38/projected_source/core/github.py#L472-L502)
```python
 472     def format_with_blame(self, code_text: str, start_line: int, file_path: Path) -> str:
 473         """
 474         Format code with git blame information.
 475 
 476         Args:
 477             code_text: The code to format
 478             start_line: Starting line number
 479             file_path: Path to the file
 480 
 481         Returns:
 482             Formatted code with blame info
 483         """
 484         lines = code_text.splitlines()
 485         end_line = start_line + len(lines) - 1
 486 
 487         blame_info = self.get_blame(file_path, start_line, end_line)
 488 
 489         formatted_lines = []
 490         for i, line in enumerate(lines):
 491             line_num = start_line + i
 492 
 493             if line_num in blame_info:
 494                 blame = blame_info[line_num]
 495                 # Format: line_num | commit | author | date | code
 496                 formatted_line = f"{line_num:4} │ {blame['commit']} │ {blame['author']:<20} │ {blame['date']} │ {line}"
 497             else:
 498                 formatted_line = f"{line_num:4} │ {line}"
 499 
 500             formatted_lines.append(formatted_line)
 501 
 502         return "\n".join(formatted_lines)
```

---

## Change Validation

One of the most powerful features: projected-source can verify that your documentation actually covers the code that changed. Run with `-V` and it diffs against a base commit, tracks which regions each `code()` call covers, and reports any gaps.

### ChangesSet

The `ChangesSet` class tracks changed regions as a set of non-overlapping intervals per file. It supports adding regions (which auto-merge overlapping ranges), subtracting regions (which can split intervals), and querying what's left uncovered:

📍 [`projected_source/core/changes_set.py:27-252`](https://github.com/sublimator/projected-source/blob/1a63693f86b67f7cbfe9bfb603a20e8bcd892b38/projected_source/core/changes_set.py#L27-L252)
```python
  27 class ChangesSet:
  28     """
  29     Set-like structure for tracking changed code regions.
  30 
  31     Supports adding regions (with automatic merging of overlapping/adjacent),
  32     subtracting regions (when claimed by documentation), and querying
  33     uncovered regions.
  34     """
  35 
  36     def __init__(self):
  37         # Dict[Path, List[Tuple[start, end]]] - sorted, non-overlapping regions
  38         self._regions: Dict[Path, List[Tuple[int, int]]] = {}
  39 
  40     @classmethod
  41     def from_diff(cls, base: Optional[str] = None, repo_path: Optional[Path] = None) -> "ChangesSet":
  42         """
  43         Build a ChangesSet from git diff against a base commit or range.
  44 
  45         Args:
  46             base: Base commit/branch, or a range like "HEAD~5..HEAD~2".
  47                   If no ".." present, diffs against HEAD. Auto-detected if None.
  48             repo_path: Path to git repository. Uses cwd if None.
  49 
  50         Returns:
  51             ChangesSet populated with all changed regions.
  52         """
  53         repo_path = repo_path or Path.cwd()
  54         base = base or cls.detect_base(repo_path)
  55 
  56         # Support commit ranges (e.g., "HEAD~5..HEAD~2") or simple base (e.g., "HEAD~5")
  57         diff_range = base if ".." in base else f"{base}..HEAD"
  58 
  59         changes = cls()
  60 
  61         # Get diff with file names and line numbers
  62         result = subprocess.run(
  63             ["git", "diff", diff_range, "--unified=3"],
  64             capture_output=True,
  65             cwd=repo_path,
  66             text=True,
  67         )
  68 
  69         if result.returncode != 0:
  70             raise RuntimeError(f"git diff failed: {result.stderr}")
  71 
  72         changes._parse_diff(result.stdout, repo_path)
  73         return changes
  74 
  75     @staticmethod
  76     def detect_base(repo_path: Path) -> str:
  77         """
  78         Auto-detect the base commit for diffing.
  79 
  80         Tries merge-base with main, then master, falls back to HEAD~1.
  81         """
  82         # Try main
  83         result = subprocess.run(
  84             ["git", "merge-base", "HEAD", "main"],
  85             capture_output=True,
  86             cwd=repo_path,
  87             text=True,
  88         )
  89         if result.returncode == 0:
  90             return result.stdout.strip()
  91 
  92         # Try master
  93         result = subprocess.run(
  94             ["git", "merge-base", "HEAD", "master"],
  95             capture_output=True,
  96             cwd=repo_path,
  97             text=True,
  98         )
  99         if result.returncode == 0:
 100             return result.stdout.strip()
 101 
 102         # Fall back to parent commit
 103         return "HEAD~1"
 104 
 105     def _parse_diff(self, diff_output: str, repo_path: Path) -> None:
 106         """Parse unified diff output and populate regions."""
 107         current_file: Optional[Path] = None
 108         current_new_line = 0
 109 
 110         for line in diff_output.splitlines():
 111             # New file header: +++ b/path/to/file
 112             if line.startswith("+++ b/"):
 113                 file_path = line[6:]  # Strip "+++ b/"
 114                 current_file = repo_path / file_path
 115             # Deleted-file sentinel: '+++ /dev/null' — skip hunk lines so we
 116             # don't spuriously record additions against the previous file.
 117             elif line.startswith("+++ ") and "/dev/null" in line:
 118                 current_file = None
 119 
 120             # Hunk header: @@ -old_start,old_count +new_start,new_count @@
 121             elif line.startswith("@@"):
 122                 # Parse new file position
 123                 parts = line.split()
 124                 if len(parts) >= 3:
 125                     new_range = parts[2]  # e.g., "+10,5" or "+10"
 126                     if new_range.startswith("+"):
 127                         new_range = new_range[1:]
 128                         if "," in new_range:
 129                             current_new_line = int(new_range.split(",")[0])
 130                         else:
 131                             current_new_line = int(new_range)
 132 
 133             # Added or context line - track position
 134             elif current_file and not line.startswith("-"):
 135                 if line.startswith("+") or line.startswith(" "):
 136                     # This line exists in the new version
 137                     if line.startswith("+"):
 138                         # Added line - definitely needs coverage
 139                         self.add(current_file, current_new_line, current_new_line)
 140                     elif line.startswith(" "):
 141                         # Context line around a change - also needs coverage
 142                         # (user chose "all changed" which includes context)
 143                         self.add(current_file, current_new_line, current_new_line)
 144                     current_new_line += 1
 145 
 146             # Deleted line - doesn't increment new line counter
 147             elif line.startswith("-") and not line.startswith("---"):
 148                 pass  # Deletion - surrounding context already captured
 149 
 150     def add(self, file_path: Path, start: int, end: int) -> None:
 151         """
 152         Add a region, merging with overlapping or adjacent regions.
 153 
 154         Args:
 155             file_path: Path to the file
 156             start: Start line (1-based, inclusive)
 157             end: End line (1-based, inclusive)
 158         """
 159         if start > end:
 160             start, end = end, start
 161 
 162         regions = self._regions.setdefault(file_path, [])
 163 
 164         # Add new region and re-merge everything
 165         regions.append((start, end))
 166         self._regions[file_path] = self._merge_sorted(sorted(regions))
 167 
 168     def _merge_sorted(self, regions: List[Tuple[int, int]]) -> List[Tuple[int, int]]:
 169         """Merge a sorted list of potentially overlapping regions."""
 170         if not regions:
 171             return []
 172 
 173         result = [regions[0]]
 174         for start, end in regions[1:]:
 175             last_start, last_end = result[-1]
 176             if start <= last_end + 1:
 177                 # Overlapping or adjacent - merge
 178                 result[-1] = (last_start, max(last_end, end))
 179             else:
 180                 result.append((start, end))
 181         return result
 182 
 183     def subtract(self, file_path: Path, start: int, end: int) -> None:
 184         """
 185         Remove a region (mark as covered by documentation).
 186 
 187         May split existing regions if the subtracted region is in the middle.
 188 
 189         Args:
 190             file_path: Path to the file
 191             start: Start line (1-based, inclusive)
 192             end: End line (1-based, inclusive)
 193         """
 194         if file_path not in self._regions:
 195             return
 196 
 197         if start > end:
 198             start, end = end, start
 199 
 200         new_regions: List[Tuple[int, int]] = []
 201 
 202         for reg_start, reg_end in self._regions[file_path]:
 203             # No overlap - keep as is
 204             if end < reg_start or start > reg_end:
 205                 new_regions.append((reg_start, reg_end))
 206 
 207             # Full coverage - remove entirely
 208             elif start <= reg_start and end >= reg_end:
 209                 pass  # Don't add it
 210 
 211             # Partial overlap - may need to split
 212             else:
 213                 # Left remainder
 214                 if reg_start < start:
 215                     new_regions.append((reg_start, start - 1))
 216                 # Right remainder
 217                 if reg_end > end:
 218                     new_regions.append((end + 1, reg_end))
 219 
 220         if new_regions:
 221             self._regions[file_path] = new_regions
 222         else:
 223             del self._regions[file_path]
 224 
 225     def uncovered(self) -> List[ChangeRegion]:
 226         """Return list of regions not yet claimed by documentation."""
 227         result = []
 228         for file_path, regions in sorted(self._regions.items()):
 229             for start, end in regions:
 230                 result.append(ChangeRegion(file_path, start, end))
 231         return result
 232 
 233     def is_complete(self) -> bool:
 234         """Return True if all regions have been claimed."""
 235         return len(self._regions) == 0
 236 
 237     def files(self) -> List[Path]:
 238         """Return list of files with uncovered changes."""
 239         return list(self._regions.keys())
 240 
 241     def __len__(self) -> int:
 242         """Return total number of uncovered regions."""
 243         return sum(len(regions) for regions in self._regions.values())
 244 
 245     def __bool__(self) -> bool:
 246         """Return True if there are uncovered regions."""
 247         return len(self._regions) > 0
 248 
 249     def __repr__(self) -> str:
 250         total = len(self)
 251         files = len(self._regions)
 252         return f"ChangesSet({total} regions in {files} files)"
```

### Building from Git Diff

`from_diff()` parses unified diff output to populate the set. It supports both simple base refs (`origin/main`) and explicit ranges (`HEAD~5..HEAD~2`):

📍 [`projected_source/core/changes_set.py:40-73`](https://github.com/sublimator/projected-source/blob/1a63693f86b67f7cbfe9bfb603a20e8bcd892b38/projected_source/core/changes_set.py#L40-L73)
```python
  40     @classmethod
  41     def from_diff(cls, base: Optional[str] = None, repo_path: Optional[Path] = None) -> "ChangesSet":
  42         """
  43         Build a ChangesSet from git diff against a base commit or range.
  44 
  45         Args:
  46             base: Base commit/branch, or a range like "HEAD~5..HEAD~2".
  47                   If no ".." present, diffs against HEAD. Auto-detected if None.
  48             repo_path: Path to git repository. Uses cwd if None.
  49 
  50         Returns:
  51             ChangesSet populated with all changed regions.
  52         """
  53         repo_path = repo_path or Path.cwd()
  54         base = base or cls.detect_base(repo_path)
  55 
  56         # Support commit ranges (e.g., "HEAD~5..HEAD~2") or simple base (e.g., "HEAD~5")
  57         diff_range = base if ".." in base else f"{base}..HEAD"
  58 
  59         changes = cls()
  60 
  61         # Get diff with file names and line numbers
  62         result = subprocess.run(
  63             ["git", "diff", diff_range, "--unified=3"],
  64             capture_output=True,
  65             cwd=repo_path,
  66             text=True,
  67         )
  68 
  69         if result.returncode != 0:
  70             raise RuntimeError(f"git diff failed: {result.stderr}")
  71 
  72         changes._parse_diff(result.stdout, repo_path)
  73         return changes
```

The diff parser walks through hunk headers and added lines to build up the initial set of changed regions:

📍 [`projected_source/core/changes_set.py:105-148`](https://github.com/sublimator/projected-source/blob/1a63693f86b67f7cbfe9bfb603a20e8bcd892b38/projected_source/core/changes_set.py#L105-L148)
```python
 105     def _parse_diff(self, diff_output: str, repo_path: Path) -> None:
 106         """Parse unified diff output and populate regions."""
 107         current_file: Optional[Path] = None
 108         current_new_line = 0
 109 
 110         for line in diff_output.splitlines():
 111             # New file header: +++ b/path/to/file
 112             if line.startswith("+++ b/"):
 113                 file_path = line[6:]  # Strip "+++ b/"
 114                 current_file = repo_path / file_path
 115             # Deleted-file sentinel: '+++ /dev/null' — skip hunk lines so we
 116             # don't spuriously record additions against the previous file.
 117             elif line.startswith("+++ ") and "/dev/null" in line:
 118                 current_file = None
 119 
 120             # Hunk header: @@ -old_start,old_count +new_start,new_count @@
 121             elif line.startswith("@@"):
 122                 # Parse new file position
 123                 parts = line.split()
 124                 if len(parts) >= 3:
 125                     new_range = parts[2]  # e.g., "+10,5" or "+10"
 126                     if new_range.startswith("+"):
 127                         new_range = new_range[1:]
 128                         if "," in new_range:
 129                             current_new_line = int(new_range.split(",")[0])
 130                         else:
 131                             current_new_line = int(new_range)
 132 
 133             # Added or context line - track position
 134             elif current_file and not line.startswith("-"):
 135                 if line.startswith("+") or line.startswith(" "):
 136                     # This line exists in the new version
 137                     if line.startswith("+"):
 138                         # Added line - definitely needs coverage
 139                         self.add(current_file, current_new_line, current_new_line)
 140                     elif line.startswith(" "):
 141                         # Context line around a change - also needs coverage
 142                         # (user chose "all changed" which includes context)
 143                         self.add(current_file, current_new_line, current_new_line)
 144                     current_new_line += 1
 145 
 146             # Deleted line - doesn't increment new line counter
 147             elif line.startswith("-") and not line.startswith("---"):
 148                 pass  # Deletion - surrounding context already captured
```

### Subtract and Query

As templates render, each `code()` call subtracts its extracted region. The `subtract()` method handles partial overlaps — if documentation covers the middle of a changed region, it splits into two uncovered remainders:

📍 [`projected_source/core/changes_set.py:183-223`](https://github.com/sublimator/projected-source/blob/1a63693f86b67f7cbfe9bfb603a20e8bcd892b38/projected_source/core/changes_set.py#L183-L223)
```python
 183     def subtract(self, file_path: Path, start: int, end: int) -> None:
 184         """
 185         Remove a region (mark as covered by documentation).
 186 
 187         May split existing regions if the subtracted region is in the middle.
 188 
 189         Args:
 190             file_path: Path to the file
 191             start: Start line (1-based, inclusive)
 192             end: End line (1-based, inclusive)
 193         """
 194         if file_path not in self._regions:
 195             return
 196 
 197         if start > end:
 198             start, end = end, start
 199 
 200         new_regions: List[Tuple[int, int]] = []
 201 
 202         for reg_start, reg_end in self._regions[file_path]:
 203             # No overlap - keep as is
 204             if end < reg_start or start > reg_end:
 205                 new_regions.append((reg_start, reg_end))
 206 
 207             # Full coverage - remove entirely
 208             elif start <= reg_start and end >= reg_end:
 209                 pass  # Don't add it
 210 
 211             # Partial overlap - may need to split
 212             else:
 213                 # Left remainder
 214                 if reg_start < start:
 215                     new_regions.append((reg_start, start - 1))
 216                 # Right remainder
 217                 if reg_end > end:
 218                     new_regions.append((end + 1, reg_end))
 219 
 220         if new_regions:
 221             self._regions[file_path] = new_regions
 222         else:
 223             del self._regions[file_path]
```

After rendering, `uncovered()` returns whatever's left:

📍 [`projected_source/core/changes_set.py:225-231`](https://github.com/sublimator/projected-source/blob/1a63693f86b67f7cbfe9bfb603a20e8bcd892b38/projected_source/core/changes_set.py#L225-L231)
```python
 225     def uncovered(self) -> List[ChangeRegion]:
 226         """Return list of regions not yet claimed by documentation."""
 227         result = []
 228         for file_path, regions in sorted(self._regions.items()):
 229             for start, end in regions:
 230                 result.append(ChangeRegion(file_path, start, end))
 231         return result
```

---

## CLI Interface

The CLI is built with Click. The main entry point registers all commands:

📍 [`projected_source/cli/__init__.py:19-29`](https://github.com/sublimator/projected-source/blob/1a63693f86b67f7cbfe9bfb603a20e8bcd892b38/projected_source/cli/__init__.py#L19-L29)
```python
  19 @click.group()
  20 @click.option("--verbose", "-v", is_flag=True, help="Enable verbose logging")
  21 @click.option("--debug", "-d", is_flag=True, help="Enable debug logging")
  22 def cli(verbose, debug):
  23     """Extract and project source code into documentation."""
  24     if debug:
  25         setup_logging(logging.DEBUG)
  26     elif verbose:
  27         setup_logging(logging.INFO)
  28     else:
  29         setup_logging(logging.WARNING)
```

### The render Command

The primary command renders `.md.j2` templates. It handles single files, directories, and stdin. Key options include `--validate-changes` for coverage checking, `--commit` for rendering against historical commits, and `--remap-dirty-lines` for sharing docs from dirty working copies.

Single-file rendering resolves the template path, creates a `TemplateRenderer`, and writes the output:

📍 [`projected_source/cli/render.py:364-394`](https://github.com/sublimator/projected-source/blob/1a63693f86b67f7cbfe9bfb603a20e8bcd892b38/projected_source/cli/render.py#L364-L394)
```python
 364 def _render_file(
 365     input_file, output_file, repo_path, output_to_stdout, remap_dirty_lines=False, changes_set=None, header=False
 366 ):
 367     """Render a single template file."""
 368     # Determine template directory
 369     template_dir = input_file.parent
 370     template_name = input_file.name
 371 
 372     # Create renderer
 373     renderer = TemplateRenderer(
 374         template_dir=template_dir, repo_path=repo_path, remap_dirty_lines=remap_dirty_lines, changes_set=changes_set
 375     )
 376 
 377     try:
 378         rendered = renderer.render_template(template_name)
 379 
 380         if header:
 381             rendered = _build_header(template_name, repo_path) + rendered
 382 
 383         if output_to_stdout:
 384             # Output to stdout
 385             click.echo(rendered)
 386         else:
 387             # Output to file
 388             output_file.parent.mkdir(parents=True, exist_ok=True)
 389             output_file.write_text(rendered)
 390             console.print(f"[green]✓[/green] {input_file} → {output_file}")
 391 
 392     except Exception as e:
 393         console.print(f"[red]✗ Failed to render {input_file}:[/red] {e}")
 394         sys.exit(1)
```

Directory rendering walks the tree and renders all `.j2` files:

📍 [`projected_source/cli/render.py:397-454`](https://github.com/sublimator/projected-source/blob/1a63693f86b67f7cbfe9bfb603a20e8bcd892b38/projected_source/cli/render.py#L397-L454)
```python
 397 def _render_directory(input_dir, output_dir, repo_path, remap_dirty_lines=False, changes_set=None, header=False):
 398     """Render all templates in a directory."""
 399     templates = list(input_dir.glob("**/*.j2"))
 400 
 401     if not templates:
 402         console.print(f"[yellow]No .j2 templates found in {input_dir}[/yellow]")
 403         return
 404 
 405     console.print(f"[bold]Processing {len(templates)} templates from {input_dir}[/bold]")
 406 
 407     # Create renderer
 408     renderer = TemplateRenderer(
 409         template_dir=input_dir, repo_path=repo_path, remap_dirty_lines=remap_dirty_lines, changes_set=changes_set
 410     )
 411 
 412     # Track results
 413     success_count = 0
 414     failed = []
 415 
 416     # Process each template
 417     for template_path in templates:
 418         rel_path = template_path.relative_to(input_dir)
 419 
 420         # Determine output path (strip .j2 extension)
 421         if rel_path.suffix == ".j2":
 422             output_rel_path = rel_path.with_suffix("")
 423         else:
 424             output_rel_path = rel_path
 425 
 426         output_path_full = output_dir / output_rel_path
 427 
 428         try:
 429             # Render template
 430             rendered = renderer.render_template(str(rel_path))
 431 
 432             if header:
 433                 rendered = _build_header(str(rel_path), repo_path) + rendered
 434 
 435             # Write output
 436             output_path_full.parent.mkdir(parents=True, exist_ok=True)
 437             output_path_full.write_text(rendered)
 438 
 439             console.print(f"  [green]✓[/green] {rel_path} → {output_rel_path}")
 440             success_count += 1
 441 
 442         except Exception as e:
 443             console.print(f"  [red]✗[/red] {rel_path}: {e}")
 444             failed.append((rel_path, str(e)))
 445 
 446     # Summary
 447     console.print("\n[bold]Summary:[/bold]")
 448     console.print(f"  [green]{success_count} templates rendered successfully[/green]")
 449 
 450     if failed:
 451         console.print(f"  [red]{len(failed)} templates failed:[/red]")
 452         for template, error in failed:
 453             console.print(f"    • {template}: {error}")
 454         sys.exit(1)
```

### Symbol Discovery

The `list-functions` command is essential for authoring templates — it shows every extractable symbol in a file, including the parameter you'd use in a `code()` call:

📍 [`projected_source/cli/list_symbols.py:15-107`](https://github.com/sublimator/projected-source/blob/1a63693f86b67f7cbfe9bfb603a20e8bcd892b38/projected_source/cli/list_symbols.py#L15-L107)
```python
  15 @click.command("list-functions")
  16 @click.argument("file", required=False, type=click.Path(exists=True, dir_okay=False))
  17 @click.option(
  18     "--include-tests",
  19     is_flag=True,
  20     default=False,
  21     help="Rust only: include items inside #[cfg(test)] modules (hidden by default).",
  22 )
  23 def list_functions(file, include_tests):
  24     """List extractable symbols in a file.
  25 
  26     When FILE is given, lists all functions, classes, structs, enums,
  27     variables, and markers that can be extracted with code() calls.
  28 
  29     When no FILE is given, shows available extraction parameters.
  30     """
  31     if not file:
  32         _show_params_table()
  33         return
  34 
  35     file_path = Path(file).resolve()
  36 
  37     try:
  38         extractor = get_extractor(file_path)
  39     except ValueError as e:
  40         console.print(f"[red]{e}[/red]")
  41         raise SystemExit(1)
  42 
  43     if not hasattr(extractor, "list_symbols"):
  44         console.print(f"[red]Symbol listing not supported for {file_path.suffix} files[/red]")
  45         raise SystemExit(1)
  46 
  47     list_kwargs = {}
  48     if include_tests and "include_tests" in inspect.signature(extractor.list_symbols).parameters:
  49         list_kwargs["include_tests"] = True
  50 
  51     symbols = extractor.list_symbols(file_path, **list_kwargs)
  52 
  53     if not symbols:
  54         console.print(f"[yellow]No extractable symbols found in {file}[/yellow]")
  55         return
  56 
  57     # Detect overloaded functions
  58     func_names = [s["name"] for s in symbols if s["param"] == "function"]
  59     name_counts = Counter(func_names)
  60     overloaded = {name for name, count in name_counts.items() if count > 1}
  61 
  62     # Group by param
  63     groups = {}
  64     for sym in symbols:
  65         param = sym["param"]
  66         if param not in groups:
  67             groups[param] = []
  68         groups[param].append(sym)
  69 
  70     # Display
  71     console.print(f"\n[bold]{file}[/bold]\n")
  72 
  73     display_order = ["function", "struct", "var", "message", "enum", "service", "marker"]
  74 
  75     for param in display_order:
  76         if param not in groups:
  77             continue
  78 
  79         syms = groups[param]
  80         count = len(syms)
  81         console.print(f"  [bold]{param}=[/bold] [dim]({count})[/dim]")
  82 
  83         for sym in syms:
  84             name = sym["name"]
  85             line = sym["line"]
  86             kind = sym["kind"]
  87 
  88             parts = []
  89 
  90             # Show kind if it differs from param (e.g. class vs struct param)
  91             if kind != param:
  92                 parts.append(f"[dim]{kind}[/dim]")
  93 
  94             # Line info
  95             if sym.get("end_line"):
  96                 parts.append(f"[dim]lines {line}-{sym['end_line']}[/dim]")
  97             else:
  98                 parts.append(f"[dim]line {line}[/dim]")
  99 
 100             # Show signature hint for overloaded functions
 101             if name in overloaded and sym.get("signature"):
 102                 parts.append(f"[dim]signature='{sym['signature']}'[/dim]")
 103 
 104             extra = "  ".join(parts)
 105             console.print(f"    [cyan]'{name}'[/cyan]  {extra}")
 106 
 107         console.print()
```