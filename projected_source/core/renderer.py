"""
Jinja2 template rendering with code extraction functions.
"""

from __future__ import annotations

import logging
import re
import subprocess
import tempfile
from dataclasses import dataclass, field
from inspect import signature as inspect_signature
from pathlib import Path
from typing import TYPE_CHECKING, Dict, List, Optional, Tuple, Union

import jinja2
from jinja2 import nodes, pass_context
from jinja2.ext import Extension

from ..languages import get_extractor
from .github import GitHubIntegration

if TYPE_CHECKING:
    from .changes_set import ChangesSet

logger = logging.getLogger(__name__)

ERROR_PREFIX = "❌ **ERROR**:"

MARKER_DIRECTIVE_RE = re.compile(r"^\s*(?://|#|--)\s*@@(?:start|end)\b")
FRONTMATTER_RE = re.compile(r"\A---[ \t]*\r?\n.*?\r?\n(?:---|\.\.\.)[ \t]*(?:\r?\n|\Z)", re.DOTALL)
PROJECTED_SOURCE_HEADER_RE = re.compile(
    r"\A<!--\r?\n"
    r"rendered_from: .*?\r?\n"
    r"-->\r?\n"
    r"\r?\n---\r?\n"
    r"\r?\n<sub>Last updated: .*?</sub>\r?\n"
    r"\r?\n---[ \t]*(?:\r?\n|\Z)",
    re.DOTALL,
)


@dataclass(frozen=True)
class CodeError:
    """A code() extraction that failed during a render.

    file_path/target are the template's own words for what it asked for, so a
    caller can report the failure without re-deriving it from the output.
    """

    message: str
    file_path: str
    target: Optional[str] = None

    def __str__(self) -> str:
        where = f"{self.file_path} ({self.target})" if self.target else self.file_path
        return f"{where}: {self.message}"


@dataclass
class RenderResult:
    """A rendered document plus the extractions that failed producing it.

    code() degrades failures into the text rather than raising, so a render can
    succeed and still be wrong. Consult errors — never scan text for
    ERROR_PREFIX: a document that legitimately quotes error-handling source
    would look broken.
    """

    text: str
    errors: List[CodeError] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


class CodeContextExtension(Extension):
    """Jinja2 extension for {% code_context root='path', ref='branch' %}...{% endcode_context %} blocks."""

    tags = {"code_context"}

    def parse(self, parser):
        lineno = next(parser.stream).lineno
        # Parse keyword arguments
        kwargs = []
        while parser.stream.current.test("name") and parser.stream.look().test("assign"):
            key = parser.stream.expect("name").value
            parser.stream.expect("assign")
            value = parser.parse_expression()
            kwargs.append(nodes.Keyword(key, value, lineno=lineno))
            if parser.stream.current.test("comma"):
                next(parser.stream)

        body = parser.parse_statements(["name:endcode_context"], drop_needle=True)

        node = nodes.CallBlock(self.call_method("_set_context", [], kwargs), [], [], body).set_lineno(lineno)
        return node

    def _set_context(self, root=None, ref=None, caller=None):
        old_root = self.environment.globals.get("code_root", "")
        old_ref = self.environment.globals.get("code_ref", "")
        if root is not None:
            self.environment.globals["code_root"] = root
        if ref is not None:
            self.environment.globals["code_ref"] = ref
        try:
            return caller()
        finally:
            self.environment.globals["code_root"] = old_root
            self.environment.globals["code_ref"] = old_ref


def _collect_error_fixture(file_path: Path, error: str, template_context: str = None):
    """Collect a file as a fixture if fixture collection is enabled."""
    # Import here to avoid circular imports
    from ..cli.helpers import get_fixture_collector

    collector = get_fixture_collector()
    if collector:
        collector.collect(file_path, error, template_context)


