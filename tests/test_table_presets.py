"""Additive, exact-shape table preset contracts; no package builds required."""

from copy import deepcopy
from fractions import Fraction
from importlib.resources import files
from pathlib import Path
import re
import tomllib

import pytest

from pdf.postprocess import postprocess
from pdf.render import md_to_html, parse_front_matter, resolve_tables_include
from pdf.table_presets import _load_catalog, expand_table_presets


HEADERS = ["Team", "P", "W", "L", "D", "GF", "GA", "%"]
CELLS = ["North", "12", "8", "4", "0", "244", "187", "130.5"]
MARKDOWN = "| " + " | ".join(HEADERS) + " |\n| " + " | ".join(["---"] * 8) + " |\n| " + " | ".join(CELLS) + " |"
HTML = ("<table><caption>Standings</caption><thead><tr>"
        + "".join(f'<th scope="col">{h}</th>' for h in HEADERS)
        + "</tr></thead><tbody><tr>"
        + "".join(f"<td>{c}</td>" for c in CELLS)
        + "</tr></tbody></table>")


def _metadata(**overrides):
    return {"tables": {"ladder": {"preset": "netball-ladder-v1", **overrides}}}


def test_catalog_is_valid_explicit_and_packaged():
    catalog = _load_catalog()
    assert list(catalog) == ["netball-ladder-v1"]
    columns = catalog["netball-ladder-v1"]["columns"]
    assert [c["name"] for c in columns] == HEADERS
    assert [c["width"] for c in columns] == [24, 6, 6, 6, 6, 8, 8, 10]
    assert files("pdf").joinpath("table_presets.yml").is_file()
    project = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    assert "table_presets.yml" in project["tool"]["setuptools"]["package-data"]["pdf"]


def test_expansion_is_non_mutating_idempotent_and_does_not_share_catalog():
    original = _metadata(highlight="bold-only")
    before = deepcopy(original)
    expanded, warnings = expand_table_presets(original)
    second, second_warnings = expand_table_presets(expanded)
    assert original == before
    assert expanded == second
    assert warnings == second_warnings == []
    assert expanded["tables"]["ladder"]["highlight"] == "bold-only"
    expanded["tables"]["ladder"]["columns"][0]["width"] = 999
    assert second["tables"]["ladder"]["columns"][0]["width"] == 24
    assert _load_catalog()["netball-ladder-v1"]["columns"][0]["width"] == 24


def test_scalar_overrides_and_complete_column_replacement():
    replacement = [{"name": "Value", "width": 5, "align": "center"}]
    expanded, warnings = expand_table_presets(_metadata(
        columns=replacement, css_class="custom-table", highlight="none"))
    layout = expanded["tables"]["ladder"]
    assert warnings == []
    assert layout == {"columns": replacement, "css_class": "custom-table", "highlight": "none"}
    assert layout["columns"] is not replacement


@pytest.mark.parametrize("identifier", [None, True, 1, [], {}, "../netball-ladder-v1", "https://example.org/v1", "netball-ladder-v99", " netball-ladder-v1 "])
def test_bad_identifier_skips_only_affected_layout_and_does_not_echo_values(identifier):
    metadata = {"tables": {"bad": {"preset": identifier}, "good": {"columns": [{"name": "Other"}]}}}
    expanded, warnings = expand_table_presets(metadata)
    assert list(expanded["tables"]) == ["good"]
    assert len(warnings) == 1
    assert "skipping layout" in warnings[0]
    assert "example.org" not in warnings[0]


@pytest.mark.parametrize("overrides", [
    {"columns": []}, {"columns": "wrong"}, {"columns": [None]},
    {"columns": [{"name": "Value", "align": "sideways"}]},
    {"columns": [{"name": "Value", "extra": True}]},
    {"columns": [{"name": ""}]},
    {"css_class": 1}, {"css_class": 'bad"class'}, {"highlight": "invalid"},
    {"unknown_field": True},
])
def test_invalid_override_skips_layout(overrides):
    expanded, warnings = expand_table_presets(_metadata(**overrides))
    assert expanded["tables"] == {}
    assert warnings == ["front matter 'tables.preset': invalid layout override; skipping layout"]


@pytest.mark.parametrize("weight", [
    True, False, 0, -1, float("inf"), float("nan"), "12em", "12", None,
    Fraction(1, 2), 10 ** 400,
])
def test_replacement_widths_reject_non_positive_non_finite_and_non_numeric_weights(weight):
    expanded, warnings = expand_table_presets(_metadata(columns=[{"name": "Value", "width": weight}]))
    assert expanded["tables"] == {}
    assert len(warnings) == 1


