"""Generic PDF rendering pipeline: markdown → HTML → PDF via WeasyPrint.

Domain-specific behaviour (extra blockquote keywords, direction markers,
risk-cell colouring) is opt-in via YAML front-matter metadata. Callers
own their stylesheets; this package provides only the base style.
"""

from .render import (
    build_pdf,
    build_html,
    md_to_html,
    parse_front_matter,
    resolve_tables_include,
    get_style_path,
    check_font,
    DEFAULT_STYLE,
)
from .postprocess import classify_marker_rows

__all__ = [
    'build_pdf',
    'build_html',
    'md_to_html',
    'parse_front_matter',
    'resolve_tables_include',
    'get_style_path',
    'check_font',
    'DEFAULT_STYLE',
    'classify_marker_rows',
]