class TemplateRenderer:
    """Render Jinja2 templates with code extraction functions."""

    def __init__(
        self,
        template_dir: Path = None,
        repo_path: Path = None,
        remap_dirty_lines: bool = False,
        changes_set: "ChangesSet" = None,
        default_enclosure_context: int = 3,
    ):
        """
        Initialize the renderer.

        Args:
            template_dir: Directory containing templates (default: current dir)
            repo_path: Repository root path (default: current dir)
            remap_dirty_lines: If True, remap line numbers in dirty files to match
                               committed version (for sharing). Affects permalinks
                               and code block line numbers.
            changes_set: Optional ChangesSet for tracking documentation coverage.
                         When provided, each code() call will mark its region as
                         covered. Check changes_set.uncovered() after rendering.
            default_enclosure_context: Default C/C++ enclosure_context for marker code() calls
                                      that do not specify it explicitly.
        """
        self.template_dir = template_dir or Path.cwd()
        self.repo_path = repo_path or Path.cwd()
        self.remap_dirty_lines = remap_dirty_lines
        self.changes_set = changes_set
        self.default_enclosure_context = self._normalize_enclosure_context(default_enclosure_context)
        self.github = GitHubIntegration(self.repo_path)

        # Failed code() extractions for the render in flight; reset per render.
        self._errors: List[CodeError] = []

        # Create Jinja2 environment
        self.env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(str(self.template_dir)),
            trim_blocks=True,
            lstrip_blocks=True,
            extensions=[CodeContextExtension],
        )

        # Register custom functions
        self.env.globals["code"] = self._code_function
        self.env.globals["ghc"] = self._code_function  # Alias for compatibility
        self.env.globals["ignore_changes"] = self._ignore_changes_function
        self.env.globals["include"] = self._include_function
        self.env.globals["include_body"] = self._include_body_function
        self.env.globals["set_code_context"] = self._set_code_context_function
        self.env.globals["set_code_root"] = self._set_code_root_function

        # Load project-specific custom tags if available
        # (loaded on-demand when rendering templates)

    def _code_function(
        self,
        file_path: str,
        function: str = None,
        struct: str = None,
        var: str = None,
        function_macro: Union[str, Dict] = None,
        macro_definition: str = None,
        lines: Tuple[int, int] = None,
        marker: str = None,
        signature: str = None,
        message: str = None,
        enum: str = None,
        service: str = None,
        github: bool = True,
        blame: bool = False,
        line_numbers: bool = True,
        language: str = None,
        ref: str = None,
        root: str = None,
        enclosure: str = None,
        enclosure_context: int = None,
    ) -> str:
        """
        Universal code extraction function for templates.

        Args:
            file_path: Path to the source file
            function: Function name to extract
            struct: Struct/class/enum name to extract (C/C++)
            var: Variable/constant declaration to extract (C/C++)
            function_macro: Macro that defines a function (dict with 'name' and optional 'arg0', 'arg1', etc)
            macro_definition: Macro definition name to extract (#define statement)
            lines: Tuple of (start_line, end_line) to extract
            marker: Marker name to extract between //@@start and //@@end
            signature: String to match against parameter types for overload disambiguation.
                       Use partial type names like "TMProposeSet" to select a specific overload.
            message: Message name to extract (protobuf)
            enum: Enum name to extract (protobuf)
            service: Service name to extract (protobuf)
            github: Include GitHub permalink (default: True)
            blame: Include git blame info (default: False)
            line_numbers: Show line numbers (default: True)
            language: Language for syntax highlighting (auto-detected if None)
            enclosure: Set to "auto" with C/C++ marker= to find the closest enclosing symbol.
            enclosure_context: For supported marker extractions, show the first
                               and last N lines of the enclosing symbol around the marker.

        Returns:
            Formatted markdown with code block

        Examples in templates:
            {{ code('src/file.cpp', function='myFunc') }}
            {{ code('src/file.cpp', function='onMessage', signature='TMProposeSet') }}
            {{ code('src/file.cpp', struct='MyClass') }}
            {{ code('src/file.cpp', var='errorInfos') }}
            {{ code('src/file.cpp', lines=(10, 20)) }}
            {{ code('src/file.cpp', marker='example1') }}
            {{ code('src/proto/file.proto', message='MyMessage') }}
            {{ code('src/proto/file.proto', enum='MyEnum') }}
        """
        tmp_file = None
        resolved_path: Optional[Path] = None
        display_segments: Optional[List[Tuple[str, int, int]]] = None

        target = ", ".join(
            f"{name}={value}"
            for name, value in (
                ("function", function),
                ("struct", struct),
                ("var", var),
                ("function_macro", function_macro),
                ("macro_definition", macro_definition),
                ("marker", marker),
                ("message", message),
                ("enum", enum),
                ("service", service),
                ("lines", lines),
            )
            if value
        )

        def fail(message: str) -> str:
            # Record the failure so callers can find it structurally, then
            # degrade it into the document so the render still completes and
            # shows the problem where it happened. file_path is read at call
            # time, so it reflects any code_root prefix applied below.
            self._errors.append(CodeError(message, file_path, target or None))
            return f"{ERROR_PREFIX} {message}"

        try:
            context_lines = self._normalize_enclosure_context(
                self.default_enclosure_context if enclosure_context is None else enclosure_context
            )
            enclosure_mode = (enclosure or "").lower()
            if enclosure_mode and enclosure_mode != "auto":
                raise ValueError("enclosure must be 'auto' when specified")
            if enclosure_mode and not marker:
                raise ValueError("enclosure requires marker=")
            explicit_enclosure = bool(enclosure_mode)
            require_enclosure_context = explicit_enclosure or (
                context_lines > 0 and enclosure_context is not None
            )

            # Apply root prefix: per-call root= overrides context code_root
            code_root = root or str(self.env.globals.get("code_root", ""))
            if code_root and not Path(file_path).is_absolute():
                file_path = str(Path(code_root) / file_path)

            # Determine active ref (per-call overrides context)
            active_ref = ref or str(self.env.globals.get("code_ref", ""))

            # Resolve file path relative to repo
            resolved_path = Path(file_path)
            if not resolved_path.is_absolute():
                resolved_path = self.repo_path / resolved_path

            # If a git ref is active, fetch file content from that ref
            if active_ref:
                rel_path = file_path
                # Ensure relative path for git show
                try:
                    rel_path = str(Path(file_path).relative_to(self.repo_path))
                except ValueError:
                    # Already relative
                    rel_path = file_path
                content = subprocess.check_output(
                    ["git", "show", f"{active_ref}:{rel_path}"],
                    cwd=self.repo_path,
                    stderr=subprocess.DEVNULL,
                )
                tmp_file = Path(tempfile.mktemp(suffix=resolved_path.suffix))
                tmp_file.write_bytes(content)
                resolved_path = tmp_file

            # Get the appropriate extractor
            extractor = get_extractor(resolved_path)

            # Extract code based on parameters
            if function:
                # Check if we also have a marker - extract marker within function
                if marker:
                    if (context_lines or explicit_enclosure) and hasattr(extractor, "extract_function_marker_enclosed"):
                        enclosed = self._call_function_marker_method(
                            extractor.extract_function_marker_enclosed,
                            resolved_path,
                            function,
                            marker,
                            signature,
                        )
                        code_text, start_line, end_line = enclosed.to_tuple()
                        if context_lines:
                            display_segments = self._build_enclosure_segments(
                                resolved_path, enclosed, context_lines
                            )
                        logger.info(
                            f"Extracted marker '{marker}' with function enclosure "
                            f"'{function}' in {file_path}"
                        )
                    elif require_enclosure_context:
                        return fail("Function marker enclosure not supported for this file type")
                    elif hasattr(extractor, "extract_function_marker"):
                        code_text, start_line, end_line = self._call_function_marker_method(
                            extractor.extract_function_marker,
                            resolved_path,
                            function,
                            marker,
                            signature,
                        )
                        logger.info(f"Extracted marker '{marker}' from function '{function}' in {file_path}")
                    else:
                        return fail("Function marker extraction not supported for this file type")
                else:
                    code_text, start_line, end_line = extractor.extract_function(resolved_path, function, signature)
                    logger.info(f"Extracted function '{function}' from {file_path}")
            elif function_macro:
                # Handle function_macro parameter
                if isinstance(function_macro, str):
                    # Simple string -> convert to dict
                    macro_spec = {"name": function_macro}
                else:
                    macro_spec = function_macro

                # Check if we also have a marker - extract marker within macro
                if marker:
                    if (context_lines or explicit_enclosure) and hasattr(
                        extractor, "extract_function_macro_marker_enclosed"
                    ):
                        enclosed = extractor.extract_function_macro_marker_enclosed(
                            resolved_path, macro_spec, marker
                        )
                        code_text, start_line, end_line = enclosed.to_tuple()
                        if context_lines:
                            display_segments = self._build_enclosure_segments(
                                resolved_path, enclosed, context_lines
                            )
                        logger.info(
                            f"Extracted marker '{marker}' with function_macro enclosure "
                            f"'{macro_spec}' in {file_path}"
                        )
                    elif require_enclosure_context:
                        return fail("Function macro marker enclosure not supported for this file type")
                    elif hasattr(extractor, "extract_function_macro_marker"):
                        code_text, start_line, end_line = extractor.extract_function_macro_marker(
                            resolved_path, macro_spec, marker
                        )
                        logger.info(f"Extracted marker '{marker}' from function_macro '{macro_spec}' in {file_path}")
                    else:
                        return fail("Function macro marker extraction not supported for this file type")
                else:
                    code_text, start_line, end_line = extractor.extract_function_macro(resolved_path, macro_spec)
                    logger.info(f"Extracted function_macro '{macro_spec}' from {file_path}")
            elif macro_definition:
                code_text, start_line, end_line = extractor.extract_macro_definition(resolved_path, macro_definition)
                logger.info(f"Extracted macro_definition '{macro_definition}' from {file_path}")
            elif var:
                # Extract variable/constant declaration
                if hasattr(extractor, "extract_variable"):
                    code_text, start_line, end_line = extractor.extract_variable(resolved_path, var)
                    logger.info(f"Extracted variable '{var}' from {file_path}")
                elif hasattr(extractor, "extract_struct"):
                    # C/C++ uses extract_struct for var= (finds declarations)
                    if marker:
                        if (context_lines or explicit_enclosure) and hasattr(
                            extractor, "extract_struct_marker_enclosed"
                        ):
                            enclosed = extractor.extract_struct_marker_enclosed(
                                resolved_path, var, marker
                            )
                            code_text, start_line, end_line = enclosed.to_tuple()
                            if context_lines:
                                display_segments = self._build_enclosure_segments(
                                    resolved_path, enclosed, context_lines
                                )
                            logger.info(
                                f"Extracted marker '{marker}' with variable enclosure "
                                f"'{var}' in {file_path}"
                            )
                        elif require_enclosure_context:
                            return fail("Marker enclosure in variable not supported")
                        elif hasattr(extractor, "extract_struct_marker"):
                            code_text, start_line, end_line = extractor.extract_struct_marker(
                                resolved_path, var, marker
                            )
                            logger.info(f"Extracted marker '{marker}' from variable '{var}' in {file_path}")
                        else:
                            return fail("Marker extraction in variable not supported")
                    else:
                        code_text, start_line, end_line = extractor.extract_struct(resolved_path, var)
                        logger.info(f"Extracted variable '{var}' from {file_path}")
                else:
                    return fail("Variable extraction not supported for this file type")
            elif struct:
                # Extract struct/class/enum definition
                if hasattr(extractor, "extract_struct"):
                    if marker:
                        if (context_lines or explicit_enclosure) and hasattr(
                            extractor, "extract_struct_marker_enclosed"
                        ):
                            enclosed = extractor.extract_struct_marker_enclosed(
                                resolved_path, struct, marker
                            )
                            code_text, start_line, end_line = enclosed.to_tuple()
                            if context_lines:
                                display_segments = self._build_enclosure_segments(
                                    resolved_path, enclosed, context_lines
                                )
                            logger.info(
                                f"Extracted marker '{marker}' with struct enclosure "
                                f"'{struct}' in {file_path}"
                            )
                        elif require_enclosure_context:
                            return fail("Marker enclosure in struct not supported")
                        elif hasattr(extractor, "extract_struct_marker"):
                            code_text, start_line, end_line = extractor.extract_struct_marker(
                                resolved_path, struct, marker
                            )
                            logger.info(f"Extracted marker '{marker}' from struct '{struct}' in {file_path}")
                        else:
                            return fail("Marker extraction in struct not supported")
                    else:
                        code_text, start_line, end_line = extractor.extract_struct(resolved_path, struct)
                        logger.info(f"Extracted struct/class '{struct}' from {file_path}")
                else:
                    return fail("Struct/class extraction not supported for this file type")
            elif message:
                # Extract protobuf message
                if hasattr(extractor, "extract_message"):
                    if marker:
                        if (context_lines or explicit_enclosure) and hasattr(
                            extractor, "extract_message_marker_enclosed"
                        ):
                            enclosed = extractor.extract_message_marker_enclosed(
                                resolved_path, message, marker
                            )
                            code_text, start_line, end_line = enclosed.to_tuple()
                            if context_lines:
                                display_segments = self._build_enclosure_segments(
                                    resolved_path, enclosed, context_lines
                                )
                            logger.info(
                                f"Extracted marker '{marker}' with message enclosure "
                                f"'{message}' in {file_path}"
                            )
                        elif require_enclosure_context:
                            return fail("Message marker enclosure not supported for this file type")
                        else:
                            code_text, start_line, end_line = extractor.extract_message_marker(
                                resolved_path, message, marker
                            )
                            logger.info(f"Extracted marker '{marker}' from message '{message}' in {file_path}")
                    else:
                        code_text, start_line, end_line = extractor.extract_message(resolved_path, message)
                        logger.info(f"Extracted message '{message}' from {file_path}")
                else:
                    return fail("Message extraction not supported for this file type")
            elif enum:
                # Extract protobuf enum
                if hasattr(extractor, "extract_enum"):
                    code_text, start_line, end_line = extractor.extract_enum(resolved_path, enum)
                    logger.info(f"Extracted enum '{enum}' from {file_path}")
                else:
                    return fail("Enum extraction not supported for this file type")
            elif service:
                # Extract protobuf service
                if hasattr(extractor, "extract_service"):
                    code_text, start_line, end_line = extractor.extract_service(resolved_path, service)
                    logger.info(f"Extracted service '{service}' from {file_path}")
                else:
                    return fail("Service extraction not supported for this file type")
            elif marker:
                if (context_lines or explicit_enclosure) and hasattr(extractor, "extract_marker_enclosed"):
                    enclosed = extractor.extract_marker_enclosed(resolved_path, marker)
                    code_text, start_line, end_line = enclosed.to_tuple()
                    if context_lines:
                        display_segments = self._build_enclosure_segments(
                            resolved_path, enclosed, context_lines
                        )
                    logger.info(f"Extracted marker '{marker}' with auto enclosure in {file_path}")
                elif require_enclosure_context:
                    return fail("Auto marker enclosure not supported for this file type")
                else:
                    code_text, start_line, end_line = extractor.extract_marker(resolved_path, marker)
                    logger.info(f"Extracted marker '{marker}' from {file_path}")
            elif lines:
                start_line, end_line = lines
                code_text, start_line, end_line = extractor.extract_lines(resolved_path, start_line, end_line)
                logger.info(f"Extracted lines {start_line}-{end_line} from {file_path}")
            else:
                return fail(
                    "Must specify function, struct, var, function_macro, "
                    "macro_definition, lines, or marker"
                )

            # Use original file path for display (not temp file)
            display_path = self.repo_path / file_path if not Path(file_path).is_absolute() else Path(file_path)

            # Track this region as covered if we have a ChangesSet
            if self.changes_set is not None and not active_ref:
                # changes_set holds HEAD-relative line numbers (built from
                # 'git diff base..HEAD'), but start_line/end_line came from
                # the working tree. Translate before subtracting so uncommitted
                # edits above the extracted region don't shift the wrong rows.
                coverage_ranges = (
                    [(segment_start, segment_end) for _, segment_start, segment_end in display_segments]
                    if display_segments
                    else [(start_line, end_line)]
                )
                for coverage_start, coverage_end in coverage_ranges:
                    committed_start = self.github.map_to_committed_line(display_path, coverage_start)
                    committed_end = self.github.map_to_committed_line(display_path, coverage_end)
                    self.changes_set.subtract(display_path, committed_start, committed_end)

            # Remap line numbers if requested (for sharing docs from dirty files)
            display_start = start_line
            display_end = end_line
            if self.remap_dirty_lines and not active_ref:
                display_start = self.github.map_to_committed_line(display_path, start_line)
                display_end = self.github.map_to_committed_line(display_path, end_line)

            # Build header with GitHub permalink if requested
            if github and not active_ref:
                header = self.github.get_permalink(
                    display_path, start_line, end_line, display_committed_lines=self.remap_dirty_lines
                )
            else:
                header = None
                if github and active_ref:
                    # Ref-pinned extracts get a permalink at that ref — the
                    # content and line numbers come from the ref's tree.
                    header = self.github.get_permalink_at_ref(display_path, active_ref, start_line, end_line)
                if header is None:
                    display_rel = (
                        display_path.relative_to(self.repo_path) if display_path.is_absolute() else display_path
                    )
                    ref_suffix = f" @ {active_ref}" if active_ref else ""
                    if display_start == display_end:
                        header = f"📍 `{display_rel}:{display_start}{ref_suffix}`"
                    else:
                        header = f"📍 `{display_rel}:{display_start}-{display_end}{ref_suffix}`"

            # Format code with line numbers and/or blame
            # Use remapped line numbers for display if remap_dirty_lines is enabled
            code_start_line = display_start if self.remap_dirty_lines else start_line
            if display_segments:
                code_text = self._format_code_segments(
                    display_segments,
                    display_path,
                    line_numbers=line_numbers,
                    blame=blame and not active_ref,
                    remap_dirty_lines=self.remap_dirty_lines and not active_ref,
                )
            elif blame and not active_ref:
                code_text = self.github.format_with_blame(code_text, code_start_line, display_path)
            elif line_numbers:
                code_text = self._add_line_numbers(code_text, code_start_line)

            # Auto-detect language if not specified
            if not language:
                suffix = display_path.suffix.lower()
                language_map = {
                    ".cpp": "cpp",
                    ".cc": "cpp",
                    ".cxx": "cpp",
                    ".hpp": "cpp",
                    ".h": "cpp",
                    ".hxx": "cpp",
                    ".ipp": "cpp",  # Inline implementation files
                    ".macro": "cpp",  # C preprocessor macro files
                    ".c": "c",
                    ".py": "python",
                    ".js": "javascript",
                    ".mjs": "javascript",
                    ".cjs": "javascript",
                    ".ts": "typescript",
                    ".tsx": "tsx",
                    ".mts": "typescript",
                    ".cts": "typescript",
                    ".java": "java",
                    ".rs": "rust",
                    ".go": "go",
                    ".proto": "protobuf",
                }
                language = language_map.get(suffix, "text")

            # Build final output
            return f"{header}\n```{language}\n{code_text}\n```"

        except Exception as e:
            logger.error(f"Code extraction failed: {e}")
            # Collect file as fixture if collection is enabled
            if resolved_path is not None:
                _collect_error_fixture(resolved_path, str(e))
            return fail(str(e))

        finally:
            # Clean up temp file if we created one
            if tmp_file and tmp_file.exists():
                tmp_file.unlink()

    def _ignore_changes_function(
        self,
        file_path: str,
        function: str = None,
        struct: str = None,
        var: str = None,
        function_macro: Union[str, Dict] = None,
        macro_definition: str = None,
        lines: Tuple[int, int] = None,
        marker: str = None,
        signature: str = None,
        message: str = None,
        enum: str = None,
        service: str = None,
        ref: str = None,
    ) -> str:
        """
        Ignore specified regions from change validation.

        Uses same extraction specs as code() - or ignores whole file if no spec given.

        Examples:
            {{ ignore_changes('file.cmake') }}  # whole file
            {{ ignore_changes('file.cpp', function='helper') }}
            {{ ignore_changes('file.cpp', lines=(1, 100)) }}
        """
        if self.changes_set is None:
            return ""

        # Apply code_root prefix if set (via {% code_context %} block)
        code_root = str(self.env.globals.get("code_root", ""))
        if code_root and not Path(file_path).is_absolute():
            file_path = str(Path(code_root) / file_path)

        # Determine active ref (per-call overrides context)
        active_ref = ref or str(self.env.globals.get("code_ref", ""))

        resolved_path = Path(file_path)
        if not resolved_path.is_absolute():
            resolved_path = self.repo_path / resolved_path

        # If no extraction spec, ignore entire file
        has_spec = any(
            [function, struct, var, function_macro, macro_definition, lines, marker, message, enum, service]
        )
        if not has_spec:
            # Ignore all lines (use a large range)
            self.changes_set.subtract(resolved_path, 1, 999999)
            logger.info(f"Ignoring all changes in: {file_path}")
            return ""

        # Use extractors to find the region, same as code()
        tmp_file = None
        try:
            # If a git ref is active, fetch file content from that ref
            extract_path = resolved_path
            if active_ref:
                rel_path = file_path
                try:
                    rel_path = str(Path(file_path).relative_to(self.repo_path))
                except ValueError:
                    rel_path = file_path
                content = subprocess.check_output(
                    ["git", "show", f"{active_ref}:{rel_path}"],
                    cwd=self.repo_path,
                    stderr=subprocess.DEVNULL,
                )
                tmp_file = Path(tempfile.mktemp(suffix=resolved_path.suffix))
                tmp_file.write_bytes(content)
                extract_path = tmp_file

            extractor = get_extractor(extract_path)

            if function:
                _, start_line, end_line = extractor.extract_function(extract_path, function, signature)
            elif function_macro:
                macro_spec = {"name": function_macro} if isinstance(function_macro, str) else function_macro
                _, start_line, end_line = extractor.extract_function_macro(extract_path, macro_spec)
            elif macro_definition:
                _, start_line, end_line = extractor.extract_macro_definition(extract_path, macro_definition)
            elif var:
                if hasattr(extractor, "extract_variable"):
                    _, start_line, end_line = extractor.extract_variable(extract_path, var)
                else:
                    _, start_line, end_line = extractor.extract_struct(extract_path, var)
            elif struct:
                _, start_line, end_line = extractor.extract_struct(extract_path, struct)
            elif message:
                _, start_line, end_line = extractor.extract_message(extract_path, message)
            elif enum:
                _, start_line, end_line = extractor.extract_enum(extract_path, enum)
            elif service:
                _, start_line, end_line = extractor.extract_service(extract_path, service)
            elif marker:
                _, start_line, end_line = extractor.extract_marker(extract_path, marker)
            elif lines:
                start_line, end_line = lines

            self.changes_set.subtract(resolved_path, start_line, end_line)
            logger.info(f"Ignoring changes: {file_path}:{start_line}-{end_line}")

        except Exception as e:
            logger.warning(f"Failed to extract region for ignore_changes: {e}")

        finally:
            if tmp_file and tmp_file.exists():
                tmp_file.unlink()

        return ""

    @pass_context
    def _include_function(self, context, path: str) -> str:
        """
        Include a file into the template output.

        .j2 files are rendered as Jinja2 templates (with access to code() etc).
        All other files are included as raw text.

        Args:
            path: Path relative to the template directory

        Returns:
            File contents (rendered if .j2)

        Examples:
            {{ include('background.md') }}
            {{ include('details.md.j2') }}
            {{ include('sections/intro.md') }}
        """
        return self._load_include(path, context)

    @pass_context
    def _include_body_function(self, context, path: str) -> str:
        """
        Include a file as embeddable body content.

        Uses the same rendering rules as include(), then strips leading YAML
        frontmatter and projected-source's generated metadata header.

        Examples:
            {{ include_body('walkthrough.md.j2') }}
            {{ include_body('rendered-doc.md') }}
        """
        return self._strip_embedded_doc_wrappers(self._load_include(path, context))

    def _load_include(self, path: str, context=None) -> str:
        """Load include content, rendering .j2 files through this renderer."""
        if path.endswith(".j2"):
            template = self.env.get_template(path)
            return template.render(context.get_all() if context is not None else {})

        full_path = self.template_dir / path
        return full_path.read_text()

    def _strip_embedded_doc_wrappers(self, text: str) -> str:
        """Strip leading wrappers that are valid for standalone docs, not embeds."""
        stripped_frontmatter = False
        stripped_header = False

        while True:
            frontmatter = None if stripped_frontmatter else FRONTMATTER_RE.match(text)
            if frontmatter:
                text = text[frontmatter.end() :].lstrip("\r\n")
                stripped_frontmatter = True
                continue

            header = None if stripped_header else PROJECTED_SOURCE_HEADER_RE.match(text)
            if header:
                text = text[header.end() :].lstrip("\r\n")
                stripped_header = True
                continue

            return text

    def _set_code_context_function(self, root: str = None, ref: str = None) -> str:
        """
        Set code_root and/or code_ref globally for all subsequent code() calls.

        Unlike {% code_context %} blocks, this does not scope — it persists
        until changed. Use '' to clear.

        Examples:
            {{ set_code_context(root='src/rippled/app') }}
            {{ set_code_context(ref='v1.0') }}
            {{ set_code_context(root='src', ref='main') }}
            {{ set_code_context(root='', ref='') }}
        """
        if root is not None:
            self.env.globals["code_root"] = root
        if ref is not None:
            self.env.globals["code_ref"] = ref
        return ""

    def _set_code_root_function(self, path: str) -> str:
        """
        Set the code_root globally for all subsequent code() calls.

        Alias for set_code_context(root=path). Kept for backward compatibility.

        Examples:
            {{ set_code_root('src/rippled/app') }}
            {{ code('Handler.cpp', function='process') }}
            {{ set_code_root('') }}
        """
        self.env.globals["code_root"] = path
        return ""

    def _find_custom_tags_file(self, start_path: Path) -> Optional[Path]:
        """
        Find .projected-source.py file by walking up from start_path.
        Stops at git root to avoid escaping the repository.

        Args:
            start_path: Path to start searching from (usually template dir)

        Returns:
            Path to .projected-source.py if found, None otherwise
        """
        current = start_path.resolve()

        # Use repo_path as the boundary (it's already the git root)
        git_root = self.repo_path

        while current >= git_root:
            custom_file = current / ".projected-source.py"
            if custom_file.exists():
                logger.info(f"Found custom tags file at {custom_file}")
                return custom_file

            # Move up one directory
            parent = current.parent
            if parent == current:  # Reached filesystem root
                break
            current = parent

        return None

    def _load_custom_tags(self, template_path: Path) -> None:
        """
        Load and execute custom tags from .projected-source.py if found.

        Args:
            template_path: Path to the template being rendered
        """
        # Start searching from template's directory
        start_dir = template_path.parent if template_path.is_file() else template_path

        custom_file = self._find_custom_tags_file(start_dir)
        if not custom_file:
            return

        try:
            # Import the module dynamically
            import importlib.util

            spec = importlib.util.spec_from_file_location("custom_tags", custom_file)
            if not spec or not spec.loader:
                logger.warning(f"Could not load {custom_file}")
                return

            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            # Look for setup_custom_tags function
            if hasattr(module, "setup_custom_tags"):
                module.setup_custom_tags(self.env, self)
                logger.info(f"Loaded custom tags from {custom_file}")
            else:
                logger.warning(f"{custom_file} missing setup_custom_tags function")

        except Exception as e:
            logger.error(f"Error loading custom tags from {custom_file}: {e}")
            # Don't crash - just continue without custom tags

    def _normalize_enclosure_context(self, value) -> int:
        """Validate and normalize enclosure_context."""
        if value is None:
            return 0
        try:
            context_lines = int(value)
        except (TypeError, ValueError) as e:
            raise ValueError("enclosure_context must be an integer") from e
        if context_lines < 0:
            raise ValueError("enclosure_context must be >= 0")
        return context_lines

    def _call_function_marker_method(self, method, file_path: Path, function: str, marker: str, signature: str = None):
        """Call a function-marker extractor, passing signature only when supported."""
        if "signature" in inspect_signature(method).parameters:
            return method(file_path, function, marker, signature)
        if signature is not None:
            raise ValueError("signature= is not supported for marker extraction in this file type")
        return method(file_path, function, marker)

    def _build_enclosure_segments(self, file_path: Path, enclosed, context_lines: int) -> List[Tuple[str, int, int]]:
        """Build displayed source segments for an enclosed marker extraction."""
        ranges = self._build_enclosure_ranges(
            enclosed.enclosure_start_line,
            enclosed.enclosure_end_line,
            enclosed.marker_start_line,
            enclosed.marker_end_line,
            context_lines,
        )
        lines = file_path.read_text().splitlines()
        segments: List[Tuple[str, int, int]] = []
        for start, end in ranges:
            if start > end:
                continue
            segment_lines: List[str] = []
            segment_start: Optional[int] = None
            for line_num in range(start, end + 1):
                line = lines[line_num - 1]
                if MARKER_DIRECTIVE_RE.match(line):
                    if segment_lines and segment_start is not None:
                        segments.append(("\n".join(segment_lines), segment_start, line_num - 1))
                    segment_lines = []
                    segment_start = None
                    continue
                if segment_start is None:
                    segment_start = line_num
                segment_lines.append(line)
            if segment_lines and segment_start is not None:
                segments.append(("\n".join(segment_lines), segment_start, end))
        return segments

    def _build_enclosure_ranges(
        self,
        enclosure_start: int,
        enclosure_end: int,
        marker_start: int,
        marker_end: int,
        context_lines: int,
    ) -> List[Tuple[int, int]]:
        """Return merged line ranges for enclosure head, marker, and enclosure tail."""
        ranges: List[Tuple[int, int]] = []

        head_end = min(enclosure_start + context_lines - 1, marker_start - 2, enclosure_end)
        if enclosure_start <= head_end:
            ranges.append((enclosure_start, head_end))

        if marker_start <= marker_end:
            ranges.append((marker_start, marker_end))

        tail_start = max(enclosure_end - context_lines + 1, marker_end + 2, enclosure_start)
        if tail_start <= enclosure_end:
            ranges.append((tail_start, enclosure_end))

        return self._merge_line_ranges(ranges)

    def _merge_line_ranges(self, ranges: List[Tuple[int, int]]) -> List[Tuple[int, int]]:
        """Merge overlapping or adjacent line ranges."""
        merged: List[Tuple[int, int]] = []
        for start, end in sorted(ranges):
            if not merged or start > merged[-1][1] + 1:
                merged.append((start, end))
            else:
                prev_start, prev_end = merged[-1]
                merged[-1] = (prev_start, max(prev_end, end))
        return merged

    def _format_code_segments(
        self,
        segments: List[Tuple[str, int, int]],
        display_path: Path,
        line_numbers: bool,
        blame: bool,
        remap_dirty_lines: bool,
    ) -> str:
        """Format non-contiguous code segments for a single markdown code block."""
        formatted: List[str] = []
        previous_end: Optional[int] = None

        for text, start_line, end_line in segments:
            if previous_end is not None and start_line > previous_end + 1:
                formatted.append("...")

            display_start = (
                self.github.map_to_committed_line(display_path, start_line)
                if remap_dirty_lines
                else start_line
            )

            if blame:
                formatted.append(self.github.format_with_blame(text, display_start, display_path))
            elif line_numbers:
                formatted.append(self._add_line_numbers(text, display_start))
            else:
                formatted.append(text)

            previous_end = end_line

        return "\n".join(part for part in formatted if part)

    def _add_line_numbers(self, code_text: str, start_line: int) -> str:
        """Add line numbers to code text."""
        lines = code_text.splitlines()
        numbered_lines = []

        for i, line in enumerate(lines):
            line_num = start_line + i
            numbered_lines.append(f"{line_num:4} {line}" if line else f"{line_num:4}")

        return "\n".join(numbered_lines)

    def render_result(self, template_name: str, **context) -> RenderResult:
        """
        Render a template, reporting the extractions that failed along the way.

        code() does not raise when an extraction fails — it degrades the failure
        into the document — so a template can render "successfully" and still be
        wrong. This is the full-fidelity entry point: it returns the text
        together with a structured CodeError per failure, including failures
        from included templates (include() renders through this same renderer).

        Prefer this over render_template() when you need to know whether the
        document is actually healthy. Do not scan the text for ERROR_PREFIX —
        a document quoting error-handling source would look broken.

        Args:
            template_name: Name of the template file
            **context: Additional context variables

        Returns:
            RenderResult with the rendered text and any failed extractions
        """
        self._errors = []
        try:
            # Load custom tags from .projected-source.py if available
            template_path = self.template_dir / template_name
            self._load_custom_tags(template_path)

            template = self.env.get_template(template_name)
            text = template.render(**context)
        except jinja2.TemplateNotFound:
            logger.error(f"Template not found: {template_name}")
            raise
        except Exception as e:
            logger.error(f"Template rendering failed: {e}")
            raise

        return RenderResult(text, list(self._errors))

    def render_template(self, template_name: str, **context) -> str:
        """
        Render a template with the given context.

        Convenience facade over render_result() for callers that only want the
        text. Failed extractions are still visible in the output, but if you
        need to detect them, use render_result().

        Args:
            template_name: Name of the template file
            **context: Additional context variables

        Returns:
            Rendered template as string
        """
        return self.render_result(template_name, **context).text

    def render_template_file(self, template_path: Path, output_path: Path = None, **context):
        """
        Render a template file and optionally save the output.

        Args:
            template_path: Path to the template file
            output_path: Optional path to save the output
            **context: Additional context variables

        Returns:
            Rendered template as string
        """
        # Get template name relative to template_dir
        if template_path.is_absolute():
            template_name = template_path.relative_to(self.template_dir)
        else:
            template_name = template_path

        rendered = self.render_template(str(template_name), **context)

        if output_path:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(rendered)
            logger.info(f"Rendered {template_name} -> {output_path}")

        return rendered
