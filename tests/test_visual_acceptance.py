"""Deterministic contracts for the T-009 visual-acceptance workflow."""

from __future__ import annotations

import dataclasses
import contextlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time

import pytest

from tools import visual_acceptance as visual


def _fragment(widths, *, page=1, x=40, y=40, height=100, cells=None):
    row = []
    cursor = x
    for width in widths:
        row.append({"x": cursor, "y": y + 20, "width": width, "height": 20})
        cursor += width
    cells = cells or []
    for index, cell in enumerate(cells):
        cell.setdefault("x", x + min(index, len(widths) - 1) * 10)
        cell.setdefault("y", y + 20)
        cell.setdefault("width", 10)
        cell.setdefault("height", 20)
    return {
        "page": page,
        "x": x,
        "y": y,
        "width": sum(widths),
        "height": height,
        "rows": [[dict(cell) for cell in row], [dict(cell) for cell in row]],
        "cells": cells,
    }


def _passing_measurements(*, landscape=False):
    ladder = [120, 25, 25, 25, 25, 35, 35, 45]
    schedule = [45, 35, 110, 110, 70]
    page = {"page": 1, "width": 900 if landscape else 600,
            "height": 700 if landscape else 800}
    ids = {
        "ladder-primary": [_fragment(ladder)],
        "ladder-secondary": [_fragment(ladder, y=160)],
        "schedule-morning": [_fragment(schedule, y=280)],
        "schedule-evening": [_fragment(schedule, y=400)],
        "summary-risk": [_fragment([80, 140, 90, 60], y=520)],
        "semantic-states": [_fragment([100, 100, 100], y=40)],
        "overwide-table": [_fragment([40] * 12, y=160)],
        "prose-table": [_fragment(
            [90, 120, 280],
            y=280,
            cells=[
                {"text": "SingleLineSentinel", "lines": 1},
                {"text": "This deliberately longer sentence wraps", "lines": 2},
                {"text": "https://example.invalid/synthetic/long", "lines": 3},
            ],
        )],
    }
    return {
        "pages": [page],
        "tables": ids,
        "width_activation": {
            "ladder-primary": True,
            "ladder-secondary": True,
            "schedule-morning": True,
            "schedule-evening": True,
        },
    }


def _environment():
    return {
        "python": "3.13.0",
        "packages": {name: "1.0" for name in visual.RENDER_DEPENDENCIES},
        "poppler": "poppler 1",
        "pango": "1.0",
        "platform": "test-platform",
        "machine": "test-machine",
        "raster": {
            "format": "PNG", "color": "RGB", "dpi": visual.RASTER_DPI,
            "thumbnail_width_px": visual.THUMB_WIDTH,
            "sheet_columns": visual.SHEET_COLUMNS,
        },
    }


def _passing_semantics(*args, **kwargs):
    return (
        [
            visual.CheckResult(check_id, "passed", "test")
            for check_id in visual.SEMANTIC_CHECK_IDS
        ],
        "",
    )


def _object_evidence(*args, **kwargs):
    return {
        "graph_sha256": "a" * 64,
        "pages": [{
            "page": 1, "media_width_pt": 1.0, "media_height_pt": 1.0,
            "crop_width_pt": 1.0, "crop_height_pt": 1.0,
        }],
        "object_count": 1,
        "decoded_stream_bytes": 1,
    }


def _bind_manifest_pdf(manifest, case_id, pdf):
    digest = visual._sha256(pdf)
    size = pdf.stat().st_size
    record = next(item for item in manifest["cases"] if item["case_id"] == case_id)
    record["pdf_bytes"] = size
    record["pdf_sha256"] = digest
    reviewed = next(
        item for item in manifest["review_artifacts"]
        if item["path"] == f"cases/{case_id}/{case_id}.pdf"
    )
    reviewed["bytes"] = size
    reviewed["sha256"] = digest


def _manifest(*, marker="a", artifacts=None, reviewed=None, baseline=None):
    input_hashes = {"tests/visual/source.md": marker * 64}
    digest = visual._input_digest(input_hashes)
    cases = []
    for case in visual.acceptance_cases():
        cases.append({
            "case_id": case.case_id,
            "case": dataclasses.asdict(case),
            "pdf": f"{case.case_id}.pdf",
            "pdf_bytes": 1,
            "pdf_sha256": marker * 64,
            "measurements": {"pages": [{"page": 1, "width": 1, "height": 1}]},
            "checks": [
                {"check_id": check_id, "status": "passed", "detail": "test"}
                for check_id in visual.GEOMETRY_CHECK_IDS
            ],
            "semantic_checks": [
                {"check_id": check_id, "status": "passed", "detail": "test"}
                for check_id in visual.SEMANTIC_CHECK_IDS
            ],
            "pages": [f"cases/{case.case_id}/page-1.png"],
        })
    if artifacts is None:
        artifacts = [
            {
                "path": f"contact-sheets/{case.case_id}.png",
                "bytes": 1,
                "sha256": marker * 64,
            }
            for case in visual.acceptance_cases()
        ]
    if reviewed is None:
        reviewed = []
        for case in visual.acceptance_cases():
            reviewed.extend((
                {
                    "path": f"cases/{case.case_id}/{case.case_id}.pdf",
                    "kind": "pdf", "bytes": 1, "sha256": marker * 64,
                },
                {
                    "path": f"cases/{case.case_id}/page-1.png",
                    "kind": "page", "bytes": 1, "sha256": marker * 64,
                    "width": 1, "height": 1,
                },
            ))
    return {
        "schema_version": visual.SCHEMA_VERSION,
        "status": "passed",
        "candidate_id": f"candidate-{marker}",
        "review_baseline": baseline,
        "source": {"digest": digest, "input_hashes": input_hashes},
        "environment": _environment(),
        "cases": cases,
        "review_artifacts": reviewed,
        "promotable_artifacts": artifacts,
    }


def test_acceptance_matrix_covers_every_theme_and_contract_variant():
    cases = visual.acceptance_cases()
    assert [case.theme for case in cases[:5]] == list(visual.THEMES)
    assert any(case.declared for case in cases)
    assert any(not case.table_widths for case in cases)
    assert {case.orientation for case in cases} == {"portrait", "landscape"}
    assert any(case.page_width_em for case in cases)
    assert len({case.case_id for case in cases}) == len(cases)


def test_fixture_is_explicitly_synthetic_and_has_stable_semantic_tables():
    source = visual.SOURCE.read_text(encoding="utf-8")
    assert "Invented content only" in source
    for table_id in (
        "ladder-primary", "ladder-secondary", "schedule-morning",
        "schedule-evening", "summary-risk", "prose-table",
        "semantic-states", "overwide-table",
    ):
        assert f'id="{table_id}"' in source
    assert 'scope="col"' in source
    assert 'headers="lp-r1 lp-p"' in source


def test_declared_and_legacy_sources_apply_only_the_case_overlay():
    declared = next(case for case in visual.acceptance_cases() if case.declared)
    legacy = next(case for case in visual.acceptance_cases() if not case.table_widths)
    declared_source = visual._case_source(declared)
    legacy_source = visual._case_source(legacy)
    assert "declared-ladder" in declared_source
    assert "preset: netball-ladder-v1" in declared_source
    assert "table_widths: false" in legacy_source
    assert "declared-ladder" not in legacy_source


@pytest.mark.parametrize("raw", [
    "", "/absolute.png", "../escape.png", "a/../escape.png",
    "./dot.png", "a\\windows.png",
])
def test_manifest_paths_reject_unsafe_components(raw):
    with pytest.raises(visual.AcceptanceError):
        visual._safe_relative_path(raw)


def test_manifest_paths_accept_repo_relative_posix_path():
    assert str(visual._safe_relative_path("contact-sheets/a.png")) == (
        "contact-sheets/a.png"
    )


@pytest.mark.parametrize("mutation", [
    lambda value: value.update(schema_version=999),
    lambda value: value.update(status="failed"),
    lambda value: value.update(cases=[]),
    lambda value: value.update(promotable_artifacts=[]),
    lambda value: value["promotable_artifacts"].append(
        value["promotable_artifacts"][0].copy()
    ),
    lambda value: value["cases"].append("unexpected"),
])
def test_manifest_schema_fails_closed(mutation):
    value = _manifest()
    mutation(value)
    with pytest.raises(visual.AcceptanceError):
        visual._validate_manifest_shape(value)


def test_manifest_json_is_deterministic_and_round_trips():
    value = _manifest()
    encoded = visual._json_bytes(value)
    assert encoded == visual._json_bytes(value)
    assert json.loads(encoded) == value
    assert encoded.endswith(b"\n")


@pytest.mark.parametrize("mutation", [
    lambda value: value["source"].update(digest="../../escape"),
    lambda value: value["source"]["input_hashes"].update(
        {"tests/visual/source.md": "0" * 64}
    ),
    lambda value: value["cases"][0]["checks"][0].update(status="failed"),
    lambda value: value["cases"][0].update(case={}),
    lambda value: value["environment"]["packages"].pop("weasyprint"),
    lambda value: value["promotable_artifacts"].pop(),
])
def test_manifest_nested_contract_fails_closed(mutation):
    value = _manifest()
    mutation(value)
    with pytest.raises(visual.AcceptanceError):
        visual._validate_manifest_shape(value)


def test_geometry_contract_accepts_independent_passing_measurements():
    case = visual.AcceptanceCase("test", "neutral")
    results = visual.check_measurements(_passing_measurements(), case)
    assert results
    assert {result.status for result in results} == {"passed"}


@pytest.mark.parametrize("defect,failed_check", [
    ("missing", "tables-present"),
    ("orientation", "orientation"),
    ("overflow", "page-overflow"),
    ("cell", "cell-containment"),
    ("boundaries", "column-boundaries"),
    ("shared-ladder", "shared-ladder-widths"),
    ("shared-schedule", "shared-schedule-widths"),
    ("inactive-ladder", "shared-ladder-widths"),
    ("single", "single-line-sentinel"),
    ("wrap", "wrap-sentinels"),
])
def test_each_geometry_detector_has_an_independent_negative_witness(
    defect, failed_check,
):
    data = _passing_measurements()
    case = visual.AcceptanceCase("test", "neutral")
    if defect == "missing":
        data["tables"].pop("summary-risk")
    elif defect == "orientation":
        data["pages"][0].update(width=1200, height=1000)
    elif defect == "overflow":
        data["tables"]["overwide-table"][0]["width"] = 900
    elif defect == "cell":
        data["tables"]["prose-table"][0]["cells"][0]["x"] = 999
    elif defect == "boundaries":
        data["tables"]["summary-risk"][0]["rows"][1][0]["x"] += 3
    elif defect == "shared-ladder":
        for row in data["tables"]["ladder-secondary"][0]["rows"]:
            row[5]["width"] += 3
    elif defect == "shared-schedule":
        for row in data["tables"]["schedule-evening"][0]["rows"]:
            row[2]["width"] += 3
    elif defect == "inactive-ladder":
        data["width_activation"]["ladder-secondary"] = False
    elif defect == "single":
        data["tables"]["prose-table"][0]["cells"][0]["lines"] = 2
    else:
        data["tables"]["prose-table"][0]["cells"][1]["lines"] = 1
    results = {result.check_id: result for result in visual.check_measurements(data, case)}
    assert results[failed_check].status == "failed"
    assert {
        check_id for check_id, result in results.items() if result.status == "failed"
    } == {failed_check}


def test_width_activation_requires_colgroups_on_stable_fixture_tables():
    html = """
    <table id="ladder-primary"><colgroup></colgroup></table>
    <table id='ladder-secondary'><tbody></tbody></table>
    <table class="x" id="schedule-morning"><COLGROUP></COLGROUP></table>
    <table id="schedule-evening"><colgroup></colgroup></table>
    """
    assert visual._width_activation(html) == {
        "ladder-primary": True,
        "ladder-secondary": False,
        "schedule-morning": True,
        "schedule-evening": True,
    }


def test_landscape_measurement_passes_landscape_case():
    case = visual.AcceptanceCase("landscape", "neutral", orientation="landscape")
    results = visual.check_measurements(_passing_measurements(landscape=True), case)
    assert all(result.status == "passed" for result in results)


