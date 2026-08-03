"""Thin authorization-first coordinator for downstream canary coverage."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import Callable

from tools.distribution_entitlement import PreflightError, preflight as entitlement_preflight

from .lifecycle import Lease, run_ephemeral
from .model import (
    CanaryError,
    RunRequest,
    parse_json_bytes,
    result_json,
    select_consumer,
    validate_registry,
)
from .provenance import (
    assert_unchanged,
    capture_snapshot,
    load_candidate_inputs,
    stage_verified_package,
)
from .scenarios import run_scenarios


def run(
    root: Path,
    request: RunRequest,
    lease_path: Path,
    temp_parent: Path,
    *,
    publish: Callable[[str], None] = print,
) -> None:
    """Run and publish while the consumer-workflow lease remains held."""

    try:
        entitlement = entitlement_preflight(
            root, "consumer_canary", request.environment_id, request.recipient_id
        )
    except PreflightError as exc:
        raise CanaryError("entitlement denied", exc.detail, 2) from exc

    inputs = load_candidate_inputs(root, request, entitlement["git_tree"])
    registry = validate_registry(parse_json_bytes(inputs.registry, "consumer registry"))
    select_consumer(registry, request)
    with Lease(lease_path):
        before = capture_snapshot(root, request, inputs)

        def execute(workspace: Path) -> tuple[str, ...]:
            package_root = stage_verified_package(before, workspace)
            return run_scenarios(
                workspace,
                package_root,
                before.package_root.parent,
                inputs.fixture,
                inputs.resource,
            )

        checks = run_ephemeral(
            temp_parent,
            execute,
        )
        after = capture_snapshot(root, request, inputs)
        assert_unchanged(before, after)
        publish(result_json(request, before.tree, before.input_digest, checks))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run an authorized canary in a dedicated consumer-owned environment."
    )
    parser.add_argument("--consumer", required=True)
    parser.add_argument("--environment", required=True)
    parser.add_argument("--recipient", required=True)
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--rollback", required=True)
    parser.add_argument("--opt-out", required=True)
    parser.add_argument("--lease-path", required=True, type=Path)
    parser.add_argument("--temp-parent", required=True, type=Path)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        request = RunRequest.create(
            args.consumer,
            args.environment,
            args.recipient,
            args.candidate,
            args.rollback,
            args.opt_out,
        )
        run(args.root.resolve(), request, args.lease_path, args.temp_parent)
    except CanaryError as exc:
        print(f"downstream canary: {exc.category}: {exc.detail}", file=sys.stderr)
        if exc.cleanup_warning:
            print(
                "downstream canary: cleanup warning: ephemeral residue may remain",
                file=sys.stderr,
            )
        return exc.exit_code
    except Exception:
        print("downstream canary: unexpected failure: no result published", file=sys.stderr)
        return 11
    return 0
