"""Generic bounded subprocess execution for the integration audit."""

from __future__ import annotations

import os
from pathlib import Path
import selectors
import subprocess
import time
from typing import Mapping, Sequence

from .lifecycle import leader_exited_unreaped, terminate_and_reap
from .model import AuditError, COMMAND_TIMEOUT, MAX_CAPTURE_BYTES
from .resources import apply_resource_limits, group_usage


_PROTECTED_ENVIRONMENT = frozenset({
    "PATH", "LANG", "LC_ALL", "GIT_CONFIG_NOSYSTEM", "GIT_CONFIG_GLOBAL",
    "GIT_TERMINAL_PROMPT", "GIT_OPTIONAL_LOCKS", "GIT_NO_REPLACE_OBJECTS",
})


def clean_environment(extra: Mapping[str, str] | None = None) -> dict[str, str]:
    """Return the small credential-free environment used for trusted commands."""
    environment = {
        "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_OPTIONAL_LOCKS": "0",
        "GIT_NO_REPLACE_OBJECTS": "1",
    }
    if extra:
        if _PROTECTED_ENVIRONMENT.intersection(extra):
            raise AuditError("invalid request", "protected command environment cannot be overridden")
        environment.update(extra)
    return environment


def _validate_command(command: Sequence[str]) -> tuple[str, ...]:
    if not command or any(not isinstance(part, str) or not part or "\x00" in part for part in command):
        raise AuditError("invalid request", "command argument vector is invalid")
    return tuple(command)


def _handle_ready_stream(
    selector: selectors.BaseSelector, key: selectors.SelectorKey,
    pending_input: memoryview, chunks: dict[str, bytearray], capture_limit: int,
    label: str,
) -> memoryview:
    if key.data == "stdin":
        try:
            written = os.write(key.fileobj.fileno(), pending_input[:65_536])
            pending_input = pending_input[written:]
        except BrokenPipeError:
            pending_input = pending_input[len(pending_input):]
        except BlockingIOError:
            return pending_input
        if not pending_input:
            selector.unregister(key.fileobj)
            key.fileobj.close()
        return pending_input
    try:
        data = os.read(key.fileobj.fileno(), 65_536)
    except BlockingIOError:
        return pending_input
    if not data:
        selector.unregister(key.fileobj)
        return pending_input
    chunks[key.data].extend(data)
    if len(chunks["stdout"]) + len(chunks["stderr"]) > capture_limit:
        raise AuditError("command output", f"{label} exceeded its output limit")
    return pending_input


def _exchange_bounded(
    process: subprocess.Popen[bytes], *, input_bytes: bytes | None, started: float,
    timeout: float, capture_limit: int, label: str,
    memory_limit_bytes: int | None, process_limit: int,
) -> dict[str, bytearray]:
    chunks: dict[str, bytearray] = {"stdout": bytearray(), "stderr": bytearray()}
    next_memory_check = started
    with selectors.DefaultSelector() as selector:
        assert process.stdout is not None and process.stderr is not None
        selector.register(process.stdout, selectors.EVENT_READ, "stdout")
        selector.register(process.stderr, selectors.EVENT_READ, "stderr")
        pending_input = memoryview(input_bytes or b"")
        if process.stdin is not None:
            os.set_blocking(process.stdin.fileno(), False)
            selector.register(process.stdin, selectors.EVENT_WRITE, "stdin")
        while selector.get_map():
            remaining = timeout - (time.monotonic() - started)
            if remaining <= 0:
                raise AuditError("command timeout", f"{label} exceeded its deadline")
            if memory_limit_bytes is not None and time.monotonic() >= next_memory_check:
                rss_bytes, process_count = group_usage(process.pid)
                if rss_bytes > memory_limit_bytes:
                    raise AuditError("resource limit", f"{label} exceeded its memory limit")
                if process_count > process_limit:
                    raise AuditError("resource limit", f"{label} exceeded its process limit")
                next_memory_check = time.monotonic() + 1
            for key, _ in selector.select(min(remaining, 0.25)):
                pending_input = _handle_ready_stream(
                    selector, key, pending_input, chunks, capture_limit, label,
                )
    while not leader_exited_unreaped(process):
        if time.monotonic() - started >= timeout:
            raise AuditError("command timeout", f"{label} exceeded its deadline")
        time.sleep(0.01)
    return chunks