def test_declared_proportion_detector_accepts_and_rejects_independently():
    data = _passing_measurements()
    widths = [24, 6, 6, 6, 6, 8, 8, 10]
    data["tables"]["ladder-primary"] = [_fragment(widths)]
    case = visual.AcceptanceCase("declared", "neutral", declared=True)
    passing = {r.check_id: r for r in visual.check_measurements(data, case)}
    assert passing["declared-proportions"].status == "passed"
    for row in data["tables"]["ladder-primary"][0]["rows"]:
        row[0]["width"] += 50
    failing = {r.check_id: r for r in visual.check_measurements(data, case)}
    assert failing["declared-proportions"].status == "failed"
    assert failing["column-boundaries"].status == "passed"


def test_run_checked_reports_missing_executable():
    with pytest.raises(visual.AcceptanceError, match="executable not found"):
        visual._run_checked(
            ["definitely-not-a-real-visual-acceptance-command"],
            timeout=0.1,
            context="synthetic-case: raster",
        )


def test_run_checked_bounds_nonzero_diagnostics(monkeypatch):
    with pytest.raises(visual.AcceptanceError) as error:
        visual._run_checked(
            [
                sys.executable, "-c",
                "import sys;sys.stderr.write('x'*33000);sys.exit(9)",
            ],
            timeout=2,
            context="case: raster",
        )
    assert len(str(error.value)) < visual.MAX_STDERR_BYTES + 100
    assert "exited 9" in str(error.value)


def test_run_checked_rejects_live_output_over_capture_budget():
    started = time.monotonic()
    with pytest.raises(visual.AcceptanceError, match="output exceeded"):
        visual._run_checked(
            [
                sys.executable, "-c",
                "import os\nwhile True: os.write(1, b'x' * 65536)",
            ],
            timeout=5,
            context="case: noisy worker",
        )
    assert time.monotonic() - started < 3


def test_run_checked_kills_timed_out_process_group_promptly():
    started = time.monotonic()
    with pytest.raises(visual.AcceptanceError, match="timed out"):
        visual._run_checked(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            timeout=0.05,
            context="case: sleeping worker",
        )
    assert time.monotonic() - started < 2


def test_run_checked_times_out_after_child_closes_captured_streams():
    started = time.monotonic()
    with pytest.raises(visual.AcceptanceError, match="timed out"):
        visual._run_checked(
            [
                sys.executable, "-c",
                "import os,time;os.close(1);os.close(2);time.sleep(30)",
            ],
            timeout=0.05,
            context="case: closed-stream worker",
        )
    assert time.monotonic() - started < 2


def test_run_checked_kills_child_when_capture_is_interrupted(monkeypatch):
    processes = []
    original_popen = visual.subprocess.Popen
    original_selector = visual.selectors.DefaultSelector

    def capture_process(*args, **kwargs):
        process = original_popen(*args, **kwargs)
        processes.append(process)
        return process

    class InterruptingSelector(original_selector):
        def select(self, timeout=None):
            raise KeyboardInterrupt

    monkeypatch.setattr(visual.subprocess, "Popen", capture_process)
    monkeypatch.setattr(visual.selectors, "DefaultSelector", InterruptingSelector)
    with pytest.raises(KeyboardInterrupt):
        visual._run_checked(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            timeout=10,
            context="case: interrupted worker",
        )
    assert processes and processes[0].poll() is not None


def test_environment_rejects_empty_pdfinfo_version_output(monkeypatch):
    def empty_version(args, **kwargs):
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

    monkeypatch.setattr(visual, "_run_checked", empty_version)
    monkeypatch.setattr(
        visual.importlib.metadata, "version", lambda name: "1.0",
    )
    with pytest.raises(visual.AcceptanceError, match="version output is empty"):
        visual._environment()


def test_pdf_semantic_checks_require_roles_headers_caption_and_order(
    tmp_path, monkeypatch,
):
    structure = """Document
  Table
    Caption
      Primary synthetic ladder
    THead
      TR
        TH <1>
    TBody
      TR
        TD:
          /Headers [(1)]
  North Comets
  Prose wrapping sentinels
""" + "\n".join("/Headers [(1)]" for _ in range(11))
    extracted = "Primary synthetic ladder\nNorth Comets\nProse wrapping sentinels\n"
    outputs = iter((structure, extracted))

    def successful(*args, **kwargs):
        return subprocess.CompletedProcess(args[0], 0, stdout=next(outputs), stderr="")

    monkeypatch.setattr(visual, "_run_checked", successful)
    checks, returned = visual._pdf_semantic_checks(tmp_path / "case.pdf", timeout=1)
    assert returned == structure
    assert all(check.status == "passed" for check in checks)


@pytest.mark.parametrize("defect,failed_check", [
    ("role", "pdf-table-tags"),
    ("caption", "pdf-caption"),
    ("owner", "pdf-caption-owner"),
    ("headers", "pdf-header-associations"),
    ("tag-order", "pdf-tagged-order"),
    ("stream-order", "pdf-content-order"),
])
def test_each_pdf_semantic_detector_has_an_independent_negative(
    defect, failed_check, tmp_path, monkeypatch,
):
    structure = """Document
  Table
    Caption
      Primary synthetic ladder
    THead
      TR
        TH <1>
    TBody
      TR
        TD:
          /Headers [(1)]
  North Comets
  Prose wrapping sentinels
""" + "\n".join("/Headers [(1)]" for _ in range(11))
    extracted = "Primary synthetic ladder\nNorth Comets\nProse wrapping sentinels\n"
    if defect == "role":
        structure = structure.replace("TBody", "Body")
    elif defect == "caption":
        structure = structure.replace("Document\n", "Document\n  Primary synthetic ladder\n")
        structure = structure.replace(
            "      Primary synthetic ladder", "      Missing caption",
        )
    elif defect == "owner":
        structure = structure.replace(
            "    Caption\n      Primary synthetic ladder\n    THead",
            "    THead\n    Caption\n      Primary synthetic ladder",
        )
    elif defect == "headers":
        structure = structure.replace("/Headers", "/Header")
    elif defect == "tag-order":
        structure = structure.replace(
            "  North Comets\n  Prose wrapping sentinels",
            "  Prose wrapping sentinels\n  North Comets",
        )
    else:
        extracted = "Prose wrapping sentinels\nNorth Comets\nPrimary synthetic ladder\n"
    outputs = iter((structure, extracted))
    monkeypatch.setattr(
        visual,
        "_run_checked",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args[0], 0, stdout=next(outputs), stderr=""
        ),
    )
    checks, _ = visual._pdf_semantic_checks(tmp_path / "case.pdf", timeout=1)
    by_id = {check.check_id: check for check in checks}
    assert by_id[failed_check].status == "failed"
    assert {
        check_id for check_id, check in by_id.items() if check.status == "failed"
    } == {failed_check}


def test_worker_requires_a_result_file(tmp_path, monkeypatch):
    case = visual.AcceptanceCase("worker-case", "neutral")
    monkeypatch.setattr(visual, "_run_checked", lambda *args, **kwargs: subprocess.CompletedProcess(
        args[0], 0, stdout="", stderr=""
    ))
    with pytest.raises(visual.AcceptanceError, match="worker returned no result"):
        visual._run_worker(case, tmp_path, timeout=0.01)


def test_worker_rejects_malformed_result(tmp_path, monkeypatch):
    case = visual.AcceptanceCase("worker-case", "neutral")

    def malformed(*args, **kwargs):
        (tmp_path / "worker-result.json").write_text("{bad")
        return subprocess.CompletedProcess(args[0], 0, stdout="", stderr="")

    monkeypatch.setattr(visual, "_run_checked", malformed)
    with pytest.raises(visual.AcceptanceError, match="result is unreadable"):
        visual._run_worker(case, tmp_path, timeout=0.01)


@pytest.mark.parametrize("defect,match", [
    ("identity", "identity mismatch"),
    ("hash", "PDF mismatch"),
    ("size", "PDF mismatch"),
])
def test_worker_rejects_tampered_success_result(
    tmp_path, monkeypatch, defect, match,
):
    case = visual.AcceptanceCase("worker-case", "neutral")

    def tampered(args, **kwargs):
        pdf = tmp_path / "worker-case.pdf"
        pdf.write_bytes(b"pdf")
        payload = {
            "case_id": "wrong" if defect == "identity" else case.case_id,
            "pdf": pdf.name,
            "pdf_bytes": 99 if defect == "size" else pdf.stat().st_size,
            "pdf_sha256": "0" * 64 if defect == "hash" else visual._sha256(pdf),
            "measurements": {
                "pages": [{"page": 1, "width": 1, "height": 1}], "tables": {},
            },
            "checks": [
                {"check_id": check_id, "status": "passed", "detail": "test"}
                for check_id in visual.GEOMETRY_CHECK_IDS
            ],
            "render_seconds": 0.01,
        }
        (tmp_path / "worker-result.json").write_bytes(visual._json_bytes(payload))
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

    monkeypatch.setattr(visual, "_run_checked", tampered)
    with pytest.raises(visual.AcceptanceError, match=match):
        visual._run_worker(case, tmp_path, timeout=0.01)


def test_worker_uses_snapshotted_tool_path(tmp_path, monkeypatch):
    case = visual.AcceptanceCase("worker-case", "neutral")
    snapshot = tmp_path / "snapshot"
    called = {}

    def successful(args, **kwargs):
        called["script"] = Path(args[1])
        pdf = tmp_path / "worker-case.pdf"
        pdf.write_bytes(b"pdf")
        (tmp_path / "worker-result.json").write_bytes(visual._json_bytes({
            "case_id": case.case_id,
            "pdf": pdf.name,
                "pdf_bytes": pdf.stat().st_size,
                "pdf_sha256": visual._sha256(pdf),
                "measurements": {
                    "pages": [{"page": 1, "width": 1, "height": 1}], "tables": {},
                },
                "checks": [
                    {"check_id": check_id, "status": "passed", "detail": "test"}
                    for check_id in visual.GEOMETRY_CHECK_IDS
                ],
                "render_seconds": 0.01,
            }))
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

    monkeypatch.setattr(visual, "_run_checked", successful)
    visual._run_worker(case, tmp_path, timeout=1, python_root=snapshot)
    assert called["script"] == snapshot / "tools" / "visual_acceptance.py"


@pytest.mark.parametrize("missing", ["measurements", "checks", "render_seconds"])
def test_worker_rejects_incomplete_success_schema(tmp_path, monkeypatch, missing):
    case = visual.AcceptanceCase("worker-case", "neutral")

    def incomplete(args, **kwargs):
        pdf = tmp_path / "worker-case.pdf"
        pdf.write_bytes(b"pdf")
        payload = {
            "case_id": case.case_id,
            "pdf": pdf.name,
            "pdf_bytes": pdf.stat().st_size,
            "pdf_sha256": visual._sha256(pdf),
            "measurements": {
                "pages": [{"page": 1, "width": 1, "height": 1}], "tables": {},
            },
            "checks": [
                {"check_id": check_id, "status": "passed", "detail": "test"}
                for check_id in visual.GEOMETRY_CHECK_IDS
            ],
            "render_seconds": 0.01,
        }
        payload.pop(missing)
        (tmp_path / "worker-result.json").write_bytes(visual._json_bytes(payload))
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

    monkeypatch.setattr(visual, "_run_checked", incomplete)
    with pytest.raises(visual.AcceptanceError, match="worker result schema mismatch"):
        visual._run_worker(case, tmp_path, timeout=1)


def test_worker_rejects_oversized_pdf_before_hash(tmp_path, monkeypatch):
    case = visual.AcceptanceCase("worker-case", "neutral")
    monkeypatch.setattr(visual, "MAX_PDF_BYTES", 2)

    def oversized(args, **kwargs):
        pdf = tmp_path / "worker-case.pdf"
        pdf.write_bytes(b"pdf")
        payload = {
            "case_id": case.case_id,
            "pdf": pdf.name,
            "pdf_bytes": 3,
            "pdf_sha256": "a" * 64,
            "measurements": {
                "pages": [{"page": 1, "width": 1, "height": 1}], "tables": {},
            },
            "checks": [
                {"check_id": check_id, "status": "passed", "detail": "test"}
                for check_id in visual.GEOMETRY_CHECK_IDS
            ],
            "render_seconds": 0.01,
        }
        (tmp_path / "worker-result.json").write_bytes(visual._json_bytes(payload))
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

    monkeypatch.setattr(visual, "_run_checked", oversized)
    monkeypatch.setattr(
        visual, "_hash_regular_file_bounded",
        lambda *args, **kwargs: pytest.fail("oversized worker PDF was hashed"),
    )
    with pytest.raises(visual.AcceptanceError, match="worker PDF record is invalid"):
        visual._run_worker(case, tmp_path, timeout=1)


