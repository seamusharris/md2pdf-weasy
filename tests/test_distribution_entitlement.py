"""Contracts for the fail-closed proprietary-font distribution preflight."""

from __future__ import annotations

import copy
from datetime import date, timedelta
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from tools import distribution_entitlement as entitlement


ROOT = Path(__file__).resolve().parents[1]
RECORD = ROOT / entitlement.RECORD_PATH
SCRIPT = ROOT / "tools/distribution_entitlement.py"
TUPLE = ("package_artifact", "owner_workstation", "owner")


def _checked_record() -> dict:
    return json.loads(RECORD.read_text(encoding="utf-8"))


def _run(root: Path, operation: str, environment: str, recipient: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(root / "tools/distribution_entitlement.py"),
            "--root",
            str(root),
            "--operation",
            operation,
            "--environment",
            environment,
            "--recipient",
            recipient,
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )


def _git(root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    )
    return completed.stdout.strip()


def _worktree_snapshot(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file() and ".git" not in path.relative_to(root).parts
    }


def _authorized_repo(tmp_path: Path) -> tuple[Path, dict]:
    (tmp_path / "docs").mkdir()
    (tmp_path / "pdf/fonts").mkdir(parents=True)
    (tmp_path / "tools").mkdir()
    shutil.copy2(SCRIPT, tmp_path / "tools/distribution_entitlement.py")
    (tmp_path / "pdf/fonts/MinionPro-Test.otf").write_bytes(b"synthetic-minion")
    (tmp_path / "pdf/fonts/MyriadPro-Test.otf").write_bytes(b"synthetic-myriad")

    inventory = entitlement.proprietary_inventory(tmp_path)
    today = date.today()
    record = _checked_record()
    record["decision"] = "authorized"
    record["reviewed_on"] = today.isoformat()
    record["proprietary_inventory"] = {
        "file_count": inventory.file_count,
        "digest_algorithm": "sha256-lines-v1",
        "digest": inventory.digest,
    }
    record["authorizations"] = [
        {
            "operation": TUPLE[0],
            "environment": TUPLE[1],
            "recipient": TUPLE[2],
            "status": "authorized",
            "reason": "Synthetic test authorization with complete opaque references.",
            "approver_ref": "IDENTITY:test-approver",
            "reviewed_on": today.isoformat(),
            "expires_on": (today + timedelta(days=30)).isoformat(),
            "governing_license_ref": "CONTRACT:test-license",
            "environment_evidence_refs": ["ENV:test-workstation"],
            "recipient_evidence_refs": ["RECIPIENT:test-owner"],
        }
    ]
    (tmp_path / entitlement.RECORD_PATH).write_text(
        json.dumps(record, indent=2) + "\n", encoding="utf-8"
    )
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "entitlement-test@example.invalid")
    _git(tmp_path, "config", "user.name", "Entitlement Test")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-q", "-m", "synthetic authorized fixture")
    return tmp_path, record


def test_checked_record_and_exact_inventory_are_valid():
    record = entitlement.validate_record(_checked_record(), today=date(2026, 8, 3))
    inventory = entitlement.proprietary_inventory(ROOT)

    assert inventory.file_count == 94
    assert inventory.digest == "6575f3fd2e10ca5675c8854e3a00b5c6f3f2642b01f6abab0d5ca6f6c7bf9896"
    assert record["proprietary_inventory"] == {
        "file_count": inventory.file_count,
        "digest_algorithm": "sha256-lines-v1",
        "digest": inventory.digest,
    }


def test_checked_matrix_grants_no_distribution_authorization():
    record = _checked_record()

    assert record["decision"] == "not_verified"
    assert {entry["status"] for entry in record["authorizations"]} == {
        "not_verified",
        "prohibited",
    }
    assert not any(entry["status"] == "authorized" for entry in record["authorizations"])


