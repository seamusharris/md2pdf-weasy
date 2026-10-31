#!/usr/bin/env python3
"""Reproducible visual PDF acceptance evidence.

The ordinary test suite exercises the small, deterministic helpers in this
module.  ``generate`` is the explicit, slower acceptance command: it renders a
synthetic matrix once per case, checks the exact rendered WeasyPrint document,
rasterizes every page with Poppler, and writes an ignored candidate manifest.
``promote`` copies only a verified manifest and contact sheets into an
immutable, tracked evidence version and atomically updates the active pointer.
"""

from __future__ import annotations

import argparse
import contextlib
import dataclasses
import fcntl
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path, PurePosixPath
import platform
import re
import selectors
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time
from typing import Any, Iterable
import uuid

import yaml


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "tests" / "visual" / "table-widths.md"
OUTPUT_ROOT = ROOT / "output" / "pdf" / "visual-acceptance"
CANDIDATE_ROOT = OUTPUT_ROOT / "candidates"
APPROVED_ROOT = ROOT / "docs" / "visual-acceptance"
APPROVED_VERSIONS = APPROVED_ROOT / "approved"
ACTIVE_POINTER = APPROVED_ROOT / "active.json"
DEFAULT_OUTPUT_ROOT = OUTPUT_ROOT
DEFAULT_APPROVED_ROOT = APPROVED_ROOT
LOADED_TOOL_SHA256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()

SCHEMA_VERSION = 3
RASTER_DPI = 144
THUMB_WIDTH = 300
SHEET_COLUMNS = 4
MAX_PAGES_PER_CASE = 24
MAX_TOTAL_PIXELS = 180_000_000
MAX_STDERR_BYTES = 32_768
MAX_CAPTURE_BYTES = 4 * 1024 * 1024
MAX_MANIFEST_BYTES = 16 * 1024 * 1024
MAX_POINTER_BYTES = 64 * 1024
MAX_WORKER_RESULT_BYTES = 4 * 1024 * 1024
MAX_CANDIDATE_BYTES = 1024 * 1024 * 1024
MAX_PDF_BYTES = 128 * 1024 * 1024
MAX_IMAGE_BYTES = 64 * 1024 * 1024
MAX_PDF_OBJECTS = 20_000
MAX_DECODED_PDF_BYTES = 256 * 1024 * 1024
MAX_CANDIDATE_ENTRIES = 10_000
MAX_CANDIDATE_DEPTH = 8
MAX_CANDIDATE_ROOT_ENTRIES = 1_000
CASE_TIMEOUT = 120.0
MATRIX_TIMEOUT = 1_200.0
GEOMETRY_TOLERANCE = 0.75
RENDER_DEPENDENCIES = (
    "weasyprint",
    "markdown",
    "pymdown-extensions",
    "pyyaml",
    "fonttools",
    "pillow",
    "pypdf",
)
THEMES = ("alpine", "wnc", "regrading", "neutral", "compact")
GEOMETRY_CHECK_IDS = (
    "tables-present", "orientation", "page-overflow", "cell-containment",
    "column-boundaries", "shared-ladder-widths", "shared-schedule-widths",
    "declared-proportions", "single-line-sentinel", "wrap-sentinels",
)
SEMANTIC_CHECK_IDS = (
    "pdf-table-tags", "pdf-caption", "pdf-caption-owner",
    "pdf-header-associations", "pdf-tagged-order", "pdf-content-order",
)


class AcceptanceError(RuntimeError):
    """An actionable, fail-closed acceptance failure."""


class LeaseBusy(AcceptanceError):
    """A nonblocking lease is currently held by another workflow."""


class TreeLimitExceeded(AcceptanceError):
    """A candidate tree exceeded a configured retention/validation bound."""


@dataclasses.dataclass(frozen=True)
class AcceptanceCase:
    case_id: str
    theme: str
    orientation: str = "portrait"
    table_widths: bool = True
    declared: bool = False
    page_width_em: float | None = None


@dataclasses.dataclass(frozen=True)
class CheckResult:
    check_id: str
    status: str
    detail: str
    measurements: dict[str, Any] = dataclasses.field(default_factory=dict)


