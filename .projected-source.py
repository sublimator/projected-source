"""
Example custom tags for the projected-source project itself.

This file demonstrates how to define project-specific Jinja2 tags
that can be used in templates.
"""

from projected_source.custom import Environment


def setup_custom_tags(env: Environment, renderer):
    """
    Register custom tags for this project.
    
    Args:
        env: Jinja2 Environment to register tags with
        renderer: TemplateRenderer instance (has _code_function method)
    """
    
    # Example: Shortcut for extracting from applyHook.cpp
    # Note: arg1 is the function name (arg0 is return type)
    def accept_hook():
        """Extract the accept hook function."""
        return renderer._code_function(
            'examples/applyHook.cpp',
            function_macro={'name': 'DEFINE_JS_FUNCTION', 'arg1': 'accept'}
        )
    
    def state_hook():
        """Extract the state_set hook function."""
        return renderer._code_function(
            'examples/applyHook.cpp',
            function_macro={'name': 'DEFINE_JS_FUNCTION', 'arg1': 'state_set'}
        )
    
    def trace_hook():
        """Extract the trace hook function."""
        return renderer._code_function(
            'examples/applyHook.cpp',
            function_macro={'name': 'DEFINE_JS_FUNCTION', 'arg1': 'trace'}
        )
    
    # Parameterized tag
    def hook(name):
        """Extract any hook by name."""
        return renderer._code_function(
            'examples/applyHook.cpp',
            function_macro={'name': 'DEFINE_JS_FUNCTION', 'arg1': name}
        )
    
    # Extract all hooks at once
    def all_hooks():
        """Extract all main hook functions."""
        hooks = ['accept', 'rollback', 'state_set', 'trace']
        sections = []
        for hook_name in hooks:
            sections.append(renderer._code_function(
                'examples/applyHook.cpp',
                function_macro={'name': 'DEFINE_JS_FUNCTION', 'arg1': hook_name}
            ))
        return '\n\n'.join(sections)
    
    # Register all tags
    env.globals['accept_hook'] = accept_hook
    env.globals['state_hook'] = state_hook  
    env.globals['trace_hook'] = trace_hook
    env.globals['hook'] = hook
    env.globals['all_hooks'] = all_hooks
    
    # You can also register filters
    env.filters['uppercase'] = lambda x: x.upper()