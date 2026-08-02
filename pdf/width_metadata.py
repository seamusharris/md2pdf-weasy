"""Pure normalization for automatic table-width front matter."""

import math
import numbers
import re
from collections.abc import Mapping


KNOWN_COLUMN_TYPES = frozenset({
    "stat", "num", "time", "pct", "score", "date", "label", "text", "prose",
})

_EM_WIDTH_RE = re.compile(r"(?:\d+(?:\.\d*)?|\.\d+)em", re.IGNORECASE)
_DISABLE_ALIASES = frozenset({"off", "none", "legacy"})


def _positive_finite_number(value):
    if not isinstance(value, numbers.Real) or isinstance(value, bool):
        return None
    try:
        converted = float(value)
    except (OverflowError, TypeError, ValueError):
        return None
    return converted if math.isfinite(converted) and converted > 0 else None


def _normalise_header(value):
    if not isinstance(value, str):
        return None
    normalized = re.sub(r"\s+", " ", value).strip().lower()
    return normalized or None


def _normalise_column_value(value):
    numeric = _positive_finite_number(value)
    if numeric is not None:
        return numeric
    if not isinstance(value, str):
        return None
    normalized = value.strip().lower()
    if normalized in KNOWN_COLUMN_TYPES:
        return normalized
    if not _EM_WIDTH_RE.fullmatch(normalized):
        return None
    width = float(normalized[:-2])
    if not math.isfinite(width) or width <= 0:
        return None
    return f"{width:g}em"


def normalise_width_metadata(metadata):
    """Return ``(normalized_copy, warnings)`` for table-width controls.

    The function is deliberately pure and idempotent. Warning strings describe
    fields and fallbacks without echoing untrusted values.
    """
    if not isinstance(metadata, Mapping):
        return {}, ["front matter: expected a mapping; using empty metadata"]

    result = dict(metadata)
    warnings = []

    if "table_widths" in result:
        value = result["table_widths"]
        if isinstance(value, bool):
            pass
        elif isinstance(value, str) and value.strip().lower() in _DISABLE_ALIASES:
            result["table_widths"] = False
        else:
            result["table_widths"] = True
            warnings.append(
                "front matter 'table_widths': expected bool or off/none/legacy; "
                "using true"
            )

    if "orientation" in result:
        value = result["orientation"]
        if isinstance(value, str) and value.strip().lower() in {"portrait", "landscape"}:
            result["orientation"] = value.strip().lower()
        else:
            result["orientation"] = "portrait"
            warnings.append(
                "front matter 'orientation': expected portrait or landscape; "
                "using portrait"
            )

    if "page_width_em" in result:
        value = result["page_width_em"]
        numeric = _positive_finite_number(value)
        if numeric is not None:
            result["page_width_em"] = numeric
        else:
            result.pop("page_width_em")
            warnings.append(
                "front matter 'page_width_em': expected a positive finite number; "
                "using the orientation default"
            )

    if "columns" in result:
        value = result["columns"]
        if not isinstance(value, Mapping):
            result["columns"] = {}
            warnings.append(
                f"front matter 'columns': expected dict, got {type(value).__name__}; "
                "using {}"
            )
        else:
            columns = {}
            for header, width in value.items():
                normalized_header = _normalise_header(header)
                if normalized_header is None:
                    warnings.append(
                        "front matter 'columns': ignored entry with invalid header"
                    )
                    continue
                normalized_width = _normalise_column_value(width)
                if normalized_width is None:
                    warnings.append(
                        "front matter 'columns': ignored entry with invalid width"
                    )
                    continue
                columns[normalized_header] = normalized_width
            result["columns"] = columns

    return result, warnings
