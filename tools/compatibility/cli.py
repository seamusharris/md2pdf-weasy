"""Thin coordinator for v0.1.0 rendering compatibility acceptance."""

from __future__ import annotations

import argparse
import contextlib
import os
from pathlib import Path
import re
import shutil
import sys
import time
from typing import Any

from .history import export_tag, remove_private_export, resolve_tag
from .model import (
    MAX_DIAGNOSTIC_BYTES, MATRIX_TIMEOUT, MODE_IDS, CompatibilityError,
    signed_manifest, validate_failure, validate_manifest,
)
from .store import (
    CANDIDATE_ROOT, PENDING_MARKER, allocate_candidate, atomic_json,
    candidate_lease, prune, discard_allocated_candidate, tree_stats,
    validate_candidate_path,
)
from .structure import classify


# Re-exported private aliases keep tests focused on the coordinator while
# ownership remains in cohesive modules.
from .artifacts import contact_sheet as _contact_sheet, render as _render, source_for_mode
from .provenance import (
    CHECKED_DECISION, FIXTURE, ROOT,
    capture_generation_provenance,
    snapshot_current_renderer,
)
from .verification import (
    read_manifest, reject_unverifiable_markers, verify_candidate_evidence,
    verify_live_provenance,
)


def _cleanup_failure(candidate: Path) -> list[str]:
    notes = []
    for child in list(candidate.iterdir()):
        if child.name in {".lease", ".pin", "failure.json", PENDING_MARKER}:
            continue
        try:
            if child.is_dir() and not child.is_symlink():
                shutil.rmtree(child)
            else:
                child.unlink()
        except OSError as exc:
            notes.append(f"could not remove {child.name}: {type(exc).__name__}")
    return notes


def _build_manifest(
    *, provenance: dict[str, Any], cases: list[dict[str, Any]],
    checks: list[dict[str, Any]], contact: dict[str, Any],
) -> dict[str, Any]:
    return signed_manifest({
        "schema_version": 1,
        "kind": "md2pdf-v0.1-compatibility",
        "provenance": provenance,
        "cases": cases,
        "checks": checks,
        "contact_sheet": contact,
        "decision": "compatible-with-intentional-default-presentation-change",
    })


def _generate_candidate(candidate: Path, started: float) -> None:
    private = candidate / "_private"
    tag_commit = resolve_tag(ROOT)
    provenance = capture_generation_provenance(tag_commit)
    current_parent, snapshot_fixture = snapshot_current_renderer(
        private / "current", provenance["source_hashes"],
    )
    legacy_parent = export_tag(ROOT, private / "legacy")
    source_text = snapshot_fixture.read_text(encoding="utf-8")
    inputs = candidate / "inputs"
    artifacts = candidate / "artifacts"
    inputs.mkdir(mode=0o700)
    artifacts.mkdir(mode=0o700)
    cases = []
    for mode in MODE_IDS:
        if time.monotonic() - started > MATRIX_TIMEOUT:
            raise CompatibilityError("compatibility matrix timed out", category="timeout", phase="matrix", case=mode)
        mode_source = inputs / f"{mode}.md"
        mode_source.write_text(source_for_mode(mode, source_text), encoding="utf-8")
        cases.append(_render(mode, mode_source, artifacts / mode, legacy_parent, current_parent))
    checks = classify({case["id"]: case for case in cases})
    failures = [check["id"] for check in checks if check["status"] != "pass"]
    if failures:
        raise CompatibilityError("compatibility blockers: " + ", ".join(failures), category="verify", phase="classify")
    contact = _contact_sheet(candidate, cases)
    remove_private_export(private)
    manifest = _build_manifest(
        provenance=provenance, cases=cases, checks=checks, contact=contact,
    )
    validate_manifest(manifest)
    tree_stats(candidate)
    atomic_json(candidate / "decision.json", manifest)
    atomic_json(candidate / "manifest.json", manifest)
    atomic_json(
        candidate / PENDING_MARKER,
        {"decision_digest": manifest["decision_digest"]},
    )
    tree_stats(candidate)
    _commit_success(candidate)


def _commit_success(candidate: Path) -> None:
    """Make success visible as the terminal, atomic generation operation."""
    os.replace(candidate / PENDING_MARKER, candidate / "success.json")


