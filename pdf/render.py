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
import json
import logging
import os
import re
import sys
import argparse
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlparse

import yaml
import markdown

from .typography import typographic_convert
from .diagnostics import (
    DEFAULT_STRICT_CODES,
    DIAGNOSTIC_CODES,
    BuildResult,
    DiagnosticsCollector,
    StrictDiagnosticsError,
    StrictPolicy,
    evaluate_strict,
)
from .postprocess import postprocess, _postprocess, generate_toc
from .resources import (
    ResourceAccessError,
    ResourceContext,
    ResourceEvent,
    make_url_fetcher,
)
from .width_metadata import normalise_width_metadata

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
    width_fields = {"table_widths", "columns", "orientation", "page_width_em"}
    for key, value in metadata.items():
        if key in width_fields:
            continue
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
    _, width_warnings = normalise_width_metadata(metadata)
    warnings.extend(width_warnings)
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
            meta, _ = normalise_width_metadata(meta)
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
    result, _ = _resolve_tables_include(metadata, md_path)
    return result


def _resolve_tables_include(
    metadata: dict,
    md_path: str | None = None,
    *,
    resource_context: ResourceContext | None = None,
    collector: DiagnosticsCollector | None = None,
) -> tuple[dict, dict[str, str]]:
    """Resolve one include and retain per-layout provenance for diagnostics."""
    include = metadata.get('tables_include')
    document_tables = metadata.get('tables', {})
    if not include:
        return metadata, {
            key: "document" for key in document_tables
        } if isinstance(document_tables, dict) else {}

    if resource_context is not None:
        resolved_path = resource_context.resolve_path(
            include,
            kind="tables_include",
            on_resource=collector.add_resource if collector is not None else None,
        )
        resolved = str(resolved_path) if resolved_path is not None and resolved_path.is_file() else None
    else:
        resolved = include if os.path.exists(include) else None
        if resolved is None and md_path:
            candidate = os.path.join(os.path.dirname(os.path.abspath(md_path)), include)
            if os.path.exists(candidate):
                resolved = candidate
        if collector is not None:
            path = Path(resolved).resolve() if resolved is not None else None
            collector.add_resource(ResourceEvent(
                "tables_include",
                "resolved" if path is not None else "missing",
                str(include),
                str(path) if path is not None else None,
            ))

    if resolved is None:
        log.warning("tables_include file not found: %r", include)
        if collector is not None:
            collector.add("tables.include_missing")
        return metadata, {
            key: "document" for key in document_tables
        } if isinstance(document_tables, dict) else {}

    try:
        with open(resolved, "r", encoding="utf-8") as f:
            shared = yaml.safe_load(f) or {}
    except yaml.YAMLError:
        if collector is not None:
            collector.add("tables.include_invalid")
        raise

    if not isinstance(shared, dict):
        log.warning("tables_include %r did not parse to a dict (got %s); skipping",
                    resolved, type(shared).__name__)
        if collector is not None:
            collector.add("tables.include_invalid")
        return metadata, {
            key: "document" for key in document_tables
        } if isinstance(document_tables, dict) else {}

    # Per-doc tables override shared by key
    merged = {**shared, **document_tables}
    metadata['tables'] = merged
    sources = {key: "tables_include" for key in shared}
    sources.update({key: "document" for key in document_tables})
    return metadata, sources


# =============================================================================
# CONVERSION
# =============================================================================

_FENCE_RE = re.compile(r'(?ms)^([ \t]*)(`{3,}|~{3,})[^\n]*\n.*?^\1?\2[ \t]*$')
_INLINE_CODE_RE = re.compile(r'(`+)[^\n]*?\1')
_MARKDOWN_IMAGE_RE = re.compile(
    r'!\[[^\]\n]*\]\([^\)\n]*\)(?:\{[^}\n]*\})?'
)
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
    # Optional image titles use straight quotes as Markdown delimiters.
    # Protect the complete token so typography cannot curl those delimiters
    # before Python-Markdown parses the image and caption.
    md_content = _MARKDOWN_IMAGE_RE.sub(_stash, md_content)
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
    """Convert Markdown text to a complete HTML document."""
    return _md_to_html(md_content, metadata)


