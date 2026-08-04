"""Off-ref evidence construction and operator-owned publication handoff."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
import os
from pathlib import Path
import tempfile

from .model import AuditError, load_result, require_sha
from .path_policy import require_relative_path
from .git_commands import GitRunner
from .state import RepositoryLease, RepositorySnapshot, capture_snapshot, lease_path


def _safe_path(value: str) -> str:
    require_relative_path(
        value, category="publication rejected", detail="evidence path is unsafe",
    )
    return value


@contextmanager
def _private_index() -> Iterator[Path]:
    descriptor: int | None = None
    index: Path | None = None
    primary: BaseException | None = None
    try:
        try:
            descriptor, index_name = tempfile.mkstemp(prefix="md2pdf-audit-index-")
            index = Path(index_name)
            os.close(descriptor)
            descriptor = None
            index.chmod(0o600)
            index.unlink()
        except OSError as exc:
            raise AuditError(
                "publication rejected", "temporary publication index could not be allocated",
            ) from exc
        yield index
    except BaseException as exc:
        primary = exc
        raise
    finally:
        cleanup_error: OSError | None = None
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError as exc:
                cleanup_error = exc
        try:
            if index is not None:
                index.unlink(missing_ok=True)
                index.with_name(index.name + ".lock").unlink(missing_ok=True)
        except OSError as exc:
            cleanup_error = exc
        if cleanup_error is not None:
            raise AuditError(
                "cleanup failed", "temporary publication index may remain", residue=True,
            ) from (primary or cleanup_error)


def _stage_evidence_tree(
    git: GitRunner, *, candidate: str, files: Mapping[str, bytes], index: Path,
) -> str:
    environment = {"GIT_INDEX_FILE": str(index)}
    git.text("read-tree", candidate, env_extra=environment)
    for path, content in sorted(files.items()):
        safe = _safe_path(path)
        if not isinstance(content, bytes):
            raise AuditError("publication rejected", "evidence content must be immutable bytes")
        blob = git.text(
            "hash-object", "-w", "--stdin", input_bytes=content, env_extra=environment,
        ).strip()
        require_sha(blob, "evidence blob")
        git.text(
            "update-index", "--add", "--cacheinfo", f"100644,{blob},{safe}",
            env_extra=environment,
        )
    tree = git.text("write-tree", env_extra=environment).strip()
    return require_sha(tree, "evidence tree")


def build_evidence_commit(
    git: GitRunner, *, candidate: str, files: Mapping[str, bytes], message: str,
) -> tuple[str, str]:
    """Build a commit from immutable supplied bytes using a private index."""
    require_sha(candidate, "candidate")
    if not files:
        raise AuditError("publication rejected", "evidence commit has no supplied files")
    record = files.get("docs/integration-audit.json")
    if record is None or load_result(record).candidate_commit != candidate:
        raise AuditError("publication rejected", "evidence record is missing or does not match the candidate")
    with _private_index() as index:
        tree = _stage_evidence_tree(git, candidate=candidate, files=files, index=index)
        commit = git.text(
            "commit-tree", tree, "-p", candidate,
            input_bytes=(message.rstrip() + "\n").encode("utf-8"),
        ).strip()
        require_sha(commit, "evidence commit")
        if git.text("show", "-s", "--format=%P", commit).strip() != candidate:
            raise AuditError("publication rejected", "evidence commit parent is invalid")
        if git.text("show", "-s", "--format=%T", commit).strip() != tree:
            raise AuditError("publication rejected", "evidence commit tree is invalid")
        return commit, tree


def require_operator_publication(
    git: GitRunner, *, before: RepositorySnapshot, candidate: str,
    commit: str, tree: str,
) -> None:
    """Validate an evidence commit, but never mutate a user-editable checkout."""
    require_sha(candidate, "candidate")
    require_sha(commit, "evidence commit")
    require_sha(tree, "evidence tree")
    with RepositoryLease(lease_path(git)):
        current = capture_snapshot(git)
        candidate_tree = git.text(
            "show", "-s", "--format=%T", candidate, capture_limit=256,
        ).strip()
        commit_parent = git.text(
            "show", "-s", "--format=%P", commit, capture_limit=1024,
        ).strip()
        commit_tree = git.text(
            "show", "-s", "--format=%T", commit, capture_limit=256,
        ).strip()
        if (
            current != before or before.head != candidate or before.activation is not None
            or before.index_tree != candidate_tree or before.tracked_status
            or commit_parent != candidate or commit_tree != tree
        ):
            raise AuditError("publication rejected", "protected pre-publication state changed")
        raise AuditError(
            "publication requires operator",
            "automated publication into a user-editable checkout is disabled",
        )
