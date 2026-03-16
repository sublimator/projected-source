<!--
rendered_from: system-overview.md.j2
rendered_at: 2026-03-16T09:04:53Z
branch: main
commit: 3a3eb7d
commit_message: feat: add --header/--no-header flag to render command
-->

---

<sub>Last updated: 2026-03-16 | branch: main | commit: 3a3eb7d (feat: add --header/--no-header flag to render command)</sub>

---






# projected-source: System Overview

**projected-source** is a documentation tool that extracts code from source files and injects it into Jinja2 templates, creating documentation that stays synchronized with the codebase. It uses tree-sitter for accurate AST-based parsing and supports C/C++, Protocol Buffers, and Python.

The core idea: write narrative documentation in Markdown templates (`.md.j2`), use `{{ code() }}` calls to pull in the exact code you're describing, and the rendered output always reflects the current state of the source.

---

## Data Structures

Before diving into how extraction works, let's look at the types that flow through the system.

### ExtractionResult

Every time code is extracted from a source file — whether a function, struct, or marker region — the result is packaged as an `ExtractionResult`. This dataclass carries the extracted text along with precise location metadata:

📍 [`projected_source/languages/extraction_result.py:9-36`](https://github.com/sublimator/projected-source/blob/3a3eb7df63981ceafb0ef882458e12f9774629ed/projected_source/languages/extraction_result.py#L9-L36)
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

📍 [`projected_source/core/changes_set.py:15-24`](https://github.com/sublimator/projected-source/blob/3a3eb7df63981ceafb0ef882458e12f9774629ed/projected_source/core/changes_set.py#L15-L24)
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

📍 [`projected_source/languages/__init__.py:15-30`](https://github.com/sublimator/projected-source/blob/3a3eb7df63981ceafb0ef882458e12f9774629ed/projected_source/languages/__init__.py#L15-L30)
```python
  15 EXTRACTORS = {
  16     ".cpp": CppExtractor,
  17     ".cc": CppExtractor,
  18     ".cxx": CppExtractor,
  19     ".c++": CppExtractor,
  20     ".hpp": CppExtractor,
  21     ".h": CppExtractor,
  22     ".hxx": CppExtractor,
  23     ".h++": CppExtractor,
  24     ".c": CppExtractor,  # C is close enough to C++ for our purposes
  25     ".ipp": CppExtractor,  # Inline implementation files
  26     ".macro": CppExtractor,  # C preprocessor macro files (e.g., rippled sfields.macro)
  27     ".proto": ProtoExtractor,  # Protocol Buffers
  28     ".py": PythonExtractor,  # Python
  29     ".pyi": PythonExtractor,  # Python type stubs
  30 }
```

When a `code()` call needs to extract from a file, it calls `get_extractor()` which looks up the right class by file extension and instantiates it:

📍 [`projected_source/languages/__init__.py:33-53`](https://github.com/sublimator/projected-source/blob/3a3eb7df63981ceafb0ef882458e12f9774629ed/projected_source/languages/__init__.py#L33-L53)
```python
  33 def get_extractor(file_path: Path):
  34     """
  35     Get the appropriate extractor for a file based on its extension.
  36 
  37     Args:
  38         file_path: Path to the file
  39 
  40     Returns:
  41         An extractor instance
  42 
  43     Raises:
  44         ValueError: If no extractor is available for the file type
  45     """
  46     suffix = file_path.suffix.lower()
  47 
  48     if suffix not in EXTRACTORS:
  49         supported = ", ".join(EXTRACTORS.keys())
  50         raise ValueError(f"No extractor for {suffix} files. Supported: {supported}")
  51 
  52     extractor_class = EXTRACTORS[suffix]
  53     return extractor_class()
```

### BaseExtractor

All language extractors inherit from `BaseExtractor`, which provides the tree-sitter parser setup, line extraction, and the marker system. The marker system lets you tag regions of source code with `//@@start name` and `//@@end name` comments, then extract just that region:

📍 [`projected_source/core/extractor.py:17-134`](https://github.com/sublimator/projected-source/blob/3a3eb7df63981ceafb0ef882458e12f9774629ed/projected_source/core/extractor.py#L17-L134)
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
  48         return "\n".join(code_lines), start_line, end_line
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

📍 [`projected_source/core/renderer.py:35-70`](https://github.com/sublimator/projected-source/blob/3a3eb7df63981ceafb0ef882458e12f9774629ed/projected_source/core/renderer.py#L35-L70)
```python
  35     def __init__(
  36         self,
  37         template_dir: Path = None,
  38         repo_path: Path = None,
  39         remap_dirty_lines: bool = False,
  40         changes_set: "ChangesSet" = None,
  41     ):
  42         """
  43         Initialize the renderer.
  44 
  45         Args:
  46             template_dir: Directory containing templates (default: current dir)
  47             repo_path: Repository root path (default: current dir)
  48             remap_dirty_lines: If True, remap line numbers in dirty files to match
  49                                committed version (for sharing). Affects permalinks
  50                                and code block line numbers.
  51             changes_set: Optional ChangesSet for tracking documentation coverage.
  52                          When provided, each code() call will mark its region as
  53                          covered. Check changes_set.uncovered() after rendering.
  54         """
  55         self.template_dir = template_dir or Path.cwd()
  56         self.repo_path = repo_path or Path.cwd()
  57         self.remap_dirty_lines = remap_dirty_lines
  58         self.changes_set = changes_set
  59         self.github = GitHubIntegration(self.repo_path)
  60 
  61         # Create Jinja2 environment
  62         self.env = jinja2.Environment(
  63             loader=jinja2.FileSystemLoader(str(self.template_dir)), trim_blocks=True, lstrip_blocks=True
  64         )
  65 
  66         # Register custom functions
  67         self.env.globals["code"] = self._code_function
  68         self.env.globals["ghc"] = self._code_function  # Alias for compatibility
  69         self.env.globals["ignore_changes"] = self._ignore_changes_function
  70         self.env.globals["include"] = self._include_function
```

### The code() Function

This is the workhorse. Every `{{ code('file.cpp', function='foo') }}` call in a template invokes `_code_function`. It resolves the file path, picks the right extractor, extracts the requested symbol, optionally generates a GitHub permalink, adds line numbers, and returns formatted markdown:

📍 [`projected_source/core/renderer.py:75-310`](https://github.com/sublimator/projected-source/blob/3a3eb7df63981ceafb0ef882458e12f9774629ed/projected_source/core/renderer.py#L75-L310)
```python
  75     def _code_function(
  76         self,
  77         file_path: str,
  78         function: str = None,
  79         struct: str = None,
  80         var: str = None,
  81         function_macro: Union[str, Dict] = None,
  82         macro_definition: str = None,
  83         lines: Tuple[int, int] = None,
  84         marker: str = None,
  85         signature: str = None,
  86         message: str = None,
  87         enum: str = None,
  88         service: str = None,
  89         github: bool = True,
  90         blame: bool = False,
  91         line_numbers: bool = True,
  92         language: str = None,
  93     ) -> str:
  94         """
  95         Universal code extraction function for templates.
  96 
  97         Args:
  98             file_path: Path to the source file
  99             function: Function name to extract
 100             struct: Struct/class/enum name to extract (C/C++)
 101             var: Variable/constant declaration to extract (C/C++)
 102             function_macro: Macro that defines a function (dict with 'name' and optional 'arg0', 'arg1', etc)
 103             macro_definition: Macro definition name to extract (#define statement)
 104             lines: Tuple of (start_line, end_line) to extract
 105             marker: Marker name to extract between //@@start and //@@end
 106             signature: String to match against parameter types for overload disambiguation.
 107                        Use partial type names like "TMProposeSet" to select a specific overload.
 108             message: Message name to extract (protobuf)
 109             enum: Enum name to extract (protobuf)
 110             service: Service name to extract (protobuf)
 111             github: Include GitHub permalink (default: True)
 112             blame: Include git blame info (default: False)
 113             line_numbers: Show line numbers (default: True)
 114             language: Language for syntax highlighting (auto-detected if None)
 115 
 116         Returns:
 117             Formatted markdown with code block
 118 
 119         Examples in templates:
 120             {{ code('src/file.cpp', function='myFunc') }}
 121             {{ code('src/file.cpp', function='onMessage', signature='TMProposeSet') }}
 122             {{ code('src/file.cpp', struct='MyClass') }}
 123             {{ code('src/file.cpp', var='errorInfos') }}
 124             {{ code('src/file.cpp', lines=(10, 20)) }}
 125             {{ code('src/file.cpp', marker='example1') }}
 126             {{ code('src/proto/file.proto', message='MyMessage') }}
 127             {{ code('src/proto/file.proto', enum='MyEnum') }}
 128         """
 129         try:
 130             # Resolve file path relative to repo
 131             resolved_path = Path(file_path)
 132             if not resolved_path.is_absolute():
 133                 resolved_path = self.repo_path / resolved_path
 134 
 135             # Get the appropriate extractor
 136             extractor = get_extractor(resolved_path)
 137 
 138             # Extract code based on parameters
 139             if function:
 140                 # Check if we also have a marker - extract marker within function
 141                 if marker:
 142                     if hasattr(extractor, "extract_function_marker"):
 143                         code_text, start_line, end_line = extractor.extract_function_marker(
 144                             resolved_path, function, marker
 145                         )
 146                         logger.info(f"Extracted marker '{marker}' from function '{function}' in {file_path}")
 147                     else:
 148                         return "❌ **ERROR**: Function marker extraction not supported for this file type"
 149                 else:
 150                     code_text, start_line, end_line = extractor.extract_function(resolved_path, function, signature)
 151                     logger.info(f"Extracted function '{function}' from {file_path}")
 152             elif function_macro:
 153                 # Handle function_macro parameter
 154                 if isinstance(function_macro, str):
 155                     # Simple string -> convert to dict
 156                     macro_spec = {"name": function_macro}
 157                 else:
 158                     macro_spec = function_macro
 159 
 160                 # Check if we also have a marker - extract marker within macro
 161                 if marker:
 162                     code_text, start_line, end_line = extractor.extract_function_macro_marker(
 163                         resolved_path, macro_spec, marker
 164                     )
 165                     logger.info(f"Extracted marker '{marker}' from function_macro '{macro_spec}' in {file_path}")
 166                 else:
 167                     code_text, start_line, end_line = extractor.extract_function_macro(resolved_path, macro_spec)
 168                     logger.info(f"Extracted function_macro '{macro_spec}' from {file_path}")
 169             elif macro_definition:
 170                 code_text, start_line, end_line = extractor.extract_macro_definition(resolved_path, macro_definition)
 171                 logger.info(f"Extracted macro_definition '{macro_definition}' from {file_path}")
 172             elif var:
 173                 # Extract variable/constant declaration
 174                 if hasattr(extractor, "extract_variable"):
 175                     code_text, start_line, end_line = extractor.extract_variable(resolved_path, var)
 176                     logger.info(f"Extracted variable '{var}' from {file_path}")
 177                 elif hasattr(extractor, "extract_struct"):
 178                     # C/C++ uses extract_struct for var= (finds declarations)
 179                     if marker:
 180                         if hasattr(extractor, "extract_struct_marker"):
 181                             code_text, start_line, end_line = extractor.extract_struct_marker(
 182                                 resolved_path, var, marker
 183                             )
 184                             logger.info(f"Extracted marker '{marker}' from variable '{var}' in {file_path}")
 185                         else:
 186                             return "❌ **ERROR**: Marker extraction in variable not supported"
 187                     else:
 188                         code_text, start_line, end_line = extractor.extract_struct(resolved_path, var)
 189                         logger.info(f"Extracted variable '{var}' from {file_path}")
 190                 else:
 191                     return "❌ **ERROR**: Variable extraction not supported for this file type"
 192             elif struct:
 193                 # Extract struct/class/enum definition
 194                 if hasattr(extractor, "extract_struct"):
 195                     if marker:
 196                         if hasattr(extractor, "extract_struct_marker"):
 197                             code_text, start_line, end_line = extractor.extract_struct_marker(
 198                                 resolved_path, struct, marker
 199                             )
 200                             logger.info(f"Extracted marker '{marker}' from struct '{struct}' in {file_path}")
 201                         else:
 202                             return "❌ **ERROR**: Marker extraction in struct not supported"
 203                     else:
 204                         code_text, start_line, end_line = extractor.extract_struct(resolved_path, struct)
 205                         logger.info(f"Extracted struct/class '{struct}' from {file_path}")
 206                 else:
 207                     return "❌ **ERROR**: Struct/class extraction not supported for this file type"
 208             elif message:
 209                 # Extract protobuf message
 210                 if hasattr(extractor, "extract_message"):
 211                     if marker:
 212                         code_text, start_line, end_line = extractor.extract_message_marker(
 213                             resolved_path, message, marker
 214                         )
 215                         logger.info(f"Extracted marker '{marker}' from message '{message}' in {file_path}")
 216                     else:
 217                         code_text, start_line, end_line = extractor.extract_message(resolved_path, message)
 218                         logger.info(f"Extracted message '{message}' from {file_path}")
 219                 else:
 220                     return "❌ **ERROR**: Message extraction not supported for this file type"
 221             elif enum:
 222                 # Extract protobuf enum
 223                 if hasattr(extractor, "extract_enum"):
 224                     code_text, start_line, end_line = extractor.extract_enum(resolved_path, enum)
 225                     logger.info(f"Extracted enum '{enum}' from {file_path}")
 226                 else:
 227                     return "❌ **ERROR**: Enum extraction not supported for this file type"
 228             elif service:
 229                 # Extract protobuf service
 230                 if hasattr(extractor, "extract_service"):
 231                     code_text, start_line, end_line = extractor.extract_service(resolved_path, service)
 232                     logger.info(f"Extracted service '{service}' from {file_path}")
 233                 else:
 234                     return "❌ **ERROR**: Service extraction not supported for this file type"
 235             elif marker:
 236                 code_text, start_line, end_line = extractor.extract_marker(resolved_path, marker)
 237                 logger.info(f"Extracted marker '{marker}' from {file_path}")
 238             elif lines:
 239                 start_line, end_line = lines
 240                 code_text, start_line, end_line = extractor.extract_lines(resolved_path, start_line, end_line)
 241                 logger.info(f"Extracted lines {start_line}-{end_line} from {file_path}")
 242             else:
 243                 return (
 244                     f"❌ **ERROR**: Must specify function, struct, var, function_macro, "
 245                     f"macro_definition, lines, or marker for {file_path}"
 246                 )
 247 
 248             # Track this region as covered if we have a ChangesSet
 249             if self.changes_set is not None:
 250                 self.changes_set.subtract(resolved_path, start_line, end_line)
 251 
 252             # Remap line numbers if requested (for sharing docs from dirty files)
 253             display_start = start_line
 254             display_end = end_line
 255             if self.remap_dirty_lines:
 256                 display_start = self.github.map_to_committed_line(resolved_path, start_line)
 257                 display_end = self.github.map_to_committed_line(resolved_path, end_line)
 258 
 259             # Build header with GitHub permalink if requested
 260             if github:
 261                 header = self.github.get_permalink(
 262                     resolved_path, start_line, end_line, display_committed_lines=self.remap_dirty_lines
 263                 )
 264             else:
 265                 rel_path = resolved_path.relative_to(self.repo_path) if resolved_path.is_absolute() else resolved_path
 266                 if display_start == display_end:
 267                     header = f"📍 `{rel_path}:{display_start}`"
 268                 else:
 269                     header = f"📍 `{rel_path}:{display_start}-{display_end}`"
 270 
 271             # Format code with line numbers and/or blame
 272             # Use remapped line numbers for display if remap_dirty_lines is enabled
 273             code_start_line = display_start if self.remap_dirty_lines else start_line
 274             if blame:
 275                 code_text = self.github.format_with_blame(code_text, code_start_line, resolved_path)
 276             elif line_numbers:
 277                 code_text = self._add_line_numbers(code_text, code_start_line)
 278 
 279             # Auto-detect language if not specified
 280             if not language:
 281                 suffix = resolved_path.suffix.lower()
 282                 language_map = {
 283                     ".cpp": "cpp",
 284                     ".cc": "cpp",
 285                     ".cxx": "cpp",
 286                     ".hpp": "cpp",
 287                     ".h": "cpp",
 288                     ".hxx": "cpp",
 289                     ".ipp": "cpp",  # Inline implementation files
 290                     ".macro": "cpp",  # C preprocessor macro files
 291                     ".c": "c",
 292                     ".py": "python",
 293                     ".js": "javascript",
 294                     ".ts": "typescript",
 295                     ".java": "java",
 296                     ".rs": "rust",
 297                     ".go": "go",
 298                     ".proto": "protobuf",
 299                 }
 300                 language = language_map.get(suffix, "text")
 301 
 302             # Build final output
 303             return f"{header}\n```{language}\n{code_text}\n```"
 304 
 305         except Exception as e:
 306             error_msg = f"❌ **ERROR**: {e}"
 307             logger.error(f"Code extraction failed: {e}")
 308             # Collect file as fixture if collection is enabled
 309             _collect_error_fixture(resolved_path, str(e))
 310             return error_msg
```

The function handles a wide variety of extraction types — functions, structs, variables, macros, protobuf messages, enums, services, markers, and raw line ranges. It also supports nesting: you can extract a marker *within* a function by passing both `function=` and `marker=`.

When a `ChangesSet` is provided (validation mode), each extraction automatically calls `subtract()` to mark those lines as documented.

### The include() Function

Templates can compose by including other files. Plain markdown files are included verbatim; `.j2` files are rendered as templates with full access to `code()` and other functions:

📍 [`projected_source/core/renderer.py:375-398`](https://github.com/sublimator/projected-source/blob/3a3eb7df63981ceafb0ef882458e12f9774629ed/projected_source/core/renderer.py#L375-L398)
```python
 375     def _include_function(self, path: str) -> str:
 376         """
 377         Include a file into the template output.
 378 
 379         .j2 files are rendered as Jinja2 templates (with access to code() etc).
 380         All other files are included as raw text.
 381 
 382         Args:
 383             path: Path relative to the template directory
 384 
 385         Returns:
 386             File contents (rendered if .j2)
 387 
 388         Examples:
 389             {{ include('background.md') }}
 390             {{ include('details.md.j2') }}
 391             {{ include('sections/intro.md') }}
 392         """
 393         if path.endswith(".j2"):
 394             template = self.env.get_template(path)
 395             return template.render()
 396         else:
 397             full_path = self.template_dir / path
 398             return full_path.read_text()
```

### Custom Tags

Projects can extend the template environment by placing a `.projected-source.py` file in the project. The renderer discovers it by walking up from the template directory to the git root:

📍 [`projected_source/core/renderer.py:400-428`](https://github.com/sublimator/projected-source/blob/3a3eb7df63981ceafb0ef882458e12f9774629ed/projected_source/core/renderer.py#L400-L428)
```python
 400     def _find_custom_tags_file(self, start_path: Path) -> Optional[Path]:
 401         """
 402         Find .projected-source.py file by walking up from start_path.
 403         Stops at git root to avoid escaping the repository.
 404 
 405         Args:
 406             start_path: Path to start searching from (usually template dir)
 407 
 408         Returns:
 409             Path to .projected-source.py if found, None otherwise
 410         """
 411         current = start_path.resolve()
 412 
 413         # Use repo_path as the boundary (it's already the git root)
 414         git_root = self.repo_path
 415 
 416         while current >= git_root:
 417             custom_file = current / ".projected-source.py"
 418             if custom_file.exists():
 419                 logger.info(f"Found custom tags file at {custom_file}")
 420                 return custom_file
 421 
 422             # Move up one directory
 423             parent = current.parent
 424             if parent == current:  # Reached filesystem root
 425                 break
 426             current = parent
 427 
 428         return None
```

### Rendering

The public API is straightforward — `render_template()` for named templates and `render_template_file()` for file paths:

📍 [`projected_source/core/renderer.py:478-501`](https://github.com/sublimator/projected-source/blob/3a3eb7df63981ceafb0ef882458e12f9774629ed/projected_source/core/renderer.py#L478-L501)
```python
 478     def render_template(self, template_name: str, **context) -> str:
 479         """
 480         Render a template with the given context.
 481 
 482         Args:
 483             template_name: Name of the template file
 484             **context: Additional context variables
 485 
 486         Returns:
 487             Rendered template as string
 488         """
 489         try:
 490             # Load custom tags from .projected-source.py if available
 491             template_path = self.template_dir / template_name
 492             self._load_custom_tags(template_path)
 493 
 494             template = self.env.get_template(template_name)
 495             return template.render(**context)
 496         except jinja2.TemplateNotFound:
 497             logger.error(f"Template not found: {template_name}")
 498             raise
 499         except Exception as e:
 500             logger.error(f"Template rendering failed: {e}")
 501             raise
```

---

## GitHub Integration

Every extracted code block can include a clickable GitHub permalink. The `GitHubIntegration` class handles the git plumbing — detecting the repository URL, mapping line numbers in dirty files to their committed counterparts, and generating blame annotations.

### Lazy Initialization

Repository info is loaded on first access. The class auto-detects the GitHub URL from the git remote, handling both SSH and HTTPS formats:

📍 [`projected_source/core/github.py:186-228`](https://github.com/sublimator/projected-source/blob/3a3eb7df63981ceafb0ef882458e12f9774629ed/projected_source/core/github.py#L186-L228)
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

📍 [`projected_source/core/github.py:37-83`](https://github.com/sublimator/projected-source/blob/3a3eb7df63981ceafb0ef882458e12f9774629ed/projected_source/core/github.py#L37-L83)
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

📍 [`projected_source/core/github.py:138-173`](https://github.com/sublimator/projected-source/blob/3a3eb7df63981ceafb0ef882458e12f9774629ed/projected_source/core/github.py#L138-L173)
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

📍 [`projected_source/core/github.py:313-388`](https://github.com/sublimator/projected-source/blob/3a3eb7df63981ceafb0ef882458e12f9774629ed/projected_source/core/github.py#L313-L388)
```python
 313     def get_permalink(
 314         self, file_path: Path, start_line: int = None, end_line: int = None, display_committed_lines: bool = True
 315     ) -> str:
 316         """
 317         Generate a GitHub permalink for a file or line range.
 318 
 319         Args:
 320             file_path: Path to the file
 321             start_line: Optional start line number (1-based)
 322             end_line: Optional end line number (1-based)
 323             display_committed_lines: If True, display shows committed line numbers (matches link).
 324                                      If False, display shows working copy line numbers.
 325 
 326         Returns:
 327             Formatted markdown link or plain text reference
 328         """
 329         # Make path relative to repo root
 330         try:
 331             if file_path.is_absolute():
 332                 rel_path = file_path.relative_to(self.repo_path)
 333             else:
 334                 rel_path = file_path
 335         except ValueError:
 336             rel_path = file_path
 337 
 338         if self.github_url and self.commit_hash:
 339             # Map line numbers if file is dirty (has uncommitted changes like markers)
 340             committed_start = None
 341             committed_end = None
 342             is_dirty = False
 343 
 344             if start_line is not None:
 345                 committed_start = self.map_to_committed_line(file_path, start_line)
 346                 is_dirty = committed_start != start_line
 347                 if end_line is not None:
 348                     committed_end = self.map_to_committed_line(file_path, end_line)
 349 
 350             # Build GitHub URL with committed line numbers
 351             url = f"{self.github_url}/blob/{self.commit_hash}/{rel_path}"
 352 
 353             # Add line anchors if specified (using committed line numbers for URL)
 354             if committed_start is not None:
 355                 # Choose which line numbers to display
 356                 if display_committed_lines or not is_dirty:
 357                     display_start = committed_start
 358                     display_end = committed_end
 359                 else:
 360                     # start_line must be set if committed_start was computed
 361                     assert start_line is not None
 362                     display_start = start_line
 363                     display_end = end_line
 364 
 365                 if committed_end and committed_end != committed_start:
 366                     url += f"#L{committed_start}-L{committed_end}"
 367                     display = f"{rel_path}:{display_start}-{display_end}"
 368                     if is_dirty:
 369                         logger.debug(
 370                             f"Dirty file: mapped lines {start_line}-{end_line} → {committed_start}-{committed_end}"
 371                         )
 372                 else:
 373                     url += f"#L{committed_start}"
 374                     display = f"{rel_path}:{display_start}"
 375             else:
 376                 display = str(rel_path)
 377 
 378             # Return as markdown link
 379             return f"📍 [`{display}`]({url})"
 380         else:
 381             # No GitHub info, return plain text
 382             if start_line is not None:
 383                 if end_line and end_line != start_line:
 384                     return f"📍 `{rel_path}:{start_line}-{end_line}`"
 385                 else:
 386                     return f"📍 `{rel_path}:{start_line}`"
 387             else:
 388                 return f"📍 `{rel_path}`"
```

### Blame Support

For deeper code archaeology, `blame=True` annotates each line with its author, date, and commit hash:

📍 [`projected_source/core/github.py:451-481`](https://github.com/sublimator/projected-source/blob/3a3eb7df63981ceafb0ef882458e12f9774629ed/projected_source/core/github.py#L451-L481)
```python
 451     def format_with_blame(self, code_text: str, start_line: int, file_path: Path) -> str:
 452         """
 453         Format code with git blame information.
 454 
 455         Args:
 456             code_text: The code to format
 457             start_line: Starting line number
 458             file_path: Path to the file
 459 
 460         Returns:
 461             Formatted code with blame info
 462         """
 463         lines = code_text.splitlines()
 464         end_line = start_line + len(lines) - 1
 465 
 466         blame_info = self.get_blame(file_path, start_line, end_line)
 467 
 468         formatted_lines = []
 469         for i, line in enumerate(lines):
 470             line_num = start_line + i
 471 
 472             if line_num in blame_info:
 473                 blame = blame_info[line_num]
 474                 # Format: line_num | commit | author | date | code
 475                 formatted_line = f"{line_num:4} │ {blame['commit']} │ {blame['author']:<20} │ {blame['date']} │ {line}"
 476             else:
 477                 formatted_line = f"{line_num:4} │ {line}"
 478 
 479             formatted_lines.append(formatted_line)
 480 
 481         return "\n".join(formatted_lines)
```

---

## Change Validation

One of the most powerful features: projected-source can verify that your documentation actually covers the code that changed. Run with `-V` and it diffs against a base commit, tracks which regions each `code()` call covers, and reports any gaps.

### ChangesSet

The `ChangesSet` class tracks changed regions as a set of non-overlapping intervals per file. It supports adding regions (which auto-merge overlapping ranges), subtracting regions (which can split intervals), and querying what's left uncovered:

📍 [`projected_source/core/changes_set.py:27-248`](https://github.com/sublimator/projected-source/blob/3a3eb7df63981ceafb0ef882458e12f9774629ed/projected_source/core/changes_set.py#L27-L248)
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
 115 
 116             # Hunk header: @@ -old_start,old_count +new_start,new_count @@
 117             elif line.startswith("@@"):
 118                 # Parse new file position
 119                 parts = line.split()
 120                 if len(parts) >= 3:
 121                     new_range = parts[2]  # e.g., "+10,5" or "+10"
 122                     if new_range.startswith("+"):
 123                         new_range = new_range[1:]
 124                         if "," in new_range:
 125                             current_new_line = int(new_range.split(",")[0])
 126                         else:
 127                             current_new_line = int(new_range)
 128 
 129             # Added or context line - track position
 130             elif current_file and not line.startswith("-"):
 131                 if line.startswith("+") or line.startswith(" "):
 132                     # This line exists in the new version
 133                     if line.startswith("+"):
 134                         # Added line - definitely needs coverage
 135                         self.add(current_file, current_new_line, current_new_line)
 136                     elif line.startswith(" "):
 137                         # Context line around a change - also needs coverage
 138                         # (user chose "all changed" which includes context)
 139                         self.add(current_file, current_new_line, current_new_line)
 140                     current_new_line += 1
 141 
 142             # Deleted line - doesn't increment new line counter
 143             elif line.startswith("-") and not line.startswith("---"):
 144                 pass  # Deletion - surrounding context already captured
 145 
 146     def add(self, file_path: Path, start: int, end: int) -> None:
 147         """
 148         Add a region, merging with overlapping or adjacent regions.
 149 
 150         Args:
 151             file_path: Path to the file
 152             start: Start line (1-based, inclusive)
 153             end: End line (1-based, inclusive)
 154         """
 155         if start > end:
 156             start, end = end, start
 157 
 158         regions = self._regions.setdefault(file_path, [])
 159 
 160         # Add new region and re-merge everything
 161         regions.append((start, end))
 162         self._regions[file_path] = self._merge_sorted(sorted(regions))
 163 
 164     def _merge_sorted(self, regions: List[Tuple[int, int]]) -> List[Tuple[int, int]]:
 165         """Merge a sorted list of potentially overlapping regions."""
 166         if not regions:
 167             return []
 168 
 169         result = [regions[0]]
 170         for start, end in regions[1:]:
 171             last_start, last_end = result[-1]
 172             if start <= last_end + 1:
 173                 # Overlapping or adjacent - merge
 174                 result[-1] = (last_start, max(last_end, end))
 175             else:
 176                 result.append((start, end))
 177         return result
 178 
 179     def subtract(self, file_path: Path, start: int, end: int) -> None:
 180         """
 181         Remove a region (mark as covered by documentation).
 182 
 183         May split existing regions if the subtracted region is in the middle.
 184 
 185         Args:
 186             file_path: Path to the file
 187             start: Start line (1-based, inclusive)
 188             end: End line (1-based, inclusive)
 189         """
 190         if file_path not in self._regions:
 191             return
 192 
 193         if start > end:
 194             start, end = end, start
 195 
 196         new_regions: List[Tuple[int, int]] = []
 197 
 198         for reg_start, reg_end in self._regions[file_path]:
 199             # No overlap - keep as is
 200             if end < reg_start or start > reg_end:
 201                 new_regions.append((reg_start, reg_end))
 202 
 203             # Full coverage - remove entirely
 204             elif start <= reg_start and end >= reg_end:
 205                 pass  # Don't add it
 206 
 207             # Partial overlap - may need to split
 208             else:
 209                 # Left remainder
 210                 if reg_start < start:
 211                     new_regions.append((reg_start, start - 1))
 212                 # Right remainder
 213                 if reg_end > end:
 214                     new_regions.append((end + 1, reg_end))
 215 
 216         if new_regions:
 217             self._regions[file_path] = new_regions
 218         else:
 219             del self._regions[file_path]
 220 
 221     def uncovered(self) -> List[ChangeRegion]:
 222         """Return list of regions not yet claimed by documentation."""
 223         result = []
 224         for file_path, regions in sorted(self._regions.items()):
 225             for start, end in regions:
 226                 result.append(ChangeRegion(file_path, start, end))
 227         return result
 228 
 229     def is_complete(self) -> bool:
 230         """Return True if all regions have been claimed."""
 231         return len(self._regions) == 0
 232 
 233     def files(self) -> List[Path]:
 234         """Return list of files with uncovered changes."""
 235         return list(self._regions.keys())
 236 
 237     def __len__(self) -> int:
 238         """Return total number of uncovered regions."""
 239         return sum(len(regions) for regions in self._regions.values())
 240 
 241     def __bool__(self) -> bool:
 242         """Return True if there are uncovered regions."""
 243         return len(self._regions) > 0
 244 
 245     def __repr__(self) -> str:
 246         total = len(self)
 247         files = len(self._regions)
 248         return f"ChangesSet({total} regions in {files} files)"
```

### Building from Git Diff

`from_diff()` parses unified diff output to populate the set. It supports both simple base refs (`origin/main`) and explicit ranges (`HEAD~5..HEAD~2`):

📍 [`projected_source/core/changes_set.py:40-73`](https://github.com/sublimator/projected-source/blob/3a3eb7df63981ceafb0ef882458e12f9774629ed/projected_source/core/changes_set.py#L40-L73)
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

📍 [`projected_source/core/changes_set.py:105-144`](https://github.com/sublimator/projected-source/blob/3a3eb7df63981ceafb0ef882458e12f9774629ed/projected_source/core/changes_set.py#L105-L144)
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
 115 
 116             # Hunk header: @@ -old_start,old_count +new_start,new_count @@
 117             elif line.startswith("@@"):
 118                 # Parse new file position
 119                 parts = line.split()
 120                 if len(parts) >= 3:
 121                     new_range = parts[2]  # e.g., "+10,5" or "+10"
 122                     if new_range.startswith("+"):
 123                         new_range = new_range[1:]
 124                         if "," in new_range:
 125                             current_new_line = int(new_range.split(",")[0])
 126                         else:
 127                             current_new_line = int(new_range)
 128 
 129             # Added or context line - track position
 130             elif current_file and not line.startswith("-"):
 131                 if line.startswith("+") or line.startswith(" "):
 132                     # This line exists in the new version
 133                     if line.startswith("+"):
 134                         # Added line - definitely needs coverage
 135                         self.add(current_file, current_new_line, current_new_line)
 136                     elif line.startswith(" "):
 137                         # Context line around a change - also needs coverage
 138                         # (user chose "all changed" which includes context)
 139                         self.add(current_file, current_new_line, current_new_line)
 140                     current_new_line += 1
 141 
 142             # Deleted line - doesn't increment new line counter
 143             elif line.startswith("-") and not line.startswith("---"):
 144                 pass  # Deletion - surrounding context already captured
```

### Subtract and Query

As templates render, each `code()` call subtracts its extracted region. The `subtract()` method handles partial overlaps — if documentation covers the middle of a changed region, it splits into two uncovered remainders:

📍 [`projected_source/core/changes_set.py:179-219`](https://github.com/sublimator/projected-source/blob/3a3eb7df63981ceafb0ef882458e12f9774629ed/projected_source/core/changes_set.py#L179-L219)
```python
 179     def subtract(self, file_path: Path, start: int, end: int) -> None:
 180         """
 181         Remove a region (mark as covered by documentation).
 182 
 183         May split existing regions if the subtracted region is in the middle.
 184 
 185         Args:
 186             file_path: Path to the file
 187             start: Start line (1-based, inclusive)
 188             end: End line (1-based, inclusive)
 189         """
 190         if file_path not in self._regions:
 191             return
 192 
 193         if start > end:
 194             start, end = end, start
 195 
 196         new_regions: List[Tuple[int, int]] = []
 197 
 198         for reg_start, reg_end in self._regions[file_path]:
 199             # No overlap - keep as is
 200             if end < reg_start or start > reg_end:
 201                 new_regions.append((reg_start, reg_end))
 202 
 203             # Full coverage - remove entirely
 204             elif start <= reg_start and end >= reg_end:
 205                 pass  # Don't add it
 206 
 207             # Partial overlap - may need to split
 208             else:
 209                 # Left remainder
 210                 if reg_start < start:
 211                     new_regions.append((reg_start, start - 1))
 212                 # Right remainder
 213                 if reg_end > end:
 214                     new_regions.append((end + 1, reg_end))
 215 
 216         if new_regions:
 217             self._regions[file_path] = new_regions
 218         else:
 219             del self._regions[file_path]
```

After rendering, `uncovered()` returns whatever's left:

📍 [`projected_source/core/changes_set.py:221-227`](https://github.com/sublimator/projected-source/blob/3a3eb7df63981ceafb0ef882458e12f9774629ed/projected_source/core/changes_set.py#L221-L227)
```python
 221     def uncovered(self) -> List[ChangeRegion]:
 222         """Return list of regions not yet claimed by documentation."""
 223         result = []
 224         for file_path, regions in sorted(self._regions.items()):
 225             for start, end in regions:
 226                 result.append(ChangeRegion(file_path, start, end))
 227         return result
```

---

## CLI Interface

The CLI is built with Click. The main entry point registers all commands:

📍 [`projected_source/cli/__init__.py:19-29`](https://github.com/sublimator/projected-source/blob/3a3eb7df63981ceafb0ef882458e12f9774629ed/projected_source/cli/__init__.py#L19-L29)
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

📍 [`projected_source/cli/render.py:356-386`](https://github.com/sublimator/projected-source/blob/3a3eb7df63981ceafb0ef882458e12f9774629ed/projected_source/cli/render.py#L356-L386)
```python
 356 def _render_file(
 357     input_file, output_file, repo_path, output_to_stdout, remap_dirty_lines=False, changes_set=None, header=False
 358 ):
 359     """Render a single template file."""
 360     # Determine template directory
 361     template_dir = input_file.parent
 362     template_name = input_file.name
 363 
 364     # Create renderer
 365     renderer = TemplateRenderer(
 366         template_dir=template_dir, repo_path=repo_path, remap_dirty_lines=remap_dirty_lines, changes_set=changes_set
 367     )
 368 
 369     try:
 370         rendered = renderer.render_template(template_name)
 371 
 372         if header:
 373             rendered = _build_header(template_name, repo_path) + rendered
 374 
 375         if output_to_stdout:
 376             # Output to stdout
 377             click.echo(rendered)
 378         else:
 379             # Output to file
 380             output_file.parent.mkdir(parents=True, exist_ok=True)
 381             output_file.write_text(rendered)
 382             console.print(f"[green]✓[/green] {input_file} → {output_file}")
 383 
 384     except Exception as e:
 385         console.print(f"[red]✗ Failed to render {input_file}:[/red] {e}")
 386         sys.exit(1)
```

Directory rendering walks the tree and renders all `.j2` files:

📍 [`projected_source/cli/render.py:389-446`](https://github.com/sublimator/projected-source/blob/3a3eb7df63981ceafb0ef882458e12f9774629ed/projected_source/cli/render.py#L389-L446)
```python
 389 def _render_directory(input_dir, output_dir, repo_path, remap_dirty_lines=False, changes_set=None, header=False):
 390     """Render all templates in a directory."""
 391     templates = list(input_dir.glob("**/*.j2"))
 392 
 393     if not templates:
 394         console.print(f"[yellow]No .j2 templates found in {input_dir}[/yellow]")
 395         return
 396 
 397     console.print(f"[bold]Processing {len(templates)} templates from {input_dir}[/bold]")
 398 
 399     # Create renderer
 400     renderer = TemplateRenderer(
 401         template_dir=input_dir, repo_path=repo_path, remap_dirty_lines=remap_dirty_lines, changes_set=changes_set
 402     )
 403 
 404     # Track results
 405     success_count = 0
 406     failed = []
 407 
 408     # Process each template
 409     for template_path in templates:
 410         rel_path = template_path.relative_to(input_dir)
 411 
 412         # Determine output path (strip .j2 extension)
 413         if rel_path.suffix == ".j2":
 414             output_rel_path = rel_path.with_suffix("")
 415         else:
 416             output_rel_path = rel_path
 417 
 418         output_path_full = output_dir / output_rel_path
 419 
 420         try:
 421             # Render template
 422             rendered = renderer.render_template(str(rel_path))
 423 
 424             if header:
 425                 rendered = _build_header(str(rel_path), repo_path) + rendered
 426 
 427             # Write output
 428             output_path_full.parent.mkdir(parents=True, exist_ok=True)
 429             output_path_full.write_text(rendered)
 430 
 431             console.print(f"  [green]✓[/green] {rel_path} → {output_rel_path}")
 432             success_count += 1
 433 
 434         except Exception as e:
 435             console.print(f"  [red]✗[/red] {rel_path}: {e}")
 436             failed.append((rel_path, str(e)))
 437 
 438     # Summary
 439     console.print("\n[bold]Summary:[/bold]")
 440     console.print(f"  [green]{success_count} templates rendered successfully[/green]")
 441 
 442     if failed:
 443         console.print(f"  [red]{len(failed)} templates failed:[/red]")
 444         for template, error in failed:
 445             console.print(f"    • {template}: {error}")
 446         sys.exit(1)
```

### Symbol Discovery

The `list-functions` command is essential for authoring templates — it shows every extractable symbol in a file, including the parameter you'd use in a `code()` call:

📍 [`projected_source/cli/list_symbols.py:14-96`](https://github.com/sublimator/projected-source/blob/3a3eb7df63981ceafb0ef882458e12f9774629ed/projected_source/cli/list_symbols.py#L14-L96)
```python
  14 @click.command("list-functions")
  15 @click.argument("file", required=False, type=click.Path(exists=True))
  16 def list_functions(file):
  17     """List extractable symbols in a file.
  18 
  19     When FILE is given, lists all functions, classes, structs, enums,
  20     variables, and markers that can be extracted with code() calls.
  21 
  22     When no FILE is given, shows available extraction parameters.
  23     """
  24     if not file:
  25         _show_params_table()
  26         return
  27 
  28     file_path = Path(file).resolve()
  29 
  30     try:
  31         extractor = get_extractor(file_path)
  32     except ValueError as e:
  33         console.print(f"[red]{e}[/red]")
  34         raise SystemExit(1)
  35 
  36     if not hasattr(extractor, "list_symbols"):
  37         console.print(f"[red]Symbol listing not supported for {file_path.suffix} files[/red]")
  38         raise SystemExit(1)
  39 
  40     symbols = extractor.list_symbols(file_path)
  41 
  42     if not symbols:
  43         console.print(f"[yellow]No extractable symbols found in {file}[/yellow]")
  44         return
  45 
  46     # Detect overloaded functions
  47     func_names = [s["name"] for s in symbols if s["param"] == "function"]
  48     name_counts = Counter(func_names)
  49     overloaded = {name for name, count in name_counts.items() if count > 1}
  50 
  51     # Group by param
  52     groups = {}
  53     for sym in symbols:
  54         param = sym["param"]
  55         if param not in groups:
  56             groups[param] = []
  57         groups[param].append(sym)
  58 
  59     # Display
  60     console.print(f"\n[bold]{file}[/bold]\n")
  61 
  62     display_order = ["function", "struct", "var", "message", "enum", "service", "marker"]
  63 
  64     for param in display_order:
  65         if param not in groups:
  66             continue
  67 
  68         syms = groups[param]
  69         count = len(syms)
  70         console.print(f"  [bold]{param}=[/bold] [dim]({count})[/dim]")
  71 
  72         for sym in syms:
  73             name = sym["name"]
  74             line = sym["line"]
  75             kind = sym["kind"]
  76 
  77             parts = []
  78 
  79             # Show kind if it differs from param (e.g. class vs struct param)
  80             if kind != param:
  81                 parts.append(f"[dim]{kind}[/dim]")
  82 
  83             # Line info
  84             if sym.get("end_line"):
  85                 parts.append(f"[dim]lines {line}-{sym['end_line']}[/dim]")
  86             else:
  87                 parts.append(f"[dim]line {line}[/dim]")
  88 
  89             # Show signature hint for overloaded functions
  90             if name in overloaded and sym.get("signature"):
  91                 parts.append(f"[dim]signature='{sym['signature']}'[/dim]")
  92 
  93             extra = "  ".join(parts)
  94             console.print(f"    [cyan]'{name}'[/cyan]  {extra}")
  95 
  96         console.print()
```