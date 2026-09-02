"""HTML post-processing passes for markdown-to-PDF conversion.

Table layouts, column widths, alignment, CSS classes, and row highlighting
are driven by declarations in the YAML front matter. All domain-specific
behaviour is opt-in via metadata:

    extra_callout_keywords  — additional bold keyword → tier mappings
    direction_markers       — enable {up}/{down}/{mod} row highlighting
    risk_tables             — list of CSS classes for risk-cell colouring

General-purpose transforms (blockquotes, headings, bold labels, section rows,
result colouring) always run regardless of metadata.

Blockquote callout tiers (cool-to-warm):
    default     — #666 grey border, light grey background
    info        — #1e3a5f navy border, light navy background
    tip         — #1a7a6d teal border, light teal background
    important   — #6b3fa0 purple border, light purple background
    caution     — #946b00 amber border, light amber background
    warning     — #d94040 red border, light pink background
"""

import html as _html
import re

from pdf.blockquotes import (  # noqa: F401
    split_merged_blockquotes,
    classify_blockquotes,
)
from pdf.table_transforms import (  # noqa: F401
    _strip_tags,
    _is_numeric,
    _is_short_text,
    detect_table_section_rows,
    align_table_columns,
    highlight_table_rows,
    _highlight_tracked_rows,
    _highlight_direction_rows,
    colour_results,
    colour_risk_cells,
    _extract_headers,
    _match_layout,
    _build_colgroup,
    _apply_column_alignment,
    apply_table_layouts,
    apply_default_table_widths,
    _validated_width_metadata,
    generate_toc,
)


# =============================================================================
# HEADING / PAGE LAYOUT TRANSFORMS
# =============================================================================

def wrap_heading_groups(html):
    """Wrap h2/h3 + italic subtitle + first body paragraph in a div.

    Prevents orphaned headings at page bottoms by keeping the heading,
    its subtitle line, and the opening paragraph as one unbreakable unit.
    """
    return re.sub(
        r"(<h[23][^>]*>.*?</h[23]>)\s*(<p><em>.*?</em></p>)\s*(<p>.*?</p>)",
        r'<div class="heading-group">\1\n\2\n\3</div>',
        html,
        flags=re.DOTALL,
    )


def mark_bold_labels(html):
    """Add keep-with-next to paragraphs containing only bold text.

    These are typically labels like 'Progression:' or 'Key points:' that
    should stay with the content that follows them.
    """
    return re.sub(
        r"(<p>)(<strong>[^<]+</strong>)(</p>)",
        r'<p class="keep-with-next">\2</p>',
        html,
    )


def bind_headings(html):
    """Prevent orphaned headings at page bottoms.

    Adds break-before:avoid as an inline style to any block element
    (table, svg, div, p) that immediately follows a heading. This tells
    WeasyPrint to keep the element on the same page as its heading.
    """
    def add_break_avoid(match):
        heading = match.group(1)
        gap = match.group(2)
        tag = match.group(3)
        rest = match.group(4)

        if 'break-before' in rest:
            return match.group(0)
        if 'style="' in rest:
            rest = rest.replace('style="', 'style="break-before:avoid; ', 1)
        else:
            rest = f' style="break-before:avoid;"{rest}'
        return f'{heading}{gap}{tag}{rest}'

    html = re.sub(
        r'(<h[2-4][^>]*>.*?</h[2-4]>)'    # heading
        r'(\s*)'                             # whitespace/newlines
        r'(<(?:table|svg|figure|div|p)\b)'   # opening tag name
        r'([^>]*>)',                          # rest of opening tag
        add_break_avoid,
        html,
        flags=re.DOTALL,
    )
    return html


def convert_page_breaks(html):
    """Convert page-break HTML comments to styling for WeasyPrint.

    Standard HTML comments are valid in markdown and invisible in normal
    renderers.

    Two markers:
      <!-- page-break -->     — force a page break at this point
      <!-- no-page-break -->  — suppress automatic break on the next heading
    """
    def _set_break(tag, value):
        if 'break-before' in tag:
            return tag
        if 'style="' in tag:
            return tag.replace('style="', f'style="break-before: {value}; ', 1)
        return tag[:-1] + f' style="break-before: {value};">'

    # Put the break on the content that follows. An empty break-only div can
    # itself land at the top of a page and force the real content onto the
    # next page, producing a blank sheet.
    html = re.sub(
        r'<!--\s*page-break\s*-->\s*(<[^!/][^>]*>)',
        lambda match: _set_break(match.group(1), 'page'),
        html,
    )
    # A marker at end of input has nothing to attach to. Keep the established
    # harmless fallback so the marker is still consumed deterministically.
    html = re.sub(
        r'<!--\s*page-break\s*-->',
        '<div style="break-before: page;"></div>',
        html,
    )
    # <!-- no-page-break --> before a heading suppresses its automatic break,
    # merging into any existing style rather than emitting a second attribute.
    def _suppress_break(match):
        tag = match.group(1)
        return _set_break(tag, 'auto')

    html = re.sub(
        r'<!--\s*no-page-break\s*-->\s*(<h[1-6][^>]*>)',
        _suppress_break,
        html,
    )
    return html


