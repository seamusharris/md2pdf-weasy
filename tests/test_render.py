"""Tests for front-matter parsing, includes, and the tracked_rows alias."""

import tempfile
from pathlib import Path

import pytest
import weasyprint
import yaml

from pdf.render import (
    _tracked_rows,
    md_to_html,
    parse_front_matter,
    resolve_tables_include,
    validate_front_matter,
)


def test_build_pdf_forwards_html_base_url(tmp_path, monkeypatch):
    markdown = tmp_path / "source.md"
    output = tmp_path / "output.pdf"
    markdown.write_text("![diagram](diagrams/example.svg)\n", encoding="utf-8")
    captured = {}

    class FakeHTML:
        def __init__(self, *, string, base_url):
            captured["html"] = string
            captured["base_url"] = base_url

        def write_pdf(self, output_path, *, stylesheets, pdf_variant=None):
            captured["output_path"] = output_path
            captured["stylesheets"] = stylesheets
            captured["pdf_variant"] = pdf_variant

    class FakeCSS:
        def __init__(self, *, string, base_url):
            self.string = string
            self.base_url = base_url

    monkeypatch.setattr(weasyprint, "HTML", FakeHTML)
    monkeypatch.setattr(weasyprint, "CSS", FakeCSS)

    from pdf.render import build_pdf

    result = build_pdf(
        str(markdown),
        str(output),
        base_url=markdown.parent.as_uri() + "/",
    )

    assert result == str(output)
    assert captured["base_url"] == markdown.parent.as_uri() + "/"
    assert "diagrams/example.svg" in captured["html"]
    assert captured["output_path"] == str(output)
    assert len(captured["stylesheets"]) == 1
    assert captured["pdf_variant"] == "pdf/ua-1"


class TestTrackedRowsAlias:
    """tracked_rows is the new name; tracked_teams remains a deprecated alias."""

    def test_new_key_works(self):
        assert _tracked_rows({'tracked_rows': ['Foo']}) == ['Foo']

    def test_old_alias_works_and_warns(self, caplog):
        result = _tracked_rows({'tracked_teams': ['Foo']})
        assert result == ['Foo']
        assert any('deprecated' in m for m in caplog.messages)

    def test_new_key_wins_when_both_present(self):
        meta = {'tracked_rows': ['New'], 'tracked_teams': ['Old']}
        assert _tracked_rows(meta) == ['New']

    def test_neither_key_returns_empty_list(self):
        assert _tracked_rows({}) == []


class TestParseFrontMatter:

    def test_no_front_matter_returns_empty_meta(self):
        meta, body = parse_front_matter("# Just markdown\n\nNo front matter.")
        assert meta == {}
        assert body == "# Just markdown\n\nNo front matter."

    def test_simple_front_matter_parsed(self):
        content = "---\ntitle: Test\ntheme: alpine\n---\n# Heading"
        meta, body = parse_front_matter(content)
        assert meta == {'title': 'Test', 'theme': 'alpine'}
        assert body == "# Heading"

    def test_empty_front_matter_is_empty_dict(self):
        content = "---\n---\n# Heading"
        meta, body = parse_front_matter(content)
        assert meta == {}
        assert body == "# Heading"

    def test_document_opening_with_thematic_break_is_not_front_matter(self):
        # A doc that opens with a `---` horizontal rule parses to a scalar, not
        # a mapping — it must be handed back untouched, not crash.
        content = "---\n# Heading\n\nIntro text\n\n---\n\nAfter the rule"
        meta, body = parse_front_matter(content)
        assert meta == {}
        assert body == content

    def test_malformed_yaml_is_tolerated(self, caplog):
        content = "---\ntitle: [unclosed\n---\n# Body"
        meta, body = parse_front_matter(content)
        assert meta == {}
        assert body == content

    def test_closing_delimiter_must_be_on_its_own_line(self):
        # A `---` embedded in a value should not terminate the front matter.
        content = "---\ntitle: A --- B\nsubtitle: x\n---\n# Body"
        meta, body = parse_front_matter(content)
        assert meta == {'title': 'A --- B', 'subtitle': 'x'}
        assert body == "# Body"