def test_checked_preflight_denies_without_stdout():
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--operation",
            TUPLE[0],
            "--environment",
            TUPLE[1],
            "--recipient",
            TUPLE[2],
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert result.returncode == 2
    assert result.stdout == ""
    assert result.stderr == (
        "entitlement preflight: denied: authorization status is not_verified\n"
    )


def test_unknown_tuple_fails_closed_with_sanitized_diagnostic():
    with pytest.raises(entitlement.PreflightError) as caught:
        entitlement.preflight(ROOT, "package_artifact", "unknown_environment", "owner")

    assert caught.value.category == "no exact authorization"
    assert caught.value.exit_code == 2
    assert "unknown_environment" not in caught.value.detail


def test_duplicate_json_object_key_is_rejected(tmp_path):
    path = tmp_path / "record.json"
    path.write_text('{"schema_version":1,"schema_version":1}', encoding="utf-8")

    with pytest.raises(entitlement.PreflightError, match="duplicate JSON object key"):
        entitlement.load_record(path)


@pytest.mark.parametrize("payload", [b"\xff", b"{", b"[]", b"null"])
def test_invalid_record_encodings_and_shapes_are_rejected(tmp_path, payload):
    path = tmp_path / "record.json"
    path.write_bytes(payload)

    with pytest.raises(entitlement.PreflightError, match="UTF-8 JSON|JSON object"):
        entitlement.load_record(path)


def test_missing_directory_symlink_and_oversize_records_are_rejected(tmp_path):
    with pytest.raises(entitlement.PreflightError, match="unavailable"):
        entitlement.load_record(tmp_path / "missing.json")
    with pytest.raises(entitlement.PreflightError, match="regular file"):
        entitlement.load_record(tmp_path)

    target = tmp_path / "target.json"
    target.write_text("{}", encoding="utf-8")
    link = tmp_path / "link.json"
    link.symlink_to(target)
    with pytest.raises(entitlement.PreflightError, match="regular file"):
        entitlement.load_record(link)

    large = tmp_path / "large.json"
    with large.open("wb") as stream:
        stream.truncate(entitlement.MAX_RECORD_BYTES + 1)
    with pytest.raises(entitlement.PreflightError, match="size limit"):
        entitlement.load_record(large)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda value: value.update(schema_version=2), "schema version"),
        (lambda value: value.update(unexpected=True), "fields"),
        (lambda value: value.update(decision="maybe"), "global decision"),
        (lambda value: value.update(reviewed_on="03-08-2026"), "ISO date"),
        (lambda value: value["proprietary_inventory"].update(file_count=0), "file_count"),
        (lambda value: value["proprietary_inventory"].update(extra=True), "fields"),
        (lambda value: value["proprietary_inventory"].update(digest_algorithm="md5"), "algorithm"),
        (lambda value: value["proprietary_inventory"].update(digest="ABC"), "digest"),
        (lambda value: value["evidence_policy"].update(storage="attachments"), "reference-only"),
        (lambda value: value["evidence_policy"].update(forbidden_content=[]), "reference-only"),
        (lambda value: value.update(evidence_gaps=[]), "evidence_gaps"),
        (lambda value: value["guidance"][0].update(url="http://adobe.com/terms"), "Adobe HTTPS"),
        (lambda value: value["guidance"][0].update(url="https://example.com/terms"), "Adobe HTTPS"),
        (lambda value: value["guidance"][0].update(url="https://["), "Adobe HTTPS"),
        (lambda value: value["authorizations"][0].update(status="pending"), "status"),
        (lambda value: value["authorizations"][0].update(reason=""), "reason"),
        (lambda value: value["authorizations"].append(copy.deepcopy(value["authorizations"][0])), "duplicate authorization"),
    ],
)
def test_malformed_records_fail_closed(mutation, message):
    record = _checked_record()
    mutation(record)

    with pytest.raises(entitlement.PreflightError, match=message):
        entitlement.validate_record(record, today=date(2026, 8, 3))


