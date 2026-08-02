"""Contract tests for table-width front-matter normalization."""

import math

import pytest

from pdf.width_metadata import normalise_width_metadata


def test_normalises_valid_controls_without_mutating_the_caller():
    columns = {" Team ": " TEXT ", "Venue": "12.50EM", "Count": 8}
    metadata = {
        "table_widths": " OFF ",
        "orientation": " LANDSCAPE ",
        "page_width_em": 76,
        "columns": columns,
    }

    result, warnings = normalise_width_metadata(metadata)

    assert result == {
        "table_widths": False,
        "orientation": "landscape",
        "page_width_em": 76.0,
        "columns": {"team": "text", "venue": "12.5em", "count": 8.0},
    }
    assert warnings == []
    assert metadata["table_widths"] == " OFF "
    assert metadata["columns"] is columns
    assert columns == {" Team ": " TEXT ", "Venue": "12.50EM", "Count": 8}


def test_normalisation_is_idempotent_and_copies_nested_columns():
    first, warnings = normalise_width_metadata({"columns": {"Team": "12em"}})
    second, second_warnings = normalise_width_metadata(first)

    assert second == first
    assert second["columns"] is not first["columns"]
    assert warnings == second_warnings == []


@pytest.mark.parametrize("value", [True, False, 0, -1, math.inf, -math.inf, math.nan])
def test_page_width_rejects_booleans_and_non_positive_or_non_finite_values(value):
    result, warnings = normalise_width_metadata({"page_width_em": value})

    assert "page_width_em" not in result
    assert warnings == [
        "front matter 'page_width_em': expected a positive finite number; "
        "using the orientation default"
    ]


@pytest.mark.parametrize(
    "value",
    [True, False, 0, -2, 10 ** 1000, math.inf, math.nan, "", "  ", "0em",
     "-1em", "infem", "nanem", "12px", "calc(12em)",
     '12em\";color:red', [], {}, None],
)
def test_invalid_column_widths_are_ignored_without_echoing_payload(value):
    result, warnings = normalise_width_metadata({
        "columns": {"Good": "label", "Bad": value},
    })

    assert result["columns"] == {"good": "label"}
    assert warnings == ["front matter 'columns': ignored entry with invalid width"]
    if str(value):
        assert str(value) not in warnings[0]


def test_invalid_controls_use_safe_defaults_and_preserve_other_metadata():
    result, warnings = normalise_width_metadata({
        "title": "Report",
        "table_widths": "sometimes",
        "orientation": "sideways",
        "columns": {7: "text", "": "label", "Team": "prose"},
    })

    assert result == {
        "title": "Report",
        "table_widths": True,
        "orientation": "portrait",
        "columns": {"team": "prose"},
    }
    assert warnings == [
        "front matter 'table_widths': expected bool or off/none/legacy; using true",
        "front matter 'orientation': expected portrait or landscape; using portrait",
        "front matter 'columns': ignored entry with invalid header",
        "front matter 'columns': ignored entry with invalid header",
    ]


@pytest.mark.parametrize("metadata", [[], "", 0, False])
def test_falsey_non_mapping_metadata_warns_and_falls_back(metadata):
    result, warnings = normalise_width_metadata(metadata)

    assert result == {}
    assert warnings == ["front matter: expected a mapping; using empty metadata"]


def test_huge_page_width_falls_back_instead_of_overflowing():
    result, warnings = normalise_width_metadata({"page_width_em": 10 ** 1000})

    assert "page_width_em" not in result
    assert len(warnings) == 1
