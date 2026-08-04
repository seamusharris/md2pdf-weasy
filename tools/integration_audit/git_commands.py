"""Fixed, bounded Git-object command facade."""

from __future__ import annotations

from pathlib import Path
from typing import Mapping

from .model import AuditError, COMMAND_TIMEOUT, MAX_CAPTURE_BYTES
from .process import clean_environment, run_bounded_bytes


class GitRunner:
    def __init__(self, root: Path) -> None:
        try:
            self.root = root.resolve(strict=True)
        except OSError as exc:
            raise AuditError("invalid request", "repository root is unavailable") from exc
        if not self.root.is_dir():
            raise AuditError("invalid request", "repository root is unavailable")

    def bytes(
        self, *args: str, input_bytes: bytes | None = None,
        capture_limit: int = MAX_CAPTURE_BYTES, timeout: float = COMMAND_TIMEOUT,
        env_extra: Mapping[str, str] | None = None,
        accepted_returncodes: frozenset[int] = frozenset({0}),
    ) -> bytes:
        environment = clean_environment(env_extra)
        stdout, _ = run_bounded_bytes(
            ("/usr/bin/git", "-C", str(self.root), *args), cwd=self.root,
            env=environment, input_bytes=input_bytes, capture_limit=capture_limit,
            timeout=timeout, label=f"git {args[0] if args else 'command'}",
            accepted_returncodes=accepted_returncodes,
        )
        return stdout

    def text(self, *args: str, **kwargs: object) -> str:
        try:
            return self.bytes(*args, **kwargs).decode("utf-8", "strict")
        except UnicodeDecodeError as exc:
            raise AuditError("command output", "Git emitted non-UTF-8 protocol data") from exc
