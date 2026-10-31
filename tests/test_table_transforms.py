"""Tests for table layout, column widths, alignment, and section detection."""

import re
from pathlib import Path

import pytest

from pdf.table_transforms import (
    _column_width,
    _classify_column,
    _DEFAULT_WIDTHS,
    _build_colgroup,
    _extract_headers,
    _highlight_direction_rows,
    _match_layout,
    align_table_columns,
    apply_default_table_widths,
    apply_table_layouts,
    colour_results,
    colour_risk_cells,
    detect_table_section_rows,
    generate_toc,
)


def _contract_table(headers, rows, table_attrs=""):
    """Build a compact semantic table for public width-contract assertions."""
    head = "".join(f"<th>{header}</th>" for header in headers)
    body = "".join(
        "<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>"
        for row in rows
    )
    attrs = f" {table_attrs}" if table_attrs else ""
    return (
        f"<table{attrs}><thead><tr>{head}</tr></thead>"
        f"<tbody>{body}</tbody></table>"
    )


def _contract_cols(html):
    """Return emitted col tags without exposing classifier implementation."""
    colgroup = re.search(r"<colgroup>(.*?)</colgroup>", html, re.DOTALL)
    assert colgroup, "expected automatic width markup"
    return re.findall(r"<col(?:\s[^>]*)?>", colgroup.group(1))


def test_toc_slug_unescapes_numeric_entities_before_normalising():
    toc, html = generate_toc(
        "<h2>Foundation, 1968&#45;1973</h2>", max_depth=2
    )

    assert 'id="foundation-1968-1973"' in html
    assert 'href="#foundation-1968-1973"' in toc
    assert "1968451973" not in html


class TestColumnWidth:
    """Resolution order: explicit width → registry lookup → fallback."""

    def test_explicit_width_wins(self):
        assert _column_width({'name': 'Day', 'width': 99}) == 99

    def test_registry_lookup_by_header_name(self):
        # 'Day' is in the default widths registry
        assert _column_width({'name': 'Day'}) == _DEFAULT_WIDTHS['widths']['day']

    def test_registry_lookup_is_case_insensitive(self):
        assert _column_width({'name': 'DAY'}) == _column_width({'name': 'day'})

    def test_unknown_header_uses_fallback(self):
        assert _column_width({'name': 'SomeNovelHeader'}) == _DEFAULT_WIDTHS['fallback']


class TestBuildColgroup:
    """Colgroup widths are normalised to percentages."""

    def test_widths_normalise_to_100_percent(self):
        cg = _build_colgroup([
            {'name': 'A', 'width': 10},
            {'name': 'B', 'width': 30},
            {'name': 'C', 'width': 60},
        ])
        # Each column gets width:X% in the style attribute
        # 10/100=10%, 30/100=30%, 60/100=60%
        assert 'width:10.0%' in cg
        assert 'width:30.0%' in cg
        assert 'width:60.0%' in cg

    def test_alignment_applied_when_set(self):
        cg = _build_colgroup([
            {'name': 'A', 'width': 50, 'align': 'right'},
            {'name': 'B', 'width': 50},
        ])
        assert 'text-align:right' in cg

    def test_per_column_css_class_added(self):
        cg = _build_colgroup([{'name': 'My Header', 'width': 100}])
        # Lowercased + spaces → hyphens
        assert 'class="col-my-header"' in cg


class TestExtractHeaders:

    def test_extracts_first_row_text(self):
        html = """
        <table>
        <thead><tr><th>Day</th><th>Session</th><th>Duration</th></tr></thead>
        <tbody><tr><td>Mon</td><td>Walk</td><td>30</td></tr></tbody>
        </table>
        """
        assert _extract_headers(html) == ['Day', 'Session', 'Duration']

    def test_extracts_normalised_repeated_headers_with_inline_markup(self):
        html = (
            '<table><thead data-kind="main"><tr>'
            '<th><span> Team </span></th><th>Team</th>'
            '</tr></thead><tbody><tr><td>A</td><td>B</td></tr></tbody></table>'
        )
        assert _extract_headers(html) == ['Team', 'Team']


class TestMatchLayout:

    def test_matches_by_header_names(self):
        layouts = {
            'schedule': {
                'columns': [{'name': 'Day'}, {'name': 'Session'}, {'name': 'Duration'}],
            },
        }
        name, layout = _match_layout(['Day', 'Session', 'Duration'], layouts)
        assert name == 'schedule'
        assert layout is layouts['schedule']

    def test_case_insensitive_match(self):
        layouts = {'x': {'columns': [{'name': 'Day'}, {'name': 'Session'}]}}
        name, _layout = _match_layout(['day', 'session'], layouts)
        assert name == 'x'

    def test_no_match_returns_none(self):
        layouts = {'x': {'columns': [{'name': 'A'}, {'name': 'B'}]}}
        name, layout = _match_layout(['Different', 'Headers'], layouts)
        assert name is None
        assert layout is None


class TestApplyTableLayouts:
    """The orchestrator that injects colgroup, alignment, and css_class."""

    def test_matching_table_gets_colgroup_injected(self):
        html = """
        <table>
        <thead><tr><th>Day</th><th>Session</th></tr></thead>
        <tbody><tr><td>Mon</td><td>Walk</td></tr></tbody>
        </table>
        """
        metadata = {
            'tables': {
                'schedule': {
                    'columns': [
                        {'name': 'Day', 'width': 30},
                        {'name': 'Session', 'width': 70},
                    ],
                },
            },
        }
        result = apply_table_layouts(html, metadata)
        assert '<colgroup>' in result
        assert 'width:30.0%' in result
        assert 'width:70.0%' in result

    def test_css_class_added_to_table(self):
        html = """
        <table>
        <thead><tr><th>Day</th><th>Session</th></tr></thead>
        <tbody><tr><td>Mon</td><td>Walk</td></tr></tbody>
        </table>
        """
        metadata = {
            'tables': {
                'schedule': {
                    'css_class': 'my-schedule',
                    'columns': [{'name': 'Day'}, {'name': 'Session'}],
                },
            },
        }
        result = apply_table_layouts(html, metadata)
        assert 'class="my-schedule"' in result

    def test_non_matching_table_left_alone(self):
        html = """
        <table>
        <thead><tr><th>Unmatched</th><th>Headers</th></tr></thead>
        <tbody><tr><td>x</td><td>y</td></tr></tbody>
        </table>
        """
        metadata = {
            'tables': {
                'schedule': {'columns': [{'name': 'Day'}, {'name': 'Session'}]},
            },
        }
        result = apply_table_layouts(html, metadata)
        assert '<colgroup>' not in result


