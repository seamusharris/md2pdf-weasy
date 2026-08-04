"""Shared lexical policy for repository-relative protocol paths."""

from __future__ import annotations

from pathlib import PurePosixPath

from .model import AuditError


def require_relative_path(
    value: str, *, category: str, detail: str, max_depth: int | None = None,
) -> PurePosixPath:
    path = PurePosixPath(value)
    if (
        not value
        or path.is_absolute()
        or (max_depth is not None and len(path.parts) > max_depth)
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise AuditError(category, detail)
    return path
