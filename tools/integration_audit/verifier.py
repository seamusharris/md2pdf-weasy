"""Independent downstream verification of checked audit evidence."""

from __future__ import annotations

from pathlib import Path

from .history import BASE_COMMIT, ORIGINAL_COMMITS, ORIGINAL_TIP, verify_history
from .hygiene import verify_hygiene
from .model import AuditError, load_result
from .git_commands import GitRunner
from .path_policy import require_relative_path
from .state import ACTIVATION_REF, RepositoryLease, capture_snapshot, lease_path


DEFAULT_RECORD_PATH = "docs/integration-audit.json"


def _safe_record_path(value: str) -> str:
    require_relative_path(
        value, category="invalid request", detail="audit record path is unsafe",
    )
    return value


def verify_downstream(root: Path, *, record_path: str = DEFAULT_RECORD_PATH) -> str:
    """Require the two-ref go signal and rederive immutable evidence."""
    git = GitRunner(root)
    with RepositoryLease(lease_path(git)):
        return _verify_downstream_under_lease(git, record_path=record_path)


def _verify_downstream_under_lease(git: GitRunner, *, record_path: str) -> str:
    initial = capture_snapshot(git)
    head = initial.head
    if head != initial.activation:
        raise AuditError("evidence rejected", "branch and activation refs do not identify one commit")
    parents = git.text("show", "-s", "--format=%P", head, capture_limit=1024).strip().split()
    raw = git.bytes("show", f"{head}:{_safe_record_path(record_path)}", capture_limit=1024 * 1024)
    result = load_result(raw)
    if parents != [result.candidate_commit]:
        raise AuditError("evidence rejected", "audit evidence commit has the wrong parent")
    history = verify_history(git, result.candidate_commit)
    hygiene = verify_hygiene(git, result.candidate_commit)
    if (
        result.base_commit != BASE_COMMIT
        or result.original_tip != ORIGINAL_TIP
        or result.original_commits != ORIGINAL_COMMITS
        or result.candidate_tree != history.tree
        or result.stabilization_commits != history.stabilization_commits
        or result.history_sha256 != history.history_sha256
        or result.diff_sha256 != hygiene.diff_sha256
        or result.changed_paths_sha256 != hygiene.changed_paths_sha256
        or result.changed_path_count != hygiene.changed_path_count
    ):
        raise AuditError("evidence rejected", "embedded audit snapshot does not match immutable objects")
    commit_tree = git.text("show", "-s", "--format=%T", head, capture_limit=256).strip()
    first = capture_snapshot(git)
    second = capture_snapshot(git)
    if (
        first != second
        or second.branch_ref != initial.branch_ref
        or second.head != head
        or second.main != initial.main
        or second.main != BASE_COMMIT
        or second.activation != head
        or second.index_tree != commit_tree
        or second.tracked_status
    ):
        raise AuditError("evidence rejected", "integration checkout is not clean and coherent")
    return head
