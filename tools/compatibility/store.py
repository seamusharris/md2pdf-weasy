"""Concurrent candidate allocation, leases, publication, and retention.

This is intentionally independent from ``tools.visual_acceptance``: T-010
attests the exact active T-009 implementation, so sharing its internals would
invalidate the evidence chain this workflow is required to preserve.
"""

from __future__ import annotations

import contextlib
from datetime import datetime, timezone
import fcntl
import os
from pathlib import Path
import re
import shutil
import stat
import uuid
from typing import Any, Iterator

from .io import write_all
from .model import (
    MAX_CANDIDATE_BYTES, MAX_CANDIDATE_DEPTH, MAX_CANDIDATE_ENTRIES,
    MAX_CANDIDATE_ROOT_ENTRIES, CompatibilityError, LeaseBusy, canonical_bytes,
)


ROOT = Path(__file__).resolve().parents[2]
CANDIDATE_ROOT = ROOT / "output" / "pdf" / "compatibility-v0.1" / "candidates"
PENDING_MARKER = "pending.json"
_NAME = re.compile(r"^\d{8}T\d{6}Z-[0-9a-f]{32}$")
_QUARANTINE = re.compile(r"^\.prune-[0-9a-f]{32}$")


_DIRECTORY_FLAGS = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)


@contextlib.contextmanager
def _root_fd(root: Path) -> Iterator[tuple[Path, int]]:
    """Open a stable candidate root, creating default components no-follow."""
    root = root.absolute()
    if root == CANDIDATE_ROOT:
        try:
            parts = root.relative_to(ROOT).parts
        except ValueError as exc:
            raise CompatibilityError("candidate root escapes repository", category="verify", phase="candidate-root") from exc
        fd = os.open(ROOT, _DIRECTORY_FLAGS)
        try:
            for part in parts:
                try:
                    os.mkdir(part, mode=0o700, dir_fd=fd)
                except FileExistsError:
                    pass
                child = os.open(part, _DIRECTORY_FLAGS, dir_fd=fd)
                os.close(fd)
                fd = child
        except OSError as exc:
            os.close(fd)
            raise CompatibilityError("candidate root has a symlinked or unsafe ancestor", category="verify", phase="candidate-root") from exc
        try:
            yield root, fd
        finally:
            os.close(fd)
        return

    # Tests and internal callers may supply an explicit temporary root. The
    # caller owns its anchor; still reject a symlink at the directory itself.
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        fd = os.open(root, _DIRECTORY_FLAGS)
    except OSError as exc:
        raise CompatibilityError("candidate root is unsafe", category="verify", phase="candidate-root") from exc
    try:
        yield root, fd
    finally:
        os.close(fd)


def _ensure_root(root: Path = CANDIDATE_ROOT) -> Path:
    with _root_fd(root) as (root, fd):
        if len(os.listdir(fd)) > MAX_CANDIDATE_ROOT_ENTRIES:
            raise CompatibilityError("candidate root entry limit exceeded", category="verify", phase="candidate-root")
        return root


@contextlib.contextmanager
def _registry_lock(
    root: Path, *, reserve_entries: int = 0, enforce_capacity: bool = True,
) -> Iterator[int]:
    with _root_fd(root) as (_, root_fd):
        entries = os.listdir(root_fd)
        if enforce_capacity and ".lock" not in entries and len(entries) >= MAX_CANDIDATE_ROOT_ENTRIES:
            raise CompatibilityError("candidate root has insufficient capacity", category="verify", phase="allocate")
        for attempt in range(3):
            try:
                lock_fd = os.open(".lock", os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600, dir_fd=root_fd)
                break
            except FileNotFoundError:
                # Darwin can transiently return ENOENT when several threads
                # race the first O_CREAT lookup for the same dir-relative file.
                if attempt == 2:
                    raise
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX)
            if (enforce_capacity
                    and len(os.listdir(root_fd)) + reserve_entries > MAX_CANDIDATE_ROOT_ENTRIES):
                raise CompatibilityError(
                    "candidate root has insufficient capacity", category="verify", phase="allocate",
                )
            yield root_fd
        finally:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            os.close(lock_fd)


def allocate_candidate(root: Path = CANDIDATE_ROOT) -> Path:
    root = _ensure_root(root)
    with _registry_lock(root, reserve_entries=1) as root_fd:
        for _ in range(10):
            name = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ-") + uuid.uuid4().hex
            try:
                os.mkdir(name, mode=0o700, dir_fd=root_fd)
                return root / name
            except FileExistsError:
                continue
    raise CompatibilityError("could not allocate a unique candidate", phase="allocate")


