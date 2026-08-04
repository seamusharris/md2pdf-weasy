"""Platform-specific process-group inventory and teardown."""

from __future__ import annotations

import ctypes
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

from .model import AuditError


def signal_group(process: subprocess.Popen[bytes], sig: signal.Signals) -> None:
    try:
        os.killpg(process.pid, sig)
    except ProcessLookupError:
        pass
    except PermissionError as exc:
        if leader_exited_unreaped(process):
            return
        raise AuditError("cleanup failed", "could not signal command process group", residue=True) from exc


def leader_exited_unreaped(process: subprocess.Popen[bytes]) -> bool:
    """Observe the child without releasing its PID for reuse."""
    if not all(hasattr(os, name) for name in ("waitid", "P_PID", "WEXITED", "WNOHANG", "WNOWAIT")):
        raise AuditError(
            "cleanup failed", "safe process-group observation is unavailable", residue=True,
        )
    try:
        result = os.waitid(os.P_PID, process.pid, os.WEXITED | os.WNOHANG | os.WNOWAIT)
    except ChildProcessError as exc:
        raise AuditError(
            "cleanup failed", "command leader was reaped before group cleanup", residue=True,
        ) from exc
    return result is not None


def group_members(group_id: int) -> set[int]:
    """Return bounded process-group membership without a full-table subprocess."""
    if sys.platform == "darwin":
        return _darwin_group_members(group_id)
    proc = Path("/proc")
    if proc.is_dir():
        return _linux_group_members(proc, group_id)
    raise AuditError(
        "cleanup failed", "safe process-group inventory is unavailable", residue=True,
    )


def _darwin_group_members(group_id: int) -> set[int]:
    try:
        library = ctypes.CDLL("/usr/lib/libproc.dylib", use_errno=True)
        list_pids = library.proc_listpids
        list_pids.argtypes = (
            ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p, ctypes.c_int,
        )
        list_pids.restype = ctypes.c_int
        required = list_pids(2, group_id, None, 0)  # PROC_PGRP_ONLY
        if required < 0 or required > 4 * 1024 * 1024:
            raise OSError(ctypes.get_errno(), "process inventory is unavailable")
        integer_bytes = ctypes.sizeof(ctypes.c_int)
        capacity = max(integer_bytes, required + 16 * integer_bytes)
        while capacity <= 4 * 1024 * 1024:
            slots = (capacity + integer_bytes - 1) // integer_bytes
            buffer = (ctypes.c_int * slots)()
            buffer_bytes = ctypes.sizeof(buffer)
            used = list_pids(2, group_id, buffer, buffer_bytes)
            if used < 0 or used > buffer_bytes:
                raise OSError(ctypes.get_errno(), "process inventory is unavailable")
            if used < buffer_bytes:
                count = used // integer_bytes
                return {pid for pid in buffer[:count] if pid > 0}
            capacity = buffer_bytes * 2
        raise OSError("process inventory exceeds its bound")
    except (AttributeError, OSError) as exc:
        raise AuditError(
            "cleanup failed", "command process group could not be inspected", residue=True,
        ) from exc


def _linux_group_members(proc: Path, group_id: int) -> set[int]:
    members: set[int] = set()
    try:
        for entry in proc.iterdir():
            if not entry.name.isdigit():
                continue
            try:
                raw = (entry / "stat").read_text(encoding="ascii")
            except FileNotFoundError:
                continue
            fields = raw[raw.rfind(")") + 2:].split()
            if len(fields) > 2 and int(fields[2]) == group_id:
                members.add(int(entry.name))
            if len(members) > 4_096:
                raise OSError("process group exceeds inventory bound")
    except (OSError, ValueError) as exc:
        raise AuditError(
            "cleanup failed", "command process group could not be inspected", residue=True,
        ) from exc
    return members


def terminate_and_reap(process: subprocess.Popen[bytes]) -> int:
    """Repeatedly kill the anchored group, then release its leader PID once."""
    signal_group(process, signal.SIGTERM)
    grace = time.monotonic() + 0.5
    while not leader_exited_unreaped(process) and time.monotonic() < grace:
        time.sleep(0.02)
    deadline = time.monotonic() + 2.0
    remaining: set[int] = {process.pid}
    while remaining and time.monotonic() < deadline:
        # The unreaped leader anchors the PGID across every repeated signal.
        signal_group(process, signal.SIGKILL)
        time.sleep(0.02)
        remaining = group_members(process.pid) - {process.pid}
    if not leader_exited_unreaped(process):
        raise AuditError("cleanup failed", "command leader could not be reaped", residue=True)
    if remaining:
        raise AuditError(
            "cleanup failed", "command descendants could not be reaped", residue=True,
        )
    return process.wait()