class TestAlignTableColumns:
    """Numeric-only columns get auto-right-aligned."""

    def test_pure_numeric_column_gets_right_aligned(self):
        html = """
        <table>
        <thead><tr><th>Day</th><th>TSS</th></tr></thead>
        <tbody>
        <tr><td>Mon</td><td>30</td></tr>
        <tr><td>Tue</td><td>60</td></tr>
        </tbody>
        </table>
        """
        result = align_table_columns(html)
        # TSS column should be detected as numeric and right-aligned;
        # the Day column should NOT be
        assert 'class="num"' in result

    def test_mixed_text_column_not_aligned(self):
        html = """
        <table>
        <thead><tr><th>Day</th><th>Notes</th></tr></thead>
        <tbody>
        <tr><td>Mon</td><td>Easy walk</td></tr>
        <tr><td>Tue</td><td>Strength</td></tr>
        </tbody>
        </table>
        """
        result = align_table_columns(html)
        # No numeric cells → no num class
        assert 'class="num"' not in result


class TestDetectTableSectionRows:
    """Rows where only the first cell has content become section dividers."""

    def test_section_row_gets_class(self):
        # First cell has text, others empty → section divider
        html = """
        <table>
        <thead><tr><th>Division</th><th>Team</th><th>W</th></tr></thead>
        <tbody>
        <tr><td>9U</td><td></td><td></td></tr>
        <tr><td>9U Red</td><td>Bilbies</td><td>8</td></tr>
        </tbody>
        </table>
        """
        result = detect_table_section_rows(html)
        assert 'class="table-section"' in result


class TestColourRiskCells:
    """Risk percentage cell colouring: last-column (default) and all-cell modes."""

    LAST_COL_TABLE = (
        '<table class="swap-summary">'
        '<thead><tr><th>Team</th><th>Risk</th></tr></thead>'
        '<tbody>'
        '<tr><td>Kangaroos</td><td>18%</td></tr>'
        '<tr><td>Wallabies</td><td>32%</td></tr>'
        '<tr><td>Possums</td><td>67%</td></tr>'
        '</tbody></table>'
    )

    ALL_CELLS_TABLE = (
        '<table class="risk-promotion">'
        '<thead><tr><th>Boundary</th><th>11U</th><th>15U</th></tr></thead>'
        '<tbody>'
        '<tr><td>Into S1</td><td>58%</td><td>71%</td></tr>'
        '<tr><td>Into S2</td><td>21%</td><td>27%</td></tr>'
        '</tbody></table>'
    )

    def test_no_risk_tables_is_noop(self):
        assert colour_risk_cells(self.LAST_COL_TABLE, risk_tables=None) == self.LAST_COL_TABLE
        assert colour_risk_cells(self.LAST_COL_TABLE, risk_tables=[]) == self.LAST_COL_TABLE

    def test_string_entry_uses_last_column(self):
        result = colour_risk_cells(self.LAST_COL_TABLE, risk_tables=['swap-summary'])
        assert 'class="risk-low">18%' in result
        assert 'class="risk-med">32%' in result
        assert 'class="risk-high">67%' in result

    def test_first_column_text_not_coloured_in_last_mode(self):
        result = colour_risk_cells(self.LAST_COL_TABLE, risk_tables=['swap-summary'])
        assert 'class="risk' not in result.split('Kangaroos')[0]

    def test_dict_with_columns_all_colours_every_cell(self):
        result = colour_risk_cells(
            self.ALL_CELLS_TABLE,
            risk_tables=[{'class': 'risk-promotion', 'columns': 'all'}],
        )
        assert 'class="risk-high">58%' in result
        assert 'class="risk-high">71%' in result
        assert 'class="risk-low">21%' in result
        assert 'class="risk-med">27%' in result

    def test_dict_with_columns_last_matches_string_behaviour(self):
        as_dict = colour_risk_cells(
            self.LAST_COL_TABLE,
            risk_tables=[{'class': 'swap-summary', 'columns': 'last'}],
        )
        as_string = colour_risk_cells(self.LAST_COL_TABLE, risk_tables=['swap-summary'])
        assert as_dict == as_string

    def test_non_matching_class_left_alone(self):
        result = colour_risk_cells(self.LAST_COL_TABLE, risk_tables=['other-class'])
        assert result == self.LAST_COL_TABLE

    def test_unknown_columns_mode_falls_back_to_last(self):
        result = colour_risk_cells(
            self.ALL_CELLS_TABLE,
            risk_tables=[{'class': 'risk-promotion', 'columns': 'sideways'}],
        )
        # Falls back to 'last' — only the last column gets coloured.
        assert 'class="risk-high">71%' in result
        # 58% sits in the non-last column → must not be wrapped.
        assert '<td>58%</td>' in result


class TestTransformCorrectnessFixes:
    """Regression tests for the batch-2 transform bug fixes."""

    def test_alignment_survives_an_empty_cell(self):
        # An empty middle cell must not desync the column index; the last
        # column (all numeric) should still be right-aligned.
        table = (
            '<table><tbody>'
            '<tr><td>Mon</td><td></td><td>30</td></tr>'
            '<tr><td>Tue</td><td>x</td><td>45</td></tr>'
            '</tbody></table>'
        )
        result = align_table_columns(table)
        assert result.count('<td class="num">30</td>') == 1
        assert '<td class="num">45</td>' in result

    def test_risk_cell_merges_with_existing_class(self):
        table = '<table class="r"><tr><td class="num">67%</td></tr></table>'
        result = colour_risk_cells(table, risk_tables=['r'])
        assert '<td class="risk-high num">67%</td>' in result

    def test_risk_cell_accepts_decimal_percent(self):
        table = '<table class="r"><tr><td>58.5%</td></tr></table>'
        result = colour_risk_cells(table, risk_tables=['r'])
        assert 'risk-high' in result

    def test_result_colouring_is_case_insensitive(self):
        result = colour_results('<td>BYE</td><td>Forfeit Win</td>')
        assert 'result-bye' in result
        assert 'result-win' in result

    def test_direction_marker_class_lands_on_the_row_not_a_cell(self):
        row = '<tr><td class="num">5</td><td><strong>{up}Possums</strong></td></tr>'
        result = _highlight_direction_rows(row)
        assert '<tr class="highlight-up">' in result
        assert '<td class="num">5</td>' in result  # cell class preserved

    def test_match_layout_tolerates_a_column_without_name(self):
        # A front-matter typo (a column missing 'name') must warn/skip, not crash.
        layouts = {'L': {'columns': [{'width': 30}, {'name': 'W'}]}}
        assert _match_layout(['Team', 'W'], layouts) == (None, None)


