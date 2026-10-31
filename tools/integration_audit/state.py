"""Repository lease and protected-state snapshots."""

from __future__ import annotations

from dataclasses import dataclass
import fcntl
import hashlib
import os
from pathlib import Path
import stat
import tempfile

from .model import AuditError, require_sha, sha256_bytes
from .git_commands import GitRunner


ACTIVATION_REF = "refs/audits/integration/T-015"
LEASE_PARENT = Path("/private/tmp") / f"md2pdf-integration-audit-locks-{os.getuid()}"


def _common_directory(git: GitRunner) -> Path:
    raw = git.text("rev-parse", "--git-common-dir", capture_limit=4096).strip()
    common = Path(raw)
    if not common.is_absolute():
        common = git.root / common
    try:
        resolved = common.resolve(strict=True)
    except OSError as exc:
        raise AuditError("lease unavailable", "shared Git directory is unavailable") from exc
    if not resolved.is_dir():
        raise AuditError("lease unavailable", "shared Git directory is unsafe")
    return resolved


def _secure_lease_parent() -> Path:
    try:
        LEASE_PARENT.mkdir(mode=0o700, parents=False, exist_ok=True)
        metadata = LEASE_PARENT.lstat()
    except OSError as exc:
        raise AuditError("lease unavailable", "shared lease directory is unavailable") from exc
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or stat.S_IMODE(metadata.st_mode) != 0o700
        or metadata.st_uid != os.getuid()
        or LEASE_PARENT.is_symlink()
    ):
        raise AuditError("lease unavailable", "shared lease directory is unsafe")
    return LEASE_PARENT


def lease_path(git: GitRunner) -> Path:
    common = _common_directory(git)
    identity = hashlib.sha256(os.fsencode(common)).hexdigest()
    return _secure_lease_parent() / f"{identity}.lock"