def test_non_authorized_entry_cannot_carry_approval_evidence():
    record = _checked_record()
    record["authorizations"][0]["approver_ref"] = "IDENTITY:false-approval"

    with pytest.raises(entitlement.PreflightError, match="must not imply approval"):
        entitlement.validate_record(record, today=date(2026, 8, 3))


def test_evidence_fields_accept_only_opaque_references(tmp_path):
    _root, record = _authorized_repo(tmp_path)
    entry = record["authorizations"][0]
    entry["governing_license_ref"] = "https://example.com/secret-license.pdf"

    with pytest.raises(entitlement.PreflightError, match="opaque reference"):
        entitlement.validate_record(record)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda value: value["authorizations"][0].update(reviewed_on="2999-01-01"), "future-dated"),
        (lambda value: value["authorizations"][0].update(expires_on="2000-01-01"), "stale"),
        (
            lambda value: value["authorizations"][0].update(
                environment_evidence_refs=["ENV:duplicate", "ENV:duplicate"]
            ),
            "duplicate references",
        ),
        (lambda value: value.update(decision="not_verified"), "cannot authorize"),
        (lambda value: value.update(decision="partially_authorized"), "mixed"),
    ],
)
def test_authorized_record_date_reference_and_global_invariants(
    tmp_path, mutation, message
):
    _root, record = _authorized_repo(tmp_path)
    mutation(record)

    with pytest.raises(entitlement.PreflightError, match=message):
        entitlement.validate_record(record)


def test_font_directory_enumeration_error_is_sanitized(tmp_path, monkeypatch):
    font_dir = tmp_path / entitlement.FONT_DIR
    font_dir.mkdir(parents=True)
    original = Path.iterdir

    def fail_for_font_dir(path: Path):
        if path == font_dir:
            raise PermissionError("private filesystem detail")
        return original(path)

    monkeypatch.setattr(Path, "iterdir", fail_for_font_dir)
    with pytest.raises(entitlement.PreflightError) as caught:
        entitlement.proprietary_inventory(tmp_path)

    assert caught.value.category == "inventory mismatch"
    assert caught.value.detail == "font inventory is unreadable"


def test_unexpected_cli_failure_is_sanitized(monkeypatch, capsys):
    def fail(*_args, **_kwargs):
        raise RuntimeError("private traceback detail")

    monkeypatch.setattr(entitlement, "preflight", fail)
    exit_code = entitlement.main(
        ["--operation", *TUPLE[:1], "--environment", TUPLE[1], "--recipient", TUPLE[2]]
    )

    captured = capsys.readouterr()
    assert exit_code == 6
    assert captured.out == ""
    assert captured.err == (
        "entitlement preflight: unexpected failure: no authorization granted\n"
    )
    assert "private traceback detail" not in captured.err


def test_synthetic_complete_authorization_succeeds_and_binds_source(tmp_path):
    root, _record = _authorized_repo(tmp_path)
    before = _worktree_snapshot(root)
    result = _run(root, *TUPLE)

    assert result.returncode == 0
    assert result.stderr == ""
    assert _worktree_snapshot(root) == before
    assert _git(root, "status", "--porcelain=v1", "--untracked-files=all") == ""
    decision = json.loads(result.stdout)
    assert decision == {
        "decision": "authorized",
        "environment": TUPLE[1],
        "git_tree": _git(root, "rev-parse", "HEAD^{tree}"),
        "inventory_digest": entitlement.proprietary_inventory(root).digest,
        "operation": TUPLE[0],
        "recipient": TUPLE[2],
        "source_kind": "immutable_git_tree",
    }