class TestTypedColumnWidths:
    """Content-typed absolute-em column widths (apply_default_table_widths)."""

    def _ladder(self, extra_cols=""):
        return (
            "<table><thead><tr>"
            "<th>Pos</th><th>Team</th><th>W</th><th>L</th>"
            "<th>GF</th><th>GA</th><th>Pts</th>" + extra_cols +
            "</tr></thead><tbody>"
            "<tr><td>1</td><td>Warrandyte Wallabies</td><td>12</td><td>2</td>"
            "<td>486</td><td>310</td><td>24</td></tr>"
            "<tr><td>8</td><td>Park Orchards</td><td>2</td><td>12</td>"
            "<td>205</td><td>498</td><td>4</td></tr>"
            "</tbody></table>"
        )

    def test_classify_column_types(self):
        assert _classify_column("W", ["12", "2"]) == "stat"
        assert _classify_column("GF", ["486", "205"]) == "stat"     # 3 digits
        assert _classify_column("Amount", ["1,234", "9999"]) == "num"
        assert _classify_column("GA%", ["150.5", "44"]) == "pct"    # % header
        assert _classify_column("Risk", ["58%", "0%"]) == "pct"
        assert _classify_column("Time", ["9:00", "9:18"]) == "time"
        assert _classify_column("Date", ["14 Jun", "21 Jun"]) == "date"
        assert _classify_column("Date", ["Saturday 14 June", "Sunday 22 June"]) == "date"
        assert _classify_column("Score", ["45-38", "6-24"]) == "score"
        assert _classify_column("Record", ["0W-2L-1D", "4W-0L"]) == "score"
        assert _classify_column("Team", ["Warrandyte Wallabies"]) == "text"
        assert _classify_column("Side", ["H", "A"]) == "stat"       # 1-2 char codes
        assert _classify_column("Age", ["15U", "17U"]) == "label"   # 3-char code -> label
        assert _classify_column("Status", ["Active", "Closed"]) == "label"

    def _classes(self, html):
        import re
        cg = re.search(r"<colgroup>.*?</colgroup>", html, re.DOTALL).group(0)
        cols = re.findall(r"<col(?: [^>]*)?>", cg)
        out = []
        for c in cols:
            m = re.search(r'class="(w\d)"', c)
            out.append(m.group(1) if m else "em")   # wide columns get an em width
        return out

    def test_stat_columns_share_one_width(self):
        result = apply_default_table_widths(self._ladder())
        classes = self._classes(result)
        # Pos, W, L, GF, GA, Pts are all stat -> identical rung; Team is a wide
        # (em-width) column.
        headers = ["Pos", "Team", "W", "L", "GF", "GA", "Pts"]
        by_header = dict(zip(headers, classes))
        assert by_header["Team"] == "em"
        stat = {by_header[h] for h in ("Pos", "W", "L", "GF", "GA", "Pts")}
        assert stat != {"em"} and len(stat) == 1     # one shared token width

    def test_all_token_table_gets_fit_class(self):
        html = (
            "<table><thead><tr><th>Rd</th><th>Ct</th><th>GF</th></tr></thead>"
            "<tbody><tr><td>1</td><td>5</td><td>42</td></tr></tbody></table>"
        )
        result = apply_default_table_widths(html)
        assert 'class="fit"' in result

    def test_every_table_shrinks_to_fit(self):
        # All columns are fixed (tokens by ladder, wide by doc-wide width), so a
        # table sizes to its content instead of stretching a column to 100%.
        result = apply_default_table_widths(self._ladder())
        assert 'class="fit"' in result

    def test_disabled_by_front_matter(self):
        result = apply_default_table_widths(self._ladder(), {"table_widths": False})
        assert "<colgroup>" not in result

    @pytest.mark.parametrize("columns", [["Team"], "Team", True, 7])
    def test_invalid_column_overrides_fall_back_to_defaults(self, columns):
        html = self._ladder()
        assert apply_default_table_widths(html, {"columns": columns}) == \
            apply_default_table_widths(html)

    def test_existing_colgroup_is_left_alone(self):
        html = "<table><colgroup><col></colgroup><thead><tr><th>W</th></tr></thead><tbody><tr><td>1</td></tr></tbody></table>"
        assert apply_default_table_widths(html) == html

    def test_colspan_table_skipped(self):
        html = '<table><thead><tr><th>A</th><th>B</th></tr></thead><tbody><tr><td colspan="2">x</td></tr></tbody></table>'
        assert "<colgroup>" not in apply_default_table_widths(html)

    @pytest.mark.parametrize("html", [
        '<table><tbody><tr><td>1</td></tr></tbody></table>',
        '<table aria-label="empty"></table>',
        '<table><thead><tr><th>A</th></tr></thead><tbody></tbody></table>',
        ('<table><thead><tr><th>A</th><th>B</th></tr></thead><tbody>'
         '<tr><td colspan="2">x</td></tr></tbody></table>'),
        ('<table><thead><tr><th>A</th><th>B</th></tr></thead><tbody>'
         '<tr><td rowspan="2">x</td><td>1</td></tr>'
         '<tr><td>y</td><td>2</td></tr></tbody></table>'),
        ('<table><thead><tr><th>A</th><th>B</th></tr></thead><tbody>'
         '<tr><td>x</td></tr></tbody></table>'),
        ('<table><colgroup><col></colgroup><thead><tr><th>A</th></tr></thead>'
         '<tbody><tr><td>x</td></tr></tbody></table>'),
    ])
    def test_ineligible_structures_pass_through_byte_for_byte(self, html):
        assert apply_default_table_widths(html) == html

    def test_all_tbody_groups_participate_in_analysis_and_are_preserved(self):
        html = (
            '<table aria-describedby="note"><thead><tr><th>Value</th></tr></thead>'
            '<tbody id="time"><tr><td>9:00</td></tr></tbody>'
            '<tbody id="date"><tr><td>14 Jun</td></tr></tbody>'
            '</table>'
        )

        result = apply_default_table_widths(html)

        assert '<col style="width:' in result
        assert result.index('id="time"') < result.index('id="date"')
        assert '>9:00<' in result
        assert '>14 Jun<' in result
        assert 'aria-describedby="note"' in result

    def test_ragged_later_tbody_makes_the_whole_table_ineligible(self):
        html = (
            '<table><thead><tr><th>A</th><th>B</th></tr></thead>'
            '<tbody><tr><td>1</td><td>2</td></tr></tbody>'
            '<tbody><tr><td>3</td></tr></tbody></table>'
        )
        assert apply_default_table_widths(html) == html

    def test_normalised_repeated_headers_share_the_same_override(self):
        html = (
            '<table><thead><tr><th><span> Team </span></th><th>Team</th></tr>'
            '</thead><tbody><tr><td>A</td><td>B</td></tr></tbody></table>'
        )
        result = apply_default_table_widths(
            html, {"columns": {"  TEAM  ": "12em"}}
        )
        assert result.count('style="width:12em"') == 2

    def test_section_rows_remain_in_place_with_their_attributes(self):
        html = (
            '<table><thead><tr><th>Division</th><th>Team</th></tr></thead>'
            '<tbody><tr data-kind="section"><td>Open</td><td></td></tr>'
            '<tr><td>Open</td><td>Falcons</td></tr></tbody></table>'
        )
        marked = detect_table_section_rows(html)
        result = apply_default_table_widths(marked)
        assert 'class="table-section"' in result
        assert 'data-kind="section"' in result
        assert result.index('>Open</td><td></td>') < result.index('>Falcons</td>')

    def test_caption_and_semantic_associations_are_preserved(self):
        html = (
            '<table aria-label="results"><caption id="cap">Results</caption>'
            '<thead id="head"><tr><th id="team" scope="col"><em>Team</em></th>'
            '<th id="won" scope="col">W</th></tr></thead>'
            '<tbody id="body"><tr data-row="1"><td headers="team">Falcons</td>'
            '<td headers="won" aria-label="wins">8</td></tr></tbody></table>'
        )

        result = apply_default_table_widths(html)

        assert result.index('<caption') < result.index('<colgroup>')
        assert result.index('<colgroup>') < result.index('<thead')
        for preserved in (
            'aria-label="results"', '<caption id="cap">Results</caption>',
            '<thead id="head">', 'id="team" scope="col"',
            'id="won" scope="col"', '<tbody id="body">', 'data-row="1"',
            'headers="team"', 'headers="won" aria-label="wins"',
            '<em>Team</em>', 'Falcons',
        ):
            assert preserved in result

    def test_declared_layout_uses_the_same_structural_guard(self):
        unsafe = (
            '<table><thead><tr><th>A</th><th>B</th></tr></thead><tbody>'
            '<tr><td rowspan="2">x</td><td>1</td></tr>'
            '<tr><td>y</td><td>2</td></tr></tbody></table>'
        )
        metadata = {
            'tables': {'unsafe': {'columns': [
                {'name': 'A', 'width': 50}, {'name': 'B', 'width': 50}
            ]}}
        }
        assert apply_table_layouts(unsafe, metadata) == unsafe

    def test_declared_layout_does_not_append_to_an_author_colgroup(self):
        html = (
            '<table data-owner="author"><colgroup><col style="width:7em">'
            '</colgroup><thead><tr><th>A</th></tr></thead>'
            '<tbody><tr><td>x</td></tr></tbody></table>'
        )
        metadata = {
            'tables': {'authored': {
                'css_class': 'declared',
                'columns': [{'name': 'A', 'width': 1}],
            }}
        }
        assert apply_table_layouts(html, metadata) == html

    def test_declared_layout_preserves_caption_first_child_position(self):
        html = (
            '<table><caption data-title="x">Title</caption><thead><tr>'
            '<th>A</th></tr></thead><tbody><tr><td>x</td></tr></tbody></table>'
        )
        metadata = {
            'tables': {'captioned': {'columns': [{'name': 'A', 'width': 1}]}}
        }
        result = apply_table_layouts(html, metadata)
        assert result.index('<caption') < result.index('<colgroup>')
        assert result.index('<colgroup>') < result.index('<thead')

    @pytest.mark.parametrize("table_open", [
        '<table>', '<table class="author">',
    ])
    def test_declared_layout_skips_non_string_css_class(self, table_open, caplog):
        html = (
            f'{table_open}<thead><tr><th>A</th></tr></thead>'
            '<tbody><tr><td>x</td></tr></tbody></table>'
        )
        metadata = {
            'tables': {'invalid-class': {
                'css_class': 5,
                'columns': [{'name': 'A', 'width': 1}],
            }}
        }
        result = apply_table_layouts(html, metadata)
        assert '<colgroup>' in result
        assert 'class="5"' not in result
        assert caplog.messages == [
            'table layout invalid-class: css_class must be a string; skipping'
        ]

    def test_column_type_override(self):
        # Force Team to a label — still a wide column, so it gets an em width.
        result = apply_default_table_widths(self._ladder(), {"columns": {"Team": "label"}})
        by_header = dict(zip(["Pos", "Team", "W", "L", "GF", "GA", "Pts"],
                            self._classes(result)))
        assert by_header["Team"] == "em"
        assert 'class="fit"' in result

    def test_explicit_width_override(self):
        result = apply_default_table_widths(self._ladder(), {"columns": {"Team": "12em"}})
        assert 'style="width:12em"' in result

    def test_direct_invalid_metadata_warns_and_uses_safe_defaults(self, caplog):
        html = self._ladder()
        invalid = {
            "table_widths": "sometimes",
            "orientation": "sideways",
            "page_width_em": False,
            "columns": {"Team": '12em";color:red'},
        }

        assert apply_default_table_widths(html, invalid) == \
            apply_default_table_widths(html, {})
        assert len(caplog.messages) == 4
        assert all("color:red" not in message for message in caplog.messages)

    @pytest.mark.parametrize("alias", [False, "off", " OFF ", "none", "Legacy"])
    def test_all_table_width_opt_out_aliases_are_supported(self, alias):
        assert apply_default_table_widths(
            self._ladder(), {"table_widths": alias}
        ) == self._ladder()

    @pytest.mark.parametrize("metadata", [[], "", 0, False])
    def test_falsey_non_mapping_direct_metadata_warns(self, metadata, caplog):
        assert apply_default_table_widths(self._ladder(), metadata) == \
            apply_default_table_widths(self._ladder(), {})
        assert caplog.messages == [
            "front matter: expected a mapping; using empty metadata"
        ]


