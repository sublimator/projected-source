"""
Jinja2 template rendering with code extraction functions.
"""

import logging
from pathlib import Path
from typing import Dict, Optional, Tuple, Union

import jinja2

from .extractor import BaseExtractor
from .github import GitHubIntegration
from ..languages import get_extractor

logger = logging.getLogger(__name__)


class TemplateRenderer:
    """Render Jinja2 templates with code extraction functions."""
    
    def __init__(self, template_dir: Path = None, repo_path: Path = None):
        """
        Initialize the renderer.
        
        Args:
            template_dir: Directory containing templates (default: current dir)
            repo_path: Repository root path (default: current dir)
        """
        self.template_dir = template_dir or Path.cwd()
        self.repo_path = repo_path or Path.cwd()
        self.github = GitHubIntegration(self.repo_path)
        
        # Create Jinja2 environment
        self.env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(str(self.template_dir)),
            trim_blocks=True,
            lstrip_blocks=True
        )
        
        # Register custom functions
        self.env.globals['code'] = self._code_function
        self.env.globals['ghc'] = self._code_function  # Alias for compatibility
        
        # Load project-specific custom tags if available
        # (loaded on-demand when rendering templates)
    
    def _code_function(self,
                      file_path: str,
                      function: str = None,
                      struct: str = None,
                      function_macro: Union[str, Dict] = None,
                      macro_definition: str = None,
                      lines: Tuple[int, int] = None,
                      marker: str = None,
                      github: bool = True,
                      blame: bool = False,
                      line_numbers: bool = True,
                      language: str = None) -> str:
        """
        Universal code extraction function for templates.
        
        Args:
            file_path: Path to the source file
            function: Function name to extract
            struct: Struct/class name to extract (C/C++)
            function_macro: Macro that defines a function (dict with 'name' and optional 'arg0', 'arg1', etc)
            macro_definition: Macro definition name to extract (#define statement)
            lines: Tuple of (start_line, end_line) to extract
            marker: Marker name to extract between //@@start and //@@end
            github: Include GitHub permalink (default: True)
            blame: Include git blame info (default: False)
            line_numbers: Show line numbers (default: True)
            language: Language for syntax highlighting (auto-detected if None)
            
        Returns:
            Formatted markdown with code block
            
        Examples in templates:
            {{ code('src/file.cpp', function='myFunc') }}
            {{ code('src/file.cpp', lines=(10, 20)) }}
            {{ code('src/file.cpp', marker='example1') }}
            {{ code('src/file.cpp', lines=(10, 20), blame=True) }}
        """
        try:
            # Resolve file path relative to repo
            file_path = Path(file_path)
            if not file_path.is_absolute():
                file_path = self.repo_path / file_path
            
            # Get the appropriate extractor
            extractor = get_extractor(file_path)
            
            # Extract code based on parameters
            if function:
                code_text, start_line, end_line = extractor.extract_function(file_path, function)
                logger.info(f"Extracted function '{function}' from {file_path}")
            elif function_macro:
                # Handle function_macro parameter
                if isinstance(function_macro, str):
                    # Simple string -> convert to dict
                    macro_spec = {'name': function_macro}
                else:
                    macro_spec = function_macro
                
                # Check if we also have a marker - extract marker within macro
                if marker:
                    code_text, start_line, end_line = extractor.extract_function_macro_marker(file_path, macro_spec, marker)
                    logger.info(f"Extracted marker '{marker}' from function_macro '{macro_spec}' in {file_path}")
                else:
                    code_text, start_line, end_line = extractor.extract_function_macro(file_path, macro_spec)
                    logger.info(f"Extracted function_macro '{macro_spec}' from {file_path}")
            elif macro_definition:
                code_text, start_line, end_line = extractor.extract_macro_definition(file_path, macro_definition)
                logger.info(f"Extracted macro_definition '{macro_definition}' from {file_path}")
            elif struct:
                # Extract struct/class (for C/C++)
                if hasattr(extractor, 'extract_struct'):
                    code_text, start_line, end_line = extractor.extract_struct(file_path, struct)
                    logger.info(f"Extracted struct/class '{struct}' from {file_path}")
                else:
                    return f"❌ **ERROR**: Struct extraction not supported for this file type"
            elif marker:
                code_text, start_line, end_line = extractor.extract_marker(file_path, marker)
                logger.info(f"Extracted marker '{marker}' from {file_path}")
            elif lines:
                start_line, end_line = lines
                code_text, start_line, end_line = extractor.extract_lines(file_path, start_line, end_line)
                logger.info(f"Extracted lines {start_line}-{end_line} from {file_path}")
            else:
                return f"❌ **ERROR**: Must specify function, struct, function_macro, macro_definition, lines, or marker for {file_path}"
            
            # Build header with GitHub permalink if requested
            if github:
                header = self.github.get_permalink(file_path, start_line, end_line)
            else:
                rel_path = file_path.relative_to(self.repo_path) if file_path.is_absolute() else file_path
                if start_line == end_line:
                    header = f"📍 `{rel_path}:{start_line}`"
                else:
                    header = f"📍 `{rel_path}:{start_line}-{end_line}`"
            
            # Format code with line numbers and/or blame
            if blame:
                code_text = self.github.format_with_blame(code_text, start_line, file_path)
            elif line_numbers:
                code_text = self._add_line_numbers(code_text, start_line)
            
            # Auto-detect language if not specified
            if not language:
                suffix = file_path.suffix.lower()
                language_map = {
                    '.cpp': 'cpp', '.cc': 'cpp', '.cxx': 'cpp',
                    '.hpp': 'cpp', '.h': 'cpp', '.hxx': 'cpp',
                    '.c': 'c',
                    '.py': 'python',
                    '.js': 'javascript',
                    '.ts': 'typescript',
                    '.java': 'java',
                    '.rs': 'rust',
                    '.go': 'go',
                }
                language = language_map.get(suffix, 'text')
            
            # Build final output
            return f"{header}\n```{language}\n{code_text}\n```"
            
        except Exception as e:
            error_msg = f"❌ **ERROR**: {e}"
            logger.error(f"Code extraction failed: {e}")
            return error_msg
    
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
            custom_file = current / '.projected-source.py'
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
            if hasattr(module, 'setup_custom_tags'):
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
        
        return '\n'.join(numbered_lines)
    
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