def acceptance_cases() -> tuple[AcceptanceCase, ...]:
    """The stable, declarative acceptance matrix."""
    theme_cases = tuple(
        AcceptanceCase(f"automatic-{theme}", theme) for theme in THEMES
    )
    return theme_cases + (
        AcceptanceCase("declared-neutral", "neutral", declared=True),
        AcceptanceCase("legacy-neutral", "neutral", table_widths=False),
        AcceptanceCase(
            "overwide-portrait", "neutral", page_width_em=42.0
        ),
        AcceptanceCase(
            "overwide-landscape", "neutral", orientation="landscape"
        ),
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _hash_regular_file_bounded(
    path: Path, *, context: str, max_bytes: int,
) -> tuple[str, int]:
    """Hash one regular file through a single no-follow, size-bounded FD."""
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise AcceptanceError(f"{context} is missing or unsafe") from exc
    digest = hashlib.sha256()
    size = 0
    try:
        metadata = os.fstat(fd)
        if not stat.S_ISREG(metadata.st_mode):
            raise AcceptanceError(f"{context} is not a regular file")
        if metadata.st_size > max_bytes:
            raise AcceptanceError(f"{context} exceeds {max_bytes} bytes")
        while True:
            chunk = os.read(fd, min(1024 * 1024, max_bytes + 1 - size))
            if not chunk:
                break
            size += len(chunk)
            if size > max_bytes:
                raise AcceptanceError(f"{context} exceeds {max_bytes} bytes")
            digest.update(chunk)
        if size != metadata.st_size:
            raise AcceptanceError(f"{context} changed while being read")
        return digest.hexdigest(), size
    except AcceptanceError:
        raise
    except OSError as exc:
        raise AcceptanceError(f"{context} changed while being read") from exc
    finally:
        os.close(fd)


def _pdf_object_evidence(path: Path) -> dict[str, Any]:
    """Return a bounded canonical digest of the complete decoded PDF graph."""
    from pypdf import PdfReader
    from pypdf.generic import (
        ArrayObject, ByteStringObject, DictionaryObject, IndirectObject,
        StreamObject,
    )

    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise AcceptanceError(f"PDF is missing or unsafe: {path.name}") from exc
    decoded_bytes = 0
    dangerous = []
    structure_ids: dict[str, str] = {}
    dangerous_keys = {
        "/AA", "/OpenAction", "/EmbeddedFiles", "/EF", "/AF", "/XFA",
        "/RichMediaContent", "/RichMediaSettings", "/Collection",
    }
    dangerous_actions = {
        "/JavaScript", "/Launch", "/SubmitForm", "/ImportData", "/GoToR",
        "/GoToE", "/Rendition", "/Sound", "/Movie", "/Hide",
        "/SetOCGState", "/Trans", "/GoTo3DView", "/URI",
    }
    dangerous_subtypes = {
        "/FileAttachment", "/RichMedia", "/Movie", "/Sound", "/Screen", "/3D",
    }

    def canonical(value: Any, location: str) -> Any:
        nonlocal decoded_bytes
        if isinstance(value, IndirectObject):
            return {"ref": [value.idnum, value.generation]}
        if isinstance(value, DictionaryObject):
            record = {}
            action = str(value.get("/S", ""))
            subtype = str(value.get("/Subtype", ""))
            if action in dangerous_actions:
                dangerous.append(f"{location}: action {action}")
            if subtype in dangerous_subtypes:
                dangerous.append(f"{location}: subtype {subtype}")
            for key in sorted(value, key=str):
                name = str(key)
                if isinstance(value, StreamObject) and name in {
                    "/Length", "/Filter", "/DecodeParms",
                }:
                    continue
                if name in dangerous_keys:
                    dangerous.append(f"{location}: key {name}")
                record[name] = canonical(value.raw_get(key), f"{location}/{name}")
            if isinstance(value, StreamObject):
                data = value.get_data()
                decoded_bytes += len(data)
                if decoded_bytes > MAX_DECODED_PDF_BYTES:
                    raise AcceptanceError("decoded PDF streams exceed safe byte limit")
                data = _canonical_stream_bytes(data)
                record["$decoded_stream"] = {
                    "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(),
                }
            return {"dictionary": record}
        if isinstance(value, ArrayObject):
            return {
                "array": [canonical(item, f"{location}[{index}]")
                          for index, item in enumerate(value)]
            }
        if isinstance(value, ByteStringObject) or isinstance(value, bytes):
            return {"bytes": bytes(value).hex()}
        if value is None:
            return {"null": True}
        if isinstance(value, bool):
            return {"bool": value}
        if isinstance(value, (int, float)):
            return {"number": str(value)}
        text = str(value)
        return {type(value).__name__: structure_ids.get(text, text)}

    try:
        metadata = os.fstat(fd)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > MAX_PDF_BYTES:
            raise AcceptanceError(f"PDF exceeds the safe parser input limit: {path.name}")
        with os.fdopen(os.dup(fd), "rb") as stream:
            reader = PdfReader(
                stream, strict=True, root_object_recovery_limit=MAX_PDF_OBJECTS,
            )
            if reader.is_encrypted:
                raise AcceptanceError("encrypted PDFs are not accepted")
            object_ids = set(reader.xref_objStm)
            object_ids.update(
                object_id for generation in reader.xref.values()
                for object_id in generation if object_id
            )
            if len(object_ids) > MAX_PDF_OBJECTS:
                raise AcceptanceError("PDF exceeds object-count limit")
            for object_id in sorted(object_ids):
                value = reader.get_object(object_id)
                if (
                    isinstance(value, DictionaryObject)
                    and str(value.get("/Type", "")) == "/StructElem"
                    and "/ID" in value
                ):
                    structure_ids[str(value.get("/ID"))] = f"struct-{object_id}"
            objects = []
            for object_id in sorted(object_ids):
                value = reader.get_object(object_id)
                if (
                    isinstance(value, DictionaryObject)
                    and str(value.get("/Type", "")) in {"/XRef", "/ObjStm"}
                ):
                    continue
                objects.append([object_id, canonical(value, f"object {object_id}")])
            trailer = DictionaryObject({
                key: value for key, value in reader.trailer.items() if str(key) != "/ID"
            })
            graph = {
                "header": reader.pdf_header,
                "trailer": canonical(trailer, "trailer"),
                "objects": objects,
            }
            pages = []
            for number, page in enumerate(reader.pages, 1):
                media = page.mediabox
                crop = page.cropbox
                pages.append({
                    "page": number,
                    "media_width_pt": float(media.width),
                    "media_height_pt": float(media.height),
                    "crop_width_pt": float(crop.width),
                    "crop_height_pt": float(crop.height),
                })
    except AcceptanceError:
        raise
    except Exception as exc:
        raise AcceptanceError(f"PDF object graph is invalid: {path.name}") from exc
    finally:
        os.close(fd)
    if dangerous:
        raise AcceptanceError(
            "PDF contains active or embedded content: " + "; ".join(dangerous[:8])
        )
    return {
        "graph_sha256": hashlib.sha256(_json_bytes(graph)).hexdigest(),
        "pages": pages,
        "object_count": len(objects),
        "decoded_stream_bytes": decoded_bytes,
    }


def _canonical_stream_bytes(data: bytes) -> bytes:
    """Remove only volatile OpenType checksum and modification fields."""
    data = bytes(data)
    if len(data) < 12 or data[:4] not in {b"\x00\x01\x00\x00", b"OTTO"}:
        return data
    table_count = int.from_bytes(data[4:6], "big")
    directory_end = 12 + (16 * table_count)
    if table_count > 4096 or directory_end > len(data):
        return data
    for offset in range(12, directory_end, 16):
        if data[offset:offset + 4] != b"head":
            continue
        table_offset = int.from_bytes(data[offset + 8:offset + 12], "big")
        table_length = int.from_bytes(data[offset + 12:offset + 16], "big")
        if table_length < 54 or table_offset + table_length > len(data):
            return data
        normalized = bytearray(data)
        normalized[offset + 4:offset + 8] = b"\0" * 4
        normalized[table_offset + 8:table_offset + 12] = b"\0" * 4
        normalized[table_offset + 28:table_offset + 36] = b"\0" * 8
        return bytes(normalized)
    return data


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _input_digest(inputs: dict[str, str]) -> str:
    return hashlib.sha256(_json_bytes(inputs)).hexdigest()


def _is_sha256(value: Any) -> bool:
    return isinstance(value, str) and bool(re.fullmatch(r"[0-9a-f]{64}", value))


def _write_bytes_atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, raw_temp = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temp = Path(raw_temp)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def _write_json_atomic(path: Path, value: Any) -> None:
    _write_bytes_atomic(path, _json_bytes(value))


def _write_json_atomic_at(directory_fd: int, name: str, value: Any) -> None:
    """Durably replace a JSON file relative to one stable directory FD."""
    temp_name = f".{name}.{os.getpid()}.{uuid.uuid4().hex}.tmp"
    fd = None
    try:
        fd = os.open(
            temp_name, os.O_CREAT | os.O_EXCL | os.O_WRONLY,
            0o600, dir_fd=directory_fd,
        )
        data = _json_bytes(value)
        view = memoryview(data)
        while view:
            written = os.write(fd, view)
            view = view[written:]
        os.fsync(fd)
        os.close(fd)
        fd = None
        os.rename(
            temp_name, name,
            src_dir_fd=directory_fd, dst_dir_fd=directory_fd,
        )
    finally:
        if fd is not None:
            os.close(fd)
        with contextlib.suppress(FileNotFoundError):
            os.unlink(temp_name, dir_fd=directory_fd)


def _read_json_bounded(path: Path, *, context: str, max_bytes: int) -> Any:
    flags = (
        os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_NONBLOCK", 0)
    )
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise AcceptanceError(f"{context} is unreadable") from exc
    try:
        metadata = os.fstat(fd)
        if not stat.S_ISREG(metadata.st_mode):
            raise AcceptanceError(f"{context} is unsafe")
        if metadata.st_size > max_bytes:
            raise AcceptanceError(
                f"{context} exceeds {max_bytes} bytes: {metadata.st_size}"
            )
        chunks = bytearray()
        while len(chunks) <= max_bytes:
            chunk = os.read(fd, min(64 * 1024, max_bytes + 1 - len(chunks)))
            if not chunk:
                break
            chunks.extend(chunk)
        if len(chunks) > max_bytes:
            raise AcceptanceError(f"{context} exceeds {max_bytes} bytes")
        return json.loads(chunks)
    except AcceptanceError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise AcceptanceError(f"{context} is unreadable") from exc
    finally:
        os.close(fd)


def _assert_no_symlink_components(path: Path, *, label: str) -> None:
    """Reject symlinks in every existing component of an absolute path."""
    absolute = path.absolute()
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current /= part
        try:
            metadata = current.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(metadata.st_mode):
            raise AcceptanceError(f"{label} has a symlinked path component: {current}")


def _assert_default_root_is_repository_anchored(
    path: Path, *, default: Path, label: str,
) -> None:
    """Keep production storage below the resolved repository root.

    Tests deliberately replace the configured roots with isolated temporary
    directories. Those roots still receive component-by-component no-follow
    checks; the immutable production default additionally has to stay below
    the repository root.
    """
    if path.absolute() != default.absolute():
        return
    try:
        path.resolve(strict=True).relative_to(ROOT.resolve(strict=True))
    except (FileNotFoundError, ValueError) as exc:
        raise AcceptanceError(f"{label} escapes the repository root") from exc


@contextlib.contextmanager
def _directory_fd(path: Path, *, label: str):
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise AcceptanceError(f"cannot open {label} safely") from exc
    try:
        metadata = os.fstat(fd)
        if not stat.S_ISDIR(metadata.st_mode):
            raise AcceptanceError(f"{label} must be a directory")
        yield fd, (metadata.st_dev, metadata.st_ino)
    finally:
        os.close(fd)


def _directory_identity(path: Path) -> tuple[int, int]:
    try:
        metadata = path.stat(follow_symlinks=False)
    except OSError as exc:
        raise AcceptanceError(f"directory changed or disappeared: {path}") from exc
    if not stat.S_ISDIR(metadata.st_mode):
        raise AcceptanceError(f"directory changed or disappeared: {path}")
    return metadata.st_dev, metadata.st_ino


def _path_from_fd(fd: int) -> Path:
    """Resolve an open directory descriptor to its current filesystem path."""
    try:
        if hasattr(fcntl, "F_GETPATH"):
            raw = fcntl.fcntl(fd, fcntl.F_GETPATH, b"\0" * 1024)
            path = Path(raw.split(b"\0", 1)[0].decode())
        else:
            path = (Path("/proc/self/fd") / str(fd)).resolve(strict=True)
    except (OSError, UnicodeError, ValueError) as exc:
        raise AcceptanceError("cannot resolve stable directory descriptor") from exc
    if _directory_identity(path) != (
        os.fstat(fd).st_dev, os.fstat(fd).st_ino,
    ):
        raise AcceptanceError("directory descriptor path changed")
    return path


@contextlib.contextmanager
def _directory_fd_at(parent_fd: int, name: str, *, label: str):
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(name, flags, dir_fd=parent_fd)
    except OSError as exc:
        raise AcceptanceError(f"cannot open {label} safely") from exc
    try:
        if not stat.S_ISDIR(os.fstat(fd).st_mode):
            raise AcceptanceError(f"{label} must be a directory")
        stable = _path_from_fd(fd)
        yield fd, stable
    finally:
        os.close(fd)


@contextlib.contextmanager
def _directory_fd_only_at(parent_fd: int, name: str, *, label: str):
    """Open a child directory without converting its descriptor to a path."""
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(name, flags, dir_fd=parent_fd)
    except OSError as exc:
        raise AcceptanceError(f"cannot open {label} safely") from exc
    try:
        metadata = os.fstat(fd)
        if not stat.S_ISDIR(metadata.st_mode):
            raise AcceptanceError(f"{label} must be a directory")
        yield fd, (metadata.st_dev, metadata.st_ino)
    finally:
        os.close(fd)


def _prepare_candidate_root() -> Path:
    expected = OUTPUT_ROOT / "candidates"
    if CANDIDATE_ROOT.absolute() != expected.absolute():
        raise AcceptanceError("candidate root is not directly beneath output root")
    _assert_no_symlink_components(OUTPUT_ROOT, label="output root")
    for path, label in ((OUTPUT_ROOT, "output root"), (CANDIDATE_ROOT, "candidate root")):
        if path.is_symlink():
            raise AcceptanceError(f"{label} must not be a symlink")
        if path.exists() and not path.is_dir():
            raise AcceptanceError(f"{label} must be a directory")
        path.mkdir(parents=True, exist_ok=True)
        _assert_no_symlink_components(path, label=label)
    output = OUTPUT_ROOT.resolve(strict=True)
    candidate = CANDIDATE_ROOT.resolve(strict=True)
    _assert_default_root_is_repository_anchored(
        OUTPUT_ROOT, default=DEFAULT_OUTPUT_ROOT, label="output root",
    )
    if candidate.parent != output:
        raise AcceptanceError("candidate root escapes output root")
    return candidate


def _prepare_approved_root(*, create: bool) -> Path:
    if APPROVED_VERSIONS.absolute() != (APPROVED_ROOT / "approved").absolute():
        raise AcceptanceError("approved versions root is not directly beneath approved root")
    if ACTIVE_POINTER.absolute() != (APPROVED_ROOT / "active.json").absolute():
        raise AcceptanceError("active pointer is not directly beneath approved root")
    _assert_no_symlink_components(APPROVED_ROOT, label="approved root")
    if create:
        APPROVED_ROOT.mkdir(parents=True, exist_ok=True)
        APPROVED_VERSIONS.mkdir(parents=False, exist_ok=True)
    for path, label in (
        (APPROVED_ROOT, "approved root"),
        (APPROVED_VERSIONS, "approved versions root"),
    ):
        if not path.exists():
            raise AcceptanceError(f"{label} does not exist")
        _assert_no_symlink_components(path, label=label)
        if not path.is_dir():
            raise AcceptanceError(f"{label} must be a directory")
    _assert_default_root_is_repository_anchored(
        APPROVED_ROOT, default=DEFAULT_APPROVED_ROOT, label="approved root",
    )
    approved = APPROVED_ROOT.resolve(strict=True)
    versions = APPROVED_VERSIONS.resolve(strict=True)
    if versions.parent != approved:
        raise AcceptanceError("approved versions root escapes approved root")
    return approved


def _scan_tree_bounded(root: Path) -> tuple[set[str], int]:
    """Return regular/special file paths using a bounded, no-follow walk."""
    files: set[str] = set()
    total = 0
    count = 0
    stack: list[tuple[Path, PurePosixPath]] = [(root, PurePosixPath())]
    try:
        while stack:
            directory, prefix = stack.pop()
            with os.scandir(directory) as entries:
                for entry in entries:
                    count += 1
                    if count > MAX_CANDIDATE_ENTRIES:
                        raise TreeLimitExceeded("candidate tree exceeds entry limit")
                    relative = prefix / entry.name
                    if len(relative.parts) > MAX_CANDIDATE_DEPTH:
                        raise TreeLimitExceeded("candidate tree exceeds depth limit")
                    metadata = entry.stat(follow_symlinks=False)
                    if stat.S_ISDIR(metadata.st_mode):
                        stack.append((Path(entry.path), relative))
                    else:
                        files.add(relative.as_posix())
                        if stat.S_ISREG(metadata.st_mode):
                            total += metadata.st_size
                            if total > MAX_CANDIDATE_BYTES:
                                raise TreeLimitExceeded("candidate tree exceeds byte limit")
    except OSError as exc:
        raise AcceptanceError("candidate tree changed during traversal") from exc
    return files, total


def _candidate_tree_size(candidate: Path) -> int:
    try:
        return _scan_tree_bounded(candidate)[1]
    except TreeLimitExceeded:
        return MAX_CANDIDATE_BYTES + 1


def _safe_relative_path(raw: str) -> PurePosixPath:
    """Validate one manifest path without consulting the filesystem."""
    if not isinstance(raw, str) or not raw:
        raise AcceptanceError("artifact path must be a non-empty string")
    raw_parts = raw.split("/")
    path = PurePosixPath(raw)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in raw_parts):
        raise AcceptanceError(f"unsafe artifact path: {raw!r}")
    if "\\" in raw:
        raise AcceptanceError(f"artifact path must use POSIX separators: {raw!r}")
    return path


def _contained_file(root: Path, raw: str, *, suffixes: set[str]) -> Path:
    relative = _safe_relative_path(raw)
    if relative.suffix.lower() not in suffixes:
        raise AcceptanceError(f"disallowed artifact type: {raw}")
    resolved_root = root.resolve()
    target = root.joinpath(*relative.parts)
    try:
        resolved = target.resolve(strict=True)
    except FileNotFoundError as exc:
        raise AcceptanceError(f"artifact is missing: {raw}") from exc
    if resolved.parent != resolved_root and resolved_root not in resolved.parents:
        raise AcceptanceError(f"artifact escapes candidate root: {raw}")
    stat = target.lstat()
    if not target.is_file() or target.is_symlink():
        raise AcceptanceError(f"artifact must be a regular non-symlink file: {raw}")
    if stat.st_size <= 0:
        raise AcceptanceError(f"artifact is empty: {raw}")
    return target