class TestClassificationAndOverrideContract:
    """Observable regression matrix for supported width behavior."""

    def test_all_semantic_types_emit_their_documented_width_families(self):
        headers = ["S", "N", "P", "T", "D", "R", "L", "Name", "Notes"]
        html = _contract_table(headers, [
            [
                "12", "1234", "58%", "9:00", "14 Jun", "45-38", "Final",
                "Warrandyte Wallabies",
                "This prose sentence has enough words to require wrapping",
            ],
            ["", "", "", "", "", "", "Active", "Park Orchards", ""],
        ])

        result = apply_default_table_widths(html, {"page_width_em": 200})
        cols = dict(zip(headers, _contract_cols(result)))

        expected_ladders = {
            "S": "w2",      # stat
            "N": "w3",      # num
            "P": "w4",      # pct
            "T": "w3",      # time
            "D": "w4",      # date
            "R": "w4",      # score
        }
        for header, css_class in expected_ladders.items():
            assert f'class="{css_class}"' in cols[header]
        for header in ("L", "Name", "Notes"):  # label, text, prose
            assert re.search(r'style="width:[\d.]+em"', cols[header])
        assert 'class="fit"' in result

    def test_empty_values_do_not_defeat_a_consistent_type(self):
        html = _contract_table(["Pct"], [["58%"], [""], ["0%"]])
        col = _contract_cols(apply_default_table_widths(html))[0]
        assert 'class="w4"' in col

    def test_mixed_values_ignore_a_misleading_header(self):
        html = _contract_table(["Risk%"], [["58%"], ["Pending"]])
        result = apply_default_table_widths(html)
        assert re.search(r'<col style="width:[\d.]+em">', result)
        assert "58%" in result and "Pending" in result

    def test_long_tokens_and_linked_urls_are_preserved_and_bounded(self):
        token = "A" * 100
        url = "https://example.com/" + "path" * 25
        link = f'<a href="{url}">{url}</a>'
        html = _contract_table(["Reference"], [[token], [link]])

        result = apply_default_table_widths(
            html, {"page_width_em": 20}
        )
        width = float(re.search(r'width:([\d.]+)em', result).group(1))
        css = (
            Path(__file__).parents[1] / "pdf" / "styles" / "style.css"
        ).read_text(encoding="utf-8")

        assert width <= 20
        assert token in result
        assert link in result
        assert re.search(
            r"th,\s*td\s*\{[^}]*overflow-wrap:\s*break-word",
            css,
            re.DOTALL,
        )

    def test_normalised_headers_share_document_identities(self):
        html = "\n".join([
            _contract_table(["Home"], [["Very Long Warrandyte Team Name"]]),
            _contract_table(["<span> TEAM </span>"], [["Alpha"]]),
            _contract_table(["Division"], [["Open Championship Division"]]),
            _contract_table([" division "], [["Short"]]),
            _contract_table(["Venue"], [["Court"]]),
        ])

        result = apply_default_table_widths(html, {"page_width_em": 200})
        table_widths = [
            re.search(r'width:([\d.]+)em', table).group(1)
            for table in re.findall(
                r"<table\b[^>]*>.*?</table>", result, re.DOTALL
            )
        ]

        assert table_widths[0] == table_widths[1]
        assert table_widths[2] == table_widths[3]
        assert table_widths[4] not in {table_widths[0], table_widths[2]}

    @pytest.mark.parametrize(
        ("forced_type", "expected_kind"),
        [
            ("stat", "ladder"), ("num", "ladder"), ("pct", "ladder"),
            ("time", "ladder"), ("date", "ladder"), ("score", "ladder"),
            ("label", "em"), ("text", "em"), ("prose", "em"),
        ],
    )
    def test_every_known_type_override_is_accepted(
        self, forced_type, expected_kind, caplog
    ):
        html = _contract_table(["Value"], [["Alpha"]])
        col = _contract_cols(apply_default_table_widths(
            html, {"columns": {"Value": forced_type}}
        ))[0]

        if expected_kind == "ladder":
            assert re.search(r'class="w\d"', col)
        else:
            assert re.search(r'style="width:[\d.]+em"', col)
        assert caplog.messages == []

    @pytest.mark.parametrize(
        ("override", "emitted"),
        [(7.25, "7.25em"), ("8.50em", "8.5em")],
    )
    def test_exact_widths_override_automatic_typing(self, override, emitted):
        html = _contract_table(["Value"], [["1234"]])
        result = apply_default_table_widths(
            html, {"columns": {"Value": override}}
        )
        assert f'style="width:{emitted}"' in result

    def test_declared_layout_wins_over_column_override(self):
        html = _contract_table(["Value"], [["1234"]])
        metadata = {
            "tables": {
                "declared": {
                    "columns": [{"name": "Value", "width": 1}],
                }
            },
            "columns": {"Value": "99em"},
        }
        result = apply_table_layouts(html, metadata)
        result = apply_default_table_widths(result, metadata)

        assert "width:100.0%" in result
        assert "99em" not in result
        assert result.count("<colgroup>") == 1

    def test_author_colgroup_wins_over_column_override(self):
        html = (
            '<table><colgroup><col style="width:7em"></colgroup>'
            '<thead><tr><th>Value</th></tr></thead>'
            '<tbody><tr><td>1234</td></tr></tbody></table>'
        )
        assert apply_default_table_widths(
            html, {"columns": {"Value": "99em"}}
        ) == html

    def test_invalid_override_does_not_discard_valid_sibling(self, caplog):
        html = _contract_table(["Good", "Bad"], [["Alpha", "1234"]])
        result = apply_default_table_widths(html, {
            "columns": {"Good": "7em", "Bad": "calc(12em)"}
        })

        assert 'style="width:7em"' in result
        assert 'class="w3"' in result
        assert caplog.messages == [
            "front matter 'columns': ignored entry with invalid width"
        ]

    @pytest.mark.parametrize("opt_out", [False, "off", " NONE ", "Legacy"])
    def test_opt_out_preserves_independent_alignment(self, opt_out):
        from pdf.postprocess import postprocess

        html = _contract_table(["Team", "Wins"], [["Falcons", "12"]])
        result = postprocess(html, {"table_widths": opt_out})
        assert "<colgroup>" not in result
        assert 'class="num"' in result


