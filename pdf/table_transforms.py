"""Table-related HTML transforms for markdown-to-PDF conversion.

Alignment, highlighting, layout, coloring, section-row detection, and TOC
generation. All transforms operate on HTML strings using regex.
"""

import math
import os
import re
from dataclasses import dataclass
from decimal import Decimal, ROUND_DOWN

import yaml

from pdf.width_metadata import KNOWN_COLUMN_TYPES, normalise_width_metadata


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


def _normalise_header(text):
    """Normalise a header for registry lookup: strip tags, collapse whitespace,
    lowercase. Keeps ``Team``, ``team``, and ``Team `` interchangeable.

    Self-contained (no _strip_tags) so it is safe to call at module load from
    _load_default_widths, before the helpers section is defined.
    """
    text = re.sub(r'<[^>]+>', '', str(text))
    return re.sub(r'\s+', ' ', text).strip().lower()


def _load_default_widths():
    if not os.path.exists(_DEFAULT_WIDTHS_PATH):
        return {'fallback': 15, 'fallback_numeric': 8, 'widths': {}}
    with open(_DEFAULT_WIDTHS_PATH, 'r', encoding='utf-8') as f:
        loaded = yaml.safe_load(f) or {}
    return {
        'fallback': loaded.get('fallback', 15),
        # Narrower default for unknown columns whose content is numeric/short.
        'fallback_numeric': loaded.get('fallback_numeric', 8),
        # Normalised keys for case-insensitive, whitespace-tolerant lookup.
        'widths': {_normalise_header(k): v
                   for k, v in (loaded.get('widths') or {}).items()},
    }


_DEFAULT_WIDTHS = _load_default_widths()


def _column_width(col):
    """Resolve a column's width: explicit width first, then defaults by name."""
    if 'width' in col:
        return col['width']
    name = _normalise_header(col.get('name', ''))
    return _DEFAULT_WIDTHS['widths'].get(name, _DEFAULT_WIDTHS['fallback'])


# =============================================================================
# HELPERS
# =============================================================================

def _strip_tags(text):
    """Remove HTML tags to get plain text content."""
    return re.sub(r"<[^>]+>", "", text).strip()


def _add_class_token(tag, token):
    """Add one class token to an opening tag without duplicating it."""
    class_attr = re.search(r'(\bclass\s*=\s*)(["\'])(.*?)\2', tag,
                           flags=re.DOTALL)
    if class_attr:
        tokens = class_attr.group(3).split()
        if token in tokens:
            return tag
        value = ' '.join([token, *tokens])
        start, end = class_attr.span(3)
        return tag[:start] + value + tag[end:]
    return tag[:-1] + f' class="{token}">'


def _has_class_token(tag, token):
    """Return whether an opening tag's class list contains one token."""
    class_attr = re.search(r'(\bclass\s*=\s*)(["\'])(.*?)\2', tag,
                           flags=re.DOTALL)
    return bool(class_attr and token in class_attr.group(3).split())


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


# Content-type detectors used by the column classifier. Each answers "could
# this single cell be of type X?"; a column is typed X when all its non-empty
# cells qualify. Kept narrow so a column only lands on a specialised type when
# the whole column really is that type.

_PCT_RE = re.compile(r"^[+-]?\d+(?:\.\d+)?\s*%$")
_TIME_RE = re.compile(r"^\d{1,2}:\d{2}(?:\s*[ap]\.?m\.?)?$", re.IGNORECASE)
_SCORE_RE = re.compile(
    r"^[WLD]?\s*[+\-−]?\d+\s*[-–—]\s*[+\-−]?\d+$"  # 45-38, 45–38
    r"|^\d+-\d+-\d+$"                                                  # 5-3-0 records
    r"|^\d+W-\d+L(?:-\d+D)?$"                                     # 0W-2L-1D records
    r"|^[WL]\s*[+\-−]\s*\d+$",                                    # W +5 / L -10
    re.IGNORECASE,
)
_MONTHS = (r"jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec")
_WEEKDAYS = (r"mon|tue|tues|wed|thu|thur|thurs|fri|sat|sun")
_DATE_RE = re.compile(
    rf"^\d{{4}}-\d{{2}}-\d{{2}}$"                       # ISO 2024-05-01
    rf"|^\d{{1,2}}\s+(?:{_MONTHS})[a-z]*$"              # 14 Jun
    rf"|^(?:{_MONTHS})[a-z]*\s+\d{{1,2}}$"              # Jun 14
    rf"|^(?:{_WEEKDAYS})[a-z]*\s+\d{{1,2}}\s+(?:{_MONTHS})[a-z]*$"  # Saturday 14 June
    rf"|^\d{{1,2}}/\d{{1,2}}(?:/\d{{2,4}})?$",          # 5/14 or 5/14/25
    re.IGNORECASE,
)


