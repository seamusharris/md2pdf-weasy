"""Bounded canonical schema for local packaging-gate evidence."""

from __future__ import annotations

from dataclasses import dataclass
import json
import re
from typing import Any


MAX_RECORD_BYTES = 64 * 1024
MAX_TEXT = 240
SHA_RE = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
CHECK_IDS = (
    "reliable-full-suite",
    "approved-visual-review",
    "wheel-build",
    "sdist-build",
    "wheel-content-inspection",
    "sdist-content-inspection",
    "clean-venv-install",
    "md2pdf-entry-point",
    "python-module-entry-point",
    "pdf-smoke-render",
    "html-smoke-render",
)
PREREQUISITE_IDS = (
    "immutable-candidate-acceptance",
    "package-artifact-entitlement",
)


class GateError(Exception):
    """A categorized packaging-gate failure safe to display."""

    def __init__(self, category: str, detail: str, exit_code: int = 3) -> None:
        super().__init__(detail)
        self.category = _text(category, "category")
        self.detail = _text(detail, "detail")
        self.exit_code = exit_code


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value or len(value) > MAX_TEXT:
        raise ValueError(f"{label} must be bounded text")
    return value


def _sha(value: Any, label: str) -> str:
    if not isinstance(value, str) or SHA_RE.fullmatch(value) is None:
        raise GateError("invalid evidence", f"{label} is not a full object id")
    return value


@dataclass(frozen=True)
class Prerequisite:
    id: str
    status: str
    category: str | None
    detail: str | None

    def as_dict(self) -> dict[str, str | None]:
        return {
            "category": self.category,
            "detail": self.detail,
            "id": self.id,
            "status": self.status,
        }


@dataclass(frozen=True)
class GateRecord:
    source_commit: str
    source_tree: str
    prerequisites: tuple[Prerequisite, ...]

    def __post_init__(self) -> None:
        _sha(self.source_commit, "source commit")
        _sha(self.source_tree, "source tree")
        if tuple(item.id for item in self.prerequisites) != PREREQUISITE_IDS:
            raise GateError("invalid evidence", "prerequisite order is invalid")
        if not all(item.status in {"authorized", "denied"} for item in self.prerequisites):
            raise GateError("invalid evidence", "prerequisite status is invalid")
        for item in self.prerequisites:
            if item.status == "authorized":
                if item.category is not None or item.detail is not None:
                    raise GateError("invalid evidence", "authorized prerequisite has a diagnostic")
            elif item.category is None or item.detail is None:
                raise GateError("invalid evidence", "denied prerequisite lacks a diagnostic")
            else:
                _text(item.category, "prerequisite category")
                _text(item.detail, "prerequisite detail")
        if all(item.status == "authorized" for item in self.prerequisites):
            raise GateError("gate unavailable", "authorized packaging workflow is not active")

    def as_dict(self) -> dict[str, Any]:
        return {
            "artifact_created": False,
            "decision": "blocked",
            "gates": [{"id": check, "status": "not-run"} for check in CHECK_IDS],
            "kind": "md2pdf-local-packaging-gates",
            "prerequisites": [item.as_dict() for item in self.prerequisites],
            "schema_version": 1,
            "source_commit": self.source_commit,
            "source_tree": self.source_tree,
        }

    def to_bytes(self) -> bytes:
        raw = (json.dumps(self.as_dict(), sort_keys=True, separators=(",", ":")) + "\n").encode()
        if len(raw) > MAX_RECORD_BYTES:
            raise GateError("invalid evidence", "packaging-gate record exceeds its size limit")
        return raw


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise GateError("invalid evidence", "duplicate JSON object key")
        result[key] = value
    return result


def load_record(raw: bytes) -> GateRecord:
    """Parse and validate one canonical blocked record."""

    if len(raw) > MAX_RECORD_BYTES:
        raise GateError("invalid evidence", "packaging-gate record exceeds its size limit")
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs)
    except (UnicodeError, json.JSONDecodeError, RecursionError, ValueError) as exc:
        raise GateError("invalid evidence", "packaging-gate record is not valid JSON") from exc
    if not isinstance(value, dict) or frozenset(value) != frozenset(
        {"artifact_created", "decision", "gates", "kind", "prerequisites",
         "schema_version", "source_commit", "source_tree"}
    ):
        raise GateError("invalid evidence", "packaging-gate record fields are invalid")
    if (
        value["schema_version"] != 1
        or value["kind"] != "md2pdf-local-packaging-gates"
        or value["decision"] != "blocked"
        or value["artifact_created"] is not False
        or value["gates"] != [{"id": check, "status": "not-run"} for check in CHECK_IDS]
        or not isinstance(value["prerequisites"], list)
    ):
        raise GateError("invalid evidence", "packaging-gate record is inconsistent")
    try:
        prerequisites: list[Prerequisite] = []
        for entry in value["prerequisites"]:
            if not isinstance(entry, dict) or frozenset(entry) != frozenset(
                {"category", "detail", "id", "status"}
            ):
                raise GateError("invalid evidence", "prerequisite fields are invalid")
            prerequisites.append(Prerequisite(**entry))
        record = GateRecord(
            _sha(value["source_commit"], "source commit"),
            _sha(value["source_tree"], "source tree"),
            tuple(prerequisites),
        )
    except GateError:
        raise
    except (TypeError, ValueError, OverflowError) as exc:
        raise GateError(
            "invalid evidence", "packaging-gate record values are invalid"
        ) from exc
    if record.to_bytes() != raw:
        raise GateError("invalid evidence", "packaging-gate record is not canonical")
    return record
