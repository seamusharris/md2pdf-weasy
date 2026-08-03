"""Bounded schemas for downstream consumer registry, requests, and results."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import hashlib
import json
import re
from typing import Any


MAX_JSON_BYTES = 128 * 1024
MAX_CONSUMERS = 64
MAX_DEPTH = 8
IDENTIFIER_RE = re.compile(r"^[a-z][a-z0-9_-]{1,63}$")
REFERENCE_RE = re.compile(r"^[A-Z][A-Z0-9_-]{1,31}:[A-Za-z0-9._/-]{1,128}$")
COMMIT_RE = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
FEATURE_SET = "public_api_v1"
OPT_OUT = "table_widths_false"
CHECK_IDS = (
    "python_api",
    "relative_resources",
    "base_url",
    "front_matter",
    "themes",
    "private_git_install",
    "opt_out",
    "rollback",
)
REGISTRY_KEYS = frozenset(
    {"schema_version", "decision", "reviewed_on", "evidence_policy", "consumers"}
)
CONSUMER_KEYS = frozenset(
    {
        "consumer_id",
        "environment_id",
        "recipient_id",
        "entitlement",
        "provenance_ref",
        "feature_set",
    }
)
ENTITLEMENT_KEYS = frozenset({"operation", "environment", "recipient"})


class CanaryError(Exception):
    """A categorized failure safe to show without paths or input contents."""

    def __init__(
        self,
        category: str,
        detail: str,
        exit_code: int = 3,
        *,
        cleanup_warning: bool = False,
    ) -> None:
        super().__init__(detail)
        self.category = category
        self.detail = detail
        self.exit_code = exit_code
        self.cleanup_warning = cleanup_warning


@dataclass(frozen=True)
class Consumer:
    consumer_id: str
    environment_id: str
    recipient_id: str
    provenance_ref: str
    feature_set: str


@dataclass(frozen=True)
class RunRequest:
    consumer_id: str
    environment_id: str
    recipient_id: str
    candidate_commit: str
    rollback_commit: str
    opt_out: str

    @classmethod
    def create(
        cls,
        consumer_id: str,
        environment_id: str,
        recipient_id: str,
        candidate_commit: str,
        rollback_commit: str,
        opt_out: str,
    ) -> "RunRequest":
        identifiers = {
            "consumer_id": consumer_id,
            "environment_id": environment_id,
            "recipient_id": recipient_id,
        }
        for label, value in identifiers.items():
            _identifier(value, label, category="invalid request", exit_code=2)
        for label, value in {
            "candidate_commit": candidate_commit,
            "rollback_commit": rollback_commit,
        }.items():
            if not isinstance(value, str) or COMMIT_RE.fullmatch(value) is None:
                raise CanaryError("invalid request", f"{label} must be a canonical full commit id", 2)
        if opt_out != OPT_OUT:
            raise CanaryError("invalid request", "unsupported opt-out control", 2)
        return cls(**identifiers, candidate_commit=candidate_commit,
                   rollback_commit=rollback_commit, opt_out=opt_out)


def _duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise CanaryError("invalid data", "duplicate JSON object key")
        result[key] = value
    return result


def _depth(value: Any, level: int = 0) -> None:
    if level > MAX_DEPTH:
        raise CanaryError("invalid data", "JSON nesting exceeds the limit")
    if isinstance(value, dict):
        for item in value.values():
            _depth(item, level + 1)
    elif isinstance(value, list):
        for item in value:
            _depth(item, level + 1)


def parse_json_bytes(raw: bytes, label: str) -> dict[str, Any]:
    if len(raw) > MAX_JSON_BYTES:
        raise CanaryError("invalid data", f"{label} exceeds the size limit")
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_duplicate_keys)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise CanaryError("invalid data", f"{label} is not valid UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise CanaryError("invalid data", f"{label} must be a JSON object")
    _depth(value)
    return value


def _keys(value: dict[str, Any], expected: frozenset[str], label: str) -> None:
    if frozenset(value) != expected:
        raise CanaryError("invalid data", f"{label} fields are incomplete or unknown")


def _identifier(
    value: Any,
    label: str,
    *,
    category: str = "invalid data",
    exit_code: int = 3,
) -> str:
    if not isinstance(value, str) or IDENTIFIER_RE.fullmatch(value) is None:
        raise CanaryError(category, f"{label} must be a bounded identifier", exit_code)
    return value


def _reference(value: Any, label: str) -> str:
    if not isinstance(value, str) or REFERENCE_RE.fullmatch(value) is None:
        raise CanaryError("invalid data", f"{label} must be an opaque reference")
    return value


def _iso_date(value: Any, label: str) -> date:
    if not isinstance(value, str):
        raise CanaryError("invalid data", f"{label} must be an ISO date")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise CanaryError("invalid data", f"{label} must be an ISO date") from exc
    if parsed.isoformat() != value or parsed > date.today():
        raise CanaryError("invalid data", f"{label} is malformed or future-dated")
    return parsed


def _validate_evidence_policy(policy: Any) -> None:
    if not isinstance(policy, dict):
        raise CanaryError("invalid data", "evidence policy must be an object")
    _keys(policy, frozenset({"storage", "forbidden_content"}), "evidence policy")
    if policy != {
        "storage": "references_only",
        "forbidden_content": [
            "consumer_names",
            "repository_urls",
            "documents",
            "credentials",
            "licenses",
            "attachments",
        ],
    }:
        raise CanaryError("invalid data", "consumer evidence policy must remain reference-only")


def _validate_consumer_entry(entry: Any) -> Consumer:
    if not isinstance(entry, dict):
        raise CanaryError("invalid data", "consumer entry must be an object")
    _keys(entry, CONSUMER_KEYS, "consumer entry")
    entitlement = entry["entitlement"]
    if not isinstance(entitlement, dict):
        raise CanaryError("invalid data", "entitlement tuple must be an object")
    _keys(entitlement, ENTITLEMENT_KEYS, "entitlement tuple")
    if entitlement["operation"] != "consumer_canary":
        raise CanaryError("invalid data", "consumer entitlement operation is invalid")
    consumer_id = _identifier(entry["consumer_id"], "consumer_id")
    environment_id = _identifier(entry["environment_id"], "environment_id")
    recipient_id = _identifier(entry["recipient_id"], "recipient_id")
    if entitlement["environment"] != environment_id or entitlement["recipient"] != recipient_id:
        raise CanaryError("invalid data", "consumer entitlement tuple is inconsistent")
    feature_set = entry["feature_set"]
    if feature_set != FEATURE_SET:
        raise CanaryError("invalid data", "consumer feature set is unsupported")
    return Consumer(
        consumer_id,
        environment_id,
        recipient_id,
        _reference(entry["provenance_ref"], "provenance_ref"),
        feature_set,
    )


def validate_registry(value: dict[str, Any]) -> tuple[Consumer, ...]:
    _keys(value, REGISTRY_KEYS, "registry")
    if value["schema_version"] != 1:
        raise CanaryError("invalid data", "unsupported registry schema")
    _iso_date(value["reviewed_on"], "registry reviewed_on")
    _validate_evidence_policy(value["evidence_policy"])
    entries = value["consumers"]
    if not isinstance(entries, list) or len(entries) > MAX_CONSUMERS:
        raise CanaryError("invalid data", "consumer list exceeds its bounds")
    expected_decision = "authorized_consumers_recorded" if entries else "no_authorized_consumers_recorded"
    if value["decision"] != expected_decision:
        raise CanaryError("invalid data", "registry decision is inconsistent")
    result: list[Consumer] = []
    seen: set[tuple[str, str, str]] = set()
    for entry in entries:
        consumer = _validate_consumer_entry(entry)
        key = consumer.consumer_id, consumer.environment_id, consumer.recipient_id
        if key in seen:
            raise CanaryError("invalid data", "duplicate consumer tuple")
        seen.add(key)
        result.append(consumer)
    return tuple(result)


def select_consumer(consumers: tuple[Consumer, ...], request: RunRequest) -> Consumer:
    matches = [item for item in consumers if (
        item.consumer_id, item.environment_id, item.recipient_id
    ) == (request.consumer_id, request.environment_id, request.recipient_id)]
    if len(matches) != 1:
        raise CanaryError("consumer denied", "no exact authorized consumer is recorded", 2)
    return matches[0]


def result_json(
    request: RunRequest,
    tree: str,
    input_digest: str,
    checks: tuple[str, ...],
) -> str:
    if tuple(checks) != CHECK_IDS:
        raise CanaryError("canary failed", "canary checks are incomplete")
    if re.fullmatch(r"[0-9a-f]{64}", input_digest) is None:
        raise CanaryError("canary failed", "canary input identity is malformed")
    value = {
        "schema_version": 1,
        "status": "pass",
        "consumer_id": request.consumer_id,
        "environment_id": request.environment_id,
        "candidate_commit": request.candidate_commit,
        "candidate_tree": tree,
        "input_digest": input_digest,
        "rollback_commit": request.rollback_commit,
        "opt_out": request.opt_out,
        "checks": list(checks),
    }
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"))
    if len(encoded.encode("utf-8")) > 4096:
        raise CanaryError("canary failed", "canary result exceeds the size limit")
    return encoded


def content_digest(items: list[tuple[str, bytes]]) -> str:
    lines = []
    for name, content in sorted(items):
        lines.append(f"{hashlib.sha256(content).hexdigest()}  {name}\n".encode("utf-8"))
    return hashlib.sha256(b"".join(lines)).hexdigest()
