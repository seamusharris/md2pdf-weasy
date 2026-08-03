"""Hermetic contracts for the explicit v0.1.0 compatibility workflow."""

from __future__ import annotations

import contextlib
import copy
from concurrent.futures import ThreadPoolExecutor
import io
import json
import multiprocessing
import os
from pathlib import Path
import sys
import tarfile
import threading
import time

import pytest
from PIL import Image

from tools.compatibility import (
    artifacts, cli, history, io as compat_io, model, process, provenance,
    store, structure, verification,
)


def _manifest() -> dict:
    digest = "a" * 64
    case = {
        "html": {"sha256": digest, "semantic_sha256": digest,
                 "content_sha256": digest, "table_count": 0, "tables": []},
        "pdf": {"sha256": digest, "text_sha256": digest, "bytes": 1,
                "pages": 1, "page_boxes": [[1, 1]], "lang": "en-AU",
                "title": "Synthetic", "struct_tree": True, "marked": True},
        "rasters": [{"path": "page.png", "width": 1, "height": 1, "sha256": digest}],
        "decoded_pixels": 1,
    }
    return model.signed_manifest({
        "schema_version": model.SCHEMA_VERSION,
        "kind": "md2pdf-v0.1-compatibility",
        "provenance": {"tag": model.TAG, "tag_commit": model.TAG_COMMIT,
                       "current_base_commit": "base", "fixture_sha256": digest,
                       "source_hashes": {"fixture": digest},
                       "active_visual_acceptance_digest": digest,
                       "publication_basis": "immutable-render-snapshot-v1",
                       "environment": {"python": "test"}, "commands": ["test"]},
        "cases": [{"id": mode, **copy.deepcopy(case)} for mode in model.MODE_IDS],
        "checks": [{"id": check, "status": "pass", "detail": "ok"} for check in model.CHECK_IDS],
        "contact_sheet": {"path": "sheet.png", "width": 1, "height": 1, "sha256": digest},
        "decision": "compatible",
    })


def test_manifest_is_canonical_signed_and_complete():
    value = _manifest()
    assert model.validate_manifest(json.loads(model.canonical_bytes(value))) == value
    assert model.canonical_bytes({"é": 2, "a": 1}) == b'{"a":1,"\xc3\xa9":2}\n'
    value["cases"].reverse()
    with pytest.raises(model.CompatibilityError, match="incomplete or reordered"):
        model.validate_manifest(value)
    value = _manifest()
    value["decision"] = "tampered but schema-valid"
    with pytest.raises(model.CompatibilityError, match="digest mismatch"):
        model.validate_manifest(value)


def test_failure_schema_is_bounded_and_categorical():
    value = {"schema_version": 1, "kind": "md2pdf-v0.1-compatibility-failure",
             "category": "render", "phase": "render-pdf", "diagnostic": "failed"}
    assert model.validate_failure(value) == value
    value["category"] = "mystery"
    with pytest.raises(model.CompatibilityError, match="category"):
        model.validate_failure(value)


def test_failure_diagnostic_accepts_exact_and_rejects_one_over(monkeypatch):
    monkeypatch.setattr(model, "MAX_DIAGNOSTIC_BYTES", 8)
    value = {"schema_version": 1, "kind": "md2pdf-v0.1-compatibility-failure",
             "category": "render", "phase": "render-pdf", "diagnostic": "12345678"}
    model.validate_failure(value)
    value["diagnostic"] += "9"
    with pytest.raises(model.CompatibilityError, match="too large"):
        model.validate_failure(value)


@pytest.mark.parametrize("field", ["pdf", "pages"])
def test_pdf_limits_accept_exact_and_reject_one_over(monkeypatch, field):
    monkeypatch.setattr(model, "MAX_PDF_BYTES", 10)
    monkeypatch.setattr(model, "MAX_PAGES_PER_MODE", 3)
    model.validate_pdf_limits(10, 3)
    args = (11, 3) if field == "pdf" else (10, 4)
    with pytest.raises(model.CompatibilityError):
        model.validate_pdf_limits(*args)


@pytest.mark.parametrize("field", ["bytes", "pixels"])
def test_image_limits_accept_exact_and_reject_one_over(monkeypatch, field):
    monkeypatch.setattr(model, "MAX_IMAGE_BYTES", 10)
    monkeypatch.setattr(model, "MAX_TOTAL_PIXELS", 12)
    assert model.validate_image_limits(10, 3, 4) == 12
    args = (11, 3, 4) if field == "bytes" else (10, 13, 1)
    with pytest.raises(model.CompatibilityError):
        model.validate_image_limits(*args)


def test_aggregate_pixels_accept_exact_and_reject_one_over(monkeypatch):
    monkeypatch.setattr(model, "MAX_TOTAL_PIXELS", 12)
    model.validate_total_pixels(12)
    with pytest.raises(model.CompatibilityError):
        model.validate_total_pixels(13)


def test_oversize_pdf_is_rejected_before_parser(tmp_path, monkeypatch):
    pdf = tmp_path / "large.pdf"
    with pdf.open("wb") as stream:
        stream.truncate(model.MAX_PDF_BYTES + 1)
    called = False

    class Reader:
        def __init__(self, *args, **kwargs):
            nonlocal called
            called = True

    import pypdf
    monkeypatch.setattr(pypdf, "PdfReader", Reader)
    with pytest.raises(model.CompatibilityError, match="size"):
        structure.pdf_evidence(pdf)
    assert not called


def _write_tar(path: Path, entries: list[tuple[str, bytes, str]]) -> None:
    with tarfile.open(path, "w") as bundle:
        for name, data, kind in entries:
            info = tarfile.TarInfo(name)
            if kind == "file":
                info.size = len(data)
                bundle.addfile(info, io.BytesIO(data))
            elif kind == "symlink":
                info.type = tarfile.SYMTYPE
                info.linkname = "target"
                bundle.addfile(info)
            elif kind == "hardlink":
                info.type = tarfile.LNKTYPE
                info.linkname = "target"
                bundle.addfile(info)
            elif kind == "fifo":
                info.type = tarfile.FIFOTYPE
                bundle.addfile(info)


def test_archive_limits_accept_exact_and_reject_one_over(tmp_path):
    archive = tmp_path / "tag.tar"
    _write_tar(archive, [("one.txt", b"abc", "file")])
    destination = tmp_path / "exact"
    destination.mkdir()
    history.safe_extract_tar(archive, destination, max_entries=1, max_file_bytes=3, max_total_bytes=3)
    assert (destination / "one.txt").read_bytes() == b"abc"
    for kwargs in ({"max_entries": 0}, {"max_file_bytes": 2}, {"max_total_bytes": 2}):
        target = tmp_path / ("over-" + next(iter(kwargs)))
        target.mkdir()
        with pytest.raises(model.CompatibilityError):
            history.safe_extract_tar(archive, target, **kwargs)


@pytest.mark.parametrize("entry", [
    ("../escape", "file"), ("/absolute", "file"), ("link", "symlink"),
    ("hard", "hardlink"), ("pipe", "fifo"),
])
def test_archive_rejects_traversal_and_links(tmp_path, entry):
    archive = tmp_path / "bad.tar"
    _write_tar(archive, [(entry[0], b"x", entry[1])])
    destination = tmp_path / "out"
    destination.mkdir()
    with pytest.raises(model.CompatibilityError):
        history.safe_extract_tar(archive, destination)


def test_process_capture_accepts_exact_and_rejects_one_over(tmp_path):
    command = (sys.executable, "-c", "import sys;sys.stdout.write('abcd')")
    assert process.run_bounded(command, cwd=tmp_path, capture_limit=4)[0] == "abcd"
    with pytest.raises(model.CompatibilityError, match="output exceeds"):
        process.run_bounded(command, cwd=tmp_path, capture_limit=3)


def test_process_timeout_terminates_group(tmp_path, monkeypatch):
    pid_file = tmp_path / "child.pid"
    script = (
        "import pathlib,subprocess,sys,time;"
        "p=subprocess.Popen([sys.executable,'-c','import time;time.sleep(10)']);"
        f"pathlib.Path({str(pid_file)!r}).write_text(str(p.pid));time.sleep(10)"
    )
    command = (sys.executable, "-c", script)
    original_capture = process._capture_bounded

    def capture_after_ready(child, selector, **kwargs):
        deadline = time.monotonic() + 30
        while not pid_file.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert pid_file.exists(), "child did not signal readiness"
        kwargs["started"] = time.monotonic() - kwargs["timeout"]
        return original_capture(child, selector, **kwargs)

    monkeypatch.setattr(process, "_capture_bounded", capture_after_ready)
    with pytest.raises(model.CompatibilityError, match="timed out"):
        process.run_bounded(command, cwd=tmp_path, timeout=30.0)
    child_pid = int(pid_file.read_text())
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        try:
            os.kill(child_pid, 0)
        except ProcessLookupError:
            break
        time.sleep(0.02)
    else:
        pytest.fail("child process survived bounded group termination")