def _validate_manifest_shape(manifest: Any) -> dict[str, Any]:
    if not isinstance(manifest, dict):
        raise AcceptanceError("manifest must be a JSON object")
    if manifest.get("schema_version") != SCHEMA_VERSION:
        raise AcceptanceError(
            f"unsupported manifest schema: {manifest.get('schema_version')!r}"
        )
    if manifest.get("status") != "passed":
        raise AcceptanceError("only a passed candidate may be verified or promoted")
    source = manifest.get("source")
    if not isinstance(source, dict) or not _is_sha256(source.get("digest")):
        raise AcceptanceError("manifest source digest must be 64 lowercase hex digits")
    input_hashes = source.get("input_hashes")
    if not isinstance(input_hashes, dict) or not input_hashes:
        raise AcceptanceError("manifest source input_hashes must be non-empty")
    for raw_path, digest in input_hashes.items():
        _safe_relative_path(raw_path)
        if not _is_sha256(digest):
            raise AcceptanceError(f"invalid source input hash: {raw_path!r}")
    if source["digest"] != _input_digest(input_hashes):
        raise AcceptanceError("manifest source digest does not match input hashes")
    baseline = manifest.get("review_baseline")
    if baseline is not None and not _is_sha256(baseline):
        raise AcceptanceError("review_baseline must be null or a SHA-256 digest")

    cases = manifest.get("cases")
    if not isinstance(cases, list) or not cases:
        raise AcceptanceError("manifest cases must be a non-empty list")
    expected_cases = acceptance_cases()
    if len(cases) != len(expected_cases) or any(
        not isinstance(case, dict) for case in cases
    ):
        raise AcceptanceError("manifest cases must be the exact object matrix")
    case_ids = [case.get("case_id") for case in cases]
    expected_ids = [case.case_id for case in expected_cases]
    if case_ids != expected_ids:
        raise AcceptanceError(
            f"manifest case order differs: expected {expected_ids}, got {case_ids}"
        )
    expected_review_paths = []
    expected_pdf_records = {}
    for record, expected_case in zip(cases, expected_cases):
        if not isinstance(record, dict):
            raise AcceptanceError(f"invalid case record: {expected_case.case_id}")
        if record.get("case") != dataclasses.asdict(expected_case):
            raise AcceptanceError(f"case metadata mismatch: {expected_case.case_id}")
        for field, expected_checks in (
            ("checks", GEOMETRY_CHECK_IDS),
            ("semantic_checks", SEMANTIC_CHECK_IDS),
        ):
            checks = record.get(field)
            if not isinstance(checks, list):
                raise AcceptanceError(
                    f"{expected_case.case_id}: {field} must be a list"
                )
            check_ids = [item.get("check_id") for item in checks or []
                         if isinstance(item, dict)]
            if check_ids != list(expected_checks) or any(
                not isinstance(item, dict) or
                item.get("status") != "passed" for item in checks or []
            ):
                raise AcceptanceError(
                    f"{expected_case.case_id}: invalid {field} result set"
                )
        if not _is_sha256(record.get("pdf_sha256")):
            raise AcceptanceError(f"{expected_case.case_id}: invalid PDF hash")
        if (
            not isinstance(record.get("pdf_bytes"), int)
            or record["pdf_bytes"] <= 0
            or record["pdf_bytes"] > MAX_PDF_BYTES
        ):
            raise AcceptanceError(f"{expected_case.case_id}: invalid PDF size")
        measurements = record.get("measurements")
        if not isinstance(measurements, dict):
            raise AcceptanceError(
                f"{expected_case.case_id}: measurements must be an object"
            )
        pages = record.get("pages")
        measured_pages = measurements.get("pages")
        if (
            not isinstance(pages, list) or not pages
            or not isinstance(measured_pages, list)
            or len(pages) != len(measured_pages)
            or len(pages) > MAX_PAGES_PER_CASE
        ):
            raise AcceptanceError(f"{expected_case.case_id}: invalid page records")
        for number, page in enumerate(measured_pages, 1):
            if (
                not isinstance(page, dict)
                or page.get("page") != number
                or any(
                    not isinstance(page.get(field), (int, float))
                    or isinstance(page.get(field), bool)
                    or not math.isfinite(page[field])
                    or page[field] <= 0
                    for field in ("width", "height")
                )
            ):
                raise AcceptanceError(
                    f"{expected_case.case_id}: invalid measured page {number}"
                )
        expected_page_paths = [
            f"cases/{expected_case.case_id}/page-{number}.png"
            for number in range(1, len(pages) + 1)
        ]
        if pages != expected_page_paths:
            raise AcceptanceError(f"{expected_case.case_id}: page paths are not exact")
        pdf_path = f"cases/{expected_case.case_id}/{record.get('pdf')}"
        if record.get("pdf") != f"{expected_case.case_id}.pdf":
            raise AcceptanceError(f"{expected_case.case_id}: PDF path is not exact")
        expected_review_paths.append((pdf_path, "pdf"))
        expected_pdf_records[pdf_path] = (
            record["pdf_bytes"], record["pdf_sha256"],
        )
        expected_review_paths.extend((path, "page") for path in pages)

    environment = manifest.get("environment")
    packages = environment.get("packages") if isinstance(environment, dict) else None
    if (
        not isinstance(packages, dict)
        or set(packages) != set(RENDER_DEPENDENCIES)
        or any(not isinstance(packages[name], str) or not packages[name]
               for name in RENDER_DEPENDENCIES)
    ):
        raise AcceptanceError("manifest environment omits render dependencies")
    for field in ("python", "poppler", "pango", "platform", "machine"):
        if not isinstance(environment.get(field), str) or not environment[field]:
            raise AcceptanceError(f"manifest environment field is invalid: {field}")
    if environment.get("raster") != {
        "format": "PNG", "color": "RGB", "dpi": RASTER_DPI,
        "thumbnail_width_px": THUMB_WIDTH, "sheet_columns": SHEET_COLUMNS,
    }:
        raise AcceptanceError("manifest raster environment is not canonical")

    artifacts = manifest.get("promotable_artifacts")
    if not isinstance(artifacts, list):
        raise AcceptanceError("manifest promotable_artifacts must be a list")
    paths = [item.get("path") for item in artifacts if isinstance(item, dict)]
    expected_paths = [f"contact-sheets/{case.case_id}.png" for case in expected_cases]
    if paths != expected_paths:
        raise AcceptanceError("manifest artifact set or order is incomplete")
    for item in artifacts:
        if not isinstance(item, dict):
            raise AcceptanceError("manifest artifact records must be objects")
        if not _is_sha256(item.get("sha256")):
            raise AcceptanceError(f"invalid artifact hash: {item.get('path')!r}")
        if (
            not isinstance(item.get("bytes"), int) or item["bytes"] <= 0
            or item["bytes"] > MAX_IMAGE_BYTES
        ):
            raise AcceptanceError(f"invalid artifact size: {item.get('path')!r}")
    reviewed = manifest.get("review_artifacts")
    if not isinstance(reviewed, list):
        raise AcceptanceError("manifest review_artifacts must be a list")
    if [(item.get("path"), item.get("kind")) for item in reviewed
        if isinstance(item, dict)] != expected_review_paths:
        raise AcceptanceError("manifest review artifact set or order is incomplete")
    for item in reviewed:
        if not isinstance(item, dict) or not _is_sha256(item.get("sha256")):
            raise AcceptanceError("invalid review artifact hash")
        size_limit = MAX_PDF_BYTES if item.get("kind") == "pdf" else MAX_IMAGE_BYTES
        if (
            not isinstance(item.get("bytes"), int) or item["bytes"] <= 0
            or item["bytes"] > size_limit
        ):
            raise AcceptanceError("invalid review artifact size")
        expected_keys = {"path", "kind", "bytes", "sha256"}
        if item["kind"] == "page":
            expected_keys |= {"width", "height"}
            if not all(isinstance(item.get(key), int) and item[key] > 0
                       for key in ("width", "height")):
                raise AcceptanceError("invalid review page dimensions")
        if set(item) != expected_keys:
            raise AcceptanceError("review artifact record has unexpected fields")
        if item["kind"] == "pdf" and (
            item["bytes"], item["sha256"]
        ) != expected_pdf_records[item["path"]]:
            raise AcceptanceError("review PDF record conflicts with case result")
    declared_bytes = sum(item["bytes"] for item in artifacts + reviewed)
    if declared_bytes > MAX_CANDIDATE_BYTES:
        raise AcceptanceError("manifest artifacts exceed candidate byte limit")
    declared_pixels = sum(
        item["width"] * item["height"]
        for item in reviewed if item["kind"] == "page"
    )
    if declared_pixels > MAX_TOTAL_PIXELS:
        raise AcceptanceError("manifest pages exceed aggregate pixel limit")
    return manifest


def _candidate_directory(candidate: Path) -> Path:
    _assert_no_symlink_components(CANDIDATE_ROOT, label="candidate root")
    if candidate.is_symlink():
        raise AcceptanceError("candidate directory must not be a symlink")
    try:
        resolved = candidate.resolve(strict=True)
    except FileNotFoundError as exc:
        raise AcceptanceError("candidate directory does not exist") from exc
    expected_root = CANDIDATE_ROOT.resolve()
    if resolved.parent != expected_root or not resolved.is_dir():
        raise AcceptanceError(f"candidate is outside {expected_root}")
    return resolved


def validate_candidate(
    candidate: Path, *, require_current: bool = False,
) -> dict[str, Any]:
    candidate = _candidate_directory(candidate)
    manifest_path = candidate / "manifest.json"
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise AcceptanceError("candidate manifest is missing or unsafe")
    manifest = _validate_manifest_shape(_read_json_bounded(
        manifest_path, context="candidate manifest", max_bytes=MAX_MANIFEST_BYTES,
    ))
    expected_files = {"manifest.json"} | {
        item["path"] for field in ("promotable_artifacts", "review_artifacts")
        for item in manifest[field]
    }
    actual_files, _ = _scan_tree_bounded(candidate)
    actual_files -= {".lease", ".pin"}
    missing = expected_files - actual_files
    if missing:
        raise AcceptanceError(f"candidate artifact is missing: {min(missing)}")
    unexpected = actual_files - expected_files
    if unexpected:
        raise AcceptanceError(f"candidate artifact is unexpected: {min(unexpected)}")
    for item in manifest["promotable_artifacts"]:
        path = _contained_file(candidate, item["path"], suffixes={".png", ".json"})
        digest, size = _hash_regular_file_bounded(
            path, context=f"artifact {item['path']}", max_bytes=item["bytes"],
        )
        if item.get("bytes") != size:
            raise AcceptanceError(f"artifact size mismatch: {item['path']}")
        if item.get("sha256") != digest:
            raise AcceptanceError(f"artifact hash mismatch: {item['path']}")
    for item in manifest["review_artifacts"]:
        suffixes = {".pdf"} if item["kind"] == "pdf" else {".png"}
        path = _contained_file(candidate, item["path"], suffixes=suffixes)
        digest, size = _hash_regular_file_bounded(
            path, context=f"review artifact {item['path']}", max_bytes=item["bytes"],
        )
        if item["sha256"] != digest or item["bytes"] != size:
            raise AcceptanceError(f"review artifact mismatch: {item['path']}")
        if item["kind"] == "page":
            from PIL import Image
            try:
                with Image.open(path) as image:
                    image.verify()
                with Image.open(path) as image:
                    size = image.size
            except (OSError, ValueError) as exc:
                raise AcceptanceError(f"review page is invalid: {item['path']}") from exc
            if size != (item["width"], item["height"]):
                raise AcceptanceError(f"review page dimensions changed: {item['path']}")
    if require_current:
        _assert_candidate_current(manifest, phase="validation")
    return manifest


def _assert_loaded_tool_current(*, phase: str) -> None:
    if _sha256(Path(__file__).resolve()) != LOADED_TOOL_SHA256:
        raise AcceptanceError(f"acceptance tool changed {phase}")


def _assert_candidate_current(
    manifest: dict[str, Any], *, phase: str,
) -> dict[str, Any]:
    _assert_loaded_tool_current(phase=phase)
    identity = _source_identity()
    if manifest["source"]["input_hashes"] != identity["input_hashes"]:
        raise AcceptanceError(f"candidate source inputs changed {phase}")
    if manifest["environment"] != _environment():
        raise AcceptanceError(f"candidate environment changed {phase}")
    return identity


@contextlib.contextmanager
def _lease(path: Path, *, blocking: bool = True, create_parent: bool = True):
    if create_parent:
        path.parent.mkdir(parents=True, exist_ok=True)
    elif not path.parent.is_dir() or path.parent.is_symlink():
        raise AcceptanceError(f"lease parent is unsafe: {path.parent}")
    flags = os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags, 0o600)
    except OSError as exc:
        raise AcceptanceError(f"cannot open lease safely: {path}") from exc
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise AcceptanceError(f"lease is not a regular file: {path}")
        flags = fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB)
        try:
            fcntl.flock(fd, flags)
        except BlockingIOError as exc:
            raise LeaseBusy(f"active lease: {path.parent.name}") from exc
        try:
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)


def _declared_layouts() -> dict[str, Any]:
    return {
        "ladder": {
            "preset": "netball-ladder-v1",
            "css_class": "declared-ladder",
        },
        "schedule": {
            "css_class": "declared-schedule",
            "columns": [
                {"name": "Time", "width": 10},
                {"name": "Court", "width": 9},
                {"name": "Home", "width": 30},
                {"name": "Away", "width": 30},
                {"name": "Date", "width": 15},
            ],
        },
    }


def _case_source(case: AcceptanceCase, *, fixture: Path = SOURCE) -> str:
    raw = fixture.read_text(encoding="utf-8")
    if not raw.startswith("---\n"):
        raise AcceptanceError("visual fixture has no YAML front matter")
    try:
        front, body = raw[4:].split("\n---\n", 1)
        metadata = yaml.safe_load(front) or {}
    except (ValueError, yaml.YAMLError) as exc:
        raise AcceptanceError("visual fixture front matter is invalid") from exc
    if not isinstance(metadata, dict):
        raise AcceptanceError("visual fixture front matter must be an object")
    metadata.update(
        theme=case.theme,
        orientation=case.orientation,
        table_widths=case.table_widths,
    )
    if case.page_width_em is not None:
        metadata["page_width_em"] = case.page_width_em
    if case.declared:
        metadata["tables"] = _declared_layouts()
    else:
        metadata.pop("tables", None)
    front = yaml.safe_dump(metadata, default_flow_style=False, sort_keys=False)
    return f"---\n{front}---\n\n{body.rstrip()}\n"


