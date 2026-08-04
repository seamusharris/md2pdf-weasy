"""Kernel resource policy and bounded process-group usage sampling."""

from __future__ import annotations

import os
import resource
import subprocess

from .model import AuditError


def apply_resource_limits(memory_limit_bytes: int | None, process_limit: int) -> None:
    limits = [(resource.RLIMIT_CPU, 1_500), (resource.RLIMIT_NOFILE, 256)]
    if memory_limit_bytes is not None and hasattr(resource, "RLIMIT_AS"):
        limits.append((resource.RLIMIT_AS, memory_limit_bytes))
    if hasattr(resource, "RLIMIT_NPROC"):
        limits.append((resource.RLIMIT_NPROC, process_limit))
    for key, value in limits:
        try:
            _soft, hard = resource.getrlimit(key)
            bounded = value if hard == resource.RLIM_INFINITY else min(value, hard)
            resource.setrlimit(key, (bounded, bounded))
        except (OSError, ValueError):
            os._exit(125)


def group_usage(group_id: int) -> tuple[int, int]:
    """Sample one process group; inherited RLIMITs remain the hard enforcement."""
    try:
        completed = subprocess.run(
            ("/bin/ps", "-o", "pid=,rss=", "-g", str(group_id)),
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            check=True, timeout=2,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise AuditError("resource monitor", "memory usage could not be measured") from exc
    if len(completed.stdout) > 4 * 1024 * 1024:
        raise AuditError("resource monitor", "memory usage inventory exceeded its bound")
    total_kib = 0
    seen: set[int] = set()
    try:
        for row in completed.stdout.splitlines():
            fields = row.split()
            if len(fields) != 2:
                raise ValueError("malformed process row")
            process_id, rss_kib = map(int, fields)
            if process_id <= 0 or rss_kib < 0 or process_id in seen:
                raise ValueError("invalid process row")
            seen.add(process_id)
            total_kib += rss_kib
            if len(seen) > 4_096:
                raise ValueError("process inventory exceeds its bound")
    except ValueError as exc:
        raise AuditError("resource monitor", "memory usage inventory was malformed") from exc
    return total_kib * 1024, len(seen)
