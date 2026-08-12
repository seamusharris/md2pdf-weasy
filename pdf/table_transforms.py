"""Table-related HTML transforms for markdown-to-PDF conversion.

Alignment, highlighting, layout, coloring, section-row detection, and TOC
generation. All transforms operate on HTML strings using regex.
"""

import os
import re

import yaml


# =============================================================================
# DEFAULT COLUMN WIDTHS
# =============================================================================
#
# Layouts in tables.yml or document front matter can declare columns without
# explicit widths. When that happens, the column header is looked up here.
# Widths are unitless relative weights — normalised to 100% in PDF colgroups,
# usable directly as character widths in XLSX exports.

_DEFAULT_WIDTHS_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), 'default_widths.yml'
)


def _load_default_widths():
    if not os.path.exists(_DEFAULT_WIDTHS_PATH):
        return {'fallback': 10, 'widths': {}}
    with open(_DEFAULT_WIDTHS_PATH, 'r', encoding='utf-8') as f:
        loaded = yaml.safe_load(f) or {}
    return {
        'fallback': loaded.get('fallback', 10),
        # Lowercased keys for case-insensitive lookup
        'widths': {k.lower(): v for k, v in (loaded.get('widths') or {}).items()},
    }


_DEFAULT_WIDTHS = _load_default_widths()


def _column_width(col):
    """Resolve a column's width: explicit width first, then defaults by name."""
    if 'width' in col:
        return col['width']
    name = col.get('name', '').lower()
    return _DEFAULT_WIDTHS['widths'].get(name, _DEFAULT_WIDTHS['fallback'])


# =============================================================================
# HELPERS
# =============================================================================

def _strip_tags(text):
    """Remove HTML tags to get plain text content."""
    return re.sub(r"<[^>]+>", "", text).strip()


def _is_numeric(text):
    """Check if text content is numeric (possibly with signs, decimals, %, en-dashes, fractions, W-L-D)."""
    clean = _strip_tags(text).strip()
    if not clean or clean == "-" or clean == "\u2014":
        return True  # empty, dash, or em-dash counts as numeric-compatible
    # Standard numbers: 42, +5, -3, 1.5, 100%, 1,234
    if re.match(r"^[+-]?\d[\d,.]*%?$", clean):
        return True
    # En-dash ranges: 5\u20133, used for digit ranges
    if re.match(r"^\d+\u2013\d+$", clean):
        return True
    # Fractions: 1/6, 2nd/8
    if re.match(r"^\d+\w*/\d+$", clean):
        return True
    # W-L-D records: 5-3-0, 12-1-2
    if re.match(r"^\d+-\d+-\d+$", clean):
        return True
    return False


def _is_short_text(text):
    """Check if text is a short centred value (1-3 chars, like H/A, W/L)."""
    clean = _strip_tags(text).strip()
    return len(clean) <= 3 and clean != ""


# =============================================================================
# DETECTION
# =============================================================================

def detect_table_section_rows(html):
    """Detect table rows where only the first cell has content.

    Rows like '| Movement & Game Drills | | |' act as section dividers.
    Adds a CSS class so they can be styled differently from data rows.
    """
    def process_row(match):
        row = match.group(0)
        cells = re.findall(r"<td>(.*?)</td>", row, flags=re.DOTALL)
        if len(cells) >= 2:
            non_empty = [c.strip() for c in cells if c.strip()]
            if len(non_empty) == 1 and cells[0].strip():
                return row.replace("<tr>", '<tr class="table-section">', 1)
        return row

    return re.sub(r"<tr>.*?</tr>", process_row, html, flags=re.DOTALL)


# =============================================================================
# ALIGNMENT
# =============================================================================

