"""Command-line interface for local packaging-gate evidence."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

from tools.integration_audit.model import AuditError

from .gate import run
from .model import GateError


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Evaluate local packaging prerequisites without creating artifacts."
    )
    parser.add_argument("--root", type=Path, default=Path.cwd())
    return parser


def _write(stream: object, content: bytes) -> bool:
    try:
        output = getattr(stream, "buffer")
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


def _diagnostic(error: GateError) -> None:
    try:
        stderr = sys.stderr
        if stderr is not None:
            stderr.write(f"local packaging gate: {error.category}: {error.detail}\n")
    except (AttributeError, OSError, ValueError):
        pass


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        root = arguments.root.resolve(strict=True)
        run(root, lambda raw: _write(sys.stdout, raw))
    except GateError as exc:
        _diagnostic(exc)
        return exc.exit_code
    except (AuditError, OSError) as exc:
        _diagnostic(GateError("gate unavailable", "local packaging prerequisites are unavailable"))
        return 3
    except Exception:
        _diagnostic(GateError("unexpected failure", "no packaging-gate evidence produced"))
        return 5
    return 1
