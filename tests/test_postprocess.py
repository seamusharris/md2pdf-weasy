"""Tests for HTML post-processing (page-break markers, etc.)."""

from pdf.postprocess import convert_page_breaks, postprocess


def test_postprocess_falsey_non_mapping_metadata_warns_and_continues(caplog):
    assert postprocess("<p>ok</p>", []) == "<p>ok</p>"
    assert caplog.messages == [
        "front matter: expected a mapping; using empty metadata"
    ]


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