def align_table_columns(html):
    """Add alignment classes to table cells based on column content.

    Scans each table's body cells to determine column types:
    - Columns where all data cells are numeric -> class="num" (right-aligned)
    - Columns where all data cells are short (1-3 chars) -> class="ctr" (centred)
    - First column (typically rank/index) -> class="ctr" if short
    - Team/name columns (long text) -> left-aligned (default)

    On by default. Disable with ``auto_align_columns: false`` in front matter.
    """
    def process_table(match):
        table_html = match.group(0)

        # Extract body rows (skip header rows in thead)
        tbody_match = re.search(r"<tbody>(.*?)</tbody>", table_html, re.DOTALL)
        if tbody_match:
            body_html = tbody_match.group(1)
        else:
            body_html = table_html

        rows = re.findall(r"<tr[^>]*>(.*?)</tr>", body_html, re.DOTALL)
        if not rows:
            return table_html

        # Analyse columns from data rows
        col_cells = {}
        for row_html in rows:
            cells = re.findall(r"<td[^>]*>(.*?)</td>", row_html, re.DOTALL)
            for i, cell in enumerate(cells):
                col_cells.setdefault(i, []).append(cell)

        if not col_cells:
            return table_html

        num_cols = max(col_cells.keys()) + 1

        # Determine alignment per column
        col_class = {}
        for i in range(num_cols):
            cells = col_cells.get(i, [])
            if not cells:
                continue

            non_empty = [c for c in cells if _strip_tags(c).strip() and _strip_tags(c).strip() != "-"]
            if not non_empty:
                continue

            if all(_is_numeric(c) for c in cells):
                if i == 0 and all(_is_short_text(c) for c in non_empty):
                    col_class[i] = "ctr"
                else:
                    col_class[i] = "num"
            elif all(_is_short_text(c) for c in non_empty):
                col_class[i] = "ctr"

        if not col_class:
            return table_html

        # Apply classes to td elements
        def add_cell_classes(row_match):
            row_html = row_match.group(0)
            cell_index = [0]

            def replace_td(td_match):
                idx = cell_index[0]
                cell_index[0] += 1
                cls = col_class.get(idx)
                if cls:
                    tag = td_match.group(0)
                    if 'class="' in tag:
                        return re.sub(r'class="', f'class="{cls} ', tag, count=1)
                    else:
                        return tag.replace("<td", f'<td class="{cls}"', 1)
                return td_match.group(0)

            return re.sub(r"<td[^>]*>", replace_td, row_html)

        result = re.sub(r"<tr[^>]*>(?=.*?<td).*?</tr>", add_cell_classes, table_html, flags=re.DOTALL)
        return result

    return re.sub(r"<table[^>]*>.*?</table>", process_table, html, flags=re.DOTALL)


# =============================================================================
# HIGHLIGHTING
# =============================================================================

def highlight_table_rows(html):
    """Detect rows where a cell is wrapped entirely in <strong> and add highlight class.

    Opt-in via front-matter metadata: ``auto_highlight_bold_rows: true``.
    """
    def process_row(match):
        row = match.group(0)
        cells = re.findall(r"<td[^>]*>(.*?)</td>", row, re.DOTALL)
        for cell in cells:
            stripped = cell.strip()
            m = re.match(r"^<strong>(.+)</strong>$", stripped)
            if m:
                inner = m.group(1)
                if len(inner) > 3:
                    new_row = row.replace("<tr>", '<tr class="highlight">', 1)
                    new_row = new_row.replace(f"<strong>{inner}</strong>", inner, 1)
                    return new_row
        return row

    return re.sub(r"<tr>.*?</tr>", process_row, html, flags=re.DOTALL)


def _highlight_tracked_rows(table_html, tracked_rows):
    """Add class="highlight" to rows containing any tracked string.

    Matches against both the raw name and common typographic variants
    (e.g. hyphen vs en dash) since typography conversion may have
    transformed text in the HTML.
    """
    if not tracked_rows:
        return table_html

    tracked_variants = []
    for t in tracked_rows:
        variants = {t.lower()}
        if '-' in t:
            variants.add(t.replace('-', '\u2013').lower())
        if '\u2013' in t:
            variants.add(t.replace('\u2013', '-').lower())
        tracked_variants.append(variants)

    def check_row(match):
        row = match.group(0)
        if '<th' in row:
            return row
        # Skip rows already classified by direction markers
        if 'highlight-' in row:
            return row
        row_text = _strip_tags(row).lower()
        for variants in tracked_variants:
            if any(v in row_text for v in variants):
                new_row = row.replace('<tr>', '<tr class="highlight">', 1)
                new_row = re.sub(r'<strong>([^<]*)</strong>', r'\1', new_row)
                return new_row
        return row

    return re.sub(r'<tr[^>]*>.*?</tr>', check_row, table_html, flags=re.DOTALL)


