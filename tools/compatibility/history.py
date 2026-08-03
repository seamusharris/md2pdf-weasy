"""Attested local-tag export and safe extraction."""

from __future__ import annotations

import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import tarfile

from .io import write_all
from .model import (
    MAX_ARCHIVE_BYTES, MAX_ARCHIVE_ENTRIES, MAX_ARCHIVE_FILE_BYTES,
    CompatibilityError, TAG, TAG_COMMIT,
)
from .process import run_bounded


def resolve_tag(root: Path) -> str:
    stdout, _ = run_bounded(
        ("git", "rev-list", "-n", "1", TAG), cwd=root,
        category="tag", phase="resolve-tag", capture_limit=4096,
    )
    resolved = stdout.strip()
    if resolved != TAG_COMMIT:
        raise CompatibilityError(
            f"{TAG} resolves to {resolved or '<empty>'}, expected {TAG_COMMIT}",
            category="tag", phase="resolve-tag",
        )
    return resolved


def export_tag(root: Path, private_root: Path) -> Path:
    """Export the attested tag without changing or creating a worktree."""
    resolve_tag(root)
    private_root.mkdir(mode=0o700, parents=True, exist_ok=False)
    archive = private_root / "tag.tar"
    run_bounded(
        ("git", "archive", "--format=tar", f"--output={archive}", TAG_COMMIT),
        cwd=root, category="archive", phase="export-tag",
    )
    metadata = archive.stat()
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > MAX_ARCHIVE_BYTES:
        raise CompatibilityError("historical archive exceeds its safe bound", category="archive", phase="export-tag")
    package_parent = private_root / "legacy-parent"
    package_root = package_parent / "pdf"
    package_root.mkdir(mode=0o700, parents=True)
    safe_extract_tar(archive, package_root)
    archive.unlink()
    return package_parent


def _safe_member_path(name: str) -> PurePosixPath:
    path = PurePosixPath(name)
    if not name or path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise CompatibilityError("archive contains an unsafe path", category="archive", phase="extract-tag")
    return path


def _validated_member(member: tarfile.TarInfo, destination: Path, max_file_bytes: int) -> Path:
    relative = _safe_member_path(member.name)
    target = destination.joinpath(*relative.parts)
    if target != destination and destination not in target.resolve(strict=False).parents:
        raise CompatibilityError("archive path escapes extraction root", category="archive", phase="extract-tag")
    if not member.isdir() and (not member.isfile() or member.issym() or member.islnk() or member.isdev()):
        raise CompatibilityError("archive contains a link or special file", category="archive", phase="extract-tag")
    if member.size > max_file_bytes:
        raise CompatibilityError("archive member size limit exceeded", category="archive", phase="extract-tag")
    return target


def _copy_member_exact(bundle: tarfile.TarFile, member: tarfile.TarInfo, target: Path) -> None:
    source = bundle.extractfile(member)
    if source is None:
        raise CompatibilityError("archive member could not be read", category="archive", phase="extract-tag")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(target, flags, 0o600)
    except OSError as exc:
        source.close()
        raise CompatibilityError("archive target is missing or unsafe", category="archive", phase="extract-tag") from exc
    written = 0
    try:
        while True:
            chunk = source.read(min(1024 * 1024, member.size - written + 1))
            if not chunk:
                break
            written += len(chunk)
            if written > member.size:
                raise CompatibilityError("archive member grew while extracting", category="archive", phase="extract-tag")
            write_all(fd, chunk)
    finally:
        os.close(fd)
        source.close()
    if written != member.size:
        raise CompatibilityError("archive member was truncated", category="archive", phase="extract-tag")


def safe_extract_tar(
    archive: Path, destination: Path, *, max_entries: int = MAX_ARCHIVE_ENTRIES,
    max_file_bytes: int = MAX_ARCHIVE_FILE_BYTES,
    max_total_bytes: int = MAX_ARCHIVE_BYTES,
) -> None:
    """Extract only bounded regular files/directories beneath destination."""
    destination = destination.resolve()
    entries = 0
    total = 0
    with tarfile.open(archive, "r:") as bundle:
        for member in bundle:
            entries += 1
            if entries > max_entries:
                raise CompatibilityError("archive entry limit exceeded", category="archive", phase="extract-tag")
            target = _validated_member(member, destination, max_file_bytes)
            if member.isdir():
                target.mkdir(mode=0o700, parents=True, exist_ok=True)
                continue
            total += member.size
            if total > max_total_bytes:
                raise CompatibilityError("archive total size limit exceeded", category="archive", phase="extract-tag")
            target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            _copy_member_exact(bundle, member, target)


def remove_private_export(path: Path) -> None:
    """Remove one already-resolved, candidate-private export root."""
    if path.exists():
        shutil.rmtree(path)
