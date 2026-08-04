"""Fixed history policy for the ratified integration candidate."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .model import AuditError, require_sha, sha256_bytes
from .git_commands import GitRunner


BASE_COMMIT = "0393826337b59f8a10be9f201083541fa7f4a49f"
ORIGINAL_TIP = "27023098530836c7c4c2c822fb67a5fd149f9ec9"
CANDIDATE_COMMIT = "0b22ebd9efb19ec25247a85fd39796aa2907b6d6"
ORIGINAL_COMMITS = (
    "2adb2ebf80851114818e6011c873b99480ec7f8e",
    "4287a8089b531f4032f01d0120c059159ede0f91",
    "d6cef2258ed070aff225d2f7aa0bc175241517fe",
    "83659e75a313c548e35de2ee89518db7caa8658c",
    "dec4dd7ba4a9f7163795ea313f313ee74c577c38",
    "dc76efbc8d5b54fb5c1efc4a469333ac53faf877",
    "5008d39e93b18f421ab1518ffa2f2eed58d717fc",
    "fbd4dc18a50f93a9c55d85b2f0e5ee7138ab4dd0",
    "0560ead96c824e1198bbcf99cbfea325da7cd8ef",
    "4fa121a3de422ceca3815059ad37505ec5ce228a",
    "4976e0f6e83571683c1dbd23c4266f97ed8569a3",
    "8a036a54aa52b7e04c920b2a78da321c0056caf1",
    "b644c01c4ce862d9ae8e13748a056b89b5002f4e",
    "8741cd9fe9f442f1f98a0c54ac31b6e7c6cd8175",
    ORIGINAL_TIP,
)
STABILIZATION_COUNT = 18


@dataclass(frozen=True)
class HistoryEvidence:
    candidate: str
    tree: str
    stabilization_commits: tuple[str, ...]
    history_sha256: str


def _lines(value: str) -> tuple[str, ...]:
    return tuple(line for line in value.splitlines() if line)


def _require_equal(actual: str, expected: str, label: str) -> None:
    if actual != expected:
        raise AuditError("history mismatch", f"{label} does not match the ratified boundary")


def _reject_object_substitution(git: GitRunner) -> None:
    """Reject repository mechanisms that can substitute commit objects."""
    replacements = git.text("for-each-ref", "--format=%(refname)", "refs/replace").strip()
    if replacements:
        raise AuditError("history mismatch", "Git replacement objects are configured")
    raw_common = git.text("rev-parse", "--git-common-dir", capture_limit=4096).strip()
    common = Path(raw_common)
    if not common.is_absolute():
        common = git.root / common
    try:
        common = common.resolve(strict=True)
        grafts = common / "info" / "grafts"
        try:
            metadata = grafts.lstat()
        except FileNotFoundError:
            return
        if not grafts.is_file() or grafts.is_symlink() or metadata.st_size > 1024 * 1024:
            raise AuditError("history mismatch", "legacy Git grafts are configured")
        if grafts.read_bytes().strip():
            raise AuditError("history mismatch", "legacy Git grafts are configured")
    except AuditError:
        raise
    except OSError as exc:
        raise AuditError("history mismatch", "Git graft configuration could not be inspected") from exc


def verify_history(git: GitRunner, candidate: str) -> HistoryEvidence:
    """Verify the exact immutable object graph and return its stable evidence."""
    require_sha(candidate, "candidate")
    _reject_object_substitution(git)
    _require_equal(candidate, CANDIDATE_COMMIT, "candidate")
    resolved = git.text("rev-parse", "--verify", f"{candidate}^{{commit}}").strip()
    _require_equal(resolved, candidate, "candidate object")
    main = git.text("rev-parse", "--verify", "refs/heads/main").strip()
    _require_equal(main, BASE_COMMIT, "local main")
    merge_base = git.text("merge-base", BASE_COMMIT, candidate).strip()
    _require_equal(merge_base, BASE_COMMIT, "merge base")
    git.text("merge-base", "--is-ancestor", BASE_COMMIT, candidate)
    git.text("merge-base", "--is-ancestor", ORIGINAL_TIP, candidate)

    original = _lines(git.text("rev-list", "--reverse", f"{BASE_COMMIT}..{ORIGINAL_TIP}"))
    if original != ORIGINAL_COMMITS:
        raise AuditError("history mismatch", "original fifteen-commit sequence changed")
    full = _lines(git.text("rev-list", "--reverse", f"{BASE_COMMIT}..{candidate}"))
    if full[: len(ORIGINAL_COMMITS)] != ORIGINAL_COMMITS:
        raise AuditError("history mismatch", "candidate does not preserve the original sequence")
    stabilization = full[len(ORIGINAL_COMMITS):]
    if len(stabilization) != STABILIZATION_COUNT or not stabilization or stabilization[-1] != candidate:
        raise AuditError("history mismatch", "stabilization range is not the approved eighteen commits")

    parent = BASE_COMMIT
    parent_rows = _lines(git.text("rev-list", "--reverse", "--parents", f"{BASE_COMMIT}..{candidate}"))
    if len(parent_rows) != len(full):
        raise AuditError("history mismatch", "candidate range could not be enumerated")
    for expected, row in zip(full, parent_rows, strict=True):
        fields = row.split()
        if fields != [expected, parent]:
            raise AuditError("history mismatch", "candidate range is not linear")
        parent = expected

    tree = git.text("show", "-s", "--format=%T", candidate).strip()
    require_sha(tree, "candidate tree")
    history_bytes = ("\n".join(full) + "\n").encode("ascii")
    return HistoryEvidence(candidate, tree, stabilization, sha256_bytes(history_bytes))