def _md_to_html(
    md_content: str,
    metadata: dict,
    *,
    collector: DiagnosticsCollector | None = None,
) -> str:
    """Convert markdown string to a complete HTML document.

    Table layouts declared in metadata['tables'] are applied during
    post-processing. Direction markers ({up}/{down}/{mod}) in bold cells
    are also handled during post-processing.
    """
    metadata, width_warnings = normalise_width_metadata(
        {} if metadata is None else metadata
    )
    for warning in width_warnings:
        log.warning("%s", warning)

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

    html_body = _postprocess(html_body, metadata=metadata, _collector=collector)

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


@dataclass(frozen=True)
class _PreparedStyle:
    """One stylesheet layer with its own URL-resolution base."""

    css: str
    base_url: str


@dataclass(frozen=True)
class _PreparedRender:
    """Private, complete input to one WeasyPrint render.

    Keeping preparation behind one value lets acceptance tooling inspect the
    exact same rendered ``Document`` that writes the PDF without changing the
    public ``build_pdf`` contract.
    """

    html: str
    css: str
    html_base_url: str | None
    css_base_url: str
    style_layers: tuple[_PreparedStyle, ...] = ()
    url_fetcher: object | None = None
    collector: DiagnosticsCollector | None = None


def _prepare_render(md_path: str, style_path: str | None = None,
                    base_style_path: str | None = None,
                    base_url: str | None = None) -> _PreparedRender:
    """Prepare HTML and CSS for one render without invoking WeasyPrint."""
    return _prepare_render_input(
        md_path=md_path,
        md_content=None,
        style_path=style_path,
        base_style_path=base_style_path,
        base_url=base_url,
        resource_context=None,
        collector=None,
    )


def _read_style(path: Path, *, base_url: str | None = None) -> _PreparedStyle:
    """Read one CSS layer and retain the base used by its nested URLs."""
    return _PreparedStyle(
        css=path.read_text(encoding="utf-8"),
        base_url=base_url or path.resolve().parent.as_uri() + "/",
    )


def _resolve_explicit_style(
    reference: str | Path,
    *,
    role: str,
    resource_context: ResourceContext,
    collector: DiagnosticsCollector,
) -> Path:
    path = resource_context.resolve_path(
        reference, kind=role, on_resource=collector.add_resource,
    )
    if path is None or not path.is_file():
        missing = str(reference) if path is None else str(path)
        raise FileNotFoundError(f"Stylesheet file not found: {missing}")
    return path