def _is_percentage(text):
    return bool(_PCT_RE.match(_strip_tags(text).strip()))


def _is_time_like(text):
    return bool(_TIME_RE.match(_strip_tags(text).strip()))


def _is_score_like(text):
    return bool(_SCORE_RE.match(_strip_tags(text).strip()))


def _is_date_like(text):
    return bool(_DATE_RE.match(_strip_tags(text).strip()))


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
        cells = re.findall(r"<td[^>]*>(.*?)</td>", row, flags=re.DOTALL)
        if len(cells) >= 2:
            non_empty = [c.strip() for c in cells if c.strip()]
            if len(non_empty) == 1 and cells[0].strip():
                opening = re.match(r'<tr\b[^>]*>', row)
                new_opening = _add_class_token(
                    opening.group(0), 'table-section'
                )
                return new_opening + row[opening.end():]
        return row

    return re.sub(r"<tr\b[^>]*>.*?</tr>", process_row, html,
                  flags=re.DOTALL)


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
                    return _add_class_token(td_match.group(0), cls)
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
            # [^<] so a cell with two bold runs ("<strong>A</strong> vs
            # <strong>B</strong>") isn't greedily matched as one, which would
            # ship unbalanced tags.
            m = re.match(r"^<strong>([^<]+)</strong>$", stripped)
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
            m = re.match(r"^<strong>([^<]+)</strong>$", stripped)
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

            # Replace or add class on the <tr> open tag specifically — a
            # blanket first-class substitution could land on a <td>'s class.
            tr_open = re.match(r'<tr\b[^>]*>', row)
            open_tag = tr_open.group(0)
            if 'class="' in open_tag:
                new_open = re.sub(r'class="[^"]*"', f'class="{css_class}"',
                                  open_tag, count=1)
            else:
                new_open = open_tag[:-1] + f' class="{css_class}">'
            new_row = new_open + row[tr_open.end():]

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

    Win (W, W +N, "Forfeit win") -> green;
    Loss (L, L -N, "Forfeit loss") -> red;
    Draw (D) -> grey;
    "Bye"/"Abandoned" -> grey (neutral).
    Targets td cells containing result patterns. Preserves existing bold/strong.
    """
    def colour_cell(match):
        td = match.group(0)
        inner = match.group(1)
        clean = _strip_tags(inner).strip()
        clean_lower = clean.lower()

        if clean.startswith('W ') or clean in ('W', 'FW') or clean_lower == 'forfeit win':
            cls = 'result-win'
        elif clean.startswith('L ') or clean in ('L', 'FL') or clean_lower == 'forfeit loss':
            cls = 'result-loss'
        elif clean == 'D':
            cls = 'result-draw'
        elif clean_lower == 'bye':
            cls = 'result-bye'
        elif clean in ('ABN',) or clean_lower == 'abandoned':
            cls = 'result-abandoned'
        else:
            return td

        coloured = f'<span class="{cls}">{inner}</span>'
        return td.replace(inner, coloured, 1)

    # Accept ASCII hyphen-minus and en-dash (U+2013) for the sign — callers
    # may use either; e.g. "L -10" or "L –10".
    return re.sub(
        r'<td[^>]*>((?:<strong>)?(?:'
        r'[WLD](?:\s*[+\-–]?\d+)?'
        r'|FW|FL|ABN'
        r'|Forfeit\s+win|Forfeit\s+loss|Bye|Abandoned'
        r')(?:</strong>)?)</td>',
        colour_cell, html, flags=re.IGNORECASE
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
        pct_match = re.match(r'(\d+(?:\.\d+)?)\s*%', content.strip())
        if not pct_match:
            return None
        pct = float(pct_match.group(1))
        if pct >= 50:
            return 'risk-high'
        if pct >= 25:
            return 'risk-med'
        return 'risk-low'

    def process_table(match):
        table_html = match.group(0)
        table_opening = re.match(r'<table\b[^>]*>', table_html)
        cols_mode = next(
            (mode for cls, mode in specs.items()
             if _has_class_token(table_opening.group(0), cls)),
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
                # Merge into any existing class (cells are already class="num"
                # from auto-alignment) rather than emitting a second attribute.
                new_td = re.sub(
                    r'<td\b[^>]*>',
                    lambda m: _add_class_token(m.group(0), cls),
                    old_td,
                    count=1,
                )
                result = result[:cell.start()] + new_td + result[cell.end():]
            return result

        return re.sub(r'<tr[^>]*>.*?</tr>', colour_row, table_html, flags=re.DOTALL)

    return re.sub(r'<table[^>]*>.*?</table>', process_table, html, flags=re.DOTALL)


# =============================================================================
# FRONT-MATTER-DRIVEN TABLE LAYOUTS
# =============================================================================

def _extract_headers(table_html):
    """Extract header cell texts from a table's <thead> or first <tr>."""
    thead = re.search(r"<thead\b[^>]*>(.*?)</thead\s*>", table_html,
                      flags=re.DOTALL | re.IGNORECASE)
    search_area = thead.group(1) if thead else table_html
    first_row = re.search(r"<tr\b[^>]*>(.*?)</tr\s*>", search_area,
                          flags=re.DOTALL | re.IGNORECASE)
    if first_row:
        search_area = first_row.group(1)
    headers = re.findall(r"<th\b[^>]*>(.*?)</th\s*>", search_area,
                         flags=re.DOTALL | re.IGNORECASE)
    return [_strip_tags(h).strip() for h in headers]


