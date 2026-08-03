"""Source snapshots and bounded provenance attestation."""

from __future__ import annotations

import importlib.metadata
import json
import os
from pathlib import Path
import platform
import re
import stat

from .io import write_all
from .model import CompatibilityError, MAX_CANDIDATE_BYTES, sha256_file
from .process import probe_version, run_bounded


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests" / "compatibility" / "v0.1.0.md"
ACTIVE_VISUAL = ROOT / "docs" / "visual-acceptance" / "active.json"
CHECKED_DECISION = ROOT / "docs" / "compatibility" / "v0.1.0-rendering.json"
SOURCE_GLOBS = ("*.py", "*.css", "*.yml", "*.yaml", "*.ttf", "*.otf")
DEPENDENCIES = (
    "weasyprint", "markdown", "pymdown-extensions", "pyyaml", "fonttools",
    "pillow", "pypdf",
)
MAX_ACTIVE_JSON_BYTES = 64 * 1024
MAX_APPROVED_MANIFEST_BYTES = 16 * 1024 * 1024
PUBLICATION_BASIS = "immutable-render-snapshot-v1"


def source_hashes() -> dict[str, str]:
    paths = [FIXTURE]
    for pattern in SOURCE_GLOBS:
        paths.extend((ROOT / "pdf").rglob(pattern))
    paths.extend((ROOT / "tools" / "compatibility").glob("*.py"))
    paths.append(ROOT / "tools" / "compatibility_v010.py")
    return {str(path.relative_to(ROOT)): sha256_file(path) for path in sorted(set(paths)) if path.is_file()}


def head_commit() -> str:
    value, _ = run_bounded(
        ("git", "rev-parse", "HEAD"), cwd=ROOT,
        category="verify", phase="provenance",
    )
    return value.strip()


def _generation_state() -> tuple[str, dict[str, str], str]:
    return head_commit(), source_hashes(), active_visual_digest()


def _stable_generation_state() -> tuple[str, dict[str, str], str]:
    first = _generation_state()
    if first != _generation_state():
        raise CompatibilityError(
            "compatibility inputs changed while attesting provenance",
            category="verify", phase="source-attestation",
        )
    return first


def capture_generation_provenance(tag_commit: str) -> dict[str, object]:
    """Capture immutable identifiers for rendering and later publication."""
    head, hashes, visual_digest = _stable_generation_state()
    fixture_name = str(FIXTURE.relative_to(ROOT))
    if fixture_name not in hashes:
        raise CompatibilityError(
            "compatibility fixture is missing or unsafe",
            category="verify", phase="source-attestation",
        )
    return {
        "tag": "v0.1.0", "tag_commit": tag_commit,
        "current_base_commit": head,
        "fixture_sha256": hashes[fixture_name],
        "source_hashes": hashes,
        "active_visual_acceptance_digest": visual_digest,
        "publication_basis": PUBLICATION_BASIS,
        "environment": environment(),
        "commands": [
            "make compatibility-v0.1",
            "make compatibility-v0.1-verify CANDIDATE=<path>",
        ],
    }

def _read_json_at(directory_fd: int, name: str, max_bytes: int) -> dict:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(name, flags, dir_fd=directory_fd)
    try:
        metadata = os.fstat(fd)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > max_bytes:
            raise CompatibilityError("JSON evidence file is unsafe or too large", category="verify", phase="provenance")
        data = bytearray()
        while len(data) <= max_bytes:
            chunk = os.read(fd, min(1024 * 1024, max_bytes + 1 - len(data)))
            if not chunk:
                break
            data.extend(chunk)
        if len(data) > max_bytes:
            raise CompatibilityError("JSON evidence file is too large", category="verify", phase="provenance")
        value = json.loads(bytes(data))
        if not isinstance(value, dict):
            raise CompatibilityError("JSON evidence must be an object", category="verify", phase="provenance")
        return value
    except (ValueError, RecursionError) as exc:
        raise CompatibilityError("JSON evidence is malformed", category="verify", phase="provenance") from exc
    finally:
        os.close(fd)