def discard_allocated_candidate(path: Path, root: Path = CANDIDATE_ROOT) -> None:
    """Remove a fresh candidate when lease setup failed before generation."""
    path = path.absolute()
    if path.parent != root.absolute() or not _NAME.fullmatch(path.name):
        raise CompatibilityError("invalid rollback candidate", category="verify", phase="allocate")
    with _registry_lock(root, enforce_capacity=False) as root_fd:
        candidate_fd = os.open(path.name, _DIRECTORY_FLAGS, dir_fd=root_fd)
        try:
            if set(os.listdir(candidate_fd)) - {".lease"}:
                raise CompatibilityError("rollback candidate is not empty", category="verify", phase="allocate")
            current = os.stat(path.name, dir_fd=root_fd, follow_symlinks=False)
            opened = os.fstat(candidate_fd)
            if (current.st_dev, current.st_ino) != (opened.st_dev, opened.st_ino):
                raise CompatibilityError("rollback candidate identity changed", category="verify", phase="allocate")
        finally:
            os.close(candidate_fd)
        quarantine = f".prune-{uuid.uuid4().hex}"
        os.rename(path.name, quarantine, src_dir_fd=root_fd, dst_dir_fd=root_fd)
        shutil.rmtree(quarantine, dir_fd=root_fd)


def validate_candidate_path(path: Path, root: Path = CANDIDATE_ROOT) -> Path:
    root = _ensure_root(root)
    path = path.absolute()
    if not _NAME.fullmatch(path.name):
        raise CompatibilityError("invalid candidate name", category="verify", phase="candidate-path")
    if path.parent != root:
        raise CompatibilityError("candidate escapes its root", category="verify", phase="candidate-path")
    try:
        with _root_fd(root) as (_, root_fd):
            candidate_fd = os.open(path.name, _DIRECTORY_FLAGS, dir_fd=root_fd)
            os.close(candidate_fd)
    except OSError as exc:
        raise CompatibilityError("candidate is missing or unsafe", category="verify", phase="candidate-path") from exc
    return path


@contextlib.contextmanager
def candidate_lease(
    path: Path, *, blocking: bool = True, root: Path = CANDIDATE_ROOT,
    yield_fd: bool = False,
) -> Iterator[Any]:
    path = validate_candidate_path(path, root)
    with _root_fd(root) as (_, root_fd):
        candidate_fd = os.open(path.name, _DIRECTORY_FLAGS, dir_fd=root_fd)
        try:
            fd = os.open(".lease", os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600, dir_fd=candidate_fd)
        except BaseException:
            os.close(candidate_fd)
            raise
        operation = fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB)
        try:
            try:
                fcntl.flock(fd, operation)
            except BlockingIOError as exc:
                raise LeaseBusy("candidate is live", category="verify", phase="lease") from exc
            yield (path, candidate_fd) if yield_fd else path
        finally:
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
            finally:
                os.close(fd)
                os.close(candidate_fd)


def atomic_json(path: Path, value: Any) -> None:
    data = canonical_bytes(value)
    temp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(temp, flags, 0o600)
    try:
        write_all(fd, data)
        os.fsync(fd)
        os.close(fd)
        fd = -1
        os.replace(temp, path)
    except BaseException:
        if fd >= 0:
            os.close(fd)
        try:
            temp.unlink()
        except FileNotFoundError:
            pass
        raise


def tree_stats(
    path: Path, *, max_entries: int = MAX_CANDIDATE_ENTRIES,
    max_bytes: int = MAX_CANDIDATE_BYTES, max_depth: int = MAX_CANDIDATE_DEPTH,
) -> tuple[int, int]:
    root = path.resolve()
    entries = total = 0
    for current, dirs, files in os.walk(root, followlinks=False):
        current_path = Path(current)
        depth = len(current_path.relative_to(root).parts)
        if depth > max_depth:
            raise CompatibilityError("candidate depth limit exceeded", category="verify", phase="tree")
        for name in [*dirs, *files]:
            entries += 1
            if entries > max_entries:
                raise CompatibilityError("candidate entry limit exceeded", category="verify", phase="tree")
            item = current_path / name
            metadata = item.lstat()
            if stat.S_ISLNK(metadata.st_mode) or not (stat.S_ISDIR(metadata.st_mode) or stat.S_ISREG(metadata.st_mode)):
                raise CompatibilityError("candidate contains an unsafe entry", category="verify", phase="tree")
            if not stat.S_ISREG(metadata.st_mode):
                continue
            total += metadata.st_size
            if total > max_bytes:
                raise CompatibilityError("candidate byte limit exceeded", category="verify", phase="tree")
    return entries, total


def _candidate_kind(path: Path) -> str | None:
    if (path / "failure.json").is_file():
        return "failed"
    if (path / PENDING_MARKER).exists():
        return None
    if (path / "manifest.json").is_file() and (path / "success.json").is_file():
        return "success"
    return None


