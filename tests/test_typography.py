"""Tests for ASCII → Unicode typographic conversions."""

from pdf.typography import typographic_convert


class TestTypographicConvert:

    def test_em_dash_with_surrounding_spaces(self):
        assert typographic_convert("a -- b") == "a — b"

    def test_em_dash_not_applied_without_spaces(self):
        # Without surrounding spaces, no conversion (avoids breaking
        # things like CSS shorthand or filenames)
        result = typographic_convert("a--b")
        assert "—" not in result

    def test_arrow_conversion(self):
        assert "→" in typographic_convert("foo -> bar")

    def test_digit_range_becomes_en_dash(self):
        assert typographic_convert("6-8") == "6–8"

    def test_dates_are_not_turned_into_en_dashes(self):
        # ISO dates have a third hyphen-digit group and must be left alone.
        assert typographic_convert("2024-05-01") == "2024-05-01"

    def test_wld_records_are_not_turned_into_en_dashes(self):
        # W-L-D records (5-3-0) are used verbatim by table alignment detection.
        assert typographic_convert("5-3-0") == "5-3-0"

    def test_multiplication_sign_between_digits(self):
        result = typographic_convert("5m x 5m")
        assert "×" in result

    def test_curly_double_quotes(self):
        result = typographic_convert('the "text" is')
        assert "“" in result   # opening
        assert "”" in result   # closing

    def test_curly_apostrophe_inside_word(self):
        result = typographic_convert("don't")
        assert "don’t" == result

    def test_ellipsis(self):
        assert typographic_convert("and...") == "and…"

    def test_html_tags_skipped(self):
        # Should not mangle attributes (no quote replacement inside tags)
        input_html = '<a href="foo.html">link</a>'
        result = typographic_convert(input_html)
        assert 'href="foo.html"' in result

    def test_non_string_passes_through(self):
        # Idempotent on non-strings
        assert typographic_convert(None) is None
        assert typographic_convert(42) == 42