def _record_generation_failure(candidate: Path, exc: BaseException) -> Path:
    category = exc.category if isinstance(exc, CompatibilityError) else "internal"
    phase = exc.phase if isinstance(exc, CompatibilityError) else "generate"
    case = exc.case if isinstance(exc, CompatibilityError) else None
    diagnostic = _sanitize_diagnostic(exc, candidate)
    failure = {"schema_version": 1, "kind": "md2pdf-v0.1-compatibility-failure",
               "category": category, "phase": phase, "case": case,
               "diagnostic": diagnostic, "cleanup_notes": []}
    validate_failure(failure)
    path = candidate / "failure.json"
    publication_error: OSError | None = None
    try:
        atomic_json(path, failure)
    except OSError as exc:
        publication_error = exc
    cleanup = _cleanup_failure(candidate)
    if publication_error is not None or cleanup:
        failure["cleanup_notes"] = cleanup
        atomic_json(path, failure)
    return path


def _sanitize_diagnostic(exc: BaseException, candidate: Path | None = None) -> str:
    text = str(exc)
    replacements = [(str(ROOT), "<repo>"), (str(CANDIDATE_ROOT), "<candidate-root>")]
    if candidate is not None:
        replacements.insert(0, (str(candidate), "<candidate>"))
    for raw, replacement in sorted(replacements, key=lambda item: len(item[0]), reverse=True):
        text = text.replace(raw, replacement)
    text = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", text)
    text = re.sub(r"[\x00-\x1f\x7f]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text.encode("utf-8", "replace")[:MAX_DIAGNOSTIC_BYTES].decode("utf-8", "ignore")


def generate(*, candidate_root: Path = CANDIDATE_ROOT) -> Path:
    candidate = allocate_candidate(candidate_root)
    entered = False
    try:
        with candidate_lease(candidate, root=candidate_root):
            entered = True
            try:
                atomic_json(candidate / PENDING_MARKER, {"state": "generating"})
                _generate_candidate(candidate, time.monotonic())
            except BaseException as exc:
                try:
                    record = _record_generation_failure(candidate, exc)
                except BaseException as cleanup_exc:
                    print(f"compatibility generation cleanup failed: {type(cleanup_exc).__name__}", file=sys.stderr)
                else:
                    print(f"compatibility generation failed; record: {record}", file=sys.stderr)
                raise
    except BaseException:
        if not entered:
            try:
                discard_allocated_candidate(candidate, candidate_root)
            except BaseException as rollback_exc:
                print(
                    f"compatibility allocation rollback failed: {type(rollback_exc).__name__}",
                    file=sys.stderr,
                )
        raise
    print(candidate)
    return candidate


def verify(
    path: Path | None = None, *, attest_tag: bool | None = None,
    candidate_root: Path = CANDIDATE_ROOT,
) -> Path:
    candidate = None if path is None else validate_candidate_path(path, candidate_root)
    target = CHECKED_DECISION if candidate is None else candidate / "manifest.json"
    lease = contextlib.nullcontext() if candidate is None else candidate_lease(candidate, root=candidate_root)
    with lease:
        if candidate is not None:
            reject_unverifiable_markers(candidate)
            tree_stats(candidate)
        value = read_manifest(target)
        verify_live_provenance(
            value,
            attest_tag=attest_tag if attest_tag is not None else candidate is not None,
        )
        if candidate is not None:
            verify_candidate_evidence(candidate, value)
    print(target)
    return target


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("generate")
    verify_parser = commands.add_parser("verify")
    verify_parser.add_argument("candidate", nargs="?", type=Path)
    prune_parser = commands.add_parser("prune")
    prune_parser.add_argument("--dry-run", action="store_true")
    prune_parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.command == "generate":
            generate()
        elif args.command == "verify":
            verify(args.candidate)
        else:
            if args.dry_run == args.apply:
                parser.error("prune requires exactly one of --dry-run or --apply")
            for name in prune(apply=args.apply):
                print(name)
        return 0
    except CompatibilityError as exc:
        print(f"compatibility error: {_sanitize_diagnostic(exc)}", file=sys.stderr)
        return 1
    except Exception as exc:
        diagnostic = _sanitize_diagnostic(exc)
        print(f"compatibility error: {type(exc).__name__}: {diagnostic}", file=sys.stderr)
        return 1
