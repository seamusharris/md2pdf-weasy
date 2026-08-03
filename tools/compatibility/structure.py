"""Pure structural evidence extraction and compatibility classification."""

from __future__ import annotations

from html.parser import HTMLParser
import hashlib
import re
from pathlib import Path
from typing import Any

from .model import (
    CHECK_IDS, MAX_PAGES_PER_MODE, MAX_PDF_BYTES, CompatibilityError,
    canonical_bytes, sha256_file, validate_pdf_limits,
)


_SPACE = re.compile(r"\s+")
_WIDTH = re.compile(r"(?:^|;)\s*width\s*:\s*([^;]+)", re.I)


def _clean(value: str) -> str:
    # v0.1.0 applied typographic dashes inside date-like cells. Treat this as
    # presentation, while retaining the exact HTML artifact hash separately.
    return _SPACE.sub(" ", value.replace("\u2013", "-").replace("\u2014", "-")).strip()


class _Tables(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tables: list[dict[str, Any]] = []
        self.table: dict[str, Any] | None = None
        self.row: list[dict[str, Any]] | None = None
        self.cell: dict[str, Any] | None = None
        self.caption: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = {key: value or "" for key, value in attrs}
        if tag == "table":
            if self.table is not None:
                raise CompatibilityError("nested tables are unsupported", category="verify", phase="html")
            self.table = {
                "id": attributes.get("id", ""),
                "classes": sorted(attributes.get("class", "").split()),
                "caption": "", "columns": [], "rows": [],
            }
        elif self.table is not None and tag == "caption":
            self.caption = []
        elif self.table is not None and tag == "tr":
            self.row = []
        elif self.row is not None and tag in {"th", "td"}:
            self.cell = {
                "tag": tag, "text": [],
                "id": attributes.get("id", ""),
                "scope": attributes.get("scope", ""),
                "headers": attributes.get("headers", ""),
            }
        elif self.table is not None and tag == "col":
            match = _WIDTH.search(attributes.get("style", ""))
            self.table["columns"].append({
                "class": attributes.get("class", ""),
                "width": _clean(match.group(1)) if match else "",
            })

    def handle_data(self, data: str) -> None:
        if self.cell is not None:
            self.cell["text"].append(data)
        if self.caption is not None:
            self.caption.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"th", "td"} and self.cell is not None and self.row is not None:
            self.cell["text"] = _clean("".join(self.cell["text"]))
            self.row.append(self.cell)
            self.cell = None
        elif tag == "tr" and self.row is not None and self.table is not None:
            if self.row:
                self.table["rows"].append(self.row)
            self.row = None
        elif tag == "caption" and self.caption is not None and self.table is not None:
            self.table["caption"] = _clean("".join(self.caption))
            self.caption = None
        elif tag == "table" and self.table is not None:
            self.tables.append(self.table)
            self.table = None


def html_evidence(path: Path) -> dict[str, Any]:
    parser = _Tables()
    parser.feed(path.read_text(encoding="utf-8"))
    if parser.table is not None:
        raise CompatibilityError("unterminated table", category="verify", phase="html")
    tables = parser.tables
    semantic = [
        {"id": table["id"], "caption": table["caption"], "rows": table["rows"]}
        for table in tables
    ]
    return {
        "sha256": sha256_file(path),
        "table_count": len(tables),
        "tables": tables,
        "semantic_sha256": hashlib.sha256(canonical_bytes(semantic)).hexdigest(),
        "content_sha256": hashlib.sha256(canonical_bytes([
            [[cell["text"] for cell in row] for row in table["rows"]]
            for table in tables
        ])).hexdigest(),
    }


def pdf_evidence(path: Path, *, case: str | None = None) -> dict[str, Any]:
    pdf_bytes = path.stat().st_size
    validate_pdf_limits(pdf_bytes, 0)
    from pypdf import PdfReader
    try:
        reader = PdfReader(path, strict=True)
        validate_pdf_limits(pdf_bytes, len(reader.pages))
        root = reader.trailer["/Root"]
        metadata = reader.metadata or {}
        text = "\n".join(_clean(page.extract_text() or "") for page in reader.pages)
        boxes = []
        for page in reader.pages:
            box = page.mediabox
            width, height = float(box.width), float(box.height)
            if not (width > 0 and height > 0):
                raise CompatibilityError("invalid PDF media box", category="verify", phase="pdf", case=case)
            boxes.append([round(width, 3), round(height, 3)])
        mark_info = root.get("/MarkInfo")
    except CompatibilityError:
        raise
    except Exception as exc:
        raise CompatibilityError(
            "PDF evidence could not be parsed", category="verify", phase="pdf", case=case,
        ) from exc
    return {
        "sha256": sha256_file(path, limit=MAX_PDF_BYTES),
        "bytes": path.stat().st_size,
        "pages": len(reader.pages),
        "page_boxes": boxes,
        "lang": str(root.get("/Lang", "")),
        "title": str(metadata.get("/Title", "")),
        "struct_tree": root.get("/StructTreeRoot") is not None,
        "marked": bool(mark_info and mark_info.get("/Marked")),
        "text_sha256": hashlib.sha256(text.encode()).hexdigest(),
    }


