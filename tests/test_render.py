"""Tests for front-matter parsing, includes, and the tracked_rows alias."""

import tempfile
from pathlib import Path

import pytest
import yaml

from pdf.render import (
    _tracked_rows,
    parse_front_matter,
    resolve_tables_include,
    validate_front_matter,
)


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
