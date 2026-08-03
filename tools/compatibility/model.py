"""Bounded data model and canonical schemas for compatibility evidence."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
from typing import Any


SCHEMA_VERSION = 1
TAG = "v0.1.0"
TAG_COMMIT = "f565357a9e6ba975ae9e1699f27be876825b149e"
MODE_IDS = (
    "v0.1.0",
    "current-auto",
    "current-legacy",
    "current-precedence",
    "current-explicit",
)
CHECK_IDS = (
    "content-preserved",
    "semantics-preserved",
    "automatic-widths-intentional",
    "legacy-opt-out",
    "declared-layout-precedence",
    "author-colgroup-precedence",
    "explicit-venue-width",
    "accessibility-rollback-warning",
    "page-bounds",
)
FAILURE_CATEGORIES = frozenset({
    "prerequisite", "tag", "archive", "render", "raster", "verify",
    "timeout", "internal",
})

MAX_PAGES_PER_MODE = 24
MAX_TOTAL_PIXELS = 180_000_000
MAX_CAPTURE_BYTES = 4 * 1024 * 1024
MAX_MANIFEST_BYTES = 16 * 1024 * 1024
MAX_CANDIDATE_BYTES = 1024 * 1024 * 1024
MAX_PDF_BYTES = 128 * 1024 * 1024
MAX_IMAGE_BYTES = 64 * 1024 * 1024
MAX_CANDIDATE_ENTRIES = 10_000
MAX_CANDIDATE_DEPTH = 8
MAX_CANDIDATE_ROOT_ENTRIES = 1_000
MAX_ARCHIVE_BYTES = 256 * 1024 * 1024
MAX_ARCHIVE_ENTRIES = 10_000
MAX_ARCHIVE_FILE_BYTES = 128 * 1024 * 1024
MAX_DIAGNOSTIC_BYTES = 16_384
COMMAND_TIMEOUT = 120.0
MATRIX_TIMEOUT = 1_200.0


class CompatibilityError(RuntimeError):
    """An actionable, fail-closed compatibility failure."""

    def __init__(self, message: str, *, category: str = "internal", phase: str = "unknown", case: str | None = None):
        super().__init__(message)
        self.category = category if category in FAILURE_CATEGORIES else "internal"
        self.phase = phase
        self.case = case


class LeaseBusy(CompatibilityError):
    """A candidate lease is already held."""


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path, *, limit: int | None = None) -> str:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            size += len(chunk)
            if limit is not None and size > limit:
                raise CompatibilityError(f"{path.name} exceeds {limit} bytes", phase="verify")
            digest.update(chunk)
    return digest.hexdigest()


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise CompatibilityError(message, category="verify", phase="schema")


def _sha(value: Any) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _validate_provenance(provenance: Any) -> None:
    _require(isinstance(provenance, dict), "missing provenance")
    _require(provenance.get("tag") == TAG and provenance.get("tag_commit") == TAG_COMMIT,
             "historical tag provenance mismatch")
    _require(isinstance(provenance.get("current_base_commit"), str), "missing current base commit")
    _require(_sha(provenance.get("fixture_sha256")), "invalid fixture hash")
    _require(_sha(provenance.get("active_visual_acceptance_digest")), "invalid visual evidence digest")
    _require(provenance.get("publication_basis") == "immutable-render-snapshot-v1",
             "invalid publication basis")
    source_hashes = provenance.get("source_hashes")
    _require(isinstance(source_hashes, dict) and source_hashes, "missing source hashes")
    _require(all(isinstance(path, str) and path and _sha(digest) for path, digest in source_hashes.items()),
             "invalid source hash entry")
    environment = provenance.get("environment")
    _require(isinstance(environment, dict) and environment, "missing environment provenance")
    _require(all(isinstance(key, str) and isinstance(item, str) for key, item in environment.items()),
             "invalid environment provenance")
    commands = provenance.get("commands")
    _require(isinstance(commands, list) and commands and all(isinstance(item, str) for item in commands),
             "invalid reproduction commands")


def _validate_html_evidence(html: Any) -> None:
    _require(isinstance(html, dict), "case is missing HTML evidence")
    _require(all(_sha(html.get(key)) for key in ("sha256", "semantic_sha256", "content_sha256")),
             "case has invalid HTML hashes")
    tables = html.get("tables")
    _require(isinstance(html.get("table_count"), int) and isinstance(tables, list)
             and html["table_count"] == len(tables),
             "case has invalid HTML structure")
    for table in tables:
        _require(isinstance(table, dict), "case has invalid HTML table evidence")
        _require(all(isinstance(table.get(key), str) for key in ("id", "caption"))
                 and isinstance(table.get("classes"), list)
                 and all(isinstance(item, str) for item in table["classes"]),
                 "case has invalid HTML table metadata")
        columns, rows = table.get("columns"), table.get("rows")
        _require(isinstance(columns, list) and all(isinstance(item, dict) for item in columns),
                 "case has invalid HTML columns")
        _require(all(all(isinstance(column.get(key), str) for key in ("class", "width"))
                     for column in columns), "case has invalid HTML column evidence")
        _require(isinstance(rows, list) and all(isinstance(row, list) for row in rows),
                 "case has invalid HTML rows")
        cells = [cell for row in rows for cell in row]
        _require(all(isinstance(cell, dict) for cell in cells), "case has invalid HTML cells")
        _require(all(all(isinstance(cell.get(key), str)
                         for key in ("tag", "text", "id", "scope", "headers"))
                     for cell in cells), "case has invalid HTML cell evidence")


def _validate_pdf_evidence(pdf: Any) -> int:
    _require(isinstance(pdf, dict), "case is missing PDF evidence")
    _require(_sha(pdf.get("sha256")) and _sha(pdf.get("text_sha256")), "case has invalid PDF hashes")
    pages, page_boxes = pdf.get("pages"), pdf.get("page_boxes")
    _require(isinstance(pdf.get("bytes"), int) and pdf["bytes"] >= 0
             and isinstance(pages, int) and pages > 0, "case has invalid PDF limits")
    _require(isinstance(page_boxes, list) and len(page_boxes) == pages
             and all(isinstance(box, list) and len(box) == 2
                     and all(isinstance(side, (int, float)) and side > 0 for side in box)
                     for box in page_boxes)
             and isinstance(pdf.get("lang"), str)
             and isinstance(pdf.get("title"), str), "case has invalid PDF metadata")
    _require(isinstance(pdf.get("struct_tree"), bool) and isinstance(pdf.get("marked"), bool),
             "case has invalid PDF structure flags")
    return pages


def _validate_raster_evidence(rasters: Any, decoded_pixels: Any, pages: int) -> None:
    _require(isinstance(rasters, list) and len(rasters) == pages
             and all(isinstance(item, dict) for item in rasters),
             "case is missing raster evidence")
    for raster in rasters:
        _require(isinstance(raster.get("path"), str)
                 and isinstance(raster.get("width"), int) and raster["width"] > 0
                 and isinstance(raster.get("height"), int) and raster["height"] > 0
                 and _sha(raster.get("sha256")), "case has invalid raster evidence")
    _require(isinstance(decoded_pixels, int) and decoded_pixels > 0,
             "case has invalid decoded-pixel evidence")


def _validate_case(case: dict[str, Any]) -> None:
    _validate_html_evidence(case.get("html"))
    pages = _validate_pdf_evidence(case.get("pdf"))
    _validate_raster_evidence(case.get("rasters"), case.get("decoded_pixels"), pages)


def _validate_decision(value: dict[str, Any]) -> None:
    contact = value.get("contact_sheet")
    _require(isinstance(contact, dict) and isinstance(contact.get("path"), str)
             and isinstance(contact.get("width"), int) and isinstance(contact.get("height"), int)
             and _sha(contact.get("sha256")), "invalid contact-sheet evidence")
    _require(isinstance(value.get("decision"), str) and value["decision"], "missing compatibility decision")


def validate_manifest(value: Any) -> dict[str, Any]:
    _require(isinstance(value, dict), "manifest must be an object")
    _require(value.get("schema_version") == SCHEMA_VERSION, "unknown manifest schema")
    _require(value.get("kind") == "md2pdf-v0.1-compatibility", "unknown manifest kind")
    _validate_provenance(value.get("provenance"))
    cases = value.get("cases")
    _require(isinstance(cases, list) and len(cases) == len(MODE_IDS)
             and all(isinstance(item, dict) for item in cases), "cases must be complete objects")
    ids = [item.get("id") for item in cases]
    _require(tuple(ids) == MODE_IDS, "compatibility modes are incomplete or reordered")
    for case in cases:
        _validate_case(case)
    checks = value.get("checks")
    _require(isinstance(checks, list) and len(checks) == len(CHECK_IDS)
             and all(isinstance(item, dict) for item in checks), "checks must be complete objects")
    check_ids = [item.get("id") for item in checks]
    _require(tuple(check_ids) == CHECK_IDS, "compatibility checks are incomplete or reordered")
    _require(all(item.get("status") == "pass" for item in checks), "compatibility decision contains a blocker")
    _require(all(isinstance(item.get("detail"), str) for item in checks), "compatibility check is missing detail")
    _validate_decision(value)
    _require(isinstance(value.get("decision_digest"), str), "missing decision digest")
    unsigned = dict(value)
    digest = unsigned.pop("decision_digest")
    _require(digest == sha256_bytes(canonical_bytes(unsigned)), "decision digest mismatch")
    _require(len(canonical_bytes(value)) <= MAX_MANIFEST_BYTES, "manifest is too large")
    return value


def validate_failure(value: Any) -> dict[str, Any]:
    _require(isinstance(value, dict), "failure record must be an object")
    _require(value.get("schema_version") == SCHEMA_VERSION, "unknown failure schema")
    _require(value.get("kind") == "md2pdf-v0.1-compatibility-failure", "unknown failure kind")
    _require(value.get("category") in FAILURE_CATEGORIES, "unknown failure category")
    _require(isinstance(value.get("phase"), str) and value["phase"], "missing failure phase")
    diagnostic = value.get("diagnostic")
    _require(isinstance(diagnostic, str), "failure diagnostic must be text")
    _require(len(diagnostic.encode()) <= MAX_DIAGNOSTIC_BYTES, "failure diagnostic is too large")
    return value


def signed_manifest(value: dict[str, Any]) -> dict[str, Any]:
    unsigned = dict(value)
    unsigned.pop("decision_digest", None)
    return {**unsigned, "decision_digest": sha256_bytes(canonical_bytes(unsigned))}


def validate_pdf_limits(pdf_bytes: int, pages: int) -> None:
    if pdf_bytes > MAX_PDF_BYTES:
        raise CompatibilityError("PDF exceeds safe size limit", category="verify", phase="pdf-preflight")
    if pages > MAX_PAGES_PER_MODE:
        raise CompatibilityError("PDF page count exceeds safe limit", category="verify", phase="pdf-preflight")


def validate_image_limits(image_bytes: int, width: int, height: int) -> int:
    if image_bytes > MAX_IMAGE_BYTES:
        raise CompatibilityError("image exceeds safe size limit", category="raster", phase="image-preflight")
    if width <= 0 or height <= 0:
        raise CompatibilityError("image dimensions must be positive", category="raster", phase="image-preflight")
    pixels = width * height
    if pixels > MAX_TOTAL_PIXELS:
        raise CompatibilityError("image decoded pixel limit exceeded", category="raster", phase="image-preflight")
    return pixels


def validate_total_pixels(pixels: int) -> None:
    if pixels > MAX_TOTAL_PIXELS:
        raise CompatibilityError("aggregate decoded pixel limit exceeded", category="raster", phase="contact-sheet")