def _insert_colgroup(table_html, colgroup):
    """Insert a generated colgroup without displacing a leading caption."""
    opening = re.search(r'<table\b[^>]*>', table_html, flags=re.IGNORECASE)
    if not opening:
        return table_html

    insertion = opening.end()
    after_opening = table_html[insertion:]
    caption = re.match(r'\s*<caption\b[^>]*>.*?</caption\s*>', after_opening,
                       flags=re.DOTALL | re.IGNORECASE)
    if caption:
        insertion += caption.end()
    return table_html[:insertion] + '\n' + colgroup + table_html[insertion:]


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
        if all(c.get('name', '').lower() == h for c, h in zip(columns, normalised)):
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
        # (.*?) not (.+?): empty cells (<td></td>, or markdown's alignment-
        # styled empties) must still be counted, else the column index desyncs
        # and every cell after an empty one gets the wrong column's alignment.
        row_html = re.sub(r'<(t[dh])(\s[^>]*)?>(.*?)</\1>',
                          set_align, row_html, flags=re.DOTALL)
        return row_html

    return re.sub(r'<tr[^>]*>.*?</tr>', align_cells, table_html, flags=re.DOTALL)


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

        structure = _analyze_table_structure(table_html)
        headers = list(structure.headers)
        _name, layout = _match_layout(headers, table_layouts)

        highlight_mode = None
        if layout and structure.eligible:
            columns = layout.get('columns', [])

            # Preserve a semantic first-child caption when inserting widths.
            colgroup = _build_colgroup(columns)
            table_html = _insert_colgroup(table_html, colgroup)

            # Apply alignment
            table_html = _apply_column_alignment(table_html, columns)

            # Add CSS class to table if declared, merging with any existing one.
            css_class = layout.get('css_class')
            if css_class and not isinstance(css_class, str):
                _log.warning(
                    "table layout %s: css_class must be a string; skipping",
                    _name,
                )
            elif css_class and css_class.strip():
                css_class = css_class.strip()

                def _add_table_class(m):
                    return _add_class_token(m.group(0), css_class)
                table_html = re.sub(r'<table\b[^>]*>', _add_table_class,
                                    table_html, count=1)

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

    return re.sub(r'<table\b[^>]*>.*?</table>', process_table, html, flags=re.DOTALL)


# =============================================================================
# DEFAULT TABLE WIDTHS (applied to every table, not just declared layouts)
# =============================================================================

import logging as _logging

_log = _logging.getLogger(__name__)


def _validated_width_metadata(metadata):
    """Normalize direct-call metadata and emit each resulting warning."""
    normalized, warnings = normalise_width_metadata(
        {} if metadata is None else metadata
    )
    for warning in warnings:
        _log.warning("%s", warning)
    return normalized


