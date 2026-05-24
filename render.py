"""
Markdown to PDF converter.

Converts markdown files to professional PDFs using WeasyPrint. All visual
styling lives in CSS files under pdf/styles/.

Pipeline:
    1. Parse YAML front matter (title, subtitle, table layouts)
    2. Apply typography (ASCII -> Unicode via typography.py)
    3. Convert markdown -> HTML (via python-markdown)
    4. Post-process HTML (via postprocess.py)
    5. Render HTML + CSS -> PDF (via WeasyPrint)

Usage (CLI):
    python -m pdf input.md                    # -> input.pdf
    python -m pdf input.md output.pdf         # explicit output
    python -m pdf *.md                        # batch convert
    python -m pdf input.md --output-dir out/  # output to directory
    python -m pdf input.md --style custom.css # different stylesheet

Usage (API):
    from pdf.render import build_pdf
    build_pdf('report.md', style_path='path/to/overlay.css',
              base_style_path='style.css')

Requires: weasyprint, markdown, pyyaml
"""
from __future__ import annotations

import logging
import os
import re
import sys
import argparse

import yaml
import markdown

from .typography import typographic_convert
from .postprocess import postprocess, generate_toc

log = logging.getLogger(__name__)


# =============================================================================
# PATHS
# =============================================================================

_STYLES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'styles')
DEFAULT_STYLE = os.path.join(_STYLES_DIR, 'style.css')


def get_style_path(name: str) -> str:
    """Resolve a style name or path to a full CSS path.

    If ``name`` is already an absolute path or exists relative to cwd, return
    it as-is. Otherwise look inside pdf/styles/.
    """
    if os.path.isabs(name) or os.path.exists(name):
        return name
    candidate = os.path.join(_STYLES_DIR, name)
    if os.path.exists(candidate):
        return candidate
    return name  # fall through — let caller handle missing file


# =============================================================================
# FONT CHECK
# =============================================================================

def check_font() -> bool:
    """Backwards-compat shim. AntSerif is now loaded from bundled TTFs via
    @font-face in pdf/styles/style.css, so no system install is required.
    Kept as a no-op so any existing callers (and the public API) don't
    break.
    """
    return True


# =============================================================================
# FRONT MATTER
# =============================================================================

# Front matter schema: field name -> expected type (or tuple of types)
_FRONT_MATTER_SCHEMA = {
    'title': str,
    'subtitle': str,
    'tables': dict,
    'tracked_teams': list,
    'direction_markers': bool,
    'risk_tables': list,
    'extra_callout_keywords': dict,
    'auto_align_columns': bool,
    'auto_highlight_bold_rows': bool,
    'toc': bool,
    'toc_depth': int,
    'h2_page_break': bool,
    'theme': str,
}


def validate_front_matter(metadata: dict) -> list[str]:
    """Warn about unknown or mistyped front matter keys.

    Returns list of warning strings (empty if all valid).
    """
    warnings = []
    for key, value in metadata.items():
        if key not in _FRONT_MATTER_SCHEMA:
            warnings.append(f"unknown front matter key: '{key}'")
        else:
            expected = _FRONT_MATTER_SCHEMA[key]
            if not isinstance(value, expected):
                warnings.append(
                    f"front matter '{key}': expected {expected.__name__}, "
                    f"got {type(value).__name__}"
                )
    return warnings


def parse_front_matter(content: str) -> tuple[dict, str]:
    """Extract YAML front matter and return (metadata, remaining_content).

    Front matter is delimited by --- lines at the start of the file.
    Warns on stderr about unknown or mistyped keys.

    ::

        ---
        title: Document Title
        subtitle: Optional subtitle
        tables:
          my_table:
            columns:
              - {name: Time, width: 14, align: center}
        ---
        # Markdown content starts here
    """
    if content.startswith("---"):
        end = content.find("---", 3)
        if end != -1:
            meta = yaml.safe_load(content[3:end].strip()) or {}
            for warning in validate_front_matter(meta):
                log.warning("%s", warning)
            return meta, content[end + 3:].strip()
    return {}, content


# =============================================================================
# CONVERSION
# =============================================================================