class TestExactWidthFitting:
    """Accepted explicit widths participate exactly in page-fit accounting."""

    @staticmethod
    def _table(headers, cells):
        th = "".join(f"<th>{header}</th>" for header in headers)
        td = "".join(f"<td>{cell}</td>" for cell in cells)
        return (
            f"<table><thead><tr>{th}</tr></thead>"
            f"<tbody><tr>{td}</tr></tbody></table>"
        )

    @staticmethod
    def _em_total(html):
        import re

        rung_em = {"w1": 2.5, "w2": 3, "w3": 3.5, "w4": 4.5, "w5": 5.5}
        colgroup = re.search(r"<colgroup>(.*?)</colgroup>", html).group(1)
        total = 0.0
        for attrs in re.findall(r"<col([^>]*)>", colgroup):
            width = re.search(r"width:([+\-.\deE]+)em", attrs)
            rung = re.search(r'class="(w\d)"', attrs)
            total += float(width.group(1)) if width else rung_em[rung.group(1)]
        return total

    def test_numeric_and_em_widths_use_the_exact_boundary_total(self):
        html = self._table(["Numeric", "String"], ["A", "B"])
        metadata = {"columns": {"Numeric": 7.5, "String": "10.5em"}}

        boundary = apply_default_table_widths(
            html, {**metadata, "page_width_em": 18}
        )
        overflow = apply_default_table_widths(
            html, {**metadata, "page_width_em": 17.99}
        )

        assert 'style="width:7.5em"' in boundary
        assert 'style="width:10.5em"' in boundary
        assert 'class="fit"' in boundary
        assert 'class="fit"' not in overflow

    @pytest.mark.parametrize("override", [1.23456789, "1.23456789em"])
    def test_high_precision_width_round_trips_to_emitted_css(self, override):
        html = self._table(["Pinned"], ["x"])
        width = 1.23456789

        result = apply_default_table_widths(
            html,
            {"columns": {"Pinned": override}, "page_width_em": width},
        )

        assert 'class="fit"' in result
        assert 'style="width:1.23456789em"' in result
        assert self._em_total(result) == width

    def test_individually_finite_widths_with_infinite_total_do_not_crash(
        self, caplog
    ):
        html = self._table(["A", "B"], ["x", "y"])

        with caplog.at_level("INFO", logger="pdf.table_transforms"):
            result = apply_default_table_widths(
                html,
                {"columns": {"A": 1e308, "B": 1e308},
                 "page_width_em": 50},
            )

        assert result.count('style="width:1e+308em"') == 2
        assert 'class="fit"' not in result
        assert "widest ~infem vs 50em available" in caplog.text
        assert "fixed columns remain wider than the budget" in caplog.text

    def test_public_pass_accepts_an_already_normalized_large_em_string(self):
        from pdf.width_metadata import normalise_width_metadata

        html = self._table(["Pinned"], ["x"])
        metadata, warnings = normalise_width_metadata({
            "columns": {"Pinned": "1" + "0" * 308 + "em"},
            "page_width_em": 50,
        })

        result = apply_default_table_widths(html, metadata)

        assert warnings == []
        assert 'style="width:1e+308em"' in result
        assert 'class="fit"' not in result

    def test_mixed_explicit_typed_and_wide_columns_share_one_exact_total(
        self, caplog
    ):
        from pdf.table_transforms import (
            _analyze_table_for_widths,
            _column_identity,
            _fit_table_widths,
        )

        html = self._table(
            ["Name", "W", "Pinned"], ["Warrandyte Wallabies", "12", "x"]
        )
        analysis = _analyze_table_for_widths(html, {"pinned": "7.25em"})
        identities = {
            _column_identity(analysis["headers"][index]): width
            for index, width in analysis["nat"].items()
        }
        unconstrained = _fit_table_widths(analysis, identities, float("inf"))

        assert unconstrained.outcome == "fit"
        assert unconstrained.emitted_total_em == unconstrained.natural_total_em
        boundary = apply_default_table_widths(
            html,
            {"columns": {"Pinned": "7.25em"},
             "page_width_em": unconstrained.natural_total_em},
        )
        overflow_budget = unconstrained.natural_total_em - 0.01
        with caplog.at_level("INFO", logger="pdf.table_transforms"):
            overflow = apply_default_table_widths(
                html,
                {"columns": {"Pinned": "7.25em"},
                 "page_width_em": overflow_budget},
            )

        assert 'class="fit"' in boundary
        assert 'class="fit"' not in overflow
        assert self._em_total(boundary) == pytest.approx(
            unconstrained.natural_total_em
        )
        assert self._em_total(overflow) <= overflow_budget
        assert 'style="width:7.25em"' in boundary
        assert 'style="width:7.25em"' in overflow
        assert boundary.count('class="w') == overflow.count('class="w') == 1
        assert "automatic wide columns were scaled to fit" in caplog.text

    def test_widest_automatic_column_gives_up_space_first(self):
        from pdf.table_transforms import _fit_table_widths

        analysis = {
            "headers": ["Description", "Division"],
            "types": ["text", "text"],
            "explicit": {},
            "group_rung": {},
            "nat": {0: 20, 1: 10},
        }
        fit = _fit_table_widths(
            analysis,
            {"description": 20, "division": 10},
            page_em=29,
        )

        assert fit.outcome == "scaled"
        assert fit.wide_em == {0: 19, 1: 10}
        assert fit.emitted_total_em == 29

    def test_wide_column_cannot_hide_fixed_column_overflow(self, caplog):
        html = self._table(["Pinned", "Name"], ["x", "Casey"])

        with caplog.at_level("INFO", logger="pdf.table_transforms"):
            result = apply_default_table_widths(
                html,
                {"columns": {"Pinned": "60em"}, "page_width_em": 50},
            )

        assert 'style="width:60em"' in result
        assert 'class="fit"' not in result
        assert self._em_total(result) > 50
        assert "fixed columns remain wider than the budget" in caplog.text

    def test_fixed_only_overflow_preserves_widths_and_is_not_fit(self, caplog):
        html = self._table(["A", "B"], ["x", "y"])
        metadata = {
            "columns": {"A": "30em", "B": 30},
            "page_width_em": 50,
        }

        with caplog.at_level("INFO", logger="pdf.table_transforms"):
            result = apply_default_table_widths(html, metadata)

        assert 'style="width:30em"' in result
        assert result.count('style="width:30em"') == 2
        assert 'class="fit"' not in result
        assert (
            "1 table(s) are wider than the fitting budget "
            "(widest ~60em vs 50em available)" in caplog.text
        )
        assert "fixed columns remain wider than the budget in 1 table(s)" \
            in caplog.text
        assert "consider 'orientation: landscape'" not in caplog.text

    def test_orientation_budget_changes_the_same_fixed_table_outcome(self):
        html = self._table(["Pinned"], ["x"])
        columns = {"Pinned": "60em"}

        portrait = apply_default_table_widths(html, {"columns": columns})
        landscape = apply_default_table_widths(
            html, {"columns": columns, "orientation": "landscape"}
        )

        assert 'class="fit"' not in portrait
        assert 'class="fit"' in landscape

    def test_landscape_overflow_is_reported_without_portrait_advice(self, caplog):
        html = self._table(["Pinned"], ["x"])

        with caplog.at_level("INFO", logger="pdf.table_transforms"):
            result = apply_default_table_widths(
                html,
                {"columns": {"Pinned": "90em"},
                 "orientation": "landscape"},
            )

        assert 'class="fit"' not in result
        assert (
            "1 table(s) are wider than the fitting budget "
            "(widest ~90em vs 82em available)" in caplog.text
        )
        assert "fixed columns remain wider than the budget in 1 table(s)" \
            in caplog.text
        assert "consider 'orientation: landscape'" not in caplog.text

    def test_default_portrait_scaling_suggests_landscape(self, caplog):
        html = self._table(
            ["Home", "Division"],
            ["Very Long Team Name " * 5, "Very Long Division Name " * 5],
        )

        with caplog.at_level("INFO", logger="pdf.table_transforms"):
            result = apply_default_table_widths(html)

        assert 'class="fit"' not in result
        assert "automatic wide columns were scaled to fit" in caplog.text
        assert "consider 'orientation: landscape'" in caplog.text