def _candidate_kind_fd(candidate_fd: int) -> str | None:
    if _regular_at(candidate_fd, "failure.json"):
        return "failed"
    if _exists_at(candidate_fd, PENDING_MARKER):
        return None
    if (_regular_at(candidate_fd, "manifest.json")
            and _regular_at(candidate_fd, "success.json")):
        return "success"
    return None


def _exists_at(candidate_fd: int, name: str) -> bool:
    try:
        os.stat(name, dir_fd=candidate_fd, follow_symlinks=False)
        return True
    except FileNotFoundError:
        return False


def _regular_at(candidate_fd: int, name: str) -> bool:
    try:
        metadata = os.stat(name, dir_fd=candidate_fd, follow_symlinks=False)
        return stat.S_ISREG(metadata.st_mode)
    except FileNotFoundError:
        return False


def _retry_quarantines(root_fd: int) -> None:
    """Complete deletions interrupted after an atomic prune rename."""
    for name in os.listdir(root_fd):
        if not _QUARANTINE.fullmatch(name):
            continue
        metadata = os.stat(name, dir_fd=root_fd, follow_symlinks=False)
        if not stat.S_ISDIR(metadata.st_mode):
            raise CompatibilityError("prune quarantine is unsafe", category="verify", phase="prune")
        shutil.rmtree(name, dir_fd=root_fd)


def _discover_candidates(root: Path, root_fd: int) -> list[Path]:
    candidates = []
    for name in os.listdir(root_fd):
        if not _NAME.fullmatch(name):
            continue
        metadata = os.stat(name, dir_fd=root_fd, follow_symlinks=False)
        if stat.S_ISDIR(metadata.st_mode):
            candidates.append(root / name)
    return candidates


def _candidate_created(path: Path) -> datetime | None:
    try:
        return datetime.strptime(path.name[:16], "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _select_prune_candidates(
    candidates: list[Path], max_total_bytes: int,
) -> dict[Path, str | None]:
    selected: dict[Path, str | None] = {}
    keep: set[Path] = set()
    for kind, limit in (("success", 3), ("failed", 2)):
        group = sorted((item for item in candidates if _candidate_kind(item) == kind), reverse=True)
        keep.update(group[:limit])
        selected.update({item: kind for item in group[limit:]})
    now = datetime.now(timezone.utc)
    for item in candidates:
        if _candidate_kind(item) is not None:
            continue
        created = _candidate_created(item)
        if created is not None and (now - created).total_seconds() >= 3600:
            selected[item] = None
    total = 0
    for item in sorted(keep, reverse=True):
        try:
            size = tree_stats(item)[1]
        except CompatibilityError:
            selected[item] = _candidate_kind(item)
            continue
        if total + size <= max_total_bytes:
            total += size
        else:
            selected[item] = _candidate_kind(item)
    return selected


def _idle_candidates(candidates: list[Path], root: Path) -> list[Path]:
    """Exclude candidates whose owner is still generating or verifying."""
    idle = []
    for item in candidates:
        try:
            with candidate_lease(item, blocking=False, root=root):
                idle.append(item)
        except LeaseBusy:
            continue
    return idle


def _apply_prune_candidate(
    item: Path, observed_kind: str | None, *, apply: bool, root: Path, root_fd: int,
) -> bool:
    try:
        with candidate_lease(item, blocking=False, root=root, yield_fd=True) as (_, candidate_fd):
            if _exists_at(candidate_fd, ".pin") or _candidate_kind_fd(candidate_fd) != observed_kind:
                return False
            if apply:
                current = os.stat(item.name, dir_fd=root_fd, follow_symlinks=False)
                leased = os.fstat(candidate_fd)
                if (current.st_dev, current.st_ino) != (leased.st_dev, leased.st_ino):
                    raise CompatibilityError("candidate identity changed before prune", category="verify", phase="prune")
                quarantine = f".prune-{uuid.uuid4().hex}"
                os.rename(item.name, quarantine, src_dir_fd=root_fd, dst_dir_fd=root_fd)
                shutil.rmtree(quarantine, dir_fd=root_fd)
            return True
    except LeaseBusy:
        return False


def prune(*, apply: bool, root: Path = CANDIDATE_ROOT, max_total_bytes: int = MAX_CANDIDATE_BYTES) -> list[str]:
    root = _ensure_root(root)
    result: list[Path] = []
    with _registry_lock(root) as root_fd:
        if apply:
            _retry_quarantines(root_fd)
        candidates = _discover_candidates(root, root_fd)
        selected = _select_prune_candidates(
            _idle_candidates(candidates, root), max_total_bytes,
        )
        for item, observed_kind in sorted(selected.items()):
            if _apply_prune_candidate(
                item, observed_kind, apply=apply, root=root, root_fd=root_fd,
            ):
                result.append(item)
    return [item.name for item in result]