def test_rasterize_rejects_zero_exit_partial_page_set(tmp_path, monkeypatch):
    from PIL import Image

    case = visual.AcceptanceCase("partial", "neutral")
    (tmp_path / "partial.pdf").write_bytes(b"pdf")

    def partial(args, **kwargs):
        prefix = Path(args[-1])
        Image.new("RGB", (10, 10), "white").save(prefix.with_name("page-1.png"))
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

    monkeypatch.setattr(visual, "_run_checked", partial)
    with pytest.raises(visual.AcceptanceError, match="incomplete raster pages"):
        visual._rasterize(
            case, tmp_path, expected_pages=2, pixel_budget=1000, timeout=1
        )
    assert not list(tmp_path.glob(".raster-*"))


def test_rasterize_normalizes_poppler_zero_padded_pages(tmp_path, monkeypatch):
    from PIL import Image

    case = visual.AcceptanceCase("padded", "neutral")
    (tmp_path / "padded.pdf").write_bytes(b"pdf")

    def padded(args, **kwargs):
        prefix = Path(args[-1])
        for number in range(1, 11):
            Image.new("RGB", (2, 3), "white").save(
                prefix.with_name(f"page-{number:02d}.png")
            )
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

    monkeypatch.setattr(visual, "_run_checked", padded)
    pages, _, pixels = visual._rasterize(
        case, tmp_path, expected_pages=10, pixel_budget=100, timeout=1,
    )
    assert [path.name for path in pages] == [f"page-{number}.png" for number in range(1, 11)]
    assert pixels == 60


def test_rasterize_rejects_invalid_png_and_cleans_temporary_tree(
    tmp_path, monkeypatch,
):
    case = visual.AcceptanceCase("invalid", "neutral")
    (tmp_path / "invalid.pdf").write_bytes(b"pdf")

    def invalid(args, **kwargs):
        Path(args[-1]).with_name("page-1.png").write_bytes(b"not-png")
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

    monkeypatch.setattr(visual, "_run_checked", invalid)
    with pytest.raises(visual.AcceptanceError, match="invalid raster page"):
        visual._rasterize(
            case, tmp_path, expected_pages=1, pixel_budget=100, timeout=1,
        )
    assert not list(tmp_path.glob(".raster-*"))


def test_rasterize_rejects_page_count_and_pixel_budget(tmp_path, monkeypatch):
    from PIL import Image

    case = visual.AcceptanceCase("bounded", "neutral")
    (tmp_path / "bounded.pdf").write_bytes(b"pdf")
    with pytest.raises(visual.AcceptanceError, match="outside"):
        visual._rasterize(
            case, tmp_path, expected_pages=visual.MAX_PAGES_PER_CASE + 1,
            pixel_budget=100, timeout=1,
        )

    def oversized(args, **kwargs):
        Image.new("RGB", (11, 11), "white").save(
            Path(args[-1]).with_name("page-1.png")
        )
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

    monkeypatch.setattr(visual, "_run_checked", oversized)
    with pytest.raises(visual.AcceptanceError, match="exceed remaining budget"):
        visual._rasterize(
            case, tmp_path, expected_pages=1, pixel_budget=100, timeout=1,
        )
    assert not list(tmp_path.glob(".raster-*"))


def test_source_identity_allowlist_contains_every_pdf_module():
    inputs = set(visual._input_files())
    assert set((visual.ROOT / "pdf").glob("*.py")) <= inputs
    assert visual.ROOT / "pyproject.toml" in inputs
    assert visual.ROOT / "pdf" / "default_widths.yml" in inputs
    assert visual.ROOT / "pdf" / "table_presets.yml" in inputs