def _table_body_rows(table_html):
    """Return the body rows of a table as lists of cell-HTML strings.

    Skips header rows. Used to infer a column's type from its content.
    """
    bodies = re.findall(r'<tbody\b[^>]*>(.*?)</tbody\s*>', table_html,
                        flags=re.DOTALL | re.IGNORECASE)
    areas = bodies or [table_html]
    rows = []
    for area in areas:
        for row in re.findall(r'<tr\b[^>]*>(.*?)</tr\s*>', area,
                              flags=re.DOTALL | re.IGNORECASE):
            if re.search(r'<th\b', row, flags=re.IGNORECASE):
                continue
            rows.append(re.findall(r'<td\b[^>]*>(.*?)</td\s*>', row,
                                   flags=re.DOTALL | re.IGNORECASE))
    return rows


@dataclass(frozen=True)
class _TableStructure:
    """Semantic shape shared by declared and automatic width paths."""

    headers: tuple
    body_rows: tuple
    ineligible_reason: str | None = None

    @property
    def eligible(self):
        return self.ineligible_reason is None


def _analyze_table_structure(table_html):
    """Return a conservative one-column-per-header eligibility decision."""
    headers = tuple(_extract_headers(table_html))
    body_rows = tuple(tuple(row) for row in _table_body_rows(table_html))

    if re.search(r'<colgroup\b', table_html, flags=re.IGNORECASE):
        reason = 'existing-colgroup'
    elif not headers:
        reason = 'no-headers'
    elif not body_rows:
        reason = 'no-body-rows'
    elif re.search(r'<t[dh]\b[^>]*\b(?:colspan|rowspan)\b', table_html,
                   flags=re.IGNORECASE):
        reason = 'spanning-cells'
    elif any(len(row) != len(headers) for row in body_rows):
        reason = 'ragged-rows'
    else:
        reason = None

    return _TableStructure(headers, body_rows, reason)


# --- Typed-column width model -------------------------------------------------
#
# Every column is classified from its CONTENT into a semantic type; token types
# get an absolute width from a shared em ladder (so the same kind of column is
# the same width in every table and document), while flex types (names, prose)
# are left width-less to absorb the remainder. Widths resolve PER TYPE-GROUP, so
# e.g. GF/GA/Pts in a ladder all share one width. All the em numbers were
# measured against the bundled Minion Caption 9pt / Myriad 8.5pt fonts — see the
# `project_table_width_redesign` memory.

_CELL_OVERHEAD_EM = 1.16          # 2×0.55em padding + 0.06em border (border-box)
_SAFETY_EM = 0.3                  # comfort margin so content near a rung edge
                                  # (e.g. "9:00 AM" breaking at its space) gets
                                  # the next rung instead of wrapping
_HEADER_EM_SCALE = 8.5 / 9.0      # headers render at 8.5pt inside a 9pt table
_LADDER_EM = [2.5, 3.0, 3.5, 4.5, 5.5, 7.0, 9.0]   # → CSS classes w1..w7

# Token type → canonical rung (index into _LADDER_EM). idx is folded into stat
# (they share a rung, and the "Pos" header floor forces ≥3em anyway).
_TYPE_CANONICAL = {
    'stat': 1,   # w2 3.0em — W/L/D/GF/GA/Pts, ranks, ≤3-digit numbers
    'num': 2,    # w3 3.5em — 4-digit ints, signed 3-digit
    'time': 2,   # w3 3.5em — 0:30
    'pct': 3,    # w4 4.5em — 68%, 99.5%
    'score': 3,  # w4 4.5em — 45–38, 5-3-0, W +5
    'date': 3,   # w4 4.5em — 14 Jun (ISO bumps up via the cell floor)
    'label': 3,  # w4 4.5em — Sat / Home / Final (snaps up to fit)
}
_FLEX_TYPES = frozenset({'text', 'prose'})
_KNOWN_TYPES = KNOWN_COLUMN_TYPES
# Numeric tokens use the shared em ladder (consistent by type across the doc).
_LADDER_TYPES = frozenset(_TYPE_CANONICAL) - {'label'}
# "Wide" columns (short labels, names, prose) get a width that is shared per
# column identity across the whole document — see _column_identity.
_WIDE_TYPES = _FLEX_TYPES | {'label'}


