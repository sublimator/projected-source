"""
Jinja2 template rendering with code extraction functions.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Dict, Optional, Tuple, Union

import jinja2

from ..languages import get_extractor
from .github import GitHubIntegration

if TYPE_CHECKING:
    from .changes_set import ChangesSet

logger = logging.getLogger(__name__)


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
        """
        self.template_dir = template_dir or Path.cwd()
        self.repo_path = repo_path or Path.cwd()
        self.remap_dirty_lines = remap_dirty_lines
        self.changes_set = changes_set
        self.github = GitHubIntegration(self.repo_path)

        # Create Jinja2 environment
        self.env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(str(self.template_dir)), trim_blocks=True, lstrip_blocks=True
        )

        # Register custom functions
        self.env.globals["code"] = self._code_function
        self.env.globals["ghc"] = self._code_function  # Alias for compatibility
        self.env.globals["ignore_changes"] = self._ignore_changes_function

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
        try:
            # Resolve file path relative to repo
            resolved_path = Path(file_path)
            if not resolved_path.is_absolute():
                resolved_path = self.repo_path / resolved_path

            # Get the appropriate extractor
            extractor = get_extractor(resolved_path)

            # Extract code based on parameters
            if function:
                # Check if we also have a marker - extract marker within function
                if marker:
                    if hasattr(extractor, "extract_function_marker"):
                        code_text, start_line, end_line = extractor.extract_function_marker(
                            resolved_path, function, marker
                        )
                        logger.info(f"Extracted marker '{marker}' from function '{function}' in {file_path}")
                    else:
                        return "❌ **ERROR**: Function marker extraction not supported for this file type"
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
                    code_text, start_line, end_line = extractor.extract_function_macro_marker(
                        resolved_path, macro_spec, marker
                    )
                    logger.info(f"Extracted marker '{marker}' from function_macro '{macro_spec}' in {file_path}")
                else:
                    code_text, start_line, end_line = extractor.extract_function_macro(resolved_path, macro_spec)
                    logger.info(f"Extracted function_macro '{macro_spec}' from {file_path}")
            elif macro_definition:
                code_text, start_line, end_line = extractor.extract_macro_definition(resolved_path, macro_definition)
                logger.info(f"Extracted macro_definition '{macro_definition}' from {file_path}")
            elif struct or var:
                # Extract struct/class/enum/variable (for C/C++)
                name = struct or var
                kind = "struct/class/enum" if struct else "variable"
                if hasattr(extractor, "extract_struct"):
                    if marker:
                        # Extract marker within struct/var
                        if hasattr(extractor, "extract_struct_marker"):
                            code_text, start_line, end_line = extractor.extract_struct_marker(
                                resolved_path, name, marker
                            )
                            logger.info(f"Extracted marker '{marker}' from {kind} '{name}' in {file_path}")
                        else:
                            return f"❌ **ERROR**: Marker extraction in {kind} not supported"
                    else:
                        code_text, start_line, end_line = extractor.extract_struct(resolved_path, name)
                        logger.info(f"Extracted {kind} '{name}' from {file_path}")
                else:
                    return f"❌ **ERROR**: {kind.capitalize()} extraction not supported for this file type"
            elif message:
                # Extract protobuf message
                if hasattr(extractor, "extract_message"):
                    if marker:
                        code_text, start_line, end_line = extractor.extract_message_marker(
                            resolved_path, message, marker
                        )
                        logger.info(f"Extracted marker '{marker}' from message '{message}' in {file_path}")
                    else:
                        code_text, start_line, end_line = extractor.extract_message(resolved_path, message)
                        logger.info(f"Extracted message '{message}' from {file_path}")
                else:
                    return "❌ **ERROR**: Message extraction not supported for this file type"
            elif enum:
                # Extract protobuf enum
                if hasattr(extractor, "extract_enum"):
                    code_text, start_line, end_line = extractor.extract_enum(resolved_path, enum)
                    logger.info(f"Extracted enum '{enum}' from {file_path}")
                else:
                    return "❌ **ERROR**: Enum extraction not supported for this file type"
            elif service:
                # Extract protobuf service
                if hasattr(extractor, "extract_service"):
                    code_text, start_line, end_line = extractor.extract_service(resolved_path, service)
                    logger.info(f"Extracted service '{service}' from {file_path}")
                else:
                    return "❌ **ERROR**: Service extraction not supported for this file type"
            elif marker:
                code_text, start_line, end_line = extractor.extract_marker(resolved_path, marker)
                logger.info(f"Extracted marker '{marker}' from {file_path}")
            elif lines:
                start_line, end_line = lines
                code_text, start_line, end_line = extractor.extract_lines(resolved_path, start_line, end_line)
                logger.info(f"Extracted lines {start_line}-{end_line} from {file_path}")
            else:
                return (
                    f"❌ **ERROR**: Must specify function, struct, var, function_macro, "
                    f"macro_definition, lines, or marker for {file_path}"
                )

            # Track this region as covered if we have a ChangesSet
            if self.changes_set is not None:
                self.changes_set.subtract(resolved_path, start_line, end_line)

            # Remap line numbers if requested (for sharing docs from dirty files)
            display_start = start_line
            display_end = end_line
            if self.remap_dirty_lines:
                display_start = self.github.map_to_committed_line(resolved_path, start_line)
                display_end = self.github.map_to_committed_line(resolved_path, end_line)

            # Build header with GitHub permalink if requested
            if github:
                header = self.github.get_permalink(
                    resolved_path, start_line, end_line, display_committed_lines=self.remap_dirty_lines
                )
            else:
                rel_path = resolved_path.relative_to(self.repo_path) if resolved_path.is_absolute() else resolved_path
                if display_start == display_end:
                    header = f"📍 `{rel_path}:{display_start}`"
                else:
                    header = f"📍 `{rel_path}:{display_start}-{display_end}`"

            # Format code with line numbers and/or blame
            # Use remapped line numbers for display if remap_dirty_lines is enabled
            code_start_line = display_start if self.remap_dirty_lines else start_line
            if blame:
                code_text = self.github.format_with_blame(code_text, code_start_line, resolved_path)
            elif line_numbers:
                code_text = self._add_line_numbers(code_text, code_start_line)

            # Auto-detect language if not specified
            if not language:
                suffix = resolved_path.suffix.lower()
                language_map = {
                    ".cpp": "cpp",
                    ".cc": "cpp",
                    ".cxx": "cpp",
                    ".hpp": "cpp",
                    ".h": "cpp",
                    ".hxx": "cpp",
                    ".ipp": "cpp",  # Inline implementation files
                    ".c": "c",
                    ".py": "python",
                    ".js": "javascript",
                    ".ts": "typescript",
                    ".java": "java",
                    ".rs": "rust",
                    ".go": "go",
                    ".proto": "protobuf",
                }
                language = language_map.get(suffix, "text")

            # Build final output
            return f"{header}\n```{language}\n{code_text}\n```"

        except Exception as e:
            error_msg = f"❌ **ERROR**: {e}"
            logger.error(f"Code extraction failed: {e}")
            # Collect file as fixture if collection is enabled
            _collect_error_fixture(resolved_path, str(e))
            return error_msg

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

        resolved_path = Path(file_path)
        if not resolved_path.is_absolute():
            resolved_path = self.repo_path / resolved_path

        # If no extraction spec, ignore entire file
        has_spec = any([function, struct, var, function_macro, macro_definition, lines, marker])
        if not has_spec:
            # Ignore all lines (use a large range)
            self.changes_set.subtract(resolved_path, 1, 999999)
            logger.info(f"Ignoring all changes in: {file_path}")
            return ""

        # Use extractors to find the region, same as code()
        try:
            extractor = get_extractor(resolved_path)

            if function:
                _, start_line, end_line = extractor.extract_function(resolved_path, function)
            elif function_macro:
                macro_spec = {"name": function_macro} if isinstance(function_macro, str) else function_macro
                _, start_line, end_line = extractor.extract_function_macro(resolved_path, macro_spec)
            elif macro_definition:
                _, start_line, end_line = extractor.extract_macro_definition(resolved_path, macro_definition)
            elif struct or var:
                name = struct or var
                _, start_line, end_line = extractor.extract_struct(resolved_path, name)
            elif marker:
                _, start_line, end_line = extractor.extract_marker(resolved_path, marker)
            elif lines:
                start_line, end_line = lines

            self.changes_set.subtract(resolved_path, start_line, end_line)
            logger.info(f"Ignoring changes: {file_path}:{start_line}-{end_line}")

        except Exception as e:
            logger.warning(f"Failed to extract region for ignore_changes: {e}")

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

    def _add_line_numbers(self, code_text: str, start_line: int) -> str:
        """Add line numbers to code text."""
        lines = code_text.splitlines()
        numbered_lines = []

        for i, line in enumerate(lines):
            line_num = start_line + i
            numbered_lines.append(f"{line_num:4} {line}")

        return "\n".join(numbered_lines)

    def render_template(self, template_name: str, **context) -> str:
        """
        Render a template with the given context.

        Args:
            template_name: Name of the template file
            **context: Additional context variables

        Returns:
            Rendered template as string
        """
        try:
            # Load custom tags from .projected-source.py if available
            template_path = self.template_dir / template_name
            self._load_custom_tags(template_path)

            template = self.env.get_template(template_name)
            return template.render(**context)
        except jinja2.TemplateNotFound:
            logger.error(f"Template not found: {template_name}")
            raise
        except Exception as e:
            logger.error(f"Template rendering failed: {e}")
            raise

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
