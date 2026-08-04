"""Bounded, link-free materialization of candidate Git archives."""

from __future__ import annotations

import io
import os
from pathlib import Path, PurePosixPath
import stat
import tarfile

from .model import (
    AuditError, MAX_ARCHIVE_BYTES, MAX_ARCHIVE_DEPTH, MAX_ARCHIVE_ENTRIES,
    MAX_ARCHIVE_FILE_BYTES,
)
from .path_policy import require_relative_path


def _safe_relative(name: str) -> PurePosixPath:
    return require_relative_path(
        name, category="archive rejected", detail="candidate archive path is unsafe",
        max_depth=MAX_ARCHIVE_DEPTH,
    )


def _copy_exact(bundle: tarfile.TarFile, member: tarfile.TarInfo, target: Path) -> None:
    source = bundle.extractfile(member)
    if source is None:
        raise AuditError("archive rejected", "candidate archive entry is unreadable")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    descriptor: int | None = None
    primary: BaseException | None = None
    try:
        descriptor = os.open(target, flags, 0o600)
        written = 0
        while written < member.size:
            chunk = source.read(min(1024 * 1024, member.size - written))
            if not chunk:
                break
            written += len(chunk)
            view = memoryview(chunk)
            while view:
                count = os.write(descriptor, view)
                view = view[count:]
        if written != member.size or source.read(1):
            raise AuditError("archive rejected", "candidate archive entry size changed")
    except BaseException as exc:
        primary = exc
    finally:
        cleanup_error: OSError | None = None
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError as exc:
                cleanup_error = exc
        try:
            source.close()
        except OSError as exc:
            cleanup_error = cleanup_error or exc
        if cleanup_error is not None:
            raise AuditError(
                "cleanup failed", "candidate archive entry may be incomplete", residue=True,
            ) from (primary or cleanup_error)
    if primary is not None:
        if isinstance(primary, AuditError):
            raise primary
        if isinstance(primary, OSError):
            raise AuditError("archive rejected", "candidate archive target is unsafe") from primary
        raise primary


def safe_extract_archive(raw: bytes, destination: Path) -> None:
    """Extract bounded regular files and directories from an in-memory tar."""
    if len(raw) > MAX_ARCHIVE_BYTES:
        raise AuditError("archive rejected", "candidate archive exceeds its size limit")
    root = destination.resolve(strict=True)
    entries = 0
    total = 0
    root_names: set[str] = set()
    try:
        bundle_context = tarfile.open(fileobj=io.BytesIO(raw), mode="r:")
    except tarfile.TarError as exc:
        raise AuditError("archive rejected", "candidate archive is malformed") from exc
    with bundle_context as bundle:
        for member in bundle:
            entries += 1
            if entries > MAX_ARCHIVE_ENTRIES:
                raise AuditError("archive rejected", "candidate archive has too many entries")
            relative = _safe_relative(member.name)
            root_names.add(relative.parts[0])
            target = root.joinpath(*relative.parts)
            if target != root and root not in target.resolve(strict=False).parents:
                raise AuditError("archive rejected", "candidate archive escapes its root")
            if member.isdir():
                target.mkdir(mode=0o700, parents=True, exist_ok=True)
                continue
            if not member.isfile() or member.issym() or member.islnk() or member.isdev():
                raise AuditError("archive rejected", "candidate archive contains a link or special entry")
            if member.size < 0 or member.size > MAX_ARCHIVE_FILE_BYTES:
                raise AuditError("archive rejected", "candidate archive member exceeds its size limit")
            total += member.size
            if total > MAX_ARCHIVE_BYTES:
                raise AuditError("archive rejected", "candidate archive expands beyond its size limit")
            target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            _copy_exact(bundle, member, target)
    if len(root_names) > 2_000:
        raise AuditError("archive rejected", "candidate archive has too many root entries")


def make_read_only(root: Path) -> None:
    for current, directories, files in os.walk(root, topdown=False, followlinks=False):
        for name in files:
            path = Path(current) / name
            mode = path.lstat().st_mode
            if not stat.S_ISREG(mode):
                raise AuditError("archive rejected", "materialized candidate contains a special entry")
            path.chmod(0o400)
        for name in directories:
            path = Path(current) / name
            if path.is_symlink():
                raise AuditError("archive rejected", "materialized candidate contains a link")
            path.chmod(0o500)
    root.chmod(0o500)