# =============================================================================
# IMAGE / FIGURE TRANSFORMS
# =============================================================================

_FIGURE_LAYOUT_CLASSES = {
    "figure-wide",
    "figure-narrow",
    "figure-page",
}


def _html_attribute(tag: str, name: str) -> str | None:
    """Return one quoted HTML attribute value, decoded for safe reuse."""
    match = re.search(
        rf"\b{re.escape(name)}\s*=\s*(?P<quote>[\"'])(?P<value>.*?)(?P=quote)",
        tag,
        flags=re.DOTALL | re.IGNORECASE,
    )
    if match is None:
        return None
    return _html.unescape(match.group("value"))


def wrap_standalone_images(html: str) -> str:
    """Turn standalone Markdown images into semantic captioned figures.

    Python-Markdown emits a standalone image as ``<p><img ...></p>``. The
    image's optional title becomes its visible caption, falling back to alt
    text. Supported layout classes on the image are copied to the figure.
    Inline images and author-supplied ``<figure>`` markup are left unchanged.
    """

    def figure(match: re.Match) -> str:
        image = match.group("image")
        alt = _html_attribute(image, "alt") or ""
        title = _html_attribute(image, "title")
        caption = title if title is not None else alt
        classes = set((_html_attribute(image, "class") or "").split())
        layout_classes = sorted(classes & _FIGURE_LAYOUT_CLASSES)
        figure_classes = " ".join(["markdown-figure", *layout_classes])
        caption_html = ""
        if caption:
            caption_html = (
                f"<figcaption>{_html.escape(caption, quote=False)}</figcaption>"
            )
        return f'<figure class="{figure_classes}">{image}{caption_html}</figure>'

    return re.sub(
        r"<p>\s*(?P<image><img\b[^>]*>)\s*</p>",
        figure,
        html,
        flags=re.DOTALL | re.IGNORECASE,
    )


# =============================================================================
# MAIN ENTRY POINTS
# =============================================================================

def postprocess(html, metadata=None):
    """Run all HTML post-processing passes.

    Args:
        html: HTML string to process.
        metadata: Optional dict from YAML front matter. When present and
                  containing 'tables', applies front-matter-driven table
                  layouts (column widths, alignment, CSS classes, row
                  highlighting).
    """
    metadata = _validated_width_metadata(metadata)

    # General-purpose transforms (always run)
    html = split_merged_blockquotes(html)
    extra_kw = metadata.get('extra_callout_keywords') if metadata else None
    html = classify_blockquotes(html, extra_keywords=extra_kw)
    html = wrap_heading_groups(html)
    html = mark_bold_labels(html)
    html = detect_table_section_rows(html)

    # Table layout from front matter
    if metadata and metadata.get('tables'):
        html = apply_table_layouts(html, metadata)

    # Typed column widths for every other table (declared layouts already have
    # a colgroup and are skipped). Gives consistent, content-typed widths.
    html = apply_default_table_widths(html, metadata)

    # Tracked-row highlighting (when tables: is absent, e.g. schedule
    # passing only tracked_rows without table layout declarations).
    # Accepts the deprecated `tracked_teams` alias via _tracked_rows().
    if metadata and not metadata.get('tables'):
        from .render import _tracked_rows
        rows = _tracked_rows(metadata)
        if rows:
            html = re.sub(
                r'<table[^>]*>.*?</table>',
                lambda m: _highlight_tracked_rows(m.group(0), rows),
                html,
                flags=re.DOTALL,
            )

    # Auto-align: on by default, disable with auto_align_columns: false
    if not metadata or metadata.get('auto_align_columns', True) is not False:
        html = align_table_columns(html)
    # Auto bold-row highlight: opt-in via metadata
    if metadata and metadata.get('auto_highlight_bold_rows'):
        html = highlight_table_rows(html)

    # Post-table transforms
    html = colour_results(html)
    risk_tables = metadata.get('risk_tables') if metadata else None
    html = colour_risk_cells(html, risk_tables=risk_tables)
    html = convert_page_breaks(html)
    html = wrap_standalone_images(html)
    html = bind_headings(html)

    return html


def classify_marker_rows(html):
    """Apply verdict-based row tinting for retrospective reports.

    Detects zero-width marker characters inserted by the report generator:
    - U+200B -> verdict-success (green tint)
    - U+200C -> verdict-warning (amber tint)
    - U+200D -> verdict-failure (red tint)
    Markers are removed after classification.
    """
    def classify_verdict_row(match):
        row = match.group(0)
        if '\u200d' in row:
            cls = 'verdict-failure'
        elif '\u200c' in row:
            cls = 'verdict-warning'
        elif '\u200b' in row:
            cls = 'verdict-success'
        else:
            return row

        row = row.replace('\u200b', '').replace('\u200c', '').replace('\u200d', '')
        row = re.sub(r'<tr(\s|>)', rf'<tr class="{cls}"\1', row, count=1)

        return row

    return re.sub(r'<tr[^>]*>.*?</tr>', classify_verdict_row, html, flags=re.DOTALL)
