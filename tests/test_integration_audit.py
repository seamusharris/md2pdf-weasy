"""Contracts for immutable integration-candidate audit tooling."""

from __future__ import annotations

from dataclasses import replace
import io
import json
import multiprocessing
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import threading
import time

import pytest

from tools.integration_audit import (
    archive, audit, cli, git_commands, history, hygiene, isolate, lifecycle, model,
    process, publication, resources, sandbox, state, verifier, workspace,
)


ROOT = Path(__file__).resolve().parents[1]


def _git(root: Path, *args: str, check: bool = True) -> str:
    completed = subprocess.run(
        ("git", "-C", str(root), *args), check=check,
        capture_output=True, text=True, timeout=20,
    )
    return completed.stdout.strip()


def _commit(root: Path, name: str, content: str) -> str:
    (root / name).parent.mkdir(parents=True, exist_ok=True)
    (root / name).write_text(content, encoding="utf-8")
    _git(root, "add", name)
    _git(root, "commit", "-q", "-m", name)
    return _git(root, "rev-parse", "HEAD")


def _repo(root: Path) -> str:
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.email", "audit-test@example.invalid")
    _git(root, "config", "user.name", "Audit Test")
    candidate = _commit(root, "base.txt", "base\n")
    _git(root, "branch", "feature")
    _git(root, "switch", "-q", "feature")
    return candidate


def _result(**changes) -> model.AuditResult:
    values = {
        "candidate_commit": "a" * 40,
        "candidate_tree": "b" * 40,
        "base_commit": "c" * 40,
        "original_tip": "d" * 40,
        "original_commits": ("e" * 40,),
        "stabilization_commits": ("f" * 40,),
        "history_sha256": "1" * 64,
        "diff_sha256": "2" * 64,
        "changed_paths_sha256": "3" * 64,
        "changed_path_count": 1,
        "validations": ("suite: pass",),
    }
    values.update(changes)
    return model.AuditResult(**values)


def _evidence_files(root: Path, candidate: str) -> dict[str, bytes]:
    tree = _git(root, "show", "-s", "--format=%T", candidate)
    return {
        "docs/integration-audit.json": _result(
            candidate_commit=candidate, candidate_tree=tree,
        ).to_bytes(),
    }


def test_result_is_canonical_round_trippable_and_strict() -> None:
    result = _result()
    assert model.load_result(result.to_bytes()) == result
    assert result.to_bytes() == model.canonical_bytes(result.to_dict())
    duplicate = b'{"schema_version":1,"schema_version":1}\n'
    with pytest.raises(model.AuditError, match="duplicate"):
        model.load_result(duplicate)
    with pytest.raises(model.AuditError, match="canonical"):
        model.load_result(json.dumps(result.to_dict()).encode())
    no_go = _result(decision=model.NO_GO_DECISION)
    assert model.load_result(no_go.to_bytes(), require_go=False) == no_go
    with pytest.raises(model.AuditError, match="not a go"):
        model.load_result(no_go.to_bytes())


def test_checked_audit_record_is_canonical_sanitized_and_no_go() -> None:
    raw = (ROOT / "docs/integration-audit.json").read_bytes()
    record = model.load_result(raw, require_go=False)
    assert record.candidate_commit == history.CANDIDATE_COMMIT
    assert record.candidate_tree == "dd8a0a74f066df7dbce772fdc3061dc845f4d1a9"
    assert record.decision == model.NO_GO_DECISION
    assert len(record.original_commits) == 15
    assert len(record.stabilization_commits) == 18
    assert b"/Users/" not in raw and b"/private/tmp" not in raw
    assert "integration-audit.md" in (ROOT / "docs/README.md").read_text()


@pytest.mark.parametrize("value", ["abc", "A" * 40, "-" + "a" * 39])
def test_full_candidate_id_is_required(value: str) -> None:
    with pytest.raises(model.AuditError, match="canonical full"):
        model.require_sha(value, "candidate")


def test_process_output_bound_and_timeout(tmp_path: Path) -> None:
    command = (sys.executable, "-c", "print('abcd', end='')")
    assert process.run_bounded(command, cwd=tmp_path, capture_limit=4)[0] == "abcd"
    with pytest.raises(model.AuditError, match="output limit"):
        process.run_bounded(command, cwd=tmp_path, capture_limit=3)
    with pytest.raises(model.AuditError, match="deadline"):
        process.run_bounded(
            (sys.executable, "-c", "import time; time.sleep(10)"),
            cwd=tmp_path, timeout=0.1,
        )


def test_process_large_stdin_is_drained_with_stdout_under_one_deadline(tmp_path: Path) -> None:
    payload = b"x" * (1024 * 1024)
    script = (
        "import sys;"
        "sys.stdout.buffer.write(b'y'*1048576);sys.stdout.buffer.flush();"
        "data=sys.stdin.buffer.read();print(len(data))"
    )
    stdout, _ = process.run_bounded(
        (sys.executable, "-c", script), cwd=tmp_path, input_bytes=payload,
        timeout=10, capture_limit=2 * 1024 * 1024,
    )
    assert stdout.endswith("1048576\n")


@pytest.mark.parametrize("failure", ["selector", "read"])
def test_process_io_failures_are_normalized_after_cleanup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str,
) -> None:
    reaped: list[int] = []
    real_reap = process.terminate_and_reap

    def record_reap(child) -> int:
        result = real_reap(child)
        reaped.append(child.pid)
        return result

    monkeypatch.setattr(process, "terminate_and_reap", record_reap)
    if failure == "selector":
        monkeypatch.setattr(
            process.selectors, "DefaultSelector",
            lambda: (_ for _ in ()).throw(OSError("injected selector failure")),
        )
    else:
        monkeypatch.setattr(
            process, "_handle_ready_stream",
            lambda *_args: (_ for _ in ()).throw(OSError("injected read failure")),
        )
    with pytest.raises(model.AuditError, match="command io"):
        process.run_bounded(
            (sys.executable, "-c", "import time;print('ready',flush=True);time.sleep(10)"),
            cwd=tmp_path, timeout=2,
        )
    assert len(reaped) == 1


