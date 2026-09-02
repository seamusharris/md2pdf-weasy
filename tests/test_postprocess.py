"""Tests for HTML post-processing (page-break markers, etc.)."""

import re

from pdf.postprocess import (
    convert_page_breaks,
    postprocess,
    wrap_standalone_images,
)


def test_postprocess_falsey_non_mapping_metadata_warns_and_continues(caplog):
    assert postprocess("<p>ok</p>", []) == "<p>ok</p>"
    assert caplog.messages == [
        "front matter: expected a mapping; using empty metadata"
    ]


def test_table_postprocessing_is_repeat_safe_for_automatic_widths():
    html = (
        '<table aria-label="results"><caption>Results</caption>'
        '<thead><tr><th scope="col">Team</th><th scope="col">W</th></tr></thead>'
        '<tbody><tr><td>Falcons</td><td headers="wins">8</td></tr></tbody>'
        '</table>'
    )
    once = postprocess(html)
    assert postprocess(once) == once
    assert once.count('<colgroup>') == 1


def test_table_postprocessing_is_repeat_safe_for_declared_layouts():
    html = (
        '<table><caption>Schedule</caption><thead><tr><th>Day</th><th>Count</th>'
        '</tr></thead><tbody><tr><td>Mon</td><td>2</td></tr></tbody></table>'
    )
    metadata = {
        'tables': {'schedule': {
            'css_class': 'schedule',
            'columns': [
                {'name': 'Day', 'width': 2},
                {'name': 'Count', 'width': 1, 'align': 'right'},
            ],
        }},
    }
    once = postprocess(html, metadata)
    assert postprocess(once, metadata) == once
    assert once.count('<colgroup>') == 1
    assert len(re.findall(r'\bclass="schedule(?:\s|\")', once)) == 1


def test_table_postprocessing_is_repeat_safe_for_risk_classes():
    html = (
        '<table class="risk"><thead><tr><th>Team</th><th>Risk</th></tr></thead>'
        '<tbody><tr><td>Falcons</td><td>67%</td></tr></tbody></table>'
    )
    metadata = {'risk_tables': ['risk']}
    once = postprocess(html, metadata)
    assert postprocess(once, metadata) == once
    assert once.count('risk-high') == 1


def test_classification_matrix_postprocessing_is_repeat_safe():
    html = (
        '<table><thead><tr><th><span> Team </span></th><th>Count</th>'
        '<th>Risk</th><th>Notes</th></tr></thead><tbody>'
        '<tr><td>Falcons</td><td>1234</td><td>58%</td>'
        '<td>Longer explanatory prose remains unchanged here</td></tr>'
        '</tbody></table>'
    )
    metadata = {
        'columns': {
            ' TEAM ': 'text',
            'Count': 'num',
            'Risk': 'pct',
            'Notes': 'prose',
        },
        'auto_align_columns': True,
    }

    once = postprocess(html, metadata)

    assert postprocess(once, metadata) == once
    assert once.count('<colgroup>') == 1
    assert once.count('class="num"') == 2
    assert '<span> Team </span>' in once


class TestStandaloneImages:
    def test_title_becomes_caption_and_layout_moves_to_figure(self):
        html = (
            '<p><img alt="Team photograph" class="figure-wide" '
            'src="images/team.jpg" title="Premiers &amp; officials"></p>'
        )
        result = wrap_standalone_images(html)

        assert '<figure class="markdown-figure figure-wide">' in result
        assert '<figcaption>Premiers &amp; officials</figcaption>' in result
        assert 'alt="Team photograph"' in result

    def test_alt_text_is_caption_fallback(self):
        result = wrap_standalone_images(
            '<p><img alt="1978 team" src="images/team.jpg"></p>'
        )
        assert '<figcaption>1978 team</figcaption>' in result

    def test_inline_image_and_authored_figure_are_unchanged(self):
        inline = '<p>Before <img alt="crest" src="crest.svg"> after</p>'
        authored = (
            '<figure class="figure-page"><img alt="Page" src="page.jpg">'
            '<figcaption>Custom caption</figcaption></figure>'
        )

        assert wrap_standalone_images(inline) == inline
        assert wrap_standalone_images(authored) == authored

    def test_postprocessing_is_repeat_safe(self):
        html = '<p><img alt="Team" src="team.jpg"></p>'
        once = postprocess(html)
        assert postprocess(once) == once


class TestConvertPageBreaks:
    """HTML-comment markers in markdown become CSS-driven page breaks."""

    def test_page_break_comment_applies_to_the_following_element(self):
        html = "<p>before</p>\n<!-- page-break -->\n<p>after</p>"
        result = convert_page_breaks(html)
        assert 'break-before: page' in result
        assert '<!-- page-break -->' not in result
        assert '<div' not in result
        assert '<p style="break-before: page;">after</p>' in result

    def test_page_break_merges_into_existing_style(self):
        html = '<!-- page-break -->\n<h2 style="color:red">Section</h2>'
        result = convert_page_breaks(html)
        assert result.count('style=') == 1
        assert 'break-before: page' in result
        assert 'color:red' in result

    def test_no_page_break_marker_does_nothing_alone(self):
        # The no-page-break marker only activates when followed by a heading
        html = "<p>before</p>\n<!-- no-page-break -->\n<p>after</p>"
        result = convert_page_breaks(html)
        # Marker is consumed by the regex when followed by a heading; on its
        # own it's harmless — passes through unchanged in this case.
        assert '<p>after</p>' in result

    def test_no_page_break_before_heading_suppresses_break(self):
        html = "<!-- no-page-break -->\n<h2>Section</h2>"
        result = convert_page_breaks(html)
        # The marker plus the next heading gets transformed
        assert 'break-before: auto' in result
        assert '<!-- no-page-break -->' not in result

    def test_no_page_break_merges_into_existing_style(self):
        # A heading that already has an inline style must not end up with two
        # style attributes (the second would be dropped by the HTML parser).
        html = '<!-- no-page-break -->\n<h2 style="color:red">Section</h2>'
        result = convert_page_breaks(html)
        assert result.count('style=') == 1
        assert 'break-before: auto' in result
        assert 'color:red' in result

    def test_whitespace_around_markers_is_tolerant(self):
        # Extra spaces inside the comment delimiters should still match
        html = "<!--    page-break   -->"
        result = convert_page_breaks(html)
        assert 'break-before: page' in result

    def test_other_html_comments_passed_through(self):
        # Comments that aren't page-break or no-page-break should survive
        html = "<!-- this is a regular comment --><p>hi</p>"
        result = convert_page_breaks(html)
        assert "<!-- this is a regular comment -->" in result
