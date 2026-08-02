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

import html as _html
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
    'author': str,
    'subject': str,
    'keywords': (str, list),
    'lang': str,
    'tables': dict,
    'tables_include': str,
    'tracked_rows': list,
    'tracked_teams': list,   # deprecated alias for tracked_rows
    'direction_markers': bool,
    'risk_tables': list,
    'extra_callout_keywords': dict,
    'auto_align_columns': bool,
    'auto_highlight_bold_rows': bool,
    'table_widths': (bool, str),      # false/'off' disables the typed-width pass
    'columns': dict,                  # Header -> type name or explicit width
    'orientation': str,               # 'landscape' for wide tables
    'page_width_em': (int, float),    # override the table-fit content width
    'toc': bool,
    'toc_depth': int,
    'h2_page_break': bool,
    'theme': str,
}


def _tracked_rows(metadata: dict) -> list:
    """Read tracked_rows from front matter, falling back to the deprecated
    tracked_teams alias. Returns an empty list if neither is set.

    Logs a deprecation warning the first time tracked_teams is used in a
    document so consumers know to migrate.
    """
    if 'tracked_rows' in metadata:
        return metadata['tracked_rows']
    if 'tracked_teams' in metadata:
        log.warning(
            "front matter 'tracked_teams' is deprecated; rename to 'tracked_rows'"
        )
        return metadata['tracked_teams']
    return []


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
                if isinstance(expected, tuple):
                    expected_name = " or ".join(t.__name__ for t in expected)
                else:
                    expected_name = expected.__name__
                warnings.append(
                    f"front matter '{key}': expected {expected_name}, "
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
        # The closing delimiter must be a line of its own (a bare `---`), not a
        # `---` embedded inside a YAML value or a `---` horizontal rule further
        # down the body.
        close = re.search(r'^---[ \t]*$', content[3:], re.MULTILINE)
        if close is not None:
            raw = content[3:3 + close.start()]
            rest = content[3 + close.end():]
            try:
                meta = yaml.safe_load(raw.strip()) or {}
            except yaml.YAMLError as exc:
                log.warning("front matter is not valid YAML; ignoring it: %s", exc)
                return {}, content
            # A document that merely opens with a `---` thematic break parses to
            # a scalar/list rather than a mapping — treat that as "no front
            # matter" and hand the whole document back untouched.
            if not isinstance(meta, dict):
                log.warning(
                    "front matter did not parse to a mapping (got %s); ignoring it",
                    type(meta).__name__,
                )
                return {}, content
            for warning in validate_front_matter(meta):
                log.warning("%s", warning)
            return meta, rest.strip()
    return {}, content


def resolve_tables_include(metadata: dict, md_path: str | None = None) -> dict:
    """Merge a shared tables-layout file into metadata if `tables_include` is set.

    Resolution order for the include path:
      1. As given — absolute or cwd-relative.
      2. Relative to the markdown file's directory (when ``md_path`` is supplied).

    Per-document ``tables:`` entries override shared layouts on key conflict, so
    a document can pull in the shared file and still tweak one specific table.

    Args:
        metadata: Parsed front matter dict (mutated and returned).
        md_path: Path to the source markdown file, used to resolve the include
            relative to the document when the cwd-relative path doesn't exist.

    Returns:
        The metadata dict with ``tables`` populated from the merge.
    """
    include = metadata.get('tables_include')
    if not include:
        return metadata

    resolved = include if os.path.exists(include) else None
    if resolved is None and md_path:
        candidate = os.path.join(os.path.dirname(os.path.abspath(md_path)), include)
        if os.path.exists(candidate):
            resolved = candidate

    if resolved is None:
        log.warning("tables_include file not found: %r", include)
        return metadata

    with open(resolved, "r", encoding="utf-8") as f:
        shared = yaml.safe_load(f) or {}

    if not isinstance(shared, dict):
        log.warning("tables_include %r did not parse to a dict (got %s); skipping",
                    resolved, type(shared).__name__)
        return metadata

    # Per-doc tables override shared by key
    merged = {**shared, **metadata.get('tables', {})}
    metadata['tables'] = merged
    return metadata


# =============================================================================
# CONVERSION
# =============================================================================

_FENCE_RE = re.compile(r'(?ms)^([ \t]*)(`{3,}|~{3,})[^\n]*\n.*?^\1?\2[ \t]*$')
_INLINE_CODE_RE = re.compile(r'(`+)[^\n]*?\1')
_LIST_MARKER_RE = re.compile(r'^[ \t]*(?:[-*+] |\d+\. )')
# A "bold label" line: **Label:** value  or  **Label**: value. Generated
# markdown emits runs of these on consecutive lines with no blank between
# them, which markdown collapses into a single run-together paragraph.
_BOLD_LABEL_RE = re.compile(r'^[ \t]*\*\*[^*\n]{1,80}\*\*[ \t]*:|^[ \t]*\*\*[^*\n]{1,80}:[ \t]*\*\*')


def _protect_code(md_content: str) -> tuple[str, list[str]]:
    """Stash fenced and inline code spans behind placeholders.

    Typography conversion and the list-marker normalisation below operate on
    raw markdown, so without this guard they would rewrite ``->``, quotes,
    digit ranges, etc. *inside* code samples. Placeholders contain no newlines
    or list markers, so neither pass touches the stashed content.
    """
    stash: list[str] = []

    def _stash(match: re.Match) -> str:
        stash.append(match.group(0))
        return f'\x00CODE{len(stash) - 1}\x00'

    md_content = _FENCE_RE.sub(_stash, md_content)
    md_content = _INLINE_CODE_RE.sub(_stash, md_content)
    return md_content, stash


def _restore_code(md_content: str, stash: list[str]) -> str:
    for i, original in enumerate(stash):
        md_content = md_content.replace(f'\x00CODE{i}\x00', original, 1)
    return md_content


def _separate_generated_blocks(md_content: str) -> str:
    """Insert blank lines that generated markdown omits between block elements.

    python-markdown needs a blank line to start a new block, but generated
    markdown frequently glues blocks together with single newlines. Two cases
    are repaired:

    - A **list** that starts right after a paragraph/heading gets a blank line
      before it. Consecutive list items are left untouched, so genuinely
      *tight* lists stay tight rather than being forced loose.
    - A run of **bold-label** lines (``**Rehab stage:** ...``) — the pattern
      generated field summaries use — gets a blank line before each label, so
      each field becomes its own paragraph instead of collapsing into one
      run-together block.

    A blank is only inserted when the line is glued to a preceding non-blank
    line, so already-separated content is left as-is (no double blanks).
    """
    lines = md_content.split('\n')
    out: list[str] = []
    for i, line in enumerate(lines):
        if i > 0 and lines[i - 1].strip():
            prev_is_list = bool(_LIST_MARKER_RE.match(lines[i - 1]))
            if _LIST_MARKER_RE.match(line) and not prev_is_list:
                out.append('')
            elif _BOLD_LABEL_RE.match(line):
                out.append('')
        out.append(line)
    return '\n'.join(out)


def md_to_html(md_content: str, metadata: dict) -> str:
    """Convert markdown string to a complete HTML document.

    Table layouts declared in metadata['tables'] are applied during
    post-processing. Direction markers ({up}/{down}/{mod}) in bold cells
    are also handled during post-processing.
    """
    # Protect code spans/fences from the source-level rewrites that follow.
    md_content, code_stash = _protect_code(md_content)

    md_content = typographic_convert(md_content)

    # Repair block separation that generated markdown omits (lists glued to
    # paragraphs, runs of bold-label field lines collapsing into one block).
    md_content = _separate_generated_blocks(md_content)

    md_content = _restore_code(md_content, code_stash)

    html_body = markdown.markdown(
        md_content,
        extensions=[
            "tables", "fenced_code", "smarty",
            "sane_lists", "def_list", "footnotes",
            "attr_list", "abbr", "md_in_html",
            "pymdownx.tasklist", "pymdownx.tilde", "pymdownx.mark",
        ],
        extension_configs={
            "pymdownx.tasklist": {
                "custom_checkbox": False,
                "clickable_checkbox": False,
            },
        },
        output_format="html5",
    )

    html_body = postprocess(html_body, metadata=metadata)

    # Table of contents (opt-in via front matter)
    toc_html = ""
    if metadata.get("toc"):
        toc_depth = metadata.get("toc_depth", 3)
        toc_html, html_body = generate_toc(html_body, max_depth=toc_depth)
        toc_html += "\n"

    # Title block from YAML front matter. Escape first so stray <, > or &
    # in the front matter can't inject markup or drop content, then apply
    # typography (quotes/dashes) to the escaped text.
    title_html = ""
    if metadata.get("title"):
        safe_title = typographic_convert(_html.escape(str(metadata["title"]), quote=False))
        title_html += f'<h1>{safe_title}</h1>\n'
    if metadata.get("subtitle"):
        safe_subtitle = typographic_convert(_html.escape(str(metadata["subtitle"]), quote=False))
        title_html += f'<p class="doc-subtitle">{safe_subtitle}</p>\n'

    title_text = _html.escape(str(metadata.get("title", "Document")), quote=False)
    lang = _html.escape(str(metadata.get("lang", "en")), quote=True)
    head_metadata = []
    for field, html_name in (
        ("author", "author"),
        ("subject", "description"),
        ("keywords", "keywords"),
    ):
        value = metadata.get(field)
        if isinstance(value, list):
            value = ", ".join(str(item) for item in value)
        if value:
            escaped = _html.escape(str(value), quote=True)
            head_metadata.append(
                f'    <meta name="{html_name}" content="{escaped}">\n'
            )

    return (
        '<!DOCTYPE html>\n'
        f'<html lang="{lang}">\n'
        '<head>\n'
        '    <meta charset="utf-8">\n'
        f'{"".join(head_metadata)}'
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
        # Without a TOC, keep the first content h2 on the title page so the
        # title doesn't sit alone above a forced break. With a TOC, let it
        # break normally — the TOC fills the title page.
        if not metadata.get('toc'):
            rules.append('.content > h2:first-child { break-before: auto; }')
    if str(metadata.get('orientation', '')).lower() == 'landscape':
        rules.append('@page { size: A4 landscape; }')
    return '\n'.join(rules)


def build_pdf(md_path: str, output_path: str | None = None, style_path: str | None = None, base_style_path: str | None = None, base_url: str | None = None) -> str:
    """Convert a markdown file to PDF.

    Args:
        md_path: Path to input markdown file.
        output_path: Path for output PDF. Defaults to input with .pdf extension.
        base_style_path: Path to base CSS. Defaults to the bundled style.css
            (DEFAULT_STYLE) so consumers don't need to know the install path.
        style_path: Optional CSS overlay loaded after the base style.
        base_url: Optional base URL used to resolve relative URLs in generated
            HTML. Defaults to WeasyPrint's no-base behavior.
    """
    from weasyprint import HTML, CSS

    if base_style_path is None:
        base_style_path = DEFAULT_STYLE

    if output_path is None:
        output_path = os.path.splitext(md_path)[0] + ".pdf"

    # Read markdown and parse front matter
    with open(md_path, "r", encoding="utf-8") as f:
        content = f.read()

    metadata, body = parse_front_matter(content)
    metadata = resolve_tables_include(metadata, md_path)

    # Read CSS (base + optional overlay + theme + front-matter-driven rules)
    css_parts = []
    with open(base_style_path, "r", encoding="utf-8") as f:
        css_parts.append(f.read())
    if style_path:
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
    HTML(string=html, base_url=base_url).write_pdf(
        output_path,
        stylesheets=[CSS(string=css_content, base_url=_STYLES_DIR + "/")],
        pdf_variant="pdf/ua-1",
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
        base_style_path: Path to base CSS. Defaults to the bundled style.css.
        style_path: Optional CSS overlay loaded after the base style.
    """
    if base_style_path is None:
        base_style_path = DEFAULT_STYLE

    if output_path is None:
        output_path = os.path.splitext(md_path)[0] + ".html"

    with open(md_path, "r", encoding="utf-8") as f:
        content = f.read()

    metadata, body = parse_front_matter(content)
    metadata = resolve_tables_include(metadata, md_path)

    # Read CSS
    css_parts = []
    with open(base_style_path, "r", encoding="utf-8") as f:
        css_parts.append(f.read())
    if style_path:
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
        help="Optional CSS overlay loaded after the base style"
    )
    parser.add_argument(
        "--base-style", "-b", default=None,
        help=f"Base CSS stylesheet (default: bundled {os.path.basename(DEFAULT_STYLE)})"
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