def _prepare_render_input(
    *,
    md_path: str | None,
    md_content: str | None,
    style_path: str | None,
    base_style_path: str | None,
    base_url: str | None,
    resource_context: ResourceContext | None,
    collector: DiagnosticsCollector | None,
) -> _PreparedRender:
    """Shared preparation for legacy and explicit-context PDF entry points."""
    if resource_context is not None and base_url is not None:
        raise ValueError("base_url and resource_context cannot be used together")
    if (md_path is None) == (md_content is None):
        raise ValueError("provide exactly one of md_path or md_content")

    if base_style_path is None:
        base_style_path = DEFAULT_STYLE

    if md_content is None:
        with open(md_path, "r", encoding="utf-8") as f:
            content = f.read()
    else:
        content = md_content

    metadata, body = parse_front_matter(content)
    metadata, layout_sources = _resolve_tables_include(
        metadata,
        md_path,
        resource_context=resource_context,
        collector=collector,
    )
    if collector is not None:
        collector.layout_sources.update(layout_sources)

    css_parts = []
    style_layers = []
    if resource_context is None:
        with open(base_style_path, "r", encoding="utf-8") as f:
            css_parts.append(f.read())
        if style_path:
            with open(style_path, "r", encoding="utf-8") as f:
                css_parts.append(f.read())
    else:
        if base_style_path == DEFAULT_STYLE:
            base_path = Path(DEFAULT_STYLE).resolve()
            collector.add_resource(ResourceEvent(
                "base_style", "resolved", "packaged:style.css", str(base_path),
            ))
        else:
            base_path = _resolve_explicit_style(
                base_style_path,
                role="base_style",
                resource_context=resource_context,
                collector=collector,
            )
        style_layers.append(_read_style(base_path))
        css_parts.append(style_layers[-1].css)
        if style_path:
            overlay_path = _resolve_explicit_style(
                style_path,
                role="style",
                resource_context=resource_context,
                collector=collector,
            )
            style_layers.append(_read_style(overlay_path))
            css_parts.append(style_layers[-1].css)

    theme = metadata.get('theme')
    if theme:
        if not isinstance(theme, str) or '/' in theme or '\\' in theme or '..' in theme:
            log.warning("invalid theme name: %r", theme)
            theme = None
    if theme:
        if resource_context is None:
            theme_path = get_style_path(f'{theme}.css')
        else:
            context_theme = resource_context.resolve_path(f'{theme}.css', kind="theme")
            packaged_theme = Path(_STYLES_DIR, f'{theme}.css').resolve()
            theme_path = str(
                context_theme if context_theme is not None and context_theme.is_file()
                else packaged_theme
            )
        if os.path.exists(theme_path):
            if resource_context is None:
                with open(theme_path, "r", encoding="utf-8") as f:
                    css_parts.append(f.read())
            else:
                theme_file = Path(theme_path)
                collector.add_resource(ResourceEvent(
                    "theme",
                    "resolved",
                    f"{theme}.css",
                    str(theme_file),
                ))
                style_layers.append(_read_style(theme_file))
                css_parts.append(style_layers[-1].css)
        else:
            log.warning("theme '%s' not found (%s)", theme, theme_path)
            if collector is not None:
                collector.add_resource(ResourceEvent(
                    "theme", "missing", f"{theme}.css", str(theme_path),
                ))

    fm_css = _front_matter_css(metadata)
    if fm_css:
        css_parts.append(fm_css)
        if resource_context is not None:
            style_layers.append(_PreparedStyle(fm_css, resource_context.base_url))

    if resource_context is not None:
        html_base_url = resource_context.base_url
        url_fetcher = make_url_fetcher(
            resource_context, on_resource=collector.add_resource,
        )
    else:
        html_base_url = (
            base_url
            if base_url is not None
            else str(Path(md_path).resolve().parent)
        )
        url_fetcher = None

    return _PreparedRender(
        html=_md_to_html(body, metadata, collector=collector),
        css="\n\n".join(css_parts),
        html_base_url=html_base_url,
        css_base_url=_STYLES_DIR + "/",
        style_layers=tuple(style_layers),
        url_fetcher=url_fetcher,
        collector=collector,
    )


def _local_image_path(src: str, base_url: str | None) -> Path | None:
    """Resolve a local image source, returning None for non-file URLs."""
    source = urlparse(src)
    if source.scheme in {"http", "https", "data"}:
        return None
    if source.scheme == "file":
        return Path(unquote(source.path))
    if source.scheme:
        return None

    source_path = Path(unquote(source.path))
    if source_path.is_absolute():
        return source_path
    if base_url is None:
        return None

    base = urlparse(base_url)
    if base.scheme == "file":
        base_path = Path(unquote(base.path))
    elif base.scheme:
        return None
    else:
        base_path = Path(base_url)
    return (base_path / source_path).resolve()


def _validate_local_images(
    prepared: _PreparedRender,
    *,
    resource_context: ResourceContext | None = None,
) -> None:
    """Fail before rendering when generated HTML references a missing file."""
    missing = []
    for match in re.finditer(
        r'<img\b[^>]*\bsrc\s*=\s*(["\'])(.*?)\1',
        prepared.html,
        flags=re.DOTALL | re.IGNORECASE,
    ):
        src = _html.unescape(match.group(2))
        if resource_context is not None:
            local_path = resource_context.resolve_path(
                src,
                kind="image",
                on_resource=(
                    prepared.collector.add_resource
                    if prepared.collector is not None else None
                ),
            )
        else:
            local_path = _local_image_path(src, prepared.html_base_url)
            if prepared.collector is not None:
                status = (
                    "remote" if local_path is None
                    else "resolved" if local_path.is_file()
                    else "missing"
                )
                prepared.collector.add_resource(ResourceEvent(
                    "image",
                    status,
                    src,
                    str(local_path) if local_path is not None else None,
                ))
        if local_path is not None and not local_path.is_file():
            missing.append(str(local_path))
    if missing:
        details = "\n".join(f"- {path}" for path in sorted(set(missing)))
        raise FileNotFoundError(f"Markdown image file(s) not found:\n{details}")


