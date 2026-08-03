#!/usr/bin/env python3
"""Fail-closed, read-only preflight for proprietary-font distribution."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
from typing import Any
from urllib.parse import urlparse


RECORD_PATH = Path("docs/distribution-entitlement.json")
FONT_DIR = Path("pdf/fonts")
PROPRIETARY_PREFIXES = ("MinionPro-", "MyriadPro-")
MAX_RECORD_BYTES = 256 * 1024
IDENTIFIER_RE = re.compile(r"^[a-z][a-z0-9_-]{1,63}$")
REFERENCE_RE = re.compile(r"^[A-Z][A-Z0-9_-]{1,31}:[A-Za-z0-9._/-]{1,128}$")
HEX_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
STATUSES = frozenset({"authorized", "not_verified", "prohibited"})
GLOBAL_DECISIONS = frozenset(
    {"authorized", "partially_authorized", "not_verified", "prohibited"}
)
AUTHORIZATION_KEYS = frozenset(
    {
        "operation",
        "environment",
        "recipient",
        "status",
        "reason",
        "approver_ref",
        "reviewed_on",
        "expires_on",
        "governing_license_ref",
        "environment_evidence_refs",
        "recipient_evidence_refs",
    }
)
RECORD_KEYS = frozenset(
    {
        "schema_version",
        "decision",
        "reviewed_on",
        "proprietary_inventory",
        "evidence_policy",
        "evidence_gaps",
        "guidance",
        "authorizations",
    }
)


class PreflightError(Exception):
    """A sanitized, categorized preflight failure."""

    def __init__(self, category: str, detail: str, exit_code: int = 3) -> None:
        super().__init__(detail)
        self.category = category
        self.detail = detail
        self.exit_code = exit_code


@dataclass(frozen=True)
class Inventory:
    file_count: int
    digest: str


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise PreflightError("invalid record", "duplicate JSON object key")
        result[key] = value
    return result


def _require_exact_keys(value: dict[str, Any], expected: frozenset[str], label: str) -> None:
    actual = frozenset(value)
    if actual != expected:
        raise PreflightError("invalid record", f"{label} fields are incomplete or unknown")


def _parse_date(value: Any, label: str) -> date:
    if not isinstance(value, str):
        raise PreflightError("invalid record", f"{label} must be an ISO date")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise PreflightError("invalid record", f"{label} must be an ISO date") from exc
    if parsed.isoformat() != value:
        raise PreflightError("invalid record", f"{label} must be an ISO date")
    return parsed


def _require_identifier(value: Any, label: str) -> str:
    if not isinstance(value, str) or IDENTIFIER_RE.fullmatch(value) is None:
        raise PreflightError("invalid record", f"{label} must be a bounded identifier")
    return value


def _require_reference(value: Any, label: str) -> str:
    if not isinstance(value, str) or REFERENCE_RE.fullmatch(value) is None:
        raise PreflightError("invalid record", f"{label} must be an opaque reference")
    return value


def _require_reference_list(value: Any, label: str) -> list[str]:
    if not isinstance(value, list) or not value:
        raise PreflightError("invalid record", f"{label} must contain opaque references")
    references = [_require_reference(item, label) for item in value]
    if len(references) != len(set(references)):
        raise PreflightError("invalid record", f"{label} contains duplicate references")
    return references


def load_record(path: Path) -> dict[str, Any]:
    """Load a small regular JSON file while rejecting ambiguous object keys."""

    try:
        metadata = path.lstat()
    except OSError as exc:
        raise PreflightError("invalid record", "entitlement record is unavailable") from exc
    if path.is_symlink() or not path.is_file():
        raise PreflightError("invalid record", "entitlement record must be a regular file")
    if metadata.st_size > MAX_RECORD_BYTES:
        raise PreflightError("invalid record", "entitlement record exceeds the size limit")
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise PreflightError("invalid record", "entitlement record is unavailable") from exc
    return _parse_record_bytes(raw)


def _parse_record_bytes(raw: bytes) -> dict[str, Any]:
    if len(raw) > MAX_RECORD_BYTES:
        raise PreflightError("invalid record", "entitlement record exceeds the size limit")
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_reject_duplicate_keys)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise PreflightError("invalid record", "entitlement record is not valid UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise PreflightError("invalid record", "entitlement record must be a JSON object")
    return value


def _validate_inventory_record(inventory: Any) -> None:
    if not isinstance(inventory, dict):
        raise PreflightError("invalid record", "proprietary_inventory must be an object")
    _require_exact_keys(
        inventory, frozenset({"file_count", "digest_algorithm", "digest"}), "inventory"
    )
    if not isinstance(inventory["file_count"], int) or inventory["file_count"] <= 0:
        raise PreflightError("invalid record", "inventory file_count must be positive")
    if inventory["digest_algorithm"] != "sha256-lines-v1":
        raise PreflightError("invalid record", "unsupported inventory digest algorithm")
    if not isinstance(inventory["digest"], str) or HEX_DIGEST_RE.fullmatch(inventory["digest"]) is None:
        raise PreflightError("invalid record", "inventory digest must be lowercase SHA-256")


def _validate_evidence_policy(policy: Any, gaps: Any) -> None:
    if not isinstance(policy, dict):
        raise PreflightError("invalid record", "evidence_policy must be an object")
    _require_exact_keys(policy, frozenset({"storage", "forbidden_content"}), "evidence_policy")
    if policy["storage"] != "references_only" or policy["forbidden_content"] != [
        "license_documents",
        "font_attachments",
        "account_data",
    ]:
        raise PreflightError("invalid record", "evidence policy must remain reference-only")
    if not isinstance(gaps, list) or not gaps or not all(
        isinstance(item, str) and 0 < len(item) <= 160 for item in gaps
    ):
        raise PreflightError("invalid record", "evidence_gaps must be bounded text")


def _validate_guidance(guidance: Any) -> None:
    if not isinstance(guidance, list) or not guidance:
        raise PreflightError("invalid record", "guidance must contain official references")
    for item in guidance:
        if not isinstance(item, dict):
            raise PreflightError("invalid record", "guidance entries must be objects")
        _require_exact_keys(item, frozenset({"title", "url"}), "guidance entry")
        try:
            parsed = urlparse(item["url"] if isinstance(item["url"], str) else "")
            host = (parsed.hostname or "").lower()
        except ValueError as exc:
            raise PreflightError(
                "invalid record", "guidance must use official Adobe HTTPS URLs"
            ) from exc
        if (
            not isinstance(item["title"], str)
            or not (1 <= len(item["title"]) <= 160)
            or not isinstance(item["url"], str)
            or len(item["url"]) > 512
            or parsed.scheme != "https"
            or not (host == "adobe.com" or host.endswith(".adobe.com"))
        ):
            raise PreflightError("invalid record", "guidance must use official Adobe HTTPS URLs")


def _validate_authorization_entry(entry: Any, current_date: date) -> tuple[str, str, str]:
    if not isinstance(entry, dict):
        raise PreflightError("invalid record", "authorization entries must be objects")
    _require_exact_keys(entry, AUTHORIZATION_KEYS, "authorization entry")
    key = tuple(
        _require_identifier(entry[field], field)
        for field in ("operation", "environment", "recipient")
    )
    status = entry["status"]
    if status not in STATUSES:
        raise PreflightError("invalid record", "unknown authorization status")
    if not isinstance(entry["reason"], str) or not (1 <= len(entry["reason"]) <= 240):
        raise PreflightError("invalid record", "authorization reason must be bounded text")
    if status == "authorized":
        reviewed = _parse_date(entry["reviewed_on"], "authorization reviewed_on")
        expires = _parse_date(entry["expires_on"], "authorization expires_on")
        if reviewed > current_date or expires < current_date or expires < reviewed:
            raise PreflightError("invalid record", "authorization is stale or future-dated")
        _require_reference(entry["approver_ref"], "approver_ref")
        _require_reference(entry["governing_license_ref"], "governing_license_ref")
        _require_reference_list(entry["environment_evidence_refs"], "environment_evidence_refs")
        _require_reference_list(entry["recipient_evidence_refs"], "recipient_evidence_refs")
    elif any(
        entry[field] not in (None, [])
        for field in (
            "approver_ref",
            "reviewed_on",
            "expires_on",
            "governing_license_ref",
            "environment_evidence_refs",
            "recipient_evidence_refs",
        )
    ):
        raise PreflightError(
            "invalid record", "non-authorized entries must not imply approval evidence"
        )
    return key


def _validate_authorizations(entries: Any, current_date: date) -> int:
    if not isinstance(entries, list) or not entries:
        raise PreflightError("invalid record", "authorizations must be a non-empty list")
    seen: set[tuple[str, str, str]] = set()
    authorized_count = 0
    for entry in entries:
        key = _validate_authorization_entry(entry, current_date)
        if key in seen:
            raise PreflightError("invalid record", "duplicate authorization tuple")
        seen.add(key)
        if entry["status"] == "authorized":
            authorized_count += 1
    return authorized_count


def _validate_global_decision(decision: str, authorized_count: int, entry_count: int) -> None:
    if decision == "authorized" and authorized_count != entry_count:
        raise PreflightError("invalid record", "global authorized decision requires all entries")
    if decision == "not_verified" and authorized_count:
        raise PreflightError("invalid record", "not_verified decision cannot authorize entries")
    if decision == "prohibited" and authorized_count:
        raise PreflightError("invalid record", "prohibited decision cannot authorize entries")
    if decision == "partially_authorized" and not (0 < authorized_count < entry_count):
        raise PreflightError("invalid record", "partial decision requires mixed authorization states")


def validate_record(value: dict[str, Any], *, today: date | None = None) -> dict[str, Any]:
    """Validate the full record, including entries not selected by this run."""

    _require_exact_keys(value, RECORD_KEYS, "record")
    if value["schema_version"] != 1:
        raise PreflightError("invalid record", "unsupported schema version")
    decision = value["decision"]
    if decision not in GLOBAL_DECISIONS:
        raise PreflightError("invalid record", "unknown global decision")
    current_date = today or date.today()
    if _parse_date(value["reviewed_on"], "record reviewed_on") > current_date:
        raise PreflightError("invalid record", "record review date is future-dated")
    _validate_inventory_record(value["proprietary_inventory"])
    _validate_evidence_policy(value["evidence_policy"], value["evidence_gaps"])
    _validate_guidance(value["guidance"])
    entries = value["authorizations"]
    authorized_count = _validate_authorizations(entries, current_date)
    _validate_global_decision(decision, authorized_count, len(entries))
    return value


def proprietary_inventory(root: Path) -> Inventory:
    """Fingerprint exact proprietary files as SHA256(hash + path) lines."""

    font_dir = root / FONT_DIR
    try:
        paths = (
            sorted(
                path
                for path in font_dir.iterdir()
                if path.name.startswith(PROPRIETARY_PREFIXES)
            )
            if font_dir.is_dir()
            else []
        )
    except OSError as exc:
        raise PreflightError("inventory mismatch", "font inventory is unreadable", 4) from exc
    if not paths:
        raise PreflightError("inventory mismatch", "no proprietary font inventory found", 4)
    lines: list[bytes] = []
    for path in paths:
        if path.is_symlink() or not path.is_file():
            raise PreflightError("inventory mismatch", "font inventory contains a non-regular file", 4)
        try:
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError as exc:
            raise PreflightError("inventory mismatch", "font inventory is unreadable", 4) from exc
        relative = path.relative_to(root).as_posix()
        lines.append(f"{digest}  {relative}\n".encode("utf-8"))
    aggregate = hashlib.sha256(b"".join(lines)).hexdigest()
    return Inventory(file_count=len(paths), digest=aggregate)


def _run_git(root: Path, *arguments: str) -> bytes:
    try:
        completed = subprocess.run(
            ["git", "-C", str(root), *arguments],
            check=False,
            capture_output=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise PreflightError("source state invalid", "Git source identity is unavailable", 5) from exc
    if completed.returncode != 0:
        raise PreflightError("source state invalid", "Git source identity is unavailable", 5)
    return completed.stdout


def _git_text(root: Path, *arguments: str) -> str:
    try:
        return _run_git(root, *arguments).decode("utf-8").strip()
    except UnicodeError as exc:
        raise PreflightError("source state invalid", "Git source identity is malformed", 5) from exc


def _git_source_identity(root: Path) -> str:
    top_level = Path(_git_text(root, "rev-parse", "--show-toplevel")).resolve()
    if top_level != root.resolve():
        raise PreflightError("source state invalid", "root is not the Git worktree root", 5)
    tree = _git_text(root, "rev-parse", "HEAD^{tree}")
    if HEX_DIGEST_RE.fullmatch(tree) is None and re.fullmatch(r"[0-9a-f]{40}", tree) is None:
        raise PreflightError("source state invalid", "Git tree identity is malformed", 5)
    if _git_text(root, "status", "--porcelain=v1", "--untracked-files=all"):
        raise PreflightError("source state invalid", "Git worktree is not clean", 5)
    return tree


def _git_tree_record(root: Path, tree: str) -> dict[str, Any]:
    raw = _run_git(root, "show", f"{tree}:{RECORD_PATH.as_posix()}")
    return _parse_record_bytes(raw)


def _git_tree_inventory(root: Path, tree: str) -> Inventory:
    raw_paths = _run_git(
        root, "ls-tree", "-r", "-z", "--name-only", tree, "--", FONT_DIR.as_posix()
    )
    try:
        names = [item.decode("utf-8") for item in raw_paths.split(b"\0") if item]
    except UnicodeError as exc:
        raise PreflightError("inventory mismatch", "Git font inventory is malformed", 4) from exc
    paths = sorted(
        name
        for name in names
        if Path(name).name.startswith(PROPRIETARY_PREFIXES)
    )
    if not paths:
        raise PreflightError("inventory mismatch", "no proprietary font inventory found", 4)
    lines = []
    for path in paths:
        blob = _run_git(root, "show", f"{tree}:{path}")
        digest = hashlib.sha256(blob).hexdigest()
        lines.append(f"{digest}  {path}\n".encode("utf-8"))
    return Inventory(file_count=len(paths), digest=hashlib.sha256(b"".join(lines)).hexdigest())


def _exact_authorization(
    record: dict[str, Any], operation: str, environment: str, recipient: str
) -> dict[str, Any]:
    for entry in record["authorizations"]:
        if (entry["operation"], entry["environment"], entry["recipient"]) == (
            operation,
            environment,
            recipient,
        ):
            return entry
    raise PreflightError("no exact authorization", "operation tuple is not recorded", 2)


def _verify_inventory(record: dict[str, Any], actual: Inventory) -> None:
    expected = record["proprietary_inventory"]
    if actual.file_count != expected["file_count"] or actual.digest != expected["digest"]:
        raise PreflightError("inventory mismatch", "proprietary font inventory changed", 4)


def preflight(
    root: Path,
    operation: str,
    environment: str,
    recipient: str,
    *,
    today: date | None = None,
) -> dict[str, str]:
    """Return a source-bound authorization decision or raise fail closed."""

    for value, label in (
        (operation, "operation"),
        (environment, "environment"),
        (recipient, "recipient"),
    ):
        _require_identifier(value, label)
    worktree_record = validate_record(load_record(root / RECORD_PATH), today=today)
    worktree_inventory = proprietary_inventory(root)
    _verify_inventory(worktree_record, worktree_inventory)
    entry = _exact_authorization(worktree_record, operation, environment, recipient)
    if entry["status"] != "authorized":
        raise PreflightError("denied", f"authorization status is {entry['status']}", 2)

    # A successful decision is derived again from an immutable Git tree. The
    # preliminary worktree checks above can only deny; mutable bytes can never
    # supply the final authorization or inventory attestation.
    tree = _git_source_identity(root)
    record = validate_record(_git_tree_record(root, tree), today=today)
    actual = _git_tree_inventory(root, tree)
    _verify_inventory(record, actual)
    entry = _exact_authorization(record, operation, environment, recipient)
    if entry["status"] != "authorized":
        raise PreflightError("denied", f"authorization status is {entry['status']}", 2)
    return {
        "decision": "authorized",
        "environment": environment,
        "git_tree": tree,
        "inventory_digest": actual.digest,
        "operation": operation,
        "recipient": recipient,
        "source_kind": "immutable_git_tree",
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Verify an exact proprietary-font distribution authorization."
    )
    parser.add_argument("--operation", required=True)
    parser.add_argument("--environment", required=True)
    parser.add_argument("--recipient", required=True)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        decision = preflight(
            args.root.resolve(), args.operation, args.environment, args.recipient
        )
    except PreflightError as exc:
        print(f"entitlement preflight: {exc.category}: {exc.detail}", file=sys.stderr)
        return exc.exit_code
    except Exception:
        print(
            "entitlement preflight: unexpected failure: no authorization granted",
            file=sys.stderr,
        )
        return 6
    print(json.dumps(decision, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
