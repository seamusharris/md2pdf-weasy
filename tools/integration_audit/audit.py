"""Thin coordinator for immutable candidate inspection and validation."""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

from .history import BASE_COMMIT, ORIGINAL_COMMITS, ORIGINAL_TIP, verify_history
from .hygiene import verify_hygiene
from .isolate import ValidationCommand, validate_candidate
from .model import AuditError, AuditResult, DECISION, NO_GO_DECISION
from .git_commands import GitRunner
from .state import RepositoryLease, capture_snapshot, lease_path, require_unchanged


def audit_candidate(
    root: Path, candidate: str, *, private_parent: Path,
    validation_commands: Sequence[ValidationCommand],
) -> AuditResult:
    """Audit one exact candidate without moving refs or using a worktree export."""
    git = GitRunner(root)
    with RepositoryLease(lease_path(git)):
        snapshot = capture_snapshot(git)
        history = verify_history(git, candidate)
        hygiene = verify_hygiene(git, candidate)
        decision = DECISION
        try:
            outcomes = validate_candidate(git, candidate, private_parent, validation_commands)
        except AuditError as exc:
            if exc.residue:
                raise
            decision = NO_GO_DECISION
            outcomes = (f"candidate-validation: fail-closed ({exc.category})",)
        require_unchanged(git, snapshot)
    return AuditResult(
        candidate_commit=history.candidate,
        candidate_tree=history.tree,
        base_commit=BASE_COMMIT,
        original_tip=ORIGINAL_TIP,
        original_commits=ORIGINAL_COMMITS,
        stabilization_commits=history.stabilization_commits,
        history_sha256=history.history_sha256,
        diff_sha256=hygiene.diff_sha256,
        changed_paths_sha256=hygiene.changed_paths_sha256,
        changed_path_count=hygiene.changed_path_count,
        validations=("history: pass", "diff-hygiene: pass", *outcomes),
        decision=decision,
    )
