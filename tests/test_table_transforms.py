"""Tests for table layout, column widths, alignment, and section detection."""

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
)


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
        assert _classify_column("Score", ["45-38", "6-24"]) == "score"
        assert _classify_column("Record", ["0W-2L-1D", "4W-0L"]) == "score"
        assert _classify_column("Team", ["Warrandyte Wallabies"]) == "text"
        assert _classify_column("Day", ["Mon", "Tue"]) == "stat"    # <=3 chars
        assert _classify_column("Status", ["Active", "Closed"]) == "label"

    def _classes(self, html):
        import re
        cg = re.search(r"<colgroup>.*?</colgroup>", html, re.DOTALL).group(0)
        cols = re.findall(r"<col(?: [^>]*)?>", cg)
        out = []
        for c in cols:
            m = re.search(r'class="(w\d)"', c)
            out.append(m.group(1) if m else "FLEX")
        return out

    def test_stat_columns_share_one_width(self):
        result = apply_default_table_widths(self._ladder())
        classes = self._classes(result)
        # Pos, W, L, GF, GA, Pts are all stat -> identical class; Team is flex.
        headers = ["Pos", "Team", "W", "L", "GF", "GA", "Pts"]
        by_header = dict(zip(headers, classes))
        assert by_header["Team"] == "FLEX"
        stat = {by_header[h] for h in ("Pos", "W", "L", "GF", "GA", "Pts")}
        assert stat != {"FLEX"} and len(stat) == 1   # one shared token width

    def test_all_token_table_gets_fit_class(self):
        html = (
            "<table><thead><tr><th>Rd</th><th>Ct</th><th>GF</th></tr></thead>"
            "<tbody><tr><td>1</td><td>5</td><td>42</td></tr></tbody></table>"
        )
        result = apply_default_table_widths(html)
        assert 'class="fit"' in result       # no flex column -> shrink to fit

    def test_table_with_flex_is_not_fit(self):
        result = apply_default_table_widths(self._ladder())
        assert "fit" not in result

    def test_disabled_by_front_matter(self):
        result = apply_default_table_widths(self._ladder(), {"table_widths": False})
        assert "<colgroup>" not in result

    def test_existing_colgroup_is_left_alone(self):
        html = "<table><colgroup><col></colgroup><thead><tr><th>W</th></tr></thead><tbody><tr><td>1</td></tr></tbody></table>"
        assert apply_default_table_widths(html) == html

    def test_colspan_table_skipped(self):
        html = '<table><thead><tr><th>A</th><th>B</th></tr></thead><tbody><tr><td colspan="2">x</td></tr></tbody></table>'
        assert "<colgroup>" not in apply_default_table_widths(html)

    def test_column_type_override(self):
        # Force Team to a fixed label instead of flex.
        result = apply_default_table_widths(self._ladder(), {"columns": {"Team": "label"}})
        classes = self._classes(result)
        assert "FLEX" not in classes          # Team no longer flex -> table is all-token
        assert 'class="fit"' in result

    def test_explicit_width_override(self):
        result = apply_default_table_widths(self._ladder(), {"columns": {"Team": "12em"}})
        assert 'style="width:12em"' in result