def _highlight_direction_rows(table_html):
    """Detect bold-wrapped cells with direction markers and apply row classes.

    Three tiers per direction, stackable from a base direction marker:

      **{up}Team**         strong move-up      → tr.highlight-up
      **{up}{mod}Team**    moderate move-up    → tr.highlight-mod-up
      **{up}{watch}Team**  watch-tier move-up  → tr.highlight-watch-up
      **{down}Team**       strong move-down    → tr.highlight-down
      **{down}{mod}Team**  moderate move-down  → tr.highlight-mod-down
      **{down}{watch}Team** watch move-down    → tr.highlight-watch-down

    `{mod}` and `{watch}` always follow a direction marker; on their own
    they're not recognised. Only rows with a direction marker are
    highlighted; plain bold cells are left unchanged.
    """
    def process_row(match):
        row = match.group(0)
        cells = re.findall(r"<td[^>]*>(.*?)</td>", row, re.DOTALL)
        for cell in cells:
            stripped = cell.strip()
            m = re.match(r"^<strong>(.+)</strong>$", stripped)
            if not m:
                continue
            inner = m.group(1)

            direction = None
            tier = None   # None (strong), 'mod', or 'watch'
            clean = inner
            if clean.startswith('{up}'):
                direction = 'up'
                clean = clean[4:]
            elif clean.startswith('{down}'):
                direction = 'down'
                clean = clean[6:]
            if clean.startswith('{mod}'):
                tier = 'mod'
                clean = clean[5:]
            elif clean.startswith('{watch}'):
                tier = 'watch'
                clean = clean[7:]

            # Only highlight if there's an actual direction marker
            if not direction:
                continue

            if tier:
                css_class = f'highlight-{tier}-{direction}'
            else:
                css_class = f'highlight-{direction}'

            # Replace or add the class on the row itself. Cells commonly
            # already carry alignment classes; searching the whole row for
            # the first class attribute would colour that cell instead.
            def set_row_class(opening_match):
                attributes = opening_match.group(1)
                if re.search(r'\bclass="[^"]*"', attributes):
                    attributes = re.sub(
                        r'\bclass="[^"]*"',
                        f'class="{css_class}"',
                        attributes,
                        count=1,
                    )
                else:
                    attributes += f' class="{css_class}"'
                return f'<tr{attributes}>'

            new_row = re.sub(
                r'^<tr([^>]*)>', set_row_class, row, count=1,
            )

            # Replace bold content with cleaned version
            new_row = new_row.replace(f"<strong>{inner}</strong>", clean, 1)
            return new_row

        return row

    return re.sub(r"<tr[^>]*>.*?</tr>", process_row, table_html, flags=re.DOTALL)


# =============================================================================
# RESULT / RISK COLORING
# =============================================================================

def colour_results(html):
    """Add colour to W/L/D result cells in round results and section tables.

    Win (W +N) -> green, Loss (L -N) -> red, Draw (D) -> grey.
    Targets td cells containing result patterns. Preserves existing bold/strong.
    """
    def colour_cell(match):
        td = match.group(0)
        inner = match.group(1)
        clean = _strip_tags(inner).strip()

        if clean.startswith('W ') or clean == 'W':
            cls = 'result-win'
        elif clean.startswith('L ') or clean == 'L':
            cls = 'result-loss'
        elif clean == 'D':
            cls = 'result-draw'
        else:
            return td

        coloured = f'<span class="{cls}">{inner}</span>'
        return td.replace(inner, coloured, 1)

    return re.sub(
        r'<td[^>]*>((?:<strong>)?[WLD](?:\s*[+-]?\d+)?(?:</strong>)?)</td>',
        colour_cell, html
    )


def colour_risk_cells(html, risk_tables=None):
    """Add background colour to risk percentage cells in specified tables.

    Scans <td> cells in each data row of matching tables and applies:
    - risk-high (>=50%) — red tint
    - risk-med (25-49%) — amber tint
    - risk-low (<25%) — green tint

    Args:
        risk_tables: List of table specs. Each entry is either:
            - a string CSS class name (back-compat; scans the last column only)
            - a dict ``{class: str, columns: 'last' | 'all'}`` — 'last' is the
              default and matches the back-compat behaviour; 'all' scans every
              <td> in the row (use for tables where every numeric column is a
              risk percentage, e.g. promotion-risk-by-age-and-boundary tables).
            When None or empty, this function is a no-op.
    """
    if not risk_tables:
        return html

    # Normalise into {class_name: columns_mode}. Unknown modes fall back to 'last'.
    specs: dict[str, str] = {}
    for entry in risk_tables:
        if isinstance(entry, str):
            specs[entry] = 'last'
        elif isinstance(entry, dict):
            cls = entry.get('class')
            if not cls:
                continue
            mode = entry.get('columns', 'last')
            specs[cls] = mode if mode in ('last', 'all') else 'last'

    if not specs:
        return html

    def _risk_class(content: str) -> str | None:
        pct_match = re.match(r'(\d+)%', content.strip())
        if not pct_match:
            return None
        pct = int(pct_match.group(1))
        if pct >= 50:
            return 'risk-high'
        if pct >= 25:
            return 'risk-med'
        return 'risk-low'

    def process_table(match):
        table_html = match.group(0)
        cols_mode = next(
            (mode for cls, mode in specs.items() if f'class="{cls}"' in table_html),
            None,
        )
        if cols_mode is None:
            return table_html

        def colour_row(row_match):
            row = row_match.group(0)
            if '<th' in row:
                return row
            cells = list(re.finditer(r'<td[^>]*>(.*?)</td>', row, re.DOTALL))
            if not cells:
                return row

            targets = cells if cols_mode == 'all' else [cells[-1]]
            # Splice from right to left so earlier offsets stay valid.
            result = row
            for cell in reversed(targets):
                cls = _risk_class(cell.group(1))
                if not cls:
                    continue
                old_td = cell.group(0)
                new_td = old_td.replace('<td', f'<td class="{cls}"', 1)
                result = result[:cell.start()] + new_td + result[cell.end():]
            return result

        return re.sub(r'<tr[^>]*>.*?</tr>', colour_row, table_html, flags=re.DOTALL)

    return re.sub(r'<table[^>]*>.*?</table>', process_table, html, flags=re.DOTALL)


