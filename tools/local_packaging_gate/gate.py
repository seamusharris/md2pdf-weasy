"""Authorization-first coordinator for local packaging-gate evidence."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from tools.distribution_entitlement import PreflightError, preflight
from tools.integration_audit.git_commands import GitRunner
from tools.integration_audit.model import AuditError
from tools.integration_audit.state import RepositoryLease, lease_path
from tools.integration_audit.verifier import verify_downstream_with_lease

from .model import GateError, GateRecord, Prerequisite


Publish = Callable[[bytes], bool]


def _identity(git: GitRunner) -> tuple[str, str]:
    commit = git.text("rev-parse", "--verify", "HEAD", capture_limit=256).strip()
    tree = git.text("rev-parse", "--verify", "HEAD^{tree}", capture_limit=256).strip()
    return commit, tree


def _integration_check(root: Path, lease: RepositoryLease) -> tuple[Prerequisite, str | None]:
    try:
        commit = verify_downstream_with_lease(root, lease)
    except AuditError as exc:
        return Prerequisite(
            "immutable-candidate-acceptance", "denied", exc.category, exc.detail,
        ), None
    return Prerequisite("immutable-candidate-acceptance", "authorized", None, None), commit


def _entitlement_check(root: Path) -> tuple[Prerequisite, dict[str, str] | None]:
    try:
        decision = preflight(root, "package_artifact", "owner_workstation", "owner")
    except PreflightError as exc:
        return Prerequisite(
            "package-artifact-entitlement", "denied", exc.category, exc.detail,
        ), None
    return Prerequisite("package-artifact-entitlement", "authorized", None, None), decision


def run(root: Path, publish: Publish) -> GateRecord:
    """Evaluate both prerequisites and emit blocked evidence under one lease."""

    git = GitRunner(root)
    with RepositoryLease(lease_path(git)) as lease:
        before = _identity(git)
        integration, accepted_commit = _integration_check(root, lease)
        entitlement, decision = _entitlement_check(root)
        after = _identity(git)
        if before != after:
            raise GateError("repository changed", "source identity changed during evaluation")
        if accepted_commit is not None:
            accepted_tree = git.text(
                "show", "-s", "--format=%T", accepted_commit, capture_limit=256,
            ).strip()
            if after[1] != accepted_tree:
                raise GateError("identity mismatch", "accepted, authorized, and source trees differ")
        if decision is not None:
            if after[1] != decision["git_tree"]:
                raise GateError("identity mismatch", "accepted, authorized, and source trees differ")
        record = GateRecord(after[0], after[1], (integration, entitlement))
        if not publish(record.to_bytes()):
            raise GateError("output failed", "canonical packaging-gate evidence was not written")
        return record
