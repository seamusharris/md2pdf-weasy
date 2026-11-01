"""Privacy-conscious, deterministic diagnostics for the existing table passes.

Collectors never retain table HTML, cell text, captions, or column names. Layout
keys and author-provided table ids are intentional identifiers in schema v1.
"""

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import asdict, dataclass, is_dataclass
import html
import math
import re

from .resources import _safe_reference


SCHEMA_VERSION = 1
DIAGNOSTIC_CODES = frozenset({
    "tables.layout_invalid", "tables.match_ambiguous", "tables.required_unapplied", "tables.layout_unused",
    "tables.structure_unsupported", "tables.width_scaled", "tables.overflow_unresolved",
    "tables.include_missing", "tables.include_invalid",
})
DEFAULT_STRICT_CODES = frozenset({
    "tables.layout_invalid", "tables.match_ambiguous", "tables.required_unapplied",
    "tables.structure_unsupported", "tables.overflow_unresolved",
    "tables.include_missing", "tables.include_invalid",
})


@dataclass(frozen=True)
class StrictPolicy:
    """Select stable diagnostic codes that make strict conversion fail."""

    codes: frozenset[str] = DEFAULT_STRICT_CODES

    def __post_init__(self):
        if isinstance(self.codes, str):
            raise ValueError("strict codes must be a collection of known codes")
        codes = frozenset(self.codes)
        if codes - DIAGNOSTIC_CODES:
            raise ValueError("unknown strict diagnostic code")
        object.__setattr__(self, "codes", codes)


class StrictDiagnosticsError(ValueError):
    """A completed diagnostics report failed the requested strict policy."""

    def __init__(self, report, codes):
        self.report = deepcopy(report)
        self.codes = tuple(sorted(set(codes)))
        super().__init__("strict table diagnostics failed: " + ", ".join(self.codes))


class DiagnosticsReport(dict):
    """JSON-safe schema-v1 value, also usable by ordinary mapping consumers."""

    def to_dict(self):
        return deepcopy(dict(self))


@dataclass(frozen=True)
class BuildResult:
    """Saved PDF location and its diagnostics, without retaining PDF bytes."""

    output_path: str
    diagnostics: DiagnosticsReport