# =============================================================================
# FRONT-MATTER-DRIVEN TABLE LAYOUTS
# =============================================================================

def _extract_headers(table_html):
    """Extract header cell texts from a table's <thead> or first <tr>."""
    thead = re.search(r"<thead>(.*?)</thead>", table_html, re.DOTALL)
    search_area = thead.group(1) if thead else table_html
    headers = re.findall(r"<th[^>]*>(.*?)</th>", search_area, re.DOTALL)
    return [_strip_tags(h).strip() for h in headers]


def _match_layout(header_texts, table_layouts):
    """Find a matching layout definition for a table's headers.

    Matches by column count and column names (case-insensitive, same order).
    Returns (layout_name, layout_dict) or (None, None).
    """
    if not table_layouts or not header_texts:
        return None, None

    normalised = [h.lower() for h in header_texts]
    for layout_name, layout in table_layouts.items():
        columns = layout.get('columns', [])
        if len(columns) != len(normalised):
            continue
        if all(c['name'].lower() == h for c, h in zip(columns, normalised)):
            return layout_name, layout

    return None, None


def _build_colgroup(columns):
    """Generate <colgroup> HTML from column definitions with normalised widths.

    Columns without an explicit ``width`` get their default from
    default_widths.yml based on header name. Final values are normalised
    so the colgroup widths sum to 100%.

    Includes CSS class names on <col> elements for per-column CSS targeting.
    """
    widths = [_column_width(c) for c in columns]
    total = sum(widths) or 1
    parts = ['<colgroup>']
    for c, w in zip(columns, widths):
        pct = round(w / total * 100, 1)
        cls = f'col-{c["name"].lower().replace(" ", "-")}'
        style = f'width:{pct}%'
        align = c.get('align', '')
        if align:
            style += f';text-align:{align}'
        parts.append(f'<col class="{cls}" style="{style}">')
    parts.append('</colgroup>')
    return ''.join(parts)


def _apply_column_alignment(table_html, columns):
    """Apply text-align styles to th and td cells based on column definitions."""
    aligns = [c.get('align', '') for c in columns]

    if not any(aligns):
        return table_html

    def align_cells(row_match):
        row_html = row_match.group(0)
        cell_idx = [0]

        def set_align(cell_match):
            tag_name = cell_match.group(1)
            existing_attrs = cell_match.group(2) or ''
            content = cell_match.group(3)
            idx = cell_idx[0]
            cell_idx[0] += 1

            if idx < len(aligns) and aligns[idx]:
                style = f'text-align:{aligns[idx]}'
                if 'style=' in existing_attrs:
                    existing_attrs = re.sub(
                        r'style="([^"]*)"',
                        f'style="\\1;{style}"',
                        existing_attrs
                    )
                else:
                    existing_attrs += f' style="{style}"'
                return f'<{tag_name}{existing_attrs}>{content}</{tag_name}>'
            return cell_match.group(0)

        cell_idx[0] = 0
        row_html = re.sub(r'<(t[dh])(\s[^>]*)?>(.+?)</\1>',
                          set_align, row_html, flags=re.DOTALL)
        return row_html

    return re.sub(r'<tr>.*?</tr>', align_cells, table_html, flags=re.DOTALL)


