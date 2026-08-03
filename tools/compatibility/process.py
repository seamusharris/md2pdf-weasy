"""Bounded process execution for the compatibility harness."""

from __future__ import annotations

import os
from pathlib import Path
import selectors
import signal
import subprocess
import time
from typing import Mapping, Sequence

from .model import COMMAND_TIMEOUT, CompatibilityError, MAX_CAPTURE_BYTES


def _terminate_process_group(process: subprocess.Popen[bytes]) -> None:
    group_id = process.pid
    try:
        os.killpg(group_id, signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        pass
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        try:
            os.killpg(group_id, 0)
        except (ProcessLookupError, PermissionError):
            break
        time.sleep(0.02)
    else:
        try:
            os.killpg(group_id, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
    if process.poll() is None:
        process.wait()


def _capture_bounded(
    process: subprocess.Popen[bytes], selector: selectors.BaseSelector, *,
    started: float, timeout: float, capture_limit: int, category: str,
    phase: str, case: str | None,
) -> dict[str, bytearray]:
    chunks: dict[str, bytearray] = {"stdout": bytearray(), "stderr": bytearray()}
    while selector.get_map():
        remaining = timeout - (time.monotonic() - started)
        if remaining <= 0:
            raise CompatibilityError(
                f"command timed out after {timeout:g}s", category="timeout",
                phase=phase, case=case,
            )
        for key, _ in selector.select(min(remaining, 0.25)):
            data = os.read(key.fileobj.fileno(), 65_536)
            if not data:
                selector.unregister(key.fileobj)
                continue
            chunks[key.data].extend(data)
            if sum(map(len, chunks.values())) > capture_limit:
                raise CompatibilityError(
                    f"command output exceeds {capture_limit} bytes",
                    category=category, phase=phase, case=case,
                )
    return chunks


def run_bounded(
    command: Sequence[str], *, cwd: Path, env: Mapping[str, str] | None = None,
    timeout: float = COMMAND_TIMEOUT, capture_limit: int = MAX_CAPTURE_BYTES,
    category: str = "render", phase: str = "command", case: str | None = None,
) -> tuple[str, str]:
    """Run a fixed argv without a shell and cap combined captured output."""
    if not command or any(not isinstance(part, str) or "\x00" in part for part in command):
        raise CompatibilityError("invalid command", category=category, phase=phase, case=case)
    try:
        process = subprocess.Popen(
            list(command), cwd=cwd, env=dict(env) if env is not None else None,
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            start_new_session=True,
        )
    except OSError as exc:
        raise CompatibilityError(
            "could not start command", category=category, phase=phase, case=case,
        ) from exc
    selector: selectors.BaseSelector | None = None
    started = time.monotonic()
    try:
        selector = selectors.DefaultSelector()
        assert process.stdout is not None and process.stderr is not None
        selector.register(process.stdout, selectors.EVENT_READ, "stdout")
        selector.register(process.stderr, selectors.EVENT_READ, "stderr")
        chunks = _capture_bounded(
            process, selector, started=started, timeout=timeout,
            capture_limit=capture_limit, category=category, phase=phase,
            case=case,
        )
        try:
            return_code = process.wait(timeout=max(0.1, timeout - (time.monotonic() - started)))
        except subprocess.TimeoutExpired as exc:
            raise CompatibilityError(
                f"command timed out after {timeout:g}s", category="timeout",
                phase=phase, case=case,
            ) from exc
        stdout = bytes(chunks["stdout"]).decode("utf-8", "replace")
        stderr = bytes(chunks["stderr"]).decode("utf-8", "replace")
        if return_code:
            diagnostic = (stderr or stdout).strip()[-16_384:]
            raise CompatibilityError(
                f"command failed ({return_code}): {diagnostic}",
                category=category, phase=phase, case=case,
            )
        return stdout, stderr
    finally:
        if selector is not None:
            selector.close()
        _terminate_process_group(process)


def probe_version(command: Sequence[str], *, cwd: Path) -> str:
    stdout, stderr = run_bounded(
        command, cwd=cwd, timeout=15, capture_limit=64 * 1024,
        category="prerequisite", phase="probe",
    )
    lines = (stdout or stderr).strip().splitlines()
    if not lines:
        raise CompatibilityError(
            "version command returned no output", category="prerequisite", phase="probe",
        )
    return lines[0][:500]