def _render_document(prepared: _PreparedRender):
    """Render a prepared input once and return the private Weasy Document."""
    from weasyprint import HTML, CSS

    if not prepared.style_layers:
        return HTML(
            string=prepared.html,
            base_url=prepared.html_base_url,
        ).render(stylesheets=[CSS(string=prepared.css, base_url=prepared.css_base_url)])

    from weasyprint.text.fonts import FontConfiguration

    font_config = FontConfiguration()
    stylesheets = [
        CSS(
            string=style.css,
            base_url=style.base_url,
            url_fetcher=prepared.url_fetcher,
            font_config=font_config,
        )
        for style in prepared.style_layers
    ]
    return HTML(
        string=prepared.html,
        base_url=prepared.html_base_url,
        url_fetcher=prepared.url_fetcher,
    ).render(stylesheets=stylesheets, font_config=font_config)


def _strict_policy(strict_codes) -> StrictPolicy | None:
    if strict_codes is None or strict_codes is False:
        return None
    if isinstance(strict_codes, str):
        raise ValueError("strict_codes must be a collection of diagnostic codes")
    codes = frozenset(strict_codes)
    return StrictPolicy(codes) if codes else None


def _attach_diagnostics(exc: BaseException, collector: DiagnosticsCollector) -> None:
    """Make failure diagnostics available without changing exception classes."""
    try:
        exc.diagnostics = collector.build_report()
    except (AttributeError, TypeError):
        pass


def _raise_fetch_violations(collector: DiagnosticsCollector) -> None:
    """Reject local fetch violations that WeasyPrint may have logged and ignored."""
    report = collector.build_report()
    for resource in report["resources"]:
        if resource.get("kind") != "fetch":
            continue
        status = resource.get("status")
        if status in {"blocked", "missing"} or (
            status == "failed" and resource.get("path") is not None
        ):
            raise ResourceAccessError(
                f"Local render resource was {status}",
                reference=resource.get("reference", "[unknown resource]"),
                kind="fetch",
            )


def _build_pdf_result(
    *,
    md_path: str | None,
    md_content: str | None,
    output_path: str,
    style_path: str | None,
    base_style_path: str | None,
    base_url: str | None,
    resource_context: ResourceContext | None,
    strict_codes,
) -> BuildResult:
    collector = DiagnosticsCollector()
    policy = _strict_policy(strict_codes)
    try:
        prepared = _prepare_render_input(
            md_path=md_path,
            md_content=md_content,
            style_path=style_path,
            base_style_path=base_style_path,
            base_url=base_url,
            resource_context=resource_context,
            collector=collector,
        )
        _validate_local_images(prepared, resource_context=resource_context)
        evaluate_strict(collector.build_report(), policy)

        document = _render_document(prepared)
        if resource_context is None:
            document.write_pdf(output_path, pdf_variant="pdf/ua-1")
        else:
            pdf_bytes = document.write_pdf(pdf_variant="pdf/ua-1")
            _raise_fetch_violations(collector)
            Path(output_path).write_bytes(pdf_bytes)
    except yaml.YAMLError as exc:
        try:
            evaluate_strict(collector.build_report(), policy)
        except StrictDiagnosticsError as strict_exc:
            raise strict_exc from exc
        _attach_diagnostics(exc, collector)
        raise
    except Exception as exc:
        _attach_diagnostics(exc, collector)
        raise

    report = collector.build_report()
    print(f"Created: {output_path}")
    return BuildResult(output_path=output_path, diagnostics=report)


def build_pdf_with_result(
    md_path: str,
    output_path: str | None = None,
    style_path: str | None = None,
    base_style_path: str | None = None,
    base_url: str | None = None,
    *,
    resource_context: ResourceContext | None = None,
    strict_codes=(),
) -> BuildResult:
    """Build a PDF and return deterministic layout/resource diagnostics.

    The existing ``build_pdf`` API remains unchanged. ``resource_context`` opts
    into deterministic local dependency resolution; it cannot be combined with
    the legacy image-only ``base_url`` override.
    """
    if output_path is None:
        output_path = os.path.splitext(md_path)[0] + ".pdf"
    if resource_context is not None and not isinstance(resource_context, ResourceContext):
        raise TypeError("resource_context must be a ResourceContext")
    return _build_pdf_result(
        md_path=md_path,
        md_content=None,
        output_path=output_path,
        style_path=style_path,
        base_style_path=base_style_path,
        base_url=base_url,
        resource_context=resource_context,
        strict_codes=strict_codes,
    )