def md_to_html(md_content: str, metadata: dict) -> str:
    """Convert markdown string to a complete HTML document.

    Table layouts declared in metadata['tables'] are applied during
    post-processing. Direction markers ({up}/{down}/{mod}) in bold cells
    are also handled during post-processing.
    """
    md_content = typographic_convert(md_content)

    # Ensure blank line before list markers — python-markdown requires it
    # but generated markdown often omits it.
    md_content = re.sub(r'([^\n])\n([-*+] |\d+\. )', r'\1\n\n\2', md_content)

    html_body = markdown.markdown(
        md_content,
        extensions=[
            "tables", "fenced_code", "smarty",
            "sane_lists", "def_list", "footnotes",
            "attr_list", "abbr", "md_in_html",
        ],
        output_format="html5",
    )

    html_body = postprocess(html_body, metadata=metadata)

    # Table of contents (opt-in via front matter)
    toc_html = ""
    if metadata.get("toc"):
        toc_depth = metadata.get("toc_depth", 3)
        toc_html, html_body = generate_toc(html_body, max_depth=toc_depth)
        toc_html += "\n"

    # Title block from YAML front matter
    title_html = ""
    if metadata.get("title"):
        title_html += (
            '<h1>'
            f'{typographic_convert(metadata["title"])}'
            '</h1>\n'
        )
    if metadata.get("subtitle"):
        title_html += (
            '<p class="doc-subtitle">'
            f'{typographic_convert(metadata["subtitle"])}'
            '</p>\n'
        )

    title_text = metadata.get("title", "Document")

    return (
        '<!DOCTYPE html>\n'
        '<html lang="en">\n'
        '<head>\n'
        '    <meta charset="utf-8">\n'
        f'    <title>{title_text}</title>\n'
        '</head>\n'
        '<body>\n'
        f'{title_html}'
        f'{toc_html}'
        '<div class="content">\n'
        f'{html_body}\n'
        '</div>\n'
        '</body>\n'
        '</html>'
    )


def _front_matter_css(metadata):
    """Generate additional CSS rules from front matter flags."""
    rules = []
    if metadata.get('h2_page_break'):
        rules.append('h2 { break-before: page; margin-top: 0; }')
        # h2 immediately after h1 stays together (cover page pattern)
        rules.append('h1 + h2 { break-before: auto; }')
    return '\n'.join(rules)


def build_pdf(md_path: str, output_path: str | None = None, style_path: str | None = None, base_style_path: str | None = None) -> str:
    """Convert a markdown file to PDF.

    Args:
        md_path: Path to input markdown file.
        output_path: Path for output PDF. Defaults to input with .pdf extension.
        style_path: Path to CSS stylesheet. Defaults to style.css in styles dir.
        base_style_path: Path to base CSS to load before style_path.
    """
    from weasyprint import HTML, CSS

    if style_path is None:
        style_path = DEFAULT_STYLE

    if output_path is None:
        output_path = os.path.splitext(md_path)[0] + ".pdf"

    # Read markdown and parse front matter
    with open(md_path, "r", encoding="utf-8") as f:
        content = f.read()

    metadata, body = parse_front_matter(content)

    # Read CSS (base + overlay + theme + front-matter-driven rules)
    css_parts = []
    if base_style_path:
        with open(base_style_path, "r", encoding="utf-8") as f:
            css_parts.append(f.read())
    with open(style_path, "r", encoding="utf-8") as f:
        css_parts.append(f.read())

    # Theme overlay from front matter (e.g. theme: compact)
    theme = metadata.get('theme')
    if theme:
        if not isinstance(theme, str) or '/' in theme or '\\' in theme or '..' in theme:
            log.warning("invalid theme name: %r", theme)
            theme = None
    if theme:
        theme_path = get_style_path(f'{theme}.css')
        if os.path.exists(theme_path):
            with open(theme_path, "r", encoding="utf-8") as f:
                css_parts.append(f.read())
        else:
            log.warning("theme '%s' not found (%s)", theme, theme_path)

    # Front-matter-driven CSS injections
    fm_css = _front_matter_css(metadata)
    if fm_css:
        css_parts.append(fm_css)

    css_content = "\n\n".join(css_parts)

    # Convert and render
    html = md_to_html(body, metadata)

    # Render PDF. base_url on the CSS lets relative URLs in the
    # stylesheet (e.g. @font-face src: url("../fonts/...")) resolve
    # against the styles directory, which is where the bundled CSS
    # and the @font-face declarations live.
    HTML(string=html).write_pdf(
        output_path,
        stylesheets=[CSS(string=css_content, base_url=_STYLES_DIR + "/")],
    )

    print(f"Created: {output_path}")
    return output_path