class RepositoryLease:
    """A stable, nonblocking POSIX lease shared by integration gates."""

    def __init__(self, path: Path) -> None:
        if not path.is_absolute():
            raise AuditError("lease unavailable", "lease path must be absolute")
        self.path = path
        self._fd: int | None = None
        self._held = False

    @property
    def held(self) -> bool:
        """Return whether this instance currently owns the lease descriptor."""

        return self._held and self._fd is not None

    def __enter__(self) -> "RepositoryLease":
        if self._fd is not None or self._held:
            raise AuditError("lease unavailable", "lease instance is already active")
        flags = os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0)
        parent_fd: int | None = None
        primary: BaseException | None = None
        try:
            resolved_parent = self.path.parent.resolve(strict=True)
            if resolved_parent != self.path.parent or self.path.is_symlink():
                raise AuditError("lease unavailable", "lease target is unsafe")
            parent_fd = os.open(
                resolved_parent,
                os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
            )
            self._fd = os.open(self.path.name, flags, 0o600, dir_fd=parent_fd)
            metadata = os.fstat(self._fd)
            if (
                not stat.S_ISREG(metadata.st_mode)
                or stat.S_IMODE(metadata.st_mode) != 0o600
                or metadata.st_uid != os.getuid()
                or metadata.st_nlink != 1
            ):
                raise AuditError("lease unavailable", "lease target is unsafe")
            fcntl.flock(self._fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self._held = True
        except AuditError as exc:
            primary = exc
        except BlockingIOError as exc:
            primary = AuditError("lease unavailable", "another integration gate is active")
            primary.__cause__ = exc
        except OSError as exc:
            primary = AuditError(
                "lease unavailable", "shared repository lease could not be acquired",
            )
            primary.__cause__ = exc
        except BaseException as exc:
            # Cancellation and other non-Exception failures must still close
            # any descriptors opened before flock completed. Re-raise the
            # original failure after bounded cleanup.
            primary = exc

        parent_close_error = _close_descriptor(parent_fd)
        if primary is not None or parent_close_error is not None:
            lease_close_error = _close_descriptor(self._fd)
            self._fd = None
            self._held = False
            cleanup_error = parent_close_error or lease_close_error
            if cleanup_error is not None:
                failure = AuditError(
                    "cleanup failed", "repository lease descriptors may remain open",
                    residue=True,
                )
                failure.__cause__ = cleanup_error
                if primary is not None:
                    primary.add_note(str(failure))
                    raise primary
                raise failure
            if primary is not None:
                raise primary
        return self

    def __exit__(self, _kind, value, _traceback) -> None:
        if self._fd is not None:
            cleanup_error: OSError | None = None
            release_primary: BaseException | None = None
            try:
                fcntl.flock(self._fd, fcntl.LOCK_UN)
            except OSError as exc:
                cleanup_error = exc
            except BaseException as exc:
                # Always close the descriptor below: closing it is also the
                # final lock-release backstop when cancellation interrupts the
                # explicit unlock call.
                release_primary = exc
            close_error = _close_descriptor(self._fd)
            self._fd = None
            self._held = False
            cleanup_error = cleanup_error or close_error
            if release_primary is not None:
                if cleanup_error is not None:
                    release_primary.add_note(str(AuditError(
                        "cleanup failed",
                        "repository lease descriptor may remain open",
                        residue=True,
                    )))
                if value is not None:
                    value.add_note("repository lease release was interrupted")
                    return None
                raise release_primary
            if cleanup_error is not None:
                failure = AuditError(
                    "cleanup failed", "repository lease could not be released", residue=True,
                )
                failure.__cause__ = cleanup_error
                if value is not None:
                    # Preserve the operation's primary failure. Python would
                    # otherwise replace it with this cleanup exception, hiding
                    # the actual gate/output error. The note still records the
                    # uncertain lease cleanup for diagnostics and tests.
                    value.add_note(str(failure))
                    return None
                raise failure


def _close_descriptor(descriptor: int | None) -> OSError | None:
    if descriptor is None:
        return None
    try:
        os.close(descriptor)
    except OSError as exc:
        return exc
    return None


@dataclass(frozen=True)
class RepositorySnapshot:
    branch_ref: str
    head: str
    main: str
    activation: str | None
    index_tree: str
    index_entries_sha256: str
    tracked_status_sha256: str
    tracked_status: bytes


def _optional_ref(git: GitRunner, ref: str) -> str | None:
    value = git.text(
        "rev-parse", "--verify", "--quiet", ref, capture_limit=256,
        accepted_returncodes=frozenset({0, 1}),
    ).strip()
    return require_sha(value, "optional ref") if value else None


def capture_snapshot(git: GitRunner) -> RepositorySnapshot:
    branch = git.text("symbolic-ref", "-q", "HEAD", capture_limit=1024).strip()
    if not branch.startswith("refs/heads/"):
        raise AuditError("repository state", "audit requires an attached local branch")
    head = git.text("rev-parse", "--verify", "HEAD", capture_limit=256).strip()
    main = git.text("rev-parse", "--verify", "refs/heads/main", capture_limit=256).strip()
    index_tree = _index_tree(git)
    index_entries = git.bytes("ls-files", "--stage", "-z")
    tracked = git.bytes("status", "--porcelain=v1", "-z", "-uno")
    return RepositorySnapshot(
        branch_ref=branch, head=head, main=main,
        activation=_optional_ref(git, ACTIVATION_REF), index_tree=index_tree,
        index_entries_sha256=sha256_bytes(index_entries),
        tracked_status_sha256=sha256_bytes(tracked), tracked_status=tracked,
    )


def _index_tree(git: GitRunner) -> str:
    """Compute the index tree using a private copy, never locking the shared index."""
    raw_path = git.text("rev-parse", "--git-path", "index", capture_limit=4096).strip()
    index_path = Path(raw_path)
    if not index_path.is_absolute():
        index_path = git.root / index_path
    try:
        index_bytes = index_path.read_bytes()
    except OSError as exc:
        raise AuditError("repository state", "shared index could not be read") from exc
    if len(index_bytes) > 64 * 1024 * 1024:
        raise AuditError("repository state", "shared index exceeds its size limit")
    try:
        descriptor, name = tempfile.mkstemp(prefix="md2pdf-audit-snapshot-index-")
    except OSError as exc:
        raise AuditError("repository state", "temporary snapshot index could not be allocated") from exc
    private_index = Path(name)
    try:
        try:
            os.fchmod(descriptor, 0o600)
            view = memoryview(index_bytes)
            while view:
                written = os.write(descriptor, view)
                view = view[written:]
            os.close(descriptor)
            descriptor = -1
        except OSError as exc:
            raise AuditError(
                "repository state", "temporary snapshot index could not be prepared",
            ) from exc
        return git.text(
            "write-tree", capture_limit=256,
            env_extra={"GIT_INDEX_FILE": str(private_index)},
        ).strip()
    finally:
        cleanup_error: OSError | None = None
        if descriptor >= 0:
            try:
                os.close(descriptor)
            except OSError as exc:
                cleanup_error = exc
        try:
            private_index.unlink(missing_ok=True)
            private_index.with_name(private_index.name + ".lock").unlink(missing_ok=True)
        except OSError as exc:
            cleanup_error = exc
        if cleanup_error is not None:
            raise AuditError(
                "cleanup failed", "temporary snapshot index may remain", residue=True,
            ) from cleanup_error


def require_unchanged(git: GitRunner, expected: RepositorySnapshot) -> RepositorySnapshot:
    current = capture_snapshot(git)
    if current != expected:
        raise AuditError("repository changed", "protected repository state changed during audit")
    return current