def build_pdf_from_markdown(
    md_content: str,
    output_path: str,
    *,
    resource_context: ResourceContext,
    style_path: str | None = None,
    base_style_path: str | None = None,
    strict_codes=(),
) -> BuildResult:
    """Build a PDF from source text using one explicit resource context."""
    if not isinstance(resource_context, ResourceContext):
        raise TypeError("resource_context must be a ResourceContext")
    return _build_pdf_result(
        md_path=None,
        md_content=md_content,
        output_path=output_path,
        style_path=style_path,
        base_style_path=base_style_path,
        base_url=None,
        resource_context=resource_context,
        strict_codes=strict_codes,
    )


def build_pdf(md_path: str, output_path: str | None = None, style_path: str | None = None, base_style_path: str | None = None, base_url: str | None = None) -> str:
    """Convert a markdown file to PDF.

    Args:
        md_path: Path to input markdown file.
        output_path: Path for output PDF. Defaults to input with .pdf extension.
        base_style_path: Path to base CSS. Defaults to the bundled style.css
            (DEFAULT_STYLE) so consumers don't need to know the install path.
        style_path: Optional CSS overlay loaded after the base style.
        base_url: Optional base URL used to resolve relative URLs in generated
            HTML. Defaults to the input Markdown file's directory.
    """
    if output_path is None:
        output_path = os.path.splitext(md_path)[0] + ".pdf"

    prepared = _prepare_render(
        md_path,
        style_path=style_path,
        base_style_path=base_style_path,
        base_url=base_url,
    )
    _validate_local_images(prepared)
    _render_document(prepared).write_pdf(output_path, pdf_variant="pdf/ua-1")

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
    if output_path is None:
        output_path = os.path.splitext(md_path)[0] + ".html"
    prepared = _prepare_render(
        md_path, style_path=style_path, base_style_path=base_style_path,
    )

    # Inject CSS into <head>
    style_tag = f'<style>\n{prepared.css}\n</style>'
    html = prepared.html.replace('</head>', f'{style_tag}\n</head>', 1)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"Created: {output_path}")
    return output_path


# =============================================================================
# CLI
# =============================================================================

class _DiagnosticsPathError(ValueError):
    """A JSON sidecar aliases an output it must not overwrite."""


def _diagnostics_json_path(path: str, *, input_path: str, output_path: str) -> Path:
    target = Path(path).resolve()
    protected = {Path(input_path).resolve(), Path(output_path).resolve()}
    for protected_path in protected:
        same_file = target == protected_path
        if not same_file and target.exists() and protected_path.exists():
            try:
                same_file = target.samefile(protected_path)
            except OSError:
                same_file = False
        if same_file:
            raise _DiagnosticsPathError(
                "diagnostics JSON cannot overwrite the input or PDF output"
            )
    return target


