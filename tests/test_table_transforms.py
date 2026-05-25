"""Tests for table layout, column widths, alignment, and section detection."""

from pdf.table_transforms import (
    _column_width,
    _DEFAULT_WIDTHS,
    _build_colgroup,
    _extract_headers,
    _match_layout,
    align_table_columns,
    apply_table_layouts,
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
