<!--
rendered_from: system-overview.md.j2
rendered_at: 2026-07-25T08:51:03Z
branch: feat/audit-verb
commit: 497c25f
commit_message: fix(graph): slug degenerate ids consistently (final review finding 6)
-->

---

<sub>Last updated: 2026-07-25 | branch: feat/audit-verb | commit: 497c25f (fix(graph): slug degenerate ids consistently (final review finding 6))</sub>

---






# projected-source: System Overview

**projected-source** is a documentation tool that extracts code from source files and injects it into Jinja2 templates, creating documentation that stays synchronized with the codebase. It uses tree-sitter for accurate AST-based parsing and supports multiple languages through extractor plugins, including C/C++, Protocol Buffers, Python, JavaScript/TypeScript, Java, Rust, and Lean.

The core idea: write narrative documentation in Markdown templates (`.md.j2`), use `{{ code() }}` calls to pull in the exact code you're describing, and the rendered output always reflects the current state of the source.

---

## Data Structures

Before diving into how extraction works, let's look at the types that flow through the system.

### ExtractionResult

Every time code is extracted from a source file — whether a function, struct, or marker region — the result is packaged as an `ExtractionResult`. This dataclass carries the extracted text along with precise location metadata:

📍 [`projected_source/languages/extraction_result.py:9-36`](https://github.com/sublimator/projected-source/blob/497c25f0b6981919134c90c28e9a524c895136fc/projected_source/languages/extraction_result.py#L9-L36)
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

📍 [`projected_source/languages/extraction_result.py:39-69`](https://github.com/sublimator/projected-source/blob/497c25f0b6981919134c90c28e9a524c895136fc/projected_source/languages/extraction_result.py#L39-L69)
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

📍 [`projected_source/core/changes_set.py:63-72`](https://github.com/sublimator/projected-source/blob/497c25f0b6981919134c90c28e9a524c895136fc/projected_source/core/changes_set.py#L63-L72)
```python
  63 @dataclass
  64 class ChangeRegion:
  65     """A contiguous region of changed code in a file."""
  66
  67     file_path: Path
  68     start_line: int
  69     end_line: int
  70
  71     def __str__(self) -> str:
  72         return f"{self.file_path}:{self.start_line}-{self.end_line}"
```

---

## The Extractor Registry

The system supports multiple languages through a simple registry pattern. Each file extension maps to an extractor class:

📍 [`projected_source/languages/__init__.py:19-44`](https://github.com/sublimator/projected-source/blob/497c25f0b6981919134c90c28e9a524c895136fc/projected_source/languages/__init__.py#L19-L44)
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

📍 [`projected_source/languages/__init__.py:47-69`](https://github.com/sublimator/projected-source/blob/497c25f0b6981919134c90c28e9a524c895136fc/projected_source/languages/__init__.py#L47-L69)
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

📍 [`projected_source/core/extractor.py:17-134`](https://github.com/sublimator/projected-source/blob/497c25f0b6981919134c90c28e9a524c895136fc/projected_source/core/extractor.py#L17-L134)
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

📍 [`projected_source/core/renderer.py:203-257`](https://github.com/sublimator/projected-source/blob/497c25f0b6981919134c90c28e9a524c895136fc/projected_source/core/renderer.py#L203-L257)
```python
 203     def __init__(
 204         self,
 205         template_dir: Path = None,
 206         repo_path: Path = None,
 207         remap_dirty_lines: bool = False,
 208         changes_set: "ChangesSet" = None,
 209         default_enclosure_context: int = 3,
 210     ):
 211         """
 212         Initialize the renderer.
 213
 214         Args:
 215             template_dir: Directory containing templates (default: current dir)
 216             repo_path: Repository root path (default: current dir)
 217             remap_dirty_lines: If True, remap line numbers in dirty files to match
 218                                committed version (for sharing). Affects permalinks
 219                                and code block line numbers.
 220             changes_set: Optional ChangesSet for tracking documentation coverage.
 221                          When provided, each code() call will mark its region as
 222                          covered. Check changes_set.uncovered() after rendering.
 223             default_enclosure_context: Default C/C++ enclosure_context for marker code() calls
 224                                       that do not specify it explicitly.
 225         """
 226         self.template_dir = template_dir or Path.cwd()
 227         self.repo_path = repo_path or Path.cwd()
 228         self.remap_dirty_lines = remap_dirty_lines
 229         self.changes_set = changes_set
 230         self.default_enclosure_context = self._normalize_enclosure_context(default_enclosure_context)
 231         self.github = GitHubIntegration(self.repo_path)
 232
 233         # Failed code() extractions for the render in flight; reset per render.
 234         self._errors: List[CodeError] = []
 235
 236         # ref= strings already resolved to commit SHAs for coverage checks.
 237         self._ref_sha_cache: Dict[str, Optional[str]] = {}
 238
 239         # Create Jinja2 environment
 240         self.env = jinja2.Environment(
 241             loader=jinja2.FileSystemLoader(str(self.template_dir)),
 242             trim_blocks=True,
 243             lstrip_blocks=True,
 244             extensions=[CodeContextExtension, ChunkExtension],
 245         )
 246
 247         # Register custom functions
 248         self.env.globals["code"] = self._code_function
 249         self.env.globals["ghc"] = self._code_function  # Alias for compatibility
 250         self.env.globals["ignore_changes"] = self._ignore_changes_function
 251         self.env.globals["audit"] = self._audit_function
 252         self.env.globals["relate"] = self._relate_function
 253         self.env.globals["link"] = self._link_function
 254         self.env.globals["include"] = self._include_function
 255         self.env.globals["include_body"] = self._include_body_function
 256         self.env.globals["set_code_context"] = self._set_code_context_function
 257         self.env.globals["set_code_root"] = self._set_code_root_function
```

### The code() Function

This is the workhorse. Every `{{ code('file.cpp', function='foo') }}` call in a template invokes `_code_function`. It resolves the file path, picks the right extractor, extracts the requested symbol, optionally generates a GitHub permalink, adds line numbers, and returns formatted markdown:

📍 [`projected_source/core/renderer.py:262-763`](https://github.com/sublimator/projected-source/blob/497c25f0b6981919134c90c28e9a524c895136fc/projected_source/core/renderer.py#L262-L763)
```python
 262     def _code_function(
 263         self,
 264         file_path: str,
 265         function: str = None,
 266         struct: str = None,
 267         var: str = None,
 268         function_macro: Union[str, Dict] = None,
 269         macro_definition: str = None,
 270         lines: Tuple[int, int] = None,
 271         marker: str = None,
 272         signature: str = None,
 273         message: str = None,
 274         enum: str = None,
 275         service: str = None,
 276         github: bool = True,
 277         blame: bool = False,
 278         line_numbers: bool = True,
 279         language: str = None,
 280         ref: str = None,
 281         root: str = None,
 282         enclosure: str = None,
 283         enclosure_context: int = None,
 284         id: str = None,
 285         tags=None,
 286         from_marker: str = None,
 287         to_marker: str = None,
 288     ) -> str:
 289         """
 290         Universal code extraction function for templates.
 291
 292         Args:
 293             file_path: Path to the source file
 294             function: Function name to extract
 295             struct: Struct/class/enum name to extract (C/C++)
 296             var: Variable/constant declaration to extract (C/C++)
 297             function_macro: Macro that defines a function (dict with 'name' and optional 'arg0', 'arg1', etc)
 298             macro_definition: Macro definition name to extract (#define statement)
 299             lines: Tuple of (start_line, end_line) to extract
 300             marker: Marker name to extract between //@@start and //@@end
 301             signature: String to match against parameter types for overload disambiguation.
 302                        Use partial type names like "TMProposeSet" to select a specific overload.
 303             message: Message name to extract (protobuf)
 304             enum: Enum name to extract (protobuf, C++, TypeScript, Java, Rust)
 305             service: Service name to extract (protobuf)
 306             github: Include GitHub permalink (default: True)
 307             blame: Include git blame info (default: False)
 308             line_numbers: Show line numbers (default: True)
 309             language: Language for syntax highlighting (auto-detected if None)
 310             enclosure: Set to "auto" with C/C++ marker= to find the closest enclosing symbol.
 311             enclosure_context: For supported marker extractions, show the first
 312                                and last N lines of the enclosing symbol around the marker.
 313
 314         Returns:
 315             Formatted markdown with code block
 316
 317         Examples in templates:
 318             {{ code('src/file.cpp', function='myFunc') }}
 319             {{ code('src/file.cpp', function='onMessage', signature='TMProposeSet') }}
 320             {{ code('src/file.cpp', struct='MyClass') }}
 321             {{ code('src/file.cpp', var='errorInfos') }}
 322             {{ code('src/file.cpp', lines=(10, 20)) }}
 323             {{ code('src/file.cpp', marker='example1') }}
 324             {{ code('src/proto/file.proto', message='MyMessage') }}
 325             {{ code('src/proto/file.proto', enum='MyEnum') }}
 326         """
 327         tmp_file = None
 328         resolved_path: Optional[Path] = None
 329         display_segments: Optional[List[Tuple[str, int, int]]] = None
 330
 331         target = ", ".join(
 332             f"{name}={value}"
 333             for name, value in (
 334                 ("function", function),
 335                 ("struct", struct),
 336                 ("var", var),
 337                 ("function_macro", function_macro),
 338                 ("macro_definition", macro_definition),
 339                 ("marker", marker),
 340                 ("message", message),
 341                 ("enum", enum),
 342                 ("service", service),
 343                 ("lines", lines),
 344             )
 345             if value
 346         )
 347
 348         def fail(message: str) -> str:
 349             # Record the failure so callers can find it structurally, then
 350             # degrade it into the document so the render still completes and
 351             # shows the problem where it happened. file_path is read at call
 352             # time, so it reflects any code_root prefix applied below.
 353             self._errors.append(CodeError(message, file_path, target or None))
 354             return f"{ERROR_PREFIX} {message}"
 355
 356         try:
 357             context_lines = self._normalize_enclosure_context(
 358                 self.default_enclosure_context if enclosure_context is None else enclosure_context
 359             )
 360             enclosure_mode = (enclosure or "").lower()
 361             if enclosure_mode and enclosure_mode != "auto":
 362                 raise ValueError("enclosure must be 'auto' when specified")
 363             if enclosure_mode and not marker:
 364                 raise ValueError("enclosure requires marker=")
 365             explicit_enclosure = bool(enclosure_mode)
 366             require_enclosure_context = explicit_enclosure or (
 367                 context_lines > 0 and enclosure_context is not None
 368             )
 369
 370             # Apply root prefix: per-call root= overrides context code_root
 371             code_root = root or str(self.env.globals.get("code_root", ""))
 372             if code_root and not Path(file_path).is_absolute():
 373                 file_path = str(Path(code_root) / file_path)
 374
 375             # Determine active ref (per-call overrides context)
 376             active_ref = ref or str(self.env.globals.get("code_ref", ""))
 377
 378             # Resolve file path relative to repo
 379             resolved_path = Path(file_path)
 380             if not resolved_path.is_absolute():
 381                 resolved_path = self.repo_path / resolved_path
 382
 383             # If a git ref is active, fetch file content from that ref
 384             if active_ref:
 385                 rel_path = file_path
 386                 # Ensure relative path for git show
 387                 try:
 388                     rel_path = str(Path(file_path).relative_to(self.repo_path))
 389                 except ValueError:
 390                     # Already relative
 391                     rel_path = file_path
 392                 content = subprocess.check_output(
 393                     ["git", "show", f"{active_ref}:{rel_path}"],
 394                     cwd=self.repo_path,
 395                     stderr=subprocess.DEVNULL,
 396                 )
 397                 tmp_file = Path(tempfile.mktemp(suffix=resolved_path.suffix))
 398                 tmp_file.write_bytes(content)
 399                 resolved_path = tmp_file
 400
 401             # Get the appropriate extractor
 402             extractor = get_extractor(resolved_path)
 403
 404             # Marker-bounded region: carve a symbol (or the file) at existing
 405             # marker cut-points — head = to_marker, tail = from_marker — so a big
 406             # function splits into readable pieces WITHOUT adding new markers.
 407             # Resolve to a concrete (start, end) and fall through as a lines= read.
 408             if from_marker or to_marker:
 409                 # Only function/struct/lines/whole-file can be a marker-bounded
 410                 # base. Reject the selectors _marker_bounded_range can't clip,
 411                 # rather than silently ignoring the bound and dumping the symbol.
 412                 if function_macro or macro_definition or message or enum or service:
 413                     return fail(
 414                         "from_marker/to_marker only supports function=, struct=, lines=, "
 415                         "or a whole-file base — not macro/message/enum/service selectors"
 416                     )
 417                 lines = self._marker_bounded_range(
 418                     extractor, resolved_path, function, struct, signature, lines, from_marker, to_marker
 419                 )
 420                 function = struct = var = marker = None  # consumed into the line range
 421
 422             # Extract code based on parameters
 423             if function:
 424                 # Check if we also have a marker - extract marker within function
 425                 if marker:
 426                     if (context_lines or explicit_enclosure) and hasattr(extractor, "extract_function_marker_enclosed"):
 427                         enclosed = self._call_function_marker_method(
 428                             extractor.extract_function_marker_enclosed,
 429                             resolved_path,
 430                             function,
 431                             marker,
 432                             signature,
 433                         )
 434                         code_text, start_line, end_line = enclosed.to_tuple()
 435                         if context_lines:
 436                             display_segments = self._build_enclosure_segments(
 437                                 resolved_path, enclosed, context_lines
 438                             )
 439                         logger.info(
 440                             f"Extracted marker '{marker}' with function enclosure "
 441                             f"'{function}' in {file_path}"
 442                         )
 443                     elif require_enclosure_context:
 444                         return fail("Function marker enclosure not supported for this file type")
 445                     elif hasattr(extractor, "extract_function_marker"):
 446                         code_text, start_line, end_line = self._call_function_marker_method(
 447                             extractor.extract_function_marker,
 448                             resolved_path,
 449                             function,
 450                             marker,
 451                             signature,
 452                         )
 453                         logger.info(f"Extracted marker '{marker}' from function '{function}' in {file_path}")
 454                     else:
 455                         return fail("Function marker extraction not supported for this file type")
 456                 else:
 457                     code_text, start_line, end_line = extractor.extract_function(resolved_path, function, signature)
 458                     logger.info(f"Extracted function '{function}' from {file_path}")
 459             elif function_macro:
 460                 # Handle function_macro parameter
 461                 if isinstance(function_macro, str):
 462                     # Simple string -> convert to dict
 463                     macro_spec = {"name": function_macro}
 464                 else:
 465                     macro_spec = function_macro
 466
 467                 # Check if we also have a marker - extract marker within macro
 468                 if marker:
 469                     if (context_lines or explicit_enclosure) and hasattr(
 470                         extractor, "extract_function_macro_marker_enclosed"
 471                     ):
 472                         enclosed = extractor.extract_function_macro_marker_enclosed(
 473                             resolved_path, macro_spec, marker
 474                         )
 475                         code_text, start_line, end_line = enclosed.to_tuple()
 476                         if context_lines:
 477                             display_segments = self._build_enclosure_segments(
 478                                 resolved_path, enclosed, context_lines
 479                             )
 480                         logger.info(
 481                             f"Extracted marker '{marker}' with function_macro enclosure "
 482                             f"'{macro_spec}' in {file_path}"
 483                         )
 484                     elif require_enclosure_context:
 485                         return fail("Function macro marker enclosure not supported for this file type")
 486                     elif hasattr(extractor, "extract_function_macro_marker"):
 487                         code_text, start_line, end_line = extractor.extract_function_macro_marker(
 488                             resolved_path, macro_spec, marker
 489                         )
 490                         logger.info(f"Extracted marker '{marker}' from function_macro '{macro_spec}' in {file_path}")
 491                     else:
 492                         return fail("Function macro marker extraction not supported for this file type")
 493                 else:
 494                     code_text, start_line, end_line = extractor.extract_function_macro(resolved_path, macro_spec)
 495                     logger.info(f"Extracted function_macro '{macro_spec}' from {file_path}")
 496             elif macro_definition:
 497                 code_text, start_line, end_line = extractor.extract_macro_definition(resolved_path, macro_definition)
 498                 logger.info(f"Extracted macro_definition '{macro_definition}' from {file_path}")
 499             elif var:
 500                 # Extract variable/constant declaration
 501                 if hasattr(extractor, "extract_variable"):
 502                     code_text, start_line, end_line = extractor.extract_variable(resolved_path, var)
 503                     logger.info(f"Extracted variable '{var}' from {file_path}")
 504                 elif hasattr(extractor, "extract_struct"):
 505                     # C/C++ uses extract_struct for var= (finds declarations)
 506                     if marker:
 507                         if (context_lines or explicit_enclosure) and hasattr(
 508                             extractor, "extract_struct_marker_enclosed"
 509                         ):
 510                             enclosed = extractor.extract_struct_marker_enclosed(
 511                                 resolved_path, var, marker
 512                             )
 513                             code_text, start_line, end_line = enclosed.to_tuple()
 514                             if context_lines:
 515                                 display_segments = self._build_enclosure_segments(
 516                                     resolved_path, enclosed, context_lines
 517                                 )
 518                             logger.info(
 519                                 f"Extracted marker '{marker}' with variable enclosure "
 520                                 f"'{var}' in {file_path}"
 521                             )
 522                         elif require_enclosure_context:
 523                             return fail("Marker enclosure in variable not supported")
 524                         elif hasattr(extractor, "extract_struct_marker"):
 525                             code_text, start_line, end_line = extractor.extract_struct_marker(
 526                                 resolved_path, var, marker
 527                             )
 528                             logger.info(f"Extracted marker '{marker}' from variable '{var}' in {file_path}")
 529                         else:
 530                             return fail("Marker extraction in variable not supported")
 531                     else:
 532                         code_text, start_line, end_line = extractor.extract_struct(resolved_path, var)
 533                         logger.info(f"Extracted variable '{var}' from {file_path}")
 534                 else:
 535                     return fail("Variable extraction not supported for this file type")
 536             elif struct:
 537                 # Extract struct/class/enum definition
 538                 if hasattr(extractor, "extract_struct"):
 539                     if marker:
 540                         if (context_lines or explicit_enclosure) and hasattr(
 541                             extractor, "extract_struct_marker_enclosed"
 542                         ):
 543                             enclosed = extractor.extract_struct_marker_enclosed(
 544                                 resolved_path, struct, marker
 545                             )
 546                             code_text, start_line, end_line = enclosed.to_tuple()
 547                             if context_lines:
 548                                 display_segments = self._build_enclosure_segments(
 549                                     resolved_path, enclosed, context_lines
 550                                 )
 551                             logger.info(
 552                                 f"Extracted marker '{marker}' with struct enclosure "
 553                                 f"'{struct}' in {file_path}"
 554                             )
 555                         elif require_enclosure_context:
 556                             return fail("Marker enclosure in struct not supported")
 557                         elif hasattr(extractor, "extract_struct_marker"):
 558                             code_text, start_line, end_line = extractor.extract_struct_marker(
 559                                 resolved_path, struct, marker
 560                             )
 561                             logger.info(f"Extracted marker '{marker}' from struct '{struct}' in {file_path}")
 562                         else:
 563                             return fail("Marker extraction in struct not supported")
 564                     else:
 565                         code_text, start_line, end_line = extractor.extract_struct(resolved_path, struct)
 566                         logger.info(f"Extracted struct/class '{struct}' from {file_path}")
 567                 else:
 568                     return fail("Struct/class extraction not supported for this file type")
 569             elif message:
 570                 # Extract protobuf message
 571                 if hasattr(extractor, "extract_message"):
 572                     if marker:
 573                         if (context_lines or explicit_enclosure) and hasattr(
 574                             extractor, "extract_message_marker_enclosed"
 575                         ):
 576                             enclosed = extractor.extract_message_marker_enclosed(
 577                                 resolved_path, message, marker
 578                             )
 579                             code_text, start_line, end_line = enclosed.to_tuple()
 580                             if context_lines:
 581                                 display_segments = self._build_enclosure_segments(
 582                                     resolved_path, enclosed, context_lines
 583                                 )
 584                             logger.info(
 585                                 f"Extracted marker '{marker}' with message enclosure "
 586                                 f"'{message}' in {file_path}"
 587                             )
 588                         elif require_enclosure_context:
 589                             return fail("Message marker enclosure not supported for this file type")
 590                         else:
 591                             code_text, start_line, end_line = extractor.extract_message_marker(
 592                                 resolved_path, message, marker
 593                             )
 594                             logger.info(f"Extracted marker '{marker}' from message '{message}' in {file_path}")
 595                     else:
 596                         code_text, start_line, end_line = extractor.extract_message(resolved_path, message)
 597                         logger.info(f"Extracted message '{message}' from {file_path}")
 598                 else:
 599                     return fail("Message extraction not supported for this file type")
 600             elif enum:
 601                 # Extract protobuf enum
 602                 if hasattr(extractor, "extract_enum"):
 603                     code_text, start_line, end_line = extractor.extract_enum(resolved_path, enum)
 604                     logger.info(f"Extracted enum '{enum}' from {file_path}")
 605                 else:
 606                     return fail("Enum extraction not supported for this file type")
 607             elif service:
 608                 # Extract protobuf service
 609                 if hasattr(extractor, "extract_service"):
 610                     code_text, start_line, end_line = extractor.extract_service(resolved_path, service)
 611                     logger.info(f"Extracted service '{service}' from {file_path}")
 612                 else:
 613                     return fail("Service extraction not supported for this file type")
 614             elif marker:
 615                 if (context_lines or explicit_enclosure) and hasattr(extractor, "extract_marker_enclosed"):
 616                     enclosed = extractor.extract_marker_enclosed(resolved_path, marker)
 617                     code_text, start_line, end_line = enclosed.to_tuple()
 618                     if context_lines:
 619                         display_segments = self._build_enclosure_segments(
 620                             resolved_path, enclosed, context_lines
 621                         )
 622                     logger.info(f"Extracted marker '{marker}' with auto enclosure in {file_path}")
 623                 elif require_enclosure_context:
 624                     return fail("Auto marker enclosure not supported for this file type")
 625                 else:
 626                     code_text, start_line, end_line = extractor.extract_marker(resolved_path, marker)
 627                     logger.info(f"Extracted marker '{marker}' from {file_path}")
 628             elif lines:
 629                 start_line, end_line = lines
 630                 code_text, start_line, end_line = extractor.extract_lines(resolved_path, start_line, end_line)
 631                 logger.info(f"Extracted lines {start_line}-{end_line} from {file_path}")
 632             else:
 633                 return fail(
 634                     "Must specify function, struct, var, function_macro, "
 635                     "macro_definition, lines, or marker"
 636                 )
 637
 638             # Use original file path for display (not temp file)
 639             display_path = self.repo_path / file_path if not Path(file_path).is_absolute() else Path(file_path)
 640
 641             # Track this region as covered if we have a ChangesSet
 642             if self.changes_set is not None:
 643                 # Coverage claims the extraction target itself. For markers
 644                 # that is the body plus its //@@ delimiter lines (introduced
 645                 # by the same edit they document) — never the enclosure
 646                 # head/tail, which is presentation only: enclosure_context
 647                 # must not change whether an edit counts as documented.
 648                 coverage_start, coverage_end = start_line, end_line
 649                 if marker:
 650                     coverage_start, coverage_end = self._widen_to_marker_delimiters(
 651                         resolved_path, coverage_start, coverage_end
 652                     )
 653                 if not active_ref:
 654                     # changes_set holds line numbers for the diff's destination
 655                     # commit (HEAD), but the extraction came from the working
 656                     # tree. Translate before subtracting so uncommitted edits
 657                     # above the extracted region don't shift the wrong rows.
 658                     committed_start = self.github.map_to_committed_line(display_path, coverage_start)
 659                     committed_end = self.github.map_to_committed_line(display_path, coverage_end)
 660                     self.changes_set.claim("code", display_path, [(committed_start, committed_end)], chunk_id=id)
 661                 elif self._ref_is_changes_target(active_ref):
 662                     # Pinned at the validated range's destination commit: the
 663                     # extraction's coordinates are already in the same space
 664                     # as the diff's new-version lines. Any other ref lives in
 665                     # an unrelated coordinate space and claims nothing.
 666                     self.changes_set.claim("code", display_path, [(coverage_start, coverage_end)], chunk_id=id)
 667
 668             # Remap line numbers if requested (for sharing docs from dirty files)
 669             display_start = start_line
 670             display_end = end_line
 671             if self.remap_dirty_lines and not active_ref:
 672                 display_start = self.github.map_to_committed_line(display_path, start_line)
 673                 display_end = self.github.map_to_committed_line(display_path, end_line)
 674
 675             # Build header with GitHub permalink if requested
 676             if github and not active_ref:
 677                 header = self.github.get_permalink(
 678                     display_path, start_line, end_line, display_committed_lines=self.remap_dirty_lines
 679                 )
 680             else:
 681                 header = None
 682                 if github and active_ref:
 683                     # Ref-pinned extracts get a permalink at that ref — the
 684                     # content and line numbers come from the ref's tree.
 685                     header = self.github.get_permalink_at_ref(display_path, active_ref, start_line, end_line)
 686                 if header is None:
 687                     display_rel = (
 688                         display_path.relative_to(self.repo_path) if display_path.is_absolute() else display_path
 689                     )
 690                     ref_suffix = f" @ {active_ref}" if active_ref else ""
 691                     if display_start == display_end:
 692                         header = f"📍 `{display_rel}:{display_start}{ref_suffix}`"
 693                     else:
 694                         header = f"📍 `{display_rel}:{display_start}-{display_end}{ref_suffix}`"
 695
 696             # Format code with line numbers and/or blame
 697             # Use remapped line numbers for display if remap_dirty_lines is enabled
 698             code_start_line = display_start if self.remap_dirty_lines else start_line
 699             if display_segments:
 700                 code_text = self._format_code_segments(
 701                     display_segments,
 702                     display_path,
 703                     line_numbers=line_numbers,
 704                     blame=blame and not active_ref,
 705                     remap_dirty_lines=self.remap_dirty_lines and not active_ref,
 706                 )
 707             elif blame and not active_ref:
 708                 code_text = self.github.format_with_blame(code_text, code_start_line, display_path)
 709             elif line_numbers:
 710                 code_text = self._add_line_numbers(code_text, code_start_line)
 711
 712             # Auto-detect language if not specified
 713             if not language:
 714                 suffix = display_path.suffix.lower()
 715                 language_map = {
 716                     ".cpp": "cpp",
 717                     ".cc": "cpp",
 718                     ".cxx": "cpp",
 719                     ".hpp": "cpp",
 720                     ".h": "cpp",
 721                     ".hxx": "cpp",
 722                     ".ipp": "cpp",  # Inline implementation files
 723                     ".macro": "cpp",  # C preprocessor macro files
 724                     ".c": "c",
 725                     ".py": "python",
 726                     ".js": "javascript",
 727                     ".mjs": "javascript",
 728                     ".cjs": "javascript",
 729                     ".ts": "typescript",
 730                     ".tsx": "tsx",
 731                     ".mts": "typescript",
 732                     ".cts": "typescript",
 733                     ".java": "java",
 734                     ".rs": "rust",
 735                     ".go": "go",
 736                     ".proto": "protobuf",
 737                 }
 738                 language = language_map.get(suffix, "text")
 739
 740             # Build final output
 741             block = f"{header}\n```{language}\n{code_text}\n```"
 742             if id:
 743                 # A reader-invisible comment so the chunk is addressable as a
 744                 # graph node, plus a linkable anchor so another chunk can link()
 745                 # here instead of repeating the extract (DRY over duplication).
 746                 anchor = self._comment_attr("id", id)
 747                 tagstr = self._format_tags(tags)
 748                 if tagstr:
 749                     anchor += " " + self._comment_attr("tags", tagstr)
 750                 block = f"<!-- chunk {anchor} -->\n{_chunk_anchor_html(id)}\n{block}"
 751             return block
 752
 753         except Exception as e:
 754             logger.error(f"Code extraction failed: {e}")
 755             # Collect file as fixture if collection is enabled
 756             if resolved_path is not None:
 757                 _collect_error_fixture(resolved_path, str(e))
 758             return fail(str(e))
 759
 760         finally:
 761             # Clean up temp file if we created one
 762             if tmp_file and tmp_file.exists():
 763                 tmp_file.unlink()
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

📍 [`projected_source/core/renderer.py:1559-1588`](https://github.com/sublimator/projected-source/blob/497c25f0b6981919134c90c28e9a524c895136fc/projected_source/core/renderer.py#L1559-L1588)
```python
1559     def _build_enclosure_segments(self, file_path: Path, enclosed, context_lines: int) -> List[Tuple[str, int, int]]:
1560         """Build displayed source segments for an enclosed marker extraction."""
1561         ranges = self._build_enclosure_ranges(
1562             enclosed.enclosure_start_line,
1563             enclosed.enclosure_end_line,
1564             enclosed.marker_start_line,
1565             enclosed.marker_end_line,
1566             context_lines,
1567         )
1568         lines = file_path.read_text().splitlines()
1569         segments: List[Tuple[str, int, int]] = []
1570         for start, end in ranges:
1571             if start > end:
1572                 continue
1573             segment_lines: List[str] = []
1574             segment_start: Optional[int] = None
1575             for line_num in range(start, end + 1):
1576                 line = lines[line_num - 1]
1577                 if MARKER_DIRECTIVE_RE.match(line):
1578                     if segment_lines and segment_start is not None:
1579                         segments.append(("\n".join(segment_lines), segment_start, line_num - 1))
1580                     segment_lines = []
1581                     segment_start = None
1582                     continue
1583                 if segment_start is None:
1584                     segment_start = line_num
1585                 segment_lines.append(line)
1586             if segment_lines and segment_start is not None:
1587                 segments.append(("\n".join(segment_lines), segment_start, end))
1588         return segments
```

C++ provides the first auto-enclosure implementation. It prefers a marker-wrapped declaration/function/class when the marker surrounds one exactly, otherwise it picks the closest useful containing construct:

📍 [`projected_source/languages/cpp.py:476-522`](https://github.com/sublimator/projected-source/blob/497c25f0b6981919134c90c28e9a524c895136fc/projected_source/languages/cpp.py#L476-L522)
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

📍 [`projected_source/core/renderer.py:1343-1362`](https://github.com/sublimator/projected-source/blob/497c25f0b6981919134c90c28e9a524c895136fc/projected_source/core/renderer.py#L1343-L1362)
```python
1343     @pass_context
1344     def _include_function(self, context, path: str) -> str:
1345         """
1346         Include a file into the template output.
1347
1348         .j2 files are rendered as Jinja2 templates (with access to code() etc).
1349         All other files are included as raw text.
1350
1351         Args:
1352             path: Path relative to the template directory
1353
1354         Returns:
1355             File contents (rendered if .j2)
1356
1357         Examples:
1358             {{ include('background.md') }}
1359             {{ include('details.md.j2') }}
1360             {{ include('sections/intro.md') }}
1361         """
1362         return self._load_include(path, context)
```

`include()` deliberately preserves standalone document wrappers. If an included file starts with YAML frontmatter or an already-rendered projected-source metadata header, that content stays in the output. Top-level CLI header handling runs only after the whole template, including nested includes, has rendered.

When embedding a standalone walkthrough inside another document, use `include_body()`. It uses the same raw/rendered include rules, then strips leading YAML frontmatter and projected-source's generated metadata header:

📍 [`projected_source/core/renderer.py:1364-1376`](https://github.com/sublimator/projected-source/blob/497c25f0b6981919134c90c28e9a524c895136fc/projected_source/core/renderer.py#L1364-L1376)
```python
1364     @pass_context
1365     def _include_body_function(self, context, path: str) -> str:
1366         """
1367         Include a file as embeddable body content.
1368
1369         Uses the same rendering rules as include(), then strips leading YAML
1370         frontmatter and projected-source's generated metadata header.
1371
1372         Examples:
1373             {{ include_body('walkthrough.md.j2') }}
1374             {{ include_body('rendered-doc.md') }}
1375         """
1376         return self._strip_embedded_doc_wrappers(self._load_include(path, context))
```

### Custom Tags

Projects can extend the template environment by placing a `.projected-source.py` file in the project. The renderer discovers it by walking up from the template directory to the git root:

📍 [`projected_source/core/renderer.py:1440-1468`](https://github.com/sublimator/projected-source/blob/497c25f0b6981919134c90c28e9a524c895136fc/projected_source/core/renderer.py#L1440-L1468)
```python
1440     def _find_custom_tags_file(self, start_path: Path) -> Optional[Path]:
1441         """
1442         Find .projected-source.py file by walking up from start_path.
1443         Stops at git root to avoid escaping the repository.
1444
1445         Args:
1446             start_path: Path to start searching from (usually template dir)
1447
1448         Returns:
1449             Path to .projected-source.py if found, None otherwise
1450         """
1451         current = start_path.resolve()
1452
1453         # Use repo_path as the boundary (it's already the git root)
1454         git_root = self.repo_path
1455
1456         while current >= git_root:
1457             custom_file = current / ".projected-source.py"
1458             if custom_file.exists():
1459                 logger.info(f"Found custom tags file at {custom_file}")
1460                 return custom_file
1461
1462             # Move up one directory
1463             parent = current.parent
1464             if parent == current:  # Reached filesystem root
1465                 break
1466             current = parent
1467
1468         return None
```

### Rendering

`code()` never raises on a failed extraction — it degrades the failure into the document so the render still completes and shows the problem in place. That means a template can render "successfully" and still be wrong, so the renderer records each failure as a `CodeError` while it works:

📍 [`projected_source/core/renderer.py:80-94`](https://github.com/sublimator/projected-source/blob/497c25f0b6981919134c90c28e9a524c895136fc/projected_source/core/renderer.py#L80-L94)
```python
  80 @dataclass(frozen=True)
  81 class CodeError:
  82     """A code() extraction that failed during a render.
  83
  84     file_path/target are the template's own words for what it asked for, so a
  85     caller can report the failure without re-deriving it from the output.
  86     """
  87
  88     message: str
  89     file_path: str
  90     target: Optional[str] = None
  91
  92     def __str__(self) -> str:
  93         where = f"{self.file_path} ({self.target})" if self.target else self.file_path
  94         return f"{where}: {self.message}"
```

`render_result()` is the full-fidelity entry point. It returns the rendered text *and* the failures behind it — including failures inside included partials, since `include()` renders through this same renderer:

📍 [`projected_source/core/renderer.py:1669-1705`](https://github.com/sublimator/projected-source/blob/497c25f0b6981919134c90c28e9a524c895136fc/projected_source/core/renderer.py#L1669-L1705)
```python
1669     def render_result(self, template_name: str, **context) -> RenderResult:
1670         """
1671         Render a template, reporting the extractions that failed along the way.
1672
1673         code() does not raise when an extraction fails — it degrades the failure
1674         into the document — so a template can render "successfully" and still be
1675         wrong. This is the full-fidelity entry point: it returns the text
1676         together with a structured CodeError per failure, including failures
1677         from included templates (include() renders through this same renderer).
1678
1679         Prefer this over render_template() when you need to know whether the
1680         document is actually healthy. Do not scan the text for ERROR_PREFIX —
1681         a document quoting error-handling source would look broken.
1682
1683         Args:
1684             template_name: Name of the template file
1685             **context: Additional context variables
1686
1687         Returns:
1688             RenderResult with the rendered text and any failed extractions
1689         """
1690         self._errors = []
1691         try:
1692             # Load custom tags from .projected-source.py if available
1693             template_path = self.template_dir / template_name
1694             self._load_custom_tags(template_path)
1695
1696             template = self.env.get_template(template_name)
1697             text = template.render(**context)
1698         except jinja2.TemplateNotFound:
1699             logger.error(f"Template not found: {template_name}")
1700             raise
1701         except Exception as e:
1702             logger.error(f"Template rendering failed: {e}")
1703             raise
1704
1705         return RenderResult(text, list(self._errors))
```

This is what `check` consumes to tell a broken document from a merely stale one. The alternative — scanning the rendered text for the error marker — cannot distinguish a real failure from a document that legitimately *quotes* error-handling source. This page does exactly that, several times over.

`render_template()` remains as a thin facade for callers that only want the text, and `render_template_file()` handles file paths:

📍 [`projected_source/core/renderer.py:1707-1722`](https://github.com/sublimator/projected-source/blob/497c25f0b6981919134c90c28e9a524c895136fc/projected_source/core/renderer.py#L1707-L1722)
```python
1707     def render_template(self, template_name: str, **context) -> str:
1708         """
1709         Render a template with the given context.
1710
1711         Convenience facade over render_result() for callers that only want the
1712         text. Failed extractions are still visible in the output, but if you
1713         need to detect them, use render_result().
1714
1715         Args:
1716             template_name: Name of the template file
1717             **context: Additional context variables
1718
1719         Returns:
1720             Rendered template as string
1721         """
1722         return self.render_result(template_name, **context).text
```

---

## GitHub Integration

Every extracted code block can include a clickable GitHub permalink. The `GitHubIntegration` class handles the git plumbing — detecting the repository URL, mapping line numbers in dirty files to their committed counterparts, and generating blame annotations.

### Lazy Initialization

Repository info is loaded on first access. The class auto-detects the GitHub URL from the git remote, handling both SSH and HTTPS formats:

📍 [`projected_source/core/github.py:191-233`](https://github.com/sublimator/projected-source/blob/497c25f0b6981919134c90c28e9a524c895136fc/projected_source/core/github.py#L191-L233)
```python
 191     def _init_repo_info(self):
 192         """Lazy initialization of repository information."""
 193         if self._initialized:
 194             return
 195
 196         try:
 197             # Get the remote origin URL
 198             origin_url = (
 199                 subprocess.check_output(
 200                     ["git", "remote", "get-url", "origin"], cwd=self.repo_path, stderr=subprocess.DEVNULL
 201                 )
 202                 .decode()
 203                 .strip()
 204             )
 205
 206             # Get current commit hash
 207             self._commit_hash = (
 208                 subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=self.repo_path, stderr=subprocess.DEVNULL)
 209                 .decode()
 210                 .strip()
 211             )
 212
 213             # Convert SSH/HTTPS URL to GitHub web URL
 214             if origin_url.startswith("git@github.com:"):
 215                 # SSH format: git@github.com:user/repo.git
 216                 repo_path = origin_url.replace("git@github.com:", "").replace(".git", "")
 217             elif "github.com" in origin_url:
 218                 # HTTPS format: https://github.com/user/repo.git
 219                 repo_path = re.sub(r"https?://github\.com/", "", origin_url).replace(".git", "")
 220             else:
 221                 logger.warning(f"Non-GitHub repository: {origin_url}")
 222                 self._initialized = True
 223                 return
 224
 225             self._github_url = f"https://github.com/{repo_path}"
 226             logger.debug(f"GitHub URL: {self._github_url}, Commit: {self._commit_hash[:8]}")
 227
 228         except subprocess.CalledProcessError as e:
 229             logger.warning(f"Git command failed: {e}")
 230         except Exception as e:
 231             logger.warning(f"Failed to get GitHub info: {e}")
 232
 233         self._initialized = True
```

### Dirty File Line Mapping

When you're working on a file with uncommitted changes, the line numbers in your working copy won't match the committed version. The permalink needs to point to committed lines (which GitHub knows about), so the system maps working copy lines back to HEAD.

The full-diff parser builds a line-by-line mapping from new to old positions:

📍 [`projected_source/core/github.py:37-88`](https://github.com/sublimator/projected-source/blob/497c25f0b6981919134c90c28e9a524c895136fc/projected_source/core/github.py#L37-L88)
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
  50     old_remaining = 0
  51     new_remaining = 0
  52
  53     for line in diff_output.split("\n"):
  54         if old_remaining <= 0 and new_remaining <= 0:
  55             # Between hunks: only a hunk header matters here.
  56             match = hunk_pattern.match(line)
  57             if match:
  58                 old_line = int(match.group(1))
  59                 new_line = int(match.group(3))
  60                 old_remaining = int(match.group(2)) if match.group(2) else 1
  61                 new_remaining = int(match.group(4)) if match.group(4) else 1
  62             continue
  63
  64         # Inside a hunk body, bounded by the header's counts: classify by
  65         # first character only. Source content that looks like a diff
  66         # header (documenting a patch puts '++++ b/x' in the body) is a
  67         # body line, not a header.
  68         if line.startswith("\\"):
  69             # "\ No newline at end of file" - meta, consumes nothing
  70             continue
  71         if line.startswith("+"):
  72             # Added line - exists in new file only
  73             mapping[new_line] = None
  74             new_line += 1
  75             new_remaining -= 1
  76         elif line.startswith("-"):
  77             # Removed line - exists in old file only
  78             old_line += 1
  79             old_remaining -= 1
  80         else:
  81             # Context line - exists in both (may be '' if whitespace-stripped)
  82             mapping[new_line] = old_line
  83             old_line += 1
  84             new_line += 1
  85             old_remaining -= 1
  86             new_remaining -= 1
  87
  88     return mapping
```

This mapping is used by `map_to_committed_line()`, which falls back gracefully — if a line was newly added, it finds the nearest existing line before it:

📍 [`projected_source/core/github.py:143-178`](https://github.com/sublimator/projected-source/blob/497c25f0b6981919134c90c28e9a524c895136fc/projected_source/core/github.py#L143-L178)
```python
 143 def map_line_to_committed_full(new_line: int, diff_output: str) -> int:
 144     """
 145     Map a line number using full diff parsing for accurate results.
 146
 147     Args:
 148         new_line: Line number in the working copy (1-based)
 149         diff_output: Full git diff output
 150
 151     Returns:
 152         Corresponding line number in HEAD
 153     """
 154     mapping = build_line_mapping(diff_output)
 155
 156     # If we have a direct mapping for this line
 157     if new_line in mapping:
 158         old = mapping[new_line]
 159         if old is not None:
 160             return old
 161         # Line was added, find nearest non-added line before it
 162         for check_line in range(new_line - 1, 0, -1):
 163             if check_line in mapping and mapping[check_line] is not None:
 164                 result = mapping[check_line]
 165                 assert result is not None  # For type narrowing
 166                 return result
 167         # Fall back to line 1
 168         return 1
 169
 170     # Line not in any hunk - calculate offset from hunks before it
 171     hunks = parse_diff_hunks(diff_output)
 172     offset = 0
 173     for old_start, old_count, new_start, new_count in hunks:
 174         if new_line < new_start:
 175             break
 176         offset += old_count - new_count
 177
 178     return new_line + offset
```

### Permalink Generation

The `get_permalink()` method ties it all together — it maps lines, builds the URL with line anchors, and returns a markdown link:

📍 [`projected_source/core/github.py:424-515`](https://github.com/sublimator/projected-source/blob/497c25f0b6981919134c90c28e9a524c895136fc/projected_source/core/github.py#L424-L515)
```python
 424     def get_permalink(
 425         self, file_path: Path, start_line: int = None, end_line: int = None, display_committed_lines: bool = True
 426     ) -> str:
 427         """
 428         Generate a GitHub permalink for a file or line range.
 429
 430         Args:
 431             file_path: Path to the file
 432             start_line: Optional start line number (1-based)
 433             end_line: Optional end line number (1-based)
 434             display_committed_lines: If True, display shows committed line numbers (matches link).
 435                                      If False, display shows working copy line numbers.
 436
 437         Returns:
 438             Formatted markdown link or plain text reference
 439         """
 440         # Make path relative to repo root
 441         try:
 442             if file_path.is_absolute():
 443                 rel_path = file_path.relative_to(self.repo_path)
 444             else:
 445                 rel_path = file_path
 446         except ValueError:
 447             rel_path = file_path
 448
 449         if self.github_url and self.commit_hash:
 450             # Map line numbers if file is dirty (has uncommitted changes like markers)
 451             committed_start = None
 452             committed_end = None
 453             # Track dirty state authoritatively, not via line-number drift —
 454             # a file can be edited without shifting the lines we render.
 455             is_dirty = self.is_file_dirty(file_path)
 456
 457             # An untracked / not-yet-committed file has no blob at commit_hash,
 458             # so a blob/<sha>/<path> link would 404. Only dirty files can be in
 459             # this state (a clean tracked file always exists at HEAD), so we gate
 460             # the extra git call on is_dirty. Suppress the link instead of
 461             # emitting a dead one.
 462             if is_dirty and not self.exists_at_commit(file_path, self.commit_hash):
 463                 logger.warning(
 464                     f"{rel_path} is not present at {self.commit_hash[:8]} "
 465                     f"(untracked or uncommitted new file); suppressing permalink"
 466                 )
 467                 return self._plain_reference(rel_path, start_line, end_line, suffix=" *(untracked — no permalink)*")
 468
 469             if start_line is not None:
 470                 committed_start = self.map_to_committed_line(file_path, start_line)
 471                 if end_line is not None:
 472                     committed_end = self.map_to_committed_line(file_path, end_line)
 473
 474             # Build GitHub URL with committed line numbers
 475             url = f"{self.github_url}/blob/{self.commit_hash}/{rel_path}"
 476
 477             # Add line anchors if specified (using committed line numbers for URL)
 478             if committed_start is not None:
 479                 # Choose which line numbers to display
 480                 if display_committed_lines or not is_dirty:
 481                     display_start = committed_start
 482                     display_end = committed_end
 483                 else:
 484                     # start_line must be set if committed_start was computed
 485                     assert start_line is not None
 486                     display_start = start_line
 487                     display_end = end_line
 488
 489                 # URL anchor must use committed line numbers
 490                 if committed_end and committed_end != committed_start:
 491                     url += f"#L{committed_start}-L{committed_end}"
 492                     if is_dirty:
 493                         logger.debug(
 494                             f"Dirty file: mapped lines {start_line}-{end_line} → {committed_start}-{committed_end}"
 495                         )
 496                 else:
 497                     url += f"#L{committed_start}"
 498
 499                 # Display label uses whichever line space we're showing — when
 500                 # display_committed_lines=False, working-copy lines may span a
 501                 # range even if their committed counterparts collapse to one.
 502                 if display_end is not None and display_end != display_start:
 503                     display = f"{rel_path}:{display_start}-{display_end}"
 504                 else:
 505                     display = f"{rel_path}:{display_start}"
 506             else:
 507                 display = str(rel_path)
 508
 509             # Surface dirty state so readers know the link points at HEAD content,
 510             # which may differ from what's rendered above.
 511             suffix = " *(uncommitted)*" if is_dirty else ""
 512             return f"📍 [`{display}`]({url}){suffix}"
 513         else:
 514             # No GitHub info, return plain text
 515             return self._plain_reference(rel_path, start_line, end_line)
```

### Blame Support

For deeper code archaeology, `blame=True` annotates each line with its author, date, and commit hash:

📍 [`projected_source/core/github.py:578-608`](https://github.com/sublimator/projected-source/blob/497c25f0b6981919134c90c28e9a524c895136fc/projected_source/core/github.py#L578-L608)
```python
 578     def format_with_blame(self, code_text: str, start_line: int, file_path: Path) -> str:
 579         """
 580         Format code with git blame information.
 581
 582         Args:
 583             code_text: The code to format
 584             start_line: Starting line number
 585             file_path: Path to the file
 586
 587         Returns:
 588             Formatted code with blame info
 589         """
 590         lines = code_text.splitlines()
 591         end_line = start_line + len(lines) - 1
 592
 593         blame_info = self.get_blame(file_path, start_line, end_line)
 594
 595         formatted_lines = []
 596         for i, line in enumerate(lines):
 597             line_num = start_line + i
 598
 599             if line_num in blame_info:
 600                 blame = blame_info[line_num]
 601                 # Format: line_num | commit | author | date | code
 602                 formatted_line = f"{line_num:4} │ {blame['commit']} │ {blame['author']:<20} │ {blame['date']} │ {line}"
 603             else:
 604                 formatted_line = f"{line_num:4} │ {line}"
 605
 606             formatted_lines.append(formatted_line)
 607
 608         return "\n".join(formatted_lines)
```

---

## Change Validation

One of the most powerful features: projected-source can verify that your documentation actually covers the code that changed. Run with `-V` and it diffs against a base commit, tracks which regions each `code()` call covers, and reports any gaps.

### ChangesSet

The `ChangesSet` class tracks changed regions as a set of non-overlapping intervals per file. It supports adding regions (which auto-merge overlapping ranges), subtracting regions (which can split intervals), and querying what's left uncovered:

📍 [`projected_source/core/changes_set.py:169-611`](https://github.com/sublimator/projected-source/blob/497c25f0b6981919134c90c28e9a524c895136fc/projected_source/core/changes_set.py#L169-L611)
```python
 169 class ChangesSet:
 170     """
 171     Set-like structure for tracking changed code regions.
 172
 173     Supports adding regions (with automatic merging of overlapping/adjacent),
 174     subtracting regions (when claimed by documentation), and querying
 175     uncovered regions.
 176     """
 177
 178     def __init__(self):
 179         # Dict[Path, List[Tuple[start, end]]] - sorted, non-overlapping regions
 180         self._regions: Dict[Path, List[Tuple[int, int]]] = {}
 181         # Destination commit of the validated range (set by from_diff).
 182         # Extractions pinned with ref= at exactly this commit share its line
 183         # coordinate space, so they may claim coverage directly.
 184         self.target_sha: Optional[str] = None
 185         # claim() subtracts immediately (so uncovered()/is_complete() stay live
 186         # and order-independent for the residual) AND records the claim here.
 187         # The disjoint per-bucket partition is a separate pure computation
 188         # (partition()) over the frozen snapshot of D plus these records, so it
 189         # is order-independent without changing the residual semantics.
 190         self._claims: List[Tuple[str, Path, List[Tuple[int, int]]]] = []
 191         # Frozen snapshot of D (the full obligation set), captured once the diff
 192         # is parsed — before any claim erodes _regions — so |D| and the partition
 193         # denominators stay recoverable.
 194         self._d_snapshot: Dict[Path, List[Tuple[int, int]]] = {}
 195         self._d_line_count: int = 0
 196         self._frozen: bool = False
 197         # review_scope: globs restricting which files' changes are obligations.
 198         # Matched against the diff-relative POSIX path (never the absolute
 199         # _regions key, which can raise for an out-of-repo root — M1). The
 200         # defaults include everything, so an unscoped ChangesSet is unchanged.
 201         self._include: List[str] = ["**"]
 202         self._exclude: List[str] = []
 203         self._include_hits: Dict[str, int] = {}
 204         self._out_of_scope_lines: int = 0
 205         self._current_out_of_scope: bool = False
 206
 207     @classmethod
 208     def from_diff(
 209         cls,
 210         base: Optional[str] = None,
 211         repo_path: Optional[Path] = None,
 212         include: Optional[List[str]] = None,
 213         exclude: Optional[List[str]] = None,
 214     ) -> "ChangesSet":
 215         """
 216         Build a ChangesSet from git diff against a base commit or range.
 217
 218         Args:
 219             base: Base commit/branch, or a range like "HEAD~5..HEAD~2".
 220                   If no ".." present, diffs against HEAD. Auto-detected if None.
 221             repo_path: Path to git repository. Uses cwd if None.
 222             include: review_scope globs; only changed files whose diff-relative
 223                      POSIX path matches one are obligations (default: all).
 224             exclude: review_scope globs applied after include.
 225
 226         Returns:
 227             ChangesSet populated with all changed regions in scope.
 228         """
 229         repo_path = repo_path or Path.cwd()
 230         base = base or cls.detect_base(repo_path)
 231
 232         # Support commit ranges (e.g., "HEAD~5..HEAD~2") or simple base (e.g., "HEAD~5")
 233         diff_range = base if ".." in base else f"{base}..HEAD"
 234
 235         changes = cls()
 236         if include is not None:
 237             changes._include = list(include)
 238         if exclude is not None:
 239             changes._exclude = list(exclude)
 240         changes._include_hits = {p: 0 for p in changes._include}
 241
 242         # Get diff with file names and line numbers. quotePath=false keeps
 243         # non-ASCII paths as raw UTF-8 instead of C-quoted octal escapes,
 244         # so '+++ b/<path>' parsing sees the real path.
 245         result = subprocess.run(
 246             ["git", "-c", "core.quotePath=false", "diff", diff_range, "--unified=3"],
 247             capture_output=True,
 248             cwd=repo_path,
 249             text=True,
 250         )
 251
 252         if result.returncode != 0:
 253             raise RuntimeError(f"git diff failed: {result.stderr}")
 254
 255         changes._parse_diff(result.stdout, repo_path)
 256         changes._freeze_d()
 257         target = diff_range.rsplit("..", 1)[-1].lstrip(".") or "HEAD"
 258         changes.target_sha = cls._resolve_commit(target, repo_path)
 259         return changes
 260
 261     @staticmethod
 262     def _resolve_commit(ref: str, repo_path: Path) -> Optional[str]:
 263         """Resolve a ref to a full commit SHA, or None if it doesn't resolve."""
 264         result = subprocess.run(
 265             ["git", "rev-parse", f"{ref}^{{commit}}"],
 266             capture_output=True,
 267             cwd=repo_path,
 268             text=True,
 269         )
 270         if result.returncode != 0:
 271             return None
 272         return result.stdout.strip()
 273
 274     @staticmethod
 275     def detect_base(repo_path: Path) -> str:
 276         """
 277         Auto-detect the base commit for diffing.
 278
 279         Tries merge-base with main, then master, falls back to HEAD~1.
 280         """
 281         # Try main
 282         result = subprocess.run(
 283             ["git", "merge-base", "HEAD", "main"],
 284             capture_output=True,
 285             cwd=repo_path,
 286             text=True,
 287         )
 288         if result.returncode == 0:
 289             return result.stdout.strip()
 290
 291         # Try master
 292         result = subprocess.run(
 293             ["git", "merge-base", "HEAD", "master"],
 294             capture_output=True,
 295             cwd=repo_path,
 296             text=True,
 297         )
 298         if result.returncode == 0:
 299             return result.stdout.strip()
 300
 301         # Fall back to parent commit
 302         return "HEAD~1"
 303
 304     _HUNK_HEADER_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
 305
 306     def _parse_diff(self, diff_output: str, repo_path: Path) -> None:
 307         """Parse unified diff output and populate regions.
 308
 309         Only '+' lines become required coverage. Unchanged hunk context
 310         advances the new-file cursor without creating an obligation.
 311         Deletion-only hunks therefore produce no obligation: a deletion has
 312         no new-version line to anchor to, and proxying it through unchanged
 313         neighbors would make coverage depend on diff presentation.
 314
 315         Hunk bodies are bounded by the @@ header's line counts. Inside a
 316         body, lines are classified only by their first character — source
 317         content that *looks* like a header (an added '++ b/x' renders as
 318         the diff line '+++ b/x') must not switch files or get dropped.
 319         """
 320         current_file: Optional[Path] = None
 321         current_new_line = 0
 322         old_remaining = 0
 323         new_remaining = 0
 324
 325         for line in diff_output.splitlines():
 326             if old_remaining > 0 or new_remaining > 0:
 327                 # Inside a hunk body.
 328                 if line.startswith("\\"):
 329                     continue  # '\ No newline at end of file' — meta line
 330                 if line.startswith("+"):
 331                     # Added/replacement line - needs coverage
 332                     if current_file:
 333                         self.add(current_file, current_new_line, current_new_line)
 334                     elif self._current_out_of_scope:
 335                         # A real change we dropped because review_scope excluded
 336                         # its file — tallied so the report can say how much scope
 337                         # removed (H5), rather than passing --strict silently.
 338                         self._out_of_scope_lines += 1
 339                     current_new_line += 1
 340                     new_remaining -= 1
 341                 elif line.startswith("-"):
 342                     # Deleted line - doesn't advance the new-file cursor
 343                     old_remaining -= 1
 344                 else:
 345                     # Unchanged context line - advances position only
 346                     current_new_line += 1
 347                     old_remaining -= 1
 348                     new_remaining -= 1
 349                 continue
 350
 351             # New file header: +++ b/path/to/file
 352             if line.startswith("+++ b/"):
 353                 current_file = self._scoped_file(repo_path, line[6:])  # Strip "+++ b/"
 354             # C-quoted header: +++ "b/path with \303\251scapes". Git quotes
 355             # paths with control characters even under quotePath=false.
 356             elif line.startswith('+++ "b/'):
 357                 current_file = self._scoped_file(repo_path, self._unquote_git_path(line[4:]))
 358             # Anything else ('+++ /dev/null' for a deleted file, or an
 359             # unrecognized header form) must never attribute the following
 360             # hunk lines to the previous file.
 361             elif line.startswith("+++ "):
 362                 current_file = None
 363                 self._current_out_of_scope = False
 364
 365             # Hunk header: @@ -old_start,old_count +new_start,new_count @@
 366             else:
 367                 match = self._HUNK_HEADER_RE.match(line)
 368                 if match:
 369                     current_new_line = int(match.group(3))
 370                     old_remaining = int(match.group(2)) if match.group(2) else 1
 371                     new_remaining = int(match.group(4)) if match.group(4) else 1
 372
 373     def _scoped_file(self, repo_path: Path, rel: str) -> Optional[Path]:
 374         """Absolute path if `rel` is in review_scope, else None.
 375
 376         Matches the diff-relative POSIX path against the include/exclude globs
 377         with real glob semantics (see _glob_regex: `**` crosses separators, `*`
 378         does not). Updates the per-pattern hit tally and the in-scope flag used
 379         to count out-of-scope changed lines.
 380         """
 381         rel_posix = Path(rel).as_posix()
 382         matched = [p for p in self._include if _glob_regex(p).match(rel_posix)]
 383         for p in matched:
 384             self._include_hits[p] = self._include_hits.get(p, 0) + 1
 385         excluded = any(_glob_regex(p).match(rel_posix) for p in self._exclude)
 386         if matched and not excluded:
 387             self._current_out_of_scope = False
 388             return repo_path / rel
 389         self._current_out_of_scope = True
 390         return None
 391
 392     _GIT_PATH_ESCAPES = {
 393         "a": "\a",
 394         "b": "\b",
 395         "f": "\f",
 396         "n": "\n",
 397         "r": "\r",
 398         "t": "\t",
 399         "v": "\v",
 400         '"': '"',
 401         "\\": "\\",
 402     }
 403
 404     @classmethod
 405     def _unquote_git_path(cls, quoted: str) -> str:
 406         """Decode a git C-style quoted path: '"b/na\\303\\257ve.h"' -> 'b/naïve.h'.
 407
 408         Octal escapes are raw bytes of the UTF-8 encoding, so unescape to
 409         bytes first and decode at the end.
 410         """
 411         inner = quoted.strip()
 412         if inner.startswith('"') and inner.endswith('"'):
 413             inner = inner[1:-1]
 414         out = bytearray()
 415         i = 0
 416         while i < len(inner):
 417             ch = inner[i]
 418             if ch == "\\" and i + 1 < len(inner):
 419                 nxt = inner[i + 1]
 420                 if nxt.isdigit():
 421                     out.append(int(inner[i + 1 : i + 4], 8))
 422                     i += 4
 423                     continue
 424                 out.extend(cls._GIT_PATH_ESCAPES.get(nxt, nxt).encode("utf8"))
 425                 i += 2
 426                 continue
 427             out.extend(ch.encode("utf8"))
 428             i += 1
 429         path = out.decode("utf8", errors="surrogateescape")
 430         return path[2:] if path.startswith("b/") else path
 431
 432     def add(self, file_path: Path, start: int, end: int) -> None:
 433         """
 434         Add a region, merging with overlapping or adjacent regions.
 435
 436         Args:
 437             file_path: Path to the file
 438             start: Start line (1-based, inclusive)
 439             end: End line (1-based, inclusive)
 440         """
 441         if start > end:
 442             start, end = end, start
 443
 444         regions = self._regions.setdefault(file_path, [])
 445
 446         # Add new region and re-merge everything
 447         regions.append((start, end))
 448         self._regions[file_path] = self._merge_sorted(sorted(regions))
 449
 450     def _merge_sorted(self, regions: List[Tuple[int, int]]) -> List[Tuple[int, int]]:
 451         """Merge a sorted list of potentially overlapping regions."""
 452         if not regions:
 453             return []
 454
 455         result = [regions[0]]
 456         for start, end in regions[1:]:
 457             last_start, last_end = result[-1]
 458             if start <= last_end + 1:
 459                 # Overlapping or adjacent - merge
 460                 result[-1] = (last_start, max(last_end, end))
 461             else:
 462                 result.append((start, end))
 463         return result
 464
 465     def subtract(self, file_path: Path, start: int, end: int) -> None:
 466         """
 467         Remove a region (mark as covered by documentation).
 468
 469         May split existing regions if the subtracted region is in the middle.
 470
 471         Args:
 472             file_path: Path to the file
 473             start: Start line (1-based, inclusive)
 474             end: End line (1-based, inclusive)
 475         """
 476         if file_path not in self._regions:
 477             return
 478
 479         if start > end:
 480             start, end = end, start
 481
 482         new_regions: List[Tuple[int, int]] = []
 483
 484         for reg_start, reg_end in self._regions[file_path]:
 485             # No overlap - keep as is
 486             if end < reg_start or start > reg_end:
 487                 new_regions.append((reg_start, reg_end))
 488
 489             # Full coverage - remove entirely
 490             elif start <= reg_start and end >= reg_end:
 491                 pass  # Don't add it
 492
 493             # Partial overlap - may need to split
 494             #@@start region-split
 495             else:
 496                 # Left remainder
 497                 if reg_start < start:
 498                     new_regions.append((reg_start, start - 1))
 499                 # Right remainder
 500                 if reg_end > end:
 501                     new_regions.append((end + 1, reg_end))
 502             #@@end region-split
 503
 504         if new_regions:
 505             self._regions[file_path] = new_regions
 506         else:
 507             del self._regions[file_path]
 508
 509     def _freeze_d(self) -> None:
 510         """Snapshot D before any claim erodes _regions (see __init__)."""
 511         self._d_snapshot = {p: list(regs) for p, regs in self._regions.items()}
 512         self._d_line_count = sum(e - s + 1 for regs in self._d_snapshot.values() for s, e in regs)
 513         self._frozen = True
 514
 515     def claim(
 516         self,
 517         bucket: str,
 518         file_path: Path,
 519         regions: List[Tuple[int, int]],
 520         chunk_id: Optional[str] = None,
 521     ) -> None:
 522         """Claim coverage for one or more line spans.
 523
 524         `bucket` is one of BUCKET_PRIORITY. `regions` is a list of (start, end)
 525         spans — one for an ordinary selector, several for geometry such as
 526         "symbol minus marker". Each span is subtracted immediately (so the
 527         residual and uncovered()/is_complete() stay live and order-independent)
 528         and recorded, so partition() can attribute lines to buckets disjointly.
 529         `chunk_id` is an optional stable node id carried through to the record
 530         (the seed for the chunk graph).
 531         """
 532         # Freeze D on the first claim if from_diff did not (a directly built
 533         # ChangesSet is the library API), so partition()/changed_line_count()
 534         # are meaningful on every construction path (F13).
 535         if not self._frozen:
 536             self._freeze_d()
 537         norm = [(min(s, e), max(s, e)) for s, e in regions]
 538         self._claims.append((bucket, file_path, norm, chunk_id))
 539         for s, e in norm:
 540             self.subtract(file_path, s, e)
 541
 542     def partition(self) -> Tuple[Dict[str, int], List[ClaimRecord]]:
 543         """Attribute every changed line to exactly one bucket, order-independently.
 544
 545         Replays the recorded claims against a fresh copy of the frozen D in
 546         bucket-priority order (code > audit > ignore): the first bucket to claim
 547         a line is credited it; later overlapping claims get nothing for it. The
 548         live residual (_regions) is untouched — this is a pure report-time
 549         computation. Returns (bucket -> line count, per-claim records).
 550         """
 551         residual = {p: list(regs) for p, regs in self._d_snapshot.items()}
 552         bucket_lines = {b: 0 for b in BUCKET_PRIORITY}
 553         records: List[ClaimRecord] = []
 554         for bucket in BUCKET_PRIORITY:
 555             for claim_bucket, path, regions, chunk_id in self._claims:
 556                 if claim_bucket != bucket:
 557                     continue
 558                 changed = sum(_count_in_intervals(self._d_snapshot.get(path, []), s, e) for s, e in regions)
 559                 credited = 0
 560                 for s, e in regions:
 561                     credited += _count_in_intervals(residual.get(path, []), s, e)
 562                     residual[path] = _subtract_interval(residual.get(path, []), s, e)
 563                 bucket_lines[bucket] += credited
 564                 records.append(ClaimRecord(bucket, path, regions, changed, credited, chunk_id))
 565         return bucket_lines, records
 566
 567     def changed_line_count(self) -> int:
 568         """Total changed lines in D (the obligation set, after scope)."""
 569         return self._d_line_count
 570
 571     def out_of_scope_line_count(self) -> int:
 572         """Changed lines dropped because review_scope excluded their file (H5)."""
 573         return self._out_of_scope_lines
 574
 575     def unmatched_includes(self) -> List[str]:
 576         """review_scope include globs that matched no changed file (H5).
 577
 578         A non-default include that matches nothing usually means a typo'd glob
 579         silently narrowing the gate to nothing — worth surfacing so an empty
 580         scope cannot pass --strict having verified nothing.
 581         """
 582         return [p for p, hits in self._include_hits.items() if hits == 0 and p not in _CATCH_ALL_GLOBS]
 583
 584     def uncovered(self) -> List[ChangeRegion]:
 585         """Return list of regions not yet claimed by documentation."""
 586         result = []
 587         for file_path, regions in sorted(self._regions.items()):
 588             for start, end in regions:
 589                 result.append(ChangeRegion(file_path, start, end))
 590         return result
 591
 592     def is_complete(self) -> bool:
 593         """Return True if all regions have been claimed."""
 594         return len(self._regions) == 0
 595
 596     def files(self) -> List[Path]:
 597         """Return list of files with uncovered changes."""
 598         return list(self._regions.keys())
 599
 600     def __len__(self) -> int:
 601         """Return total number of uncovered regions."""
 602         return sum(len(regions) for regions in self._regions.values())
 603
 604     def __bool__(self) -> bool:
 605         """Return True if there are uncovered regions."""
 606         return len(self._regions) > 0
 607
 608     def __repr__(self) -> str:
 609         total = len(self)
 610         files = len(self._regions)
 611         return f"ChangesSet({total} regions in {files} files)"
```

### Building from Git Diff

`from_diff()` parses unified diff output to populate the set. It supports both simple base refs (`origin/main`) and explicit ranges (`HEAD~5..HEAD~2`):

📍 [`projected_source/core/changes_set.py:207-259`](https://github.com/sublimator/projected-source/blob/497c25f0b6981919134c90c28e9a524c895136fc/projected_source/core/changes_set.py#L207-L259)
```python
 207     @classmethod
 208     def from_diff(
 209         cls,
 210         base: Optional[str] = None,
 211         repo_path: Optional[Path] = None,
 212         include: Optional[List[str]] = None,
 213         exclude: Optional[List[str]] = None,
 214     ) -> "ChangesSet":
 215         """
 216         Build a ChangesSet from git diff against a base commit or range.
 217
 218         Args:
 219             base: Base commit/branch, or a range like "HEAD~5..HEAD~2".
 220                   If no ".." present, diffs against HEAD. Auto-detected if None.
 221             repo_path: Path to git repository. Uses cwd if None.
 222             include: review_scope globs; only changed files whose diff-relative
 223                      POSIX path matches one are obligations (default: all).
 224             exclude: review_scope globs applied after include.
 225
 226         Returns:
 227             ChangesSet populated with all changed regions in scope.
 228         """
 229         repo_path = repo_path or Path.cwd()
 230         base = base or cls.detect_base(repo_path)
 231
 232         # Support commit ranges (e.g., "HEAD~5..HEAD~2") or simple base (e.g., "HEAD~5")
 233         diff_range = base if ".." in base else f"{base}..HEAD"
 234
 235         changes = cls()
 236         if include is not None:
 237             changes._include = list(include)
 238         if exclude is not None:
 239             changes._exclude = list(exclude)
 240         changes._include_hits = {p: 0 for p in changes._include}
 241
 242         # Get diff with file names and line numbers. quotePath=false keeps
 243         # non-ASCII paths as raw UTF-8 instead of C-quoted octal escapes,
 244         # so '+++ b/<path>' parsing sees the real path.
 245         result = subprocess.run(
 246             ["git", "-c", "core.quotePath=false", "diff", diff_range, "--unified=3"],
 247             capture_output=True,
 248             cwd=repo_path,
 249             text=True,
 250         )
 251
 252         if result.returncode != 0:
 253             raise RuntimeError(f"git diff failed: {result.stderr}")
 254
 255         changes._parse_diff(result.stdout, repo_path)
 256         changes._freeze_d()
 257         target = diff_range.rsplit("..", 1)[-1].lstrip(".") or "HEAD"
 258         changes.target_sha = cls._resolve_commit(target, repo_path)
 259         return changes
```

The diff parser walks through hunk headers and added lines to build up the initial set of changed regions:

📍 [`projected_source/core/changes_set.py:306-371`](https://github.com/sublimator/projected-source/blob/497c25f0b6981919134c90c28e9a524c895136fc/projected_source/core/changes_set.py#L306-L371)
```python
 306     def _parse_diff(self, diff_output: str, repo_path: Path) -> None:
 307         """Parse unified diff output and populate regions.
 308
 309         Only '+' lines become required coverage. Unchanged hunk context
 310         advances the new-file cursor without creating an obligation.
 311         Deletion-only hunks therefore produce no obligation: a deletion has
 312         no new-version line to anchor to, and proxying it through unchanged
 313         neighbors would make coverage depend on diff presentation.
 314
 315         Hunk bodies are bounded by the @@ header's line counts. Inside a
 316         body, lines are classified only by their first character — source
 317         content that *looks* like a header (an added '++ b/x' renders as
 318         the diff line '+++ b/x') must not switch files or get dropped.
 319         """
 320         current_file: Optional[Path] = None
 321         current_new_line = 0
 322         old_remaining = 0
 323         new_remaining = 0
 324
 325         for line in diff_output.splitlines():
 326             if old_remaining > 0 or new_remaining > 0:
 327                 # Inside a hunk body.
 328                 if line.startswith("\\"):
 329                     continue  # '\ No newline at end of file' — meta line
 330                 if line.startswith("+"):
 331                     # Added/replacement line - needs coverage
 332                     if current_file:
 333                         self.add(current_file, current_new_line, current_new_line)
 334                     elif self._current_out_of_scope:
 335                         # A real change we dropped because review_scope excluded
 336                         # its file — tallied so the report can say how much scope
 337                         # removed (H5), rather than passing --strict silently.
 338                         self._out_of_scope_lines += 1
 339                     current_new_line += 1
 340                     new_remaining -= 1
 341                 elif line.startswith("-"):
 342                     # Deleted line - doesn't advance the new-file cursor
 343                     old_remaining -= 1
 344                 else:
 345                     # Unchanged context line - advances position only
 346                     current_new_line += 1
 347                     old_remaining -= 1
 348                     new_remaining -= 1
 349                 continue
 350
 351             # New file header: +++ b/path/to/file
 352             if line.startswith("+++ b/"):
 353                 current_file = self._scoped_file(repo_path, line[6:])  # Strip "+++ b/"
 354             # C-quoted header: +++ "b/path with \303\251scapes". Git quotes
 355             # paths with control characters even under quotePath=false.
 356             elif line.startswith('+++ "b/'):
 357                 current_file = self._scoped_file(repo_path, self._unquote_git_path(line[4:]))
 358             # Anything else ('+++ /dev/null' for a deleted file, or an
 359             # unrecognized header form) must never attribute the following
 360             # hunk lines to the previous file.
 361             elif line.startswith("+++ "):
 362                 current_file = None
 363                 self._current_out_of_scope = False
 364
 365             # Hunk header: @@ -old_start,old_count +new_start,new_count @@
 366             else:
 367                 match = self._HUNK_HEADER_RE.match(line)
 368                 if match:
 369                     current_new_line = int(match.group(3))
 370                     old_remaining = int(match.group(2)) if match.group(2) else 1
 371                     new_remaining = int(match.group(4)) if match.group(4) else 1
```

### Subtract and Query

As templates render, each `code()` call subtracts its extracted region. The `subtract()` method handles partial overlaps — if documentation covers the middle of a changed region, it splits into two uncovered remainders:

📍 [`projected_source/core/changes_set.py:465-507`](https://github.com/sublimator/projected-source/blob/497c25f0b6981919134c90c28e9a524c895136fc/projected_source/core/changes_set.py#L465-L507)
```python
 465     def subtract(self, file_path: Path, start: int, end: int) -> None:
 466         """
 467         Remove a region (mark as covered by documentation).
 468
 469         May split existing regions if the subtracted region is in the middle.
 470
 471         Args:
 472             file_path: Path to the file
 473             start: Start line (1-based, inclusive)
 474             end: End line (1-based, inclusive)
 475         """
 476         if file_path not in self._regions:
 477             return
 478
 479         if start > end:
 480             start, end = end, start
 481
 482         new_regions: List[Tuple[int, int]] = []
 483
 484         for reg_start, reg_end in self._regions[file_path]:
 485             # No overlap - keep as is
 486             if end < reg_start or start > reg_end:
 487                 new_regions.append((reg_start, reg_end))
 488
 489             # Full coverage - remove entirely
 490             elif start <= reg_start and end >= reg_end:
 491                 pass  # Don't add it
 492
 493             # Partial overlap - may need to split
 494             #@@start region-split
 495             else:
 496                 # Left remainder
 497                 if reg_start < start:
 498                     new_regions.append((reg_start, start - 1))
 499                 # Right remainder
 500                 if reg_end > end:
 501                     new_regions.append((end + 1, reg_end))
 502             #@@end region-split
 503
 504         if new_regions:
 505             self._regions[file_path] = new_regions
 506         else:
 507             del self._regions[file_path]
```

After rendering, `uncovered()` returns whatever's left:

📍 [`projected_source/core/changes_set.py:584-590`](https://github.com/sublimator/projected-source/blob/497c25f0b6981919134c90c28e9a524c895136fc/projected_source/core/changes_set.py#L584-L590)
```python
 584     def uncovered(self) -> List[ChangeRegion]:
 585         """Return list of regions not yet claimed by documentation."""
 586         result = []
 587         for file_path, regions in sorted(self._regions.items()):
 588             for start, end in regions:
 589                 result.append(ChangeRegion(file_path, start, end))
 590         return result
```

---

## CLI Interface

The CLI is built with Click. The main entry point registers all commands:

📍 [`projected_source/cli/__init__.py:22-32`](https://github.com/sublimator/projected-source/blob/497c25f0b6981919134c90c28e9a524c895136fc/projected_source/cli/__init__.py#L22-L32)
```python
  22 @click.group()
  23 @click.option("--verbose", "-v", is_flag=True, help="Enable verbose logging")
  24 @click.option("--debug", "-d", is_flag=True, help="Enable debug logging")
  25 def cli(verbose, debug):
  26     """Extract and project source code into documentation."""
  27     if debug:
  28         setup_logging(logging.DEBUG)
  29     elif verbose:
  30         setup_logging(logging.INFO)
  31     else:
  32         setup_logging(logging.WARNING)
```

### The render Command

The primary command renders `.md.j2` templates. It handles single files, directories, and stdin. Key options include `--validate-changes` for coverage checking, `--commit` for rendering against historical commits, `--remap-dirty-lines` for sharing docs from dirty working copies, and `--enclosure-context N` for changing the default C/C++ marker enclosure context.

C/C++ extractor-backed marker extracts default to `enclosure_context=3`. `--enclosure-context N` overrides that render-wide for `code()` marker extracts that omit `enclosure_context`; use `--enclosure-context 0` to disable it globally. A template can still use `enclosure_context=0` on a specific call to render the marker body alone. Other languages currently keep exact marker output unless they add enclosed marker support.

Single-file rendering resolves the template path, creates a `TemplateRenderer`, and writes the output:

📍 [`projected_source/cli/render.py:834-879`](https://github.com/sublimator/projected-source/blob/497c25f0b6981919134c90c28e9a524c895136fc/projected_source/cli/render.py#L834-L879)
```python
 834 def _render_file(
 835     input_file,
 836     output_file,
 837     repo_path,
 838     output_to_stdout,
 839     remap_dirty_lines=False,
 840     changes_set=None,
 841     header=False,
 842     html_output=False,
 843     enclosure_context=3,
 844 ):
 845     """Render a single template file."""
 846     # Determine template directory
 847     template_dir = input_file.parent
 848     template_name = input_file.name
 849
 850     # Create renderer
 851     renderer = TemplateRenderer(
 852         template_dir=template_dir,
 853         repo_path=repo_path,
 854         remap_dirty_lines=remap_dirty_lines,
 855         changes_set=changes_set,
 856         default_enclosure_context=enclosure_context,
 857     )
 858
 859     try:
 860         rendered = renderer.render_template(template_name)
 861
 862         if header:
 863             rendered = _apply_header(_build_header(template_name, repo_path), rendered)
 864         if html_output:
 865             title_hint = Path(template_name).with_suffix("").stem.replace("-", " ").replace("_", " ").title()
 866             rendered = markdown_to_html(rendered, title_hint=title_hint)
 867
 868         if output_to_stdout:
 869             # Output to stdout
 870             click.echo(rendered)
 871         else:
 872             # Output to file
 873             output_file.parent.mkdir(parents=True, exist_ok=True)
 874             output_file.write_text(rendered)
 875             console.print(f"[green]✓[/green] {input_file} → {output_file}")
 876
 877     except Exception as e:
 878         console.print(f"[red]✗ Failed to render {input_file}:[/red] {escape(str(e))}")
 879         sys.exit(1)
```

Directory rendering walks the tree and renders all `.j2` files:

📍 [`projected_source/cli/render.py:882-957`](https://github.com/sublimator/projected-source/blob/497c25f0b6981919134c90c28e9a524c895136fc/projected_source/cli/render.py#L882-L957)
```python
 882 def _render_directory(
 883     input_dir,
 884     output_dir,
 885     repo_path,
 886     remap_dirty_lines=False,
 887     changes_set=None,
 888     header=False,
 889     html_output=False,
 890     enclosure_context=3,
 891 ):
 892     """Render all templates in a directory."""
 893     templates = list(input_dir.glob("**/*.j2"))
 894
 895     if not templates:
 896         console.print(f"[yellow]No .j2 templates found in {input_dir}[/yellow]")
 897         return
 898
 899     console.print(f"[bold]Processing {len(templates)} templates from {input_dir}[/bold]")
 900
 901     # Create renderer
 902     renderer = TemplateRenderer(
 903         template_dir=input_dir,
 904         repo_path=repo_path,
 905         remap_dirty_lines=remap_dirty_lines,
 906         changes_set=changes_set,
 907         default_enclosure_context=enclosure_context,
 908     )
 909
 910     # Track results
 911     success_count = 0
 912     failed = []
 913
 914     # Process each template
 915     for template_path in templates:
 916         rel_path = template_path.relative_to(input_dir)
 917
 918         # Determine output path (strip .j2 extension, or map to .html)
 919         if html_output:
 920             output_rel_path = default_html_output(rel_path)
 921         elif rel_path.suffix == ".j2":
 922             output_rel_path = rel_path.with_suffix("")
 923         else:
 924             output_rel_path = rel_path
 925
 926         output_path_full = output_dir / output_rel_path
 927
 928         try:
 929             # Render template
 930             rendered = renderer.render_template(str(rel_path))
 931
 932             if header:
 933                 rendered = _apply_header(_build_header(str(rel_path), repo_path), rendered)
 934             if html_output:
 935                 title_hint = rel_path.with_suffix("").stem.replace("-", " ").replace("_", " ").title()
 936                 rendered = markdown_to_html(rendered, title_hint=title_hint)
 937
 938             # Write output
 939             output_path_full.parent.mkdir(parents=True, exist_ok=True)
 940             output_path_full.write_text(rendered)
 941
 942             console.print(f"  [green]✓[/green] {rel_path} → {output_rel_path}")
 943             success_count += 1
 944
 945         except Exception as e:
 946             console.print(f"  [red]✗[/red] {rel_path}: {escape(str(e))}")
 947             failed.append((rel_path, str(e)))
 948
 949     # Summary
 950     console.print("\n[bold]Summary:[/bold]")
 951     console.print(f"  [green]{success_count} templates rendered successfully[/green]")
 952
 953     if failed:
 954         console.print(f"  [red]{len(failed)} templates failed:[/red]")
 955         for template, error in failed:
 956             console.print(f"    • {template}: {escape(error)}")
 957         sys.exit(1)
```

### Symbol Discovery

The `list-functions` command is essential for authoring templates — it shows every extractable symbol in a file, including the parameter you'd use in a `code()` call:

📍 [`projected_source/cli/list_symbols.py:16-114`](https://github.com/sublimator/projected-source/blob/497c25f0b6981919134c90c28e9a524c895136fc/projected_source/cli/list_symbols.py#L16-L114)
```python
  16 @click.command("list-functions")
  17 @click.argument("file", required=False, type=click.Path(exists=True, dir_okay=False))
  18 @click.option(
  19     "--include-tests",
  20     is_flag=True,
  21     default=False,
  22     help="Rust only: include items inside #[cfg(test)] modules (hidden by default).",
  23 )
  24 def list_functions(file, include_tests):
  25     """List extractable symbols in a file.
  26
  27     When FILE is given, lists all functions, classes, structs, enums,
  28     variables, and markers that can be extracted with code() calls.
  29
  30     When no FILE is given, shows available extraction parameters.
  31     """
  32     if not file:
  33         _show_params_table()
  34         return
  35
  36     file_path = Path(file).resolve()
  37
  38     try:
  39         extractor = get_extractor(file_path)
  40     except ValueError as e:
  41         console.print(f"[red]{e}[/red]")
  42         raise SystemExit(1)
  43
  44     if not hasattr(extractor, "list_symbols"):
  45         console.print(f"[red]Symbol listing not supported for {file_path.suffix} files[/red]")
  46         raise SystemExit(1)
  47
  48     list_kwargs = {}
  49     if include_tests and "include_tests" in inspect.signature(extractor.list_symbols).parameters:
  50         list_kwargs["include_tests"] = True
  51
  52     try:
  53         symbols = extractor.list_symbols(file_path, **list_kwargs)
  54     except Exception as e:
  55         console.print(f"[red]Could not read symbols from {file}: {escape(str(e))}[/red]")
  56         raise SystemExit(1)
  57
  58     if not symbols:
  59         console.print(f"[yellow]No extractable symbols found in {file}[/yellow]")
  60         return
  61
  62     # Detect overloaded functions
  63     func_names = [s["name"] for s in symbols if s["param"] == "function"]
  64     name_counts = Counter(func_names)
  65     overloaded = {name for name, count in name_counts.items() if count > 1}
  66
  67     # Group by param
  68     groups = {}
  69     for sym in symbols:
  70         param = sym["param"]
  71         if param not in groups:
  72             groups[param] = []
  73         groups[param].append(sym)
  74
  75     # Display
  76     console.print(f"\n[bold]{file}[/bold]\n")
  77
  78     display_order = ["function", "struct", "var", "message", "enum", "service", "marker"]
  79
  80     for param in display_order:
  81         if param not in groups:
  82             continue
  83
  84         syms = groups[param]
  85         count = len(syms)
  86         console.print(f"  [bold]{param}=[/bold] [dim]({count})[/dim]")
  87
  88         for sym in syms:
  89             name = sym["name"]
  90             line = sym["line"]
  91             kind = sym["kind"]
  92
  93             parts = []
  94
  95             # Show kind if it differs from param (e.g. class vs struct param)
  96             if kind != param:
  97                 parts.append(f"[dim]{kind}[/dim]")
  98
  99             # Line info
 100             if sym.get("end_line"):
 101                 parts.append(f"[dim]lines {line}-{sym['end_line']}[/dim]")
 102             else:
 103                 parts.append(f"[dim]line {line}[/dim]")
 104
 105             # Show signature hint for overloaded functions
 106             if name in overloaded and sym.get("signature"):
 107                 # Signatures are raw source text (e.g. '(char buf[size])')
 108                 # — escape so Rich doesn't eat brackets as markup.
 109                 parts.append(f"[dim]signature='{escape(sym['signature'])}'[/dim]")
 110
 111             extra = "  ".join(parts)
 112             console.print(f"    [cyan]'{escape(name)}'[/cyan]  {extra}")
 113
 114         console.print()
```