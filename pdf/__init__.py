"""Generic PDF rendering pipeline: markdown → HTML → PDF via WeasyPrint.

Domain-specific behaviour (extra blockquote keywords, direction markers,
risk-cell colouring) is opt-in via YAML front-matter metadata. Callers
own their stylesheets; this package provides only the base style.
"""

from .render import (
    build_pdf,
    build_pdf_with_result,
    build_pdf_from_markdown,
    build_html,
    md_to_html,
    parse_front_matter,
    resolve_tables_include,
    get_style_path,
    check_font,
    DEFAULT_STYLE,
)
from .diagnostics import (
    BuildResult,
    DiagnosticsReport,
    StrictDiagnosticsError,
    StrictPolicy,
)
from .resources import ResourceAccessError, ResourceContext
from .postprocess import classify_marker_rows

__all__ = [
    'build_pdf',
    'build_pdf_with_result',
    'build_pdf_from_markdown',
    'build_html',
    'md_to_html',
    'parse_front_matter',
    'resolve_tables_include',
    'get_style_path',
    'check_font',
    'DEFAULT_STYLE',
    'BuildResult',
    'DiagnosticsReport',
    'StrictDiagnosticsError',
    'StrictPolicy',
    'ResourceAccessError',
    'ResourceContext',
    'classify_marker_rows',
]
