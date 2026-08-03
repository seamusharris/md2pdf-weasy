"""Immutable candidate inputs and verified installed-package provenance."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from importlib import metadata
from pathlib import Path, PurePosixPath
import re
import subprocess

from .model import CanaryError, COMMIT_RE, MAX_JSON_BYTES, RunRequest, content_digest, parse_json_bytes


MAX_INSTALLED_FILES = 512
MAX_INSTALLED_BYTES = 64 * 1024 * 1024
MAX_FIXTURE_BYTES = 64 * 1024
REGISTRY_PATH = "docs/downstream-consumers.json"
FIXTURE_PATH = "tests/canary/downstream.md"
RESOURCE_PATH = "tests/canary/canary-resource.svg"


@dataclass(frozen=True)
class CandidateInputs:
    commit: str
    tree: str
    rollback_commit: str
    registry: bytes
    fixture: bytes
    resource: bytes
    input_digest: str
    package_digest: str
    package_files: tuple[str, ...]


@dataclass(frozen=True)
class SourceSnapshot:
    commit: str
    tree: str
    rollback_commit: str
    installed_commit: str
    installed_digest: str
    direct_url_digest: str
    input_digest: str
    expected_package_digest: str
    package_files: tuple[str, ...]
    package_root: Path


def _git(root: Path, *arguments: str) -> bytes:
    try:
        completed = subprocess.run(
            ["git", "-C", str(root), *arguments],
            check=False,
            capture_output=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise CanaryError("source invalid", "Git identity is unavailable", 4) from exc
    if completed.returncode != 0:
        raise CanaryError("source invalid", "Git identity check failed", 4)
    return completed.stdout


def _git_text(root: Path, *arguments: str) -> str:
    try:
        return _git(root, *arguments).decode("utf-8").strip()
    except UnicodeError as exc:
        raise CanaryError("source invalid", "Git identity is malformed", 4) from exc


def _commit_object(root: Path, commit: str, label: str) -> str:
    if COMMIT_RE.fullmatch(commit) is None:
        raise CanaryError("source invalid", f"{label} is not a canonical full commit", 4)
    resolved = _git_text(root, "rev-parse", "--verify", f"{commit}^{{commit}}")
    if resolved != commit:
        raise CanaryError("source invalid", f"{label} does not resolve exactly", 4)
    if _git_text(root, "cat-file", "-t", commit) != "commit":
        raise CanaryError("source invalid", f"{label} is not a commit object", 4)
    return resolved


def _source_identity(root: Path, request: RunRequest, entitled_tree: str) -> tuple[str, str, str]:
    try:
        top = Path(_git_text(root, "rev-parse", "--show-toplevel")).resolve()
        resolved_root = root.resolve()
    except OSError as exc:
        raise CanaryError("source invalid", "checkout root is unavailable", 4) from exc
    if top != resolved_root:
        raise CanaryError("source invalid", "root is not the checkout root", 4)
    candidate = _commit_object(root, request.candidate_commit, "candidate commit")
    rollback = _commit_object(root, request.rollback_commit, "rollback commit")
    if _git_text(root, "rev-parse", "HEAD") != candidate:
        raise CanaryError("source invalid", "checkout is not at the candidate commit", 4)
    tree = _git_text(root, "rev-parse", "HEAD^{tree}")
    if not re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", tree) or tree != entitled_tree:
        raise CanaryError("source invalid", "checkout tree does not match entitlement", 4)
    if _git_text(root, "status", "--porcelain=v1", "--untracked-files=all"):
        raise CanaryError("source invalid", "checkout is not clean", 4)
    return candidate, tree, rollback


def _tree_entries(root: Path, tree: str, prefix: str) -> tuple[tuple[str, str], ...]:
    raw = _git(root, "ls-tree", "-r", "-z", tree, "--", prefix)
    result: list[tuple[str, str]] = []
    seen: set[str] = set()
    for record in (item for item in raw.split(b"\0") if item):
        try:
            header, raw_name = record.split(b"\t", 1)
            mode, kind, object_id = header.decode("ascii").split(" ")
            name = raw_name.decode("utf-8")
        except (UnicodeError, ValueError) as exc:
            raise CanaryError("source invalid", "Git tree entry is malformed", 4) from exc
        pure = PurePosixPath(name)
        if (
            mode not in {"100644", "100755"}
            or kind != "blob"
            or COMMIT_RE.fullmatch(object_id) is None
            or pure.is_absolute()
            or ".." in pure.parts
            or pure.as_posix() != name
            or name in seen
        ):
            raise CanaryError("source invalid", "Git tree entry is unsafe", 4)
        seen.add(name)
        result.append((name, object_id))
    return tuple(sorted(result))


def _tree_blob(root: Path, tree: str, name: str, limit: int) -> bytes:
    matches = [entry for entry in _tree_entries(root, tree, name) if entry[0] == name]
    if len(matches) != 1:
        raise CanaryError("source invalid", "required candidate input is unavailable", 4)
    raw = _git(root, "cat-file", "blob", matches[0][1])
    if len(raw) > limit:
        raise CanaryError("source invalid", "candidate input exceeds its size limit", 4)
    return raw


def _package_manifest(root: Path, tree: str) -> tuple[str, tuple[str, ...]]:
    entries = _tree_entries(root, tree, "pdf")
    if not entries or len(entries) > MAX_INSTALLED_FILES:
        raise CanaryError("source invalid", "candidate package inventory exceeds its bounds", 4)
    items: list[tuple[str, bytes]] = []
    total = 0
    for name, object_id in entries:
        if not name.startswith("pdf/"):
            raise CanaryError("source invalid", "candidate package inventory is unsafe", 4)
        content = _git(root, "cat-file", "blob", object_id)
        total += len(content)
        if total > MAX_INSTALLED_BYTES:
            raise CanaryError("source invalid", "candidate package inventory exceeds its bounds", 4)
        items.append((name, content))
    return content_digest(items), tuple(name for name, _content in items)


def load_candidate_inputs(
    root: Path,
    request: RunRequest,
    entitled_tree: str,
) -> CandidateInputs:
    """Capture all trusted inputs from the immutable entitled Git tree."""

    candidate, tree, rollback = _source_identity(root, request, entitled_tree)
    registry = _tree_blob(root, tree, REGISTRY_PATH, MAX_JSON_BYTES)
    fixture = _tree_blob(root, tree, FIXTURE_PATH, MAX_FIXTURE_BYTES)
    resource = _tree_blob(root, tree, RESOURCE_PATH, MAX_FIXTURE_BYTES)
    package_digest, package_files = _package_manifest(root, tree)
    digest = content_digest(
        [
            (REGISTRY_PATH, registry),
            (FIXTURE_PATH, fixture),
            (RESOURCE_PATH, resource),
            ("pdf-manifest.sha256", package_digest.encode("ascii")),
        ]
    )
    return CandidateInputs(
        candidate,
        tree,
        rollback,
        registry,
        fixture,
        resource,
        digest,
        package_digest,
        package_files,
    )


def _validate_direct_url(raw: bytes, expected_commit: str) -> tuple[str, str]:
    if len(raw) > MAX_JSON_BYTES:
        raise CanaryError("provenance invalid", "PEP 610 metadata exceeds the size limit", 5)
    value = parse_json_bytes(raw, "PEP 610 metadata")
    if frozenset(value) != frozenset({"url", "vcs_info"}):
        raise CanaryError("provenance invalid", "PEP 610 metadata is not a direct VCS install", 5)
    url = value["url"]
    vcs = value["vcs_info"]
    if not isinstance(url, str) or not (1 <= len(url) <= 2048) or not isinstance(vcs, dict):
        raise CanaryError("provenance invalid", "PEP 610 VCS metadata is malformed", 5)
    if not frozenset(vcs).issubset({"vcs", "commit_id", "requested_revision"}):
        raise CanaryError("provenance invalid", "PEP 610 VCS fields are unknown", 5)
    if frozenset(vcs) < frozenset({"vcs", "commit_id"}):
        raise CanaryError("provenance invalid", "PEP 610 VCS fields are incomplete", 5)
    commit = vcs["commit_id"]
    if vcs["vcs"] != "git" or not isinstance(commit, str) or COMMIT_RE.fullmatch(commit) is None:
        raise CanaryError("provenance invalid", "PEP 610 Git commit is malformed", 5)
    if commit != expected_commit:
        raise CanaryError("provenance invalid", "installed commit does not match candidate", 5)
    requested = vcs.get("requested_revision")
    if requested is not None and (
        not isinstance(requested, str) or len(requested) > 256 or requested.startswith("-")
    ):
        raise CanaryError("provenance invalid", "PEP 610 requested revision is malformed", 5)
    return commit, hashlib.sha256(raw).hexdigest()


def _installed_distribution(expected_commit: str):
    try:
        distribution = metadata.distribution("md2pdf-weasy")
        direct_text = distribution.read_text("direct_url.json")
    except (OSError, UnicodeError, metadata.PackageNotFoundError) as exc:
        raise CanaryError("provenance invalid", "installed distribution metadata is unavailable", 5) from exc
    if direct_text is None:
        raise CanaryError("provenance invalid", "PEP 610 metadata is unavailable", 5)
    installed_commit, direct_digest = _validate_direct_url(
        direct_text.encode("utf-8"), expected_commit
    )
    return distribution, installed_commit, direct_digest


def _installed_paths(distribution) -> tuple[str, ...]:
    files = distribution.files
    if files is None:
        raise CanaryError("provenance invalid", "installed file inventory is unavailable", 5)
    return tuple(
        sorted(
            Path(*item.parts).as_posix()
            for item in files
            if item.parts
            and item.parts[0] == "pdf"
            and "__pycache__" not in item.parts
            and item.suffix != ".pyc"
        )
    )


def _read_installed_inventory(distribution, selected: tuple[str, ...]) -> tuple[str, Path]:
    raw_package_root = Path(distribution.locate_file("pdf"))
    try:
        package_root = raw_package_root.resolve(strict=True)
    except OSError as exc:
        raise CanaryError("provenance invalid", "installed package root is unavailable", 5) from exc
    if raw_package_root.is_symlink() or not package_root.is_dir():
        raise CanaryError("provenance invalid", "installed package root is unsafe", 5)
    items: list[tuple[str, bytes]] = []
    total = 0
    for name in selected:
        path = package_root.parent.joinpath(*PurePosixPath(name).parts)
        try:
            resolved = path.resolve(strict=True)
            if path.is_symlink() or not resolved.is_file() or not resolved.is_relative_to(package_root):
                raise CanaryError("provenance invalid", "installed inventory contains an unsafe file", 5)
            content = resolved.read_bytes()
        except OSError as exc:
            raise CanaryError("provenance invalid", "installed file inventory is unreadable", 5) from exc
        total += len(content)
        if total > MAX_INSTALLED_BYTES:
            raise CanaryError("provenance invalid", "installed file inventory exceeds its bounds", 5)
        items.append((name, content))
    installed_digest = content_digest(items)
    return installed_digest, package_root


def _distribution_snapshot(
    expected_commit: str,
    expected_digest: str,
    expected_files: tuple[str, ...],
) -> tuple[str, str, str, Path]:
    distribution, installed_commit, direct_digest = _installed_distribution(expected_commit)
    selected = _installed_paths(distribution)
    if selected != expected_files:
        raise CanaryError("provenance invalid", "installed file inventory does not match candidate", 5)
    installed_digest, package_root = _read_installed_inventory(distribution, selected)
    if installed_digest != expected_digest:
        raise CanaryError("provenance invalid", "installed package bytes do not match candidate", 5)
    return installed_commit, installed_digest, direct_digest, package_root


def capture_snapshot(root: Path, request: RunRequest, inputs: CandidateInputs) -> SourceSnapshot:
    candidate, tree, rollback = _source_identity(root, request, inputs.tree)
    if (candidate, tree, rollback) != (inputs.commit, inputs.tree, inputs.rollback_commit):
        raise CanaryError("source changed", "candidate identity changed during canary", 6)
    installed_commit, installed_digest, direct_digest, package_root = _distribution_snapshot(
        candidate,
        inputs.package_digest,
        inputs.package_files,
    )
    return SourceSnapshot(
        candidate,
        tree,
        rollback,
        installed_commit,
        installed_digest,
        direct_digest,
        inputs.input_digest,
        inputs.package_digest,
        inputs.package_files,
        package_root,
    )


def stage_verified_package(snapshot: SourceSnapshot, workspace: Path) -> Path:
    """Copy candidate-matching installed bytes before executing any package code."""

    runtime = workspace / "verified-runtime"
    runtime.mkdir(mode=0o700)
    items: list[tuple[str, bytes]] = []
    total = 0
    for name in snapshot.package_files:
        parts = PurePosixPath(name).parts
        source = snapshot.package_root.parent.joinpath(*parts)
        try:
            resolved = source.resolve(strict=True)
            if source.is_symlink() or not resolved.is_file() or not resolved.is_relative_to(snapshot.package_root):
                raise CanaryError("provenance invalid", "installed inventory contains an unsafe file", 5)
            content = resolved.read_bytes()
        except OSError as exc:
            raise CanaryError("provenance invalid", "installed file inventory is unreadable", 5) from exc
        total += len(content)
        if total > MAX_INSTALLED_BYTES:
            raise CanaryError("provenance invalid", "installed file inventory exceeds its bounds", 5)
        destination = runtime.joinpath(*parts)
        destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        try:
            destination.write_bytes(content)
        except OSError as exc:
            raise CanaryError("workspace unavailable", "verified runtime could not be staged", 8) from exc
        items.append((name, content))
    if content_digest(items) != snapshot.expected_package_digest:
        raise CanaryError("provenance invalid", "staged package bytes do not match candidate", 5)
    return runtime / "pdf"


def assert_unchanged(before: SourceSnapshot, after: SourceSnapshot) -> None:
    if before != after:
        raise CanaryError("source changed", "checkout or installed environment changed during canary", 6)