def _width_activation(html: str) -> dict[str, bool]:
    """Record whether each stable fixture table received a colgroup.

    Geometry alone cannot prove that the width engine ran: browser auto-layout
    can coincidentally make paired columns equal.  Keep this source-level
    witness beside the rendered measurements so the existing geometry checks
    fail closed when a declared or automatic layout silently skips a table.
    """
    activation = {}
    for table_id in (
        "ladder-primary", "ladder-secondary", "schedule-morning",
        "schedule-evening",
    ):
        table = re.search(
            rf'<table\b(?=[^>]*\bid\s*=\s*(["\']){re.escape(table_id)}\1)'
            r'[^>]*>.*?</table\s*>',
            html,
            flags=re.DOTALL | re.IGNORECASE,
        )
        activation[table_id] = bool(
            table and re.search(r'<colgroup\b', table.group(0), re.IGNORECASE)
        )
    return activation


def _walk_boxes(box) -> Iterable[Any]:
    yield box
    for child in box.all_children():
        yield from _walk_boxes(child)


def _box_rect(box) -> dict[str, float]:
    width = box.border_width() if hasattr(box, "border_width") else box.width
    height = box.border_height() if hasattr(box, "border_height") else box.height
    x = box.border_box_x() if hasattr(box, "border_box_x") else box.position_x
    y = box.border_box_y() if hasattr(box, "border_box_y") else box.position_y
    return {
        "x": round(float(x), 4),
        "y": round(float(y), 4),
        "width": round(float(width), 4),
        "height": round(float(height), 4),
    }


def _element_text(box) -> str:
    element = getattr(box, "element", None)
    if element is None:
        return ""
    return " ".join("".join(element.itertext()).split())


def measure_document(document) -> dict[str, Any]:
    """Extract stable page/table/cell measurements from a Weasy Document."""
    pages: list[dict[str, Any]] = []
    tables: dict[str, list[dict[str, Any]]] = {}
    for page_number, page in enumerate(document.pages, 1):
        page_record = {
            "page": page_number,
            "width": round(float(page.width), 4),
            "height": round(float(page.height), 4),
        }
        pages.append(page_record)
        for box in _walk_boxes(page._page_box):
            if box.__class__.__name__ != "TableBox":
                continue
            element = getattr(box, "element", None)
            table_id = element.get("id") if element is not None else None
            if not table_id:
                continue
            rows = []
            cells = []
            for nested in _walk_boxes(box):
                if nested.__class__.__name__ == "TableRowBox":
                    row_cells = [
                        child for child in nested.all_children()
                        if child.__class__.__name__ == "TableCellBox"
                    ]
                    if row_cells:
                        rows.append([_box_rect(cell) for cell in row_cells])
                if nested.__class__.__name__ == "TableCellBox":
                    line_count = sum(
                        1 for child in _walk_boxes(nested)
                        if child.__class__.__name__ == "LineBox"
                    )
                    cells.append({
                        "text": _element_text(nested),
                        "lines": line_count,
                        **_box_rect(nested),
                    })
            tables.setdefault(table_id, []).append({
                "page": page_number,
                **_box_rect(box),
                "rows": rows,
                "cells": cells,
            })
    return {"pages": pages, "tables": tables}


def _check(condition: bool, check_id: str, detail: str,
           measurements: dict[str, Any] | None = None) -> CheckResult:
    return CheckResult(
        check_id,
        "passed" if condition else "failed",
        detail,
        measurements or {},
    )


def check_measurements(measurements: dict[str, Any], case: AcceptanceCase
                       ) -> list[CheckResult]:
    pages = measurements["pages"]
    tables = measurements["tables"]
    width_activation = measurements.get("width_activation", {})
    expected_ids = {
        "ladder-primary", "ladder-secondary", "schedule-morning",
        "schedule-evening", "summary-risk", "prose-table",
        "semantic-states", "overwide-table",
    }
    results = [
        _check(
            expected_ids <= set(tables),
            "tables-present",
            f"expected stable table ids for {case.case_id}",
            {"missing": sorted(expected_ids - set(tables))},
        )
    ]
    landscape = all(page["width"] > page["height"] for page in pages)
    results.append(_check(
        landscape == (case.orientation == "landscape"),
        "orientation",
        f"{case.case_id} physical page orientation",
        {"pages": pages},
    ))

    overflow = []
    for table_id, fragments in tables.items():
        for fragment in fragments:
            page = pages[fragment["page"] - 1]
            if (
                fragment["x"] < -GEOMETRY_TOLERANCE
                or fragment["y"] < -GEOMETRY_TOLERANCE
                or fragment["x"] + fragment["width"]
                > page["width"] + GEOMETRY_TOLERANCE
                or fragment["y"] + fragment["height"]
                > page["height"] + GEOMETRY_TOLERANCE
            ):
                overflow.append({"table": table_id, **fragment})
    results.append(_check(
        not overflow, "page-overflow", "all table fragments remain on page",
        {"overflow": overflow},
    ))

    escaped_cells = []
    boundary_drift = []
    for table_id, fragments in tables.items():
        for fragment in fragments:
            left, top = fragment["x"], fragment["y"]
            right = left + fragment["width"]
            bottom = top + fragment["height"]
            for cell in fragment["cells"]:
                if not all(key in cell for key in ("x", "y", "width", "height")):
                    escaped_cells.append({"table": table_id, "cell": cell})
                    continue
                if (
                    cell["x"] < left - GEOMETRY_TOLERANCE
                    or cell["y"] < top - GEOMETRY_TOLERANCE
                    or cell["x"] + cell["width"] > right + GEOMETRY_TOLERANCE
                    or cell["y"] + cell["height"] > bottom + GEOMETRY_TOLERANCE
                ):
                    escaped_cells.append({"table": table_id, "cell": cell})
            rows = fragment["rows"]
            if rows:
                reference = [(cell["x"], cell["width"]) for cell in rows[0]]
                for row_number, row in enumerate(rows[1:], 2):
                    current = [(cell["x"], cell["width"]) for cell in row]
                    if len(current) != len(reference) or any(
                        not math.isclose(a, b, abs_tol=GEOMETRY_TOLERANCE)
                        for pair_a, pair_b in zip(reference, current)
                        for a, b in zip(pair_a, pair_b)
                    ):
                        boundary_drift.append({
                            "table": table_id, "row": row_number,
                            "expected": reference, "actual": current,
                        })
    results.extend((
        _check(
            not escaped_cells, "cell-containment",
            "all measured cells remain inside their table fragment",
            {"escaped": escaped_cells},
        ),
        _check(
            not boundary_drift, "column-boundaries",
            "column boundaries remain stable through every row",
            {"drift": boundary_drift},
        ),
    ))

    def first_widths(table_id: str) -> list[float]:
        for fragment in tables.get(table_id, []):
            if len(fragment["rows"]) > 1:
                return [cell["width"] for cell in fragment["rows"][1]]
        return []

    for left, right, prefix, indexes in (
        # GF/GA share one stat floor inside each ladder. Other stat headers
        # can legitimately raise their own floor, and the Team flex column
        # absorbs the different fixed totals.
        ("ladder-primary", "ladder-secondary", "ladder", (5, 6)),
        # Home/Away are document-wide identities; Date legitimately widens
        # for the ISO values in the evening fixture.
        ("schedule-morning", "schedule-evening", "schedule", (2, 3)),
    ):
        a, b = first_widths(left), first_widths(right)
        complete = len(a) > max(indexes) and len(b) > max(indexes)
        selected = (
            [a[index] for index in indexes] + [b[index] for index in indexes]
            if complete else []
        )
        if not complete:
            equal = False
        elif prefix == "ladder":
            equal = (
                math.isclose(a[indexes[0]], a[indexes[1]],
                             abs_tol=GEOMETRY_TOLERANCE)
                and math.isclose(b[indexes[0]], b[indexes[1]],
                                 abs_tol=GEOMETRY_TOLERANCE)
            )
        else:
            equal = all(
                math.isclose(selected[0], value,
                             abs_tol=GEOMETRY_TOLERANCE)
                for value in selected[1:]
            )
        width_sharing_applicable = case.table_widths and case.page_width_em is None
        activation_ok = (
            not case.table_widths
            or all(width_activation.get(table_id) for table_id in (left, right))
        )
        if not width_sharing_applicable:
            # Legacy mode deliberately delegates content-based widths to
            # WeasyPrint. A custom narrow budget can also scale each table by
            # its own fixed-width total. Both remain visually covered but have
            # no cross-table shared-width invariant to assert.
            equal = activation_ok
        else:
            equal = equal and activation_ok
        results.append(_check(
            equal,
            f"shared-{prefix}-widths",
            (
                f"{left} and {right} activated the width engine and share "
                "rendered column widths"
                if width_sharing_applicable
                else (
                    "shared-width invariant is not applicable; expected width "
                    "engine activation was still verified"
                    if case.table_widths else
                    "shared-width invariant and activation are disabled"
                )
            ),
            {
                left: a,
                right: b,
                "activation": {
                    left: bool(width_activation.get(left)),
                    right: bool(width_activation.get(right)),
                },
            },
        ))

    declared_widths = first_widths("ladder-primary")
    # Frozen v1 contract. Keeping the requested weights independent of the
    # rendered measurements makes catalog drift visible to this acceptance
    # check rather than teaching the assertion to accept its own input.
    declared_expected = [24, 6, 6, 6, 6, 8, 8, 10]
    declared_ok = True
    if case.declared:
        if len(declared_widths) != len(declared_expected):
            declared_ok = False
        else:
            rendered_total = sum(declared_widths)
            requested_total = sum(declared_expected)
            declared_ok = all(
                math.isclose(
                    width / rendered_total,
                    requested / requested_total,
                    # WeasyPrint's auto layout honours the declared colgroup
                    # while still expanding cells to their minimum content.
                    # A 2.5-point ratio tolerance catches drift without
                    # pretending the rendered result is mathematically exact.
                    abs_tol=0.025,
                )
                for width, requested in zip(declared_widths, declared_expected)
            )
    results.append(_check(
        declared_ok,
        "declared-proportions",
        "declared ladder columns retain requested proportions",
        {"actual": declared_widths, "requested": declared_expected},
    ))

    prose_cells = [
        cell for fragment in tables.get("prose-table", [])
        for cell in fragment["cells"]
    ]
    sentinel = next(
        (cell for cell in prose_cells if cell["text"] == "SingleLineSentinel"),
        None,
    )
    wrapped = [
        cell for cell in prose_cells
        if cell["text"].startswith("This deliberately longer")
        or cell["text"].startswith("https://example.invalid")
    ]
    results.extend((
        _check(
            bool(sentinel and sentinel["lines"] == 1),
            "single-line-sentinel",
            "known short sentinel stays on one line",
            {"cell": sentinel},
        ),
        _check(
            len(wrapped) == 2 and all(
                cell["lines"] >= (1 if case.orientation == "landscape" else 2)
                for cell in wrapped
            ),
            "wrap-sentinels",
            (
                "wide landscape cells remain legible without forced wrapping"
                if case.orientation == "landscape"
                else "prose and long token wrap within their cells"
            ),
            {"cells": wrapped},
        ),
    ))
    return results