def test_render_input_snapshot_is_hash_verified_and_immutable(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    source = root / "tests" / "visual" / "table-widths.md"
    module = root / "pdf" / "render.py"
    source.parent.mkdir(parents=True)
    module.parent.mkdir(parents=True)
    source.write_text("fixture")
    module.write_text("VALUE = 1\n")
    inputs = {
        path.relative_to(root).as_posix(): visual._sha256(path)
        for path in (source, module)
    }
    identity = {"input_hashes": inputs}
    monkeypatch.setattr(visual, "ROOT", root)
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    snapshot = visual._snapshot_inputs(candidate, identity)
    module.write_text("VALUE = 2\n")
    assert (snapshot / "pdf" / "render.py").read_text() == "VALUE = 1\n"
    assert {
        path.relative_to(snapshot).as_posix(): visual._sha256(path)
        for path in snapshot.rglob("*") if path.is_file()
    } == inputs


def test_contact_sheet_is_bounded_and_created(tmp_path):
    from PIL import Image
    pages = []
    for number in range(2):
        path = tmp_path / f"page-{number}.png"
        Image.new("RGB", (200, 300), "white").save(path)
        pages.append(path)
    output = tmp_path / "sheet.png"
    visual._contact_sheet(visual.AcceptanceCase("sheet", "neutral"), pages, output)
    with Image.open(output) as sheet:
        assert sheet.width == visual.THUMB_WIDTH * visual.SHEET_COLUMNS
        assert sheet.height < 1000


def _make_candidate(root: Path, marker: str, *, baseline=None) -> Path:
    from PIL import Image

    candidate = root / f"candidate-{marker}"
    sheets = candidate / "contact-sheets"
    sheets.mkdir(parents=True)
    artifacts = []
    for case in visual.acceptance_cases():
        sheet = sheets / f"{case.case_id}.png"
        sheet.write_bytes(marker.encode())
        artifacts.append({
            "path": f"contact-sheets/{case.case_id}.png",
            "bytes": 1,
            "sha256": visual._sha256(sheet),
        })
    reviewed = []
    for case in visual.acceptance_cases():
        case_dir = candidate / "cases" / case.case_id
        case_dir.mkdir(parents=True)
        pdf = case_dir / f"{case.case_id}.pdf"
        pdf.write_bytes(marker.encode())
        page = case_dir / "page-1.png"
        Image.new("RGB", (1, 1), "white").save(page)
        reviewed.extend((
            visual._artifact_record(pdf, candidate, kind="pdf"),
            visual._artifact_record(page, candidate, kind="page"),
        ))
    manifest = _manifest(
        marker=marker, artifacts=artifacts, reviewed=reviewed, baseline=baseline,
    )
    for record in manifest["cases"]:
        pdf = candidate / "cases" / record["case_id"] / record["pdf"]
        record["pdf_bytes"] = pdf.stat().st_size
        record["pdf_sha256"] = visual._sha256(pdf)
    (candidate / "manifest.json").write_bytes(
        visual._json_bytes(manifest)
    )
    return candidate


def test_candidate_validation_rejects_hash_mismatch(tmp_path, monkeypatch):
    root = tmp_path / "candidates"
    candidate = _make_candidate(root, "a")
    monkeypatch.setattr(visual, "CANDIDATE_ROOT", root)
    manifest = json.loads((candidate / "manifest.json").read_text())
    manifest["promotable_artifacts"][0]["sha256"] = "0" * 64
    (candidate / "manifest.json").write_bytes(visual._json_bytes(manifest))
    with pytest.raises(visual.AcceptanceError, match="hash mismatch"):
        visual.validate_candidate(candidate)


def test_candidate_validation_rejects_symlinked_artifact(tmp_path, monkeypatch):
    root = tmp_path / "candidates"
    candidate = _make_candidate(root, "a")
    monkeypatch.setattr(visual, "CANDIDATE_ROOT", root)
    sheet = candidate / "contact-sheets" / "automatic-neutral.png"
    outside = tmp_path / "outside.png"
    outside.write_bytes(b"p")
    sheet.unlink()
    sheet.symlink_to(outside)
    with pytest.raises(visual.AcceptanceError):
        visual.validate_candidate(candidate)


def test_candidate_validation_rejects_missing_review_page(tmp_path, monkeypatch):
    root = tmp_path / "candidates"
    candidate = _make_candidate(root, "a")
    monkeypatch.setattr(visual, "CANDIDATE_ROOT", root)
    (candidate / "cases" / "automatic-neutral" / "page-1.png").unlink()
    with pytest.raises(visual.AcceptanceError, match="artifact is missing"):
        visual.validate_candidate(candidate)


@pytest.mark.parametrize("bad_measurements", [None, [], "bad"])
def test_candidate_validation_bounds_nested_container_errors(
    tmp_path, monkeypatch, bad_measurements,
):
    root = tmp_path / "candidates"
    candidate = _make_candidate(root, "a")
    monkeypatch.setattr(visual, "CANDIDATE_ROOT", root)
    manifest_path = candidate / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["cases"][0]["measurements"] = bad_measurements
    manifest_path.write_bytes(visual._json_bytes(manifest))
    with pytest.raises(visual.AcceptanceError, match="measurements must be an object"):
        visual.validate_candidate(candidate)


def test_candidate_validation_bounds_malformed_json(tmp_path, monkeypatch):
    root = tmp_path / "candidates"
    candidate = _make_candidate(root, "a")
    monkeypatch.setattr(visual, "CANDIDATE_ROOT", root)
    (candidate / "manifest.json").write_text("{not-json")
    with pytest.raises(visual.AcceptanceError, match="manifest is unreadable"):
        visual.validate_candidate(candidate)


def test_candidate_validation_rejects_oversized_manifest_before_decode(
    tmp_path, monkeypatch,
):
    root = tmp_path / "candidates"
    candidate = _make_candidate(root, "a")
    monkeypatch.setattr(visual, "CANDIDATE_ROOT", root)
    monkeypatch.setattr(visual, "MAX_MANIFEST_BYTES", 8)
    (candidate / "manifest.json").write_bytes(b"{" + b"x" * 8)
    with pytest.raises(visual.AcceptanceError, match="exceeds 8 bytes"):
        visual.validate_candidate(candidate)


def test_candidate_validation_rejects_oversized_pdf_before_hash(
    tmp_path, monkeypatch,
):
    root = tmp_path / "candidates"
    candidate = _make_candidate(root, "a")
    monkeypatch.setattr(visual, "CANDIDATE_ROOT", root)
    monkeypatch.setattr(visual, "MAX_PDF_BYTES", 8)
    manifest_path = candidate / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    case = manifest["cases"][0]
    case["pdf_bytes"] = 9
    pdf_record = next(
        item for item in manifest["review_artifacts"]
        if item["path"] == f"cases/{case['case_id']}/{case['pdf']}"
    )
    pdf_record["bytes"] = 9
    manifest_path.write_bytes(visual._json_bytes(manifest))
    (candidate / pdf_record["path"]).write_bytes(b"x" * 9)
    monkeypatch.setattr(
        visual, "_hash_regular_file_bounded",
        lambda *args, **kwargs: pytest.fail("oversized PDF was hashed"),
    )
    with pytest.raises(visual.AcceptanceError, match="invalid PDF size"):
        visual.validate_candidate(candidate)


def test_candidate_validation_stops_at_tree_entry_limit(tmp_path, monkeypatch):
    root = tmp_path / "candidates"
    candidate = _make_candidate(root, "a")
    monkeypatch.setattr(visual, "CANDIDATE_ROOT", root)
    monkeypatch.setattr(visual, "MAX_CANDIDATE_ENTRIES", 2)
    with pytest.raises(visual.AcceptanceError, match="tree exceeds entry limit"):
        visual.validate_candidate(candidate)


def test_pdf_object_evidence_is_stable_and_rejects_decoded_active_action(tmp_path):
    from pypdf import PdfWriter
    from pypdf.generic import DictionaryObject, NameObject, TextStringObject

    first = tmp_path / "first.pdf"
    second = tmp_path / "second.pdf"
    active = tmp_path / "active.pdf"
    for path in (first, second):
        writer = PdfWriter()
        writer.add_blank_page(width=100, height=100)
        with path.open("wb") as stream:
            writer.write(stream)
    assert (
        visual._pdf_object_evidence(first)["graph_sha256"]
        == visual._pdf_object_evidence(second)["graph_sha256"]
    )
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    writer.root_object[NameObject("/OpenAction")] = DictionaryObject({
        NameObject("/S"): NameObject("/JavaScript"),
        NameObject("/JS"): TextStringObject("app.alert('blocked')"),
    })
    with active.open("wb") as stream:
        writer.write(stream)
    with pytest.raises(visual.AcceptanceError, match="active or embedded content"):
        visual._pdf_object_evidence(active)


def test_pdf_stream_canonicalization_ignores_only_volatile_font_fields():
    first = bytearray(82)
    first[:6] = b"\x00\x01\x00\x00\x00\x01"
    first[12:16] = b"head"
    first[16:20] = b"aaaa"
    first[20:24] = (28).to_bytes(4, "big")
    first[24:28] = (54).to_bytes(4, "big")
    first[36:40] = b"bbbb"
    first[56:64] = b"cccccccc"
    second = bytearray(first)
    second[16:20] = b"dddd"
    second[36:40] = b"eeee"
    second[56:64] = b"ffffffff"
    assert visual._canonical_stream_bytes(first) == visual._canonical_stream_bytes(second)
    second[65] = 1
    assert visual._canonical_stream_bytes(first) != visual._canonical_stream_bytes(second)


def test_pdf_object_evidence_rejects_oversize_and_symlink(tmp_path, monkeypatch):
    pdf = tmp_path / "document.pdf"
    pdf.write_bytes(b"%PDF-1.7\n")
    monkeypatch.setattr(visual, "MAX_PDF_BYTES", 4)
    with pytest.raises(visual.AcceptanceError, match="safe parser input limit"):
        visual._pdf_object_evidence(pdf)
    alias = tmp_path / "alias.pdf"
    alias.symlink_to(pdf)
    with pytest.raises(visual.AcceptanceError, match="missing or unsafe"):
        visual._pdf_object_evidence(alias)


def test_pdf_object_evidence_enforces_encryption_and_parser_budgets(
    tmp_path, monkeypatch,
):
    from pypdf import PdfWriter
    from pypdf.generic import DecodedStreamObject, NameObject

    encrypted = tmp_path / "encrypted.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    writer.encrypt("secret")
    with encrypted.open("wb") as stream:
        writer.write(stream)
    with pytest.raises(visual.AcceptanceError, match="encrypted"):
        visual._pdf_object_evidence(encrypted)

    ordinary = tmp_path / "ordinary.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    with ordinary.open("wb") as stream:
        writer.write(stream)
    monkeypatch.setattr(visual, "MAX_PDF_OBJECTS", 1)
    with pytest.raises(visual.AcceptanceError, match="object-count limit"):
        visual._pdf_object_evidence(ordinary)

    streamed = tmp_path / "streamed.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    payload = DecodedStreamObject()
    payload.set_data(b"bounded decoded payload")
    writer.root_object[NameObject("/SyntheticData")] = writer._add_object(payload)
    with streamed.open("wb") as stream:
        writer.write(stream)
    monkeypatch.setattr(visual, "MAX_PDF_OBJECTS", 20_000)
    monkeypatch.setattr(visual, "MAX_DECODED_PDF_BYTES", 4)
    with pytest.raises(visual.AcceptanceError, match="decoded PDF streams"):
        visual._pdf_object_evidence(streamed)


def test_two_version_promotion_keeps_previous_and_updates_pointer(
    tmp_path, monkeypatch,
):
    output = tmp_path / "output"
    candidates = output / "candidates"
    approved = tmp_path / "approved-root"
    monkeypatch.setattr(visual, "CANDIDATE_ROOT", candidates)
    monkeypatch.setattr(visual, "APPROVED_ROOT", approved)
    monkeypatch.setattr(visual, "APPROVED_VERSIONS", approved / "approved")
    monkeypatch.setattr(visual, "ACTIVE_POINTER", approved / "active.json")
    monkeypatch.setattr(visual, "OUTPUT_ROOT", output)
    first = _make_candidate(candidates, "a")
    first_manifest = json.loads((first / "manifest.json").read_text())
    first_digest = first_manifest["source"]["digest"]
    current = {"source": first_manifest["source"]}
    monkeypatch.setattr(visual, "_source_identity", lambda: current["source"])
    monkeypatch.setattr(visual, "_environment", _environment)
    monkeypatch.setattr(visual, "_pdf_semantic_checks", _passing_semantics)
    monkeypatch.setattr(visual, "_attest_candidate", lambda *args: None)
    visual.promote(first)
    second = _make_candidate(candidates, "b", baseline=first_digest)
    second_manifest = json.loads((second / "manifest.json").read_text())
    second_digest = second_manifest["source"]["digest"]
    current["source"] = second_manifest["source"]
    visual.promote(second)
    pointer = json.loads((approved / "active.json").read_text())
    assert pointer["digest"] == second_digest
    assert pointer["previous_digest"] == first_digest
    assert (approved / "approved" / first_digest / "manifest.json").is_file()
    assert (approved / "approved" / second_digest / "manifest.json").is_file()


def _configure_store(tmp_path, monkeypatch):
    output = tmp_path / "output"
    candidates = output / "candidates"
    approved = tmp_path / "approved-root"
    monkeypatch.setattr(visual, "CANDIDATE_ROOT", candidates)
    monkeypatch.setattr(visual, "APPROVED_ROOT", approved)
    monkeypatch.setattr(visual, "APPROVED_VERSIONS", approved / "approved")
    monkeypatch.setattr(visual, "ACTIVE_POINTER", approved / "active.json")
    monkeypatch.setattr(visual, "OUTPUT_ROOT", output)
    monkeypatch.setattr(visual, "_environment", _environment)
    monkeypatch.setattr(visual, "_pdf_semantic_checks", _passing_semantics)
    monkeypatch.setattr(visual, "_attest_candidate", lambda *args: None)
    return candidates, approved


def test_promotion_rejects_stale_review_baseline(tmp_path, monkeypatch):
    candidates, approved = _configure_store(tmp_path, monkeypatch)
    first = _make_candidate(candidates, "a")
    first_manifest = json.loads((first / "manifest.json").read_text())
    monkeypatch.setattr(visual, "_source_identity", lambda: first_manifest["source"])
    visual.promote(first)
    stale = _make_candidate(candidates, "b", baseline=None)
    stale_manifest = json.loads((stale / "manifest.json").read_text())
    monkeypatch.setattr(visual, "_source_identity", lambda: stale_manifest["source"])
    with pytest.raises(visual.AcceptanceError, match="baseline is stale"):
        visual.promote(stale)
    pointer = json.loads((approved / "active.json").read_text())
    assert pointer["digest"] == first_manifest["source"]["digest"]


def test_promotion_detects_candidate_mutation_during_copy(tmp_path, monkeypatch):
    candidates, approved = _configure_store(tmp_path, monkeypatch)
    candidate = _make_candidate(candidates, "a")
    manifest = json.loads((candidate / "manifest.json").read_text())
    monkeypatch.setattr(visual, "_source_identity", lambda: manifest["source"])
    original = visual._copy_verified_at
    mutated = False

    def mutate_then_copy(source, destination_fd, name, item):
        nonlocal mutated
        if not mutated:
            source.write_bytes(b"changed")
            mutated = True
        return original(source, destination_fd, name, item)

    monkeypatch.setattr(visual, "_copy_verified_at", mutate_then_copy)
    with pytest.raises(visual.AcceptanceError, match="changed during copy"):
        visual.promote(candidate)
    assert not (approved / "active.json").exists()


def test_promotion_root_replacement_cannot_redirect_staging_writes(
    tmp_path, monkeypatch,
):
    candidates, approved = _configure_store(tmp_path, monkeypatch)
    candidate = _make_candidate(candidates, "a")
    manifest = json.loads((candidate / "manifest.json").read_text())
    monkeypatch.setattr(visual, "_source_identity", lambda: manifest["source"])
    versions = approved / "approved"
    displaced = approved / "displaced-approved"
    original = visual._copy_verified_at
    replaced = False

    def replace_root_then_copy(source, destination_fd, name, item):
        nonlocal replaced
        if not replaced:
            versions.rename(displaced)
            versions.mkdir()
            replacement_sentinel = versions / "sentinel"
            replacement_sentinel.write_text("untouched", encoding="utf-8")
            replaced = True
        return original(source, destination_fd, name, item)

    monkeypatch.setattr(visual, "_copy_verified_at", replace_root_then_copy)
    with pytest.raises(visual.AcceptanceError, match="approved roots changed"):
        visual.promote(candidate)
    replacement_sentinel = versions / "sentinel"
    assert replacement_sentinel.read_text(encoding="utf-8") == "untouched"
    assert list(versions.iterdir()) == [replacement_sentinel]
    assert not (approved / "active.json").exists()
    assert (displaced / manifest["source"]["digest"]).is_dir()


def test_promotion_rejects_approved_root_replacement_before_publication(
    tmp_path, monkeypatch,
):
    candidates, approved = _configure_store(tmp_path, monkeypatch)
    candidate = _make_candidate(candidates, "a")
    manifest = json.loads((candidate / "manifest.json").read_text())
    monkeypatch.setattr(visual, "_source_identity", lambda: manifest["source"])
    displaced = tmp_path / "displaced-approved-root"
    original = visual._assert_candidate_current

    def replace_before_publication(candidate_manifest, *, phase):
        result = original(candidate_manifest, phase=phase)
        if phase == "before publication":
            approved.rename(displaced)
            (approved / "approved").mkdir(parents=True)
            (approved / "sentinel").write_text("untouched", encoding="utf-8")
        return result

    monkeypatch.setattr(
        visual, "_assert_candidate_current", replace_before_publication,
    )
    with pytest.raises(visual.AcceptanceError, match="approved roots changed"):
        visual.promote(candidate)
    assert (approved / "sentinel").read_text(encoding="utf-8") == "untouched"
    assert not (approved / "active.json").exists()
    assert not (displaced / "active.json").exists()


def test_existing_approved_version_is_reverified(tmp_path, monkeypatch):
    candidates, approved = _configure_store(tmp_path, monkeypatch)
    candidate = _make_candidate(candidates, "a")
    manifest = json.loads((candidate / "manifest.json").read_text())
    monkeypatch.setattr(visual, "_source_identity", lambda: manifest["source"])
    version = visual.promote(candidate)
    manifest["review_baseline"] = manifest["source"]["digest"]
    (candidate / "manifest.json").write_bytes(visual._json_bytes(manifest))
    (version / "contact-sheets" / "automatic-neutral.png").write_bytes(b"bad")
    with pytest.raises(visual.AcceptanceError, match="approved artifact mismatch"):
        visual.promote(candidate)


@pytest.mark.parametrize("entry", ["version", "manifest", "contact", "png"])
def test_descriptor_validator_rejects_symlinked_approved_entries(
    tmp_path, monkeypatch, entry,
):
    candidates, approved = _configure_store(tmp_path, monkeypatch)
    candidate = _make_candidate(candidates, "a")
    manifest = json.loads((candidate / "manifest.json").read_text())
    monkeypatch.setattr(visual, "_source_identity", lambda: manifest["source"])
    version = visual.promote(candidate)
    versions = approved / "approved"
    external = tmp_path / f"external-{entry}"

    if entry == "version":
        version.rename(tmp_path / "real-version")
        external.mkdir()
        sentinel = external / "sentinel"
        sentinel.write_bytes(b"external version")
        version.symlink_to(external, target_is_directory=True)
    elif entry == "manifest":
        target = version / "manifest.json"
        target.unlink()
        external.write_bytes(b"external manifest")
        sentinel = external
        target.symlink_to(external)
    elif entry == "contact":
        target = version / "contact-sheets"
        target.rename(version / "real-contact-sheets")
        external.mkdir()
        sentinel = external / "sentinel"
        sentinel.write_bytes(b"external contact directory")
        target.symlink_to(external, target_is_directory=True)
    else:
        target = version / manifest["promotable_artifacts"][0]["path"]
        target.unlink()
        external.write_bytes(b"external image")
        sentinel = external
        target.symlink_to(external)
    before = sentinel.read_bytes()

    with visual._directory_fd(versions, label="approved versions root") as (
        versions_fd, _,
    ):
        with pytest.raises(visual.AcceptanceError):
            visual._ensure_approved_version_at(
                versions_fd, manifest["source"]["digest"], candidate, manifest,
            )
    assert sentinel.read_bytes() == before


def test_existing_approved_version_rejects_changed_measurement_evidence(
    tmp_path, monkeypatch,
):
    candidates, _ = _configure_store(tmp_path, monkeypatch)
    candidate = _make_candidate(candidates, "a")
    manifest_path = candidate / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    monkeypatch.setattr(visual, "_source_identity", lambda: manifest["source"])
    visual.promote(candidate)
    manifest["review_baseline"] = manifest["source"]["digest"]
    manifest["cases"][0]["measurements"]["pages"][0]["width"] = 999
    manifest_path.write_bytes(visual._json_bytes(manifest))
    with pytest.raises(visual.AcceptanceError, match="conflicts with candidate evidence"):
        visual.promote(candidate)


@pytest.mark.parametrize(
    "field",
    ["python", "poppler", "pango", "platform", "machine"]
    + [f"package:{name}" for name in visual.RENDER_DEPENDENCIES]
    + ["raster:dpi"],
)
def test_current_candidate_validation_rejects_each_environment_change(
    tmp_path, monkeypatch, field,
):
    candidates = tmp_path / "candidates"
    candidate = _make_candidate(candidates, "a")
    manifest = json.loads((candidate / "manifest.json").read_text())
    monkeypatch.setattr(visual, "CANDIDATE_ROOT", candidates)
    monkeypatch.setattr(visual, "_source_identity", lambda: manifest["source"])
    changed = json.loads(json.dumps(manifest["environment"]))
    if field.startswith("package:"):
        changed["packages"][field.split(":", 1)[1]] += "-changed"
    elif field == "raster:dpi":
        changed["raster"]["dpi"] += 1
    else:
        changed[field] += "-changed"
    monkeypatch.setattr(visual, "_environment", lambda: changed)
    with pytest.raises(visual.AcceptanceError, match="environment changed validation"):
        visual.validate_candidate(candidate, require_current=True)


def test_pointer_replace_failure_keeps_previous_active_version(
    tmp_path, monkeypatch,
):
    candidates, approved = _configure_store(tmp_path, monkeypatch)
    first = _make_candidate(candidates, "a")
    first_manifest = json.loads((first / "manifest.json").read_text())
    current = {"source": first_manifest["source"]}
    monkeypatch.setattr(visual, "_source_identity", lambda: current["source"])
    visual.promote(first)
    before = (approved / "active.json").read_bytes()
    second = _make_candidate(
        candidates, "b", baseline=first_manifest["source"]["digest"],
    )
    second_manifest = json.loads((second / "manifest.json").read_text())
    current["source"] = second_manifest["source"]
    original = visual._write_json_atomic_at

    def fail_pointer(directory_fd, name, value):
        if name == "active.json":
            raise OSError("injected pointer failure")
        return original(directory_fd, name, value)

    monkeypatch.setattr(visual, "_write_json_atomic_at", fail_pointer)
    with pytest.raises(OSError, match="injected pointer failure"):
        visual.promote(second)
    assert (approved / "active.json").read_bytes() == before


def test_concurrent_reader_sees_complete_old_or_new_evidence(
    tmp_path, monkeypatch,
):
    candidates, approved = _configure_store(tmp_path, monkeypatch)
    first = _make_candidate(candidates, "a")
    first_manifest = json.loads((first / "manifest.json").read_text())
    current = {"source": first_manifest["source"]}
    monkeypatch.setattr(visual, "_source_identity", lambda: current["source"])
    visual.promote(first)
    second = _make_candidate(
        candidates, "b", baseline=first_manifest["source"]["digest"],
    )
    second_manifest = json.loads((second / "manifest.json").read_text())
    current["source"] = second_manifest["source"]
    entered = threading.Event()
    release = threading.Event()
    original = visual._write_json_atomic_at

    def pause_pointer(directory_fd, name, value):
        if name == "active.json" and value.get("digest") == second_manifest["source"]["digest"]:
            entered.set()
            assert release.wait(5)
        return original(directory_fd, name, value)

    monkeypatch.setattr(visual, "_write_json_atomic_at", pause_pointer)
    errors = []
    thread = threading.Thread(
        target=lambda: _capture_thread_error(errors, visual.promote, second),
    )
    thread.start()
    assert entered.wait(5)
    for _ in range(10):
        assert visual._active_digest() == first_manifest["source"]["digest"]
    release.set()
    thread.join(5)
    assert not thread.is_alive()
    assert errors == []
    assert visual._active_digest() == second_manifest["source"]["digest"]


def _capture_thread_error(errors, function, *args):
    try:
        function(*args)
    except Exception as exc:  # pragma: no cover - assertion reports captured error
        errors.append(exc)


def test_concurrent_promoters_serialize_and_stale_second_is_rejected(
    tmp_path, monkeypatch,
):
    candidates, approved = _configure_store(tmp_path, monkeypatch)
    baseline_candidate = _make_candidate(candidates, "a")
    baseline_manifest = json.loads((baseline_candidate / "manifest.json").read_text())
    current = {"source": baseline_manifest["source"]}
    monkeypatch.setattr(visual, "_source_identity", lambda: current["source"])
    visual.promote(baseline_candidate)
    first = _make_candidate(
        candidates, "b", baseline=baseline_manifest["source"]["digest"],
    )
    first_manifest = json.loads((first / "manifest.json").read_text())
    second = candidates / "candidate-b-second"
    shutil.copytree(first, second)
    current["source"] = first_manifest["source"]
    entered = threading.Event()
    release = threading.Event()
    original = visual._write_json_atomic_at
    pointer_calls = 0

    def pause_first_pointer(directory_fd, name, value):
        nonlocal pointer_calls
        if name == "active.json" and value.get("digest") == first_manifest["source"]["digest"]:
            pointer_calls += 1
            if pointer_calls == 1:
                entered.set()
                assert release.wait(5)
        return original(directory_fd, name, value)

    monkeypatch.setattr(visual, "_write_json_atomic_at", pause_first_pointer)
    first_errors = []
    second_errors = []
    first_thread = threading.Thread(
        target=lambda: _capture_thread_error(first_errors, visual.promote, first),
    )
    second_thread = threading.Thread(
        target=lambda: _capture_thread_error(second_errors, visual.promote, second),
    )
    first_thread.start()
    assert entered.wait(5)
    second_thread.start()
    time.sleep(0.05)
    release.set()
    first_thread.join(5)
    second_thread.join(5)
    assert not first_thread.is_alive() and not second_thread.is_alive()
    assert first_errors == []
    assert len(second_errors) == 1
    assert "baseline is stale" in str(second_errors[0])
    assert visual._active_digest() == first_manifest["source"]["digest"]
    assert json.loads((approved / "active.json").read_text())["digest"] == first_manifest["source"]["digest"]


def test_version_replace_failure_never_publishes_pointer(tmp_path, monkeypatch):
    candidates, approved = _configure_store(tmp_path, monkeypatch)
    candidate = _make_candidate(candidates, "a")
    manifest = json.loads((candidate / "manifest.json").read_text())
    monkeypatch.setattr(visual, "_source_identity", lambda: manifest["source"])
    version = approved / "approved" / manifest["source"]["digest"]
    original = visual.os.rename

    def fail_version(source, destination, *args, **kwargs):
        if destination == manifest["source"]["digest"]:
            raise OSError("injected version replace failure")
        return original(source, destination, *args, **kwargs)

    monkeypatch.setattr(visual.os, "rename", fail_version)
    with pytest.raises(OSError, match="version replace failure"):
        visual.promote(candidate)
    assert not (approved / "active.json").exists()
    assert not version.exists()


@pytest.mark.parametrize("failure_point", ["copy", "manifest", "fsync"])
def test_promotion_staging_failures_never_publish_or_leave_temp_tree(
    tmp_path, monkeypatch, failure_point,
):
    candidates, approved = _configure_store(tmp_path, monkeypatch)
    candidate = _make_candidate(candidates, "a")
    manifest = json.loads((candidate / "manifest.json").read_text())
    monkeypatch.setattr(visual, "_source_identity", lambda: manifest["source"])
    if failure_point == "copy":
        monkeypatch.setattr(
            visual, "_copy_verified_at",
            lambda *args, **kwargs: (_ for _ in ()).throw(OSError("copy failure")),
        )
    elif failure_point == "manifest":
        original = visual._write_json_atomic_at

        def fail_manifest(directory_fd, name, value):
            if name == "manifest.json":
                raise OSError("manifest failure")
            return original(directory_fd, name, value)

        monkeypatch.setattr(visual, "_write_json_atomic_at", fail_manifest)
    else:
        monkeypatch.setattr(
            visual, "_fsync_directory_fd",
            lambda fd: (_ for _ in ()).throw(OSError("fsync failure")),
        )
    with pytest.raises(OSError, match="failure"):
        visual.promote(candidate)
    assert not (approved / "active.json").exists()
    versions = approved / "approved"
    assert not any(path.name.startswith(".") for path in versions.iterdir())
    assert not (versions / manifest["source"]["digest"]).exists()


@pytest.mark.parametrize("failure", ["interrupt", "open", "stat"])
def test_promotion_cleans_staging_on_interrupt_and_initial_open_failure(
    tmp_path, monkeypatch, failure,
):
    candidates, approved = _configure_store(tmp_path, monkeypatch)
    candidate = _make_candidate(candidates, "a")
    manifest = json.loads((candidate / "manifest.json").read_text())
    monkeypatch.setattr(visual, "_source_identity", lambda: manifest["source"])
    if failure == "interrupt":
        monkeypatch.setattr(
            visual, "_copy_verified_at",
            lambda *args, **kwargs: (_ for _ in ()).throw(KeyboardInterrupt()),
        )
        expected = KeyboardInterrupt
    elif failure == "open":
        original = visual._directory_fd_only_at

        @contextlib.contextmanager
        def fail_staging_open(parent_fd, name, *, label):
            if label == "approved staging directory":
                raise visual.AcceptanceError("injected staging open failure")
            with original(parent_fd, name, label=label) as opened:
                yield opened

        monkeypatch.setattr(visual, "_directory_fd_only_at", fail_staging_open)
        expected = visual.AcceptanceError
    else:
        original_stat = visual.os.stat
        interrupted = False

        def interrupt_first_staging_stat(path, *args, **kwargs):
            nonlocal interrupted
            if (
                not interrupted and isinstance(path, str)
                and path.startswith(f".{manifest['source']['digest']}.")
            ):
                interrupted = True
                raise KeyboardInterrupt
            return original_stat(path, *args, **kwargs)

        monkeypatch.setattr(visual.os, "stat", interrupt_first_staging_stat)
        expected = KeyboardInterrupt
    with pytest.raises(expected):
        visual.promote(candidate)
    versions = approved / "approved"
    assert not any(path.name.startswith(".") for path in versions.iterdir())
    assert not (approved / "active.json").exists()


@pytest.mark.parametrize("failure_call", [1, 2, 3, 4])
def test_promotion_fsync_failures_leave_only_recoverable_states(
    tmp_path, monkeypatch, failure_call,
):
    candidates, approved = _configure_store(tmp_path, monkeypatch)
    candidate = _make_candidate(candidates, "a")
    manifest = json.loads((candidate / "manifest.json").read_text())
    monkeypatch.setattr(visual, "_source_identity", lambda: manifest["source"])
    original = visual._fsync_directory_fd
    calls = 0

    def fail_selected(fd):
        nonlocal calls
        calls += 1
        if calls == failure_call:
            raise OSError(f"fsync failure {failure_call}")
        return original(fd)

    monkeypatch.setattr(visual, "_fsync_directory_fd", fail_selected)
    with pytest.raises(OSError, match=f"fsync failure {failure_call}"):
        visual.promote(candidate)
    version = approved / "approved" / manifest["source"]["digest"]
    pointer = approved / "active.json"
    if failure_call <= 2:
        assert not version.exists() and not pointer.exists()
    elif failure_call == 3:
        assert version.is_dir() and not pointer.exists()
    else:
        assert version.is_dir() and pointer.is_file()
        assert json.loads(pointer.read_text())["digest"] == manifest["source"]["digest"]


def test_promotion_cleanup_failure_does_not_mask_primary_error(
    tmp_path, monkeypatch,
):
    candidates, _ = _configure_store(tmp_path, monkeypatch)
    candidate = _make_candidate(candidates, "a")
    manifest = json.loads((candidate / "manifest.json").read_text())
    monkeypatch.setattr(visual, "_source_identity", lambda: manifest["source"])
    monkeypatch.setattr(
        visual, "_copy_verified_at",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("primary copy failure")),
    )
    monkeypatch.setattr(
        visual.shutil, "rmtree",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("cleanup failure")),
    )
    with pytest.raises(OSError, match="primary copy failure") as raised:
        visual.promote(candidate)
    assert any("cleanup failure" in note for note in raised.value.__notes__)