class TestDocLevelWidths:
    """Document-level width grouping for wide columns."""

    def test_column_identity_shares_team_headers(self):
        from pdf.table_transforms import _column_identity
        # Team / Home / Away all resolve to one identity; Division to its own.
        team = _column_identity("Home")
        assert _column_identity("Away") == team
        assert _column_identity("Team") == team
        assert _column_identity("Home Team") == team
        assert _column_identity("Division") != team

    def _schedule(self):
        homes = ["Manningham 15U Champ", "Frankston District 17U Champ",
                 "Lilydale & Yarra Valley 17U Champ", "Kingston 17U Res",
                 "Bayside District 15U Res", "Casey 15U Res", "Yarra 15U Champ",
                 "Chelsea District 17U Champ", "Manningham 17U Res", "Melbourne East"]
        aways = ["Mornington Peninsula 15U Champ", "Nepean 15U Res", "Stonnington City",
                 "Whitehorse 15U Champ", "Springvale 15U Res", "Boroondara 17U Champ",
                 "Ariels VCNA 17U Champ", "Waverley 17U Res", "Dandenong District 15U",
                 "Outer East FNL 15U Champ"]
        divs = ["15U Champ Pool A", "17U Reserve Pool B"] * 5
        rows = "".join(
            f"<tr><td>{9+i}:00</td><td>{i%11+1}</td><td>{i%9+1}</td>"
            f"<td>{divs[i]}</td><td>{homes[i]}</td><td>{aways[i]}</td></tr>"
            for i in range(10)
        )
        return (
            "<table><thead><tr><th>Time</th><th>Ct</th><th>Rd</th>"
            "<th>Division</th><th>Home</th><th>Away</th></tr></thead>"
            f"<tbody>{rows}</tbody></table>"
        )

    def _colmap(self, html):
        import re
        cg = re.search(r"<colgroup>(.*?)</colgroup>", html, re.DOTALL).group(1)
        out = []
        for c in re.findall(r"<col([^>]*)>", cg):
            m = re.search(r'class="(w\d)"', c) or re.search(r'width:([\d.]+em)', c)
            out.append(m.group(1) if m else "BARE")
        return out

    def test_wide_columns_get_em_widths_tokens_get_rungs(self):
        result = apply_default_table_widths(self._schedule())
        cols = dict(zip(["Time", "Ct", "Rd", "Division", "Home", "Away"],
                        self._colmap(result)))
        # Division and the two name columns are wide -> explicit em widths.
        assert cols["Division"].endswith("em")
        assert cols["Home"].endswith("em") and cols["Away"].endswith("em")
        # Home and Away share the team identity -> identical width.
        assert cols["Home"] == cols["Away"]
        # Court/Round stay narrow token rungs; the table shrinks to fit.
        assert cols["Ct"].startswith("w") and cols["Rd"].startswith("w")
        assert 'class="fit"' in result

    def test_page_width_controls_overflow_scaling(self):
        import re
        sched = self._schedule()
        # A narrow page forces the wide columns to scale down; a wide page (or
        # landscape) lets them keep their full document-wide width.
        narrow = apply_default_table_widths(sched, {"page_width_em": 40})
        wide = apply_default_table_widths(sched, {"page_width_em": 90})
        nw = max(float(x) for x in re.findall(r"width:([\d.]+)em", narrow))
        ww = max(float(x) for x in re.findall(r"width:([\d.]+)em", wide))
        assert ww > nw
        # orientation: landscape selects a wider budget than portrait.
        from pdf.table_transforms import _page_content_em
        assert _page_content_em({"orientation": "landscape"}) > _page_content_em({})

    def test_identity_width_shared_across_tables(self):
        # A team column in a second, separate table gets the SAME width as the
        # widest team name anywhere in the document.
        schedule = self._schedule()
        summary = ("<table><thead><tr><th>Team</th><th>Gms</th></tr></thead>"
                   "<tbody><tr><td>Casey</td><td>9</td></tr>"
                   "<tr><td>Yarra</td><td>8</td></tr></tbody></table>")
        result = apply_default_table_widths(schedule + "\n" + summary)
        import re
        widths = re.findall(r'width:([\d.]+)em', result)
        # The summary's short "Team" column is widened to the doc-wide team
        # width (driven by the long schedule names), so that value recurs.
        home = self._colmap(
            re.search(r'<table[^>]*>.*?</table>', result, re.DOTALL).group(0))
        # The team width appears at least 3× (Home, Away, summary Team).
        team_w = home[4]  # Home column
        assert result.count(f'width:{team_w}') >= 3