def build_html(md_path: str, output_path: str | None = None,
               style_path: str | None = None,
               base_style_path: str | None = None) -> str:
    """Convert a markdown file to a self-contained HTML file.

    Same pipeline as build_pdf but stops before the WeasyPrint step,
    inlining the CSS into a <style> tag.

    Args:
        md_path: Path to input markdown file.
        output_path: Path for output HTML. Defaults to input with .html extension.
        style_path: Path to CSS stylesheet. Defaults to style.css in styles dir.
        base_style_path: Path to base CSS to load before style_path.
    """
    if style_path is None:
        style_path = DEFAULT_STYLE

    if output_path is None:
        output_path = os.path.splitext(md_path)[0] + ".html"

    with open(md_path, "r", encoding="utf-8") as f:
        content = f.read()

    metadata, body = parse_front_matter(content)

    # Read CSS
    css_parts = []
    if base_style_path:
        with open(base_style_path, "r", encoding="utf-8") as f:
            css_parts.append(f.read())
    with open(style_path, "r", encoding="utf-8") as f:
        css_parts.append(f.read())

    theme = metadata.get('theme')
    if theme:
        if not isinstance(theme, str) or '/' in theme or '\\' in theme or '..' in theme:
            log.warning("invalid theme name: %r", theme)
            theme = None
    if theme:
        theme_path = get_style_path(f'{theme}.css')
        if os.path.exists(theme_path):
            with open(theme_path, "r", encoding="utf-8") as f:
                css_parts.append(f.read())
        else:
            log.warning("theme '%s' not found (%s)", theme, theme_path)

    fm_css = _front_matter_css(metadata)
    if fm_css:
        css_parts.append(fm_css)

    css_content = "\n\n".join(css_parts)

    html = md_to_html(body, metadata)

    # Inject CSS into <head>
    style_tag = f'<style>\n{css_content}\n</style>'
    html = html.replace('</head>', f'{style_tag}\n</head>', 1)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"Created: {output_path}")
    return output_path


# =============================================================================
# CLI
# =============================================================================

def main():
    """CLI entry point with batch mode, --output-dir, --style, --base-style, --html."""
    parser = argparse.ArgumentParser(
        description="Convert markdown files to PDF (or HTML) using WeasyPrint."
    )
    parser.add_argument(
        "files", nargs="+",
        help="Markdown files to convert (or file.md output.pdf for explicit output)"
    )
    parser.add_argument(
        "--output-dir", "-o", default=None,
        help="Directory for output files (default: same as input file)"
    )
    parser.add_argument(
        "--html", action="store_true",
        help="Output styled HTML instead of PDF"
    )
    parser.add_argument(
        "--style", "-s", default=None,
        help=f"CSS stylesheet (default: {os.path.basename(DEFAULT_STYLE)})"
    )
    parser.add_argument(
        "--base-style", "-b", default=None,
        help="Base CSS stylesheet loaded before --style"
    )

    args = parser.parse_args()

    style_path = get_style_path(args.style) if args.style else None
    base_style_path = get_style_path(args.base_style) if args.base_style else None

    build_fn = build_html if args.html else build_pdf
    ext = ".html" if args.html else ".pdf"

    # Handle explicit output: pdf input.md output.pdf
    if len(args.files) == 2 and args.files[1].endswith(ext):
        build_fn(args.files[0], args.files[1],
                 style_path=style_path, base_style_path=base_style_path)
        return

    # Batch: convert all .md files
    md_files = [f for f in args.files if f.endswith(".md")]
    if not md_files:
        md_files = [args.files[0]]

    for md_file in md_files:
        if args.output_dir:
            os.makedirs(args.output_dir, exist_ok=True)
            basename = os.path.splitext(os.path.basename(md_file))[0] + ext
            out_path = os.path.join(args.output_dir, basename)
        else:
            out_path = None  # defaults to same dir as input

        build_fn(md_file, out_path,
                 style_path=style_path, base_style_path=base_style_path)


if __name__ == "__main__":
    main()