def test_promotion_rejects_stale_loaded_coordinator_before_mutation(
    tmp_path, monkeypatch,
):
    candidates, approved = _configure_store(tmp_path, monkeypatch)
    candidate = _make_candidate(candidates, "a")
    monkeypatch.setattr(visual, "LOADED_TOOL_SHA256", "0" * 64)
    with pytest.raises(visual.AcceptanceError, match="tool changed before promotion"):
        visual.promote(candidate)
    assert not (approved / "active.json").exists()


def test_generation_cleans_candidate_when_snapshot_setup_fails(tmp_path, monkeypatch):
    candidates, _ = _configure_store(tmp_path, monkeypatch)
    identity = _manifest()["source"]
    monkeypatch.setattr(visual, "_source_identity", lambda: identity)
    monkeypatch.setattr(
        visual, "_snapshot_inputs",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("snapshot failure")),
    )
    with pytest.raises(OSError, match="snapshot failure"):
        visual.generate()
    assert list(candidates.iterdir()) == []


def test_generation_cleans_candidate_when_post_create_identity_check_fails(
    tmp_path, monkeypatch,
):
    candidates, _ = _configure_store(tmp_path, monkeypatch)
    identity = _manifest()["source"]
    monkeypatch.setattr(visual, "_source_identity", lambda: identity)
    original_mkdir = visual.os.mkdir
    original_identity = visual._directory_identity
    candidate_created = False

    def tracked_mkdir(path, mode=0o777, *, dir_fd=None):
        nonlocal candidate_created
        result = original_mkdir(path, mode, dir_fd=dir_fd)
        if dir_fd is not None:
            candidate_created = True
        return result

    def fail_after_creation(path):
        if candidate_created and Path(path) == candidates:
            raise OSError("identity lookup failure")
        return original_identity(path)

    monkeypatch.setattr(visual.os, "mkdir", tracked_mkdir)
    monkeypatch.setattr(visual, "_directory_identity", fail_after_creation)
    with pytest.raises(OSError, match="identity lookup failure"):
        visual.generate()
    assert list(candidates.iterdir()) == []


