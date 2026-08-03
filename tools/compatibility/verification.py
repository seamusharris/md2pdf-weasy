"""Bounded manifest, provenance, and candidate-evidence verification."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .history import resolve_tag
from .model import (
    MAX_IMAGE_BYTES, MAX_MANIFEST_BYTES, MAX_PDF_BYTES, CompatibilityError,
    sha256_file, validate_manifest,
)
from .provenance import (
    FIXTURE, ROOT, active_visual_digest, source_hashes,
)
from .store import PENDING_MARKER


def read_manifest(path: Path) -> dict[str, Any]:
    try:
        if path.stat().st_size > MAX_MANIFEST_BYTES:
            raise CompatibilityError(
                "manifest exceeds safe size limit", category="verify", phase="verify",
            )
        return validate_manifest(json.loads(path.read_text(encoding="utf-8")))
    except CompatibilityError:
        raise
    except (OSError, UnicodeError, ValueError, RecursionError) as exc:
        raise CompatibilityError(
            "manifest is missing or malformed", category="verify", phase="verify",
        ) from exc


def verify_live_provenance(value: dict[str, Any], *, attest_tag: bool) -> None:
    provenance = value["provenance"]
    if provenance["source_hashes"] != source_hashes():
        raise CompatibilityError(
            "current compatibility source hashes changed",
            category="verify", phase="source-attestation",
        )
    if provenance["fixture_sha256"] != sha256_file(FIXTURE):
        raise CompatibilityError(
            "fixture hash changed", category="verify", phase="source-attestation",
        )
    if provenance["active_visual_acceptance_digest"] != active_visual_digest():
        raise CompatibilityError(
            "active T-009 evidence changed", category="verify", phase="provenance",
        )
    if attest_tag:
        resolve_tag(ROOT)


def _verify_hash(
    path: Path, expected: str, label: str, *, case: str | None = None,
    limit: int | None = None,
) -> None:
    try:
        actual = sha256_file(path, limit=limit)
    except (OSError, CompatibilityError) as exc:
        raise CompatibilityError(
            f"{label} artifact is missing or unsafe",
            category="verify", phase="artifact", case=case,
        ) from exc
    if actual != expected:
        raise CompatibilityError(
            f"{label} artifact hash mismatch",
            category="verify", phase="artifact", case=case,
        )


def reject_unverifiable_markers(candidate: Path) -> None:
    try:
        (candidate / "failure.json").lstat()
    except FileNotFoundError:
        pass
    else:
        raise CompatibilityError(
            "candidate contains a failure marker",
            category="verify", phase="artifact",
        )
    try:
        (candidate / PENDING_MARKER).lstat()
    except FileNotFoundError:
        return
    else:
        raise CompatibilityError(
            "candidate contains a pending marker",
            category="verify", phase="artifact",
        )


def _read_success_marker(candidate: Path, digest: str) -> None:
    try:
        success_path = candidate / "success.json"
        if success_path.stat().st_size > 1024:
            raise ValueError
        success = json.loads(success_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError, RecursionError) as exc:
        raise CompatibilityError(
            "candidate success marker is missing or malformed",
            category="verify", phase="artifact",
        ) from exc
    if success != {"decision_digest": digest}:
        raise CompatibilityError(
            "candidate success marker does not match manifest",
            category="verify", phase="artifact",
        )


def _verify_case(candidate: Path, case: dict[str, Any]) -> None:
    case_id = case["id"]
    mode_dir = candidate / "artifacts" / case_id
    _verify_hash(
        mode_dir / "document.html", case["html"]["sha256"], "HTML", case=case_id,
    )
    _verify_hash(
        mode_dir / "document.pdf", case["pdf"]["sha256"], "PDF",
        case=case_id, limit=MAX_PDF_BYTES,
    )
    for page, raster in enumerate(case["rasters"], 1):
        relative = f"artifacts/{case_id}/page-{page}.png"
        if raster["path"] != relative:
            raise CompatibilityError(
                "raster artifact path mismatch",
                category="verify", phase="artifact", case=case_id,
            )
        _verify_hash(
            candidate / relative, raster["sha256"], "raster",
            case=case_id, limit=MAX_IMAGE_BYTES,
        )


def _verify_contact(candidate: Path, contact: dict[str, Any]) -> None:
    if contact["path"] != "contact-sheet.png":
        raise CompatibilityError(
            "contact-sheet artifact path mismatch",
            category="verify", phase="artifact",
        )
    _verify_hash(
        candidate / contact["path"], contact["sha256"], "contact-sheet",
        limit=MAX_IMAGE_BYTES,
    )


def verify_candidate_evidence(candidate: Path, value: dict[str, Any]) -> None:
    _read_success_marker(candidate, value["decision_digest"])
    decision = read_manifest(candidate / "decision.json")
    if decision != value:
        raise CompatibilityError(
            "decision and manifest evidence differ",
            category="verify", phase="artifact",
        )
    for case in value["cases"]:
        _verify_case(candidate, case)
    _verify_contact(candidate, value["contact_sheet"])
