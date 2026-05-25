"""Tests for blockquote splitting and tier classification."""

from pdf.blockquotes import classify_blockquotes, split_merged_blockquotes


def _classify(content, **kwargs):
    """Shortcut: wrap content in <blockquote>, classify, return result."""
    html = f"<blockquote>{content}</blockquote>"
    return classify_blockquotes(html, **kwargs)


class TestClassifyBlockquotes:
    """Bold-keyword and GitHub-style alert detection."""

    def test_note_keyword_becomes_info_tier(self):
        result = _classify("<p><strong>Note:</strong> blah</p>")
        assert 'class="info"' in result

    def test_warning_keyword_becomes_warning_tier(self):
        result = _classify("<p><strong>Warning:</strong> blah</p>")
        assert 'class="warning"' in result

    def test_tip_keyword_becomes_tip_tier(self):
        result = _classify("<p><strong>Tip:</strong> blah</p>")
        assert 'class="tip"' in result

    def test_important_keyword_becomes_important_tier(self):
        result = _classify("<p><strong>Important:</strong> blah</p>")
        assert 'class="important"' in result

    def test_caution_keyword_becomes_caution_tier(self):
        result = _classify("<p><strong>Caution:</strong> blah</p>")
        assert 'class="caution"' in result

    def test_no_keyword_becomes_default_aside(self):
        result = _classify("<p>just some plain content</p>")
        assert 'class="default-aside"' in result

    def test_keyword_aliases_map_to_same_tier(self):
        # 'Info' and 'Note' both map to the info tier
        assert 'class="info"' in _classify("<p><strong>Info:</strong> x</p>")
        # 'Attention' and 'Caution' both map to caution
        assert 'class="caution"' in _classify("<p><strong>Attention:</strong> x</p>")
        # 'Key' and 'Highlight' both map to important
        assert 'class="important"' in _classify("<p><strong>Key:</strong> x</p>")
        # 'Success' maps to tip
        assert 'class="tip"' in _classify("<p><strong>Success:</strong> x</p>")

    def test_keyword_matching_is_case_insensitive(self):
        assert 'class="warning"' in _classify("<p><strong>WARNING:</strong> x</p>")
        assert 'class="warning"' in _classify("<p><strong>warning:</strong> x</p>")

    def test_plain_text_note_prefix_falls_back_to_info(self):
        # No <strong>; just plain "Note:" at the start
        result = _classify("<p>Note: a plain-text note</p>")
        assert 'class="info"' in result

    def test_extra_keywords_extend_existing_tiers(self):
        result = _classify(
            "<p><strong>Recipe:</strong> chop onions</p>",
            extra_keywords={'tip': ['Recipe']},
        )
        assert 'class="tip"' in result

    def test_github_alert_note(self):
        result = _classify("<p>[!NOTE] some content</p>")
        assert 'class="info"' in result

    def test_github_alert_warning(self):
        result = _classify("<p>[!WARNING] watch out</p>")
        assert 'class="warning"' in result

    def test_github_alert_case_insensitive(self):
        result = _classify("<p>[!important] read this</p>")
        assert 'class="important"' in result


class TestSplitMergedBlockquotes:
    """When python-markdown merges multiple > lines into one blockquote."""

    def test_single_paragraph_unchanged(self):
        html = "<blockquote>\n<p>only one</p>\n</blockquote>"
        assert split_merged_blockquotes(html) == html

    def test_multiple_paragraphs_split_to_separate_blockquotes(self):
        html = "<blockquote>\n<p>first</p>\n<p>second</p>\n</blockquote>"
        result = split_merged_blockquotes(html)
        # Should be two separate blockquote elements
        assert result.count("<blockquote>") == 2
        assert result.count("</blockquote>") == 2
        assert "<p>first</p>" in result
        assert "<p>second</p>" in result

    def test_three_merged_paragraphs_split_to_three(self):
        html = "<blockquote>\n<p>a</p>\n<p>b</p>\n<p>c</p>\n</blockquote>"
        result = split_merged_blockquotes(html)
        assert result.count("<blockquote>") == 3