def test_generation_cleans_completed_candidate_when_final_check_fails(
    tmp_path, monkeypatch,
):
    candidates, _ = _configure_store(tmp_path, monkeypatch)
    identity = _manifest()["source"]
    monkeypatch.setattr(visual, "_source_identity", lambda: identity)

    def snapshot(candidate, ignored_identity):
        root = candidate / "input-snapshot"
        fixture = root / visual.SOURCE.relative_to(visual.ROOT)
        fixture.parent.mkdir(parents=True)
        fixture.write_text("fixture", encoding="utf-8")
        return root

    def complete(candidate, **kwargs):
        (candidate / "manifest.json").write_text("{}", encoding="utf-8")

    original_identity = visual._directory_identity

    def fail_after_completion(path):
        if Path(path) == candidates and any(
            (entry / "manifest.json").is_file() for entry in candidates.iterdir()
        ):
            raise OSError("final identity lookup failure")
        return original_identity(path)

    monkeypatch.setattr(visual, "_snapshot_inputs", snapshot)
    monkeypatch.setattr(visual, "_generate_locked", complete)
    monkeypatch.setattr(visual, "_directory_identity", fail_after_completion)
    with pytest.raises(OSError, match="final identity lookup failure"):
        visual.generate()
    assert list(candidates.iterdir()) == []


def test_promotion_rechecks_inputs_after_attestation(tmp_path, monkeypatch):
    candidates, _ = _configure_store(tmp_path, monkeypatch)
    candidate = _make_candidate(candidates, "a")
    manifest = json.loads((candidate / "manifest.json").read_text())
    changed = dict(manifest["source"])
    changed["input_hashes"] = {"changed.py": "0" * 64}
    calls = 0

    def identity():
        nonlocal calls
        calls += 1
        return manifest["source"] if calls <= 2 else changed

    monkeypatch.setattr(visual, "_source_identity", identity)
    with pytest.raises(visual.AcceptanceError, match="changed during attestation"):
        visual.promote(candidate)


@pytest.mark.parametrize("pointer", [None, [], ["schema_version"], "bad", 1])
def test_active_pointer_rejects_non_object_shapes(tmp_path, monkeypatch, pointer):
    approved = tmp_path / "approved-root"
    approved.mkdir()
    active = approved / "active.json"
    active.write_bytes(visual._json_bytes(pointer))
    monkeypatch.setattr(visual, "APPROVED_ROOT", approved)
    monkeypatch.setattr(visual, "APPROVED_VERSIONS", approved / "approved")
    monkeypatch.setattr(visual, "ACTIVE_POINTER", active)
    with pytest.raises(visual.AcceptanceError, match="pointer schema is invalid"):
        visual._active_digest()


def test_active_pointer_rejects_broken_symlink(tmp_path, monkeypatch):
    approved = tmp_path / "approved-root"
    approved.mkdir()
    active = approved / "active.json"
    active.symlink_to(tmp_path / "missing-pointer-target")
    monkeypatch.setattr(visual, "APPROVED_ROOT", approved)
    monkeypatch.setattr(visual, "APPROVED_VERSIONS", approved / "approved")
    monkeypatch.setattr(visual, "ACTIVE_POINTER", active)
    with pytest.raises(visual.AcceptanceError, match="pointer is unsafe"):
        visual._active_digest()


def test_independent_attestation_rejects_changed_geometry(tmp_path, monkeypatch):
    case = visual.AcceptanceCase("one-case", "neutral")
    monkeypatch.setattr(visual, "acceptance_cases", lambda: (case,))
    manifest = _manifest()
    fresh = dict(manifest["cases"][0])
    fresh["measurements"] = {"pages": [{"page": 1, "width": 2, "height": 1}]}
    monkeypatch.setattr(visual, "OUTPUT_ROOT", tmp_path)
    monkeypatch.setattr(
        visual, "_snapshot_inputs", lambda root, identity: root / "snapshot",
    )
    monkeypatch.setattr(visual, "_run_worker", lambda *args, **kwargs: fresh)
    with pytest.raises(visual.AcceptanceError, match="geometry attestation differs"):
        visual._attest_candidate(tmp_path / "candidate", manifest, {"input_hashes": {}})


def test_independent_attestation_rejects_same_text_substituted_candidate_pdf(
    tmp_path, monkeypatch,
):
    case = visual.AcceptanceCase("one-case", "neutral")
    monkeypatch.setattr(visual, "acceptance_cases", lambda: (case,))
    manifest = _manifest()
    manifest["cases"][0]["semantic_checks"] = [
        dataclasses.asdict(result) for result in _passing_semantics()[0]
    ]
    output = tmp_path / "output"
    output.mkdir()
    monkeypatch.setattr(visual, "OUTPUT_ROOT", output)
    monkeypatch.setattr(visual, "_pdf_object_evidence", _object_evidence)
    monkeypatch.setattr(
        visual, "_snapshot_inputs", lambda root, identity: root / "snapshot",
    )
    candidate_pdf = tmp_path / "candidate" / "cases" / case.case_id / f"{case.case_id}.pdf"
    candidate_pdf.parent.mkdir(parents=True)
    candidate_pdf.write_bytes(b"candidate-pdf")
    _bind_manifest_pdf(manifest, case.case_id, candidate_pdf)

    def worker(selected, case_dir, **kwargs):
        (case_dir / f"{selected.case_id}.pdf").write_bytes(b"fresh-pdf")
        return manifest["cases"][0]

    monkeypatch.setattr(visual, "_run_worker", worker)

    def semantic(pdf, **kwargs):
        return _passing_semantics()[0], "Document\nTable\nTH <1>\n", "same text"

    monkeypatch.setattr(visual, "_pdf_semantic_evidence", semantic)
    reference_page = tmp_path / "reference-page.png"
    reference_page.write_bytes(b"fresh pixels")
    manifest["review_artifacts"][1]["sha256"] = visual._sha256(reference_page)

    def raster(selected, case_dir, **kwargs):
        page = case_dir / "page-1.png"
        page.write_bytes(
            b"fresh pixels" if "candidate-copies" not in case_dir.parts
            else b"substituted pixels"
        )
        return [page], 0.01, 1

    monkeypatch.setattr(visual, "_rasterize", raster)
    candidate = tmp_path / "candidate"
    before = {
        path.relative_to(candidate).as_posix(): visual._sha256(path)
        for path in candidate.rglob("*") if path.is_file()
    }
    with pytest.raises(visual.AcceptanceError, match="candidate PDF pixels differ"):
        visual._attest_candidate(
            candidate, manifest, {"input_hashes": {}},
        )
    after = {
        path.relative_to(candidate).as_posix(): visual._sha256(path)
        for path in candidate.rglob("*") if path.is_file()
    }
    assert after == before


def test_independent_attestation_rejects_fresh_semantic_mismatch(
    tmp_path, monkeypatch,
):
    case = visual.AcceptanceCase("one-case", "neutral")
    monkeypatch.setattr(visual, "acceptance_cases", lambda: (case,))
    manifest = _manifest()
    output = tmp_path / "output"
    output.mkdir()
    monkeypatch.setattr(visual, "OUTPUT_ROOT", output)
    monkeypatch.setattr(visual, "_pdf_object_evidence", _object_evidence)
    monkeypatch.setattr(
        visual, "_snapshot_inputs", lambda root, identity: root / "snapshot",
    )
    monkeypatch.setattr(
        visual, "_run_worker", lambda *args, **kwargs: manifest["cases"][0],
    )
    failed = [
        visual.CheckResult(check_id, "failed", "changed")
        for check_id in visual.SEMANTIC_CHECK_IDS
    ]
    monkeypatch.setattr(
        visual, "_pdf_semantic_evidence",
        lambda *args, **kwargs: (failed, "", ""),
    )
    with pytest.raises(visual.AcceptanceError, match="semantic attestation differs"):
        visual._attest_candidate(
            tmp_path / "candidate", manifest, {"input_hashes": {}},
        )


def test_attestation_rejects_oversized_candidate_page_box_before_raster(
    tmp_path, monkeypatch,
):
    from pypdf import PdfWriter

    case = visual.AcceptanceCase("one-case", "neutral")
    monkeypatch.setattr(visual, "acceptance_cases", lambda: (case,))
    manifest = _manifest()
    semantic = _passing_semantics()[0]
    manifest["cases"][0]["semantic_checks"] = [
        dataclasses.asdict(result) for result in semantic
    ]
    output = tmp_path / "output"
    output.mkdir()
    monkeypatch.setattr(visual, "OUTPUT_ROOT", output)
    monkeypatch.setattr(
        visual, "_snapshot_inputs", lambda root, identity: root / "snapshot",
    )
    candidate = tmp_path / "candidate"
    candidate_pdf = candidate / "cases" / case.case_id / f"{case.case_id}.pdf"
    candidate_pdf.parent.mkdir(parents=True)
    writer = PdfWriter()
    writer.add_blank_page(width=1_000_000, height=1_000_000)
    with candidate_pdf.open("wb") as stream:
        writer.write(stream)
    _bind_manifest_pdf(manifest, case.case_id, candidate_pdf)

    def worker(selected, case_dir, **kwargs):
        writer = PdfWriter()
        writer.add_blank_page(width=100, height=100)
        pdf = case_dir / f"{selected.case_id}.pdf"
        with pdf.open("wb") as stream:
            writer.write(stream)
        return manifest["cases"][0]

    monkeypatch.setattr(visual, "_run_worker", worker)
    monkeypatch.setattr(
        visual, "_pdf_semantic_evidence",
        lambda *args, **kwargs: (semantic, "Document\nTable\n", "text"),
    )
    monkeypatch.setattr(
        visual, "_rasterize",
        lambda *args, **kwargs: pytest.fail("oversized candidate was rasterized"),
    )
    with pytest.raises(visual.AcceptanceError, match="object graph differs"):
        visual._attest_candidate(candidate, manifest, {"input_hashes": {}})