def test_denied_preflight_is_read_only(tmp_path):
    root, record = _authorized_repo(tmp_path)
    entry = record["authorizations"][0]
    entry.update(
        status="not_verified",
        approver_ref=None,
        reviewed_on=None,
        expires_on=None,
        governing_license_ref=None,
        environment_evidence_refs=[],
        recipient_evidence_refs=[],
    )
    record["decision"] = "not_verified"
    (root / entitlement.RECORD_PATH).write_text(
        json.dumps(record, indent=2) + "\n", encoding="utf-8"
    )
    _git(root, "add", ".")
    _git(root, "commit", "-q", "-m", "deny synthetic fixture")
    before = _worktree_snapshot(root)

    result = _run(root, *TUPLE)

    assert result.returncode == 2
    assert result.stdout == ""
    assert _worktree_snapshot(root) == before
    assert _git(root, "status", "--porcelain=v1", "--untracked-files=all") == ""


def test_authorization_attests_immutable_tree_when_worktree_changes_after_check(
    tmp_path, monkeypatch
):
    root, record = _authorized_repo(tmp_path)
    font = root / "pdf/fonts/MinionPro-Test.otf"
    original_identity = entitlement._git_source_identity

    def identify_then_mutate(candidate: Path) -> str:
        tree = original_identity(candidate)
        font.write_bytes(b"changed-after-clean-check")
        return tree

    monkeypatch.setattr(entitlement, "_git_source_identity", identify_then_mutate)
    decision = entitlement.preflight(root, *TUPLE)

    assert decision["source_kind"] == "immutable_git_tree"
    assert decision["inventory_digest"] == record["proprietary_inventory"]["digest"]
    assert entitlement.proprietary_inventory(root).digest != decision["inventory_digest"]


@pytest.mark.parametrize(
    ("field", "replacement", "expected_category"),
    [
        ("approver_ref", None, "invalid record"),
        ("reviewed_on", None, "invalid record"),
        ("expires_on", "2000-01-01", "invalid record"),
        ("governing_license_ref", None, "invalid record"),
        ("environment_evidence_refs", [], "invalid record"),
        ("recipient_evidence_refs", [], "invalid record"),
        ("operation", "different_operation", "no exact authorization"),
        ("environment", "different_environment", "no exact authorization"),
        ("recipient", "different_recipient", "no exact authorization"),
    ],
)
def test_authorized_tuple_requires_every_exact_field(
    tmp_path, field, replacement, expected_category
):
    root, record = _authorized_repo(tmp_path)
    record["authorizations"][0][field] = replacement
    (root / entitlement.RECORD_PATH).write_text(
        json.dumps(record, indent=2) + "\n", encoding="utf-8"
    )

    result = _run(root, *TUPLE)

    assert result.returncode != 0
    assert result.stdout == ""
    assert result.stderr.startswith(f"entitlement preflight: {expected_category}:")


def test_authorized_preflight_rejects_inventory_drift_before_source_use(tmp_path):
    root, _record = _authorized_repo(tmp_path)
    (root / "pdf/fonts/MinionPro-Test.otf").write_bytes(b"changed")

    result = _run(root, *TUPLE)

    assert result.returncode == 4
    assert result.stdout == ""
    assert result.stderr == (
        "entitlement preflight: inventory mismatch: proprietary font inventory changed\n"
    )


def test_authorized_preflight_rejects_dirty_git_tree(tmp_path):
    root, _record = _authorized_repo(tmp_path)
    (root / "untracked.txt").write_text("changed after approval", encoding="utf-8")

    result = _run(root, *TUPLE)

    assert result.returncode == 5
    assert result.stdout == ""
    assert result.stderr == (
        "entitlement preflight: source state invalid: Git worktree is not clean\n"
    )


def test_checked_record_contains_references_not_sensitive_evidence():
    record = _checked_record()

    assert record["evidence_policy"] == {
        "storage": "references_only",
        "forbidden_content": [
            "license_documents",
            "font_attachments",
            "account_data",
        ],
    }
    for entry in record["authorizations"]:
        assert entry["approver_ref"] is None
        assert entry["governing_license_ref"] is None
        assert entry["environment_evidence_refs"] == []
        assert entry["recipient_evidence_refs"] == []
