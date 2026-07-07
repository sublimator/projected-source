<!--
rendered_from: system-overview.md.j2
rendered_at: 2026-07-07T12:40:15Z
branch: main
commit: 43c6fe7
commit_message: feat: add C++ marker enclosure context
-->

---

<sub>Last updated: 2026-07-07 | branch: main | commit: 43c6fe7 (feat: add C++ marker enclosure context)</sub>

---






# projected-source: System Overview

**projected-source** is a documentation tool that extracts code from source files and injects it into Jinja2 templates, creating documentation that stays synchronized with the codebase. It uses tree-sitter for accurate AST-based parsing and supports multiple languages through extractor plugins, including C/C++, Protocol Buffers, Python, JavaScript/TypeScript, Java, Rust, and Lean.

The core idea: write narrative documentation in Markdown templates (`.md.j2`), use `{{ code() }}` calls to pull in the exact code you're describing, and the rendered output always reflects the current state of the source.

---

## Data Structures

Before diving into how extraction works, let's look at the types that flow through the system.

### ExtractionResult

Every time code is extracted from a source file — whether a function, struct, or marker region — the result is packaged as an `ExtractionResult`. This dataclass carries the extracted text along with precise location metadata:

📍 [`projected_source/languages/extraction_result.py:9-36`](https://github.com/sublimator/projected-source/blob/43c6fe74cd655402f491d196271da65d39199c09/projected_source/languages/extraction_result.py#L9-L36)
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

### EnclosedMarkerResult

Marker extracts can also carry their outer context. `EnclosedMarkerResult` keeps the marker body and marker line range as the primary extraction, while preserving the enclosing function/class/declaration range for rendering surrounding context:

📍 [`projected_source/languages/extraction_result.py:39-69`](https://github.com/sublimator/projected-source/blob/43c6fe74cd655402f491d196271da65d39199c09/projected_source/languages/extraction_result.py#L39-L69)
```python
  39 @dataclass
  40 class EnclosedMarkerResult:
  41     """A marker extraction plus the enclosing source range that contains it."""
  42
  43     marker_text: str
  44     marker_start_line: int
  45     marker_end_line: int
  46     enclosure_text: str
  47     enclosure_start_line: int
  48     enclosure_end_line: int
  49     enclosure_kind: Optional[str] = None
  50     enclosure_name: Optional[str] = None
  51
  52     @property
  53     def text(self) -> str:
  54         """Marker text, matching the legacy extraction result shape."""
  55         return self.marker_text
  56
  57     @property
  58     def start_line(self) -> int:
  59         """Marker start line, matching the legacy extraction result shape."""
  60         return self.marker_start_line
  61
  62     @property
  63     def end_line(self) -> int:
  64         """Marker end line, matching the legacy extraction result shape."""
  65         return self.marker_end_line
  66
  67     def to_tuple(self) -> tuple:
  68         """For backwards compatibility with marker extraction APIs."""
  69         return (self.marker_text, self.marker_start_line, self.marker_end_line)
```

Permalinks and source location metadata use the marker range. Validation coverage uses the displayed segments, so rendered enclosure head/tail lines count as documented when context is shown. C/C++ extractor-backed marker extracts default to `enclosure_context=3`, which renders selected head and tail lines from the enclosure around the marker body without changing the marker's own source location. Other languages currently keep exact marker output unless they add an enclosed marker result.

### ChangeRegion

When validating that documentation covers code changes, individual changed regions are represented as `ChangeRegion` — a simple dataclass tying a file path to a line range:

📍 [`projected_source/core/changes_set.py:15-24`](https://github.com/sublimator/projected-source/blob/43c6fe74cd655402f491d196271da65d39199c09/projected_source/core/changes_set.py#L15-L24)
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

📍 [`projected_source/languages/__init__.py:19-44`](https://github.com/sublimator/projected-source/blob/43c6fe74cd655402f491d196271da65d39199c09/projected_source/languages/__init__.py#L19-L44)
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
  38     ".js": TypeScriptExtractor,  # JavaScript — TS grammar parses plain JS
  39     ".mjs": TypeScriptExtractor,  # JavaScript ES module
  40     ".cjs": TypeScriptExtractor,  # JavaScript CommonJS module
  41     ".java": JavaExtractor,  # Java
  42     ".rs": RustExtractor,  # Rust
  43     ".lean": LeanExtractor,  # Lean 4
  44 }
```

When a `code()` call needs to extract from a file, it calls `get_extractor()` which looks up the right class by file extension and instantiates it:

📍 [`projected_source/languages/__init__.py:47-69`](https://github.com/sublimator/projected-source/blob/43c6fe74cd655402f491d196271da65d39199c09/projected_source/languages/__init__.py#L47-L69)
```python
  47 def get_extractor(file_path: Path):
  48     """
  49     Get the appropriate extractor for a file based on its extension.
  50
  51     Args:
  52         file_path: Path to the file
  53
  54     Returns:
  55         An extractor instance
  56
  57     Raises:
  58         ValueError: If no extractor is available for the file type
  59     """
  60     suffix = file_path.suffix.lower()
  61
  62     if suffix not in EXTRACTORS:
  63         supported = ", ".join(EXTRACTORS.keys())
  64         raise ValueError(f"No extractor for {suffix} files. Supported: {supported}")
  65
  66     extractor_class = EXTRACTORS[suffix]
  67     if extractor_class is TypeScriptExtractor and suffix == ".tsx":
  68         return extractor_class(tsx=True)
  69     return extractor_class()
```

### BaseExtractor

All language extractors inherit from `BaseExtractor`, which provides the tree-sitter parser setup, line extraction, and the marker system. The marker system lets you tag regions of source code with `//@@start name` and `//@@end name` comments, then extract just that region:

📍 [`projected_source/core/extractor.py:17-134`](https://github.com/sublimator/projected-source/blob/43c6fe74cd655402f491d196271da65d39199c09/projected_source/core/extractor.py#L17-L134)
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

The `TemplateRenderer` is the heart of the system. It creates a Jinja2 environment and registers template functions — `code()`, `include()`, `include_body()`, and `ignore_changes()` — that templates use to pull in live code.

### Initialization

When a renderer is created, it sets up the Jinja2 environment with the template directory as the loader root, and registers the extraction functions as globals:

📍 [`projected_source/core/renderer.py:89-134`](https://github.com/sublimator/projected-source/blob/43c6fe74cd655402f491d196271da65d39199c09/projected_source/core/renderer.py#L89-L134)
```python
  89     def __init__(
  90         self,
  91         template_dir: Path = None,
  92         repo_path: Path = None,
  93         remap_dirty_lines: bool = False,
  94         changes_set: "ChangesSet" = None,
  95         default_enclosure_context: int = 3,
  96     ):
  97         """
  98         Initialize the renderer.
  99
 100         Args:
 101             template_dir: Directory containing templates (default: current dir)
 102             repo_path: Repository root path (default: current dir)
 103             remap_dirty_lines: If True, remap line numbers in dirty files to match
 104                                committed version (for sharing). Affects permalinks
 105                                and code block line numbers.
 106             changes_set: Optional ChangesSet for tracking documentation coverage.
 107                          When provided, each code() call will mark its region as
 108                          covered. Check changes_set.uncovered() after rendering.
 109             default_enclosure_context: Default C/C++ enclosure_context for marker code() calls
 110                                       that do not specify it explicitly.
 111         """
 112         self.template_dir = template_dir or Path.cwd()
 113         self.repo_path = repo_path or Path.cwd()
 114         self.remap_dirty_lines = remap_dirty_lines
 115         self.changes_set = changes_set
 116         self.default_enclosure_context = self._normalize_enclosure_context(default_enclosure_context)
 117         self.github = GitHubIntegration(self.repo_path)
 118
 119         # Create Jinja2 environment
 120         self.env = jinja2.Environment(
 121             loader=jinja2.FileSystemLoader(str(self.template_dir)),
 122             trim_blocks=True,
 123             lstrip_blocks=True,
 124             extensions=[CodeContextExtension],
 125         )
 126
 127         # Register custom functions
 128         self.env.globals["code"] = self._code_function
 129         self.env.globals["ghc"] = self._code_function  # Alias for compatibility
 130         self.env.globals["ignore_changes"] = self._ignore_changes_function
 131         self.env.globals["include"] = self._include_function
 132         self.env.globals["include_body"] = self._include_body_function
 133         self.env.globals["set_code_context"] = self._set_code_context_function
 134         self.env.globals["set_code_root"] = self._set_code_root_function
```

### The code() Function

This is the workhorse. Every `{{ code('file.cpp', function='foo') }}` call in a template invokes `_code_function`. It resolves the file path, picks the right extractor, extracts the requested symbol, optionally generates a GitHub permalink, adds line numbers, and returns formatted markdown:

📍 [`projected_source/core/renderer.py:139-572`](https://github.com/sublimator/projected-source/blob/43c6fe74cd655402f491d196271da65d39199c09/projected_source/core/renderer.py#L139-L572)
```python
 139     def _code_function(
 140         self,
 141         file_path: str,
 142         function: str = None,
 143         struct: str = None,
 144         var: str = None,
 145         function_macro: Union[str, Dict] = None,
 146         macro_definition: str = None,
 147         lines: Tuple[int, int] = None,
 148         marker: str = None,
 149         signature: str = None,
 150         message: str = None,
 151         enum: str = None,
 152         service: str = None,
 153         github: bool = True,
 154         blame: bool = False,
 155         line_numbers: bool = True,
 156         language: str = None,
 157         ref: str = None,
 158         root: str = None,
 159         enclosure: str = None,
 160         enclosure_context: int = None,
 161     ) -> str:
 162         """
 163         Universal code extraction function for templates.
 164
 165         Args:
 166             file_path: Path to the source file
 167             function: Function name to extract
 168             struct: Struct/class/enum name to extract (C/C++)
 169             var: Variable/constant declaration to extract (C/C++)
 170             function_macro: Macro that defines a function (dict with 'name' and optional 'arg0', 'arg1', etc)
 171             macro_definition: Macro definition name to extract (#define statement)
 172             lines: Tuple of (start_line, end_line) to extract
 173             marker: Marker name to extract between //@@start and //@@end
 174             signature: String to match against parameter types for overload disambiguation.
 175                        Use partial type names like "TMProposeSet" to select a specific overload.
 176             message: Message name to extract (protobuf)
 177             enum: Enum name to extract (protobuf)
 178             service: Service name to extract (protobuf)
 179             github: Include GitHub permalink (default: True)
 180             blame: Include git blame info (default: False)
 181             line_numbers: Show line numbers (default: True)
 182             language: Language for syntax highlighting (auto-detected if None)
 183             enclosure: Set to "auto" with C/C++ marker= to find the closest enclosing symbol.
 184             enclosure_context: For supported marker extractions, show the first
 185                                and last N lines of the enclosing symbol around the marker.
 186
 187         Returns:
 188             Formatted markdown with code block
 189
 190         Examples in templates:
 191             {{ code('src/file.cpp', function='myFunc') }}
 192             {{ code('src/file.cpp', function='onMessage', signature='TMProposeSet') }}
 193             {{ code('src/file.cpp', struct='MyClass') }}
 194             {{ code('src/file.cpp', var='errorInfos') }}
 195             {{ code('src/file.cpp', lines=(10, 20)) }}
 196             {{ code('src/file.cpp', marker='example1') }}
 197             {{ code('src/proto/file.proto', message='MyMessage') }}
 198             {{ code('src/proto/file.proto', enum='MyEnum') }}
 199         """
 200         tmp_file = None
 201         resolved_path: Optional[Path] = None
 202         display_segments: Optional[List[Tuple[str, int, int]]] = None
 203         try:
 204             context_lines = self._normalize_enclosure_context(
 205                 self.default_enclosure_context if enclosure_context is None else enclosure_context
 206             )
 207             enclosure_mode = (enclosure or "").lower()
 208             if enclosure_mode and enclosure_mode != "auto":
 209                 raise ValueError("enclosure must be 'auto' when specified")
 210             if enclosure_mode and not marker:
 211                 raise ValueError("enclosure requires marker=")
 212             explicit_enclosure = bool(enclosure_mode)
 213             require_enclosure_context = explicit_enclosure or (
 214                 context_lines > 0 and enclosure_context is not None
 215             )
 216
 217             # Apply root prefix: per-call root= overrides context code_root
 218             code_root = root or str(self.env.globals.get("code_root", ""))
 219             if code_root and not Path(file_path).is_absolute():
 220                 file_path = str(Path(code_root) / file_path)
 221
 222             # Determine active ref (per-call overrides context)
 223             active_ref = ref or str(self.env.globals.get("code_ref", ""))
 224
 225             # Resolve file path relative to repo
 226             resolved_path = Path(file_path)
 227             if not resolved_path.is_absolute():
 228                 resolved_path = self.repo_path / resolved_path
 229
 230             # If a git ref is active, fetch file content from that ref
 231             if active_ref:
 232                 rel_path = file_path
 233                 # Ensure relative path for git show
 234                 try:
 235                     rel_path = str(Path(file_path).relative_to(self.repo_path))
 236                 except ValueError:
 237                     # Already relative
 238                     rel_path = file_path
 239                 content = subprocess.check_output(
 240                     ["git", "show", f"{active_ref}:{rel_path}"],
 241                     cwd=self.repo_path,
 242                     stderr=subprocess.DEVNULL,
 243                 )
 244                 tmp_file = Path(tempfile.mktemp(suffix=resolved_path.suffix))
 245                 tmp_file.write_bytes(content)
 246                 resolved_path = tmp_file
 247
 248             # Get the appropriate extractor
 249             extractor = get_extractor(resolved_path)
 250
 251             # Extract code based on parameters
 252             if function:
 253                 # Check if we also have a marker - extract marker within function
 254                 if marker:
 255                     if (context_lines or explicit_enclosure) and hasattr(extractor, "extract_function_marker_enclosed"):
 256                         enclosed = self._call_function_marker_method(
 257                             extractor.extract_function_marker_enclosed,
 258                             resolved_path,
 259                             function,
 260                             marker,
 261                             signature,
 262                         )
 263                         code_text, start_line, end_line = enclosed.to_tuple()
 264                         if context_lines:
 265                             display_segments = self._build_enclosure_segments(
 266                                 resolved_path, enclosed, context_lines
 267                             )
 268                         logger.info(
 269                             f"Extracted marker '{marker}' with function enclosure "
 270                             f"'{function}' in {file_path}"
 271                         )
 272                     elif require_enclosure_context:
 273                         return "❌ **ERROR**: Function marker enclosure not supported for this file type"
 274                     elif hasattr(extractor, "extract_function_marker"):
 275                         code_text, start_line, end_line = self._call_function_marker_method(
 276                             extractor.extract_function_marker,
 277                             resolved_path,
 278                             function,
 279                             marker,
 280                             signature,
 281                         )
 282                         logger.info(f"Extracted marker '{marker}' from function '{function}' in {file_path}")
 283                     else:
 284                         return "❌ **ERROR**: Function marker extraction not supported for this file type"
 285                 else:
 286                     code_text, start_line, end_line = extractor.extract_function(resolved_path, function, signature)
 287                     logger.info(f"Extracted function '{function}' from {file_path}")
 288             elif function_macro:
 289                 # Handle function_macro parameter
 290                 if isinstance(function_macro, str):
 291                     # Simple string -> convert to dict
 292                     macro_spec = {"name": function_macro}
 293                 else:
 294                     macro_spec = function_macro
 295
 296                 # Check if we also have a marker - extract marker within macro
 297                 if marker:
 298                     if (context_lines or explicit_enclosure) and hasattr(
 299                         extractor, "extract_function_macro_marker_enclosed"
 300                     ):
 301                         enclosed = extractor.extract_function_macro_marker_enclosed(
 302                             resolved_path, macro_spec, marker
 303                         )
 304                         code_text, start_line, end_line = enclosed.to_tuple()
 305                         if context_lines:
 306                             display_segments = self._build_enclosure_segments(
 307                                 resolved_path, enclosed, context_lines
 308                             )
 309                         logger.info(
 310                             f"Extracted marker '{marker}' with function_macro enclosure "
 311                             f"'{macro_spec}' in {file_path}"
 312                         )
 313                     elif require_enclosure_context:
 314                         return "❌ **ERROR**: Function macro marker enclosure not supported for this file type"
 315                     elif hasattr(extractor, "extract_function_macro_marker"):
 316                         code_text, start_line, end_line = extractor.extract_function_macro_marker(
 317                             resolved_path, macro_spec, marker
 318                         )
 319                         logger.info(f"Extracted marker '{marker}' from function_macro '{macro_spec}' in {file_path}")
 320                     else:
 321                         return "❌ **ERROR**: Function macro marker extraction not supported for this file type"
 322                 else:
 323                     code_text, start_line, end_line = extractor.extract_function_macro(resolved_path, macro_spec)
 324                     logger.info(f"Extracted function_macro '{macro_spec}' from {file_path}")
 325             elif macro_definition:
 326                 code_text, start_line, end_line = extractor.extract_macro_definition(resolved_path, macro_definition)
 327                 logger.info(f"Extracted macro_definition '{macro_definition}' from {file_path}")
 328             elif var:
 329                 # Extract variable/constant declaration
 330                 if hasattr(extractor, "extract_variable"):
 331                     code_text, start_line, end_line = extractor.extract_variable(resolved_path, var)
 332                     logger.info(f"Extracted variable '{var}' from {file_path}")
 333                 elif hasattr(extractor, "extract_struct"):
 334                     # C/C++ uses extract_struct for var= (finds declarations)
 335                     if marker:
 336                         if (context_lines or explicit_enclosure) and hasattr(
 337                             extractor, "extract_struct_marker_enclosed"
 338                         ):
 339                             enclosed = extractor.extract_struct_marker_enclosed(
 340                                 resolved_path, var, marker
 341                             )
 342                             code_text, start_line, end_line = enclosed.to_tuple()
 343                             if context_lines:
 344                                 display_segments = self._build_enclosure_segments(
 345                                     resolved_path, enclosed, context_lines
 346                                 )
 347                             logger.info(
 348                                 f"Extracted marker '{marker}' with variable enclosure "
 349                                 f"'{var}' in {file_path}"
 350                             )
 351                         elif require_enclosure_context:
 352                             return "❌ **ERROR**: Marker enclosure in variable not supported"
 353                         elif hasattr(extractor, "extract_struct_marker"):
 354                             code_text, start_line, end_line = extractor.extract_struct_marker(
 355                                 resolved_path, var, marker
 356                             )
 357                             logger.info(f"Extracted marker '{marker}' from variable '{var}' in {file_path}")
 358                         else:
 359                             return "❌ **ERROR**: Marker extraction in variable not supported"
 360                     else:
 361                         code_text, start_line, end_line = extractor.extract_struct(resolved_path, var)
 362                         logger.info(f"Extracted variable '{var}' from {file_path}")
 363                 else:
 364                     return "❌ **ERROR**: Variable extraction not supported for this file type"
 365             elif struct:
 366                 # Extract struct/class/enum definition
 367                 if hasattr(extractor, "extract_struct"):
 368                     if marker:
 369                         if (context_lines or explicit_enclosure) and hasattr(
 370                             extractor, "extract_struct_marker_enclosed"
 371                         ):
 372                             enclosed = extractor.extract_struct_marker_enclosed(
 373                                 resolved_path, struct, marker
 374                             )
 375                             code_text, start_line, end_line = enclosed.to_tuple()
 376                             if context_lines:
 377                                 display_segments = self._build_enclosure_segments(
 378                                     resolved_path, enclosed, context_lines
 379                                 )
 380                             logger.info(
 381                                 f"Extracted marker '{marker}' with struct enclosure "
 382                                 f"'{struct}' in {file_path}"
 383                             )
 384                         elif require_enclosure_context:
 385                             return "❌ **ERROR**: Marker enclosure in struct not supported"
 386                         elif hasattr(extractor, "extract_struct_marker"):
 387                             code_text, start_line, end_line = extractor.extract_struct_marker(
 388                                 resolved_path, struct, marker
 389                             )
 390                             logger.info(f"Extracted marker '{marker}' from struct '{struct}' in {file_path}")
 391                         else:
 392                             return "❌ **ERROR**: Marker extraction in struct not supported"
 393                     else:
 394                         code_text, start_line, end_line = extractor.extract_struct(resolved_path, struct)
 395                         logger.info(f"Extracted struct/class '{struct}' from {file_path}")
 396                 else:
 397                     return "❌ **ERROR**: Struct/class extraction not supported for this file type"
 398             elif message:
 399                 # Extract protobuf message
 400                 if hasattr(extractor, "extract_message"):
 401                     if marker:
 402                         if (context_lines or explicit_enclosure) and hasattr(
 403                             extractor, "extract_message_marker_enclosed"
 404                         ):
 405                             enclosed = extractor.extract_message_marker_enclosed(
 406                                 resolved_path, message, marker
 407                             )
 408                             code_text, start_line, end_line = enclosed.to_tuple()
 409                             if context_lines:
 410                                 display_segments = self._build_enclosure_segments(
 411                                     resolved_path, enclosed, context_lines
 412                                 )
 413                             logger.info(
 414                                 f"Extracted marker '{marker}' with message enclosure "
 415                                 f"'{message}' in {file_path}"
 416                             )
 417                         elif require_enclosure_context:
 418                             return "❌ **ERROR**: Message marker enclosure not supported for this file type"
 419                         else:
 420                             code_text, start_line, end_line = extractor.extract_message_marker(
 421                                 resolved_path, message, marker
 422                             )
 423                             logger.info(f"Extracted marker '{marker}' from message '{message}' in {file_path}")
 424                     else:
 425                         code_text, start_line, end_line = extractor.extract_message(resolved_path, message)
 426                         logger.info(f"Extracted message '{message}' from {file_path}")
 427                 else:
 428                     return "❌ **ERROR**: Message extraction not supported for this file type"
 429             elif enum:
 430                 # Extract protobuf enum
 431                 if hasattr(extractor, "extract_enum"):
 432                     code_text, start_line, end_line = extractor.extract_enum(resolved_path, enum)
 433                     logger.info(f"Extracted enum '{enum}' from {file_path}")
 434                 else:
 435                     return "❌ **ERROR**: Enum extraction not supported for this file type"
 436             elif service:
 437                 # Extract protobuf service
 438                 if hasattr(extractor, "extract_service"):
 439                     code_text, start_line, end_line = extractor.extract_service(resolved_path, service)
 440                     logger.info(f"Extracted service '{service}' from {file_path}")
 441                 else:
 442                     return "❌ **ERROR**: Service extraction not supported for this file type"
 443             elif marker:
 444                 if (context_lines or explicit_enclosure) and hasattr(extractor, "extract_marker_enclosed"):
 445                     enclosed = extractor.extract_marker_enclosed(resolved_path, marker)
 446                     code_text, start_line, end_line = enclosed.to_tuple()
 447                     if context_lines:
 448                         display_segments = self._build_enclosure_segments(
 449                             resolved_path, enclosed, context_lines
 450                         )
 451                     logger.info(f"Extracted marker '{marker}' with auto enclosure in {file_path}")
 452                 elif require_enclosure_context:
 453                     return "❌ **ERROR**: Auto marker enclosure not supported for this file type"
 454                 else:
 455                     code_text, start_line, end_line = extractor.extract_marker(resolved_path, marker)
 456                     logger.info(f"Extracted marker '{marker}' from {file_path}")
 457             elif lines:
 458                 start_line, end_line = lines
 459                 code_text, start_line, end_line = extractor.extract_lines(resolved_path, start_line, end_line)
 460                 logger.info(f"Extracted lines {start_line}-{end_line} from {file_path}")
 461             else:
 462                 return (
 463                     f"❌ **ERROR**: Must specify function, struct, var, function_macro, "
 464                     f"macro_definition, lines, or marker for {file_path}"
 465                 )
 466
 467             # Use original file path for display (not temp file)
 468             display_path = self.repo_path / file_path if not Path(file_path).is_absolute() else Path(file_path)
 469
 470             # Track this region as covered if we have a ChangesSet
 471             if self.changes_set is not None and not active_ref:
 472                 # changes_set holds HEAD-relative line numbers (built from
 473                 # 'git diff base..HEAD'), but start_line/end_line came from
 474                 # the working tree. Translate before subtracting so uncommitted
 475                 # edits above the extracted region don't shift the wrong rows.
 476                 coverage_ranges = (
 477                     [(segment_start, segment_end) for _, segment_start, segment_end in display_segments]
 478                     if display_segments
 479                     else [(start_line, end_line)]
 480                 )
 481                 for coverage_start, coverage_end in coverage_ranges:
 482                     committed_start = self.github.map_to_committed_line(display_path, coverage_start)
 483                     committed_end = self.github.map_to_committed_line(display_path, coverage_end)
 484                     self.changes_set.subtract(display_path, committed_start, committed_end)
 485
 486             # Remap line numbers if requested (for sharing docs from dirty files)
 487             display_start = start_line
 488             display_end = end_line
 489             if self.remap_dirty_lines and not active_ref:
 490                 display_start = self.github.map_to_committed_line(display_path, start_line)
 491                 display_end = self.github.map_to_committed_line(display_path, end_line)
 492
 493             # Build header with GitHub permalink if requested
 494             if github and not active_ref:
 495                 header = self.github.get_permalink(
 496                     display_path, start_line, end_line, display_committed_lines=self.remap_dirty_lines
 497                 )
 498             else:
 499                 header = None
 500                 if github and active_ref:
 501                     # Ref-pinned extracts get a permalink at that ref — the
 502                     # content and line numbers come from the ref's tree.
 503                     header = self.github.get_permalink_at_ref(display_path, active_ref, start_line, end_line)
 504                 if header is None:
 505                     display_rel = (
 506                         display_path.relative_to(self.repo_path) if display_path.is_absolute() else display_path
 507                     )
 508                     ref_suffix = f" @ {active_ref}" if active_ref else ""
 509                     if display_start == display_end:
 510                         header = f"📍 `{display_rel}:{display_start}{ref_suffix}`"
 511                     else:
 512                         header = f"📍 `{display_rel}:{display_start}-{display_end}{ref_suffix}`"
 513
 514             # Format code with line numbers and/or blame
 515             # Use remapped line numbers for display if remap_dirty_lines is enabled
 516             code_start_line = display_start if self.remap_dirty_lines else start_line
 517             if display_segments:
 518                 code_text = self._format_code_segments(
 519                     display_segments,
 520                     display_path,
 521                     line_numbers=line_numbers,
 522                     blame=blame and not active_ref,
 523                     remap_dirty_lines=self.remap_dirty_lines and not active_ref,
 524                 )
 525             elif blame and not active_ref:
 526                 code_text = self.github.format_with_blame(code_text, code_start_line, display_path)
 527             elif line_numbers:
 528                 code_text = self._add_line_numbers(code_text, code_start_line)
 529
 530             # Auto-detect language if not specified
 531             if not language:
 532                 suffix = display_path.suffix.lower()
 533                 language_map = {
 534                     ".cpp": "cpp",
 535                     ".cc": "cpp",
 536                     ".cxx": "cpp",
 537                     ".hpp": "cpp",
 538                     ".h": "cpp",
 539                     ".hxx": "cpp",
 540                     ".ipp": "cpp",  # Inline implementation files
 541                     ".macro": "cpp",  # C preprocessor macro files
 542                     ".c": "c",
 543                     ".py": "python",
 544                     ".js": "javascript",
 545                     ".mjs": "javascript",
 546                     ".cjs": "javascript",
 547                     ".ts": "typescript",
 548                     ".tsx": "tsx",
 549                     ".mts": "typescript",
 550                     ".cts": "typescript",
 551                     ".java": "java",
 552                     ".rs": "rust",
 553                     ".go": "go",
 554                     ".proto": "protobuf",
 555                 }
 556                 language = language_map.get(suffix, "text")
 557
 558             # Build final output
 559             return f"{header}\n```{language}\n{code_text}\n```"
 560
 561         except Exception as e:
 562             error_msg = f"❌ **ERROR**: {e}"
 563             logger.error(f"Code extraction failed: {e}")
 564             # Collect file as fixture if collection is enabled
 565             if resolved_path is not None:
 566                 _collect_error_fixture(resolved_path, str(e))
 567             return error_msg
 568
 569         finally:
 570             # Clean up temp file if we created one
 571             if tmp_file and tmp_file.exists():
 572                 tmp_file.unlink()
```

The function handles a wide variety of extraction types — functions, structs, variables, macros, protobuf messages, enums, services, markers, and raw line ranges. It also supports nesting: you can extract a marker *within* a function by passing both `function=` and `marker=`.

When a `ChangesSet` is provided (validation mode), each extraction automatically calls `subtract()` to mark those lines as documented.

### Marker Enclosure Context

C/C++ extractor-backed marker extracts include a little orientation by default: `enclosure_context=N` renders the marker body plus the first and last `N` lines of the enclosing source construct, and the built-in default is `3`. This works for explicit scopes such as `function=` or `struct=`, and marker-only C/C++ calls imply `enclosure='auto'`:

```jinja
{{ code('src/file.cpp', function='share', signature='TxSetShare', marker='encode') }}
{{ code('src/file.cpp', marker='encode') }}
{{ code('src/file.cpp', marker='encode', enclosure_context=0) }}
```

The permalink still targets the marker body, not the wider enclosure. In validation mode, only the displayed segments are counted as covered, so hidden middle lines do not accidentally satisfy change coverage.

#### Rationale and Scope

Markers are usually intentionally narrow: they identify the branch, guard, field, or handoff that the prose is about. A reviewer still needs orientation, so C/C++ marker snippets default to showing the enclosing symbol's opening and closing context. Exact marker output remains available with `enclosure_context=0` for intentionally surgical snippets.

This is limited to C/C++ extractor-backed files for now because the feature depends on language-specific AST enclosure selection. For languages without enclosed marker support, the implicit default falls back to exact marker extraction. Explicit requests such as `enclosure_context=2` or `enclosure='auto'` still report unsupported behavior instead of pretending context was added.

The renderer builds those non-contiguous display ranges here:

📍 [`projected_source/core/renderer.py:868-897`](https://github.com/sublimator/projected-source/blob/43c6fe74cd655402f491d196271da65d39199c09/projected_source/core/renderer.py#L868-L897)
```python
 868     def _build_enclosure_segments(self, file_path: Path, enclosed, context_lines: int) -> List[Tuple[str, int, int]]:
 869         """Build displayed source segments for an enclosed marker extraction."""
 870         ranges = self._build_enclosure_ranges(
 871             enclosed.enclosure_start_line,
 872             enclosed.enclosure_end_line,
 873             enclosed.marker_start_line,
 874             enclosed.marker_end_line,
 875             context_lines,
 876         )
 877         lines = file_path.read_text().splitlines()
 878         segments: List[Tuple[str, int, int]] = []
 879         for start, end in ranges:
 880             if start > end:
 881                 continue
 882             segment_lines: List[str] = []
 883             segment_start: Optional[int] = None
 884             for line_num in range(start, end + 1):
 885                 line = lines[line_num - 1]
 886                 if MARKER_DIRECTIVE_RE.match(line):
 887                     if segment_lines and segment_start is not None:
 888                         segments.append(("\n".join(segment_lines), segment_start, line_num - 1))
 889                     segment_lines = []
 890                     segment_start = None
 891                     continue
 892                 if segment_start is None:
 893                     segment_start = line_num
 894                 segment_lines.append(line)
 895             if segment_lines and segment_start is not None:
 896                 segments.append(("\n".join(segment_lines), segment_start, end))
 897         return segments
```

C++ provides the first auto-enclosure implementation. It prefers a marker-wrapped declaration/function/class when the marker surrounds one exactly, otherwise it picks the closest useful containing construct:

📍 [`projected_source/languages/cpp.py:476-522`](https://github.com/sublimator/projected-source/blob/43c6fe74cd655402f491d196271da65d39199c09/projected_source/languages/cpp.py#L476-L522)
```python
 476     def extract_marker_enclosed(self, file_path: Path, marker: str) -> EnclosedMarkerResult:
 477         """Extract a marker with the closest enclosing function/class-like C++ node."""
 478         source = file_path.read_bytes()
 479         root = self.parse_bytes(source)
 480         markers = self._find_marker_ranges_in_node(root)
 481
 482         if marker not in markers:
 483             available = ", ".join(markers.keys()) if markers else "none"
 484             raise ValueError(f"Marker '{marker}' not found. Available markers: {available}")
 485
 486         marker_ranges = markers[marker]
 487         if len(marker_ranges) > 1:
 488             locations = ", ".join(f"{start}-{end}" for start, end in marker_ranges)
 489             raise ValueError(f"Marker '{marker}' is ambiguous. Found multiple ranges: {locations}")
 490
 491         marker_start, marker_end = marker_ranges[0]
 492         enclosing_node = self._find_closest_enclosing_node(root, marker_start, marker_end)
 493         if enclosing_node is None:
 494             raise ValueError(f"No enclosing function/class found for marker '{marker}'")
 495
 496         enclosure_start = enclosing_node.start_point.row + 1
 497         enclosure_end = enclosing_node.end_point.row + 1
 498         enclosure_contains_marker = enclosure_start <= marker_start and marker_end <= enclosure_end
 499         marker_wraps_enclosure = marker_start <= enclosure_start and enclosure_end <= marker_end
 500         if not enclosure_contains_marker:
 501             top_level_wrapped = self._top_level_auto_enclosures_inside_range(
 502                 root, marker_start, marker_end
 503             )
 504             if not (
 505                 marker_wraps_enclosure
 506                 and len(top_level_wrapped) == 1
 507                 and self._same_node_range(top_level_wrapped[0], enclosing_node)
 508             ):
 509                 raise ValueError(f"No enclosing function/class contains marker '{marker}'")
 510
 511         result = node_to_result(enclosing_node, self._auto_enclosure_name(enclosing_node) or "")
 512         marker_text = "\n".join(source.decode("utf8").splitlines()[marker_start - 1 : marker_end])
 513         return EnclosedMarkerResult(
 514             marker_text=marker_text,
 515             marker_start_line=marker_start,
 516             marker_end_line=marker_end,
 517             enclosure_text=result.text,
 518             enclosure_start_line=result.start_line,
 519             enclosure_end_line=result.end_line,
 520             enclosure_kind=result.node_type,
 521             enclosure_name=result.qualified_name,
 522         )
```

### The include() Function

Templates can compose by including other files. Plain markdown files are included verbatim; `.j2` files are rendered as templates with full access to `code()`, caller variables, and other functions:

📍 [`projected_source/core/renderer.py:684-703`](https://github.com/sublimator/projected-source/blob/43c6fe74cd655402f491d196271da65d39199c09/projected_source/core/renderer.py#L684-L703)
```python
 684     @pass_context
 685     def _include_function(self, context, path: str) -> str:
 686         """
 687         Include a file into the template output.
 688
 689         .j2 files are rendered as Jinja2 templates (with access to code() etc).
 690         All other files are included as raw text.
 691
 692         Args:
 693             path: Path relative to the template directory
 694
 695         Returns:
 696             File contents (rendered if .j2)
 697
 698         Examples:
 699             {{ include('background.md') }}
 700             {{ include('details.md.j2') }}
 701             {{ include('sections/intro.md') }}
 702         """
 703         return self._load_include(path, context)
```

`include()` deliberately preserves standalone document wrappers. If an included file starts with YAML frontmatter or an already-rendered projected-source metadata header, that content stays in the output. Top-level CLI header handling runs only after the whole template, including nested includes, has rendered.

When embedding a standalone walkthrough inside another document, use `include_body()`. It uses the same raw/rendered include rules, then strips leading YAML frontmatter and projected-source's generated metadata header:

📍 [`projected_source/core/renderer.py:705-717`](https://github.com/sublimator/projected-source/blob/43c6fe74cd655402f491d196271da65d39199c09/projected_source/core/renderer.py#L705-L717)
```python
 705     @pass_context
 706     def _include_body_function(self, context, path: str) -> str:
 707         """
 708         Include a file as embeddable body content.
 709
 710         Uses the same rendering rules as include(), then strips leading YAML
 711         frontmatter and projected-source's generated metadata header.
 712
 713         Examples:
 714             {{ include_body('walkthrough.md.j2') }}
 715             {{ include_body('rendered-doc.md') }}
 716         """
 717         return self._strip_embedded_doc_wrappers(self._load_include(path, context))
```

### Custom Tags

Projects can extend the template environment by placing a `.projected-source.py` file in the project. The renderer discovers it by walking up from the template directory to the git root:

📍 [`projected_source/core/renderer.py:781-809`](https://github.com/sublimator/projected-source/blob/43c6fe74cd655402f491d196271da65d39199c09/projected_source/core/renderer.py#L781-L809)
```python
 781     def _find_custom_tags_file(self, start_path: Path) -> Optional[Path]:
 782         """
 783         Find .projected-source.py file by walking up from start_path.
 784         Stops at git root to avoid escaping the repository.
 785
 786         Args:
 787             start_path: Path to start searching from (usually template dir)
 788
 789         Returns:
 790             Path to .projected-source.py if found, None otherwise
 791         """
 792         current = start_path.resolve()
 793
 794         # Use repo_path as the boundary (it's already the git root)
 795         git_root = self.repo_path
 796
 797         while current >= git_root:
 798             custom_file = current / ".projected-source.py"
 799             if custom_file.exists():
 800                 logger.info(f"Found custom tags file at {custom_file}")
 801                 return custom_file
 802
 803             # Move up one directory
 804             parent = current.parent
 805             if parent == current:  # Reached filesystem root
 806                 break
 807             current = parent
 808
 809         return None
```

### Rendering

The public API is straightforward — `render_template()` for named templates and `render_template_file()` for file paths:

📍 [`projected_source/core/renderer.py:978-1001`](https://github.com/sublimator/projected-source/blob/43c6fe74cd655402f491d196271da65d39199c09/projected_source/core/renderer.py#L978-L1001)
```python
 978     def render_template(self, template_name: str, **context) -> str:
 979         """
 980         Render a template with the given context.
 981
 982         Args:
 983             template_name: Name of the template file
 984             **context: Additional context variables
 985
 986         Returns:
 987             Rendered template as string
 988         """
 989         try:
 990             # Load custom tags from .projected-source.py if available
 991             template_path = self.template_dir / template_name
 992             self._load_custom_tags(template_path)
 993
 994             template = self.env.get_template(template_name)
 995             return template.render(**context)
 996         except jinja2.TemplateNotFound:
 997             logger.error(f"Template not found: {template_name}")
 998             raise
 999         except Exception as e:
1000             logger.error(f"Template rendering failed: {e}")
1001             raise
```

---

## GitHub Integration

Every extracted code block can include a clickable GitHub permalink. The `GitHubIntegration` class handles the git plumbing — detecting the repository URL, mapping line numbers in dirty files to their committed counterparts, and generating blame annotations.

### Lazy Initialization

Repository info is loaded on first access. The class auto-detects the GitHub URL from the git remote, handling both SSH and HTTPS formats:

📍 [`projected_source/core/github.py:186-228`](https://github.com/sublimator/projected-source/blob/43c6fe74cd655402f491d196271da65d39199c09/projected_source/core/github.py#L186-L228)
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

📍 [`projected_source/core/github.py:37-83`](https://github.com/sublimator/projected-source/blob/43c6fe74cd655402f491d196271da65d39199c09/projected_source/core/github.py#L37-L83)
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

📍 [`projected_source/core/github.py:138-173`](https://github.com/sublimator/projected-source/blob/43c6fe74cd655402f491d196271da65d39199c09/projected_source/core/github.py#L138-L173)
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

📍 [`projected_source/core/github.py:419-510`](https://github.com/sublimator/projected-source/blob/43c6fe74cd655402f491d196271da65d39199c09/projected_source/core/github.py#L419-L510)
```python
 419     def get_permalink(
 420         self, file_path: Path, start_line: int = None, end_line: int = None, display_committed_lines: bool = True
 421     ) -> str:
 422         """
 423         Generate a GitHub permalink for a file or line range.
 424
 425         Args:
 426             file_path: Path to the file
 427             start_line: Optional start line number (1-based)
 428             end_line: Optional end line number (1-based)
 429             display_committed_lines: If True, display shows committed line numbers (matches link).
 430                                      If False, display shows working copy line numbers.
 431
 432         Returns:
 433             Formatted markdown link or plain text reference
 434         """
 435         # Make path relative to repo root
 436         try:
 437             if file_path.is_absolute():
 438                 rel_path = file_path.relative_to(self.repo_path)
 439             else:
 440                 rel_path = file_path
 441         except ValueError:
 442             rel_path = file_path
 443
 444         if self.github_url and self.commit_hash:
 445             # Map line numbers if file is dirty (has uncommitted changes like markers)
 446             committed_start = None
 447             committed_end = None
 448             # Track dirty state authoritatively, not via line-number drift —
 449             # a file can be edited without shifting the lines we render.
 450             is_dirty = self.is_file_dirty(file_path)
 451
 452             # An untracked / not-yet-committed file has no blob at commit_hash,
 453             # so a blob/<sha>/<path> link would 404. Only dirty files can be in
 454             # this state (a clean tracked file always exists at HEAD), so we gate
 455             # the extra git call on is_dirty. Suppress the link instead of
 456             # emitting a dead one.
 457             if is_dirty and not self.exists_at_commit(file_path, self.commit_hash):
 458                 logger.warning(
 459                     f"{rel_path} is not present at {self.commit_hash[:8]} "
 460                     f"(untracked or uncommitted new file); suppressing permalink"
 461                 )
 462                 return self._plain_reference(rel_path, start_line, end_line, suffix=" *(untracked — no permalink)*")
 463
 464             if start_line is not None:
 465                 committed_start = self.map_to_committed_line(file_path, start_line)
 466                 if end_line is not None:
 467                     committed_end = self.map_to_committed_line(file_path, end_line)
 468
 469             # Build GitHub URL with committed line numbers
 470             url = f"{self.github_url}/blob/{self.commit_hash}/{rel_path}"
 471
 472             # Add line anchors if specified (using committed line numbers for URL)
 473             if committed_start is not None:
 474                 # Choose which line numbers to display
 475                 if display_committed_lines or not is_dirty:
 476                     display_start = committed_start
 477                     display_end = committed_end
 478                 else:
 479                     # start_line must be set if committed_start was computed
 480                     assert start_line is not None
 481                     display_start = start_line
 482                     display_end = end_line
 483
 484                 # URL anchor must use committed line numbers
 485                 if committed_end and committed_end != committed_start:
 486                     url += f"#L{committed_start}-L{committed_end}"
 487                     if is_dirty:
 488                         logger.debug(
 489                             f"Dirty file: mapped lines {start_line}-{end_line} → {committed_start}-{committed_end}"
 490                         )
 491                 else:
 492                     url += f"#L{committed_start}"
 493
 494                 # Display label uses whichever line space we're showing — when
 495                 # display_committed_lines=False, working-copy lines may span a
 496                 # range even if their committed counterparts collapse to one.
 497                 if display_end is not None and display_end != display_start:
 498                     display = f"{rel_path}:{display_start}-{display_end}"
 499                 else:
 500                     display = f"{rel_path}:{display_start}"
 501             else:
 502                 display = str(rel_path)
 503
 504             # Surface dirty state so readers know the link points at HEAD content,
 505             # which may differ from what's rendered above.
 506             suffix = " *(uncommitted)*" if is_dirty else ""
 507             return f"📍 [`{display}`]({url}){suffix}"
 508         else:
 509             # No GitHub info, return plain text
 510             return self._plain_reference(rel_path, start_line, end_line)
```

### Blame Support

For deeper code archaeology, `blame=True` annotates each line with its author, date, and commit hash:

📍 [`projected_source/core/github.py:573-603`](https://github.com/sublimator/projected-source/blob/43c6fe74cd655402f491d196271da65d39199c09/projected_source/core/github.py#L573-L603)
```python
 573     def format_with_blame(self, code_text: str, start_line: int, file_path: Path) -> str:
 574         """
 575         Format code with git blame information.
 576
 577         Args:
 578             code_text: The code to format
 579             start_line: Starting line number
 580             file_path: Path to the file
 581
 582         Returns:
 583             Formatted code with blame info
 584         """
 585         lines = code_text.splitlines()
 586         end_line = start_line + len(lines) - 1
 587
 588         blame_info = self.get_blame(file_path, start_line, end_line)
 589
 590         formatted_lines = []
 591         for i, line in enumerate(lines):
 592             line_num = start_line + i
 593
 594             if line_num in blame_info:
 595                 blame = blame_info[line_num]
 596                 # Format: line_num | commit | author | date | code
 597                 formatted_line = f"{line_num:4} │ {blame['commit']} │ {blame['author']:<20} │ {blame['date']} │ {line}"
 598             else:
 599                 formatted_line = f"{line_num:4} │ {line}"
 600
 601             formatted_lines.append(formatted_line)
 602
 603         return "\n".join(formatted_lines)
```

---

## Change Validation

One of the most powerful features: projected-source can verify that your documentation actually covers the code that changed. Run with `-V` and it diffs against a base commit, tracks which regions each `code()` call covers, and reports any gaps.

### ChangesSet

The `ChangesSet` class tracks changed regions as a set of non-overlapping intervals per file. It supports adding regions (which auto-merge overlapping ranges), subtracting regions (which can split intervals), and querying what's left uncovered:

📍 [`projected_source/core/changes_set.py:27-252`](https://github.com/sublimator/projected-source/blob/43c6fe74cd655402f491d196271da65d39199c09/projected_source/core/changes_set.py#L27-L252)
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

📍 [`projected_source/core/changes_set.py:40-73`](https://github.com/sublimator/projected-source/blob/43c6fe74cd655402f491d196271da65d39199c09/projected_source/core/changes_set.py#L40-L73)
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

📍 [`projected_source/core/changes_set.py:105-148`](https://github.com/sublimator/projected-source/blob/43c6fe74cd655402f491d196271da65d39199c09/projected_source/core/changes_set.py#L105-L148)
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

📍 [`projected_source/core/changes_set.py:183-223`](https://github.com/sublimator/projected-source/blob/43c6fe74cd655402f491d196271da65d39199c09/projected_source/core/changes_set.py#L183-L223)
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

📍 [`projected_source/core/changes_set.py:225-231`](https://github.com/sublimator/projected-source/blob/43c6fe74cd655402f491d196271da65d39199c09/projected_source/core/changes_set.py#L225-L231)
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

📍 [`projected_source/cli/__init__.py:19-29`](https://github.com/sublimator/projected-source/blob/43c6fe74cd655402f491d196271da65d39199c09/projected_source/cli/__init__.py#L19-L29)
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

The primary command renders `.md.j2` templates. It handles single files, directories, and stdin. Key options include `--validate-changes` for coverage checking, `--commit` for rendering against historical commits, `--remap-dirty-lines` for sharing docs from dirty working copies, and `--enclosure-context N` for changing the default C/C++ marker enclosure context.

C/C++ extractor-backed marker extracts default to `enclosure_context=3`. `--enclosure-context N` overrides that render-wide for `code()` marker extracts that omit `enclosure_context`; use `--enclosure-context 0` to disable it globally. A template can still use `enclosure_context=0` on a specific call to render the marker body alone. Other languages currently keep exact marker output unless they add enclosed marker support.

Single-file rendering resolves the template path, creates a `TemplateRenderer`, and writes the output:

📍 [`projected_source/cli/render.py:436-477`](https://github.com/sublimator/projected-source/blob/43c6fe74cd655402f491d196271da65d39199c09/projected_source/cli/render.py#L436-L477)
```python
 436 def _render_file(
 437     input_file,
 438     output_file,
 439     repo_path,
 440     output_to_stdout,
 441     remap_dirty_lines=False,
 442     changes_set=None,
 443     header=False,
 444     enclosure_context=3,
 445 ):
 446     """Render a single template file."""
 447     # Determine template directory
 448     template_dir = input_file.parent
 449     template_name = input_file.name
 450
 451     # Create renderer
 452     renderer = TemplateRenderer(
 453         template_dir=template_dir,
 454         repo_path=repo_path,
 455         remap_dirty_lines=remap_dirty_lines,
 456         changes_set=changes_set,
 457         default_enclosure_context=enclosure_context,
 458     )
 459
 460     try:
 461         rendered = renderer.render_template(template_name)
 462
 463         if header:
 464             rendered = _apply_header(_build_header(template_name, repo_path), rendered)
 465
 466         if output_to_stdout:
 467             # Output to stdout
 468             click.echo(rendered)
 469         else:
 470             # Output to file
 471             output_file.parent.mkdir(parents=True, exist_ok=True)
 472             output_file.write_text(rendered)
 473             console.print(f"[green]✓[/green] {input_file} → {output_file}")
 474
 475     except Exception as e:
 476         console.print(f"[red]✗ Failed to render {input_file}:[/red] {e}")
 477         sys.exit(1)
```

Directory rendering walks the tree and renders all `.j2` files:

📍 [`projected_source/cli/render.py:480-549`](https://github.com/sublimator/projected-source/blob/43c6fe74cd655402f491d196271da65d39199c09/projected_source/cli/render.py#L480-L549)
```python
 480 def _render_directory(
 481     input_dir,
 482     output_dir,
 483     repo_path,
 484     remap_dirty_lines=False,
 485     changes_set=None,
 486     header=False,
 487     enclosure_context=3,
 488 ):
 489     """Render all templates in a directory."""
 490     templates = list(input_dir.glob("**/*.j2"))
 491
 492     if not templates:
 493         console.print(f"[yellow]No .j2 templates found in {input_dir}[/yellow]")
 494         return
 495
 496     console.print(f"[bold]Processing {len(templates)} templates from {input_dir}[/bold]")
 497
 498     # Create renderer
 499     renderer = TemplateRenderer(
 500         template_dir=input_dir,
 501         repo_path=repo_path,
 502         remap_dirty_lines=remap_dirty_lines,
 503         changes_set=changes_set,
 504         default_enclosure_context=enclosure_context,
 505     )
 506
 507     # Track results
 508     success_count = 0
 509     failed = []
 510
 511     # Process each template
 512     for template_path in templates:
 513         rel_path = template_path.relative_to(input_dir)
 514
 515         # Determine output path (strip .j2 extension)
 516         if rel_path.suffix == ".j2":
 517             output_rel_path = rel_path.with_suffix("")
 518         else:
 519             output_rel_path = rel_path
 520
 521         output_path_full = output_dir / output_rel_path
 522
 523         try:
 524             # Render template
 525             rendered = renderer.render_template(str(rel_path))
 526
 527             if header:
 528                 rendered = _apply_header(_build_header(str(rel_path), repo_path), rendered)
 529
 530             # Write output
 531             output_path_full.parent.mkdir(parents=True, exist_ok=True)
 532             output_path_full.write_text(rendered)
 533
 534             console.print(f"  [green]✓[/green] {rel_path} → {output_rel_path}")
 535             success_count += 1
 536
 537         except Exception as e:
 538             console.print(f"  [red]✗[/red] {rel_path}: {e}")
 539             failed.append((rel_path, str(e)))
 540
 541     # Summary
 542     console.print("\n[bold]Summary:[/bold]")
 543     console.print(f"  [green]{success_count} templates rendered successfully[/green]")
 544
 545     if failed:
 546         console.print(f"  [red]{len(failed)} templates failed:[/red]")
 547         for template, error in failed:
 548             console.print(f"    • {template}: {error}")
 549         sys.exit(1)
```

### Symbol Discovery

The `list-functions` command is essential for authoring templates — it shows every extractable symbol in a file, including the parameter you'd use in a `code()` call:

📍 [`projected_source/cli/list_symbols.py:15-107`](https://github.com/sublimator/projected-source/blob/43c6fe74cd655402f491d196271da65d39199c09/projected_source/cli/list_symbols.py#L15-L107)
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