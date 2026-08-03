"""Lease and ephemeral workspace lifecycle for consumer-owned canaries."""

from __future__ import annotations

import fcntl
import os
from pathlib import Path
import shutil
import tempfile
from typing import Callable, TypeVar

from .model import CanaryError


T = TypeVar("T")


def _safe_parent(path: Path, label: str) -> Path:
    if not path.is_absolute():
        raise CanaryError("invalid request", f"{label} must be absolute", 2)
    try:
        if path.is_symlink() or not path.is_dir():
            raise CanaryError("invalid request", f"{label} must be a regular directory", 2)
        return path.resolve(strict=True)
    except OSError as exc:
        raise CanaryError("invalid request", f"{label} is unavailable", 2) from exc


class Lease:
    """A non-blocking POSIX lease; the stable lock file is never deleted."""

    def __init__(self, path: Path) -> None:
        if not path.is_absolute():
            raise CanaryError("invalid request", "lease path must be absolute", 2)
        self.path = path
        self._stream = None

    def __enter__(self) -> "Lease":
        _safe_parent(self.path.parent, "lease parent")
        descriptor: int | None = None
        try:
            if self.path.is_symlink():
                raise CanaryError("lease unavailable", "lease target is unsafe", 7)
            flags = os.O_CREAT | os.O_RDWR
            if hasattr(os, "O_NOFOLLOW"):
                flags |= os.O_NOFOLLOW
            descriptor = os.open(self.path, flags, 0o600)
            self._stream = os.fdopen(descriptor, "r+b", buffering=0)
            descriptor = None
            fcntl.flock(self._stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except CanaryError:
            raise
        except (OSError, BlockingIOError) as exc:
            if descriptor is not None:
                try:
                    os.close(descriptor)
                except OSError:
                    pass
            self._close()
            raise CanaryError("lease unavailable", "another canary may be active", 7) from exc
        return self

    def _close(self) -> None:
        if self._stream is not None:
            try:
                self._stream.close()
            finally:
                self._stream = None

    def __exit__(self, _type, _value, _traceback) -> None:
        if self._stream is not None:
            try:
                fcntl.flock(self._stream.fileno(), fcntl.LOCK_UN)
            finally:
                self._close()


def run_ephemeral(
    parent: Path,
    callback: Callable[[Path], T],
    *,
    remove_tree: Callable[[Path], None] = shutil.rmtree,
) -> T:
    """Run in a fresh tree and preserve primary errors if cleanup also fails."""

    safe_parent = _safe_parent(parent, "temporary parent")
    try:
        workspace = Path(tempfile.mkdtemp(prefix="md2pdf-canary-", dir=safe_parent))
    except OSError as exc:
        raise CanaryError("workspace unavailable", "temporary workspace could not be created", 8) from exc
    result: T | None = None
    primary: BaseException | None = None
    try:
        result = callback(workspace)
    except BaseException as exc:
        primary = exc
    cleanup_failed = False
    try:
        remove_tree(workspace)
    except OSError:
        cleanup_failed = True
    if primary is not None:
        if not isinstance(primary, Exception):
            if cleanup_failed:
                primary.add_note("downstream canary cleanup warning: ephemeral residue may remain")
            raise primary
        if isinstance(primary, CanaryError):
            raise CanaryError(
                primary.category,
                primary.detail,
                primary.exit_code,
                cleanup_warning=cleanup_failed or primary.cleanup_warning,
            ) from primary
        raise CanaryError(
            "canary failed",
            "consumer canary step failed",
            9,
            cleanup_warning=cleanup_failed,
        ) from primary
    if cleanup_failed:
        raise CanaryError(
            "cleanup failed",
            "ephemeral residue may remain",
            10,
            cleanup_warning=True,
        )
    return result  # type: ignore[return-value]