def test_overflowing_sum_is_rejected():
    expanded, warnings = expand_table_presets(_metadata(columns=[
        {"name": "One", "width": 1e308}, {"name": "Two", "width": 1e308},
    ]))
    assert expanded["tables"] == {}
    assert len(warnings) == 1


def test_ordinary_ampersand_headers_and_multiple_class_tokens_are_supported():
    metadata = _metadata(columns=[{"name": "For & Against", "width": 1}], css_class="custom-table secondary")
    source = "| For & Against |\n|---|\n| 42 |"
    result = md_to_html(source, metadata)
    assert 'class="custom-table secondary"' in result
    assert "width:100.0%" in result
    assert postprocess(result, metadata) == result


def test_non_preset_layout_retains_legacy_fields_and_widths():
    metadata = {"tables": {"legacy": {"columns": [{"name": "Other", "width": 1}], "extra": "untouched"}}}
    result, warnings = expand_table_presets(metadata)
    assert result == metadata
    assert result["tables"] is not metadata["tables"]
    assert warnings == []


@pytest.mark.parametrize("processor, source", [(postprocess, HTML), (md_to_html, MARKDOWN)])
def test_all_direct_processing_boundaries_expand_presets(processor, source):
    result = processor(source, _metadata())
    assert 'class="netball-ladder"' in result
    assert 'width:32.4%' in result
    assert result.count("<colgroup>") == 1
    assert "text-align:right" in result


def test_parse_accepts_preset_without_unknown_front_matter_warning(caplog):
    metadata, body = parse_front_matter("---\ntables:\n  ladder:\n    preset: netball-ladder-v1\n---\n" + MARKDOWN)
    assert metadata == _metadata()
    assert md_to_html(body, metadata).count("<colgroup>") == 1
    assert not caplog.messages


def test_disabled_automatic_widths_does_not_disable_explicit_preset():
    result = postprocess(HTML, {**_metadata(), "table_widths": False, "columns": {"Team": "99em"}})
    assert "width:32.4%" in result
    assert "99em" not in result


def test_unknown_preset_warns_and_falls_back_to_automatic_widths(caplog):
    result = postprocess(HTML, {"tables": {"bad": {"preset": "unknown-v1"}}})
    assert "<colgroup>" in result
    assert re.search(r'width:[\d.]+em', result)
    assert caplog.messages == ["front matter 'tables.preset': unknown preset; skipping layout"]


def test_unknown_preset_with_automatic_widths_disabled_leaves_widths_untouched():
    result = postprocess(HTML, {"tables": {"bad": {"preset": "unknown-v1"}}, "table_widths": False})
    assert "<colgroup>" not in result


def test_preset_matches_exact_shape_not_subsets_or_reordered_columns():
    reordered = MARKDOWN.replace("Team | P", "P | Team")
    result = md_to_html(reordered, _metadata())
    assert 'class="netball-ladder"' not in result
    assert "width:32.4%" not in result
    assert "<colgroup>" in result


def test_caption_author_colgroup_structure_and_repeat_processing_are_preserved():
    result = postprocess(HTML, _metadata())
    assert result.index("<caption>") < result.index("<colgroup>")
    assert result.count('scope="col"') == 8
    assert postprocess(result, _metadata()) == result
    author = HTML.replace("<caption>", '<colgroup><col style="width:7em"></colgroup><caption>', 1)
    assert "width:7em" in postprocess(author, _metadata())
    assert "width:32.4%" not in postprocess(author, _metadata())
    spanning = HTML.replace("<td>North</td>", '<td colspan="2">North</td>', 1)
    assert "<colgroup>" not in postprocess(spanning, _metadata())


def test_include_merge_retains_whole_layout_replacement_and_preset_scalar_overrides(tmp_path):
    shared = tmp_path / "tables.yml"
    shared.write_text("ladder:\n  preset: netball-ladder-v1\n  highlight: none\n", encoding="utf-8")
    metadata = {"tables_include": str(shared)}
    loaded = resolve_tables_include(metadata)
    expanded, warnings = expand_table_presets(loaded)
    assert expanded["tables"]["ladder"]["highlight"] == "none"
    assert warnings == []
    loaded = resolve_tables_include({"tables_include": str(shared), **_metadata(css_class="local")})
    expanded, warnings = expand_table_presets(loaded)
    assert expanded["tables"]["ladder"]["css_class"] == "local"
    assert "highlight" not in expanded["tables"]["ladder"]