def _write_diagnostics_json(
    path: str,
    report,
    *,
    input_path: str,
    output_path: str,
) -> None:
    target = _diagnostics_json_path(
        path, input_path=input_path, output_path=output_path,
    )
    target.write_text(
        json.dumps(report.to_dict(), indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def _cli_strict_codes(use_defaults, values) -> tuple[str, ...]:
    if not use_defaults and not values:
        return ()
    codes = set(DEFAULT_STRICT_CODES if use_defaults else ())
    codes.update(values or ())
    StrictPolicy(frozenset(codes))
    return tuple(sorted(codes))


def _build_pdf_from_cli(
    input_path: str,
    output_path: str,
    *,
    style_path: str | None,
    base_style_path: str | None,
    resource_context: ResourceContext | None,
    strict_codes: tuple[str, ...],
    diagnostics_json: str | None,
) -> None:
    """Run one result build and keep strict/sidecar behavior in one place."""
    if diagnostics_json:
        _diagnostics_json_path(
            diagnostics_json, input_path=input_path, output_path=output_path,
        )
    try:
        result = build_pdf_with_result(
            input_path, output_path,
            style_path=style_path,
            base_style_path=base_style_path,
            resource_context=resource_context,
            strict_codes=strict_codes,
        )
    except StrictDiagnosticsError as exc:
        if diagnostics_json:
            _write_diagnostics_json(
                diagnostics_json,
                exc.report,
                input_path=input_path,
                output_path=output_path,
            )
        raise
    if diagnostics_json:
        _write_diagnostics_json(
            diagnostics_json,
            result.diagnostics,
            input_path=input_path,
            output_path=output_path,
        )


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
    parser.add_argument(
        "--resource-root", default=None,
        help="Explicit local base for includes, images, styles, and theme overrides",
    )
    parser.add_argument(
        "--allowed-resource-root", default=None,
        help="Optional symlink-aware local containment root (requires --resource-root)",
    )
    parser.add_argument(
        "--diagnostics-json", default=None,
        help="Write one document's structured diagnostics to this JSON sidecar",
    )
    parser.add_argument(
        "--strict", action="store_true",
        help="Fail for the documented default strict diagnostic set",
    )
    parser.add_argument(
        "--strict-code", action="append", default=None, metavar="CODE",
        help=(
            "Fail for one selected diagnostic code; repeat as needed. Known codes: "
            + ", ".join(sorted(DIAGNOSTIC_CODES))
        ),
    )

    args = parser.parse_args()

    using_new_pdf_options = bool(
        args.resource_root or args.allowed_resource_root
        or args.diagnostics_json or args.strict or args.strict_code
    )
    if args.html and using_new_pdf_options:
        parser.error("resource contexts and diagnostics are currently PDF-only")
    if args.allowed_resource_root and not args.resource_root:
        parser.error("--allowed-resource-root requires --resource-root")

    try:
        strict_codes = _cli_strict_codes(args.strict, args.strict_code)
        resource_context = (
            ResourceContext(args.resource_root, args.allowed_resource_root)
            if args.resource_root else None
        )
    except (TypeError, ValueError) as exc:
        parser.error(str(exc))

    if resource_context is None:
        style_path = get_style_path(args.style) if args.style else None
        base_style_path = get_style_path(args.base_style) if args.base_style else None
    else:
        style_path = args.style
        base_style_path = args.base_style

    build_fn = build_html if args.html else build_pdf
    ext = ".html" if args.html else ".pdf"

    # Handle explicit output: pdf input.md output.pdf
    explicit_output = len(args.files) == 2 and args.files[1].endswith(ext)
    if explicit_output:
        if using_new_pdf_options:
            try:
                _build_pdf_from_cli(
                    args.files[0], args.files[1],
                    style_path=style_path,
                    base_style_path=base_style_path,
                    resource_context=resource_context,
                    strict_codes=strict_codes,
                    diagnostics_json=args.diagnostics_json,
                )
            except _DiagnosticsPathError as exc:
                parser.error(str(exc))
        else:
            build_fn(args.files[0], args.files[1],
                     style_path=style_path, base_style_path=base_style_path)
        return

    # Batch: convert all .md files
    md_files = [f for f in args.files if f.endswith(".md")]
    if not md_files:
        md_files = [args.files[0]]
    if args.diagnostics_json and len(md_files) != 1:
        parser.error("--diagnostics-json supports exactly one input document")

    for md_file in md_files:
        if args.output_dir:
            os.makedirs(args.output_dir, exist_ok=True)
            basename = os.path.splitext(os.path.basename(md_file))[0] + ext
            out_path = os.path.join(args.output_dir, basename)
        else:
            out_path = None  # defaults to same dir as input

        if using_new_pdf_options:
            final_output = out_path or os.path.splitext(md_file)[0] + ".pdf"
            try:
                _build_pdf_from_cli(
                    md_file, final_output,
                    style_path=style_path,
                    base_style_path=base_style_path,
                    resource_context=resource_context,
                    strict_codes=strict_codes,
                    diagnostics_json=args.diagnostics_json,
                )
            except _DiagnosticsPathError as exc:
                parser.error(str(exc))
        else:
            build_fn(md_file, out_path,
                     style_path=style_path, base_style_path=base_style_path)


if __name__ == "__main__":
    main()