def test_process_timeout_reaps_descendant(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    pid_file = tmp_path / "child.pid"
    script = (
        "import pathlib,subprocess,sys,time;"
        "p=subprocess.Popen([sys.executable,'-c','import time;time.sleep(10)']);"
        f"pathlib.Path({str(pid_file)!r}).write_text(str(p.pid));time.sleep(10)"
    )
    failures: list[BaseException] = []
    real_exchange = process._exchange_bounded

    def exchange_after_ready(child, **kwargs):
        deadline = time.monotonic() + 5
        while not pid_file.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert pid_file.exists(), "child readiness handshake did not complete"
        kwargs["started"] = time.monotonic() - kwargs["timeout"]
        return real_exchange(child, **kwargs)

    monkeypatch.setattr(process, "_exchange_bounded", exchange_after_ready)

    def run() -> None:
        try:
            process.run_bounded((sys.executable, "-c", script), cwd=tmp_path, timeout=10)
        except BaseException as exc:
            failures.append(exc)

    worker = threading.Thread(target=run)
    worker.start()
    deadline = time.monotonic() + 5
    while not pid_file.exists() and time.monotonic() < deadline:
        time.sleep(0.01)
    assert pid_file.exists(), "child readiness handshake did not complete"
    worker.join(5)
    assert len(failures) == 1 and "deadline" in str(failures[0])
    child = int(pid_file.read_text())
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        try:
            os.kill(child, 0)
        except ProcessLookupError:
            break
        time.sleep(0.02)
    else:
        pytest.fail("descendant survived process-group cleanup")


def test_successful_leader_exit_still_reaps_background_group(tmp_path: Path) -> None:
    pid_file = tmp_path / "background.pid"
    ready = tmp_path / "background.ready"
    survived = tmp_path / "survived.txt"
    descendant = (
        f"import pathlib,time;pathlib.Path({str(ready)!r}).write_text('ready');"
        "time.sleep(10);"
        f"pathlib.Path({str(survived)!r}).write_text('alive')"
    )
    script = (
        "import os,pathlib,subprocess,sys,time\n"
        f"p=subprocess.Popen([sys.executable,'-c',{descendant!r}],"
        "stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)\n"
        f"pathlib.Path({str(pid_file)!r}).write_text(f'{{os.getpid()}} {{p.pid}}')\n"
        f"ready=pathlib.Path({str(ready)!r})\n"
        "deadline=time.monotonic()+5\n"
        "while not ready.exists() and time.monotonic()<deadline: time.sleep(.01)\n"
    )
    process.run_bounded((sys.executable, "-c", script), cwd=tmp_path)
    leader, child = map(int, pid_file.read_text().split())
    assert ready.exists()
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        try:
            os.kill(child, 0)
        except ProcessLookupError:
            break
        time.sleep(0.02)
    else:
        pytest.fail("successful command left its background descendant alive")
    assert child not in lifecycle.group_members(leader)
    assert not survived.exists()


def test_process_group_is_reinventoried_and_repeatedly_killed_before_leader_reap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []

    class FakeProcess:
        pid = 1234

        def wait(self) -> int:
            events.append("reap")
            return 0

    inventories = iter(({1234, 5678}, {1234}))
    monkeypatch.setattr(lifecycle, "leader_exited_unreaped", lambda _child: True)
    monkeypatch.setattr(
        lifecycle, "signal_group", lambda _child, sig: events.append(f"signal:{sig.name}"),
    )
    monkeypatch.setattr(lifecycle, "group_members", lambda _group: next(inventories))
    monkeypatch.setattr(lifecycle.time, "sleep", lambda _seconds: None)
    assert lifecycle.terminate_and_reap(FakeProcess()) == 0
    assert events == ["signal:SIGTERM", "signal:SIGKILL", "signal:SIGKILL", "reap"]


def test_linux_group_inventory_ignores_processes_that_vanish(tmp_path: Path) -> None:
    present = tmp_path / "123"
    vanished = tmp_path / "456"
    present.mkdir()
    vanished.mkdir()
    (present / "stat").write_text("123 (worker) S 1 99 0 0\n", encoding="ascii")
    assert lifecycle._linux_group_members(tmp_path, 99) == {123}


def test_darwin_group_inventory_retries_a_saturated_fill(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capacities: list[int] = []

    class FakeListPids:
        argtypes = None
        restype = None

        def __call__(self, _kind: int, _group: int, buffer, size: int) -> int:
            if buffer is None:
                return 4
            capacities.append(size)
            if len(capacities) == 1:
                return size
            buffer[0] = 123
            return 4

    class FakeLibrary:
        proc_listpids = FakeListPids()

    monkeypatch.setattr(lifecycle.ctypes, "CDLL", lambda *_args, **_kwargs: FakeLibrary())
    assert lifecycle._darwin_group_members(99) == {123}
    assert len(capacities) == 2 and capacities[1] == capacities[0] * 2


def test_protected_command_environment_cannot_be_overridden() -> None:
    assert process.clean_environment()["GIT_NO_REPLACE_OBJECTS"] == "1"
    with pytest.raises(model.AuditError, match="protected"):
        process.clean_environment({"GIT_NO_REPLACE_OBJECTS": "0"})


def test_kernel_memory_and_process_limits_are_applied(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(process, "group_usage", lambda _group: (0, 1))
    memory_script = (
        "try: bytearray(512*1024*1024)\n"
        "except (MemoryError,OSError): print('blocked')\n"
        "else: print('escaped')\n"
    )
    try:
        stdout, _ = process.run_bounded(
            (sys.executable, "-c", memory_script), cwd=tmp_path,
            resource_limits=True, memory_limit_bytes=256 * 1024 * 1024,
        )
    except model.AuditError as exc:
        if "status 125" in str(exc):
            pytest.skip("this kernel refused the requested hard resource limits")
        raise
    assert stdout == "blocked\n"
    if not hasattr(resources.resource, "RLIMIT_NPROC") or os.geteuid() == 0:
        return
    process_script = (
        "import subprocess\n"
        "try: subprocess.run(['/usr/bin/true'],check=True)\n"
        "except OSError: print('blocked')\n"
        "else: print('escaped')\n"
    )
    stdout, _ = process.run_bounded(
        (sys.executable, "-c", process_script), cwd=tmp_path,
        resource_limits=True, process_limit=1,
    )
    if stdout == "escaped\n":
        pytest.skip("RLIMIT_NPROC is present but not enforced for this account")
    assert stdout == "blocked\n"


def test_resource_limit_installer_includes_process_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    if not hasattr(resources.resource, "RLIMIT_NPROC"):
        pytest.skip("RLIMIT_NPROC is unavailable")
    calls: list[tuple[int, tuple[int, int]]] = []
    monkeypatch.setattr(
        resources.resource, "getrlimit",
        lambda _key: (resources.resource.RLIM_INFINITY, resources.resource.RLIM_INFINITY),
    )
    monkeypatch.setattr(
        resources.resource, "setrlimit", lambda key, value: calls.append((key, value)),
    )
    resources.apply_resource_limits(None, 7)
    assert (resources.resource.RLIMIT_NPROC, (7, 7)) in calls


@pytest.mark.parametrize("quiet", [False, True])
@pytest.mark.parametrize("usage", [(2, 1), (0, 3)])
def test_process_monitors_enforce_group_resource_limits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    quiet: bool, usage: tuple[int, int],
) -> None:
    monkeypatch.setattr(process, "group_usage", lambda _group: usage)
    command = (sys.executable, "-c", "import time;time.sleep(10)")
    kwargs = {
        "cwd": tmp_path, "timeout": 2, "memory_limit_bytes": 1,
        "process_limit": 2,
    }
    runner = process.run_bounded_quiet if quiet else process.run_bounded
    with pytest.raises(model.AuditError, match="resource limit"):
        runner(command, **kwargs)


def test_group_usage_samples_the_process_group_in_one_query(monkeypatch: pytest.MonkeyPatch) -> None:
    completed = subprocess.CompletedProcess([], 0, stdout=b"10 5\n20 7\n")
    calls: list[tuple[str, ...]] = []

    def run(command: tuple[str, ...], **_kwargs: object):
        calls.append(command)
        return completed

    monkeypatch.setattr(resources.subprocess, "run", run)
    assert resources.group_usage(99) == (12 * 1024, 2)
    assert calls == [("/bin/ps", "-o", "pid=,rss=", "-g", "99")]


@pytest.mark.parametrize(
    "failure",
    [subprocess.CompletedProcess([], 0, stdout=b"10 malformed\n"), OSError("unavailable")],
)
def test_group_usage_failures_are_bounded(
    monkeypatch: pytest.MonkeyPatch, failure: object,
) -> None:
    def run(*_args: object, **_kwargs: object):
        if isinstance(failure, BaseException):
            raise failure
        return failure

    monkeypatch.setattr(resources.subprocess, "run", run)
    with pytest.raises(model.AuditError, match="memory usage"):
        resources.group_usage(99)


@pytest.mark.parametrize("raw", [b"10 1\n10 2\n", b"0 1\n", b"10 -1\n"])
def test_group_usage_rejects_invalid_numeric_rows(
    monkeypatch: pytest.MonkeyPatch, raw: bytes,
) -> None:
    completed = subprocess.CompletedProcess([], 0, stdout=raw)
    monkeypatch.setattr(resources.subprocess, "run", lambda *_args, **_kwargs: completed)
    with pytest.raises(model.AuditError, match="malformed"):
        resources.group_usage(99)


def test_group_usage_process_count_boundary(monkeypatch: pytest.MonkeyPatch) -> None:
    raw = b"".join(f"{pid} 1\n".encode("ascii") for pid in range(1, 4_097))
    completed = subprocess.CompletedProcess([], 0, stdout=raw)
    monkeypatch.setattr(resources.subprocess, "run", lambda *_args, **_kwargs: completed)
    assert resources.group_usage(99) == (4_096 * 1_024, 4_096)

    completed.stdout += b"4097 1\n"
    with pytest.raises(model.AuditError, match="malformed"):
        resources.group_usage(99)


def test_group_usage_output_size_boundary(monkeypatch: pytest.MonkeyPatch) -> None:
    limit = 4 * 1024 * 1024
    completed = subprocess.CompletedProcess([], 0, stdout=b"1 1" + b" " * (limit - 4) + b"\n")
    monkeypatch.setattr(resources.subprocess, "run", lambda *_args, **_kwargs: completed)
    assert len(completed.stdout) == limit
    assert resources.group_usage(99) == (1_024, 1)

    completed.stdout += b" "
    with pytest.raises(model.AuditError, match="exceeded"):
        resources.group_usage(99)


def test_git_text_rejects_non_utf8_protocol_data(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = git_commands.GitRunner(tmp_path)
    monkeypatch.setattr(runner, "bytes", lambda *_args, **_kwargs: b"\xff")
    with pytest.raises(model.AuditError, match="non-UTF-8"):
        runner.text("status")


def _tar(entries: list[tuple[str, bytes, str]]) -> bytes:
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w") as bundle:
        for name, content, kind in entries:
            member = tarfile.TarInfo(name)
            if kind == "file":
                member.size = len(content)
                bundle.addfile(member, io.BytesIO(content))
            elif kind == "dir":
                member.type = tarfile.DIRTYPE
                bundle.addfile(member)
            elif kind == "symlink":
                member.type = tarfile.SYMTYPE
                member.linkname = "target"
                bundle.addfile(member)
            elif kind == "hardlink":
                member.type = tarfile.LNKTYPE
                member.linkname = "target"
                bundle.addfile(member)
            elif kind == "fifo":
                member.type = tarfile.FIFOTYPE
                bundle.addfile(member)
    return stream.getvalue()


def test_safe_archive_extracts_regular_entries(tmp_path: Path) -> None:
    destination = tmp_path / "out"
    destination.mkdir()
    isolate.safe_extract_archive(_tar([("a/", b"", "dir"), ("a/b.txt", b"ok", "file")]), destination)
    assert (destination / "a/b.txt").read_bytes() == b"ok"


@pytest.mark.parametrize("entry", [
    ("../escape", "file"), ("/absolute", "file"), ("link", "symlink"),
    ("hard", "hardlink"), ("pipe", "fifo"),
])
def test_safe_archive_rejects_escape_links_and_special_entries(tmp_path: Path, entry: tuple[str, str]) -> None:
    destination = tmp_path / "out"
    destination.mkdir()
    with pytest.raises(model.AuditError, match="archive"):
        isolate.safe_extract_archive(_tar([(entry[0], b"x", entry[1])]), destination)


def test_archive_entry_and_size_boundaries(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    destination = tmp_path / "out"
    destination.mkdir()
    monkeypatch.setattr(archive, "MAX_ARCHIVE_ENTRIES", 1)
    with pytest.raises(model.AuditError, match="too many"):
        isolate.safe_extract_archive(_tar([("a", b"", "file"), ("b", b"", "file")]), destination)
    monkeypatch.setattr(archive, "MAX_ARCHIVE_ENTRIES", 20)
    monkeypatch.setattr(archive, "MAX_ARCHIVE_FILE_BYTES", 1)
    with pytest.raises(model.AuditError, match="member"):
        isolate.safe_extract_archive(_tar([("large", b"xx", "file")]), destination)


def _hold_lease(path: str, ready: multiprocessing.Event, release: multiprocessing.Event) -> None:
    with state.RepositoryLease(Path(path)):
        ready.set()
        release.wait(5)


def test_repository_lease_is_nonblocking(tmp_path: Path) -> None:
    lock = tmp_path / "audit.lock"
    ready = multiprocessing.Event()
    release = multiprocessing.Event()
    worker = multiprocessing.Process(target=_hold_lease, args=(str(lock), ready, release))
    worker.start()
    assert ready.wait(5)
    try:
        with pytest.raises(model.AuditError, match="another integration gate"):
            with state.RepositoryLease(lock):
                pass
    finally:
        release.set()
        worker.join(5)
    assert worker.exitcode == 0


def test_repository_lease_release_failure_is_bounded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    lease = state.RepositoryLease(tmp_path / "audit.lock")
    lease.__enter__()
    real_close = state.os.close

    def close_then_fail(descriptor: int) -> None:
        real_close(descriptor)
        raise OSError("injected close failure")

    monkeypatch.setattr(state.os, "close", close_then_fail)
    with pytest.raises(model.AuditError, match="could not be released") as caught:
        lease.__exit__(None, None, None)
    assert caught.value.residue


def test_linked_worktrees_share_one_repository_lease(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _repo(repo)
    linked = tmp_path / "linked"
    _git(repo, "worktree", "add", "-q", "-b", "other", str(linked), "main")
    assert state.lease_path(git_commands.GitRunner(repo)) == state.lease_path(git_commands.GitRunner(linked))


def test_snapshot_ignores_untracked_but_detects_tracked_mutation(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _repo(repo)
    runner = git_commands.GitRunner(repo)
    before = state.capture_snapshot(runner)
    (repo / "untracked.txt").write_text("mine\n")
    assert state.capture_snapshot(runner) == before
    (repo / "base.txt").write_text("changed\n")
    with pytest.raises(model.AuditError, match="protected"):
        state.require_unchanged(runner, before)


@pytest.mark.parametrize("operation", ["fchmod", "write", "close"])
def test_snapshot_index_io_failure_is_bounded_and_cleaned(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, operation: str,
) -> None:
    shared_index = tmp_path / "shared-index"
    shared_index.write_bytes(b"DIRC")

    class FakeGit:
        root = tmp_path

        def text(self, *args: str, **_kwargs: object) -> str:
            if args[:3] == ("rev-parse", "--git-path", "index"):
                return str(shared_index)
            if args[0] == "write-tree":
                return "a" * 40
            raise AssertionError(args)

    real_mkstemp = state.tempfile.mkstemp
    real_operation = getattr(state.os, operation)
    injected = False
    target_descriptor: int | None = None

    def local_mkstemp(*, prefix: str):
        nonlocal target_descriptor
        target_descriptor, name = real_mkstemp(prefix=prefix, dir=tmp_path)
        return target_descriptor, name

    def fail_once(*args):
        nonlocal injected
        if args and args[0] == target_descriptor and not injected:
            injected = True
            raise OSError("injected snapshot-index failure")
        return real_operation(*args)

    monkeypatch.setattr(state.tempfile, "mkstemp", local_mkstemp)
    monkeypatch.setattr(state.os, operation, fail_once)
    with pytest.raises(model.AuditError, match="repository state"):
        state._index_tree(FakeGit())
    assert not tuple(tmp_path.glob("md2pdf-audit-snapshot-index-*"))


def test_history_policy_accepts_exact_linear_graph(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = tmp_path / "repo"
    base = _repo(repo)
    first = _commit(repo, "one.txt", "one\n")
    tip = _commit(repo, "two.txt", "two\n")
    candidate = _commit(repo, "three.txt", "three\n")
    monkeypatch.setattr(history, "BASE_COMMIT", base)
    monkeypatch.setattr(history, "ORIGINAL_COMMITS", (first, tip))
    monkeypatch.setattr(history, "ORIGINAL_TIP", tip)
    monkeypatch.setattr(history, "CANDIDATE_COMMIT", candidate)
    monkeypatch.setattr(history, "STABILIZATION_COUNT", 1)
    evidence = history.verify_history(git_commands.GitRunner(repo), candidate)
    assert evidence.stabilization_commits == (candidate,)


def test_history_policy_rejects_abbreviated_and_moved_main(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = tmp_path / "repo"
    base = _repo(repo)
    candidate = _commit(repo, "one.txt", "one\n")
    monkeypatch.setattr(history, "BASE_COMMIT", base)
    monkeypatch.setattr(history, "ORIGINAL_COMMITS", (candidate,))
    monkeypatch.setattr(history, "ORIGINAL_TIP", candidate)
    monkeypatch.setattr(history, "CANDIDATE_COMMIT", candidate)
    monkeypatch.setattr(history, "STABILIZATION_COUNT", 0)
    with pytest.raises(model.AuditError, match="canonical full"):
        history.verify_history(git_commands.GitRunner(repo), candidate[:8])
    _git(repo, "branch", "-f", "main", candidate)
    with pytest.raises(model.AuditError, match="local main"):
        history.verify_history(git_commands.GitRunner(repo), candidate)


@pytest.mark.parametrize("mechanism", ["replace", "graft"])
def test_history_rejects_object_substitution(tmp_path: Path, mechanism: str) -> None:
    repo = tmp_path / "repo"
    base = _repo(repo)
    candidate = _commit(repo, "one.txt", "one\n")
    if mechanism == "replace":
        _git(repo, "replace", candidate, base)
        match = "replacement"
    else:
        info = repo / ".git" / "info"
        info.mkdir(exist_ok=True)
        (info / "grafts").write_text(f"{candidate} {base}\n", encoding="ascii")
        match = "grafts"
    with pytest.raises(model.AuditError, match=match):
        history.verify_history(git_commands.GitRunner(repo), candidate)


def test_hygiene_is_object_based_and_rejects_conflict_markers(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = tmp_path / "repo"
    base = _repo(repo)
    candidate = _commit(repo, "ok.txt", "clean\n")
    monkeypatch.setattr(hygiene, "BASE_COMMIT", base)
    evidence = hygiene.verify_hygiene(git_commands.GitRunner(repo), candidate)
    assert evidence.changed_paths == ("ok.txt",)
    bad = _commit(repo, "bad.txt", "<<<<<<< ours\n=======\n>>>>>>> theirs\n")
    with pytest.raises(model.AuditError, match="diff hygiene"):
        hygiene.verify_hygiene(git_commands.GitRunner(repo), bad)


def test_hygiene_rejects_malformed_batch_protocols() -> None:
    object_id = "a" * 40

    class MalformedSizes:
        def bytes(self, *_args: str, **_kwargs: object) -> bytes:
            return f"{object_id} blob not-a-size\n".encode("ascii")

    with pytest.raises(model.AuditError, match="blob size"):
        hygiene._bounded_blob_sizes(MalformedSizes(), (object_id,))

    class TrailingBatch:
        def bytes(self, *_args: str, **_kwargs: object) -> bytes:
            return f"{object_id} blob 1\nx\ntrailing".encode("ascii")

    with pytest.raises(model.AuditError, match="trailing data"):
        hygiene._scan_blob_batch(TrailingBatch(), [(object_id, 1)])


def test_build_evidence_commit_and_refuse_live_checkout_publication(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    candidate = _repo(repo)
    runner = git_commands.GitRunner(repo)
    before = state.capture_snapshot(runner)
    commit, tree = publication.build_evidence_commit(
        runner, candidate=candidate, files=_evidence_files(repo, candidate),
        message="audit evidence",
    )
    assert _git(repo, "rev-parse", "HEAD") == candidate
    with pytest.raises(model.AuditError, match="operator"):
        publication.require_operator_publication(
            runner, before=before, candidate=candidate, commit=commit, tree=tree,
        )
    assert state.capture_snapshot(runner) == before
    assert _git(repo, "rev-parse", "HEAD") == candidate
    assert _git(repo, "show-ref", "--verify", state.ACTIVATION_REF, check=False) == ""
    assert _git(repo, "status", "--porcelain", "-uno") == ""


def test_no_go_record_cannot_be_published(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    candidate = _repo(repo)
    tree = _git(repo, "show", "-s", "--format=%T", candidate)
    record = _result(
        candidate_commit=candidate, candidate_tree=tree, decision=model.NO_GO_DECISION,
    ).to_bytes()
    with pytest.raises(model.AuditError, match="not a go"):
        publication.build_evidence_commit(
            git_commands.GitRunner(repo), candidate=candidate,
            files={"docs/integration-audit.json": record}, message="blocked",
        )


def test_partial_publication_index_allocation_is_cleaned(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    candidate = _repo(repo)
    real_mkstemp = publication.tempfile.mkstemp
    real_chmod = Path.chmod

    def local_mkstemp(*, prefix: str):
        return real_mkstemp(prefix=prefix, dir=tmp_path)

    def fail_index_chmod(path: Path, mode: int) -> None:
        if path.name.startswith("md2pdf-audit-index-"):
            raise OSError("injected chmod failure")
        real_chmod(path, mode)

    monkeypatch.setattr(publication.tempfile, "mkstemp", local_mkstemp)
    monkeypatch.setattr(Path, "chmod", fail_index_chmod)
    with pytest.raises(model.AuditError, match="could not be allocated"):
        publication.build_evidence_commit(
            git_commands.GitRunner(repo), candidate=candidate,
            files=_evidence_files(repo, candidate), message="evidence",
        )
    assert not tuple(tmp_path.glob("md2pdf-audit-index-*"))


def test_publication_rejects_changed_preconditions_without_mutation(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    candidate = _repo(repo)
    runner = git_commands.GitRunner(repo)
    before = state.capture_snapshot(runner)
    commit, tree = publication.build_evidence_commit(
        runner, candidate=candidate, files=_evidence_files(repo, candidate), message="evidence",
    )

    (repo / "base.txt").write_text("editor change\n", encoding="utf-8")
    with pytest.raises(model.AuditError, match="pre-publication state changed"):
        publication.require_operator_publication(
            runner, before=before, candidate=candidate, commit=commit, tree=tree,
        )
    assert (repo / "base.txt").read_text(encoding="utf-8") == "editor change\n"
    assert _git(repo, "rev-parse", "HEAD") == candidate
    assert _git(repo, "show-ref", "--verify", state.ACTIVATION_REF, check=False) == ""


def test_sandbox_profile_denies_network_and_limits_writes(tmp_path: Path) -> None:
    source = tmp_path / "source"
    writable = tmp_path / "writable"
    source.mkdir()
    writable.mkdir()
    profile = isolate.sandbox_profile(source, writable, Path(sys.executable))
    assert "(deny network*)" in profile
    assert "(deny process-info-setcontrol)" in profile
    assert "(allow mach-lookup)" not in profile
    assert str(source) in profile and str(writable) in profile
    assert str(tmp_path / "outside") not in profile


def test_sandbox_runtime_allowlist_never_grants_a_home_ancestor(tmp_path: Path) -> None:
    fake_home = tmp_path / "home"
    launcher = fake_home / "python"
    fake_home.mkdir()
    shutil.copy2(Path(sys.executable).resolve(), launcher)
    launcher.chmod(0o700)
    version = f"python{sys.version_info.major}.{sys.version_info.minor}"
    (fake_home / "lib" / version / "site-packages").mkdir(parents=True)
    source = tmp_path / "source"
    writable = tmp_path / "writable"
    source.mkdir()
    writable.mkdir()
    profile = isolate.sandbox_profile(source, writable, launcher)
    assert f'(subpath "{fake_home}")' not in profile
    assert str(fake_home / ".ssh") not in profile


def test_sandbox_runtime_rejects_symlinked_dependency_root(tmp_path: Path) -> None:
    fake_home = tmp_path / "home"
    (fake_home / "site-packages").mkdir(parents=True)
    (fake_home / "credential").write_text("secret", encoding="utf-8")
    environment = tmp_path / "runtime"
    launcher = environment / "bin" / "python"
    launcher.parent.mkdir(parents=True)
    launcher.symlink_to(Path(sys.executable))
    library = environment / "lib"
    library.mkdir()
    (library / f"python{sys.version_info.major}.{sys.version_info.minor}").symlink_to(
        fake_home, target_is_directory=True,
    )
    source = tmp_path / "source"
    writable = tmp_path / "writable"
    source.mkdir()
    writable.mkdir()
    with pytest.raises(model.AuditError, match="runtime root is unsafe"):
        isolate.sandbox_profile(source, writable, launcher)


def test_sandbox_profile_close_failure_is_bounded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_close = sandbox.os.close

    def close_then_fail(descriptor: int) -> None:
        real_close(descriptor)
        raise OSError("injected close failure")

    monkeypatch.setattr(sandbox.os, "close", close_then_fail)
    with pytest.raises(model.AuditError, match="could not be finalized") as caught:
        sandbox._write_profile(tmp_path / "profile.sb", "(version 1)\n")
    assert caught.value.residue


def test_sandbox_profile_rejects_surrogate_escaped_paths() -> None:
    with pytest.raises(model.AuditError, match="not UTF-8"):
        sandbox._profile_literal(Path("bad-\udcff-path"))


@pytest.mark.parametrize("operation", ["extract", "chmod"])
def test_materialization_io_failure_is_fail_closed_and_cleans_workspace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, operation: str,
) -> None:
    class FakeGit:
        def bytes(self, *args: str, **kwargs: object) -> bytes:
            return _tar([("test_probe.py", b"def test_ok(): assert True\n", "file")])

    def fail(*_args: object, **_kwargs: object) -> None:
        raise OSError("injected materialization failure")

    monkeypatch.setattr(isolate.shutil, "which", lambda _name: "/usr/bin/sandbox-exec")
    monkeypatch.setattr(
        isolate, "safe_extract_archive" if operation == "extract" else "make_read_only", fail,
    )
    with pytest.raises(model.AuditError, match="materialization failed"):
        isolate.validate_candidate(
            FakeGit(), "a" * 40, tmp_path,
            (isolate.ValidationCommand("suite", Path(sys.executable), ("-V",)),),
        )
    assert not tuple(tmp_path.glob("md2pdf-audit-*"))


def test_partial_workspace_allocation_is_cleaned(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_chmod = Path.chmod
    injected = False

    def fail_once(path: Path, mode: int) -> None:
        nonlocal injected
        if path.name.startswith("md2pdf-audit-") and not injected:
            injected = True
            raise OSError("injected chmod failure")
        real_chmod(path, mode)

    monkeypatch.setattr(Path, "chmod", fail_once)
    with pytest.raises(model.AuditError, match="could not be allocated"):
        with isolate.private_workspace(tmp_path):
            pass
    assert not tuple(tmp_path.glob("md2pdf-audit-*"))


def test_unavailable_sandbox_fails_closed_and_cleans_workspace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeGit:
        def bytes(self, *args: str, **kwargs: object) -> bytes:
            assert args[:2] == ("archive", "--format=tar")
            return _tar([("test_probe.py", b"def test_ok(): assert True\n", "file")])

    def unavailable(*args: object, **kwargs: object) -> None:
        raise model.AuditError("command failed", "sandbox startup probe failed")

    monkeypatch.setattr(isolate.shutil, "which", lambda _name: "/usr/bin/sandbox-exec")
    monkeypatch.setattr(sandbox, "run_bounded_quiet", unavailable)
    with pytest.raises(model.AuditError, match="validation unavailable"):
        isolate.validate_candidate(
            FakeGit(), "a" * 40, tmp_path,
            [isolate.ValidationCommand("suite", Path(sys.executable), ("-m", "pytest"))],
        )
    assert not tuple(tmp_path.glob("md2pdf-audit-*"))


def test_validation_command_runs_startup_identity_and_candidate_in_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeGit:
        def bytes(self, *args: str, **kwargs: object) -> bytes:
            return _tar([("test_probe.py", b"def test_ok(): assert True\n", "file")])

    calls: list[tuple[tuple[str, ...], dict[str, object]]] = []

    def record(command: tuple[str, ...], **kwargs: object) -> None:
        calls.append((command, kwargs))

    monkeypatch.setattr(isolate.shutil, "which", lambda _name: "/usr/bin/sandbox-exec")
    monkeypatch.setattr(sandbox, "run_bounded_quiet", record)
    command = isolate.ValidationCommand(
        "suite", Path(sys.executable), ("-m", "pytest"),
        (sys.version_info.major, sys.version_info.minor),
    )
    assert isolate.validate_candidate(FakeGit(), "a" * 40, tmp_path, (command,)) == ("suite: pass",)
    assert len(calls) == 3
    assert calls[0][0][-1] == "/usr/bin/true"
    assert "sys.version_info" in calls[1][0][-1]
    assert calls[2][0][-3:] == (str(Path(sys.executable).resolve()), "-m", "pytest")
    for _argv, kwargs in calls:
        assert kwargs["resource_limits"] is True
        assert kwargs["session_wrapper"] is True
        assert Path(kwargs["cwd"]).name == "source"
        environment = kwargs["env"]
        assert environment["PYTHONNOUSERSITE"] == "1"
        assert environment["GIT_CONFIG_GLOBAL"] == "/dev/null"
    assert calls[0][1]["memory_limit_bytes"] == 512 * 1024 * 1024
    assert calls[1][1]["memory_limit_bytes"] == 512 * 1024 * 1024
    assert calls[2][1]["memory_limit_bytes"] == 4 * 1024 * 1024 * 1024
    assert calls[2][1]["timeout"] == model.SUITE_TIMEOUT


def test_validation_identity_failure_and_residue_stay_blocking(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeGit:
        def bytes(self, *args: str, **kwargs: object) -> bytes:
            return _tar([("test_probe.py", b"def test_ok(): assert True\n", "file")])

    monkeypatch.setattr(isolate.shutil, "which", lambda _name: "/usr/bin/sandbox-exec")
    count = 0

    def fail_identity(*_args: object, **_kwargs: object) -> None:
        nonlocal count
        count += 1
        if count == 2:
            raise model.AuditError("command failed", "wrong version")

    monkeypatch.setattr(sandbox, "run_bounded_quiet", fail_identity)
    command = isolate.ValidationCommand("suite", Path(sys.executable), (), (0, 0))
    with pytest.raises(model.AuditError, match="version is incorrect"):
        isolate.validate_candidate(FakeGit(), "a" * 40, tmp_path, (command,))

    count = 0

    def residue(*_args: object, **_kwargs: object) -> None:
        nonlocal count
        count += 1
        if count == 3:
            raise model.AuditError("cleanup failed", "uncertain", residue=True)

    monkeypatch.setattr(sandbox, "run_bounded_quiet", residue)
    with pytest.raises(model.AuditError) as caught:
        isolate.validate_candidate(FakeGit(), "a" * 40, tmp_path, (command,))
    assert caught.value.residue and "residue may remain" in str(caught.value)


def test_private_workspace_cleanup_never_follows_candidate_symlink(tmp_path: Path) -> None:
    outside = tmp_path / "outside.txt"
    outside.write_text("unchanged\n", encoding="utf-8")
    outside.chmod(0o640)
    with isolate.private_workspace(tmp_path) as workspace:
        writable = workspace / "writable"
        writable.mkdir()
        (writable / "attacker-link").symlink_to(outside)
    assert outside.read_text(encoding="utf-8") == "unchanged\n"
    assert outside.stat().st_mode & 0o777 == 0o640


@pytest.mark.parametrize("body_fails", [False, True])
def test_private_workspace_teardown_failure_is_residue_blocking(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, body_fails: bool,
) -> None:
    real_rmtree = workspace.shutil.rmtree

    def remove_then_fail(path: Path) -> None:
        real_rmtree(path)
        raise OSError("injected teardown failure")

    monkeypatch.setattr(workspace.shutil, "rmtree", remove_then_fail)
    primary = RuntimeError("primary failure")
    with pytest.raises(model.AuditError, match="residue may remain") as caught:
        with isolate.private_workspace(tmp_path):
            if body_fails:
                raise primary
    assert caught.value.residue
    if body_fails:
        assert caught.value.__cause__ is primary


def _sandbox_available() -> bool:
    if not Path("/usr/bin/sandbox-exec").is_file():
        return False
    try:
        completed = subprocess.run(
            ("/usr/bin/sandbox-exec", "-p", "(version 1)\n(allow default)\n", "/usr/bin/true"),
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return completed.returncode == 0


@pytest.mark.skipif(not _sandbox_available(), reason="sandbox-exec is unavailable on this host")
def test_sandbox_boundary_executes_hostile_probes(tmp_path: Path) -> None:
    source = tmp_path / "source"
    writable = tmp_path / "writable"
    outside = tmp_path / "outside"
    source.mkdir()
    writable.mkdir()
    outside.mkdir()
    secret = outside / "credential"
    secret.write_text("secret", encoding="utf-8")
    profile = isolate.sandbox_profile(source, writable, Path("/usr/bin/python3"))

    def probe(code: str) -> subprocess.CompletedProcess[bytes]:
        return subprocess.run(
            ("/usr/bin/sandbox-exec", "-p", profile, "/usr/bin/python3", "-c", code),
            cwd=source, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10,
        )

    assert probe(f"open({str(secret)!r}).read()").returncode != 0
    assert probe(f"open({str(outside / 'write')!r},'w').write('x')").returncode != 0
    assert probe("import socket;socket.create_connection(('127.0.0.1',9),.1)").returncode != 0
    assert probe("import os;os.setsid()").returncode != 0
    permitted = writable / "allowed"
    assert probe(f"open({str(permitted)!r},'w').write('ok')").returncode == 0
    assert permitted.read_text(encoding="utf-8") == "ok"


def test_downstream_requires_both_refs(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _repo(repo)
    with pytest.raises(model.AuditError):
        verifier.verify_downstream(repo)


def test_downstream_verification_holds_repository_lease(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _repo(repo)
    runner = git_commands.GitRunner(repo)
    with state.RepositoryLease(state.lease_path(runner)):
        with pytest.raises(model.AuditError, match="another integration gate"):
            verifier.verify_downstream(repo)


def test_cli_contracts_candidate_commands_decisions_and_residue(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    captured: dict[str, object] = {}

    def fake_audit(root, candidate, *, private_parent, validation_commands):
        captured.update(
            root=root, candidate=candidate, private_parent=private_parent,
            validation_commands=validation_commands,
        )
        return _result(decision=model.NO_GO_DECISION)

    monkeypatch.setattr(cli, "audit_candidate", fake_audit)
    arguments = [
        "audit", history.CANDIDATE_COMMIT, "--root", str(tmp_path),
        "--private-parent", str(tmp_path), "--python313", sys.executable,
        "--current-python", sys.executable,
    ]
    assert cli.main(arguments) == 1
    commands = captured["validation_commands"]
    assert [item.label for item in commands] == [
        "python-3.13-full-suite", "current-interpreter-full-suite",
        "visual-and-v0.1-compatibility",
    ]
    assert commands[0].expected_version == (3, 13)
    assert commands[1].expected_version == (sys.version_info.major, sys.version_info.minor)
    suite = ("-m", "pytest", "-q", "-p", "no:cacheprovider")
    assert commands == (
        isolate.ValidationCommand("python-3.13-full-suite", Path(sys.executable), suite, (3, 13)),
        isolate.ValidationCommand(
            "current-interpreter-full-suite", Path(sys.executable), suite,
            (sys.version_info.major, sys.version_info.minor),
        ),
        isolate.ValidationCommand(
            "visual-and-v0.1-compatibility", Path(sys.executable),
            (*suite, "tests/test_visual_acceptance.py", "tests/test_compatibility.py"),
            (3, 13),
        ),
    )
    assert model.load_result(capsys.readouterr().out.encode(), require_go=False).decision == model.NO_GO_DECISION

    monkeypatch.setattr(cli, "audit_candidate", lambda *_args, **_kwargs: _result())
    assert cli.main(arguments) == 0
    capsys.readouterr()
    assert cli.main([*arguments[:1], "0" * 40, *arguments[2:]]) == 2
    assert "fixed T-015 object" in capsys.readouterr().err

    def fail(*_args, **_kwargs):
        raise model.AuditError("cleanup failed", "uncertain", residue=True)

    monkeypatch.setattr(cli, "audit_candidate", fail)
    assert cli.main(arguments) == 1
    assert "residue may remain" in capsys.readouterr().err


@pytest.mark.parametrize("failure", [BrokenPipeError, OSError])
def test_cli_handles_output_io_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: type[OSError],
) -> None:
    class ClosedOutput:
        buffer: "ClosedOutput"

        def __init__(self) -> None:
            self.buffer = self

        def write(self, _value: object) -> int:
            raise failure("injected output failure")

    monkeypatch.setattr(cli, "audit_candidate", lambda *_args, **_kwargs: _result())
    monkeypatch.setattr(cli.sys, "stdout", ClosedOutput())
    assert cli.main([
        "audit", history.CANDIDATE_COMMIT, "--root", str(tmp_path),
        "--private-parent", str(tmp_path), "--python313", sys.executable,
        "--current-python", sys.executable,
    ]) == 1


def test_cli_handles_broken_error_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    class ClosedError:
        def write(self, _value: object) -> int:
            raise BrokenPipeError("injected error failure")

    monkeypatch.setattr(
        cli, "audit_candidate",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            model.AuditError("cleanup failed", "uncertain", residue=True)
        ),
    )
    monkeypatch.setattr(cli.sys, "stderr", ClosedError())
    assert cli.main([
        "audit", history.CANDIDATE_COMMIT, "--root", str(tmp_path),
        "--private-parent", str(tmp_path), "--python313", sys.executable,
        "--current-python", sys.executable,
    ]) == 1


@pytest.mark.parametrize("failure", [BrokenPipeError, OSError])
def test_cli_handles_delayed_output_flush_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: type[OSError],
) -> None:
    class DelayedFailure:
        buffer: "DelayedFailure"

        def __init__(self) -> None:
            self.buffer = self

        def write(self, value: bytes) -> int:
            return len(value)

        def flush(self) -> None:
            raise failure("injected flush failure")

    monkeypatch.setattr(cli, "audit_candidate", lambda *_args, **_kwargs: _result())
    monkeypatch.setattr(cli.sys, "stdout", DelayedFailure())
    assert cli.main([
        "audit", history.CANDIDATE_COMMIT, "--root", str(tmp_path),
        "--private-parent", str(tmp_path), "--python313", sys.executable,
        "--current-python", sys.executable,
    ]) == 1


def test_cli_retries_short_output_writes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    class PartialOutput:
        buffer: "PartialOutput"

        def __init__(self) -> None:
            self.buffer = self
            self.content = bytearray()

        def write(self, value: bytes) -> int:
            accepted = min(7, len(value))
            self.content.extend(value[:accepted])
            return accepted

        def flush(self) -> None:
            pass

    output = PartialOutput()
    monkeypatch.setattr(cli, "audit_candidate", lambda *_args, **_kwargs: _result())
    monkeypatch.setattr(cli.sys, "stdout", output)
    assert cli.main([
        "audit", history.CANDIDATE_COMMIT, "--root", str(tmp_path),
        "--private-parent", str(tmp_path), "--python313", sys.executable,
        "--current-python", sys.executable,
    ]) == 0
    assert model.load_result(bytes(output.content)) == _result()


@pytest.mark.parametrize("result", [None, 0, True])
def test_cli_rejects_output_without_forward_progress(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, result: int | bool | None,
) -> None:
    class StalledOutput:
        buffer: "StalledOutput"

        def __init__(self) -> None:
            self.buffer = self

        def write(self, _value: bytes) -> int | bool | None:
            return result

        def flush(self) -> None:
            raise AssertionError("stalled output must not be flushed")

    monkeypatch.setattr(cli, "audit_candidate", lambda *_args, **_kwargs: _result())
    monkeypatch.setattr(cli.sys, "stdout", StalledOutput())
    assert cli.main([
        "audit", history.CANDIDATE_COMMIT, "--root", str(tmp_path),
        "--private-parent", str(tmp_path), "--python313", sys.executable,
        "--current-python", sys.executable,
    ]) == 1


def test_cli_rejects_output_overreported_as_written(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    class OverreportedOutput:
        buffer: "OverreportedOutput"

        def __init__(self) -> None:
            self.buffer = self

        def write(self, value: bytes) -> int:
            return len(value) + 1

        def flush(self) -> None:
            raise AssertionError("invalid output must not be flushed")

    monkeypatch.setattr(cli, "audit_candidate", lambda *_args, **_kwargs: _result())
    monkeypatch.setattr(cli.sys, "stdout", OverreportedOutput())
    assert cli.main([
        "audit", history.CANDIDATE_COMMIT, "--root", str(tmp_path),
        "--private-parent", str(tmp_path), "--python313", sys.executable,
        "--current-python", sys.executable,
    ]) == 1


@pytest.mark.parametrize("stream_name", ["stdout", "stderr"])
@pytest.mark.parametrize("stream", [None, object()])
def test_cli_handles_unavailable_standard_streams(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    stream_name: str, stream: object | None,
) -> None:
    monkeypatch.setattr(cli.sys, stream_name, stream)
    if stream_name == "stdout":
        monkeypatch.setattr(cli, "audit_candidate", lambda *_args, **_kwargs: _result())
        expected = 1
    else:
        monkeypatch.setattr(
            cli, "audit_candidate",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(
                model.AuditError("cleanup failed", "uncertain", residue=True)
            ),
        )
        expected = 1
    assert cli.main([
        "audit", history.CANDIDATE_COMMIT, "--root", str(tmp_path),
        "--private-parent", str(tmp_path), "--python313", sys.executable,
        "--current-python", sys.executable,
    ]) == expected


@pytest.mark.parametrize("stream_name", ["stdout", "stderr"])
def test_cli_handles_closed_standard_streams(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stream_name: str,
) -> None:
    class ClosedStream:
        buffer: "ClosedStream"

        def __init__(self) -> None:
            self.buffer = self

        def write(self, _value: object) -> int:
            raise ValueError("I/O operation on closed file")

        def flush(self) -> None:
            raise AssertionError("closed output must not be flushed")

    monkeypatch.setattr(cli.sys, stream_name, ClosedStream())
    if stream_name == "stdout":
        monkeypatch.setattr(cli, "audit_candidate", lambda *_args, **_kwargs: _result())
    else:
        monkeypatch.setattr(
            cli, "audit_candidate",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(
                model.AuditError("cleanup failed", "uncertain", residue=True)
            ),
        )
    assert cli.main([
        "audit", history.CANDIDATE_COMMIT, "--root", str(tmp_path),
        "--private-parent", str(tmp_path), "--python313", sys.executable,
        "--current-python", sys.executable,
    ]) == 1


def test_residue_from_validation_is_never_downgraded_to_no_go(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    candidate = _repo(repo)
    monkeypatch.setattr(audit, "verify_history", lambda _git, _candidate: history.HistoryEvidence(
        candidate, _git.text("show", "-s", "--format=%T", candidate).strip(), (), "1" * 64,
    ))
    monkeypatch.setattr(audit, "verify_hygiene", lambda _git, _candidate: hygiene.HygieneEvidence(
        "2" * 64, "3" * 64, 0, (),
    ))
    monkeypatch.setattr(
        audit, "validate_candidate",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            model.AuditError("cleanup failed", "residue", residue=True)
        ),
    )
    with pytest.raises(model.AuditError) as caught:
        audit.audit_candidate(repo, candidate, private_parent=tmp_path, validation_commands=(
            isolate.ValidationCommand("suite", Path(sys.executable), ("-V",)),
        ))
    assert caught.value.residue


def test_nonresidue_validation_failure_becomes_no_go(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    candidate = _repo(repo)
    monkeypatch.setattr(audit, "verify_history", lambda git, _candidate: history.HistoryEvidence(
        candidate, git.text("show", "-s", "--format=%T", candidate).strip(), (), "1" * 64,
    ))
    monkeypatch.setattr(audit, "verify_hygiene", lambda _git, _candidate: hygiene.HygieneEvidence(
        "2" * 64, "3" * 64, 0, (),
    ))
    monkeypatch.setattr(
        audit, "validate_candidate",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            model.AuditError("validation unavailable", "host rejected sandbox")
        ),
    )
    runner = git_commands.GitRunner(repo)
    before = state.capture_snapshot(runner)
    result = audit.audit_candidate(
        repo, candidate, private_parent=tmp_path,
        validation_commands=(isolate.ValidationCommand("suite", Path(sys.executable), ("-V",)),),
    )
    assert result.decision == model.NO_GO_DECISION
    assert result.validations[-1] == "candidate-validation: fail-closed (validation unavailable)"
    assert state.capture_snapshot(runner) == before


def test_audit_and_operator_installed_evidence_verify_end_to_end(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    base = _repo(repo)
    original = _commit(repo, "original.txt", "original\n")
    candidate = _commit(repo, "candidate.txt", "candidate\n")
    for module in (history,):
        monkeypatch.setattr(module, "BASE_COMMIT", base)
        monkeypatch.setattr(module, "ORIGINAL_COMMITS", (original,))
        monkeypatch.setattr(module, "ORIGINAL_TIP", original)
        monkeypatch.setattr(module, "CANDIDATE_COMMIT", candidate)
        monkeypatch.setattr(module, "STABILIZATION_COUNT", 1)
    monkeypatch.setattr(hygiene, "BASE_COMMIT", base)
    monkeypatch.setattr(audit, "BASE_COMMIT", base)
    monkeypatch.setattr(audit, "ORIGINAL_COMMITS", (original,))
    monkeypatch.setattr(audit, "ORIGINAL_TIP", original)
    monkeypatch.setattr(verifier, "BASE_COMMIT", base)
    monkeypatch.setattr(verifier, "ORIGINAL_COMMITS", (original,))
    monkeypatch.setattr(verifier, "ORIGINAL_TIP", original)
    monkeypatch.setattr(audit, "validate_candidate", lambda *_args, **_kwargs: ("suite: pass",))

    result = audit.audit_candidate(
        repo, candidate, private_parent=tmp_path,
        validation_commands=(isolate.ValidationCommand("suite", Path(sys.executable), ("-V",)),),
    )
    runner = git_commands.GitRunner(repo)
    before = state.capture_snapshot(runner)
    commit, tree = publication.build_evidence_commit(
        runner, candidate=candidate,
        files={"docs/integration-audit.json": result.to_bytes()}, message="audit evidence",
    )
    with pytest.raises(model.AuditError, match="operator"):
        publication.require_operator_publication(
            runner, before=before, candidate=candidate, commit=commit, tree=tree,
        )
    # This deliberately models the separately coordinated operator transition;
    # publication code itself never writes into the live checkout.
    _git(repo, "reset", "--hard", commit)
    _git(repo, "update-ref", state.ACTIVATION_REF, commit)
    assert verifier.verify_downstream(repo) == commit

    real_load_result = verifier.load_result
    mutations = (
        replace(result, base_commit="a" * 40),
        replace(result, original_tip="a" * 40),
        replace(result, original_commits=()),
        replace(result, candidate_tree="a" * 40),
        replace(result, stabilization_commits=()),
        replace(result, history_sha256="9" * 64),
        replace(result, diff_sha256="9" * 64),
        replace(result, changed_paths_sha256="9" * 64),
        replace(result, changed_path_count=result.changed_path_count + 1),
    )
    for mutation in mutations:
        monkeypatch.setattr(verifier, "load_result", lambda _raw, value=mutation: value)
        with pytest.raises(model.AuditError, match="snapshot"):
            verifier.verify_downstream(repo)
    monkeypatch.setattr(verifier, "load_result", real_load_result)

    real_hygiene = verifier.verify_hygiene
    expected_hygiene = real_hygiene(git_commands.GitRunner(repo), candidate)
    monkeypatch.setattr(
        verifier, "verify_hygiene",
        lambda _git, _candidate: hygiene.HygieneEvidence(
            "9" * 64, expected_hygiene.changed_paths_sha256,
            expected_hygiene.changed_path_count, expected_hygiene.changed_paths,
        ),
    )
    with pytest.raises(model.AuditError, match="snapshot"):
        verifier.verify_downstream(repo)
    monkeypatch.setattr(verifier, "verify_hygiene", real_hygiene)

    real_capture = verifier.capture_snapshot
    captures = 0

    def move_main_before_final_snapshot(git):
        nonlocal captures
        captures += 1
        if captures == 3:
            _git(repo, "branch", "-f", "main", candidate)
        return real_capture(git)

    monkeypatch.setattr(verifier, "capture_snapshot", move_main_before_final_snapshot)
    with pytest.raises(model.AuditError, match="clean and coherent"):
        verifier.verify_downstream(repo)
    _git(repo, "branch", "-f", "main", base)

    captures = 0

    def move_activation_before_final_snapshot(git):
        nonlocal captures
        captures += 1
        if captures == 3:
            _git(repo, "update-ref", "-d", state.ACTIVATION_REF, commit)
        return real_capture(git)

    monkeypatch.setattr(verifier, "capture_snapshot", move_activation_before_final_snapshot)
    with pytest.raises(model.AuditError, match="clean and coherent"):
        verifier.verify_downstream(repo)