@pytest.mark.parametrize(
    ("changed", "match"),
    [("page", "independent page attestation differs"),
     ("sheet", "independent contact sheet differs")],
)
def test_independent_attestation_rejects_reproduced_artifact_mismatch(
    tmp_path, monkeypatch, changed, match,
):
    case = visual.AcceptanceCase("one-case", "neutral")
    monkeypatch.setattr(visual, "acceptance_cases", lambda: (case,))
    manifest = _manifest()
    semantic = _passing_semantics()[0]
    manifest["cases"][0]["semantic_checks"] = [
        dataclasses.asdict(result) for result in semantic
    ]
    output = tmp_path / "output"
    output.mkdir()
    candidate = tmp_path / "candidate"
    candidate_pdf = candidate / "cases" / case.case_id / f"{case.case_id}.pdf"
    candidate_pdf.parent.mkdir(parents=True)
    candidate_pdf.write_bytes(b"same pdf")
    _bind_manifest_pdf(manifest, case.case_id, candidate_pdf)
    monkeypatch.setattr(visual, "OUTPUT_ROOT", output)
    monkeypatch.setattr(visual, "_pdf_object_evidence", _object_evidence)
    monkeypatch.setattr(
        visual, "_snapshot_inputs", lambda root, identity: root / "snapshot",
    )

    def worker(selected, case_dir, **kwargs):
        (case_dir / f"{selected.case_id}.pdf").write_bytes(b"same pdf")
        return manifest["cases"][0]

    monkeypatch.setattr(visual, "_run_worker", worker)
    monkeypatch.setattr(
        visual, "_pdf_semantic_evidence",
        lambda *args, **kwargs: (semantic, "Document\nTable\n", "text"),
    )
    expected_page = tmp_path / "expected-page"
    expected_page.write_bytes(b"expected page")
    manifest["review_artifacts"][1]["sha256"] = visual._sha256(expected_page)
    expected_sheet = tmp_path / "expected-sheet"
    expected_sheet.write_bytes(b"expected sheet")
    manifest["promotable_artifacts"][0]["sha256"] = visual._sha256(expected_sheet)

    def raster(selected, case_dir, **kwargs):
        page = case_dir / "page-1.png"
        is_fresh = "candidate-copies" not in case_dir.parts
        page.write_bytes(b"changed page" if changed == "page" and is_fresh else b"expected page")
        return [page], 0.01, 1

    def contact(selected, pages, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"changed sheet" if changed == "sheet" else b"expected sheet")

    monkeypatch.setattr(visual, "_rasterize", raster)
    monkeypatch.setattr(visual, "_contact_sheet", contact)
    with pytest.raises(visual.AcceptanceError, match=match):
        visual._attest_candidate(candidate, manifest, {"input_hashes": {}})


def test_independent_attestation_enforces_aggregate_pixel_budget(
    tmp_path, monkeypatch,
):
    cases = (
        visual.AcceptanceCase("case-one", "neutral"),
        visual.AcceptanceCase("case-two", "neutral"),
    )
    monkeypatch.setattr(visual, "acceptance_cases", lambda: cases)
    manifest = _manifest()
    semantic = _passing_semantics()[0]
    for record in manifest["cases"]:
        record["semantic_checks"] = [dataclasses.asdict(result) for result in semantic]
    by_id = {record["case_id"]: record for record in manifest["cases"]}
    output = tmp_path / "output"
    output.mkdir()
    monkeypatch.setattr(visual, "OUTPUT_ROOT", output)
    monkeypatch.setattr(visual, "_pdf_object_evidence", _object_evidence)
    monkeypatch.setattr(visual, "MAX_TOTAL_PIXELS", 100)
    monkeypatch.setattr(
        visual, "_snapshot_inputs", lambda root, identity: root / "snapshot",
    )
    candidate = tmp_path / "candidate"
    for selected in cases:
        pdf = candidate / "cases" / selected.case_id / f"{selected.case_id}.pdf"
        pdf.parent.mkdir(parents=True)
        pdf.write_bytes(b"same-pdf")
        _bind_manifest_pdf(manifest, selected.case_id, pdf)

    def worker(selected, case_dir, **kwargs):
        (case_dir / f"{selected.case_id}.pdf").write_bytes(b"same-pdf")
        return by_id[selected.case_id]

    monkeypatch.setattr(visual, "_run_worker", worker)
    monkeypatch.setattr(
        visual, "_pdf_semantic_evidence",
        lambda *args, **kwargs: (semantic, "Document\nTable\n", "text"),
    )
    budgets = []

    def raster(case, case_dir, *, pixel_budget, **kwargs):
        budgets.append(pixel_budget)
        if len(budgets) == 3:
            raise visual.AcceptanceError("aggregate pixel budget exhausted")
        return [], 0.01, 60

    monkeypatch.setattr(visual, "_rasterize", raster)
    monkeypatch.setattr(
        visual, "_contact_sheet", lambda case, pages, output: (
            output.parent.mkdir(parents=True, exist_ok=True), output.write_bytes(b"x")
        ),
    )
    monkeypatch.setattr(visual, "_sha256", lambda path: "a" * 64)
    with pytest.raises(visual.AcceptanceError, match="aggregate pixel budget"):
        visual._attest_candidate(
            candidate, manifest, {"input_hashes": {}},
        )
    assert budgets == [100, 100, 40]


def test_generate_verify_promote_coordinator_lifecycle(tmp_path, monkeypatch):
    from PIL import Image

    candidates, approved = _configure_store(tmp_path, monkeypatch)
    case = visual.AcceptanceCase("one-case", "neutral")
    input_hashes = {"tests/visual/table-widths.md": "a" * 64}
    identity = {
        "digest": visual._input_digest(input_hashes),
        "git_base": "test",
        "input_hashes": input_hashes,
        "dirty_render_inputs": [],
        "unrelated_worktree_dirty": False,
    }
    monkeypatch.setattr(visual, "acceptance_cases", lambda: (case,))
    monkeypatch.setattr(visual, "_source_identity", lambda: identity)

    def snapshot(candidate, ignored_identity):
        root = candidate / "input-snapshot"
        fixture = root / visual.SOURCE.relative_to(visual.ROOT)
        fixture.parent.mkdir(parents=True)
        fixture.write_text("---\ntitle: Synthetic\n---\nbody\n")
        return root

    def worker(selected, case_dir, **kwargs):
        pdf = case_dir / f"{selected.case_id}.pdf"
        pdf.write_bytes(b"pdf")
        return {
            "case_id": selected.case_id,
            "pdf": pdf.name,
            "pdf_bytes": pdf.stat().st_size,
            "pdf_sha256": visual._sha256(pdf),
            "measurements": {"pages": [{"page": 1, "width": 1, "height": 1}]},
            "checks": [
                {"check_id": check_id, "status": "passed", "detail": "test"}
                for check_id in visual.GEOMETRY_CHECK_IDS
            ],
            "render_seconds": 0.01,
        }

    def raster(selected, case_dir, **kwargs):
        page = case_dir / "page-1.png"
        Image.new("RGB", (2, 2), "white").save(page)
        return [page], 0.01, 4

    def contact(selected, pages, output):
        output.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (2, 2), "white").save(output)

    monkeypatch.setattr(visual, "_snapshot_inputs", snapshot)
    monkeypatch.setattr(visual, "_run_worker", worker)
    monkeypatch.setattr(visual, "_pdf_object_evidence", _object_evidence)
    monkeypatch.setattr(visual, "_rasterize", raster)
    monkeypatch.setattr(visual, "_contact_sheet", contact)
    candidate = visual.generate()
    manifest = visual.validate_candidate(candidate, require_current=True)
    assert len(manifest["review_artifacts"]) == 2
    version = visual.promote(candidate)
    assert version.is_dir()
    assert visual._active_digest() == identity["digest"]
    assert json.loads((approved / "active.json").read_text())["previous_digest"] is None


def test_generation_cleanup_preserves_original_error_and_writes_failure_marker(
    tmp_path, monkeypatch,
):
    candidate = tmp_path / "candidate"
    snapshot = candidate / "input-snapshot"
    snapshot.mkdir(parents=True)
    (candidate / "manifest.json").write_text("stale", encoding="utf-8")
    case = visual.AcceptanceCase("one-case", "neutral")
    monkeypatch.setattr(visual, "acceptance_cases", lambda: (case,))
    monkeypatch.setattr(
        visual, "_run_worker",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            visual.AcceptanceError("original render failure")
        ),
    )
    original_rmtree = visual.shutil.rmtree

    def fail_cases_cleanup(path, *args, **kwargs):
        if Path(path).name == "cases":
            raise OSError("injected cleanup failure")
        return original_rmtree(path, *args, **kwargs)

    monkeypatch.setattr(visual.shutil, "rmtree", fail_cases_cleanup)
    with pytest.raises(visual.AcceptanceError, match="original render failure") as raised:
        visual._generate_locked(
            candidate,
            candidate_id="candidate-test",
            identity={"input_hashes": {}},
            review_baseline=None,
            deadline=time.monotonic() + 1,
            snapshot=snapshot,
            fixture=tmp_path / "fixture.md",
        )
    assert any("injected cleanup failure" in note for note in raised.value.__notes__)
    assert not (candidate / "manifest.json").exists()
    assert json.loads((candidate / "failure.json").read_text())["status"] == "failed"


def test_generation_interrupt_cleans_raw_artifacts_and_marks_failure(
    tmp_path, monkeypatch,
):
    candidate = tmp_path / "candidate"
    snapshot = candidate / "input-snapshot"
    snapshot.mkdir(parents=True)
    case = visual.AcceptanceCase("one-case", "neutral")
    monkeypatch.setattr(visual, "acceptance_cases", lambda: (case,))
    monkeypatch.setattr(
        visual, "_run_worker",
        lambda *args, **kwargs: (_ for _ in ()).throw(KeyboardInterrupt()),
    )
    with pytest.raises(KeyboardInterrupt):
        visual._generate_locked(
            candidate,
            candidate_id="candidate-interrupted",
            identity={"input_hashes": {}},
            review_baseline=None,
            deadline=time.monotonic() + 1,
            snapshot=snapshot,
            fixture=tmp_path / "fixture.md",
        )
    assert not (candidate / "cases").exists()
    assert not snapshot.exists()
    assert json.loads((candidate / "failure.json").read_text()) == {
        "candidate_id": "candidate-interrupted",
        "schema_version": visual.SCHEMA_VERSION,
        "status": "failed",
    }


