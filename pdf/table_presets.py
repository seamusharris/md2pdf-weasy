"""Pure expansion of opt-in table presets into ordinary declared layouts.

Preset widths are relative weights, not automatic-width em values. Existing
layouts without a ``preset`` key retain their historical behavior.
"""

from collections.abc import Mapping
from copy import deepcopy
from functools import lru_cache
from importlib.resources import files
import math
import re

import yaml


_PRESET_ID = re.compile(r"[a-z][a-z0-9-]*-v[1-9][0-9]*")
_CSS_CLASSES = re.compile(r"[A-Za-z_][A-Za-z0-9_-]*(?:\s+[A-Za-z_][A-Za-z0-9_-]*)*")
_LAYOUT_FIELDS = frozenset({"columns", "css_class", "highlight", "required"})
_COLUMN_FIELDS = frozenset({"name", "width", "align"})


def _positive_weight(value):
    # Keep this contract identical to declared-layout validation downstream.
    # Exotic numeric objects must not pass expansion only to be skipped later.
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        return math.isfinite(float(value)) and value > 0
    except (ValueError, TypeError, OverflowError):
        return False


def _valid_layout(layout, *, require_widths=False):
    """Validate only new preset-derived layouts, not the legacy schema."""
    if not isinstance(layout, Mapping) or set(layout) - _LAYOUT_FIELDS:
        return False
    if "required" in layout and type(layout["required"]) is not bool:
        return False
    columns = layout.get("columns")
    if not isinstance(columns, list) or not columns:
        return False
    weights = []
    for column in columns:
        if not isinstance(column, Mapping) or set(column) - _COLUMN_FIELDS:
            return False
        name = column.get("name")
        if not isinstance(name, str) or not name.strip():
            return False
        if "width" in column:
            if not _positive_weight(column["width"]):
                return False
            weights.append(float(column["width"]))
        elif require_widths:
            return False
        if "align" in column and column["align"] not in ("left", "right", "center"):
            return False
    try:
        if not math.isfinite(math.fsum(weights)):
            return False
    except OverflowError:
        return False
    if "css_class" in layout:
        css_class = layout["css_class"]
        if not isinstance(css_class, str) or (css_class and not _CSS_CLASSES.fullmatch(css_class)):
            return False
    if "highlight" in layout and layout["highlight"] not in ("row", "bold-only", "none"):
        return False
    return True


@lru_cache(maxsize=1)
def _load_catalog():
    """Read trusted package data once; catalog defects are operational errors."""
    catalog = yaml.safe_load(files("pdf").joinpath("table_presets.yml").read_text(encoding="utf-8"))
    if (not isinstance(catalog, Mapping)
            or type(catalog.get("schema_version")) is not int
            or catalog["schema_version"] != 1
            or not isinstance(catalog.get("presets"), Mapping)):
        raise ValueError("invalid bundled table preset catalog schema")
    for identifier, layout in catalog["presets"].items():
        if (not isinstance(identifier, str) or not _PRESET_ID.fullmatch(identifier)
                or not _valid_layout(layout, require_widths=True)):
            raise ValueError("invalid bundled table preset definition")
    return catalog["presets"]


def expand_table_presets(metadata):
    """Return ``(metadata_copy, warnings)`` without modifying caller inputs."""
    return _expand_table_presets(metadata)


def _expand_table_presets(metadata, *, _collector=None):
    """Return ``(metadata_copy, warnings)`` without modifying caller inputs.

    Explicit layout fields override preset defaults; ``columns`` replaces the
    complete list. Invalid preset layouts are omitted so the normal automatic
    width pass (when enabled) can handle their tables. No filesystem paths or
    imports can be selected by a document's preset reference.
    """
    if not isinstance(metadata, Mapping):
        return {}, ["front matter: expected a mapping; using empty metadata"]
    result = dict(metadata)
    tables = metadata.get("tables")
    if not isinstance(tables, Mapping):
        return result, []
    expanded = {}
    warnings = []
    for name, layout in tables.items():
        if not isinstance(layout, Mapping) or "preset" not in layout:
            expanded[name] = deepcopy(layout)
            continue
        identifier = layout["preset"]
        if not isinstance(identifier, str) or not _PRESET_ID.fullmatch(identifier):
            warnings.append("front matter 'tables.preset': invalid preset identifier; skipping layout")
            if _collector is not None:
                _collector.add("tables.layout_invalid", layout_key=name)
            continue
        preset = _load_catalog().get(identifier)
        if preset is None:
            warnings.append("front matter 'tables.preset': unknown preset; skipping layout")
            if _collector is not None:
                _collector.add("tables.layout_invalid", layout_key=name)
            continue
        resolved = {**deepcopy(preset), **deepcopy({k: v for k, v in layout.items() if k != "preset"})}
        if not _valid_layout(resolved):
            warnings.append("front matter 'tables.preset': invalid layout override; skipping layout")
            if _collector is not None:
                _collector.add("tables.layout_invalid", layout_key=name)
            continue
        expanded[name] = resolved
    result["tables"] = expanded
    return result, warnings
