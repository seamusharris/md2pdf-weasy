"""macOS sandbox policy and execution for candidate validation commands."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Sequence

from .model import AuditError, SUITE_TIMEOUT
from .process import clean_environment, run_bounded_quiet


@dataclass(frozen=True)
class ValidationCommand:
    label: str
    executable: Path
    arguments: tuple[str, ...]
    expected_version: tuple[int, int] | None = None


def _profile_literal(path: Path) -> str:
    value = str(path)
    if any(ord(character) < 32 for character in value):
        raise AuditError("validation unavailable", "sandbox path contains a control character")
    try:
        value.encode("utf-8", "strict")
    except UnicodeEncodeError as exc:
        raise AuditError("validation unavailable", "sandbox path is not UTF-8") from exc
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _validated_runtime_root(environment: Path, path: Path) -> Path | None:
    if path.is_symlink():
        raise AuditError("validation unavailable", "validation runtime root is unsafe")
    if not path.is_dir():
        return None
    resolved_root = path.resolve(strict=True)
    resolved_environment = environment.resolve(strict=True)
    if resolved_environment not in resolved_root.parents:
        raise AuditError("validation unavailable", "validation runtime root is unsafe")
    return resolved_root


def _runtime_paths(executable: Path) -> tuple[Path, tuple[Path, ...]]:
    """Return one resolved executable plus narrow runtime/dependency read roots."""
    try:
        resolved = executable.resolve(strict=True)
        if not resolved.is_file() or not os.access(resolved, os.X_OK):
            raise AuditError("validation unavailable", "validation interpreter is unavailable")
        launcher = executable.absolute()
        roots: list[Path] = []
        environments = (
            launcher.parent.parent if launcher.parent.name == "bin" else launcher.parent,
            resolved.parent.parent if resolved.parent.name == "bin" else resolved.parent,
        )
        for environment in environments:
            library = environment / "lib"
            if library.is_symlink():
                raise AuditError("validation unavailable", "validation runtime root is unsafe")
            for path in sorted(library.glob("python*")):
                root = _validated_runtime_root(environment, path)
                if root is not None:
                    roots.append(root)
        unique = tuple(dict.fromkeys(roots))
    except OSError as exc:
        raise AuditError("validation unavailable", "validation interpreter is unavailable") from exc
    site_packages = tuple(
        root / "site-packages" for root in unique
        if (root / "site-packages").is_dir() and not (root / "site-packages").is_symlink()
    )
    if not site_packages:
        raise AuditError("validation unavailable", "validation dependencies are unavailable")
    return resolved, unique


def sandbox_profile(
    source: Path, writable: Path, executable: Path,
    runtime_paths: Sequence[Path] | None = None,
) -> str:
    resolved, discovered = _runtime_paths(executable)
    reads = [
        source, *(runtime_paths if runtime_paths is not None else discovered),
        Path("/System"), Path("/usr"), Path("/Library"), Path("/opt/homebrew/lib"),
        Path("/private/var/db/timezone"),
    ]
    clauses = [
        "(version 1)", "(deny default)", "(allow process*)",
        "(deny process-info-setcontrol)", "(deny network*)", "(allow sysctl-read)",
    ]
    for path in reads:
        if path.exists():
            clauses.append(f"(allow file-read* (subpath {_profile_literal(path)}))")
    clauses.extend([
        '(allow file-read-metadata (literal "/"))',
        f"(allow file-read-metadata (subpath {_profile_literal(source.parent)}))",
        '(allow file-read* (literal "/dev/null"))',
        '(allow file-read* (literal "/dev/urandom"))',
        '(allow file-write* (literal "/dev/null"))',
        f"(allow file-write* (subpath {_profile_literal(writable)}))",
        f"(allow file-read* (literal {_profile_literal(resolved)}))",
    ])
    return "\n".join(clauses) + "\n"


def _write_profile(path: Path, content: str) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    descriptor: int | None = None
    primary: OSError | None = None
    try:
        raw = content.encode("utf-8", "strict")
    except UnicodeEncodeError as exc:
        raise AuditError(
            "validation unavailable", "private sandbox profile is not UTF-8",
        ) from exc
    try:
        descriptor = os.open(path, flags, 0o600)
        view = memoryview(raw)
        while view:
            written = os.write(descriptor, view)
            view = view[written:]
    except OSError as exc:
        primary = exc
    finally:
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError as exc:
                raise AuditError(
                    "validation unavailable", "private sandbox profile could not be finalized",
                    residue=True,
                ) from (primary or exc)
    if primary is not None:
        raise AuditError(
            "validation unavailable", "private sandbox profile could not be created",
        ) from primary


def run_validation_command(
    command: ValidationCommand, *, command_index: int, source: Path,
    writable: Path, home: Path, temporary: Path,
) -> None:
    executable, runtime_paths = _runtime_paths(command.executable)
    site_packages = tuple(
        path / "site-packages" for path in runtime_paths
        if (path / "site-packages").is_dir()
    )
    if not executable.is_file() or not os.access(executable, os.X_OK) or not site_packages:
        raise AuditError("validation unavailable", "validation interpreter is unavailable")
    profile_path = writable / f"sandbox-{command_index}.sb"
    _write_profile(profile_path, sandbox_profile(source, writable, command.executable, runtime_paths))
    environment = clean_environment({
        "HOME": str(home), "TMPDIR": str(temporary),
        "PYTHONDONTWRITEBYTECODE": "1", "PYTHONNOUSERSITE": "1",
        "PYTHONPATH": os.pathsep.join(map(str, site_packages)),
        "PYTEST_ADDOPTS": "-p no:cacheprovider",
        "DYLD_FALLBACK_LIBRARY_PATH": "/opt/homebrew/lib",
    })
    _sandbox_probe(
        ("/usr/bin/sandbox-exec", "-f", str(profile_path), "/usr/bin/true"),
        source=source, environment=environment, label="sandbox startup probe",
        failure="sandbox-exec failed its startup probe",
    )
    if command.expected_version is not None:
        major, minor = command.expected_version
        _sandbox_probe(
            ("/usr/bin/sandbox-exec", "-f", str(profile_path), str(executable),
             "-I", "-c", f"import sys;raise SystemExit(sys.version_info[:2] != ({major},{minor}))"),
            source=source, environment=environment, label="validation interpreter identity",
            failure="validation interpreter version is incorrect",
        )
    run_bounded_quiet(
        ("/usr/bin/sandbox-exec", "-f", str(profile_path), "/usr/bin/env", "-i",
         *(f"{key}={value}" for key, value in sorted(environment.items())),
         str(executable), *command.arguments),
        cwd=source, env=environment, timeout=SUITE_TIMEOUT, label=command.label,
        resource_limits=True, memory_limit_bytes=4 * 1024 * 1024 * 1024,
        session_wrapper=True,
    )


def _sandbox_probe(
    command: tuple[str, ...], *, source: Path, environment: dict[str, str],
    label: str, failure: str,
) -> None:
    try:
        run_bounded_quiet(
            command, cwd=source, env=environment, timeout=15, label=label,
            resource_limits=True, memory_limit_bytes=512 * 1024 * 1024,
            session_wrapper=True,
        )
    except AuditError as exc:
        if exc.residue:
            raise
        raise AuditError("validation unavailable", failure) from exc