def _char_em_body(ch):
    """Measured advance of one character in the 9pt Minion Caption cell font,
    as a fraction of font-size."""
    if ch.isdigit():
        return 0.487          # tabular figures — exact, no kerning
    if ch == ' ':
        return 0.241
    if ch in '.:':
        return 0.237
    if ch == '-':
        return 0.364
    if ch == '–':        # en dash (scores)
        return 0.521
    if ch == '−':        # minus (negative GD)
        return 0.599
    if ch == '%':
        return 0.786
    if ch == '/':
        return 0.337
    if ch.islower():
        return 0.466
    if ch.isupper():
        return 0.659
    return 0.55               # unknown glyph — mid estimate


def _text_em(text):
    """Estimated rendered width of a body-cell string, in table em."""
    return sum(_char_em_body(c) for c in text)


def _header_em(text):
    """Estimated rendered width of a header string, in table em. Headers are
    uppercased 8.5pt Myriad with letter-spacing (already in the advances)."""
    total = 0.0
    for c in text.upper():
        if c.isdigit():
            total += 0.566
        elif c.isalpha():
            total += 0.640
        elif c == ' ':
            total += 0.30
        else:
            total += 0.45
    return total * _HEADER_EM_SCALE


def _classify_column(header, cells):
    """Assign a semantic type to a column from its content (header is only a
    tie-break hint). All non-empty cells must qualify for a specialised type."""
    vals = [_strip_tags(c).strip() for c in cells]
    vals = [v for v in vals if v]
    hdr = _strip_tags(header).strip()

    if not vals:                       # empty column — guess from the header
        return 'label' if len(hdr) <= 12 else 'text'

    def every(fn):
        return all(fn(v) for v in vals)

    if every(_is_percentage) or (hdr.endswith('%') and every(_is_numeric)):
        return 'pct'
    if every(_is_time_like):
        return 'time'
    if every(_is_date_like):
        return 'date'
    if every(_is_score_like):
        return 'score'
    if every(_is_numeric):
        # Count digits, not characters, so a signed/decimal 3-digit value
        # (+176, −293) stays `stat` and shares the ladder's stat group.
        max_digits = max(len(re.sub(r'\D', '', v)) for v in vals)
        return 'stat' if max_digits <= 3 else 'num'
    if all(len(v) <= 2 for v in vals):
        # 1-2 char result/side codes: W/L, H/A, ✓. Longer alphanumeric codes
        # (15U, ABN, Mon) are labels, not stats — keeping them out of the
        # numeric stat group stops their wider headers dragging it.
        return 'stat'

    maxlen = max(len(v) for v in vals)
    maxwords = max(len(v.split()) for v in vals)
    if maxlen <= 12 and maxwords <= 2:
        return 'label'
    if maxlen > 40 or maxwords > 6:
        return 'prose'
    return 'text'


def _snap_up_rung(target_em):
    """Smallest ladder rung index whose width covers target_em; clamps to the
    widest rung (token content then wraps inside via overflow-wrap)."""
    for i, rung in enumerate(_LADDER_EM):
        if target_em <= rung + 1e-9:
            return i
    return len(_LADDER_EM) - 1


# --- Wide-column widths (document-level grouping) -----------------------------

import functools

# Content width in 9pt-table em for A4 with the bundled 18mm side margins:
# portrait 210mm−36mm = 174mm ≈ 54.8em; landscape 297mm−36mm = 261mm ≈ 82.2em.
# A table whose fixed columns exceed the page width is scaled down to fit.
_PAGE_CONTENT_EM = 54.8
_PAGE_CONTENT_EM_LANDSCAPE = 82.2


def _page_content_em(metadata):
    """Usable content width (em) for the overflow guard, from front matter.

    ``page_width_em`` overrides everything; otherwise ``orientation: landscape``
    selects the wider A4 landscape width. Defaults to A4 portrait."""
    metadata = metadata or {}
    override = metadata.get('page_width_em')
    if isinstance(override, (int, float)) and override > 0:
        return float(override)
    if str(metadata.get('orientation', '')).lower() == 'landscape':
        return _PAGE_CONTENT_EM_LANDSCAPE
    return _PAGE_CONTENT_EM
# Headers naming a team/entity share one "@team" identity, so Team, Home and
# Away all get a single width across the whole document.
_NAME_HINTS = frozenset({'team', 'home', 'away', 'opponent', 'club', 'name',
                         'player'})
