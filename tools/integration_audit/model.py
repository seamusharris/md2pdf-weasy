"""Canonical, bounded evidence model for immutable integration audits."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import re
from typing import Any, Mapping, Sequence


SCHEMA_VERSION = 1
KIND = "md2pdf-immutable-integration-audit"
DECISION = "go-for-local-integration-gates"
NO_GO_DECISION = "no-go"
SHA_RE = re.compile(r"[0-9a-f]{40}\Z")
MAX_CAPTURE_BYTES = 16 * 1024 * 1024
MAX_CHANGED_PATHS = 2_000
MAX_PATH_BYTES = 4_096
MAX_BLOB_SCAN_BYTES = 4 * 1024 * 1024
MAX_ARCHIVE_BYTES = 256 * 1024 * 1024
MAX_ARCHIVE_ENTRIES = 20_000
MAX_ARCHIVE_FILE_BYTES = 128 * 1024 * 1024
MAX_ARCHIVE_DEPTH = 16
COMMAND_TIMEOUT = 120.0
SUITE_TIMEOUT = 1_800.0


class AuditError(RuntimeError):
    """A fail-closed audit error safe to expose in bounded diagnostics."""

    def __init__(self, category: str, detail: str, *, residue: bool = False) -> None:
        clean_category = re.sub(r"[^a-z0-9 -]", "", category.lower())[:80] or "audit failed"
        clean_detail = re.sub(r"[\r\n\x00-\x1f]+", " ", detail).strip()[:1_000]
        suffix = "; cleanup residue may remain" if residue else ""
        super().__init__(f"{clean_category}: {clean_detail}{suffix}")
        self.category = clean_category
        self.detail = clean_detail
        self.residue = residue


def require_sha(value: str, label: str) -> str:
    if not isinstance(value, str) or SHA_RE.fullmatch(value) is None:
        raise AuditError("invalid request", f"{label} must be a canonical full commit id")
    return value


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


@dataclass(frozen=True)
class AuditResult:
    """Stable evidence shared by the CLI, checked record, and downstream gate."""

    candidate_commit: str
    candidate_tree: str
    base_commit: str
    original_tip: str
    original_commits: tuple[str, ...]
    stabilization_commits: tuple[str, ...]
    history_sha256: str
    diff_sha256: str
    changed_paths_sha256: str
    changed_path_count: int
    validations: tuple[str, ...]
    decision: str = DECISION
    schema_version: int = SCHEMA_VERSION
    kind: str = KIND

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_bytes(self) -> bytes:
        return canonical_bytes(self.to_dict())


_RESULT_KEYS = {
    "candidate_commit", "candidate_tree", "base_commit", "original_tip",
    "original_commits", "stabilization_commits", "history_sha256",
    "diff_sha256", "changed_paths_sha256", "changed_path_count",
    "validations", "decision", "schema_version", "kind",
}


def parse_result(value: Mapping[str, Any], *, require_go: bool = True) -> AuditResult:
    if set(value) != _RESULT_KEYS:
        raise AuditError("invalid evidence", "audit record fields do not match schema")
    if value.get("schema_version") != SCHEMA_VERSION or value.get("kind") != KIND:
        raise AuditError("invalid evidence", "audit record schema is unsupported")
    if value.get("decision") not in {DECISION, NO_GO_DECISION}:
        raise AuditError("invalid evidence", "audit decision is unsupported")
    if require_go and value.get("decision") != DECISION:
        raise AuditError("invalid evidence", "audit decision is not a go decision")
    for key in ("candidate_commit", "candidate_tree", "base_commit", "original_tip"):
        require_sha(value.get(key), key)  # type: ignore[arg-type]
    for key in ("history_sha256", "diff_sha256", "changed_paths_sha256"):
        digest = value.get(key)
        if not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
            raise AuditError("invalid evidence", f"{key} is invalid")
    original = value.get("original_commits")
    stabilization = value.get("stabilization_commits")
    validations = value.get("validations")
    if not isinstance(original, Sequence) or isinstance(original, (str, bytes)) or not all(isinstance(item, str) and SHA_RE.fullmatch(item) for item in original):
        raise AuditError("invalid evidence", "original commit sequence is invalid")
    if not isinstance(stabilization, Sequence) or isinstance(stabilization, (str, bytes)) or not all(isinstance(item, str) and SHA_RE.fullmatch(item) for item in stabilization):
        raise AuditError("invalid evidence", "stabilization commit sequence is invalid")
    if not isinstance(validations, Sequence) or isinstance(validations, (str, bytes)) or not validations or not all(isinstance(item, str) and 0 < len(item) <= 200 for item in validations):
        raise AuditError("invalid evidence", "validation outcomes are invalid")
    count = value.get("changed_path_count")
    if not isinstance(count, int) or count < 0 or count > MAX_CHANGED_PATHS:
        raise AuditError("invalid evidence", "changed path count is invalid")
    return AuditResult(
        candidate_commit=value["candidate_commit"], candidate_tree=value["candidate_tree"],
        base_commit=value["base_commit"], original_tip=value["original_tip"],
        original_commits=tuple(original), stabilization_commits=tuple(stabilization),
        history_sha256=value["history_sha256"], diff_sha256=value["diff_sha256"],
        changed_paths_sha256=value["changed_paths_sha256"], changed_path_count=count,
        validations=tuple(validations), decision=value["decision"],
        schema_version=value["schema_version"], kind=value["kind"],
    )


def load_result(raw: bytes, *, require_go: bool = True) -> AuditResult:
    if len(raw) > 1024 * 1024:
        raise AuditError("invalid evidence", "audit record exceeds size limit")
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AuditError("invalid evidence", "audit record is not canonical JSON") from exc
    if not isinstance(value, dict):
        raise AuditError("invalid evidence", "audit record must be an object")
    result = parse_result(value, require_go=require_go)
    if result.to_bytes() != raw:
        raise AuditError("invalid evidence", "audit record is not canonically encoded")
    return result


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise AuditError("invalid evidence", "audit record contains duplicate fields")
        result[key] = value
    return result
