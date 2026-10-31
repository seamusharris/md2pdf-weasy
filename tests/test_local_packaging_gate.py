from __future__ import annotations

import json
from pathlib import Path
import subprocess

import pytest

from tools.local_packaging_gate import cli, gate, model
from tools.integration_audit.model import AuditError
from tools.distribution_entitlement import PreflightError


COMMIT = "1" * 40
TREE = "2" * 40


def _prerequisite(identifier: str, *, authorized: bool) -> model.Prerequisite:
    if authorized:
        return model.Prerequisite(identifier, "authorized", None, None)
    return model.Prerequisite(identifier, "denied", "denied", "not authorized")


def _record() -> model.GateRecord:
    return model.GateRecord(
        COMMIT,
        TREE,
        tuple(_prerequisite(identifier, authorized=False) for identifier in model.PREREQUISITE_IDS),
    )


def test_record_is_canonical_and_round_trips() -> None:
    raw = _record().to_bytes()
    assert model.load_record(raw) == _record()
    assert raw.endswith(b"\n")
    assert json.loads(raw)["artifact_created"] is False
    assert {item["status"] for item in json.loads(raw)["gates"]} == {"not-run"}


@pytest.mark.parametrize(
    "raw",
    [
        b"{}\n",
        b'{"schema_version":1,"schema_version":1}\n',
        _record().to_bytes().replace(b'"blocked"', b'"go"'),
        _record().to_bytes() + b" ",
    ],
)
def test_record_rejects_invalid_or_noncanonical_bytes(raw: bytes) -> None:
    with pytest.raises(model.GateError):
        model.load_record(raw)