def active_visual_digest() -> str:
    visual_root = ACTIVE_VISUAL.parent
    directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        parts = visual_root.relative_to(ROOT).parts
        root_fd = os.open(ROOT, directory_flags)
        try:
            for part in parts:
                child = os.open(part, directory_flags, dir_fd=root_fd)
                os.close(root_fd)
                root_fd = child
            value = _read_json_at(root_fd, ACTIVE_VISUAL.name, MAX_ACTIVE_JSON_BYTES)
            digest = value.get("digest") or value.get("active_digest")
            if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
                raise CompatibilityError("active T-009 evidence pointer is invalid", category="verify", phase="provenance")
            approved_fd = os.open("approved", directory_flags, dir_fd=root_fd)
            try:
                digest_fd = os.open(digest, directory_flags, dir_fd=approved_fd)
                try:
                    approved_value = _read_json_at(
                        digest_fd, "manifest.json", MAX_APPROVED_MANIFEST_BYTES,
                    )
                finally:
                    os.close(digest_fd)
            finally:
                os.close(approved_fd)
        finally:
            os.close(root_fd)
    except CompatibilityError:
        raise
    except (OSError, ValueError) as exc:
        raise CompatibilityError("active T-009 evidence path is missing or unsafe", category="verify", phase="provenance") from exc
    source = approved_value.get("source")
    if not isinstance(source, dict) or source.get("digest") != digest:
        raise CompatibilityError("active T-009 manifest does not attest its digest", category="verify", phase="provenance")
    return digest


def environment() -> dict[str, str]:
    versions = {}
    for name in DEPENDENCIES:
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError as exc:
            raise CompatibilityError(
                f"required package metadata is unavailable: {name}",
                category="prerequisite", phase="probe",
            ) from exc
    versions["python"] = platform.python_version()
    versions["platform"] = platform.platform()
    versions["pdftoppm"] = probe_version(("pdftoppm", "-v"), cwd=ROOT)
    return versions


def _copy_regular(source: Path, target: Path, remaining: int) -> int:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    source_fd = os.open(source, flags)
    try:
        metadata = os.fstat(source_fd)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > remaining:
            raise CompatibilityError("snapshot input is unsafe or too large", category="verify", phase="source-snapshot")
        target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        target_fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
        try:
            copied = 0
            while True:
                chunk = os.read(source_fd, min(1024 * 1024, remaining - copied + 1))
                if not chunk:
                    break
                copied += len(chunk)
                if copied > remaining:
                    raise CompatibilityError("snapshot exceeds candidate byte limit", category="verify", phase="source-snapshot")
                write_all(target_fd, chunk)
        finally:
            os.close(target_fd)
        if copied != metadata.st_size:
            raise CompatibilityError("snapshot input changed while copying", category="verify", phase="source-snapshot")
        return copied
    finally:
        os.close(source_fd)


def snapshot_current_renderer(private_root: Path, expected: dict[str, str]) -> tuple[Path, Path]:
    """Copy all current render inputs once and attest that immutable snapshot."""
    parent = private_root / "current-parent"
    parent.mkdir(mode=0o700, parents=True)
    logical = [name for name in expected if name == str(FIXTURE.relative_to(ROOT)) or name.startswith("pdf/")]
    remaining = MAX_CANDIDATE_BYTES
    snapshot_hashes = {}
    for name in sorted(logical):
        source, target = ROOT / name, parent / name
        remaining -= _copy_regular(source, target, remaining)
        snapshot_hashes[name] = sha256_file(target)
    expected_render = {name: expected[name] for name in logical}
    if snapshot_hashes != expected_render:
        raise CompatibilityError("current renderer changed while snapshotting", category="verify", phase="source-snapshot")
    return parent, parent / FIXTURE.relative_to(ROOT)