def _real_acceptance_prerequisites_available() -> bool:
    if not all(
        shutil.which(name)
        for name in ("pdfinfo", "pdftotext", "pdftoppm", "pkg-config")
    ):
        return False
    return subprocess.run(
        ["pkg-config", "--exists", "pango"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        check=False, timeout=10,
    ).returncode == 0


@pytest.mark.skipif(
    not _real_acceptance_prerequisites_available(),
    reason="visual acceptance integration prerequisites are unavailable",
)
def test_real_one_case_acceptance_pipeline(tmp_path, monkeypatch):
    output = tmp_path / "output"
    candidates = output / "candidates"
    approved = tmp_path / "approved-root"
    case = visual.AcceptanceCase("automatic-neutral", "neutral")
    monkeypatch.setattr(visual, "OUTPUT_ROOT", output)
    monkeypatch.setattr(visual, "CANDIDATE_ROOT", candidates)
    monkeypatch.setattr(visual, "APPROVED_ROOT", approved)
    monkeypatch.setattr(visual, "APPROVED_VERSIONS", approved / "approved")
    monkeypatch.setattr(visual, "ACTIVE_POINTER", approved / "active.json")
    monkeypatch.setattr(visual, "acceptance_cases", lambda: (case,))
    candidate = visual.generate()
    manifest = visual.validate_candidate(candidate, require_current=True)
    assert len(manifest["cases"]) == 1
    assert all(path.is_file() for path in candidate.glob("cases/*/page-*.png"))
    before = {
        path.relative_to(candidate).as_posix(): visual._sha256(path)
        for path in candidate.rglob("*") if path.is_file()
    }
    version = visual.promote(candidate)
    after = {
        path.relative_to(candidate).as_posix(): visual._sha256(path)
        for path in candidate.rglob("*") if path.is_file()
    }
    assert after == before
    assert version.is_dir()
    assert visual._active_digest() == manifest["source"]["digest"]


def test_promotion_rejects_manifest_digest_path_injection(tmp_path, monkeypatch):
    candidates, _ = _configure_store(tmp_path, monkeypatch)
    candidate = _make_candidate(candidates, "a")
    manifest_path = candidate / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["source"]["digest"] = "/tmp/escape"
    manifest_path.write_bytes(visual._json_bytes(manifest))
    with pytest.raises(visual.AcceptanceError, match="source digest"):
        visual.promote(candidate)


def test_promotion_rejects_outside_path_without_mutating_it(tmp_path, monkeypatch):
    candidates, _ = _configure_store(tmp_path, monkeypatch)
    outside = tmp_path / "outside" / "missing"
    with pytest.raises(visual.AcceptanceError):
        visual.promote(outside)
    assert not outside.exists()
    assert not (outside / ".lease").exists()


def test_promotion_rejects_symlinked_candidate_and_lease(tmp_path, monkeypatch):
    candidates, _ = _configure_store(tmp_path, monkeypatch)
    candidate = _make_candidate(candidates, "a")
    alias = candidates / "alias"
    alias.symlink_to(candidate, target_is_directory=True)
    with pytest.raises(visual.AcceptanceError, match="must not be a symlink"):
        visual.promote(alias)
    outside = tmp_path / "outside-lease"
    outside.write_bytes(b"sentinel")
    (candidate / ".lease").symlink_to(outside)
    with pytest.raises(visual.AcceptanceError, match="lease safely"):
        visual.promote(candidate)
    assert outside.read_bytes() == b"sentinel"


def test_prune_dry_run_and_apply_choose_same_old_candidate(tmp_path, monkeypatch):
    output = tmp_path / "output"
    root = output / "candidates"
    monkeypatch.setattr(visual, "CANDIDATE_ROOT", root)
    monkeypatch.setattr(visual, "OUTPUT_ROOT", output)
    candidates = [_make_candidate(root, character) for character in "abcde"]
    dry = visual.prune_candidates(apply=False)
    assert dry == candidates[:2]
    applied = visual.prune_candidates(apply=True)
    assert applied == dry
    assert all(not path.exists() for path in dry)
    assert all(path.exists() for path in candidates[2:])


def test_prune_never_removes_pinned_candidate(tmp_path, monkeypatch):
    output = tmp_path / "output"
    root = output / "candidates"
    monkeypatch.setattr(visual, "CANDIDATE_ROOT", root)
    monkeypatch.setattr(visual, "OUTPUT_ROOT", output)
    candidates = [_make_candidate(root, character) for character in "abcd"]
    (candidates[0] / ".pin").touch()
    selected = visual.prune_candidates(apply=False)
    assert candidates[0] not in selected


def test_prune_applies_aggregate_byte_budget(tmp_path, monkeypatch):
    output = tmp_path / "output"
    root = output / "candidates"
    root.mkdir(parents=True)
    paths = []
    for name in "abcd":
        path = root / name
        path.mkdir()
        (path / "manifest.json").write_bytes(b"x" * 60)
        paths.append(path)
    monkeypatch.setattr(visual, "CANDIDATE_ROOT", root)
    monkeypatch.setattr(visual, "OUTPUT_ROOT", output)
    monkeypatch.setattr(visual, "MAX_CANDIDATE_BYTES", 100)
    assert visual.prune_candidates(apply=False) == paths[:3]


def test_prune_removes_single_success_over_hard_byte_cap(tmp_path, monkeypatch):
    output = tmp_path / "output"
    root = output / "candidates"
    candidate = root / "only"
    candidate.mkdir(parents=True)
    (candidate / "manifest.json").write_bytes(b"x" * 101)
    monkeypatch.setattr(visual, "CANDIDATE_ROOT", root)
    monkeypatch.setattr(visual, "OUTPUT_ROOT", output)
    monkeypatch.setattr(visual, "MAX_CANDIDATE_BYTES", 100)
    assert visual.prune_candidates(apply=False) == [candidate]


def test_prune_does_not_snapshot_while_registry_is_leased(tmp_path, monkeypatch):
    output = tmp_path / "output"
    root = output / "candidates"
    candidate = _make_candidate(root, "a")
    monkeypatch.setattr(visual, "CANDIDATE_ROOT", root)
    monkeypatch.setattr(visual, "OUTPUT_ROOT", output)
    with visual._lease(output / "candidate-registry.lock"):
        assert visual.prune_candidates(apply=False) == []
    assert candidate.exists()


def test_prune_propagates_unsafe_registry_lease(tmp_path, monkeypatch):
    output = tmp_path / "output"
    root = output / "candidates"
    root.mkdir(parents=True)
    outside = tmp_path / "outside-lock"
    outside.write_bytes(b"sentinel")
    (output / "candidate-registry.lock").symlink_to(outside)
    monkeypatch.setattr(visual, "CANDIDATE_ROOT", root)
    monkeypatch.setattr(visual, "OUTPUT_ROOT", output)
    with pytest.raises(visual.AcceptanceError, match="lease safely"):
        visual.prune_candidates(apply=True)
    assert outside.read_bytes() == b"sentinel"


def test_prune_rejects_symlinked_candidate_root_without_touching_target(
    tmp_path, monkeypatch,
):
    output = tmp_path / "output"
    output.mkdir()
    outside = tmp_path / "outside-candidates"
    protected = outside / "protected" / "sentinel.txt"
    protected.parent.mkdir(parents=True)
    protected.write_text("keep")
    root = output / "candidates"
    root.symlink_to(outside, target_is_directory=True)
    monkeypatch.setattr(visual, "OUTPUT_ROOT", output)
    monkeypatch.setattr(visual, "CANDIDATE_ROOT", root)
    with pytest.raises(visual.AcceptanceError, match="must not be a symlink"):
        visual.prune_candidates(apply=True)
    assert protected.read_text() == "keep"


def test_prune_rejects_symlinked_output_ancestor_without_touching_target(
    tmp_path, monkeypatch,
):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside = tmp_path / "outside-output"
    candidate = outside / "pdf" / "visual-acceptance" / "candidates" / "old"
    candidate.mkdir(parents=True)
    protected = candidate / "sentinel.txt"
    protected.write_text("keep")
    (workspace / "output").symlink_to(outside, target_is_directory=True)
    output = workspace / "output" / "pdf" / "visual-acceptance"
    monkeypatch.setattr(visual, "OUTPUT_ROOT", output)
    monkeypatch.setattr(visual, "CANDIDATE_ROOT", output / "candidates")
    with pytest.raises(visual.AcceptanceError, match="symlinked path component"):
        visual.prune_candidates(apply=True)
    assert protected.read_text() == "keep"


def test_promotion_rejects_symlinked_approved_ancestor_without_touching_target(
    tmp_path, monkeypatch,
):
    candidates, _ = _configure_store(tmp_path, monkeypatch)
    outside = tmp_path / "outside-approved"
    outside.mkdir()
    protected = outside / "sentinel.txt"
    protected.write_text("keep")
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "docs").symlink_to(outside, target_is_directory=True)
    approved = workspace / "docs" / "visual-acceptance"
    monkeypatch.setattr(visual, "APPROVED_ROOT", approved)
    monkeypatch.setattr(visual, "APPROVED_VERSIONS", approved / "approved")
    monkeypatch.setattr(visual, "ACTIVE_POINTER", approved / "active.json")
    candidate = _make_candidate(candidates, "a")
    manifest = json.loads((candidate / "manifest.json").read_text())
    monkeypatch.setattr(visual, "_source_identity", lambda: manifest["source"])
    with pytest.raises(visual.AcceptanceError, match="symlinked path component"):
        visual.promote(candidate)
    assert protected.read_text() == "keep"


def test_prune_stops_at_candidate_root_entry_limit(tmp_path, monkeypatch):
    output = tmp_path / "output"
    root = output / "candidates"
    root.mkdir(parents=True)
    for number in range(4):
        (root / f"candidate-{number}").mkdir()
    monkeypatch.setattr(visual, "OUTPUT_ROOT", output)
    monkeypatch.setattr(visual, "CANDIDATE_ROOT", root)
    monkeypatch.setattr(visual, "MAX_CANDIDATE_ROOT_ENTRIES", 2)
    with pytest.raises(visual.AcceptanceError, match="root exceeds entry limit"):
        visual.prune_candidates(apply=True)
    assert len(list(root.iterdir())) == 4


def test_prune_mixed_success_and_incomplete_pool_parity(tmp_path, monkeypatch):
    output = tmp_path / "output"
    root = output / "candidates"
    monkeypatch.setattr(visual, "OUTPUT_ROOT", output)
    monkeypatch.setattr(visual, "CANDIDATE_ROOT", root)
    successful = [_make_candidate(root, f"s{number}") for number in range(4)]
    incomplete = []
    for number in range(3):
        path = root / f"f{number}"
        path.mkdir(parents=True)
        (path / "failure.json").write_text("{}")
        incomplete.append(path)
    expected = [successful[0], incomplete[0]]
    assert visual.prune_candidates(apply=False) == expected
    assert visual.prune_candidates(apply=True) == expected
    assert all(not path.exists() for path in expected)


def test_prune_treats_failure_marker_as_authoritative_over_manifest(
    tmp_path, monkeypatch,
):
    output = tmp_path / "output"
    root = output / "candidates"
    monkeypatch.setattr(visual, "OUTPUT_ROOT", output)
    monkeypatch.setattr(visual, "CANDIDATE_ROOT", root)
    successful = [_make_candidate(root, marker) for marker in ("a", "b", "c", "d")]
    stale_failed = _make_candidate(root, "z")
    (stale_failed / "failure.json").write_text("{}", encoding="utf-8")
    selected = visual.prune_candidates(apply=False)
    assert selected == [successful[0]]
    assert stale_failed not in selected


def test_candidate_tree_size_stops_at_entry_limit(tmp_path, monkeypatch):
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    for number in range(4):
        (candidate / f"file-{number}").touch()
    monkeypatch.setattr(visual, "MAX_CANDIDATE_ENTRIES", 2)
    monkeypatch.setattr(visual, "MAX_CANDIDATE_BYTES", 100)
    assert visual._candidate_tree_size(candidate) == 101


def test_candidate_tree_size_propagates_unreliable_traversal(monkeypatch):
    monkeypatch.setattr(
        visual, "_scan_tree_bounded",
        lambda path: (_ for _ in ()).throw(
            visual.AcceptanceError("candidate tree changed during traversal")
        ),
    )
    with pytest.raises(visual.AcceptanceError, match="changed during traversal"):
        visual._candidate_tree_size(Path("candidate"))


def test_prune_skips_candidate_with_held_lease(tmp_path, monkeypatch):
    output = tmp_path / "output"
    root = output / "candidates"
    monkeypatch.setattr(visual, "CANDIDATE_ROOT", root)
    monkeypatch.setattr(visual, "OUTPUT_ROOT", output)
    candidates = [_make_candidate(root, character) for character in "abcde"]
    with visual._lease(candidates[0] / ".lease"):
        selected = visual.prune_candidates(apply=False)
    assert candidates[0] not in selected


@pytest.mark.parametrize(
    ("argv", "expected"),
    [
        (["generate"], ("generate", None)),
        (["verify", "candidate"], ("verify", Path("candidate"))),
        (["promote", "candidate"], ("promote", Path("candidate"))),
        (["prune", "--dry-run"], ("prune", False)),
        (["prune", "--apply"], ("prune", True)),
    ],
)
def test_visual_acceptance_cli_dispatches_subcommands(monkeypatch, argv, expected):
    calls = []
    monkeypatch.setattr(visual, "generate", lambda: calls.append(("generate", None)))
    monkeypatch.setattr(
        visual, "verify_candidate", lambda path: calls.append(("verify", path)),
    )
    monkeypatch.setattr(visual, "promote", lambda path: calls.append(("promote", path)))
    monkeypatch.setattr(
        visual, "prune_candidates",
        lambda *, apply=False: calls.append(("prune", apply)),
    )
    assert visual.main(argv) == 0
    assert calls == [expected]


def test_verify_candidate_holds_prune_lease_while_validating(tmp_path, monkeypatch):
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    lease_active = False

    @contextlib.contextmanager
    def lease(path, **kwargs):
        nonlocal lease_active
        assert path == candidate / ".lease"
        lease_active = True
        try:
            yield
        finally:
            lease_active = False

    monkeypatch.setattr(visual, "_candidate_directory", lambda path: candidate)
    monkeypatch.setattr(visual, "_lease", lease)
    monkeypatch.setattr(
        visual, "validate_candidate",
        lambda path: {"validated": path} if lease_active else pytest.fail("lease missing"),
    )
    assert visual.verify_candidate(candidate) == {"validated": candidate}
    assert lease_active is False


def test_visual_acceptance_cli_rejects_conflicting_prune_modes():
    with pytest.raises(SystemExit) as raised:
        visual.main(["prune", "--dry-run", "--apply"])
    assert raised.value.code == 2


def test_checked_in_active_evidence_resolves_and_hash_verifies():
    pointer = json.loads(visual.ACTIVE_POINTER.read_text(encoding="utf-8"))
    assert visual._active_digest() == pointer["digest"]