def _run_checked(args: list[str], *, timeout: float, context: str,
                 cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    try:
        process = subprocess.Popen(
            args, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            start_new_session=True,
        )
    except FileNotFoundError as exc:
        raise AcceptanceError(f"{context}: executable not found: {args[0]}") from exc
    assert process.stdout is not None and process.stderr is not None
    streams = {process.stdout: "stdout", process.stderr: "stderr"}
    buffers = {"stdout": bytearray(), "stderr": bytearray()}
    selector = None

    def terminate() -> None:
        if process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            except (AttributeError, PermissionError):
                if process.poll() is None:
                    process.kill()
        with contextlib.suppress(OSError):
            process.wait()

    try:
        selector = selectors.DefaultSelector()
        for stream, name in streams.items():
            selector.register(stream, selectors.EVENT_READ, name)
        deadline = time.monotonic() + max(timeout, 0.001)
        while selector.get_map():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise AcceptanceError(f"{context}: timed out after {timeout:.1f}s")
            events = selector.select(min(remaining, 0.1))
            for key, _ in events:
                chunk = os.read(key.fileobj.fileno(), 64 * 1024)
                if not chunk:
                    selector.unregister(key.fileobj)
                    key.fileobj.close()
                    continue
                name = key.data
                buffers[name].extend(chunk)
                if len(buffers[name]) > MAX_CAPTURE_BYTES:
                    sizes = {key: len(value) for key, value in buffers.items()}
                    raise AcceptanceError(
                        f"{context}: subprocess output exceeded "
                        f"{MAX_CAPTURE_BYTES} bytes: {sizes}"
                    )
        try:
            returncode = process.wait(
                timeout=max(0.0, deadline - time.monotonic()),
            )
        except subprocess.TimeoutExpired as exc:
            raise AcceptanceError(
                f"{context}: timed out after {timeout:.1f}s"
            ) from exc
    except OSError as exc:
        terminate()
        raise AcceptanceError(f"{context}: subprocess I/O failed") from exc
    except BaseException:
        terminate()
        raise
    finally:
        for stream in streams:
            with contextlib.suppress(OSError):
                stream.close()
        if selector is not None:
            selector.close()
    stdout = buffers["stdout"].decode("utf-8", errors="replace")
    stderr = buffers["stderr"].decode("utf-8", errors="replace")
    result = subprocess.CompletedProcess(args, returncode, stdout, stderr)
    if result.returncode != 0:
        diagnostic = result.stderr[-MAX_STDERR_BYTES:]
        raise AcceptanceError(
            f"{context}: exited {result.returncode}: {diagnostic.strip()}"
        )
    return result


def _pdf_semantic_evidence(
    pdf: Path, *, timeout: float,
) -> tuple[list[CheckResult], str, str]:
    info = _run_checked(
        ["pdfinfo", "-struct-text", str(pdf)], timeout=timeout,
        context=f"{pdf.stem}: pdfinfo structure",
    ).stdout
    text = _run_checked(
        ["pdftotext", "-layout", str(pdf), "-"], timeout=timeout,
        context=f"{pdf.stem}: pdftotext",
    ).stdout
    tags = {tag: bool(re.search(rf"\b{tag}\b", info)) for tag in (
        "Document", "Table", "Caption", "THead", "TBody", "TR", "TH", "TD"
    )}
    header_associations = len(re.findall(r"/Headers\s*\[", info))
    sentinels = ["Primary synthetic ladder", "North Comets", "Prose wrapping sentinels"]
    positions = [text.find(value) for value in sentinels]
    ordered = all(pos >= 0 for pos in positions) and positions == sorted(positions)
    tagged_positions = [info.find(value) for value in sentinels]
    tagged_ordered = (
        all(pos >= 0 for pos in tagged_positions)
        and tagged_positions == sorted(tagged_positions)
    )
    table_position = info.find("Table")
    caption_position = info.find("Caption", table_position + 1)
    head_position = info.find("THead", table_position + 1)
    caption_owned = 0 <= table_position < caption_position < head_position
    caption_has_text = _structure_role_owns_text(
        info, "Caption", "Primary synthetic ladder",
    )
    checks = [
        _check(all(tags.values()), "pdf-table-tags", "PDF structure has table roles", tags),
        _check(caption_has_text, "pdf-caption", "caption is in tag tree"),
        _check(
            caption_owned, "pdf-caption-owner",
            "caption remains attached to its table before the table head",
            {"table": table_position, "caption": caption_position, "head": head_position},
        ),
        _check(
            header_associations >= 12,
            "pdf-header-associations",
            "representative data cells retain tagged header associations",
            {"association_count": header_associations},
        ),
        _check(
            tagged_ordered, "pdf-tagged-order",
            "tagged-tree sentinels preserve assistive reading order",
            {"sentinels": sentinels, "positions": tagged_positions},
        ),
        _check(ordered, "pdf-content-order", "independent extracted sentinel order", {
            "sentinels": sentinels, "positions": positions,
        }),
    ]
    return checks, info, text


def _structure_role_owns_text(info: str, role: str, text: str) -> bool:
    lines = info.splitlines()
    for index, line in enumerate(lines):
        stripped = line.lstrip()
        if not stripped or stripped.split(maxsplit=1)[0] != role:
            continue
        role_indent = len(line) - len(stripped)
        for descendant in lines[index + 1:]:
            descendant_text = descendant.lstrip()
            if not descendant_text:
                continue
            if len(descendant) - len(descendant_text) <= role_indent:
                break
            if text in descendant_text:
                return True
    return False


def _pdf_semantic_checks(
    pdf: Path, *, timeout: float,
) -> tuple[list[CheckResult], str]:
    checks, info, _ = _pdf_semantic_evidence(pdf, timeout=timeout)
    return checks, info


def _canonical_structure(info: str) -> str:
    identifiers: dict[str, str] = {}

    def replace(match: re.Match[str]) -> str:
        raw = match.group(0)
        return identifiers.setdefault(raw, f"ID{len(identifiers) + 1}")

    return re.sub(r"(?<=[<(])\d+(?=[>)])", replace, info)


def _worker(request_path: Path, result_path: Path) -> int:
    request = json.loads(request_path.read_text(encoding="utf-8"))
    python_root = Path(request["python_root"])
    sys.path.insert(0, str(python_root))
    case = AcceptanceCase(**request["case"])
    source = Path(request["source"])
    pdf = Path(request["pdf"])
    from pdf.render import _prepare_render, _render_document

    started = time.monotonic()
    prepared = _prepare_render(source, base_url=source.parent.as_uri() + "/")
    document = _render_document(prepared)
    measurements = measure_document(document)
    measurements["width_activation"] = _width_activation(prepared.html)
    checks = check_measurements(measurements, case)
    if any(check.status != "passed" for check in checks):
        failed = [check.check_id for check in checks if check.status != "passed"]
        raise AcceptanceError(f"{case.case_id}: geometry checks failed: {failed}")
    document.write_pdf(pdf, pdf_variant="pdf/ua-1")
    payload = {
        "case_id": case.case_id,
        "pdf": pdf.name,
        "pdf_bytes": pdf.stat().st_size,
        "pdf_sha256": _sha256(pdf),
        "measurements": measurements,
        "checks": [dataclasses.asdict(check) for check in checks],
        "render_seconds": round(time.monotonic() - started, 4),
    }
    _write_json_atomic(result_path, payload)
    return 0


def _run_worker(
    case: AcceptanceCase, case_dir: Path, *, timeout: float,
    fixture: Path = SOURCE, python_root: Path = ROOT,
) -> dict[str, Any]:
    source = case_dir / "source.md"
    pdf = case_dir / f"{case.case_id}.pdf"
    request = case_dir / "worker-request.json"
    result_path = case_dir / "worker-result.json"
    source.write_text(_case_source(case, fixture=fixture), encoding="utf-8")
    _write_json_atomic(request, {
        "case": dataclasses.asdict(case), "source": str(source), "pdf": str(pdf),
        "python_root": str(python_root),
    })
    worker_script = python_root / Path(__file__).resolve().relative_to(ROOT)
    process = _run_checked(
        [sys.executable, str(worker_script), "_worker", str(request), str(result_path)],
        timeout=timeout,
        context=f"{case.case_id}: render worker",
        cwd=ROOT,
    )
    if not result_path.is_file():
        raise AcceptanceError(f"{case.case_id}: worker returned no result")
    result = _read_json_bounded(
        result_path, context=f"{case.case_id}: worker result",
        max_bytes=MAX_WORKER_RESULT_BYTES,
    )
    if not isinstance(result, dict):
        raise AcceptanceError(f"{case.case_id}: worker result must be an object")
    expected_keys = {
        "case_id", "pdf", "pdf_bytes", "pdf_sha256", "measurements",
        "checks", "render_seconds",
    }
    if set(result) != expected_keys:
        raise AcceptanceError(f"{case.case_id}: worker result schema mismatch")
    if result.get("case_id") != case.case_id or result.get("pdf") != pdf.name:
        raise AcceptanceError(f"{case.case_id}: worker result identity mismatch")
    measurements = result.get("measurements")
    pages = measurements.get("pages") if isinstance(measurements, dict) else None
    if not isinstance(pages, list) or not 1 <= len(pages) <= MAX_PAGES_PER_CASE:
        raise AcceptanceError(f"{case.case_id}: worker measurements are invalid")
    for number, page in enumerate(pages, 1):
        if (
            not isinstance(page, dict)
            or page.get("page") != number
            or any(
                not isinstance(page.get(field), (int, float))
                or isinstance(page.get(field), bool)
                or not math.isfinite(page[field])
                or page[field] <= 0
                for field in ("width", "height")
            )
        ):
            raise AcceptanceError(
                f"{case.case_id}: worker page measurement {number} is invalid"
            )
    checks = result.get("checks")
    if (
        not isinstance(checks, list)
        or [item.get("check_id") for item in checks if isinstance(item, dict)]
        != list(GEOMETRY_CHECK_IDS)
        or any(
            not isinstance(item, dict) or item.get("status") != "passed"
            for item in checks
        )
    ):
        raise AcceptanceError(f"{case.case_id}: worker checks are invalid")
    render_seconds = result.get("render_seconds")
    if (
        not isinstance(render_seconds, (int, float))
        or isinstance(render_seconds, bool)
        or not math.isfinite(render_seconds)
        or render_seconds < 0
    ):
        raise AcceptanceError(f"{case.case_id}: worker timing is invalid")
    if (
        not isinstance(result.get("pdf_bytes"), int)
        or isinstance(result.get("pdf_bytes"), bool)
        or result["pdf_bytes"] <= 0
        or result["pdf_bytes"] > MAX_PDF_BYTES
        or not _is_sha256(result.get("pdf_sha256"))
    ):
        raise AcceptanceError(f"{case.case_id}: worker PDF record is invalid")
    digest, size = _hash_regular_file_bounded(
        pdf, context=f"{case.case_id}: worker PDF", max_bytes=MAX_PDF_BYTES,
    )
    if result.get("pdf_sha256") != digest or result.get("pdf_bytes") != size:
        raise AcceptanceError(f"{case.case_id}: worker PDF mismatch")
    if process.stdout:
        result["worker_stdout"] = process.stdout[-MAX_STDERR_BYTES:]
    return result


def _rasterize(case: AcceptanceCase, case_dir: Path, *, expected_pages: int,
               pixel_budget: int, timeout: float
               ) -> tuple[list[Path], float, int]:
    pdf = case_dir / f"{case.case_id}.pdf"
    if not 1 <= expected_pages <= MAX_PAGES_PER_CASE:
        raise AcceptanceError(
            f"{case.case_id}: expected page count is outside 1-{MAX_PAGES_PER_CASE}"
        )
    raster_dir = Path(tempfile.mkdtemp(prefix=".raster-", dir=case_dir))
    prefix = raster_dir / "page"
    started = time.monotonic()
    try:
        _run_checked(
            [
                "pdftoppm", "-png", "-r", str(RASTER_DPI),
                "-f", "1", "-l", str(expected_pages), str(pdf), str(prefix),
            ],
            timeout=timeout,
            context=f"{case.case_id}: raster",
        )
        numbered_pages = []
        for page in raster_dir.glob("page-*.png"):
            match = re.fullmatch(r"page-(\d+)\.png", page.name)
            if not match:
                raise AcceptanceError(f"{case.case_id}: unexpected raster name {page.name}")
            numbered_pages.append((int(match.group(1)), page))
        numbered_pages.sort(key=lambda item: item[0])
        pages = [page for _, page in numbered_pages]
        numbers = [number for number, _ in numbered_pages]
        expected_numbers = list(range(1, expected_pages + 1))
        if numbers != expected_numbers:
            raise AcceptanceError(
                f"{case.case_id}: incomplete raster pages; expected {expected_numbers}, "
                f"got {numbers}"
            )
        from PIL import Image
        pixels = 0
        try:
            for page in pages:
                with Image.open(page) as image:
                    image.verify()
                with Image.open(page) as image:
                    pixels += image.width * image.height
        except (OSError, ValueError) as exc:
            raise AcceptanceError(f"{case.case_id}: invalid raster page") from exc
        if pixels > pixel_budget:
            raise AcceptanceError(
                f"{case.case_id}: raster pixels {pixels} exceed remaining budget "
                f"{pixel_budget}"
            )
        installed = []
        for number, page in numbered_pages:
            destination = case_dir / f"page-{number}.png"
            os.replace(page, destination)
            installed.append(destination)
        return installed, round(time.monotonic() - started, 4), pixels
    finally:
        shutil.rmtree(raster_dir, ignore_errors=True)


def _contact_sheet(case: AcceptanceCase, pages: list[Path], output: Path) -> None:
    from PIL import Image, ImageDraw

    thumbs = []
    for path in pages:
        with Image.open(path) as original:
            image = original.convert("RGB")
            height = round(image.height * THUMB_WIDTH / image.width)
            image.thumbnail((THUMB_WIDTH, height))
            thumbs.append(image.copy())
    label_height = 28
    cell_height = max(image.height for image in thumbs) + label_height
    rows = math.ceil(len(thumbs) / SHEET_COLUMNS)
    sheet = Image.new("RGB", (THUMB_WIDTH * SHEET_COLUMNS, cell_height * rows), "white")
    draw = ImageDraw.Draw(sheet)
    for index, image in enumerate(thumbs):
        x = (index % SHEET_COLUMNS) * THUMB_WIDTH
        y = (index // SHEET_COLUMNS) * cell_height
        sheet.paste(image, (x, y + label_height))
        draw.text((x + 8, y + 7), f"{case.case_id} - page {index + 1}", fill="black")
    output.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output, format="PNG", optimize=True)


def _input_files() -> list[Path]:
    paths = [
        SOURCE,
        Path(__file__).resolve(),
        ROOT / "pyproject.toml",
        ROOT / "pdf" / "default_widths.yml",
        ROOT / "pdf" / "table_presets.yml",
    ]
    paths.extend(sorted((ROOT / "pdf").glob("*.py")))
    paths.extend(sorted((ROOT / "pdf" / "styles").glob("*.css")))
    paths.extend(sorted((ROOT / "pdf" / "fonts").glob("*")))
    return [path for path in paths if path.is_file()]


def _snapshot_inputs(candidate: Path, identity: dict[str, Any]) -> Path:
    snapshot = candidate / "input-snapshot"
    snapshot.mkdir()
    for raw_path, digest in identity["input_hashes"].items():
        source = _contained_file(ROOT, raw_path, suffixes={
            ".md", ".py", ".toml", ".yml", ".css", ".ttf", ".otf",
        })
        destination = snapshot.joinpath(*PurePosixPath(raw_path).parts)
        destination.parent.mkdir(parents=True, exist_ok=True)
        _copy_verified(source, destination, {
            "path": raw_path,
            "bytes": source.stat().st_size,
            "sha256": digest,
        })
    copied = {
        path.relative_to(snapshot).as_posix(): _sha256(path)
        for path in snapshot.rglob("*") if path.is_file()
    }
    if copied != identity["input_hashes"]:
        raise AcceptanceError("render input snapshot does not match source identity")
    return snapshot


def _artifact_record(path: Path, root: Path, *, kind: str) -> dict[str, Any]:
    record = {
        "path": path.relative_to(root).as_posix(),
        "kind": kind,
        "bytes": path.stat().st_size,
        "sha256": _sha256(path),
    }
    if kind == "page":
        from PIL import Image
        with Image.open(path) as image:
            record.update(width=image.width, height=image.height)
    return record


def _source_identity() -> dict[str, Any]:
    inputs = {
        path.relative_to(ROOT).as_posix(): _sha256(path)
        for path in _input_files()
    }
    digest = _input_digest(inputs)
    git = _run_checked(
        ["git", "rev-parse", "HEAD"], timeout=10, context="git revision", cwd=ROOT
    ).stdout.strip()
    status = _run_checked(
        ["git", "status", "--porcelain", "--untracked-files=all"], timeout=10,
        context="git status", cwd=ROOT,
    ).stdout.splitlines()
    dirty_names = {line[3:] for line in status if len(line) > 3}
    input_dirty = sorted(name for name in inputs if name in dirty_names)
    return {
        "digest": digest,
        "git_base": git,
        "input_hashes": inputs,
        "dirty_render_inputs": input_dirty,
        "unrelated_worktree_dirty": any(name not in inputs for name in dirty_names),
    }


def _environment() -> dict[str, Any]:
    packages = {
        name: importlib.metadata.version(name) for name in RENDER_DEPENDENCIES
    }
    poppler_result = _run_checked(
        ["pdfinfo", "-v"], timeout=10, context="pdfinfo version"
    )
    poppler_lines = [
        line for output in (poppler_result.stderr, poppler_result.stdout)
        for line in output.splitlines() if line.strip()
    ]
    if not poppler_lines:
        raise AcceptanceError("pdfinfo version output is empty")
    poppler = poppler_lines[0]
    pango = _run_checked(
        ["pkg-config", "--modversion", "pango"], timeout=10,
        context="Pango version",
    ).stdout.strip()
    return {
        "python": platform.python_version(),
        "packages": packages,
        "poppler": poppler,
        "pango": pango,
        "platform": platform.platform(),
        "machine": platform.machine(),
        "raster": {
            "format": "PNG", "color": "RGB", "dpi": RASTER_DPI,
            "thumbnail_width_px": THUMB_WIDTH, "sheet_columns": SHEET_COLUMNS,
        },
    }


def generate() -> Path:
    _assert_loaded_tool_current(phase="after the coordinator loaded")
    _prepare_candidate_root()
    with _lease(OUTPUT_ROOT / "candidate-registry.lock"):
        _prepare_candidate_root()
        identity = _source_identity()
        base_id = (
            time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
            + "-" + identity["digest"][:12]
        )
        with _directory_fd(CANDIDATE_ROOT, label="candidate root") as (root_fd, root_id):
            candidate_id = f"{base_id}-{uuid.uuid4().hex[:8]}"
            try:
                os.mkdir(candidate_id, mode=0o700, dir_fd=root_fd)
            except OSError as exc:
                raise AcceptanceError("cannot create candidate safely") from exc
            logical_candidate = CANDIDATE_ROOT / candidate_id
            generation_started = False
            generation_completed = False
            try:
                if _directory_identity(CANDIDATE_ROOT) != root_id:
                    raise AcceptanceError("candidate root changed during creation")
                with _directory_fd_at(
                    root_fd, candidate_id, label="candidate directory",
                ) as (_, candidate):
                    review_baseline = _active_digest()
                    deadline = time.monotonic() + MATRIX_TIMEOUT
                    snapshot = _snapshot_inputs(candidate, identity)
                    fixture = snapshot / SOURCE.relative_to(ROOT)
                    with _lease(candidate / ".lease", create_parent=False):
                        generation_started = True
                        _generate_locked(
                            candidate, candidate_id=candidate_id, identity=identity,
                            review_baseline=review_baseline, deadline=deadline,
                            snapshot=snapshot, fixture=fixture,
                            display_candidate=logical_candidate,
                        )
                        generation_completed = True
                    if _directory_identity(CANDIDATE_ROOT) != root_id:
                        raise AcceptanceError("candidate root changed during generation")
                    return logical_candidate
            except BaseException as original:
                if not generation_started or generation_completed:
                    try:
                        metadata = os.stat(
                            candidate_id, dir_fd=root_fd, follow_symlinks=False,
                        )
                        if stat.S_ISDIR(metadata.st_mode):
                            shutil.rmtree(candidate_id, dir_fd=root_fd)
                    except FileNotFoundError:
                        pass
                    except OSError as cleanup_error:
                        if hasattr(original, "add_note"):
                            original.add_note(
                                f"failed to clean incomplete candidate: {cleanup_error}"
                            )
                raise


def _generate_locked(
    candidate: Path, *, candidate_id: str, identity: dict[str, Any],
    review_baseline: str | None, deadline: float, snapshot: Path, fixture: Path,
    display_candidate: Path | None = None,
) -> Path:
    cases_out = []
    total_pixels = 0
    promotable = []
    reviewed = []
    try:
        for case in acceptance_cases():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise AcceptanceError("overall matrix deadline exhausted")
            case_dir = candidate / "cases" / case.case_id
            case_dir.mkdir(parents=True)
            result = _run_worker(
                case, case_dir, timeout=min(CASE_TIMEOUT, remaining),
                fixture=fixture, python_root=snapshot,
            )
            _pdf_object_evidence(case_dir / result["pdf"])
            semantic, _ = _pdf_semantic_checks(
                case_dir / result["pdf"],
                timeout=min(30, deadline - time.monotonic()),
            )
            if any(check.status != "passed" for check in semantic):
                failed = [c.check_id for c in semantic if c.status != "passed"]
                raise AcceptanceError(
                    f"{case.case_id}: semantic checks failed: {failed}"
                )
            expected_pages = len(result["measurements"]["pages"])
            projected_pixels = sum(
                math.ceil(page["width"] * RASTER_DPI / 96)
                * math.ceil(page["height"] * RASTER_DPI / 96)
                for page in result["measurements"]["pages"]
            )
            remaining_pixels = MAX_TOTAL_PIXELS - total_pixels
            if projected_pixels > remaining_pixels:
                raise AcceptanceError(
                    f"{case.case_id}: projected raster exceeds remaining pixel budget"
                )
            pages, raster_seconds, case_pixels = _rasterize(
                case, case_dir, expected_pages=expected_pages,
                pixel_budget=remaining_pixels,
                timeout=min(60, deadline - time.monotonic()),
            )
            total_pixels += case_pixels
            sheet = candidate / "contact-sheets" / f"{case.case_id}.png"
            _contact_sheet(case, pages, sheet)
            promotable.append({
                "path": sheet.relative_to(candidate).as_posix(),
                "bytes": sheet.stat().st_size,
                "sha256": _sha256(sheet),
            })
            result.update(
                case=dataclasses.asdict(case),
                pages=[page.relative_to(candidate).as_posix() for page in pages],
                raster_seconds=raster_seconds,
                semantic_checks=[dataclasses.asdict(check) for check in semantic],
            )
            pdf = case_dir / result["pdf"]
            reviewed.append(_artifact_record(pdf, candidate, kind="pdf"))
            reviewed.extend(
                _artifact_record(page, candidate, kind="page") for page in pages
            )
            for transient in (
                case_dir / "source.md", case_dir / "worker-request.json",
                case_dir / "worker-result.json",
            ):
                transient.unlink(missing_ok=True)
            cases_out.append(result)
        shutil.rmtree(snapshot)
        manifest = {
            "schema_version": SCHEMA_VERSION,
            "status": "passed",
            "candidate_id": candidate_id,
            "review_baseline": review_baseline,
            "source": identity,
            "environment": _environment(),
            "limits": {
                "case_timeout_seconds": CASE_TIMEOUT,
                "matrix_timeout_seconds": MATRIX_TIMEOUT,
                "max_pages_per_case": MAX_PAGES_PER_CASE,
                "max_total_pixels": MAX_TOTAL_PIXELS,
                "geometry_tolerance_css_px": GEOMETRY_TOLERANCE,
            },
            "cases": cases_out,
            "total_raster_pixels": total_pixels,
            "review_artifacts": reviewed,
            "promotable_artifacts": promotable,
        }
        manifest_path = candidate / "manifest.json"
        final_identity = _source_identity()
        if (
            final_identity["input_hashes"] != identity["input_hashes"]
            or _sha256(Path(__file__).resolve()) != LOADED_TOOL_SHA256
        ):
            raise AcceptanceError("render inputs changed during acceptance generation")
        _write_json_atomic(manifest_path, manifest)
        validate_candidate(candidate, require_current=True)
    except BaseException as original:
        # Failed candidates retain only compact diagnostics. Raw PDFs and
        # rasters can be large and are never reviewable as passed evidence.
        cleanup_errors = []
        try:
            (candidate / "manifest.json").unlink(missing_ok=True)
        except OSError as exc:
            cleanup_errors.append(f"failed to remove invalid manifest: {exc}")
        for raw_dir in (
            candidate / "cases", candidate / "contact-sheets",
            candidate / "input-snapshot",
        ):
            try:
                if (
                    raw_dir.parent == candidate and raw_dir.exists()
                    and raw_dir.is_dir() and not raw_dir.is_symlink()
                ):
                    shutil.rmtree(raw_dir)
            except OSError as exc:
                cleanup_errors.append(f"failed to clean {raw_dir.name}: {exc}")
        try:
            _write_json_atomic(candidate / "failure.json", {
                "schema_version": SCHEMA_VERSION,
                "status": "failed",
                "candidate_id": candidate_id,
            })
        except OSError as exc:
            cleanup_errors.append(f"failed to write failure marker: {exc}")
        for note in cleanup_errors:
            if hasattr(original, "add_note"):
                original.add_note(note)
        raise
    print(display_candidate or candidate)
    return candidate


def _active_digest() -> str | None:
    try:
        metadata = ACTIVE_POINTER.lstat()
    except FileNotFoundError:
        return None
    if ACTIVE_POINTER.is_symlink() or not stat.S_ISREG(metadata.st_mode):
        raise AcceptanceError("active evidence pointer is unsafe")
    pointer = _read_json_bounded(
        ACTIVE_POINTER, context="active evidence pointer",
        max_bytes=MAX_POINTER_BYTES,
    )
    if not isinstance(pointer, dict) or set(pointer) != {
        "schema_version", "digest", "version", "previous_digest",
    } or pointer.get("schema_version") not in {1, 2, SCHEMA_VERSION}:
        raise AcceptanceError("active evidence pointer schema is invalid")
    digest = pointer.get("digest")
    if not _is_sha256(digest):
        raise AcceptanceError("active evidence pointer has an invalid digest")
    previous = pointer.get("previous_digest")
    if previous is not None and not _is_sha256(previous):
        raise AcceptanceError("active evidence pointer has an invalid previous digest")
    expected_version = f"approved/{digest}"
    if pointer.get("version") != expected_version:
        raise AcceptanceError("active evidence pointer version is inconsistent")
    _prepare_approved_root(create=False)
    version = APPROVED_ROOT / expected_version
    if pointer["schema_version"] == SCHEMA_VERSION:
        _validate_evidence_tree(version)
    else:
        _validate_legacy_evidence_tree(version, digest)
    return digest


def _validate_legacy_evidence_tree(version: Path, digest: str) -> None:
    versions_root = APPROVED_VERSIONS.resolve()
    if version.is_symlink() or not version.is_dir() or version.resolve().parent != versions_root:
        raise AcceptanceError("legacy approved version is unsafe")
    manifest_path = version / "manifest.json"
    manifest = _read_json_bounded(
        manifest_path, context="legacy approved manifest",
        max_bytes=MAX_MANIFEST_BYTES,
    )
    source = manifest.get("source") if isinstance(manifest, dict) else None
    artifacts = manifest.get("promotable_artifacts") if isinstance(manifest, dict) else None
    expected_paths = [f"contact-sheets/{case.case_id}.png" for case in acceptance_cases()]
    if (
        not isinstance(source, dict) or source.get("digest") != digest
        or not isinstance(artifacts, list)
        or [item.get("path") for item in artifacts if isinstance(item, dict)]
        != expected_paths
    ):
        raise AcceptanceError("legacy approved manifest is inconsistent")
    expected_files = {"manifest.json"} | set(expected_paths)
    actual_files = {
        path.relative_to(version).as_posix() for path in version.rglob("*")
        if path.is_file() or path.is_symlink()
    }
    if actual_files != expected_files:
        raise AcceptanceError("legacy approved artifact set is incomplete")
    for item in artifacts:
        if not isinstance(item, dict) or not _is_sha256(item.get("sha256")):
            raise AcceptanceError("legacy approved artifact record is invalid")
        path = _contained_file(version, item["path"], suffixes={".png"})
        if path.stat().st_size != item.get("bytes") or _sha256(path) != item["sha256"]:
            raise AcceptanceError(f"legacy approved artifact mismatch: {item['path']}")


def _copy_verified(source: Path, destination: Path, item: dict[str, Any]) -> None:
    """Copy and hash from one no-follow file descriptor."""
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(source, flags)
    except OSError as exc:
        raise AcceptanceError(f"cannot open artifact safely: {item['path']}") from exc
    digest = hashlib.sha256()
    size = 0
    try:
        metadata = os.fstat(fd)
        if not stat.S_ISREG(metadata.st_mode):
            raise AcceptanceError(f"artifact is not regular: {item['path']}")
        with os.fdopen(fd, "rb", closefd=False) as input_stream:
            with destination.open("xb") as output_stream:
                for chunk in iter(lambda: input_stream.read(1024 * 1024), b""):
                    digest.update(chunk)
                    size += len(chunk)
                    output_stream.write(chunk)
                output_stream.flush()
                os.fsync(output_stream.fileno())
    finally:
        os.close(fd)
    if size != item["bytes"] or digest.hexdigest() != item["sha256"]:
        destination.unlink(missing_ok=True)
        raise AcceptanceError(f"artifact changed during copy: {item['path']}")


def _copy_verified_at(
    source: Path, destination_fd: int, name: str, item: dict[str, Any],
) -> None:
    """Copy one verified regular file into a held destination directory."""
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    source_fd = destination_file_fd = None
    digest = hashlib.sha256()
    size = 0
    try:
        source_fd = os.open(source, flags)
        metadata = os.fstat(source_fd)
        if not stat.S_ISREG(metadata.st_mode):
            raise AcceptanceError(f"artifact is not regular: {item['path']}")
        destination_file_fd = os.open(
            name, os.O_WRONLY | os.O_CREAT | os.O_EXCL
            | getattr(os, "O_NOFOLLOW", 0),
            0o600, dir_fd=destination_fd,
        )
        while True:
            chunk = os.read(source_fd, 1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
            size += len(chunk)
            view = memoryview(chunk)
            while view:
                written = os.write(destination_file_fd, view)
                view = view[written:]
        os.fsync(destination_file_fd)
    except AcceptanceError:
        raise
    except OSError as exc:
        raise AcceptanceError(f"artifact copy failed: {item['path']}") from exc
    finally:
        if source_fd is not None:
            os.close(source_fd)
        if destination_file_fd is not None:
            os.close(destination_file_fd)
    if size != item["bytes"] or digest.hexdigest() != item["sha256"]:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(name, dir_fd=destination_fd)
        raise AcceptanceError(f"artifact changed during copy: {item['path']}")


def _read_json_bounded_at(
    directory_fd: int, name: str, *, context: str, max_bytes: int,
) -> Any:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    try:
        fd = os.open(name, flags, dir_fd=directory_fd)
    except OSError as exc:
        raise AcceptanceError(f"{context} is unreadable") from exc
    try:
        metadata = os.fstat(fd)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > max_bytes:
            raise AcceptanceError(f"{context} is unsafe or oversized")
        data = bytearray()
        while len(data) <= max_bytes:
            chunk = os.read(fd, min(64 * 1024, max_bytes + 1 - len(data)))
            if not chunk:
                break
            data.extend(chunk)
        if len(data) > max_bytes:
            raise AcceptanceError(f"{context} exceeds {max_bytes} bytes")
        return json.loads(data)
    except AcceptanceError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise AcceptanceError(f"{context} is unreadable") from exc
    finally:
        os.close(fd)


def _hash_regular_at(
    directory_fd: int, name: str, *, max_bytes: int, context: str,
) -> tuple[str, int]:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    try:
        fd = os.open(name, flags, dir_fd=directory_fd)
    except OSError as exc:
        raise AcceptanceError(f"{context} is unreadable") from exc
    digest = hashlib.sha256()
    size = 0
    try:
        metadata = os.fstat(fd)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > max_bytes:
            raise AcceptanceError(f"{context} is unsafe or oversized")
        while True:
            chunk = os.read(fd, min(1024 * 1024, max_bytes + 1 - size))
            if not chunk:
                break
            size += len(chunk)
            if size > max_bytes:
                raise AcceptanceError(f"{context} exceeds {max_bytes} bytes")
            digest.update(chunk)
        if size != metadata.st_size:
            raise AcceptanceError(f"{context} changed while being read")
        return digest.hexdigest(), size
    finally:
        os.close(fd)


def _canonical_evidence_manifest(value: dict[str, Any]) -> dict[str, Any]:
    normalized = json.loads(json.dumps(value))
    normalized.pop("candidate_id", None)
    normalized.pop("review_baseline", None)
    for field in ("git_base", "dirty_render_inputs", "unrelated_worktree_dirty"):
        normalized["source"].pop(field, None)
    for record in normalized["cases"]:
        record.pop("render_seconds", None)
        record.pop("raster_seconds", None)
    return normalized


def _validate_evidence_tree_at(
    version_fd: int, version_name: str,
    *, candidate_manifest: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate an approved tree entirely through held directory descriptors."""
    manifest = _validate_manifest_shape(_read_json_bounded_at(
        version_fd, "manifest.json", context="approved version manifest",
        max_bytes=MAX_MANIFEST_BYTES,
    ))
    digest = manifest["source"]["digest"]
    if version_name != digest and not version_name.startswith(f".{digest}."):
        raise AcceptanceError("approved directory does not match source digest")
    if (
        candidate_manifest is not None
        and _canonical_evidence_manifest(manifest)
        != _canonical_evidence_manifest(candidate_manifest)
    ):
        raise AcceptanceError("existing approved version conflicts with candidate evidence")
    artifacts = manifest["promotable_artifacts"]
    expected_names = set()
    for item in artifacts:
        parts = PurePosixPath(item["path"]).parts
        if len(parts) != 2 or parts[0] != "contact-sheets":
            raise AcceptanceError("approved artifact path is invalid")
        expected_names.add(parts[1])
    if set(os.listdir(version_fd)) != {"manifest.json", "contact-sheets"}:
        raise AcceptanceError("approved version artifact set is incomplete or unexpected")
    with _directory_fd_only_at(
        version_fd, "contact-sheets", label="approved contact sheets",
    ) as (contact_fd, _):
        if set(os.listdir(contact_fd)) != expected_names:
            raise AcceptanceError("approved version artifact set is incomplete or unexpected")
        for item in artifacts:
            name = PurePosixPath(item["path"]).name
            digest_value, size = _hash_regular_at(
                contact_fd, name, max_bytes=MAX_IMAGE_BYTES,
                context=f"approved artifact: {item['path']}",
            )
            if size != item["bytes"] or digest_value != item["sha256"]:
                raise AcceptanceError(f"approved artifact mismatch: {item['path']}")
    return manifest


def _remove_directory_at_if_identity(
    parent_fd: int, name: str, identity: tuple[int, int],
) -> None:
    """Remove only the exact directory entry created by this process."""
    try:
        metadata = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except FileNotFoundError:
        return
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or (metadata.st_dev, metadata.st_ino) != identity
    ):
        raise AcceptanceError("staging directory changed before cleanup")
    shutil.rmtree(name, dir_fd=parent_fd)


def _validate_evidence_tree(
    version: Path, *, candidate_manifest: dict[str, Any] | None = None,
) -> dict[str, Any]:
    versions_root = APPROVED_VERSIONS.resolve()
    if version.is_symlink() or not version.is_dir() or version.resolve().parent != versions_root:
        raise AcceptanceError(f"approved version is unsafe: {version}")
    manifest_path = version / "manifest.json"
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise AcceptanceError(f"approved version manifest is unsafe: {version}")
    manifest = _validate_manifest_shape(_read_json_bounded(
        manifest_path, context=f"approved version manifest: {version}",
        max_bytes=MAX_MANIFEST_BYTES,
    ))
    if version.name != manifest["source"]["digest"] and not version.name.startswith(
        f".{manifest['source']['digest']}."
    ):
        raise AcceptanceError("approved directory does not match source digest")
    if candidate_manifest is not None:
        if (
            _canonical_evidence_manifest(manifest)
            != _canonical_evidence_manifest(candidate_manifest)
        ):
            raise AcceptanceError("existing approved version conflicts with candidate evidence")
    expected_files = {"manifest.json"} | {
        item["path"] for item in manifest["promotable_artifacts"]
    }
    actual_files = {
        path.relative_to(version).as_posix() for path in version.rglob("*")
        if path.is_file() or path.is_symlink()
    }
    if actual_files != expected_files:
        raise AcceptanceError("approved version artifact set is incomplete or unexpected")
    for item in manifest["promotable_artifacts"]:
        path = _contained_file(version, item["path"], suffixes={".png"})
        if path.stat().st_size != item["bytes"] or _sha256(path) != item["sha256"]:
            raise AcceptanceError(f"approved artifact mismatch: {item['path']}")
    return manifest


def _fsync_directory_fd(fd: int) -> None:
    os.fsync(fd)


def _attest_candidate(
    candidate: Path, manifest: dict[str, Any], identity: dict[str, Any],
) -> None:
    """Independently bind stored geometry and reviewed pixels to current inputs."""
    reviewed = {item["path"]: item for item in manifest["review_artifacts"]}
    promotable = {item["path"]: item for item in manifest["promotable_artifacts"]}
    deadline = time.monotonic() + MATRIX_TIMEOUT
    total_pixels = 0
    candidate_pixels = 0
    with tempfile.TemporaryDirectory(prefix=".attest-", dir=OUTPUT_ROOT) as raw_root:
        root = Path(raw_root)
        snapshot = _snapshot_inputs(root, identity)
        fixture = snapshot / SOURCE.relative_to(ROOT)
        for case, stored in zip(acceptance_cases(), manifest["cases"]):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise AcceptanceError("promotion attestation deadline exhausted")
            case_dir = root / "cases" / case.case_id
            case_dir.mkdir(parents=True)
            fresh = _run_worker(
                case, case_dir, timeout=min(CASE_TIMEOUT, remaining),
                fixture=fixture, python_root=snapshot,
            )
            if (
                fresh["measurements"] != stored["measurements"]
                or fresh["checks"] != stored["checks"]
            ):
                raise AcceptanceError(
                    f"{case.case_id}: independent geometry attestation differs"
                )
            fresh_pdf = case_dir / fresh["pdf"]
            fresh_objects = _pdf_object_evidence(fresh_pdf)
            semantic, fresh_info, fresh_text = _pdf_semantic_evidence(
                fresh_pdf,
                timeout=min(30, deadline - time.monotonic()),
            )
            fresh_semantic = [dataclasses.asdict(check) for check in semantic]
            if fresh_semantic != stored["semantic_checks"]:
                raise AcceptanceError(
                    f"{case.case_id}: independent semantic attestation differs"
                )
            candidate_pdf = candidate / "cases" / case.case_id / stored["pdf"]
            pdf_relative = f"cases/{case.case_id}/{stored['pdf']}"
            private_case_dir = root / "candidate-copies" / case.case_id
            private_case_dir.mkdir(parents=True)
            private_candidate_pdf = private_case_dir / stored["pdf"]
            _copy_verified(
                candidate_pdf, private_candidate_pdf, reviewed[pdf_relative],
            )
            candidate_objects = _pdf_object_evidence(private_candidate_pdf)
            if (
                candidate_objects["graph_sha256"] != fresh_objects["graph_sha256"]
                or candidate_objects["pages"] != fresh_objects["pages"]
            ):
                raise AcceptanceError(
                    f"{case.case_id}: candidate PDF object graph differs"
                )
            candidate_semantic, candidate_info, candidate_text = _pdf_semantic_evidence(
                private_candidate_pdf,
                timeout=min(30, deadline - time.monotonic()),
            )
            if (
                [dataclasses.asdict(check) for check in candidate_semantic]
                != stored["semantic_checks"]
                or candidate_text != fresh_text
                or _canonical_structure(candidate_info)
                != _canonical_structure(fresh_info)
            ):
                raise AcceptanceError(
                    f"{case.case_id}: candidate PDF attestation differs"
                )
            expected_pages = len(fresh["measurements"]["pages"])
            pages, _, case_pixels = _rasterize(
                case, case_dir, expected_pages=expected_pages,
                pixel_budget=MAX_TOTAL_PIXELS - total_pixels,
                timeout=min(60, deadline - time.monotonic()),
            )
            total_pixels += case_pixels
            candidate_pages, _, candidate_case_pixels = _rasterize(
                case, private_case_dir, expected_pages=expected_pages,
                pixel_budget=MAX_TOTAL_PIXELS - candidate_pixels,
                timeout=min(60, deadline - time.monotonic()),
            )
            candidate_pixels += candidate_case_pixels
            for page, candidate_page in zip(pages, candidate_pages, strict=True):
                relative = f"cases/{case.case_id}/{page.name}"
                if _sha256(page) != reviewed[relative]["sha256"]:
                    raise AcceptanceError(
                        f"{case.case_id}: independent page attestation differs"
                    )
                if _sha256(candidate_page) != _sha256(page):
                    raise AcceptanceError(
                        f"{case.case_id}: candidate PDF pixels differ"
                    )
            sheet = root / "contact-sheets" / f"{case.case_id}.png"
            _contact_sheet(case, pages, sheet)
            sheet_path = f"contact-sheets/{case.case_id}.png"
            if _sha256(sheet) != promotable[sheet_path]["sha256"]:
                raise AcceptanceError(
                    f"{case.case_id}: independent contact sheet differs"
                )


def _ensure_approved_version_at(
    versions_fd: int, digest: str, candidate: Path, manifest: dict[str, Any],
) -> None:
    """Stage or revalidate one immutable version below a held root FD."""
    try:
        existing = os.stat(digest, dir_fd=versions_fd, follow_symlinks=False)
    except FileNotFoundError:
        existing = None
    if existing is not None:
        if not stat.S_ISDIR(existing.st_mode):
            raise AcceptanceError("approved version is unsafe")
        with _directory_fd_only_at(
            versions_fd, digest, label="approved version",
        ) as (version_fd, _):
            _validate_evidence_tree_at(
                version_fd, digest, candidate_manifest=manifest,
            )
        return

    temp_name = f".{digest}.{os.getpid()}.{uuid.uuid4().hex}.tmp"
    os.mkdir(temp_name, mode=0o700, dir_fd=versions_fd)
    temp_identity = None
    try:
        created = os.stat(temp_name, dir_fd=versions_fd, follow_symlinks=False)
        if not stat.S_ISDIR(created.st_mode):
            raise AcceptanceError("approved staging directory is unsafe")
        temp_identity = (created.st_dev, created.st_ino)
        with _directory_fd_only_at(
            versions_fd, temp_name, label="approved staging directory",
        ) as (temp_fd, opened_identity):
            if opened_identity != temp_identity:
                raise AcceptanceError("approved staging directory changed")
            os.mkdir("contact-sheets", mode=0o700, dir_fd=temp_fd)
            with _directory_fd_only_at(
                temp_fd, "contact-sheets",
                label="approved staging contact sheets",
            ) as (contact_fd, _):
                for item in manifest["promotable_artifacts"]:
                    source = _contained_file(
                        candidate, item["path"], suffixes={".png"},
                    )
                    _copy_verified_at(
                        source, contact_fd,
                        PurePosixPath(item["path"]).name, item,
                    )
                _fsync_directory_fd(contact_fd)
            _write_json_atomic_at(temp_fd, "manifest.json", manifest)
            _validate_evidence_tree_at(
                temp_fd, temp_name, candidate_manifest=manifest,
            )
            _fsync_directory_fd(temp_fd)
        os.rename(
            temp_name, digest,
            src_dir_fd=versions_fd, dst_dir_fd=versions_fd,
        )
        _fsync_directory_fd(versions_fd)
    except BaseException as original:
        if temp_identity is None:
            try:
                created = os.stat(
                    temp_name, dir_fd=versions_fd, follow_symlinks=False,
                )
                if stat.S_ISDIR(created.st_mode):
                    temp_identity = (created.st_dev, created.st_ino)
            except OSError as identity_error:
                if hasattr(original, "add_note"):
                    original.add_note(
                        f"cannot identify approved staging tree: {identity_error}"
                    )
        if temp_identity is not None:
            try:
                _remove_directory_at_if_identity(
                    versions_fd, temp_name, temp_identity,
                )
            except (OSError, AcceptanceError) as cleanup_error:
                if hasattr(original, "add_note"):
                    original.add_note(
                        "failed to clean approved staging tree: "
                        f"{cleanup_error}"
                    )
        raise
    with _directory_fd_only_at(
        versions_fd, digest, label="approved version",
    ) as (version_fd, _):
        _validate_evidence_tree_at(
            version_fd, digest, candidate_manifest=manifest,
        )


def _publish_active_pointer_at(approved_fd: int, pointer: dict[str, Any]) -> None:
    _write_json_atomic_at(approved_fd, "active.json", pointer)
    _fsync_directory_fd(approved_fd)


def promote(candidate: Path) -> Path:
    _assert_loaded_tool_current(phase="before promotion")
    _prepare_candidate_root()
    _prepare_approved_root(create=True)
    candidate = _candidate_directory(candidate)
    with _lease(candidate / ".lease", create_parent=False):
        with _lease(OUTPUT_ROOT / "promotion.lock"):
            candidate = _candidate_directory(candidate)
            manifest = validate_candidate(candidate, require_current=True)
            identity = _assert_candidate_current(
                manifest, phase="before attestation",
            )
            _attest_candidate(candidate, manifest, identity)
            _assert_candidate_current(manifest, phase="during attestation")
            digest = manifest["source"]["digest"]
            baseline = _active_digest()
            if manifest["review_baseline"] != baseline:
                raise AcceptanceError(
                    "candidate review baseline is stale; regenerate and review again"
                )
            with _directory_fd(APPROVED_ROOT, label="approved root") as (
                approved_fd, approved_id,
            ), _directory_fd(APPROVED_VERSIONS, label="approved versions root") as (
                versions_fd, versions_id,
            ):
                logical_version = APPROVED_VERSIONS / digest
                _ensure_approved_version_at(
                    versions_fd, digest, candidate, manifest,
                )
                pointer = {
                    "schema_version": SCHEMA_VERSION,
                    "digest": digest,
                    "version": f"approved/{digest}",
                    "previous_digest": baseline,
                }
                _assert_candidate_current(manifest, phase="before publication")
                if (
                    _directory_identity(APPROVED_ROOT) != approved_id
                    or _directory_identity(APPROVED_VERSIONS) != versions_id
                ):
                    raise AcceptanceError("approved roots changed during promotion")
                _publish_active_pointer_at(approved_fd, pointer)
                if _directory_identity(APPROVED_ROOT) != approved_id:
                    raise AcceptanceError("approved root changed during publication")
    print(logical_version)
    return logical_version


def prune_candidates(*, apply: bool = False) -> list[Path]:
    candidate_root = _prepare_candidate_root()
    selected = []
    try:
        with _lease(OUTPUT_ROOT / "candidate-registry.lock", blocking=False):
            candidate_root = _prepare_candidate_root()
            with _directory_fd(candidate_root, label="candidate root") as (root_fd, root_id):
                stable_root = _path_from_fd(root_fd)
                names = os.listdir(root_fd)
                if len(names) > MAX_CANDIDATE_ROOT_ENTRIES:
                    raise AcceptanceError("candidate root exceeds entry limit")
                with contextlib.ExitStack() as leases:
                    records = []
                    for name in sorted(names):
                        candidate = stable_root / name
                        if not candidate.is_dir() or candidate.is_symlink():
                            continue
                        try:
                            leases.enter_context(_lease(
                                candidate / ".lease", blocking=False,
                                create_parent=False,
                            ))
                        except LeaseBusy:
                            continue
                        manifest = candidate / "manifest.json"
                        failed = candidate / "failure.json"
                        total = _candidate_tree_size(candidate)
                        records.append({
                            "path": candidate_root / name,
                            "candidate_id": name,
                            "status": (
                                "successful"
                                if manifest.is_file() and not failed.is_file()
                                else "failed"
                            ),
                            "bytes": total,
                            "pinned": (candidate / ".pin").exists(),
                        })
                    if _directory_identity(candidate_root) != root_id:
                        raise AcceptanceError("candidate root changed during pruning")
                    successful = [
                        record for record in records
                        if record["status"] == "successful" and not record["pinned"]
                    ]
                    incomplete = [
                        record for record in records
                        if record["status"] != "successful" and not record["pinned"]
                    ]
                    keep_ids: set[str] = set()
                    retained_bytes = 0
                    for pool, limit in ((successful, 3), (incomplete, 2)):
                        retained = 0
                        for record in reversed(pool):
                            if retained_bytes + record["bytes"] <= MAX_CANDIDATE_BYTES:
                                keep_ids.add(record["candidate_id"])
                                retained_bytes += record["bytes"]
                                retained += 1
                            if retained >= limit:
                                break
                    for record in records:
                        if record["pinned"] or record["candidate_id"] in keep_ids:
                            continue
                        selected.append(record["path"])
                        if apply:
                            name = record["candidate_id"]
                            try:
                                metadata = os.stat(name, dir_fd=root_fd, follow_symlinks=False)
                            except OSError as exc:
                                raise AcceptanceError(
                                    f"candidate changed before pruning: {name}"
                                ) from exc
                            if not stat.S_ISDIR(metadata.st_mode):
                                raise AcceptanceError(
                                    f"candidate changed before pruning: {name}"
                                )
                            quarantine_name = f".prune-{name}-{uuid.uuid4().hex}"
                            os.rename(
                                name, quarantine_name,
                                src_dir_fd=root_fd, dst_dir_fd=root_fd,
                            )
                            quarantined = os.stat(
                                quarantine_name, dir_fd=root_fd, follow_symlinks=False,
                            )
                            if not stat.S_ISDIR(quarantined.st_mode):
                                raise AcceptanceError("quarantined candidate is unsafe")
                            shutil.rmtree(quarantine_name, dir_fd=root_fd)
    except LeaseBusy:
        return []
    for path in selected:
        print(path)
    return selected


def verify_candidate(candidate: Path) -> dict[str, Any]:
    """Validate a candidate while holding the lease used by pruning."""
    candidate = _candidate_directory(candidate)
    with _lease(candidate / ".lease", create_parent=False):
        candidate = _candidate_directory(candidate)
        return validate_candidate(candidate)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("generate")
    verify_parser = sub.add_parser("verify")
    verify_parser.add_argument("candidate", type=Path)
    promote_parser = sub.add_parser("promote")
    promote_parser.add_argument("candidate", type=Path)
    prune_parser = sub.add_parser("prune")
    prune_mode = prune_parser.add_mutually_exclusive_group()
    prune_mode.add_argument("--dry-run", action="store_true")
    prune_mode.add_argument("--apply", action="store_true")
    worker = sub.add_parser("_worker")
    worker.add_argument("request", type=Path)
    worker.add_argument("result", type=Path)
    args = parser.parse_args(argv)
    if args.command == "generate":
        generate()
    elif args.command == "verify":
        verify_candidate(args.candidate)
        print(args.candidate)
    elif args.command == "promote":
        promote(args.candidate)
    elif args.command == "prune":
        prune_candidates(apply=args.apply)
    else:
        return _worker(args.request, args.result)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (AcceptanceError, OSError) as exc:
        diagnostic = str(exc)[:MAX_STDERR_BYTES]
        print(f"visual acceptance failed: {diagnostic}", file=sys.stderr)
        raise SystemExit(1)