_BODY_FONT_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), 'fonts', 'MinionPro-Capt.otf')
_HEADER_FONT_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), 'fonts', 'MyriadPro-Semibold.otf')


@functools.lru_cache(maxsize=None)
def _glyph_advances(font_path):
    """char -> advance width (em) from a bundled OTF, or None if unavailable."""
    try:
        from fontTools.ttLib import TTFont
        if not os.path.exists(font_path):
            return None
        font = TTFont(font_path)
        upm = font['head'].unitsPerEm
        hmtx = font['hmtx']
        return {chr(code): hmtx[g][0] / upm
                for code, g in font.getBestCmap().items()}
    except Exception:
        return None


def _measure_em(text, header=False):
    """Rendered width of a string in table em, from the real bundled-font glyph
    advances (falls back to the per-class averages if fontTools/the font is
    unavailable). More accurate than the averages for proportional names, which
    matters for flex caps — under fixed layout a too-tight cap wraps."""
    adv = _glyph_advances(_HEADER_FONT_PATH if header else _BODY_FONT_PATH)
    if adv is None:
        return _header_em(text) if header else _text_em(text)
    src = text.upper() if header else text
    fallback = 0.6 if header else 0.5
    total = sum(adv.get(c, fallback) for c in src)
    if header:                    # header is 8.5pt in a 9pt table + 0.03em tracking
        total = (total + 0.03 * len(src)) * _HEADER_EM_SCALE
    return total


def _flex_natural_em(header, cells):
    """Width a wide column needs to hold its widest cell/header without wrapping."""
    widest = max((_measure_em(c) for c in cells), default=0.0)
    return max(widest, _measure_em(header, header=True)) \
        + _CELL_OVERHEAD_EM + _SAFETY_EM


def _column_identity(header):
    """Document-level grouping key for a wide column. All team/entity headers
    share one identity so Team/Home/Away get a single width across the document;
    everything else is keyed by its normalised header (so every "Division"
    column matches, etc.)."""
    norm = _normalise_header(header)
    if set(norm.split()) & _NAME_HINTS:
        return '\x00team'
    return norm


def _analyze_table_for_widths(table_html, overrides):
    """First pass: classify a table's columns and compute the widths it needs.

    Returns a dict (headers, types, explicit, group_rung, nat) or None if the
    table should be left alone (already has a colgroup, has no header/body data,
    or has a spanning/ragged shape a fixed colgroup would misrender). Explicit
    widths are stored as numeric em values; callers must pass normalized
    overrides."""
    structure = _analyze_table_structure(table_html)
    if not structure.eligible:
        return None
    headers = list(structure.headers)
    body_rows = [list(row) for row in structure.body_rows]

    # Type each column (respecting overrides).
    types = []
    explicit = {}
    for i, header in enumerate(headers):
        ov = overrides.get(_normalise_header(header))
        if ov is not None:
            if isinstance(ov, str) and ov.lower() in _KNOWN_TYPES:
                types.append(ov.lower())
                continue
            explicit[i] = float(ov[:-2]) if isinstance(ov, str) else float(ov)
            types.append('_explicit')
            continue
        col_cells = [row[i] for row in body_rows if i < len(row)]
        types.append(_classify_column(header, col_cells))

    # Numeric-token columns → one shared ladder rung per type (header-floored).
    col_floor = []
    for i, header in enumerate(headers):
        cells = [_strip_tags(row[i]).strip() for row in body_rows if i < len(row)]
        widest = max((_text_em(c) for c in cells), default=0.0)
        col_floor.append(
            max(widest, _header_em(header)) + _CELL_OVERHEAD_EM + _SAFETY_EM)
    group_rung = {}
    for t in set(types):
        if t not in _LADDER_TYPES:
            continue
        canonical = _LADDER_EM[_TYPE_CANONICAL[t]]
        group_floor = max(col_floor[i] for i, tt in enumerate(types) if tt == t)
        group_rung[t] = _snap_up_rung(max(canonical, group_floor))

    # Wide columns (label/text/prose) → the natural width they need.
    nat = {}
    for i, t in enumerate(types):
        if t in _WIDE_TYPES:
            cells = [c for c in (_strip_tags(row[i]).strip()
                                 for row in body_rows if i < len(row)) if c]
            nat[i] = _flex_natural_em(headers[i], cells)

    return {'headers': headers, 'types': types, 'explicit': explicit,
            'group_rung': group_rung, 'nat': nat}