def test_process_closed_pipes_still_obeys_deadline(tmp_path):
    command = (sys.executable, "-c", "import os,time;os.close(1);os.close(2);time.sleep(10)")
    with pytest.raises(model.CompatibilityError, match="timed out") as caught:
        process.run_bounded(command, cwd=tmp_path, timeout=0.2, phase="closed-pipes")
    assert (caught.value.category, caught.value.phase) == ("timeout", "closed-pipes")


def test_process_interrupt_terminates_group(tmp_path, monkeypatch):
    pid_file = tmp_path / "interrupt-child.pid"
    script = (
        "import pathlib,subprocess,sys,time;"
        "p=subprocess.Popen([sys.executable,'-c','import time;time.sleep(10)']);"
        f"pathlib.Path({str(pid_file)!r}).write_text(str(p.pid));time.sleep(10)"
    )
    parent_pid = None
    original_popen = process.subprocess.Popen

    def capture_parent(*args, **kwargs):
        nonlocal parent_pid
        child = original_popen(*args, **kwargs)
        parent_pid = child.pid
        return child

    def interrupt(*args, **kwargs):
        deadline = time.monotonic() + 30
        while not pid_file.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        raise KeyboardInterrupt

    monkeypatch.setattr(process.subprocess, "Popen", capture_parent)
    monkeypatch.setattr(process, "_capture_bounded", interrupt)
    with pytest.raises(KeyboardInterrupt):
        process.run_bounded((sys.executable, "-c", script), cwd=tmp_path)
    child_pid = int(pid_file.read_text())
    for pid in (parent_pid, child_pid):
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                break
            time.sleep(0.02)
        else:
            pytest.fail(f"interrupted process survived cleanup: {pid}")


def test_process_cleanup_kills_descendant_after_leader_exits(tmp_path):
    pid_file = tmp_path / "orphan.pid"
    child_code = (
        "import pathlib,signal,time;"
        "signal.signal(signal.SIGTERM,signal.SIG_IGN);"
        f"pathlib.Path({str(pid_file)!r}).write_text(str(__import__('os').getpid()));"
        "__import__('os').close(1);__import__('os').close(2);"
        "time.sleep(10)"
    )
    leader_code = f"""import pathlib, subprocess, sys, time
subprocess.Popen([sys.executable, '-c', {child_code!r}])
p = pathlib.Path({str(pid_file)!r})
deadline = time.monotonic() + 30
while not p.exists() and time.monotonic() < deadline:
    time.sleep(0.01)
"""
    assert process.run_bounded(
        (sys.executable, "-c", leader_code), cwd=tmp_path, timeout=30,
    ) == ("", "")
    descendant = int(pid_file.read_text())
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        try:
            os.kill(descendant, 0)
        except ProcessLookupError:
            break
        time.sleep(0.02)
    else:
        pytest.fail("descendant survived exited-leader cleanup")


def test_process_start_failure_is_categorical(tmp_path, monkeypatch):
    def fail(*args, **kwargs):
        raise FileNotFoundError("private executable path")

    monkeypatch.setattr(process.subprocess, "Popen", fail)
    with pytest.raises(model.CompatibilityError, match="could not start") as caught:
        process.run_bounded(("missing",), cwd=tmp_path, category="render", phase="html", case="current-auto")
    assert (caught.value.category, caught.value.phase, caught.value.case) == ("render", "html", "current-auto")


def test_process_nonzero_exit_preserves_context_and_stderr(tmp_path):
    command = (
        sys.executable, "-c",
        "import sys;sys.stdout.write('public');sys.stderr.write('specific failure');sys.exit(7)",
    )
    with pytest.raises(model.CompatibilityError, match=r"failed \(7\): specific failure") as caught:
        process.run_bounded(
            command, cwd=tmp_path, category="raster",
            phase="rasterize", case="current-auto",
        )
    assert (caught.value.category, caught.value.phase, caught.value.case) == (
        "raster", "rasterize", "current-auto",
    )


def test_empty_version_output_is_prerequisite_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(process, "run_bounded", lambda *args, **kwargs: ("", ""))
    with pytest.raises(model.CompatibilityError, match="no output") as caught:
        process.probe_version(("tool", "--version"), cwd=tmp_path)
    assert (caught.value.category, caught.value.phase) == ("prerequisite", "probe")


def test_tree_limits_accept_exact_and_reject_one_over(tmp_path):
    root = tmp_path / "tree"
    (root / "level").mkdir(parents=True)
    (root / "level" / "file").write_bytes(b"123")
    assert store.tree_stats(root, max_entries=2, max_bytes=3, max_depth=1) == (2, 3)
    for kwargs in ({"max_entries": 1}, {"max_bytes": 2}, {"max_depth": 0}):
        with pytest.raises(model.CompatibilityError):
            store.tree_stats(root, **kwargs)


def test_candidate_root_limit_accepts_exact_and_rejects_one_over(tmp_path, monkeypatch):
    root = tmp_path / "candidates"
    root.mkdir()
    monkeypatch.setattr(store, "MAX_CANDIDATE_ROOT_ENTRIES", 2)
    (root / "a").mkdir()
    (root / "b").mkdir()
    store._ensure_root(root)
    (root / "c").mkdir()
    with pytest.raises(model.CompatibilityError, match="root entry"):
        store._ensure_root(root)


def test_allocation_reserves_lock_and_candidate_capacity(tmp_path, monkeypatch):
    root = tmp_path / "candidates"
    root.mkdir()
    (root / "existing").mkdir()
    monkeypatch.setattr(store, "MAX_CANDIDATE_ROOT_ENTRIES", 3)
    allocated = store.allocate_candidate(root)
    assert allocated.is_dir()
    before = set(root.iterdir())
    with pytest.raises(model.CompatibilityError, match="capacity"):
        store.allocate_candidate(root)
    assert set(root.iterdir()) == before