def _table(evidence: dict[str, Any], table_id: str = "", caption: str = "") -> dict[str, Any]:
    matches = [table for table in evidence["tables"]
               if (table_id and table["id"] == table_id) or (caption and table["caption"] == caption)]
    if len(matches) != 1:
        raise CompatibilityError(f"expected one table {table_id or caption!r}", category="verify", phase="classify")
    return matches[0]


def _header(table: dict[str, Any]) -> list[str]:
    rows = table.get("rows")
    if not isinstance(rows, list) or not rows or not isinstance(rows[0], list):
        return []
    return [cell.get("text", "") for cell in rows[0] if isinstance(cell, dict)]


def _schedule(case: dict[str, Any], case_id: str) -> dict[str, Any]:
    matches = [table for table in case["html"]["tables"]
               if _header(table)[:3] == ["Date", "Time", "Venue"]]
    if len(matches) != 1:
        raise CompatibilityError(
            "expected one schedule table", category="verify", phase="classify", case=case_id,
        )
    return matches[0]


def _check_result(check_id: str, condition: bool, detail: str) -> dict[str, str]:
    return {"id": check_id, "status": "pass" if condition else "fail", "detail": detail}


def _content_checks(cases: dict[str, dict[str, Any]]) -> list[dict[str, str]]:
    htmls = [case["html"] for case in cases.values()]
    return [
        _check_result("content-preserved", len({item["content_sha256"] for item in htmls}) == 1,
                "all modes retain identical ordered cell text"),
        _check_result("semantics-preserved", len({item["semantic_sha256"] for item in htmls}) == 1,
                "table captions and header associations remain stable"),
    ]


def _width_checks(cases: dict[str, dict[str, Any]]) -> list[dict[str, str]]:
    legacy, auto = cases["v0.1.0"], cases["current-auto"]
    optout, precedence, explicit = cases["current-legacy"], cases["current-precedence"], cases["current-explicit"]
    declared_matches = [table for table in precedence["html"]["tables"]
                        if _header(table) == ["Division", "Club", "Points"]]
    if len(declared_matches) != 1:
        raise CompatibilityError(
            "expected one declared-width table", category="verify", phase="classify",
            case="current-precedence",
        )
    declared = declared_matches[0]
    author = _table(precedence["html"], "author-layout")
    venue_columns = _schedule(explicit, "current-explicit")["columns"]
    venue = venue_columns[2] if len(venue_columns) >= 3 else {}
    return [
        _check_result("automatic-widths-intentional", bool(_schedule(auto, "current-auto")["columns"])
                and not _schedule(legacy, "v0.1.0")["columns"],
                "current default adds typed widths to an eligible undeclared schedule"),
        _check_result("legacy-opt-out", not _schedule(optout, "current-legacy")["columns"],
                "table_widths:false suppresses automatic widths"),
        _check_result("declared-layout-precedence", [col["width"] for col in declared["columns"]] == ["25.0%", "50.0%", "25.0%"],
                "declared percentage layout remains authoritative"),
        _check_result("author-colgroup-precedence", [col["width"] for col in author["columns"]] == ["30%", "70%"],
                "author colgroup remains unchanged"),
        _check_result("explicit-venue-width", venue.get("width") == "12em",
                "supported Venue override emits exactly 12em"),
    ]


def _document_checks(cases: dict[str, dict[str, Any]]) -> list[dict[str, str]]:
    legacy, auto = cases["v0.1.0"], cases["current-auto"]
    accessibility_delta = (
        auto["pdf"]["lang"] == "en-AU"
        and (legacy["pdf"]["lang"] != "en-AU" or legacy["pdf"]["marked"] != auto["pdf"]["marked"])
    )
    return [
        _check_result("accessibility-rollback-warning", accessibility_delta,
                "tag rollback loses current language and/or PDF/UA marking behavior"),
        _check_result("page-bounds", all(case["pdf"]["pages"] <= MAX_PAGES_PER_MODE
                                         and case["pdf"]["page_boxes"]
                                   for case in cases.values()),
                "all PDFs stay within bounded positive media boxes"),
    ]


def classify(cases: dict[str, dict[str, Any]]) -> list[dict[str, str]]:
    """Classify deltas, with one independent witness for each contract."""
    checks = _content_checks(cases) + _width_checks(cases) + _document_checks(cases)
    if tuple(item["id"] for item in checks) != CHECK_IDS:
        raise AssertionError("check order drifted")
    return checks