class TestMdToHtmlCodeProtection:

    def test_typography_does_not_touch_fenced_code(self):
        html = md_to_html('```\na -> b\n```', {})
        assert 'a -&gt; b' in html or 'a -> b' in html
        assert '→' not in html

    def test_typography_does_not_touch_inline_code(self):
        html = md_to_html('Use `x -> y` here.', {})
        assert '→' not in html
        # Prose arrows outside code still convert.
        html2 = md_to_html('go from a -> b', {})
        assert '→' in html2

    def test_tight_list_stays_tight(self):
        # Consecutive items must not be forced loose (no <p> wrapping in <li>).
        html = md_to_html('- one\n- two\n- three', {})
        assert '<li>one</li>' in html

    def test_blank_line_inserted_before_list_after_paragraph(self):
        # A list glued to the preceding paragraph is still recognised as a list.
        html = md_to_html('A paragraph.\n- item one\n- item two', {})
        assert '<ul>' in html
        assert '<li>item one</li>' in html

    def test_title_is_html_escaped(self):
        html = md_to_html('body', {'title': 'Q&A <live>'})
        assert '<h1>Q&amp;A &lt;live&gt;</h1>' in html

    def test_document_metadata_is_exposed_to_html_and_pdf(self):
        html = md_to_html('body', {
            'title': 'Training & Review',
            'author': 'Netball Coaching',
            'subject': 'Private coaching reference',
            'keywords': ['netball', 'coaching'],
            'lang': 'en-AU',
        })

        assert '<html lang="en-AU">' in html
        assert '<meta name="author" content="Netball Coaching">' in html
        assert '<meta name="description" content="Private coaching reference">' in html
        assert '<meta name="keywords" content="netball, coaching">' in html
        assert '<title>Training &amp; Review</title>' in html

    def test_consecutive_bold_label_lines_become_separate_paragraphs(self):
        # Generated field summaries glue **Label:** lines together; they must
        # not collapse into one run-together paragraph.
        src = (
            "**Rehab stage:** running\n"
            "**Focus:** stability\n"
            "**Tone:** encouraging"
        )
        html = md_to_html(src, {})
        assert html.count('<strong>Rehab stage:</strong>') == 1
        # Three distinct paragraphs, one per field.
        assert '<strong>Focus:</strong> stability</p>' in html
        assert '<strong>Tone:</strong> encouraging</p>' in html

    def test_bold_label_with_value_on_next_line_stays_one_paragraph(self):
        src = "**Focus:**\nmobility work"
        html = md_to_html(src, {})
        assert '<strong>Focus:</strong>\nmobility work</p>' in html

    def test_ordinary_prose_starting_with_bold_is_not_split(self):
        # No colon → not a label; soft-wrapped prose is left intact.
        src = "This keeps going\n**and this** is still the same sentence."
        html = md_to_html(src, {})
        assert html.count('<p>') == 1


class TestValidateFrontMatter:

    def test_known_keys_produce_no_warnings(self):
        warnings = validate_front_matter({
            'title': 'x',
            'theme': 'alpine',
            'h2_page_break': True,
        })
        assert warnings == []

    def test_unknown_key_produces_warning(self):
        warnings = validate_front_matter({'nonsense_key': 'value'})
        assert len(warnings) == 1
        assert 'nonsense_key' in warnings[0]

    def test_mistyped_key_produces_warning(self):
        warnings = validate_front_matter({'h2_page_break': 'should-be-bool'})
        assert len(warnings) == 1
        assert 'h2_page_break' in warnings[0]

    def test_mistyped_columns_warns_and_uses_default_widths(self, caplog):
        content = """---
columns:
  - Team
---
| Team | W |
|------|---|
| Warrandyte | 4 |
"""
        metadata, body = parse_front_matter(content)

        assert any(
            "front matter 'columns': expected dict, got list" in message
            for message in caplog.messages
        )
        assert md_to_html(body, metadata) == md_to_html(body, {})

    def test_semantically_invalid_width_controls_warn_once_and_normalise(self, caplog):
        content = """---
table_widths: SOMETIMES
orientation: sideways
page_width_em: -10
columns:
  Team: 12px
---
| Team | W |
|------|---|
| Warrandyte | 4 |
"""
        metadata, body = parse_front_matter(content)

        assert metadata == {
            "table_widths": True,
            "orientation": "portrait",
            "columns": {},
        }
        assert len(caplog.messages) == 4
        assert all("12px" not in message for message in caplog.messages)

        caplog.clear()
        md_to_html(body, metadata)
        assert caplog.messages == []

    def test_direct_md_to_html_non_mapping_metadata_warns_and_continues(self, caplog):
        html = md_to_html("| Team | W |\n|---|---|\n| A | 1 |", [])

        assert "<table" in html
        assert caplog.messages == [
            "front matter: expected a mapping; using empty metadata"
        ]


class TestResolveTablesInclude:

    def test_no_include_is_noop(self):
        meta = {'title': 'x'}
        result = resolve_tables_include(meta, md_path=None)
        assert 'tables' not in result

    def test_loads_shared_layouts(self, tmp_path):
        shared = tmp_path / "tables.yml"
        shared.write_text(yaml.safe_dump({
            'ladder': {'columns': [{'name': 'Team'}, {'name': 'W'}]},
        }))
        meta = {'tables_include': str(shared)}
        result = resolve_tables_include(meta, md_path=None)
        assert 'ladder' in result['tables']

    def test_per_doc_tables_override_shared(self, tmp_path):
        shared = tmp_path / "tables.yml"
        shared.write_text(yaml.safe_dump({
            'ladder': {'columns': [{'name': 'Team', 'width': 50}]},
        }))
        meta = {
            'tables_include': str(shared),
            'tables': {'ladder': {'columns': [{'name': 'Team', 'width': 80}]}},
        }
        result = resolve_tables_include(meta, md_path=None)
        # Per-doc width (80) wins, not the shared file's (50)
        assert result['tables']['ladder']['columns'][0]['width'] == 80

    def test_missing_include_file_is_tolerated(self, caplog):
        meta = {'tables_include': '/nonexistent/path/tables.yml'}
        result = resolve_tables_include(meta, md_path=None)
        # No crash, no tables key added
        assert 'tables' not in result
        assert any('not found' in m for m in caplog.messages)

    def test_resolves_relative_to_md_file(self, tmp_path):
        shared = tmp_path / "shared.yml"
        shared.write_text(yaml.safe_dump({'foo': {'columns': []}}))
        md = tmp_path / "doc.md"
        md.write_text("")
        # tables_include is relative to the md file's directory
        meta = {'tables_include': 'shared.yml'}
        result = resolve_tables_include(meta, md_path=str(md))
        assert 'foo' in result['tables']
