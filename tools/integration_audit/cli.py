"""Command-line interface for immutable candidate audits."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
import tempfile

from .audit import audit_candidate
from .history import CANDIDATE_COMMIT
from .isolate import ValidationCommand
from .model import AuditError
from .verifier import verify_downstream


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m tools.integration_audit")
    subparsers = parser.add_subparsers(dest="command", required=True)
    audit = subparsers.add_parser("audit", help="audit the fixed immutable candidate")
    audit.add_argument("candidate")
    audit.add_argument("--root", type=Path, default=Path.cwd())
    audit.add_argument("--private-parent", type=Path, default=Path(tempfile.gettempdir()))
    audit.add_argument("--python313", type=Path, required=True)
    audit.add_argument("--current-python", type=Path, required=True)
    verify = subparsers.add_parser("verify-downstream", help="verify published audit evidence")
    verify.add_argument("--root", type=Path, default=Path.cwd())
    return parser


def _validation_commands(python313: Path, current: Path) -> tuple[ValidationCommand, ...]:
    suite = ("-m", "pytest", "-q", "-p", "no:cacheprovider")
    focused = (
        "-m", "pytest", "-q", "-p", "no:cacheprovider",
        "tests/test_visual_acceptance.py", "tests/test_compatibility.py",
    )
    return (
        ValidationCommand("python-3.13-full-suite", python313, suite, (3, 13)),
        ValidationCommand(
            "current-interpreter-full-suite", current, suite,
            (sys.version_info.major, sys.version_info.minor),
        ),
        ValidationCommand("visual-and-v0.1-compatibility", python313, focused, (3, 13)),
    )


def _write_stdout(content: bytes) -> bool:
    try:
        stdout = sys.stdout
        if stdout is None:
            return False
        output = stdout.buffer
        pending = memoryview(content)
        while pending:
            written = output.write(pending)
            if (
                not isinstance(written, int) or isinstance(written, bool)
                or written <= 0 or written > len(pending)
            ):
                return False
            pending = pending[written:]
        output.flush()
    except (AttributeError, OSError, ValueError):
        return False
    return True


def _write_error(error: AuditError) -> None:
    try:
        stderr = sys.stderr
        if stderr is not None:
            stderr.write(f"{error}\n")
    except (AttributeError, OSError, ValueError):
        pass


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        if arguments.command == "audit":
            if arguments.candidate != CANDIDATE_COMMIT:
                raise AuditError("invalid request", "candidate is not the fixed T-015 object")
            try:
                root = arguments.root.resolve(strict=True)
                private_parent = arguments.private_parent.resolve(strict=True)
            except OSError as exc:
                raise AuditError("invalid request", "audit directory is unavailable") from exc
            result = audit_candidate(
                root, arguments.candidate, private_parent=private_parent,
                validation_commands=_validation_commands(arguments.python313, arguments.current_python),
            )
            status = 0 if result.decision == "go-for-local-integration-gates" else 1
            return status if _write_stdout(result.to_bytes()) else 1
        try:
            root = arguments.root.resolve(strict=True)
        except OSError as exc:
            raise AuditError("invalid request", "repository root is unavailable") from exc
        commit = verify_downstream(root)
        return 0 if _write_stdout(f"{commit}\n".encode("ascii")) else 1
    except AuditError as exc:
        _write_error(exc)
        return 2 if exc.category == "invalid request" else 1
