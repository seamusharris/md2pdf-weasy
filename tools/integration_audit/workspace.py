"""Private validation-workspace allocation and cleanup."""

from __future__ import annotations

from contextlib import contextmanager
import os
from pathlib import Path
import shutil
import stat
import tempfile
from typing import Iterator

from .model import AuditError


def _safe_parent(path: Path) -> Path:
    if not path.is_absolute():
        raise AuditError("workspace unavailable", "private parent must be absolute")
    try:
        parent = path.resolve(strict=True)
    except OSError as exc:
        raise AuditError("workspace unavailable", "private parent is unavailable") from exc
    if not parent.is_dir() or parent.is_symlink():
        raise AuditError("workspace unavailable", "private parent is unsafe")
    return parent


@contextmanager
def private_workspace(parent: Path) -> Iterator[Path]:
    safe_parent = _safe_parent(parent)
    workspace: Path | None = None
    try:
        workspace = Path(tempfile.mkdtemp(prefix="md2pdf-audit-", dir=safe_parent))
        workspace.chmod(0o700)
    except OSError as exc:
        if workspace is not None:
            try:
                _remove_workspace(workspace)
            except AuditError as cleanup:
                raise cleanup from exc
        raise AuditError("workspace unavailable", "private workspace could not be allocated") from exc
    primary: BaseException | None = None
    try:
        yield workspace
    except BaseException as exc:
        primary = exc
        raise
    finally:
        try:
            _remove_workspace(workspace)
        except AuditError as cleanup:
            if primary is not None:
                if isinstance(primary, AuditError):
                    raise AuditError(primary.category, primary.detail, residue=True) from primary
                raise AuditError("cleanup failed", "private validation residue may remain", residue=True) from primary
            raise cleanup


def _remove_workspace(workspace: Path) -> None:
    cleanup_error: OSError | None = None
    try:
        for current, directories, _files in os.walk(workspace, topdown=False, followlinks=False):
            for name in directories:
                path = Path(current) / name
                try:
                    metadata = path.lstat()
                    if stat.S_ISLNK(metadata.st_mode):
                        path.unlink()
                    elif stat.S_ISDIR(metadata.st_mode):
                        path.chmod(0o700)
                except OSError:
                    pass
        workspace.chmod(0o700)
        shutil.rmtree(workspace)
    except OSError as exc:
        cleanup_error = exc
    if workspace.exists() or cleanup_error is not None:
        raise AuditError(
            "cleanup failed", "private validation residue may remain", residue=True,
        ) from cleanup_error