@dataclass(frozen=True)
class _TableFitResult:
    """Pure fitting outcome consumed by HTML emission and diagnostics."""

    explicit_em: dict
    wide_em: dict
    natural_total_em: float
    emitted_total_em: float
    outcome: str


_WIDE_EM_QUANTUM = Decimal('0.01')


def _wide_em_for_css(value, *, round_down=False):
    """Return the exact numeric value emitted by the two-decimal CSS format."""
    if round_down:
        return float(Decimal(str(value)).quantize(
            _WIDE_EM_QUANTUM, rounding=ROUND_DOWN
        ))
    return float(f'{value:.2f}')


def _explicit_em_for_css(value):
    """Return a shortest CSS number that round-trips to the fitted float."""
    text = repr(float(value))
    return text[:-2] if text.endswith('.0') else text


def _width_sum(values):
    """Sum positive em values, treating an unrepresentable total as infinity."""
    try:
        return math.fsum(values)
    except OverflowError:
        return math.inf


def _scale_wide_em(wide_em, fixed_em, natural_total, page_em):
    """Reduce automatic wide columns and quantize to their emitted precision."""
    wide_total = _width_sum(wide_em.values())
    deficit = natural_total - page_em
    w_min = min(wide_em.values())
    excess = _width_sum(width - w_min for width in wide_em.values())
    if excess > deficit:
        for i in wide_em:
            wide_em[i] -= deficit * (wide_em[i] - w_min) / excess
    else:
        factor = (
            max((page_em - fixed_em) / wide_total, 0.0)
            if fixed_em <= page_em else 0.1
        )
        for i in wide_em:
            wide_em[i] *= factor
    return {
        i: _wide_em_for_css(width, round_down=True)
        for i, width in wide_em.items()
    }


def _fit_table_widths(analysis, identity_width, page_em):
    """Calculate exact em widths and classify the table fitting outcome."""
    explicit_em = dict(analysis['explicit'])
    wide_em = {
        i: _wide_em_for_css(identity_width.get(
            _column_identity(analysis['headers'][i]), analysis['nat'][i]
        ))
        for i, t in enumerate(analysis['types']) if t in _WIDE_TYPES
    }
    fixed_em = _width_sum([
        *explicit_em.values(),
        *(
            _LADDER_EM[analysis['group_rung'][t]]
            for t in analysis['types']
            if t not in _WIDE_TYPES and t != '_explicit'
        ),
    ])
    natural_total = _width_sum((fixed_em, *wide_em.values()))
    if natural_total > page_em and wide_em:
        wide_em = _scale_wide_em(wide_em, fixed_em, natural_total, page_em)
    emitted_total = _width_sum((fixed_em, *wide_em.values()))
    outcome = (
        'fit' if natural_total <= page_em else
        'scaled' if emitted_total <= page_em else
        'unresolved_overflow'
    )

    return _TableFitResult(
        explicit_em=explicit_em,
        wide_em=wide_em,
        natural_total_em=natural_total,
        emitted_total_em=emitted_total,
        outcome=outcome,
    )


def _emit_table_widths(table_html, a, identity_width, page_em):
    """Second pass: inject the colgroup. Numeric columns take their ladder rung;
    wide columns take their identity's document-wide width (so the same kind of
    column is the same width in every table).

    If the fixed columns fit ``page_em``, the table shrinks to fit (never
    stretches one column). If they overflow (e.g. two long team columns at the
    doc-wide width), the wide columns are scaled down just enough to fit — the
    only case the shared width is not honoured exactly, in exchange for the
    table staying on the page. Returns ``(html, fit_result)``."""
    fit = _fit_table_widths(a, identity_width, page_em)

    cols = []
    for i, t in enumerate(a['types']):
        if t == '_explicit':
            cols.append(
                f'<col style="width:{_explicit_em_for_css(fit.explicit_em[i])}em">'
            )
        elif t in _WIDE_TYPES:
            cols.append(f'<col style="width:{fit.wide_em[i]:.2f}em">')
        else:
            cols.append(f'<col class="w{a["group_rung"][t] + 1}">')
    colgroup = '<colgroup>' + ''.join(cols) + '</colgroup>'

    result = _insert_colgroup(table_html, colgroup)

    if fit.outcome == 'fit':    # shrink to content (don't stretch to 100%)
        def _add_fit(m):
            return _add_class_token(m.group(0), 'fit')
        result = re.sub(r'<table\b[^>]*>', _add_fit, result, count=1)
    return result, fit