def test_concurrent_allocations_are_unique_and_contained(tmp_path):
    root = tmp_path / "candidates"
    results: list[Path] = []
    errors: list[BaseException] = []

    def allocate():
        try:
            results.append(store.allocate_candidate(root))
        except BaseException as exc:
            errors.append(exc)

    threads = [threading.Thread(target=allocate) for _ in range(12)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(3)
    assert all(not thread.is_alive() for thread in threads)
    assert errors == []
    assert len({path.name for path in results}) == 12
    assert all(path.parent.resolve() == root.resolve() for path in results)


def test_concurrent_allocation_never_exceeds_capacity(tmp_path, monkeypatch):
    root = tmp_path / "bounded-candidates"
    root.mkdir()
    (root / "existing").mkdir()
    monkeypatch.setattr(store, "MAX_CANDIDATE_ROOT_ENTRIES", 3)
    start_barrier = threading.Barrier(2)
    observed_barrier = threading.Barrier(2)
    thread_state = threading.local()
    original_listdir = store.os.listdir
    results, errors = [], []

    def synchronized_listdir(path):
        result = original_listdir(path)
        if threading.current_thread() is not threading.main_thread():
            thread_state.calls = getattr(thread_state, "calls", 0) + 1
            if thread_state.calls == 2:
                observed_barrier.wait(3)
        return result

    monkeypatch.setattr(store.os, "listdir", synchronized_listdir)

    def allocate():
        start_barrier.wait()
        try:
            results.append(store.allocate_candidate(root))
        except model.CompatibilityError as exc:
            errors.append(exc)

    threads = [threading.Thread(target=allocate) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(3)
    assert all(not thread.is_alive() for thread in threads)
    assert len(results) == 1 and len(errors) == 1
    assert len(list(root.iterdir())) == 3


def test_write_all_handles_partial_and_zero_progress(monkeypatch):
    emitted = bytearray()

    def partial(fd, value):
        count = min(2, len(value))
        emitted.extend(bytes(value[:count]))
        return count

    monkeypatch.setattr(compat_io.os, "write", partial)
    compat_io.write_all(7, b"abcdef")
    assert emitted == b"abcdef"
    monkeypatch.setattr(compat_io.os, "write", lambda fd, value: 0)
    with pytest.raises(OSError, match="no progress"):
        compat_io.write_all(7, b"x")


def _candidate(root: Path, index: int, kind: str = "success") -> Path:
    path = root / f"20260101T0000{index:02d}Z-{index:032x}"
    path.mkdir(parents=True)
    if kind == "success":
        value = _manifest()
        store.atomic_json(path / "manifest.json", value)
        store.atomic_json(
            path / "success.json", {"decision_digest": value["decision_digest"]},
        )
    else:
        store.atomic_json(path / "failure.json", {
            "schema_version": 1, "kind": "md2pdf-v0.1-compatibility-failure",
            "category": "verify", "phase": "test", "case": None,
            "diagnostic": "synthetic failure", "cleanup_notes": [],
        })
    return path


def test_prune_dry_run_apply_parity_and_pin_exclusion(tmp_path):
    root = tmp_path / "candidates"
    candidates = [_candidate(root, index) for index in range(6)]
    candidates[0].joinpath(".pin").touch()
    dry = store.prune(apply=False, root=root)
    applied = store.prune(apply=True, root=root)
    assert applied == dry
    assert candidates[0].exists()
    assert all(not (root / name).exists() for name in applied)


def test_prune_enforces_success_failure_and_byte_retention(tmp_path):
    root = tmp_path / "count-candidates"
    successes = [_candidate(root, index, "success") for index in range(5)]
    failures = [_candidate(root, index, "failed") for index in range(10, 14)]
    selected = set(store.prune(apply=False, root=root))
    assert selected == {item.name for item in [*successes[:2], *failures[:2]]}

    budget_root = tmp_path / "budget-candidates"
    budgeted = [_candidate(budget_root, index) for index in range(3)]
    for item in budgeted:
        (item / "payload").write_bytes(b"1234")
    two_candidates = 2 * store.tree_stats(budgeted[0])[1]
    assert store.prune(
        apply=False, root=budget_root, max_total_bytes=two_candidates,
    ) == [budgeted[0].name]


def test_prune_apply_recovers_stranded_quarantine(tmp_path):
    root = tmp_path / "candidates"
    quarantine = root / (".prune-" + "a" * 32)
    quarantine.mkdir(parents=True)
    (quarantine / "partial").write_text("x", encoding="utf-8")
    assert store.prune(apply=True, root=root) == []
    assert not quarantine.exists()


def _hold_lease(path: str, root: str, ready: multiprocessing.Event, release: multiprocessing.Event) -> None:
    with store.candidate_lease(Path(path), root=Path(root)):
        ready.set()
        release.wait(5)


def test_prune_skips_live_candidate(tmp_path):
    root = tmp_path / "candidates"
    oldest = _candidate(root, 0)
    for index in range(1, 5):
        _candidate(root, index)
    ready, release = multiprocessing.Event(), multiprocessing.Event()
    child = multiprocessing.Process(target=_hold_lease, args=(str(oldest), str(root), ready, release))
    child.start()
    try:
        deadline = time.monotonic() + 10
        while not ready.is_set() and time.monotonic() < deadline:
            time.sleep(0.02)
        assert ready.is_set(), "lease holder did not become ready"
        assert oldest.name not in store.prune(apply=False, root=root)
    finally:
        release.set()
        child.join(5)
        if child.is_alive():
            child.terminate()
            child.join(5)
    assert not child.is_alive()
    assert child.exitcode == 0


def test_live_newest_candidate_does_not_consume_retention_slot(tmp_path):
    root = tmp_path / "candidates"
    candidates = [_candidate(root, index) for index in range(5)]
    newest = candidates[-1]
    ready, release = multiprocessing.Event(), multiprocessing.Event()
    child = multiprocessing.Process(
        target=_hold_lease, args=(str(newest), str(root), ready, release),
    )
    child.start()
    try:
        assert ready.wait(5), "lease holder did not become ready"
        assert store.prune(apply=False, root=root) == [candidates[0].name]
    finally:
        release.set()
        child.join(5)
        if child.is_alive():
            child.terminate()
            child.join(5)
    assert child.exitcode == 0


def test_mode_sources_are_narrow_and_deterministic():
    source = cli.FIXTURE.read_text(encoding="utf-8")
    assert cli.source_for_mode("v0.1.0", source) == source
    assert "table_widths: false" in cli.source_for_mode("current-legacy", source)
    assert "Venue: 12em" in cli.source_for_mode("current-explicit", source)


def _stub_artifact_boundaries(monkeypatch, *, raster: str = "valid"):
    monkeypatch.setattr(artifacts, "html_evidence", lambda path: {"html": "ok"})
    monkeypatch.setattr(artifacts, "pdf_evidence", lambda path, **kwargs: {"pages": 1, "pdf": "ok"})

    def run(command, **kwargs):
        if "--html" in command:
            Path(command[-2]).write_text("<p>ok</p>", encoding="utf-8")
        elif command[0] == "pdftoppm":
            page = Path(command[-1]).with_name(Path(command[-1]).name + "-1.png")
            if raster == "valid":
                Image.new("RGB", (10, 10), "white").save(page)
            elif raster == "corrupt":
                page.write_bytes(b"not a png")
        else:
            Path(command[-1]).write_bytes(b"pdf")
        return "", ""

    monkeypatch.setattr(artifacts, "run_bounded", run)


def test_artifact_render_is_hermetic_and_rejects_bad_page_sets(tmp_path, monkeypatch):
    source = tmp_path / "source.md"
    source.write_text("fixture", encoding="utf-8")
    _stub_artifact_boundaries(monkeypatch)
    target = tmp_path / "candidate" / "artifacts" / "current-auto"
    target.parent.mkdir(parents=True)
    result = artifacts.render("current-auto", source, target, tmp_path, tmp_path)
    page = target / "page-1.png"
    assert result == {
        "id": "current-auto",
        "html": {"html": "ok"},
        "pdf": {"pages": 1, "pdf": "ok"},
        "rasters": [{"path": "artifacts/current-auto/page-1.png", "width": 10,
                     "height": 10, "sha256": model.sha256_file(page)}],
        "decoded_pixels": 100,
    }

    _stub_artifact_boundaries(monkeypatch, raster="missing")
    with pytest.raises(model.CompatibilityError, match="incomplete"):
        artifacts.render("current-auto", source, tmp_path / "missing", tmp_path, tmp_path)

    _stub_artifact_boundaries(monkeypatch, raster="corrupt")
    with pytest.raises(model.CompatibilityError, match="invalid"):
        artifacts.render("current-auto", source, tmp_path / "corrupt", tmp_path, tmp_path)


def test_artifact_render_rejects_decoded_pixel_limit(tmp_path, monkeypatch):
    source = tmp_path / "source.md"
    source.write_text("fixture", encoding="utf-8")
    _stub_artifact_boundaries(monkeypatch)
    monkeypatch.setattr(model, "MAX_TOTAL_PIXELS", 99)
    with pytest.raises(model.CompatibilityError, match="pixel limit"):
        artifacts.render("current-auto", source, tmp_path / "pixels", tmp_path, tmp_path)


def test_contact_sheet_success_no_pages_and_size_limit(tmp_path, monkeypatch):
    candidate = tmp_path / "candidate"
    page = candidate / "artifacts" / "current-auto" / "page-1.png"
    page.parent.mkdir(parents=True)
    Image.new("RGB", (10, 10), "white").save(page)
    cases = [{"id": "current-auto", "decoded_pixels": 100}]
    result = artifacts.contact_sheet(candidate, cases)
    sheet_path = candidate / result["path"]
    with Image.open(sheet_path) as sheet:
        assert (result["width"], result["height"]) == sheet.size
    assert result["sha256"] == model.sha256_file(sheet_path)

    with pytest.raises(model.CompatibilityError, match="no raster"):
        artifacts.contact_sheet(tmp_path / "empty", [])
    monkeypatch.setattr(artifacts, "MAX_IMAGE_BYTES", 1)
    with pytest.raises(model.CompatibilityError, match="safe size"):
        artifacts.contact_sheet(candidate, cases)


def _html(tmp_path: Path, name: str, schedule_cols: str) -> dict:
    value = f"""<table id='ladder-primary'><caption>Primary ladder</caption><tr><th id='h' scope='col'>Team</th></tr><tr><td headers='h'>North</td></tr></table>
<table>{schedule_cols}<tr><th>Date</th><th>Time</th><th>Venue</th></tr><tr><td>2026-08-08</td><td>09:00</td><td>Court</td></tr></table>
<table><colgroup><col style='width:25.0%'><col style='width:50.0%'><col style='width:25.0%'></colgroup><tr><th>Division</th><th>Club</th><th>Points</th></tr><tr><td>A</td><td>North</td><td>1</td></tr></table>
<table id='author-layout'><colgroup><col style='width:30%'><col style='width:70%'></colgroup><tr><th>Key</th><th>Explanation</th></tr><tr><td>A</td><td>B</td></tr></table>"""
    path = tmp_path / f"{name}.html"
    path.write_text(value, encoding="utf-8")
    return structure.html_evidence(path)


def _classification_cases(tmp_path: Path) -> dict:
    auto_cols = "<colgroup><col><col><col style='width:7em'></colgroup>"
    explicit_cols = "<colgroup><col><col><col style='width:12em'></colgroup>"
    result = {}
    for mode, cols in (("v0.1.0", ""), ("current-auto", auto_cols),
                       ("current-legacy", ""), ("current-precedence", auto_cols),
                       ("current-explicit", explicit_cols)):
        result[mode] = {"html": _html(tmp_path, mode, cols),
                        "pdf": {"pages": 1, "page_boxes": [[1, 1]],
                                "lang": "en" if mode == "v0.1.0" else "en-AU",
                                "marked": mode != "v0.1.0"}}
    return result


def test_classification_has_independent_positive_witnesses(tmp_path):
    checks = structure.classify(_classification_cases(tmp_path))
    assert [item["id"] for item in checks] == list(model.CHECK_IDS)
    assert all(item["status"] == "pass" for item in checks)


def test_classification_missing_witness_is_categorical(tmp_path):
    cases = _classification_cases(tmp_path)
    cases["current-auto"]["html"]["tables"] = []
    with pytest.raises(model.CompatibilityError, match="schedule") as caught:
        structure.classify(cases)
    assert (caught.value.category, caught.value.phase, caught.value.case) == (
        "verify", "classify", "current-auto",
    )


@pytest.mark.parametrize("mutation,failed", [
    ("content", "content-preserved"),
    ("semantics", "semantics-preserved"),
    ("automatic", "automatic-widths-intentional"),
    ("legacy", "legacy-opt-out"),
    ("declared", "declared-layout-precedence"),
    ("author", "author-colgroup-precedence"),
    ("explicit", "explicit-venue-width"),
    ("accessibility", "accessibility-rollback-warning"),
    ("pages", "page-bounds"),
])
def test_classification_negative_witness_names_failed_invariant(tmp_path, mutation, failed):
    cases = _classification_cases(tmp_path)
    if mutation == "content":
        cases["current-auto"]["html"]["content_sha256"] = "changed"
    elif mutation == "semantics":
        cases["current-auto"]["html"]["semantic_sha256"] = "changed"
    elif mutation == "automatic":
        cases["v0.1.0"]["html"] = cases["current-auto"]["html"]
    elif mutation == "legacy":
        cases["current-legacy"]["html"] = cases["current-auto"]["html"]
    elif mutation == "declared":
        cases["current-precedence"]["html"]["tables"][2]["columns"][0]["width"] = "26%"
    elif mutation == "author":
        cases["current-precedence"]["html"]["tables"][3]["columns"][0]["width"] = "31%"
    elif mutation == "explicit":
        cases["current-explicit"]["html"] = cases["current-auto"]["html"]
    elif mutation == "accessibility":
        cases["v0.1.0"]["pdf"]["lang"] = "en-AU"
        cases["v0.1.0"]["pdf"]["marked"] = True
    else:
        cases["current-auto"]["pdf"]["pages"] = 25
    failures = {item["id"] for item in structure.classify(cases) if item["status"] == "fail"}
    assert failures == {failed}


def test_failure_cleanup_removes_partial_artifacts(tmp_path):
    candidate = tmp_path / "candidate"
    (candidate / "artifacts" / "mode").mkdir(parents=True)
    (candidate / "artifacts" / "mode" / "partial.pdf").write_bytes(b"partial")
    (candidate / ".lease").touch()
    assert cli._cleanup_failure(candidate) == []
    assert sorted(path.name for path in candidate.iterdir()) == [".lease"]


@pytest.mark.parametrize("ancestor", ["output", "pdf", "compatibility-v0.1"])
def test_default_candidate_root_rejects_symlinked_ancestors(tmp_path, monkeypatch, ancestor):
    repo = tmp_path / "repo"
    external = tmp_path / "external"
    repo.mkdir()
    external.mkdir()
    parts = ["output", "pdf", "compatibility-v0.1"]
    current = repo
    for part in parts:
        target = current / part
        if part == ancestor:
            target.symlink_to(external, target_is_directory=True)
            break
        target.mkdir()
        current = target
    candidate_root = repo / "output" / "pdf" / "compatibility-v0.1" / "candidates"
    monkeypatch.setattr(store, "ROOT", repo)
    monkeypatch.setattr(store, "CANDIDATE_ROOT", candidate_root)
    with pytest.raises(model.CompatibilityError, match="ancestor"):
        store._ensure_root(candidate_root)
    assert list(external.iterdir()) == []


def test_active_visual_digest_rejects_malformed_and_symlinked_evidence(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    visual = repo / "docs" / "visual-acceptance"
    approved = visual / "approved"
    approved.mkdir(parents=True)
    active = visual / "active.json"
    monkeypatch.setattr(provenance, "ROOT", repo)
    monkeypatch.setattr(provenance, "ACTIVE_VISUAL", active)
    active.write_text('{"digest":"../not-a-digest"}', encoding="utf-8")
    with pytest.raises(model.CompatibilityError, match="pointer"):
        provenance.active_visual_digest()
    digest = "a" * 64
    active.write_text(json.dumps({"digest": digest}), encoding="utf-8")
    digest_dir = approved / digest
    digest_dir.mkdir()
    (digest_dir / "manifest.json").write_text(json.dumps({"source": []}), encoding="utf-8")
    with pytest.raises(model.CompatibilityError, match="does not attest"):
        provenance.active_visual_digest()
    (digest_dir / "manifest.json").unlink()
    outside = tmp_path / "outside.json"
    outside.write_text(json.dumps({"source": {"digest": digest}}), encoding="utf-8")
    (digest_dir / "manifest.json").symlink_to(outside)
    with pytest.raises(model.CompatibilityError, match="unsafe"):
        provenance.active_visual_digest()


def _visual_evidence_tree(tmp_path: Path, monkeypatch) -> tuple[Path, Path, str]:
    repo = tmp_path / "repo"
    visual = repo / "docs" / "visual-acceptance"
    digest = "a" * 64
    approved = visual / "approved" / digest
    approved.mkdir(parents=True)
    active = visual / "active.json"
    manifest = approved / "manifest.json"
    monkeypatch.setattr(provenance, "ROOT", repo)
    monkeypatch.setattr(provenance, "ACTIVE_VISUAL", active)
    monkeypatch.setattr(provenance, "MAX_ACTIVE_JSON_BYTES", 96)
    monkeypatch.setattr(provenance, "MAX_APPROVED_MANIFEST_BYTES", 128)
    active.write_text(json.dumps({"digest": digest}), encoding="utf-8")
    manifest.write_text(json.dumps({"source": {"digest": digest}}), encoding="utf-8")
    return active, manifest, digest


@pytest.mark.parametrize("target", ["active", "approved"])
@pytest.mark.parametrize("payload", [b"\xff", b"{"])
def test_active_visual_digest_rejects_malformed_bytes(
    tmp_path, monkeypatch, target, payload,
):
    active, manifest, _ = _visual_evidence_tree(tmp_path, monkeypatch)
    (active if target == "active" else manifest).write_bytes(payload)
    with pytest.raises(model.CompatibilityError):
        provenance.active_visual_digest()


@pytest.mark.parametrize("target", ["active", "approved"])
def test_active_visual_digest_enforces_byte_limits(tmp_path, monkeypatch, target):
    active, manifest, digest = _visual_evidence_tree(tmp_path, monkeypatch)
    path = active if target == "active" else manifest
    limit = (provenance.MAX_ACTIVE_JSON_BYTES if target == "active"
             else provenance.MAX_APPROVED_MANIFEST_BYTES)
    value = ({"digest": digest} if target == "active"
             else {"source": {"digest": digest}})
    encoded = json.dumps(value).encode()
    path.write_bytes(encoded + b" " * (limit - len(encoded)))
    assert provenance.active_visual_digest() == digest
    path.write_bytes(encoded + b" " * (limit + 1 - len(encoded)))
    with pytest.raises(model.CompatibilityError, match="large|unsafe"):
        provenance.active_visual_digest()


@pytest.mark.parametrize("error_type", [RecursionError, ValueError])
def test_active_visual_digest_categorizes_parser_failures(
    tmp_path, monkeypatch, error_type,
):
    _visual_evidence_tree(tmp_path, monkeypatch)
    monkeypatch.setattr(
        provenance.json, "loads",
        lambda value: (_ for _ in ()).throw(error_type("invalid")),
    )
    with pytest.raises(model.CompatibilityError, match="malformed") as caught:
        provenance.active_visual_digest()
    assert (caught.value.category, caught.value.phase) == ("verify", "provenance")


def test_current_renderer_snapshot_is_immutable(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    fixture = repo / "tests" / "compatibility" / "v0.1.0.md"
    renderer = repo / "pdf" / "render.py"
    fixture.parent.mkdir(parents=True)
    renderer.parent.mkdir(parents=True)
    fixture.write_text("fixture", encoding="utf-8")
    renderer.write_text("renderer", encoding="utf-8")
    monkeypatch.setattr(provenance, "ROOT", repo)
    monkeypatch.setattr(provenance, "FIXTURE", fixture)
    before = provenance.source_hashes()
    parent, snapshot_fixture = provenance.snapshot_current_renderer(tmp_path / "private", before)
    fixture.write_text("changed", encoding="utf-8")
    renderer.write_text("changed", encoding="utf-8")
    assert snapshot_fixture.read_text(encoding="utf-8") == "fixture"
    assert (parent / "pdf" / "render.py").read_text(encoding="utf-8") == "renderer"


def test_generation_provenance_records_immutable_publication_basis(monkeypatch):
    fixture_name = str(provenance.FIXTURE.relative_to(provenance.ROOT))
    hashes = {fixture_name: "a" * 64}
    monkeypatch.setattr(
        provenance, "_generation_state",
        lambda: ("head-1", dict(hashes), "b" * 64),
    )
    monkeypatch.setattr(provenance, "environment", lambda: {"python": "test"})
    provenance_value = provenance.capture_generation_provenance(model.TAG_COMMIT)
    manifest = cli._build_manifest(
        provenance=provenance_value, cases=_manifest()["cases"],
        checks=_manifest()["checks"], contact=_manifest()["contact_sheet"],
    )
    assert manifest["provenance"] == provenance_value
    assert provenance_value["publication_basis"] == provenance.PUBLICATION_BASIS


def test_generation_provenance_missing_fixture_is_categorical(monkeypatch):
    monkeypatch.setattr(
        provenance, "_generation_state", lambda: ("head", {}, "a" * 64),
    )
    with pytest.raises(model.CompatibilityError, match="fixture is missing") as caught:
        provenance.capture_generation_provenance(model.TAG_COMMIT)
    assert (caught.value.category, caught.value.phase) == (
        "verify", "source-attestation",
    )


def test_generation_provenance_rejects_unstable_double_read(monkeypatch):
    fixture_name = str(provenance.FIXTURE.relative_to(provenance.ROOT))
    stable = ("head", {fixture_name: "a" * 64}, "b" * 64)
    changed = ("other-head", {fixture_name: "c" * 64}, "d" * 64)
    states = iter([stable, changed])
    monkeypatch.setattr(provenance, "_generation_state", lambda: next(states))
    with pytest.raises(model.CompatibilityError, match="changed while attesting") as caught:
        provenance.capture_generation_provenance(model.TAG_COMMIT)
    assert caught.value.phase == "source-attestation"


def test_generation_publishes_immutable_snapshot_as_terminal_operation(
    tmp_path, monkeypatch,
):
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    snapshot = tmp_path / "snapshot.md"
    snapshot.write_text("---\ntitle: fixture\n---\nbody", encoding="utf-8")
    template = _manifest()
    events = []

    monkeypatch.setattr(cli, "resolve_tag", lambda root: model.TAG_COMMIT)
    monkeypatch.setattr(
        cli, "capture_generation_provenance",
        lambda tag: copy.deepcopy(template["provenance"]),
    )
    monkeypatch.setattr(
        cli, "snapshot_current_renderer", lambda *args: (tmp_path, snapshot),
    )
    monkeypatch.setattr(cli, "export_tag", lambda *args: tmp_path)
    cases = iter(copy.deepcopy(template["cases"]))
    monkeypatch.setattr(cli, "_render", lambda *args: next(cases))
    monkeypatch.setattr(cli, "classify", lambda value: copy.deepcopy(template["checks"]))
    monkeypatch.setattr(cli, "_contact_sheet", lambda *args: copy.deepcopy(template["contact_sheet"]))
    monkeypatch.setattr(cli, "remove_private_export", lambda path: None)
    monkeypatch.setattr(cli, "tree_stats", lambda path: (0, 0))
    published = {}

    def publish(path, value):
        events.append(path.name)
        published[path.name] = copy.deepcopy(value)

    monkeypatch.setattr(cli, "atomic_json", publish)
    monkeypatch.setattr(cli, "_commit_success", lambda path: events.append("success.json"))

    cli._generate_candidate(candidate, time.monotonic())
    assert events == [
        "decision.json", "manifest.json", "pending.json", "success.json",
    ]
    assert published["pending.json"] == {
        "decision_digest": published["manifest.json"]["decision_digest"],
    }


@pytest.mark.parametrize("abort", ["timeout", "blocker"])
def test_generation_abort_guards_publish_no_success(tmp_path, monkeypatch, abort):
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    snapshot = tmp_path / "snapshot.md"
    snapshot.write_text("---\ntitle: fixture\n---\nbody", encoding="utf-8")
    template = _manifest()
    monkeypatch.setattr(cli, "resolve_tag", lambda root: model.TAG_COMMIT)
    monkeypatch.setattr(
        cli, "capture_generation_provenance",
        lambda tag: copy.deepcopy(template["provenance"]),
    )
    monkeypatch.setattr(
        cli, "snapshot_current_renderer", lambda *args: (tmp_path, snapshot),
    )
    monkeypatch.setattr(cli, "export_tag", lambda *args: tmp_path)
    monkeypatch.setattr(
        cli, "atomic_json",
        lambda *args: pytest.fail("abort path published terminal evidence"),
    )
    if abort == "timeout":
        started = time.monotonic() - cli.MATRIX_TIMEOUT - 1
        expected = "matrix timed out"
    else:
        cases = iter(copy.deepcopy(template["cases"]))
        monkeypatch.setattr(cli, "_render", lambda *args: next(cases))
        checks = copy.deepcopy(template["checks"])
        checks[0]["status"] = "fail"
        monkeypatch.setattr(cli, "classify", lambda value: checks)
        started = time.monotonic()
        expected = "compatibility blockers"
    with pytest.raises(model.CompatibilityError, match=expected):
        cli._generate_candidate(candidate, started)
    assert not (candidate / "success.json").exists()


def test_missing_dependency_metadata_is_prerequisite_failure(monkeypatch):
    def missing(name):
        raise provenance.importlib.metadata.PackageNotFoundError(name)

    monkeypatch.setattr(provenance.importlib.metadata, "version", missing)
    with pytest.raises(model.CompatibilityError, match="metadata") as caught:
        provenance.environment()
    assert (caught.value.category, caught.value.phase) == ("prerequisite", "probe")


def test_failure_diagnostic_hides_internal_paths_and_controls():
    raw = RuntimeError(f"{cli.ROOT}/secret\x1b[31m\nsecond")
    diagnostic = cli._sanitize_diagnostic(raw)
    assert str(cli.ROOT) not in diagnostic
    assert "\x1b" not in diagnostic and "\n" not in diagnostic
    assert diagnostic == "<repo>/secret second"


def test_atomic_json_removes_temporary_file_on_replace_failure(tmp_path, monkeypatch):
    target = tmp_path / "manifest.json"
    monkeypatch.setattr(store.os, "replace", lambda *args, **kwargs: (_ for _ in ()).throw(OSError("full")))
    with pytest.raises(OSError, match="full"):
        store.atomic_json(target, {"ok": True})
    assert list(tmp_path.iterdir()) == []


def _publish_fake_candidate(candidate: Path, source_hashes: dict[str, str], visual_digest: str) -> dict:
    value = _manifest()
    value["provenance"]["source_hashes"] = source_hashes
    value["provenance"]["fixture_sha256"] = model.sha256_file(cli.FIXTURE)
    value["provenance"]["active_visual_acceptance_digest"] = visual_digest
    for case in value["cases"]:
        mode = candidate / "artifacts" / case["id"]
        mode.mkdir(parents=True)
        html = mode / "document.html"
        pdf = mode / "document.pdf"
        raster = mode / "page-1.png"
        html.write_bytes(f"html-{case['id']}".encode())
        pdf.write_bytes(f"pdf-{case['id']}".encode())
        Image.new("RGB", (1, 1), "white").save(raster)
        case["html"]["sha256"] = model.sha256_file(html)
        case["pdf"]["sha256"] = model.sha256_file(pdf)
        case["rasters"] = [{
            "path": f"artifacts/{case['id']}/page-1.png",
            "width": 1, "height": 1, "sha256": model.sha256_file(raster),
        }]
    contact = candidate / "contact-sheet.png"
    Image.new("RGB", (1, 1), "white").save(contact)
    value["contact_sheet"] = {
        "path": contact.name, "width": 1, "height": 1,
        "sha256": model.sha256_file(contact),
    }
    value = model.signed_manifest(value)
    store.atomic_json(candidate / "decision.json", value)
    store.atomic_json(candidate / "manifest.json", value)
    store.atomic_json(
        candidate / "success.json", {"decision_digest": value["decision_digest"]},
    )
    return value


def _republish_fake_manifest(candidate: Path, value: dict) -> dict:
    value = model.signed_manifest(value)
    store.atomic_json(candidate / "decision.json", value)
    store.atomic_json(candidate / "manifest.json", value)
    store.atomic_json(
        candidate / "success.json", {"decision_digest": value["decision_digest"]},
    )
    return value


def test_controlled_generation_and_candidate_verification(tmp_path, monkeypatch):
    root = tmp_path / "candidates"
    source_hashes = {"fixture": "b" * 64}
    visual_digest = "c" * 64

    def generate_fake(candidate, started):
        _publish_fake_candidate(candidate, source_hashes, visual_digest)
        (candidate / store.PENDING_MARKER).unlink()

    monkeypatch.setattr(cli, "_generate_candidate", generate_fake)
    monkeypatch.setattr(verification, "source_hashes", lambda: source_hashes)
    monkeypatch.setattr(verification, "active_visual_digest", lambda: visual_digest)
    candidate = cli.generate(candidate_root=root)
    assert cli.verify(candidate, candidate_root=root, attest_tag=False) == candidate / "manifest.json"
    first = candidate / "artifacts" / model.MODE_IDS[0]
    first.joinpath("document.html").write_bytes(b"corrupt-html")
    with pytest.raises(model.CompatibilityError, match="HTML artifact"):
        cli.verify(candidate, candidate_root=root, attest_tag=False)
    first.joinpath("document.html").write_bytes(f"html-{model.MODE_IDS[0]}".encode())
    first.joinpath("document.pdf").write_bytes(b"corrupt-pdf")
    with pytest.raises(model.CompatibilityError, match="PDF artifact"):
        cli.verify(candidate, candidate_root=root, attest_tag=False)
    first.joinpath("document.pdf").write_bytes(f"pdf-{model.MODE_IDS[0]}".encode())
    raster = first / "page-1.png"
    raster_bytes = raster.read_bytes()
    raster.unlink()
    with pytest.raises(model.CompatibilityError, match="raster artifact"):
        cli.verify(candidate, candidate_root=root, attest_tag=False)
    raster.write_bytes(raster_bytes)
    contact = candidate / "contact-sheet.png"
    contact.write_bytes(b"corrupt-contact")
    with pytest.raises(model.CompatibilityError, match="contact-sheet artifact"):
        cli.verify(candidate, candidate_root=root, attest_tag=False)


def test_candidate_decision_must_match_manifest(tmp_path, monkeypatch):
    root = tmp_path / "candidates"
    source_hashes = {"fixture": "b" * 64}
    visual_digest = "c" * 64
    candidate = store.allocate_candidate(root)
    value = _publish_fake_candidate(candidate, source_hashes, visual_digest)
    changed = model.signed_manifest({**value, "decision": "different"})
    store.atomic_json(candidate / "decision.json", changed)
    monkeypatch.setattr(verification, "source_hashes", lambda: source_hashes)
    monkeypatch.setattr(verification, "active_visual_digest", lambda: visual_digest)
    with pytest.raises(model.CompatibilityError, match="decision and manifest"):
        cli.verify(candidate, candidate_root=root, attest_tag=False)


def test_failure_marker_overrides_complete_success_candidate(tmp_path, monkeypatch):
    root = tmp_path / "candidates"
    sources = {"fixture": "b" * 64}
    visual_digest = "c" * 64
    candidate = store.allocate_candidate(root)
    _publish_fake_candidate(candidate, sources, visual_digest)
    store.atomic_json(candidate / "failure.json", {
        "schema_version": 1, "kind": "md2pdf-v0.1-compatibility-failure",
        "category": "verify", "phase": "source-attestation", "case": None,
        "diagnostic": "changed", "cleanup_notes": ["manifest remained"],
    })
    store.atomic_json(candidate / store.PENDING_MARKER, {"state": "generating"})
    monkeypatch.setattr(verification, "source_hashes", lambda: sources)
    monkeypatch.setattr(verification, "active_visual_digest", lambda: visual_digest)
    assert store._candidate_kind(candidate) == "failed"
    with store.candidate_lease(candidate, root=root, yield_fd=True) as (_, candidate_fd):
        assert store._candidate_kind_fd(candidate_fd) == "failed"
    with pytest.raises(model.CompatibilityError, match="failure marker"):
        cli.verify(candidate, candidate_root=root, attest_tag=False)


def test_failure_marker_precedes_malformed_manifest(tmp_path):
    root = tmp_path / "candidates"
    candidate = store.allocate_candidate(root)
    (candidate / "manifest.json").write_text("{", encoding="utf-8")
    (candidate / "failure.json").write_text("{}", encoding="utf-8")
    with pytest.raises(model.CompatibilityError, match="failure marker"):
        cli.verify(candidate, candidate_root=root, attest_tag=False)


@pytest.mark.parametrize(
    "mutation", ["missing", "invalid-utf8", "invalid-json", "oversized", "wrong-digest"],
)
def test_candidate_rejects_invalid_success_markers(tmp_path, monkeypatch, mutation):
    root = tmp_path / "candidates"
    sources = {"fixture": "b" * 64}
    visual_digest = "c" * 64
    candidate = store.allocate_candidate(root)
    _publish_fake_candidate(candidate, sources, visual_digest)
    marker = candidate / "success.json"
    if mutation == "missing":
        marker.unlink()
    elif mutation == "invalid-utf8":
        marker.write_bytes(b"\xff")
    elif mutation == "invalid-json":
        marker.write_text("{", encoding="utf-8")
    elif mutation == "oversized":
        marker.write_bytes(b" " * 1025)
    else:
        store.atomic_json(marker, {"decision_digest": "0" * 64})
    monkeypatch.setattr(verification, "source_hashes", lambda: sources)
    monkeypatch.setattr(verification, "active_visual_digest", lambda: visual_digest)
    with pytest.raises(model.CompatibilityError, match="success marker"):
        cli.verify(candidate, candidate_root=root, attest_tag=False)


def test_failure_marker_is_published_before_cleanup(tmp_path, monkeypatch):
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    observed = []

    def cleanup(path):
        observed.append((path / "failure.json").is_file())
        return ["manifest remained"]

    monkeypatch.setattr(cli, "_cleanup_failure", cleanup)
    path = cli._record_generation_failure(
        candidate,
        model.CompatibilityError(
            "changed", category="verify", phase="source-attestation",
        ),
    )
    assert observed == [True]
    assert json.loads(path.read_text())["cleanup_notes"] == ["manifest remained"]


def test_failure_publication_retry_always_invalidates_success(tmp_path, monkeypatch):
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    (candidate / "manifest.json").write_text("{}", encoding="utf-8")
    (candidate / "success.json").write_text("{}", encoding="utf-8")
    original_atomic = cli.atomic_json
    attempts = 0

    def fail_once(path, value):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise OSError("quota exhausted")
        original_atomic(path, value)

    monkeypatch.setattr(cli, "atomic_json", fail_once)
    failure = cli._record_generation_failure(
        candidate,
        model.CompatibilityError(
            "changed", category="verify", phase="source-attestation",
        ),
    )
    assert attempts == 2 and failure.is_file()
    assert not (candidate / "success.json").exists()
    assert not (candidate / "manifest.json").exists()


def test_persistent_failure_publication_remains_fail_closed(tmp_path, monkeypatch):
    root = tmp_path / "candidates"

    def publish_then_fail(candidate, started):
        (candidate / "manifest.json").write_text("{}", encoding="utf-8")
        (candidate / "success.json").write_text("{}", encoding="utf-8")
        raise model.CompatibilityError(
            "original generation failure", category="verify", phase="test",
        )

    original_atomic = cli.atomic_json

    def reject_failure_marker(path, value):
        if path.name == "failure.json":
            raise OSError("quota exhausted")
        original_atomic(path, value)

    monkeypatch.setattr(cli, "_generate_candidate", publish_then_fail)
    monkeypatch.setattr(cli, "atomic_json", reject_failure_marker)
    monkeypatch.setattr(cli, "_cleanup_failure", lambda candidate: ["cleanup blocked"])
    with pytest.raises(model.CompatibilityError, match="original generation failure"):
        cli.generate(candidate_root=root)
    candidate = next(path for path in root.iterdir() if path.is_dir())
    assert (candidate / store.PENDING_MARKER).is_file()
    assert store._candidate_kind(candidate) is None
    with pytest.raises(model.CompatibilityError, match="pending marker"):
        cli.verify(candidate, candidate_root=root, attest_tag=False)


def test_failure_publication_interruption_preserves_generation_error(tmp_path, monkeypatch):
    root = tmp_path / "candidates"

    def fail(candidate, started):
        raise model.CompatibilityError(
            "original generation failure", category="render", phase="test",
        )

    original_atomic = cli.atomic_json

    def interrupt_failure_marker(path, value):
        if path.name == "failure.json":
            raise KeyboardInterrupt
        original_atomic(path, value)

    monkeypatch.setattr(cli, "_generate_candidate", fail)
    monkeypatch.setattr(cli, "atomic_json", interrupt_failure_marker)
    with pytest.raises(model.CompatibilityError, match="original generation failure"):
        cli.generate(candidate_root=root)
    candidate = next(path for path in root.iterdir() if path.is_dir())
    assert (candidate / store.PENDING_MARKER).is_file()
    assert store._candidate_kind(candidate) is None


@pytest.mark.parametrize("target", ["raster", "contact"])
def test_candidate_rejects_noncanonical_evidence_paths(tmp_path, monkeypatch, target):
    root = tmp_path / "candidates"
    sources = {"fixture": "b" * 64}
    visual_digest = "c" * 64
    candidate = store.allocate_candidate(root)
    value = _publish_fake_candidate(candidate, sources, visual_digest)
    if target == "raster":
        value["cases"][0]["rasters"][0]["path"] = "../outside.png"
    else:
        value["contact_sheet"]["path"] = "../outside.png"
    _republish_fake_manifest(candidate, value)
    monkeypatch.setattr(verification, "source_hashes", lambda: sources)
    monkeypatch.setattr(verification, "active_visual_digest", lambda: visual_digest)
    with pytest.raises(model.CompatibilityError, match=f"{target}.*path mismatch"):
        cli.verify(candidate, candidate_root=root, attest_tag=False)


def test_candidate_path_must_be_direct_child_of_root(tmp_path):
    root = tmp_path / "candidates"
    outside = tmp_path / "outside" / ("20260101T000000Z-" + "a" * 32)
    outside.mkdir(parents=True)
    with pytest.raises(model.CompatibilityError, match="escapes its root"):
        cli.verify(outside, candidate_root=root, attest_tag=False)


def test_candidate_directory_symlink_is_rejected(tmp_path):
    root = tmp_path / "candidates"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    candidate = root / ("20260101T000000Z-" + "a" * 32)
    candidate.symlink_to(outside, target_is_directory=True)
    with pytest.raises(model.CompatibilityError, match="missing or unsafe"):
        cli.verify(candidate, candidate_root=root, attest_tag=False)


@pytest.mark.parametrize("entry_type", ["symlink", "fifo"])
def test_candidate_rejects_unsafe_canonical_artifact_entries(
    tmp_path, monkeypatch, entry_type,
):
    root = tmp_path / "candidates"
    candidate = store.allocate_candidate(root)
    sources = {"fixture": "b" * 64}
    visual_digest = "c" * 64
    value = _publish_fake_candidate(candidate, sources, visual_digest)
    artifact = candidate / "artifacts" / value["cases"][0]["id"] / "document.html"
    artifact.unlink()
    if entry_type == "symlink":
        outside = tmp_path / "outside.html"
        outside.write_text("external", encoding="utf-8")
        artifact.symlink_to(outside)
    else:
        os.mkfifo(artifact)
    with pytest.raises(model.CompatibilityError, match="unsafe entry"):
        cli.verify(candidate, candidate_root=root, attest_tag=False)


@pytest.mark.parametrize("target", ["pdf", "raster", "contact"])
def test_candidate_rejects_oversized_evidence(tmp_path, monkeypatch, target):
    root = tmp_path / "candidates"
    sources = {"fixture": "b" * 64}
    visual_digest = "c" * 64
    candidate = store.allocate_candidate(root)
    value = _publish_fake_candidate(candidate, sources, visual_digest)
    case = value["cases"][0]
    if target == "pdf":
        path = candidate / "artifacts" / case["id"] / "document.pdf"
        limit_name, evidence = "MAX_PDF_BYTES", case["pdf"]
    elif target == "raster":
        evidence = case["rasters"][0]
        path = candidate / evidence["path"]
        limit_name = "MAX_IMAGE_BYTES"
    else:
        evidence = value["contact_sheet"]
        path = candidate / evidence["path"]
        limit_name = "MAX_IMAGE_BYTES"
    path.write_bytes(path.read_bytes() + b"oversized-evidence")
    evidence["sha256"] = model.sha256_file(path)
    _republish_fake_manifest(candidate, value)
    monkeypatch.setattr(verification, "source_hashes", lambda: sources)
    monkeypatch.setattr(verification, "active_visual_digest", lambda: visual_digest)
    monkeypatch.setattr(verification, limit_name, path.stat().st_size - 1)
    label = {"pdf": "PDF", "raster": "raster", "contact": "contact-sheet"}[target]
    with pytest.raises(model.CompatibilityError, match=f"{label}.*missing or unsafe"):
        cli.verify(candidate, candidate_root=root, attest_tag=False)


@pytest.mark.parametrize("mismatch", ["sources", "fixture", "visual"])
def test_live_provenance_mismatches_are_rejected(monkeypatch, mismatch):
    value = _manifest()
    provenance_value = value["provenance"]
    sources = provenance_value["source_hashes"]
    fixture_hash = provenance_value["fixture_sha256"]
    visual_digest = provenance_value["active_visual_acceptance_digest"]
    monkeypatch.setattr(
        verification, "source_hashes",
        lambda: {"other": "b" * 64} if mismatch == "sources" else sources,
    )
    monkeypatch.setattr(
        verification, "sha256_file",
        lambda path: "b" * 64 if mismatch == "fixture" else fixture_hash,
    )
    monkeypatch.setattr(
        verification, "active_visual_digest",
        lambda: "b" * 64 if mismatch == "visual" else visual_digest,
    )
    with pytest.raises(model.CompatibilityError) as caught:
        verification.verify_live_provenance(value, attest_tag=False)
    expected_phase = "provenance" if mismatch == "visual" else "source-attestation"
    assert caught.value.phase == expected_phase


def test_candidate_verification_attests_tag_by_default(tmp_path, monkeypatch):
    root = tmp_path / "candidates"
    sources = {"fixture": "b" * 64}
    visual_digest = "c" * 64
    candidate = store.allocate_candidate(root)
    _publish_fake_candidate(candidate, sources, visual_digest)
    monkeypatch.setattr(verification, "source_hashes", lambda: sources)
    monkeypatch.setattr(verification, "active_visual_digest", lambda: visual_digest)
    monkeypatch.setattr(
        verification, "resolve_tag",
        lambda root: (_ for _ in ()).throw(
            model.CompatibilityError("tag changed", category="tag", phase="resolve-tag"),
        ),
    )
    with pytest.raises(model.CompatibilityError, match="tag changed") as caught:
        cli.verify(candidate, candidate_root=root)
    assert (caught.value.category, caught.value.phase) == ("tag", "resolve-tag")


@pytest.mark.parametrize("kind", ["missing", "invalid-utf8", "invalid-json", "oversized"])
def test_manifest_reader_failures_are_categorical(tmp_path, monkeypatch, kind):
    path = tmp_path / "manifest.json"
    if kind == "invalid-utf8":
        path.write_bytes(b"\xff")
    elif kind == "invalid-json":
        path.write_text("{", encoding="utf-8")
    elif kind == "oversized":
        monkeypatch.setattr(verification, "MAX_MANIFEST_BYTES", 4)
        path.write_bytes(b"12345")
    message = "safe size" if kind == "oversized" else "missing or malformed"
    with pytest.raises(model.CompatibilityError, match=message) as caught:
        verification.read_manifest(path)
    assert (caught.value.category, caught.value.phase) == ("verify", "verify")


@pytest.mark.parametrize("error_type", [RecursionError, ValueError])
def test_manifest_reader_categorizes_parser_failures(tmp_path, monkeypatch, error_type):
    path = tmp_path / "manifest.json"
    path.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        verification.json, "loads",
        lambda value: (_ for _ in ()).throw(error_type("invalid")),
    )
    with pytest.raises(model.CompatibilityError, match="missing or malformed") as caught:
        verification.read_manifest(path)
    assert (caught.value.category, caught.value.phase) == ("verify", "verify")


def test_generation_rolls_back_when_lease_setup_fails(tmp_path, monkeypatch):
    root = tmp_path / "candidates"

    @contextlib.contextmanager
    def fail_lease(*args, **kwargs):
        raise model.CompatibilityError("lease setup failed", category="verify", phase="lease")
        yield

    monkeypatch.setattr(cli, "candidate_lease", fail_lease)
    with pytest.raises(model.CompatibilityError, match="lease setup"):
        cli.generate(candidate_root=root)
    assert not [path for path in root.iterdir() if path.is_dir()]


def test_generation_preserves_primary_error_when_rollback_fails(tmp_path, monkeypatch, capsys):
    @contextlib.contextmanager
    def fail_lease(*args, **kwargs):
        raise model.CompatibilityError("primary lease failure", category="verify", phase="lease")
        yield

    monkeypatch.setattr(cli, "candidate_lease", fail_lease)
    monkeypatch.setattr(
        cli, "discard_allocated_candidate",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("private rollback path")),
    )
    with pytest.raises(model.CompatibilityError, match="primary lease") as caught:
        cli.generate(candidate_root=tmp_path / "candidates")
    assert caught.value.phase == "lease"
    assert capsys.readouterr().err == "compatibility allocation rollback failed: OSError\n"


def test_tag_resolution_accepts_exact_and_rejects_mismatch(tmp_path, monkeypatch):
    monkeypatch.setattr(history, "run_bounded", lambda *args, **kwargs: (model.TAG_COMMIT + "\n", ""))
    assert history.resolve_tag(tmp_path) == model.TAG_COMMIT
    monkeypatch.setattr(history, "run_bounded", lambda *args, **kwargs: ("0" * 40 + "\n", ""))
    with pytest.raises(model.CompatibilityError, match="expected") as caught:
        history.resolve_tag(tmp_path)
    assert (caught.value.category, caught.value.phase) == ("tag", "resolve-tag")
    private = tmp_path / "private"
    with pytest.raises(model.CompatibilityError):
        history.export_tag(tmp_path, private)
    assert not private.exists()


def test_cli_dispatch_and_sanitized_failure(monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(cli, "generate", lambda: calls.append(("generate", None)))
    monkeypatch.setattr(cli, "verify", lambda path=None: calls.append(("verify", path)))
    monkeypatch.setattr(
        cli, "prune", lambda *, apply: calls.append(("prune", apply)) or ["old"],
    )
    assert cli.main(["generate"]) == 0
    assert cli.main(["verify", "candidate"]) == 0
    assert cli.main(["verify"]) == 0
    assert cli.main(["prune", "--dry-run"]) == 0
    assert cli.main(["prune", "--apply"]) == 0
    assert calls == [
        ("generate", None), ("verify", Path("candidate")), ("verify", None),
        ("prune", False), ("prune", True),
    ]
    assert capsys.readouterr().out == "old\nold\n"

    def fail():
        raise model.CompatibilityError(
            f"failure at {cli.ROOT}/private", category="verify", phase="cli",
        )

    monkeypatch.setattr(cli, "generate", fail)
    assert cli.main(["generate"]) == 1
    assert capsys.readouterr().err == "compatibility error: failure at <repo>/private\n"


def test_cli_prune_requires_exactly_one_mode():
    with pytest.raises(SystemExit) as neither:
        cli.main(["prune"])
    assert neither.value.code == 2
    with pytest.raises(SystemExit) as both:
        cli.main(["prune", "--dry-run", "--apply"])
    assert both.value.code == 2


@pytest.mark.skipif(os.environ.get("MD2PDF_COMPAT_REAL") != "1",
                    reason="explicit real-render compatibility acceptance")
def test_two_real_generators_publish_complete_distinct_candidates(tmp_path):
    root = tmp_path / "candidates"
    with ThreadPoolExecutor(max_workers=2) as executor:
        candidates = list(executor.map(lambda _: cli.generate(candidate_root=root), range(2)))
    assert candidates[0] != candidates[1]
    manifests = []
    for candidate in candidates:
        assert cli.verify(candidate, candidate_root=root) == candidate / "manifest.json"
        manifest = json.loads((candidate / "manifest.json").read_text(encoding="utf-8"))
        manifests.append(manifest)
        assert all((candidate / "artifacts" / mode / "document.html").is_file()
                   and (candidate / "artifacts" / mode / "document.pdf").is_file()
                   for mode in model.MODE_IDS)
        for case in manifest["cases"]:
            for raster in case["rasters"]:
                path = candidate / raster["path"]
                assert path.is_file() and model.sha256_file(path) == raster["sha256"]
        contact = candidate / manifest["contact_sheet"]["path"]
        assert contact.is_file()
        assert model.sha256_file(contact) == manifest["contact_sheet"]["sha256"]

    deterministic = []
    for manifest in manifests:
        value = {key: copy.deepcopy(manifest[key])
                 for key in ("cases", "checks", "contact_sheet", "decision")}
        for case in value["cases"]:
            case["pdf"].pop("sha256")
            case["pdf"].pop("bytes")
        deterministic.append(value)
    assert deterministic[0] == deterministic[1]


def test_generation_failure_record_is_published_under_continuous_lease(tmp_path, monkeypatch):
    root = tmp_path / "candidates"
    observed_busy = []

    def fail(candidate, started):
        raise model.CompatibilityError("synthetic render failure", category="render", phase="test")

    original_record = cli._record_generation_failure

    def record(candidate, exc):
        with pytest.raises(model.LeaseBusy):
            with store.candidate_lease(candidate, blocking=False, root=root):
                pass
        observed_busy.append(True)
        return original_record(candidate, exc)

    monkeypatch.setattr(cli, "_generate_candidate", fail)
    monkeypatch.setattr(cli, "_record_generation_failure", record)
    with pytest.raises(model.CompatibilityError, match="synthetic"):
        cli.generate(candidate_root=root)
    candidates = [path for path in root.iterdir() if path.is_dir()]
    assert observed_busy == [True]
    assert len(candidates) == 1
    failure = json.loads((candidates[0] / "failure.json").read_text())
    assert model.validate_failure(failure)["category"] == "render"


def test_prune_reclassifies_after_acquiring_lease(tmp_path, monkeypatch):
    root = tmp_path / "candidates"
    candidates = [_candidate(root, index) for index in range(4)]
    oldest = candidates[0]
    original_lease = store.candidate_lease

    @contextlib.contextmanager
    def mutate_before_yield(path, **kwargs):
        with original_lease(path, **kwargs) as leased:
            if path == oldest:
                (path / "manifest.json").unlink()
                (path / "failure.json").write_text("{}\n", encoding="utf-8")
            yield leased

    monkeypatch.setattr(store, "candidate_lease", mutate_before_yield)
    assert oldest.name not in store.prune(apply=True, root=root)
    assert oldest.exists()


def test_manifest_nested_shape_fails_closed():
    value = _manifest()
    del value["cases"][0]["pdf"]
    value = model.signed_manifest(value)
    with pytest.raises(model.CompatibilityError, match="PDF evidence"):
        model.validate_manifest(value)


def test_malformed_pdf_is_categorical(tmp_path):
    path = tmp_path / "bad.pdf"
    path.write_bytes(b"not a pdf")
    with pytest.raises(model.CompatibilityError, match="could not be parsed") as caught:
        structure.pdf_evidence(path, case="current-auto")
    assert (caught.value.category, caught.value.phase, caught.value.case) == (
        "verify", "pdf", "current-auto",
    )


def test_checked_decision_validates_current_sources_and_visual_pointer():
    assert cli.verify() == cli.CHECKED_DECISION