def run_bounded_bytes(
    command: Sequence[str], *, cwd: Path, env: Mapping[str, str] | None = None,
    input_bytes: bytes | None = None, timeout: float = COMMAND_TIMEOUT,
    capture_limit: int = MAX_CAPTURE_BYTES, label: str = "command",
    resource_limits: bool = False, memory_limit_bytes: int | None = None,
    process_limit: int = 128,
    accepted_returncodes: frozenset[int] = frozenset({0}),
) -> tuple[bytes, bytes]:
    """Run a fixed argv with hard per-process limits and sampled group bounds."""
    argv = _validate_command(command)
    if not cwd.is_absolute():
        raise AuditError("invalid request", "command working directory must be absolute")
    try:
        process = subprocess.Popen(
            argv, cwd=cwd, env=dict(env) if env is not None else clean_environment(),
            stdin=subprocess.PIPE if input_bytes is not None else subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True,
            preexec_fn=(
                (lambda: apply_resource_limits(memory_limit_bytes, process_limit))
                if resource_limits else None
            ),
        )
    except OSError as exc:
        raise AuditError("command unavailable", f"{label} could not start") from exc
    started = time.monotonic()
    chunks: dict[str, bytearray] = {"stdout": bytearray(), "stderr": bytearray()}
    primary: BaseException | None = None
    try:
        chunks = _exchange_bounded(
            process, input_bytes=input_bytes, started=started, timeout=timeout,
            capture_limit=capture_limit, label=label,
            memory_limit_bytes=memory_limit_bytes, process_limit=process_limit,
        )
    except BaseException as exc:
        primary = exc
    try:
        return_code = terminate_and_reap(process)
    except AuditError as cleanup:
        raise cleanup from primary
    if primary is not None:
        if isinstance(primary, OSError):
            raise AuditError("command I/O", f"{label} communication failed") from primary
        raise primary
    if return_code not in accepted_returncodes:
        raise AuditError("command failed", f"{label} exited with status {return_code}")
    return bytes(chunks["stdout"]), bytes(chunks["stderr"])


def run_bounded(
    command: Sequence[str], *, cwd: Path, env: Mapping[str, str] | None = None,
    input_bytes: bytes | None = None, timeout: float = COMMAND_TIMEOUT,
    capture_limit: int = MAX_CAPTURE_BYTES, label: str = "command",
    resource_limits: bool = False, memory_limit_bytes: int | None = None,
    process_limit: int = 128,
    accepted_returncodes: frozenset[int] = frozenset({0}),
) -> tuple[str, str]:
    stdout, stderr = run_bounded_bytes(
        command, cwd=cwd, env=env, input_bytes=input_bytes, timeout=timeout,
        capture_limit=capture_limit, label=label, resource_limits=resource_limits,
        memory_limit_bytes=memory_limit_bytes, process_limit=process_limit,
        accepted_returncodes=accepted_returncodes,
    )
    return stdout.decode("utf-8", "strict"), stderr.decode("utf-8", "replace")


def run_bounded_quiet(
    command: Sequence[str], *, cwd: Path, env: Mapping[str, str] | None = None,
    timeout: float = COMMAND_TIMEOUT, label: str = "command",
    resource_limits: bool = False, memory_limit_bytes: int | None = None,
    process_limit: int = 128,
    session_wrapper: bool = False,
) -> None:
    """Run with all output discarded, retaining bounded lifecycle and resources."""
    argv = _validate_command(command)
    spawn_argv = argv
    if session_wrapper:
        wrapper = '"$@"; audit_status=$?; exit "$audit_status"'
        spawn_argv = ("/bin/bash", "--noprofile", "--norc", "-c", wrapper, "audit-wrapper", *argv)
    try:
        child = subprocess.Popen(
            spawn_argv, cwd=cwd, env=dict(env) if env is not None else clean_environment(),
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            start_new_session=True,
            preexec_fn=(
                (lambda: apply_resource_limits(memory_limit_bytes, process_limit))
                if resource_limits else None
            ),
        )
    except OSError as exc:
        raise AuditError("command unavailable", f"{label} could not start") from exc
    started = time.monotonic()
    next_memory_check = started
    primary: BaseException | None = None
    try:
        while not leader_exited_unreaped(child):
            if time.monotonic() - started >= timeout:
                raise AuditError("command timeout", f"{label} exceeded its deadline")
            if memory_limit_bytes is not None and time.monotonic() >= next_memory_check:
                rss_bytes, process_count = group_usage(child.pid)
                if rss_bytes > memory_limit_bytes:
                    raise AuditError("resource limit", f"{label} exceeded its memory limit")
                if process_count > process_limit:
                    raise AuditError("resource limit", f"{label} exceeded its process limit")
                next_memory_check = time.monotonic() + 1
            time.sleep(0.1)
    except BaseException as exc:
        primary = exc
    try:
        return_code = terminate_and_reap(child)
    except AuditError as cleanup:
        raise cleanup from primary
    if primary is not None:
        raise primary
    if return_code:
        raise AuditError("command failed", f"{label} exited with status {return_code}")