def _finite_values(value):
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {key: _finite_values(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_finite_values(item) for item in value]
    return value


def evaluate_strict(report, strict=None):
    """Raise only for selected codes; an ordinary unused layout is informational."""
    if strict is None or strict is False:
        return
    policy = StrictPolicy() if strict is True else strict
    if not isinstance(policy, StrictPolicy):
        raise TypeError("strict must be a bool or StrictPolicy")
    failed = {item["code"] for item in report["diagnostics"]
              if item["code"] in policy.codes}
    if failed:
        raise StrictDiagnosticsError(report, failed)


class DiagnosticsCollector:
    """Private pass observer; only explicit, bounded diagnostic facts are stored."""

    def __init__(self, layout_sources=None):
        self.layout_sources = dict(layout_sources or {})
        self.tables = []
        self.resources = []
        self.diagnostics = []
        self.layouts = {}
        self.applied = set()

    def table(self, index, table_html):
        while len(self.tables) < index:
            self.tables.append({
                "index": len(self.tables) + 1, "id": None,
                "origin": "unchanged", "layout_key": None,
                "layout_source": None, "preset_id": None,
                "matching_layout_keys": [], "widths": [], "alignment": [],
                "fit": None, "skip_reason": None,
            })
        record = self.tables[index - 1]
        if not record['alignment']:
            # Inspect attributes only, never retain a cell's text or HTML.
            rows = re.findall(r'<tr\b[^>]*>(.*?)</tr>', table_html, re.DOTALL)
            author = {}
            count = 0
            for row in rows:
                tags = re.findall(r'<t[dh]\b[^>]*>', row)
                count = max(count, len(tags))
                for position, tag in enumerate(tags, 1):
                    align = re.search(r'text-align\s*:\s*(left|right|center)\b', tag, re.IGNORECASE)
                    if align:
                        author.setdefault(position, set()).add(align[1].lower())
                    else:
                        classes = re.search(r'\sclass\s*=\s*([\"\'])(.*?)\1', tag, re.DOTALL)
                        if classes:
                            tokens = classes[2].split()
                            if 'num' in tokens:
                                author.setdefault(position, set()).add('right')
                            elif 'ctr' in tokens:
                                author.setdefault(position, set()).add('center')
            record['alignment'] = [
                {'column_index': position, 'value': (next(iter(author[position])) if len(author[position]) == 1 else 'mixed') if position in author else 'left',
                 'source': 'author' if position in author else 'unchanged'}
                for position in range(1, count + 1)]
        opening = re.match(r"<table\b[^>]*>", table_html, re.IGNORECASE)
        if opening:
            identifier = re.search(r"\sid\s*=\s*([\"'])(.*?)\1", opening[0], re.DOTALL)
            if identifier:
                record["id"] = html.unescape(identifier[2])
        if record["origin"] == "unchanged" and re.search(r"<colgroup\b", table_html, re.IGNORECASE):
            record["origin"] = "author_colgroup"
            group = re.search(r'<colgroup\b[^>]*>(.*?)</colgroup>', table_html, re.DOTALL | re.IGNORECASE)
            if group:
                for position, tag in enumerate(re.findall(r'<col\b[^>]*>', group[1], re.IGNORECASE), 1):
                    width = re.search(r'\bwidth\s*:\s*([0-9]+(?:\.[0-9]+)?)(%|em)(?=[;\s\"\'])', tag)
                    if width:
                        record['widths'].append({'column_index': position,
                                                 'value': float(width[1]), 'unit': width[2],
                                                 'source': 'author'})
        return record

    def configure_layouts(self, metadata):
        layouts = metadata.get("tables", {}) if isinstance(metadata, Mapping) else {}
        if not isinstance(layouts, Mapping):
            self.add("tables.layout_invalid", severity="warning")
            return
        for key, layout in layouts.items():
            if not isinstance(key, str):
                self.add("tables.layout_invalid", severity="warning")
                continue
            self.layouts[key] = {
                "required": isinstance(layout, Mapping) and layout.get("required") is True,
                "preset_id": layout.get("preset") if isinstance(layout, Mapping) and isinstance(layout.get("preset"), str)
                and re.fullmatch(r'[a-z][a-z0-9-]*-v[1-9][0-9]*', layout['preset']) else None,
            }

    def add(self, code, *, severity="warning", table_index=None, layout_key=None):
        if code not in DIAGNOSTIC_CODES:
            raise ValueError("unknown diagnostic code")
        item = {"code": code, "severity": severity}
        if table_index is not None:
            item["table_index"] = table_index
        if isinstance(layout_key, str):
            item["layout_key"] = layout_key
        if item not in self.diagnostics:
            self.diagnostics.append(item)

    add_diagnostic = add

    def add_resource(self, event):
        """Retain resolution facts only; content and arbitrary payloads are excluded."""
        if is_dataclass(event):
            event = asdict(event)
        elif hasattr(event, 'to_dict'):
            event = event.to_dict()
        if not isinstance(event, Mapping):
            raise TypeError('resource event must be a mapping or dataclass')
        safe_event = {key: value for key, value in event.items()
                      if key in {'kind', 'status', 'reference', 'path', 'resolved_path', 'resolved', 'base_path', 'source'}
                      and (value is None or isinstance(value, (str, bool, int, float)))}
        if "reference" in safe_event:
            safe_event["reference"] = _safe_reference(safe_event["reference"])
        self.resources.append(safe_event)

    def layout_applied(self, record, key):
        self.applied.add(key)
        preset_id = self.layouts.get(key, {}).get("preset_id")
        record.update(origin="preset" if preset_id else "declared",
                      layout_key=key, layout_source=self.layout_sources.get(key, "document"),
                      preset_id=preset_id, skip_reason=None)

    def build_report(self):
        diagnostics = deepcopy(self.diagnostics)
        for key, layout in self.layouts.items():
            if key not in self.applied:
                diagnostics.append({"code": "tables.required_unapplied" if layout["required"] else "tables.layout_unused",
                                    "severity": "error" if layout["required"] else "info",
                                    "layout_key": key})
        return DiagnosticsReport(_finite_values({"schema_version": SCHEMA_VERSION,
                "tables": deepcopy(self.tables), "resources": deepcopy(self.resources), "diagnostics": diagnostics}))

    @property
    def report(self):
        return self.build_report()