def apply_default_table_widths(html, metadata=None):
    """Give every colgroup-less table typed, document-consistent column widths.

    Runs after ``apply_table_layouts``: any table that already carries a
    ``<colgroup>`` (a declared layout matched, or the author supplied one) is
    left untouched, so declared layouts stay the override layer.

    Two passes over the document's tables:
      1. Classify each column. Numeric columns get a shared em-ladder width by
         type. "Wide" columns (short labels, names, prose) get the width they
         need, keyed by a document-level *identity* (all team/Home/Away columns
         share one; every "Division" column shares one; etc.).
      2. Emit each colgroup using the widest width seen for each identity across
         the whole document, so the same kind of column is the same width in
         every table — a schedule's Home/Away, a summary's Team, and a ladder's
         Team all line up. Every column is fixed, so a table sizes to its
         content instead of stretching one column to fill the page.

    Front matter:
      table_widths: false   — disable this pass for the document
      columns: {Header: type|width}
                            — force a column's type or pin an explicit width.
    """
    metadata = _validated_width_metadata(metadata)
    if metadata.get('table_widths') in (False, 'off', 'none', 'legacy'):
        return html

    raw_overrides = metadata.get('columns')
    if not isinstance(raw_overrides, dict):
        raw_overrides = {}
    overrides = {
        _normalise_header(k): v
        for k, v in raw_overrides.items()
    }
    page_em = _page_content_em(metadata)

    # Pass 1: analyse every table, accumulate the widest natural width per
    # document-level column identity.
    spans = []                 # (start, end, analysis-or-None)
    identity_width = {}
    for m in re.finditer(r'<table\b[^>]*>.*?</table>', html, flags=re.DOTALL):
        a = _analyze_table_for_widths(m.group(0), overrides)
        spans.append((m.start(), m.end(), a))
        if a is None:
            continue
        for i, w in a['nat'].items():
            ident = _column_identity(a['headers'][i])
            identity_width[ident] = max(identity_width.get(ident, 0.0), w)

    # Pass 2: rebuild the document, emitting each table's colgroup.
    out = []
    last = 0
    overwide = []
    for start, end, a in spans:
        out.append(html[last:start])
        table_html = html[start:end]
        if a is None:
            out.append(table_html)
        else:
            emitted, fit = _emit_table_widths(
                table_html, a, identity_width, page_em)
            out.append(emitted)
            if fit.natural_total_em > page_em:
                overwide.append(fit)
        last = end
    out.append(html[last:])

    # Report every overflow. Landscape advice applies only to the default
    # portrait budget; it is not actionable for landscape or custom budgets.
    is_landscape = str(metadata.get('orientation', '')).lower() == 'landscape'
    if overwide:
        unresolved = sum(
            fit.emitted_total_em > page_em for fit in overwide
        )
        outcome_note = (
            f"; fixed columns remain wider than the budget in {unresolved} "
            "table(s)" if unresolved else
            "; automatic wide columns were scaled to fit"
        )
        advice = ""
        if not is_landscape and 'page_width_em' not in metadata:
            advice = (
                "; consider 'orientation: landscape' in the front matter for "
                f"{max(len(a['types']) for _, _, a in spans if a)}-column tables"
            )
        _log.info(
            "%d table(s) are wider than the fitting budget (widest ~%.0fem "
            "vs %.0fem available)%s%s.",
            len(overwide),
            max(fit.natural_total_em for fit in overwide),
            page_em,
            outcome_note,
            advice,
        )

    return ''.join(out)


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
        r'<(h([1-6]))([^>]*)>(.*?)</\1>', re.DOTALL
    )
    headings = []
    for match in heading_pat.finditer(html):
        level = int(match.group(2))
        if level > max_depth:
            continue
        text = re.sub(r'<[^>]+>', '', match.group(4)).strip()
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

        # Replace heading tag with one that has an id, preserving any existing
        # attributes (e.g. the break-before style injected by no-page-break).
        tag_name = match.group(1)
        attrs = re.sub(r'\s*id="[^"]*"', '', match.group(3))
        inner = match.group(4)
        new_tag = f'<{tag_name} id="{slug}"{attrs}>{inner}</{tag_name}>'
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