class TestTableWidthCorrectness:
    @staticmethod
    def _row_header_table():
        return (
            '<table><caption>Results</caption><thead><tr>'
            '<th id="team" scope="col">Team</th><th scope="col">W</th>'
            '<th scope="col">GD</th></tr></thead><tbody data-group="ladder">'
            '<tr><th id="row-one" scope="row">River Kites</th>'
            '<td headers="row-one">12</td><td>−293</td></tr></tbody></table>'
        )

    @pytest.mark.parametrize('explicit_tbody', [True, False])
    def test_row_headers_participate_without_losing_semantics(self, explicit_tbody):
        html = self._row_header_table()
        if not explicit_tbody:
            html = html.replace('<tbody data-group="ladder">', '').replace('</tbody>', '')
        equivalent = html.replace(
            '<th id="row-one" scope="row">River Kites</th>',
            '<td id="row-one">River Kites</td>',
        )

        result = apply_default_table_widths(html)

        assert _contract_cols(result) == _contract_cols(apply_default_table_widths(equivalent))
        assert '<th id="row-one" scope="row">River Kites</th>' in result
        assert 'headers="row-one"' in result
        assert result.index('<caption>') < result.index('<colgroup>')
        assert apply_default_table_widths(result) == result

    def test_declared_layout_accepts_row_headers_and_wins(self):
        result = apply_table_layouts(self._row_header_table(), {'tables': {'ladder': {
            'columns': [{'name': 'Team', 'width': 60},
                        {'name': 'W', 'width': 20}, {'name': 'GD', 'width': 20}],
        }}})
        assert 'width:60.0%' in result
        assert '<th id="row-one" scope="row">River Kites</th>' in result
        assert apply_default_table_widths(result) == result

    def test_row_headers_do_not_shift_numeric_alignment(self):
        result = align_table_columns(self._row_header_table())
        assert '<td headers="row-one" class="num">12</td>' in result
        assert '<td class="num">−293</td>' in result
        assert '<th id="row-one" scope="row">River Kites</th>' in result

    @pytest.mark.parametrize('header', ['For &amp; Against', 'For &#38; Against'])
    def test_decoded_headers_match_exact_width_overrides(self, header):
        html = _contract_table([header], [['20']])
        result = apply_default_table_widths(html, {'columns': {'For & Against': '12em'}})
        assert _contract_cols(result) == ['<col style="width:12em">']
        assert header in result

    def test_declared_matching_uses_decoded_collapsed_headers(self):
        html = _contract_table(['<em>For &amp; Against</em>'], [['20']])
        result = apply_table_layouts(html, {'tables': {'goals': {
            'columns': [{'name': '  For & Against  ', 'width': 1}],
        }}})
        assert 'width:100.0%' in result
        assert '<em>For &amp; Against</em>' in result

    def test_encoded_names_have_the_same_natural_measurement(self):
        encoded = _contract_table(['Team'], [['River &amp; District Kites']])
        literal = _contract_table(['Team'], [['River & District Kites']])
        assert _contract_cols(apply_default_table_widths(encoded)) == \
            _contract_cols(apply_default_table_widths(literal))

    def test_html_line_breaks_do_not_join_numeric_tokens(self):
        assert _classify_column('Value', ['1<br>2']) != 'stat'

    @pytest.mark.parametrize('cell', [
        '&lt;Northern District United&gt;',
        '&amp;#49;',
    ])
    def test_visible_escaped_text_is_decoded_exactly_once(self, cell):
        assert _classify_column('Team', [cell]) not in {'stat', 'num'}

    def test_visible_angle_bracket_header_survives_matching_and_overrides(self):
        html = _contract_table(['&lt;Club&gt;'], [['River Kites']])
        automatic = apply_default_table_widths(
            html, {'columns': {'<Club>': '12em'}})
        declared = apply_table_layouts(html, {'tables': {'club': {
            'columns': [{'name': '<Club>', 'width': 1}],
        }}})
        assert _contract_cols(automatic) == ['<col style="width:12em">']
        assert 'width:100.0%' in declared
        assert '&lt;Club&gt;' in declared

    @pytest.mark.parametrize('minus', ['−', '&#8722;', '&minus;'])
    def test_unicode_minus_keeps_numeric_types_and_grouping(self, minus):
        assert _classify_column('GD', ['+176', f'{minus}293']) == 'stat'
        assert _classify_column('Change', [f'{minus}12.5%']) == 'pct'
        html = _contract_table(['W', 'GD'], [['12', f'{minus}293']])
        columns = _contract_cols(apply_default_table_widths(html))
        assert columns[0] == columns[1]

    def test_impossible_budget_preserves_usable_wide_minimum(self, caplog):
        from pdf.table_transforms import _MIN_WIDE_EM, _analyze_table_for_widths, _fit_table_widths

        html = _contract_table(['Pinned', 'Team'], [['x', 'Warrandyte Wallabies']])
        analysis = _analyze_table_for_widths(html, {'pinned': 54})
        fit = _fit_table_widths(analysis, {}, 54.8)
        assert fit.outcome == 'unresolved_overflow'
        assert fit.wide_em[1] == pytest.approx(_MIN_WIDE_EM)
        assert fit.emitted_total_em > 54.8
        with caplog.at_level('INFO', logger='pdf.table_transforms'):
            result = apply_default_table_widths(html, {'columns': {'Pinned': 54}})
        assert 'class="fit"' not in result
        assert 'unresolved overflow' in caplog.text
        assert 'minimum usable automatic widths' in caplog.text
        assert 'automatic wide columns were scaled to fit' not in caplog.text

    def test_mixed_short_and_long_columns_respect_minima(self):
        from pdf.table_transforms import _MIN_WIDE_EM, _fit_table_widths

        analysis = {'headers': ['Notes', 'Venue', 'Day'], 'types': ['text'] * 3,
                    'explicit': {}, 'group_rung': {}, 'nat': {0: 20, 1: 10, 2: 2}}
        fit = _fit_table_widths(analysis, {}, 9)
        assert fit.outcome == 'scaled'
        assert fit.wide_em[0] >= _MIN_WIDE_EM
        assert fit.wide_em[1] >= _MIN_WIDE_EM
        assert fit.wide_em[2] == 2
        assert fit.emitted_total_em <= 9

    @pytest.mark.parametrize('invalid', [None, [], {'columns': None}, {'columns': [None]},
        {'columns': [{'width': 10}]}, {'columns': [{'name': 12}]},
        *[{'columns': [{'name': 'Team', 'width': value}]}
          for value in [-1, 0, '12em', True, float('inf'), float('nan')]],
        {'columns': [{'name': 'Team', 'align': 'sideways'}]},
    ])
    def test_invalid_declared_layout_does_not_discard_valid_sibling(self, invalid, caplog):
        html = _contract_table(['Team'], [['River Kites']])
        valid = {'columns': [{'name': 'Team', 'width': 1}]}
        result = apply_table_layouts(html, {'tables': {'invalid': invalid, 'valid': valid}})
        assert 'width:100.0%' in result
        assert 'invalid columns or relative widths' in caplog.text

    def test_large_declared_relative_weights_do_not_overflow(self):
        html = _contract_table(['Team', 'W'], [['River Kites', '12']])
        result = apply_table_layouts(html, {'tables': {'ladder': {'columns': [
            {'name': 'Team', 'width': 1e308}, {'name': 'W', 'width': 1e308},
        ]}}})
        assert result.count('width:50.0%') == 2