@pytest.mark.parametrize(
    "field,value",
    [
        ("status", []),
        ("status", {}),
        ("category", []),
        ("category", "x" * (model.MAX_TEXT + 1)),
        ("detail", "x" * (model.MAX_TEXT + 1)),
    ],
)
def test_record_wraps_malformed_prerequisite_values_as_gate_errors(
    field: str, value: object,
) -> None:
    record = _record().as_dict()
    record["prerequisites"][0][field] = value
    raw = (json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n").encode()
    with pytest.raises(model.GateError, match="invalid"):
        model.load_record(raw)


def test_record_wraps_json_integer_limit_as_gate_error() -> None:
    raw = b'{"value":' + (b"9" * 5_000) + b"}\n"
    with pytest.raises(model.GateError, match="not valid JSON"):
        model.load_record(raw)


@pytest.mark.parametrize("length", [39, 41, 63, 65])
def test_record_rejects_noncanonical_git_object_id_lengths(length: int) -> None:
    record = _record().as_dict()
    record["source_commit"] = "a" * length
    raw = (json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n").encode()
    with pytest.raises(model.GateError, match="full object id"):
        model.load_record(raw)


class _Git:
    root = Path("/repo")

    def text(self, *arguments: str, **_kwargs) -> str:
        if "--format=%T" in arguments:
            return f"{TREE}\n"
        if "HEAD^{tree}" in arguments:
            return f"{TREE}\n"
        return f"{COMMIT}\n"


class _Lease:
    path = Path("/lease")
    held = False

    def __init__(self, _path: Path) -> None:
        pass

    def __enter__(self) -> "_Lease":
        self.held = True
        return self

    def __exit__(self, *_args) -> None:
        self.held = False


def _patch_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gate, "GitRunner", lambda _root: _Git())
    monkeypatch.setattr(gate, "lease_path", lambda _git: Path("/lease"))
    monkeypatch.setattr(gate, "RepositoryLease", _Lease)


def test_denials_are_both_evaluated_before_canonical_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_runtime(monkeypatch)
    calls: list[str] = []

    def deny_integration(_root: Path, lease: _Lease) -> str:
        assert lease.held
        calls.append("integration")
        raise AuditError("evidence rejected", "activation is absent")

    def deny_entitlement(*_args) -> dict[str, str]:
        calls.append("entitlement")
        raise PreflightError("denied", "authorization status is not_verified", 2)

    published: list[bytes] = []
    monkeypatch.setattr(gate, "verify_downstream_with_lease", deny_integration)
    monkeypatch.setattr(gate, "preflight", deny_entitlement)
    result = gate.run(Path("/repo"), lambda raw: not published.append(raw))
    assert calls == ["integration", "entitlement"]
    assert result == model.load_record(published[0])
    assert [item.status for item in result.prerequisites] == ["denied", "denied"]


@pytest.mark.parametrize("integration_authorized", [False, True])
def test_one_authorized_prerequisite_still_emits_blocked_evidence(
    monkeypatch: pytest.MonkeyPatch, integration_authorized: bool,
) -> None:
    _patch_runtime(monkeypatch)
    if integration_authorized:
        monkeypatch.setattr(
            gate, "verify_downstream_with_lease", lambda *_args: COMMIT,
        )
        monkeypatch.setattr(
            gate,
            "preflight",
            lambda *_args: (_ for _ in ()).throw(
                PreflightError("denied", "not authorized", 2)
            ),
        )
    else:
        monkeypatch.setattr(
            gate,
            "verify_downstream_with_lease",
            lambda *_args: (_ for _ in ()).throw(
                AuditError("denied", "not accepted")
            ),
        )
        monkeypatch.setattr(
            gate,
            "preflight",
            lambda *_args: {"git_tree": TREE, "inventory_digest": "4" * 64},
        )
    published: list[bytes] = []
    result = gate.run(Path("/repo"), lambda raw: not published.append(raw))
    expected = ["authorized", "denied"] if integration_authorized else ["denied", "authorized"]
    assert [item.status for item in result.prerequisites] == expected
    assert model.load_record(published[0]) == result


def test_source_identity_change_blocks_output(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_runtime(monkeypatch)

    class ChangingGit(_Git):
        head_reads = 0

        def text(self, *arguments: str, **kwargs) -> str:
            if arguments == ("rev-parse", "--verify", "HEAD"):
                self.head_reads += 1
                return f"{COMMIT if self.head_reads == 1 else '9' * 40}\n"
            return super().text(*arguments, **kwargs)

    monkeypatch.setattr(gate, "GitRunner", lambda _root: ChangingGit())
    monkeypatch.setattr(
        gate,
        "verify_downstream_with_lease",
        lambda *_args: (_ for _ in ()).throw(AuditError("denied", "not accepted")),
    )
    monkeypatch.setattr(
        gate,
        "preflight",
        lambda *_args: (_ for _ in ()).throw(
            PreflightError("denied", "not authorized", 2)
        ),
    )
    with pytest.raises(model.GateError, match="source identity changed"):
        gate.run(Path("/repo"), lambda _raw: pytest.fail("must not publish"))


def test_authorized_identity_mismatch_fails_without_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_runtime(monkeypatch)
    monkeypatch.setattr(gate, "verify_downstream_with_lease", lambda *_args: COMMIT)
    monkeypatch.setattr(
        gate,
        "preflight",
        lambda *_args: {"git_tree": "3" * 40, "inventory_digest": "4" * 64},
    )
    with pytest.raises(model.GateError, match="accepted, authorized, and source trees differ"):
        gate.run(Path("/repo"), lambda _raw: pytest.fail("must not publish"))


def test_entitlement_identity_mismatch_fails_when_integration_is_denied(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_runtime(monkeypatch)
    monkeypatch.setattr(
        gate,
        "verify_downstream_with_lease",
        lambda *_args: (_ for _ in ()).throw(AuditError("denied", "not accepted")),
    )
    monkeypatch.setattr(
        gate,
        "preflight",
        lambda *_args: {"git_tree": "3" * 40, "inventory_digest": "4" * 64},
    )
    with pytest.raises(model.GateError, match="accepted, authorized, and source trees differ"):
        gate.run(Path("/repo"), lambda _raw: pytest.fail("must not publish"))


def test_fully_authorized_state_fails_closed_until_workflow_is_active(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_runtime(monkeypatch)
    monkeypatch.setattr(gate, "verify_downstream_with_lease", lambda *_args: COMMIT)
    monkeypatch.setattr(
        gate,
        "preflight",
        lambda *_args: {"git_tree": TREE, "inventory_digest": "4" * 64},
    )
    with pytest.raises(model.GateError, match="authorized packaging workflow is not active"):
        gate.run(Path("/repo"), lambda _raw: pytest.fail("must not publish"))


def test_output_failure_is_blocking(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_runtime(monkeypatch)
    monkeypatch.setattr(
        gate,
        "verify_downstream_with_lease",
        lambda *_args: (_ for _ in ()).throw(AuditError("denied", "not accepted")),
    )
    monkeypatch.setattr(
        gate,
        "preflight",
        lambda *_args: (_ for _ in ()).throw(PreflightError("denied", "not authorized")),
    )
    with pytest.raises(model.GateError, match="evidence was not written"):
        gate.run(Path("/repo"), lambda _raw: False)


def test_real_checked_records_take_artifact_free_blocked_path() -> None:
    root = Path(__file__).resolve().parents[1]
    published: list[bytes] = []
    record = gate.run(root, lambda raw: not published.append(raw))
    assert record == model.load_record(published[0])
    assert record.as_dict()["artifact_created"] is False
    assert [item.status for item in record.prerequisites] == ["denied", "denied"]


def test_checked_blocked_record_is_canonical() -> None:
    path = Path(__file__).resolve().parents[1] / "docs" / "local-packaging-gates.json"
    assert model.load_record(path.read_bytes()).as_dict()["decision"] == "blocked"


def test_documented_make_invocation_keeps_stdout_canonical() -> None:
    root = Path(__file__).resolve().parents[1]
    completed = subprocess.run(
        ["make", "local-packaging-gates"],
        cwd=root,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 2
    assert model.load_record(completed.stdout).as_dict()["decision"] == "blocked"
    assert b"Error 1" in completed.stderr


def test_cli_returns_blocked_status_and_canonical_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(cli, "run", lambda _root, publish: publish(_record().to_bytes()))
    assert cli.main(["--root", str(tmp_path)]) == 1
    assert model.load_record(capsys.readouterr().out.encode()) == _record()


def test_cli_handles_unavailable_stdout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_output(_root: Path, publish) -> None:
        if not publish(_record().to_bytes()):
            raise model.GateError("output failed", "canonical evidence was not written")

    monkeypatch.setattr(cli.sys, "stdout", None)
    monkeypatch.setattr(cli, "run", fail_output)
    assert cli.main(["--root", str(tmp_path)]) == 3


_DEFAULT_WRITE_RESULT = object()


class _ShortWriteBuffer:
    def __init__(self, *, limit: int = 2, result: object = _DEFAULT_WRITE_RESULT,
                 write_error: bool = False, flush_error: bool = False) -> None:
        self.limit = limit
        self.result = result
        self.write_error = write_error
        self.flush_error = flush_error
        self.value = bytearray()
        self.flushed = False

    def write(self, content: memoryview) -> object:
        if self.write_error:
            raise OSError("write failed")
        if self.result is not _DEFAULT_WRITE_RESULT:
            return self.result
        count = min(self.limit, len(content))
        self.value.extend(content[:count])
        return count

    def flush(self) -> None:
        if self.flush_error:
            raise OSError("flush failed")
        self.flushed = True


class _Stream:
    def __init__(self, buffer: _ShortWriteBuffer) -> None:
        self.buffer = buffer


def test_cli_exact_writer_completes_repeated_short_writes() -> None:
    buffer = _ShortWriteBuffer(limit=2)
    assert cli._write(_Stream(buffer), b"abcdef")
    assert bytes(buffer.value) == b"abcdef"
    assert buffer.flushed


@pytest.mark.parametrize("result", [None, 0, -1, True, 99, "1"])
def test_cli_exact_writer_rejects_invalid_progress(result: object) -> None:
    assert not cli._write(_Stream(_ShortWriteBuffer(result=result)), b"abc")


@pytest.mark.parametrize(
    "write_error,flush_error",
    [(True, False), (False, True)],
)
def test_cli_exact_writer_rejects_io_failures(
    write_error: bool, flush_error: bool,
) -> None:
    buffer = _ShortWriteBuffer(
        write_error=write_error, flush_error=flush_error,
    )
    assert not cli._write(_Stream(buffer), b"abc")
