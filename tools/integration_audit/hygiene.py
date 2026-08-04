"""Immutable diff and blob hygiene checks."""

from __future__ import annotations

from dataclasses import dataclass
import re

from .history import BASE_COMMIT
from .model import (
    AuditError, MAX_BLOB_SCAN_BYTES, MAX_CAPTURE_BYTES, MAX_CHANGED_PATHS,
    MAX_PATH_BYTES, require_sha, sha256_bytes,
)
from .git_commands import GitRunner
from .path_policy import require_relative_path


CONFLICT_LINE = re.compile(br"(?m)^(?:<{7}|={7}|>{7})(?: |$)")


@dataclass(frozen=True)
class HygieneEvidence:
    diff_sha256: str
    changed_paths_sha256: str
    changed_path_count: int
    changed_paths: tuple[str, ...]


def _validated_paths(raw: bytes) -> tuple[str, ...]:
    chunks = raw.split(b"\0")
    if chunks and chunks[-1] == b"":
        chunks.pop()
    if len(chunks) > MAX_CHANGED_PATHS:
        raise AuditError("diff hygiene", "changed path inventory exceeds its bound")
    paths: list[str] = []
    for item in chunks:
        if not item or len(item) > MAX_PATH_BYTES:
            raise AuditError("diff hygiene", "changed path is empty or too long")
        try:
            path = item.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise AuditError("diff hygiene", "changed path is not UTF-8") from exc
        require_relative_path(
            path, category="diff hygiene", detail="changed path is unsafe",
        )
        paths.append(path)
    if len(paths) != len(set(paths)):
        raise AuditError("diff hygiene", "changed path inventory contains duplicates")
    return tuple(paths)


def _candidate_blobs(
    git: GitRunner, candidate: str, paths: tuple[str, ...],
) -> tuple[str, ...]:
    raw = git.bytes(
        "diff", "--raw", "--no-abbrev", "-z", "--no-renames", BASE_COMMIT, candidate,
        capture_limit=MAX_CAPTURE_BYTES,
    )
    fields = raw.split(b"\0")
    if fields and fields[-1] == b"":
        fields.pop()
    if len(fields) % 2:
        raise AuditError("diff hygiene", "raw changed-path inventory is malformed")
    raw_paths = fields[1::2]
    parsed_paths = _validated_paths(b"\0".join(raw_paths) + (b"\0" if raw_paths else b""))
    if parsed_paths != paths:
        raise AuditError("diff hygiene", "changed-path inventories disagree")
    blobs: list[str] = []
    for header in fields[::2]:
        parts = header.split()
        if len(parts) != 5 or not parts[0].startswith(b":"):
            raise AuditError("diff hygiene", "raw tree entry is malformed")
        mode = parts[1]
        try:
            object_id = parts[3].decode("ascii")
        except UnicodeDecodeError as exc:
            raise AuditError("diff hygiene", "candidate object id is malformed") from exc
        if mode in {b"100644", b"100755"}:
            blobs.append(require_sha(object_id, "candidate blob"))
    return tuple(dict.fromkeys(blobs))


def _bounded_blob_sizes(git: GitRunner, object_ids: tuple[str, ...]) -> tuple[tuple[str, int], ...]:
    if not object_ids:
        return ()
    raw = git.bytes(
        "cat-file", "--batch-check=%(objectname) %(objecttype) %(objectsize)",
        input_bytes=("\n".join(object_ids) + "\n").encode("ascii"),
        capture_limit=max(1024, len(object_ids) * 128),
    )
    lines = raw.splitlines()
    if len(lines) != len(object_ids):
        raise AuditError("diff hygiene", "candidate blob inventory is malformed")
    result: list[tuple[str, int]] = []
    for expected, line in zip(object_ids, lines, strict=True):
        parts = line.split()
        try:
            size = int(parts[2])
        except (IndexError, ValueError) as exc:
            raise AuditError("diff hygiene", "candidate blob size is invalid") from exc
        if parts[:2] != [expected.encode("ascii"), b"blob"] or size < 0:
            raise AuditError("diff hygiene", "candidate blob inventory is malformed")
        if size <= MAX_BLOB_SCAN_BYTES:
            result.append((expected, size))
    return tuple(result)


def _scan_blob_batch(git: GitRunner, batch: list[tuple[str, int]]) -> None:
    raw = git.bytes(
        "cat-file", "--batch",
        input_bytes=("\n".join(object_id for object_id, _size in batch) + "\n").encode("ascii"),
        capture_limit=sum(size + 128 for _object_id, size in batch) + 16 * 1024,
    )
    offset = 0
    for object_id, size in batch:
        header_end = raw.find(b"\n", offset)
        if header_end < 0:
            raise AuditError("diff hygiene", "candidate blob batch is malformed")
        expected = f"{object_id} blob {size}".encode("ascii")
        if raw[offset:header_end] != expected:
            raise AuditError("diff hygiene", "candidate blob batch is malformed")
        start = header_end + 1
        end = start + size
        blob = raw[start:end]
        if len(blob) != size or raw[end:end + 1] != b"\n":
            raise AuditError("diff hygiene", "candidate blob batch is truncated")
        if b"\x00" not in blob and CONFLICT_LINE.search(blob):
            raise AuditError("diff hygiene", "candidate blob contains a conflict marker")
        offset = end + 1
    if offset != len(raw):
        raise AuditError("diff hygiene", "candidate blob batch has trailing data")


def _scan_candidate_blobs(git: GitRunner, object_ids: tuple[str, ...]) -> None:
    batch: list[tuple[str, int]] = []
    batch_bytes = 0
    for item in _bounded_blob_sizes(git, object_ids):
        cost = item[1] + 128
        if batch and batch_bytes + cost > MAX_CAPTURE_BYTES - 16 * 1024:
            _scan_blob_batch(git, batch)
            batch = []
            batch_bytes = 0
        batch.append(item)
        batch_bytes += cost
    if batch:
        _scan_blob_batch(git, batch)


def verify_hygiene(git: GitRunner, candidate: str) -> HygieneEvidence:
    try:
        check = git.bytes("diff", "--check", BASE_COMMIT, candidate)
    except AuditError as exc:
        raise AuditError("diff hygiene", "git diff --check reported an error") from exc
    if check:
        raise AuditError("diff hygiene", "git diff --check reported an error")
    raw_paths = git.bytes(
        "diff", "--name-only", "-z", BASE_COMMIT, candidate,
        capture_limit=MAX_CAPTURE_BYTES,
    )
    paths = _validated_paths(raw_paths)
    _scan_candidate_blobs(git, _candidate_blobs(git, candidate, paths))
    patch = git.bytes("diff", "--binary", "--full-index", BASE_COMMIT, candidate, capture_limit=MAX_CAPTURE_BYTES)
    return HygieneEvidence(
        diff_sha256=sha256_bytes(patch),
        changed_paths_sha256=sha256_bytes(raw_paths),
        changed_path_count=len(paths), changed_paths=paths,
    )
