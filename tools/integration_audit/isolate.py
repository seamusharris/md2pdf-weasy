"""Coordinate immutable archive materialization and sandboxed validation."""

from __future__ import annotations

from pathlib import Path
import shutil
import tarfile
from typing import Sequence

from .archive import make_read_only, safe_extract_archive
from .git_commands import GitRunner
from .model import AuditError, MAX_ARCHIVE_BYTES
from .sandbox import ValidationCommand, run_validation_command, sandbox_profile
from .workspace import private_workspace


def validate_candidate(
    git: GitRunner, candidate: str, private_parent: Path,
    commands: Sequence[ValidationCommand],
) -> tuple[str, ...]:
    if not commands:
        raise AuditError("validation unavailable", "no candidate validation commands were provided")
    if shutil.which("sandbox-exec") != "/usr/bin/sandbox-exec":
        raise AuditError("validation unavailable", "sandbox-exec is unavailable")
    archive = git.bytes(
        "archive", "--format=tar", candidate,
        capture_limit=MAX_ARCHIVE_BYTES + 1, timeout=300,
    )
    outcomes: list[str] = []
    with private_workspace(private_parent) as workspace:
        try:
            source = workspace / "source"
            writable = workspace / "writable"
            home = writable / "home"
            temporary = writable / "tmp"
            source.mkdir(mode=0o700)
            for path in (writable, home, temporary):
                path.mkdir(mode=0o700)
            safe_extract_archive(archive, source)
            make_read_only(source)
        except AuditError:
            raise
        except (OSError, tarfile.TarError) as exc:
            raise AuditError("validation unavailable", "candidate materialization failed") from exc
        for command_index, command in enumerate(commands):
            run_validation_command(
                command, command_index=command_index, source=source, writable=writable,
                home=home, temporary=temporary,
            )
            outcomes.append(f"{command.label}: pass")
    return tuple(outcomes)