def apply_table_layouts(html, metadata):
    """Apply front-matter-driven layouts to all tables in the HTML.

    For each table:
    1. Extract headers and find matching layout
    2. Inject colgroup with declared widths
    3. Apply column alignment
    4. Add css_class to <table> tag if declared
    5. Apply highlight mode (controlled per-table via 'highlight' key):
       - 'row'       — full row highlight for tracked rows (default when
                        tracked_rows present; green/blue depending on CSS)
       - 'bold-only' — keep bold cell content, no row-level class
       - 'none'      — no highlighting at all, strip bold from matched cells
       Omitting 'highlight' uses 'row' if tracked_rows exists, else skips.
    6. Scan for {up}/{down}/{mod} direction markers (when direction_markers set)
    """
    from .render import _tracked_rows
    table_layouts = metadata.get('tables', {})
    tracked_rows = _tracked_rows(metadata)

    def process_table(match):
        table_html = match.group(0)

        # Skip tables with section rows (training doc format)
        if 'class="table-section"' in table_html:
            return table_html

        headers = _extract_headers(table_html)
        _name, layout = _match_layout(headers, table_layouts)

        highlight_mode = None
        if layout:
            columns = layout.get('columns', [])

            # Inject colgroup
            colgroup = _build_colgroup(columns)
            table_html = table_html.replace('<table>', f'<table>\n{colgroup}', 1)

            # Apply alignment
            table_html = _apply_column_alignment(table_html, columns)

            # Add CSS class to table if declared
            css_class = layout.get('css_class')
            if css_class:
                table_html = table_html.replace(
                    '<table>', f'<table class="{css_class}">', 1)

            # Per-table highlight mode
            highlight_mode = layout.get('highlight')

        # Direction-marker highlighting (opt-in via metadata)
        if metadata.get('direction_markers'):
            table_html = _highlight_direction_rows(table_html)

        # Apply highlight mode
        if highlight_mode == 'none':
            # Strip bold from team names, no row classes
            pass
        elif highlight_mode == 'bold-only':
            # Keep bold as-is, don't add row-level highlight classes
            pass
        elif tracked_rows:
            # Default: row-level highlighting when tracked_rows present
            table_html = _highlight_tracked_rows(table_html, tracked_rows)

        return table_html

    return re.sub(
        r'<table(?:\s[^>]*)?>.*?</table>',
        process_table,
        html,
        flags=re.DOTALL,
    )


# =============================================================================
# TABLE OF CONTENTS
# =============================================================================

def generate_toc(html, max_depth=3):
    """Generate a table of contents from headings in the HTML.

    Scans for h1-h{max_depth} elements and builds a nested list with
    internal links. Headings get id attributes added for linking.

    Args:
        html: HTML string to scan for headings.
        max_depth: Maximum heading level to include (default 3).

    Returns:
        (toc_html, modified_html) — the TOC block and the HTML with
        id attributes added to headings.
    """
    heading_pat = re.compile(
        r'<(h([1-6]))[^>]*>(.*?)</\1>', re.DOTALL
    )
    headings = []
    for match in heading_pat.finditer(html):
        level = int(match.group(2))
        if level > max_depth:
            continue
        text = re.sub(r'<[^>]+>', '', match.group(3)).strip()
        headings.append((level, text, match))

    if not headings:
        return '', html

    # Add id attributes to headings and build TOC entries
    used_ids = set()
    toc_entries = []
    modified = html

    # Process in reverse so string offsets stay valid
    for level, text, match in reversed(headings):
        slug = re.sub(r'[^\w\s-]', '', text.lower())
        slug = re.sub(r'[\s]+', '-', slug).strip('-')
        if not slug:
            slug = 'section'
        base_slug = slug
        counter = 1
        while slug in used_ids:
            slug = f'{base_slug}-{counter}'
            counter += 1
        used_ids.add(slug)

        # Replace heading tag with one that has an id
        old_tag = match.group(0)
        tag_name = match.group(1)
        inner = match.group(3)
        new_tag = f'<{tag_name} id="{slug}">{inner}</{tag_name}>'
        modified = modified[:match.start()] + new_tag + modified[match.end():]

        toc_entries.append((level, text, slug))

    toc_entries.reverse()

    # Build nested list
    min_level = min(e[0] for e in toc_entries)
    lines = ['<nav class="toc">', '<p class="toc-title">Contents</p>']
    lines.append('<ul>')
    prev_level = min_level
    for level, text, slug in toc_entries:
        if level > prev_level:
            for _ in range(level - prev_level):
                lines.append('<ul>')
        elif level < prev_level:
            for _ in range(prev_level - level):
                lines.append('</ul></li>')
        else:
            if lines[-1] != '<ul>':
                lines.append('</li>')
        lines.append(f'<li><a href="#{slug}">{text}</a>')
        prev_level = level
    # Close remaining open tags
    for _ in range(prev_level - min_level):
        lines.append('</li></ul>')
    lines.append('</li></ul>')
    lines.append('</nav>')

    return '\n'.join(lines), modified
