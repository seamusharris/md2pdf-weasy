"""Contracts for guarded, consumer-owned downstream canary coverage."""

from __future__ import annotations

import contextlib
from concurrent.futures import ThreadPoolExecutor
import copy
from importlib import metadata
import json
import multiprocessing
import os
from pathlib import Path
import subprocess
import sys
import time
import types

import pytest

from tools.distribution_entitlement import PreflightError
from tools.downstream_canary import cli, lifecycle, model, provenance, scenarios


ROOT = Path(__file__).resolve().parents[1]
CANDIDATE = "a" * 40
ROLLBACK = "b" * 40
TREE = "c" * 40
TUPLE = ("private_consumer", "consumer_environment", "consumer_recipient")


def _request(**changes) -> model.RunRequest:
    values = {
        "consumer_id": TUPLE[0],
        "environment_id": TUPLE[1],
        "recipient_id": TUPLE[2],
        "candidate_commit": CANDIDATE,
        "rollback_commit": ROLLBACK,
        "opt_out": model.OPT_OUT,
    }
    values.update(changes)
    return model.RunRequest.create(**values)


def _registry(*, consumers=None) -> dict:
    entries = [] if consumers is None else consumers
    return {
        "schema_version": 1,
        "decision": "authorized_consumers_recorded" if entries else "no_authorized_consumers_recorded",
        "reviewed_on": "2026-08-03",
        "evidence_policy": {
            "storage": "references_only",
            "forbidden_content": [
                "consumer_names",
                "repository_urls",
                "documents",
                "credentials",
                "licenses",
                "attachments",
            ],
        },
        "consumers": entries,
    }


def _consumer_entry() -> dict:
    return {
        "consumer_id": TUPLE[0],
        "environment_id": TUPLE[1],
        "recipient_id": TUPLE[2],
        "entitlement": {
            "operation": "consumer_canary",
            "environment": TUPLE[1],
            "recipient": TUPLE[2],
        },
        "provenance_ref": "PROVENANCE:consumer-install",
        "feature_set": model.FEATURE_SET,
    }


def _snapshot(**changes) -> provenance.SourceSnapshot:
    values = {
        "commit": CANDIDATE,
        "tree": TREE,
        "rollback_commit": ROLLBACK,
        "installed_commit": CANDIDATE,
        "installed_digest": "d" * 64,
        "direct_url_digest": "e" * 64,
        "input_digest": "f" * 64,
        "expected_package_digest": "d" * 64,
        "package_files": ("pdf/__init__.py",),
        "package_root": Path("/synthetic/site/pdf"),
    }
    values.update(changes)
    return provenance.SourceSnapshot(**values)


def _inputs(**changes) -> provenance.CandidateInputs:
    entry = _consumer_entry()
    values = {
        "commit": CANDIDATE,
        "tree": TREE,
        "rollback_commit": ROLLBACK,
        "registry": json.dumps(_registry(consumers=[entry])).encode("utf-8"),
        "fixture": (ROOT / provenance.FIXTURE_PATH).read_bytes(),
        "resource": (ROOT / provenance.RESOURCE_PATH).read_bytes(),
        "input_digest": "f" * 64,
        "package_digest": "d" * 64,
        "package_files": ("pdf/__init__.py",),
    }
    values.update(changes)
    return provenance.CandidateInputs(**values)


class _SyntheticDistribution:
    def __init__(self, root: Path, direct: str | None, files) -> None:
        self.root = root
        self.direct = direct
        self.files = files

    def read_text(self, name: str) -> str | None:
        assert name == "direct_url.json"
        return self.direct

    def locate_file(self, item) -> Path:
        return self.root / str(item)


def _git(root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    )
    return completed.stdout.strip()


def _git_repo(root: Path) -> str:
    (root / "pdf").mkdir()
    (root / "pdf/__init__.py").write_text("VALUE = 'candidate'\n", encoding="utf-8")
    (root / "docs").mkdir()
    (root / "docs/downstream-consumers.json").write_text(
        json.dumps(_registry(consumers=[_consumer_entry()])), encoding="utf-8"
    )
    (root / "tests/canary").mkdir(parents=True)
    (root / "tests/canary/downstream.md").write_text(
        "---\ntitle: Sanitized downstream canary\nlang: en-AU\ntheme: __THEME__\n---\n",
        encoding="utf-8",
    )
    (root / "tests/canary/canary-resource.svg").write_text("<svg/>\n", encoding="utf-8")
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "canary-test@example.invalid")
    _git(root, "config", "user.name", "Canary Test")
    _git(root, "add", ".")
    _git(root, "commit", "-q", "-m", "synthetic canary fixture")
    return _git(root, "rev-parse", "HEAD")


def _hold_lease(path: str, ready: multiprocessing.Event, release: multiprocessing.Event) -> None:
    with lifecycle.Lease(Path(path)):
        ready.set()
        release.wait(5)


def test_checked_registry_is_empty_reference_only():
    raw = (ROOT / provenance.REGISTRY_PATH).read_bytes()
    value = model.parse_json_bytes(raw, "consumer registry")

    assert model.validate_registry(value) == ()
    assert value["decision"] == "no_authorized_consumers_recorded"
    assert value["evidence_policy"]["storage"] == "references_only"


@pytest.mark.parametrize("raw", [b"\xff", b"{", b"[]", b"null", b'{"a":1,"a":2}'])
def test_json_boundary_rejects_encoding_shape_and_duplicate_keys(raw):
    with pytest.raises(model.CanaryError):
        model.parse_json_bytes(raw, "synthetic input")


def test_json_boundary_rejects_size_and_depth():
    with pytest.raises(model.CanaryError, match="size"):
        model.parse_json_bytes(b"x" * (model.MAX_JSON_BYTES + 1), "synthetic input")
    value = b'{"a":{"b":{"c":{"d":{"e":{"f":{"g":{"h":{"i":1}}}}}}}}}'
    with pytest.raises(model.CanaryError, match="nesting"):
        model.parse_json_bytes(value, "synthetic input")


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda value: value.update(extra=True), "fields"),
        (lambda value: value.update(schema_version=2), "schema"),
        (lambda value: value.update(reviewed_on="2999-01-01"), "future"),
        (lambda value: value.update(decision="authorized_consumers_recorded"), "inconsistent"),
        (lambda value: value["evidence_policy"].update(storage="attachments"), "reference-only"),
        (lambda value: value.update(consumers="many"), "bounds"),
    ],
)
def test_registry_top_level_malformed_matrix(mutation, message):
    value = _registry()
    mutation(value)
    with pytest.raises(model.CanaryError, match=message):
        model.validate_registry(value)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda entry: entry.update(extra=True), "fields"),
        (lambda entry: entry.update(consumer_id="-option"), "identifier"),
        (lambda entry: entry.update(provenance_ref="https://private.invalid"), "opaque"),
        (lambda entry: entry.update(feature_set="unknown"), "feature"),
        (lambda entry: entry["entitlement"].update(operation="package_artifact"), "operation"),
        (lambda entry: entry["entitlement"].update(environment="other_environment"), "inconsistent"),
    ],
)
def test_registry_consumer_malformed_matrix(mutation, message):
    entry = _consumer_entry()
    mutation(entry)
    with pytest.raises(model.CanaryError, match=message):
        model.validate_registry(_registry(consumers=[entry]))


def test_registry_rejects_duplicate_consumer_tuple_and_missing_exact_match():
    entry = _consumer_entry()
    with pytest.raises(model.CanaryError, match="duplicate"):
        model.validate_registry(_registry(consumers=[entry, copy.deepcopy(entry)]))
    consumers = model.validate_registry(_registry(consumers=[entry]))
    with pytest.raises(model.CanaryError, match="no exact"):
        model.select_consumer(consumers, _request(recipient_id="different_recipient"))


def test_registry_consumer_count_boundary(monkeypatch):
    monkeypatch.setattr(model, "MAX_CONSUMERS", 1)
    first = _consumer_entry()
    assert len(model.validate_registry(_registry(consumers=[first]))) == 1
    second = copy.deepcopy(first)
    second["consumer_id"] = "second_consumer"
    with pytest.raises(model.CanaryError, match="bounds"):
        model.validate_registry(_registry(consumers=[first, second]))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("consumer_id", "x"),
        ("environment_id", "-option"),
        ("recipient_id", "contains space"),
        ("candidate_commit", "abc123"),
        ("rollback_commit", "-" + "a" * 39),
        ("opt_out", "legacy"),
    ],
)
def test_run_request_requires_bounded_ids_full_commits_and_supported_optout(field, value):
    with pytest.raises(model.CanaryError) as caught:
        _request(**{field: value})
    assert caught.value.category == "invalid request"
    assert caught.value.exit_code == 2


def test_result_is_bounded_and_contains_only_sanitized_fields():
    result = json.loads(model.result_json(_request(), TREE, "f" * 64, model.CHECK_IDS))

    assert set(result) == {
        "schema_version", "status", "consumer_id", "environment_id",
        "candidate_commit", "candidate_tree", "input_digest", "rollback_commit",
        "opt_out", "checks",
    }
    assert "recipient" not in result
    assert "path" not in result
    with pytest.raises(model.CanaryError, match="incomplete"):
        model.result_json(_request(), TREE, "f" * 64, model.CHECK_IDS[:-1])
    with pytest.raises(model.CanaryError, match="input identity"):
        model.result_json(_request(), TREE, "not-a-digest", model.CHECK_IDS)


def _direct_url(**changes) -> bytes:
    value = {
        "url": "ssh://private.invalid/project.git",
        "vcs_info": {"vcs": "git", "commit_id": CANDIDATE, "requested_revision": CANDIDATE},
    }
    value.update(changes)
    return json.dumps(value).encode("utf-8")


def test_pep610_accepts_exact_noneditable_git_commit():
    commit, digest = provenance._validate_direct_url(_direct_url(), CANDIDATE)
    assert commit == CANDIDATE
    assert len(digest) == 64


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        (b"[]", "JSON object"),
        (b'{"url":"x","url":"y"}', "duplicate"),
        (json.dumps({"url": "x", "dir_info": {"editable": True}}).encode(), "direct VCS"),
        (json.dumps({"url": "x", "archive_info": {}}).encode(), "direct VCS"),
        (json.dumps({"url": "x", "vcs_info": {"vcs": "hg", "commit_id": CANDIDATE}}).encode(), "Git commit"),
        (json.dumps({"url": "x", "vcs_info": {"vcs": "git"}}).encode(), "incomplete"),
        (json.dumps({"url": "x", "vcs_info": {"vcs": "git", "commit_id": "abc"}}).encode(), "malformed"),
        (_direct_url(), "does not match"),
    ],
)
def test_pep610_malformed_and_unsupported_matrix(raw, message):
    expected = ROLLBACK if raw == _direct_url() else CANDIDATE
    with pytest.raises(model.CanaryError, match=message):
        provenance._validate_direct_url(raw, expected)


def _install_synthetic_distribution(monkeypatch, root: Path, commit: str):
    direct = _direct_url(vcs_info={
        "vcs": "git", "commit_id": commit, "requested_revision": commit
    }).decode("utf-8")
    distribution = _SyntheticDistribution(
        root,
        direct,
        (metadata.PackagePath("pdf/__init__.py"),),
    )
    monkeypatch.setattr(provenance.metadata, "distribution", lambda _name: distribution)


def test_capture_snapshot_uses_candidate_tree_and_full_installed_provenance(tmp_path, monkeypatch):
    commit = _git_repo(tmp_path)
    tree = _git(tmp_path, "rev-parse", "HEAD^{tree}")
    request = model.RunRequest.create(*TUPLE, commit, commit, model.OPT_OUT)
    _install_synthetic_distribution(monkeypatch, tmp_path, commit)
    inputs = provenance.load_candidate_inputs(tmp_path, request, tree)

    snapshot = provenance.capture_snapshot(tmp_path, request, inputs)
    assert snapshot.commit == commit
    assert snapshot.rollback_commit == commit
    assert snapshot.installed_digest == inputs.package_digest
    assert model.validate_registry(model.parse_json_bytes(inputs.registry, "registry"))

    (tmp_path / "untracked.txt").write_text("mutation", encoding="utf-8")
    with pytest.raises(model.CanaryError, match="not clean"):
        provenance.capture_snapshot(tmp_path, request, inputs)


def test_candidate_inputs_come_from_immutable_tree_not_mutable_paths(tmp_path, monkeypatch):
    commit = _git_repo(tmp_path)
    tree = _git(tmp_path, "rev-parse", "HEAD^{tree}")
    request = model.RunRequest.create(*TUPLE, commit, commit, model.OPT_OUT)
    expected = {
        name: (tmp_path / name).read_bytes()
        for name in (
            provenance.REGISTRY_PATH,
            provenance.FIXTURE_PATH,
            provenance.RESOURCE_PATH,
        )
    }
    source_identity = provenance._source_identity

    def mutate_after_identity(*args):
        identity = source_identity(*args)
        for name in expected:
            (tmp_path / name).write_bytes(b"mutable replacement")
        return identity

    monkeypatch.setattr(provenance, "_source_identity", mutate_after_identity)
    inputs = provenance.load_candidate_inputs(tmp_path, request, tree)

    assert inputs.registry == expected[provenance.REGISTRY_PATH]
    assert inputs.fixture == expected[provenance.FIXTURE_PATH]
    assert inputs.resource == expected[provenance.RESOURCE_PATH]
    assert inputs.input_digest != model.content_digest(
        [(name, b"mutable replacement") for name in expected]
    )


def test_capture_snapshot_rejects_wrong_root_head_tree_and_rollback(tmp_path, monkeypatch):
    commit = _git_repo(tmp_path)
    tree = _git(tmp_path, "rev-parse", "HEAD^{tree}")
    request = model.RunRequest.create(*TUPLE, commit, commit, model.OPT_OUT)
    _install_synthetic_distribution(monkeypatch, tmp_path, commit)
    inputs = provenance.load_candidate_inputs(tmp_path, request, tree)

    subdirectory = tmp_path / "nested"
    subdirectory.mkdir()
    with pytest.raises(model.CanaryError, match="checkout root"):
        provenance.capture_snapshot(subdirectory, request, inputs)
    with pytest.raises(model.CanaryError, match="tree does not match"):
        provenance.capture_snapshot(
            tmp_path, request, provenance.CandidateInputs(**{**inputs.__dict__, "tree": "c" * 40})
        )
    bad_rollback = model.RunRequest.create(*TUPLE, commit, "f" * 40, model.OPT_OUT)
    with pytest.raises(model.CanaryError, match="Git identity check failed"):
        provenance.capture_snapshot(tmp_path, bad_rollback, inputs)

    (tmp_path / "new.txt").write_text("next", encoding="utf-8")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-q", "-m", "move head")
    with pytest.raises(model.CanaryError, match="candidate commit"):
        provenance.capture_snapshot(tmp_path, request, inputs)


@pytest.mark.parametrize("failure", ["missing-direct", "missing-files", "wrong-bytes", "unsafe-link"])
def test_distribution_snapshot_fails_closed_on_hostile_install(
    tmp_path, monkeypatch, failure
):
    package = tmp_path / "pdf"
    package.mkdir()
    installed = package / "__init__.py"
    installed.write_bytes(b"candidate\n")
    expected_files = ("pdf/__init__.py",)
    expected_digest = model.content_digest([(expected_files[0], b"candidate\n")])
    direct = _direct_url().decode("utf-8")
    files = (metadata.PackagePath(expected_files[0]),)
    if failure == "missing-direct":
        direct = None
    elif failure == "missing-files":
        files = None
    elif failure == "wrong-bytes":
        installed.write_bytes(b"tampered\n")
    elif failure == "unsafe-link":
        installed.unlink()
        target = tmp_path / "outside.py"
        target.write_bytes(b"candidate\n")
        installed.symlink_to(target)
    distribution = _SyntheticDistribution(tmp_path, direct, files)
    monkeypatch.setattr(provenance.metadata, "distribution", lambda _name: distribution)

    with pytest.raises(model.CanaryError):
        provenance._distribution_snapshot(CANDIDATE, expected_digest, expected_files)


def test_distribution_snapshot_enforces_file_and_byte_bounds(tmp_path, monkeypatch):
    package = tmp_path / "pdf"
    package.mkdir()
    installed = package / "__init__.py"
    installed.write_bytes(b"candidate\n")
    expected_files = ("pdf/__init__.py",)
    distribution = _SyntheticDistribution(
        tmp_path,
        _direct_url().decode("utf-8"),
        (metadata.PackagePath(expected_files[0]),),
    )
    monkeypatch.setattr(provenance.metadata, "distribution", lambda _name: distribution)
    monkeypatch.setattr(provenance, "MAX_INSTALLED_BYTES", 1)

    with pytest.raises(model.CanaryError, match="bounds"):
        provenance._distribution_snapshot(CANDIDATE, "d" * 64, expected_files)


def test_candidate_package_file_count_boundary(tmp_path, monkeypatch):
    commit = _git_repo(tmp_path)
    tree = _git(tmp_path, "rev-parse", "HEAD^{tree}")
    monkeypatch.setattr(provenance, "MAX_INSTALLED_FILES", 1)
    digest, files = provenance._package_manifest(tmp_path, tree)
    assert len(digest) == 64
    assert files == ("pdf/__init__.py",)
    monkeypatch.setattr(provenance, "MAX_INSTALLED_FILES", 0)
    with pytest.raises(model.CanaryError, match="bounds"):
        provenance._package_manifest(tmp_path, tree)


def test_stage_verified_package_rechecks_bytes_before_execution(tmp_path):
    installed_root = tmp_path / "installed/pdf"
    installed_root.mkdir(parents=True)
    installed_file = installed_root / "__init__.py"
    installed_file.write_bytes(b"verified\n")
    digest = model.content_digest([("pdf/__init__.py", b"verified\n")])
    snapshot = _snapshot(
        installed_digest=digest,
        expected_package_digest=digest,
        package_root=installed_root,
    )
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    staged = provenance.stage_verified_package(snapshot, workspace)
    assert (staged / "__init__.py").read_bytes() == b"verified\n"

    installed_file.write_bytes(b"tampered\n")
    second_workspace = tmp_path / "workspace-2"
    second_workspace.mkdir()
    with pytest.raises(model.CanaryError, match="staged package bytes"):
        provenance.stage_verified_package(snapshot, second_workspace)


def test_source_snapshot_change_is_rejected():
    with pytest.raises(model.CanaryError, match="changed"):
        provenance.assert_unchanged(_snapshot(), _snapshot(installed_digest="f" * 64))


def test_ephemeral_cleanup_success_and_primary_failure(tmp_path):
    observed: list[Path] = []
    result = lifecycle.run_ephemeral(tmp_path, lambda workspace: observed.append(workspace) or "ok")
    assert result == "ok"
    assert observed and not observed[0].exists()

    def fail(workspace: Path):
        observed.append(workspace)
        raise model.CanaryError("scenario failed", "bounded primary", 9)

    with pytest.raises(model.CanaryError, match="bounded primary") as caught:
        lifecycle.run_ephemeral(tmp_path, fail)
    assert caught.value.category == "scenario failed"
    assert not observed[-1].exists()


def test_cleanup_failure_contract_preserves_primary_and_never_succeeds(tmp_path):
    def cleanup_fail(_path: Path) -> None:
        raise PermissionError("private path")

    with pytest.raises(model.CanaryError) as cleanup_only:
        lifecycle.run_ephemeral(tmp_path, lambda _workspace: "pass", remove_tree=cleanup_fail)
    assert cleanup_only.value.category == "cleanup failed"
    assert cleanup_only.value.cleanup_warning

    def primary(_workspace: Path):
        raise model.CanaryError("scenario failed", "bounded primary", 9)

    with pytest.raises(model.CanaryError) as combined:
        lifecycle.run_ephemeral(tmp_path, primary, remove_tree=cleanup_fail)
    assert combined.value.category == "scenario failed"
    assert combined.value.detail == "bounded primary"
    assert combined.value.cleanup_warning


@pytest.mark.parametrize("interruption", [KeyboardInterrupt(), SystemExit(130)])
def test_ephemeral_cleanup_runs_and_preserves_interruption(tmp_path, interruption):
    observed: list[Path] = []

    def interrupt(workspace: Path):
        observed.append(workspace)
        (workspace / "partial.pdf").write_bytes(b"partial")
        raise interruption

    with pytest.raises(type(interruption)):
        lifecycle.run_ephemeral(tmp_path, interrupt)
    assert observed and not observed[0].exists()


def test_interruption_reports_bounded_cleanup_residue_note(tmp_path):
    interruption = KeyboardInterrupt()

    def interrupt(_workspace: Path):
        raise interruption

    def cleanup_fail(_path: Path) -> None:
        raise PermissionError("private path")

    with pytest.raises(KeyboardInterrupt) as caught:
        lifecycle.run_ephemeral(tmp_path, interrupt, remove_tree=cleanup_fail)
    assert caught.value.__notes__ == [
        "downstream canary cleanup warning: ephemeral residue may remain"
    ]


def test_lease_contention_lifecycle_and_safe_target(tmp_path):
    lease_path = tmp_path / "canary.lock"
    ready = multiprocessing.Event()
    release = multiprocessing.Event()
    child = multiprocessing.Process(target=_hold_lease, args=(str(lease_path), ready, release))
    child.start()
    try:
        assert ready.wait(5)
        with pytest.raises(model.CanaryError, match="another canary"):
            with lifecycle.Lease(lease_path):
                pass
    finally:
        release.set()
        child.join(5)
    assert child.exitcode == 0
    assert lease_path.is_file()
    with lifecycle.Lease(lease_path):
        pass
    target = tmp_path / "target.lock"
    target.touch()
    unsafe = tmp_path / "unsafe.lock"
    unsafe.symlink_to(target)
    with pytest.raises(model.CanaryError, match="unsafe"):
        with lifecycle.Lease(unsafe):
            pass


def test_scenarios_cover_all_apis_themes_resources_base_url_and_optout(tmp_path, monkeypatch):
    calls: dict[str, list] = {name: [] for name in (
        "parse_front_matter", "md_to_html", "build_html", "build_pdf", "postprocess"
    )}

    def parse(markdown):
        theme = next(value for value in scenarios.THEMES if f"theme: {value}" in markdown)
        calls["parse_front_matter"].append(theme)
        return {
            "title": "Sanitized downstream canary", "theme": theme, "lang": "en-AU"
        }, markdown

    def md_to_html(body, metadata):
        calls["md_to_html"].append(metadata["theme"])
        return f'<img src="{scenarios.RESOURCE_NAME}"><table>{body}</table>'

    def build_html(source, output):
        calls["build_html"].append(source)
        Path(output).write_text("html", encoding="utf-8")
        return output

    def build_pdf(source, output, *, base_url=None):
        calls["build_pdf"].append((source, base_url))
        Path(output).write_bytes(b"synthetic pdf")
        return output

    def postprocess(html, metadata):
        calls["postprocess"].append(metadata)
        return html

    monkeypatch.setattr(scenarios, "_load_api", lambda *_roots: contextlib.nullcontext({
        "parse_front_matter": parse,
        "md_to_html": md_to_html,
        "build_html": build_html,
        "build_pdf": build_pdf,
        "postprocess": postprocess,
    }))
    checks = scenarios._run_scenarios_in_process(
        tmp_path,
        Path("/synthetic/site/pdf"),
        Path("/synthetic/site"),
        (ROOT / provenance.FIXTURE_PATH).read_bytes(),
        (ROOT / provenance.RESOURCE_PATH).read_bytes(),
    )

    assert checks == model.CHECK_IDS
    assert calls["parse_front_matter"] == list(scenarios.THEMES)
    assert calls["md_to_html"] == list(scenarios.THEMES)
    assert len(calls["build_html"]) == len(scenarios.THEMES)
    assert {base_url for _source, base_url in calls["build_pdf"]} == {tmp_path.as_uri() + "/"}
    assert calls["postprocess"] == [{"table_widths": False}]


def test_scenarios_reject_wrong_front_matter_language(tmp_path, monkeypatch):
    def parse(markdown):
        theme = next(value for value in scenarios.THEMES if f"theme: {value}" in markdown)
        return {
            "title": "Sanitized downstream canary", "theme": theme, "lang": "en-US"
        }, markdown

    monkeypatch.setattr(scenarios, "_load_api", lambda *_roots: contextlib.nullcontext({
        "parse_front_matter": parse,
        "md_to_html": lambda body, _metadata: body,
        "build_html": lambda *_args: None,
        "build_pdf": lambda *_args, **_kwargs: None,
        "postprocess": lambda html, _metadata: html,
    }))
    with pytest.raises(model.CanaryError, match="front matter"):
        scenarios._run_scenarios_in_process(
            tmp_path,
            Path("/synthetic/site/pdf"),
            Path("/synthetic/site"),
            (ROOT / provenance.FIXTURE_PATH).read_bytes(),
            (ROOT / provenance.RESOURCE_PATH).read_bytes(),
        )


@pytest.mark.parametrize(
    ("failure", "message"),
    [
        ("missing-resource", "relative resource"),
        ("missing-html", "builder output"),
        ("missing-pdf", "builder output"),
        ("colgroup", "opt-out"),
    ],
)
def test_scenarios_fail_closed_for_missing_outputs_resources_and_optout(
    tmp_path, monkeypatch, failure, message
):
    def parse(markdown):
        theme = next(value for value in scenarios.THEMES if f"theme: {value}" in markdown)
        return {
            "title": "Sanitized downstream canary", "theme": theme, "lang": "en-AU"
        }, markdown

    def build_html(_source, output):
        if failure != "missing-html":
            Path(output).write_text("html", encoding="utf-8")

    def build_pdf(_source, output, *, base_url=None):
        assert base_url
        if failure != "missing-pdf":
            Path(output).write_bytes(b"pdf")

    fake_api = {
        "parse_front_matter": parse,
        "md_to_html": lambda body, _metadata: (
            "<p>resource omitted</p>"
            if failure == "missing-resource"
            else scenarios.RESOURCE_NAME + body
        ),
        "build_html": build_html,
        "build_pdf": build_pdf,
        "postprocess": lambda html, _metadata: (
            "<colgroup></colgroup>" + html if failure == "colgroup" else html
        ),
    }
    monkeypatch.setattr(
        scenarios, "_load_api", lambda *_roots: contextlib.nullcontext(fake_api)
    )

    with pytest.raises(model.CanaryError, match=message):
        scenarios._run_scenarios_in_process(
            tmp_path,
            Path("/synthetic/site/pdf"),
            Path("/synthetic/site"),
            (ROOT / provenance.FIXTURE_PATH).read_bytes(),
            (ROOT / provenance.RESOURCE_PATH).read_bytes(),
        )


def test_api_loader_ignores_hostile_import_path_and_uses_verified_copy(tmp_path, monkeypatch):
    verified = tmp_path / "verified/pdf"
    hostile = tmp_path / "hostile/pdf"
    verified.mkdir(parents=True)
    hostile.mkdir(parents=True)
    (verified / "__init__.py").write_text(
        "MARKER = 'verified'\n"
        "build_pdf = build_html = md_to_html = parse_front_matter = lambda *a, **k: None\n",
        encoding="utf-8",
    )
    (verified / "postprocess.py").write_text(
        "def postprocess(html, metadata=None): return html\n", encoding="utf-8"
    )
    (hostile / "__init__.py").write_text(
        "raise RuntimeError('hostile import executed')\n", encoding="utf-8"
    )
    monkeypatch.syspath_prepend(str(hostile.parent))
    prior_pdf = types.ModuleType("pdf")
    monkeypatch.setitem(sys.modules, "pdf", prior_pdf)
    before_path = sys.path[:]
    before_meta_path = sys.meta_path[:]
    before_pdf_modules = {
        name: module
        for name, module in sys.modules.items()
        if name == "pdf" or name.startswith("pdf.")
    }

    with scenarios._load_api(verified, tmp_path) as api:
        assert api["postprocess"]("safe") == "safe"
    assert sys.path == before_path
    assert sys.meta_path == before_meta_path
    assert {
        name: module
        for name, module in sys.modules.items()
        if name == "pdf" or name.startswith("pdf.")
    } == before_pdf_modules


def test_api_loader_restores_import_state_after_package_failure(tmp_path, monkeypatch):
    failing = tmp_path / "verified/pdf"
    failing.mkdir(parents=True)
    (failing / "__init__.py").write_text(
        "raise RuntimeError('synthetic package failure')\n", encoding="utf-8"
    )
    prior_pdf = types.ModuleType("pdf")
    monkeypatch.setitem(sys.modules, "pdf", prior_pdf)
    before_path = sys.path[:]
    before_meta_path = sys.meta_path[:]

    with pytest.raises(RuntimeError, match="synthetic package failure"):
        with scenarios._load_api(failing, tmp_path):
            pass
    assert sys.path == before_path
    assert sys.meta_path == before_meta_path
    assert sys.modules["pdf"] is prior_pdf


def _write_worker_package(root: Path) -> Path:
    package = root / "pdf"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text(
        "from pathlib import Path\n"
        "import sys\n"
        "print('discarded worker diagnostic', file=sys.stderr)\n"
        "def parse_front_matter(markdown):\n"
        "    values = {}\n"
        "    for line in markdown.splitlines()[1:6]:\n"
        "        if ': ' in line:\n"
        "            key, value = line.split(': ', 1)\n"
        "            values[key] = value.strip('\\\"')\n"
        "    return values, markdown\n"
        "def md_to_html(body, metadata):\n"
        "    return '<img src=\\\"canary-resource.svg\\\">' + body\n"
        "def build_html(source, output):\n"
        "    Path(output).write_text('html', encoding='utf-8')\n"
        "def build_pdf(source, output, base_url=None):\n"
        "    Path(output).write_bytes(b'pdf')\n",
        encoding="utf-8",
    )
    (package / "postprocess.py").write_text(
        "def postprocess(html, metadata=None): return html\n", encoding="utf-8"
    )
    return package


def test_isolated_worker_runs_concurrently_without_parent_import_mutation(tmp_path):
    package = _write_worker_package(tmp_path / "runtime")
    fixture = (ROOT / provenance.FIXTURE_PATH).read_bytes()
    resource = (ROOT / provenance.RESOURCE_PATH).read_bytes()
    workspaces = [tmp_path / "work-a", tmp_path / "work-b"]
    for workspace in workspaces:
        workspace.mkdir()
    before_path = sys.path[:]
    before_meta_path = sys.meta_path[:]
    before_pdf_modules = {
        name: module
        for name, module in sys.modules.items()
        if name == "pdf" or name.startswith("pdf.")
    }

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                lambda workspace: scenarios.run_scenarios(
                    workspace, package, tmp_path, fixture, resource
                ),
                workspaces,
            )
        )

    assert results == [model.CHECK_IDS, model.CHECK_IDS]
    assert sys.path == before_path
    assert sys.meta_path == before_meta_path
    assert {
        name: module
        for name, module in sys.modules.items()
        if name == "pdf" or name.startswith("pdf.")
    } == before_pdf_modules


@pytest.mark.parametrize(
    ("outcome", "cleanup_ok", "expected_category", "cleanup_warning"),
    [
        ("failure-status", True, "canary failed", False),
        ("timeout", True, "canary failed", False),
        ("success", False, "cleanup failed", True),
        ("failure-status", False, "canary failed", True),
        ("timeout", False, "canary failed", True),
    ],
)
def test_isolated_worker_wrapper_fails_closed_and_terminates_group(
    tmp_path, monkeypatch, outcome, cleanup_ok, expected_category, cleanup_warning
):
    class FakeProcess:
        pid = 123456

    process = FakeProcess()
    terminated: list[object] = []
    monkeypatch.setattr(scenarios.subprocess, "Popen", lambda *_args, **_kwargs: process)

    def await_status(_descriptor):
        if outcome == "timeout":
            raise subprocess.TimeoutExpired("worker", scenarios.WORKER_TIMEOUT_SECONDS)
        return b"F" if outcome == "failure-status" else b"P"

    monkeypatch.setattr(scenarios, "_await_worker_status", await_status)
    monkeypatch.setattr(
        scenarios,
        "_terminate_worker_group",
        lambda value: terminated.append(value) or cleanup_ok,
    )

    with pytest.raises(model.CanaryError) as caught:
        scenarios.run_scenarios(
            tmp_path,
            Path("/verified/pdf"),
            Path("/dependencies"),
            b"fixture",
            b"resource",
        )
    assert caught.value.category == expected_category
    assert caught.value.cleanup_warning is cleanup_warning
    if expected_category == "canary failed":
        assert caught.value.detail == "isolated scenario worker failed"
        assert caught.value.exit_code == 9
    assert terminated == [process]


def test_worker_writer_close_failure_still_terminates_and_closes_reader(
    tmp_path, monkeypatch
):
    class FakeProcess:
        pid = 123456

    process = FakeProcess()
    terminated: list[object] = []
    closed: list[int] = []
    monkeypatch.setattr(scenarios.os, "pipe", lambda: (101, 102))
    monkeypatch.setattr(scenarios.subprocess, "Popen", lambda *_args, **_kwargs: process)
    monkeypatch.setattr(
        scenarios,
        "_close_descriptor",
        lambda descriptor: closed.append(descriptor) or descriptor != 102,
    )
    monkeypatch.setattr(
        scenarios,
        "_terminate_worker_group",
        lambda value: terminated.append(value) or True,
    )

    with pytest.raises(model.CanaryError) as caught:
        scenarios.run_scenarios(
            tmp_path,
            Path("/verified/pdf"),
            Path("/dependencies"),
            b"fixture",
            b"resource",
        )

    assert caught.value.category == "canary failed"
    assert caught.value.cleanup_warning
    assert terminated == [process]
    assert closed == [102, 101]


@pytest.mark.parametrize("close_failure", [False, True])
def test_worker_spawn_failure_closes_pipe_and_reports_cleanup(
    tmp_path, monkeypatch, close_failure
):
    closed: list[int] = []
    monkeypatch.setattr(scenarios.os, "pipe", lambda: (101, 102))

    def fail_spawn(*_args, **_kwargs):
        raise OSError("synthetic spawn failure")

    monkeypatch.setattr(scenarios.subprocess, "Popen", fail_spawn)
    monkeypatch.setattr(
        scenarios,
        "_close_descriptor",
        lambda descriptor: closed.append(descriptor)
        or not (close_failure and descriptor == 102),
    )

    with pytest.raises(model.CanaryError) as caught:
        scenarios.run_scenarios(
            tmp_path,
            Path("/verified/pdf"),
            Path("/dependencies"),
            b"fixture",
            b"resource",
        )

    assert caught.value.category == "canary failed"
    assert caught.value.detail == "isolated scenario worker failed"
    assert caught.value.exit_code == 9
    assert caught.value.cleanup_warning is close_failure
    assert closed == [101, 102]


@pytest.mark.parametrize("interruption", [KeyboardInterrupt, SystemExit])
@pytest.mark.parametrize("cleanup_ok", [True, False])
def test_worker_ownership_is_registered_before_result_collection(
    tmp_path, monkeypatch, interruption, cleanup_ok
):
    class FakeProcess:
        pid = 123456

    process = FakeProcess()
    terminated: list[object] = []
    monkeypatch.setattr(scenarios.subprocess, "Popen", lambda *_args, **_kwargs: process)

    def interrupt_collection(_worker):
        raise interruption

    monkeypatch.setattr(scenarios, "_collect_worker_result", interrupt_collection)
    monkeypatch.setattr(
        scenarios,
        "_terminate_worker_group",
        lambda value: terminated.append(value) or cleanup_ok,
    )

    with pytest.raises(interruption) as caught:
        scenarios.run_scenarios(
            tmp_path,
            Path("/verified/pdf"),
            Path("/dependencies"),
            b"fixture",
            b"resource",
        )

    assert terminated == [process]
    notes = getattr(caught.value, "__notes__", [])
    if cleanup_ok:
        assert notes == []
    else:
        assert notes == [
            "downstream canary cleanup warning: worker residue may remain"
        ]


def test_acquisition_interruption_reports_cleanup_failure(tmp_path, monkeypatch):
    class FakeProcess:
        pid = 123456

    process = FakeProcess()

    def interrupt_start(worker, *_args):
        worker.process = process
        worker.read_descriptor = 101
        worker.write_descriptor = 102
        raise KeyboardInterrupt

    monkeypatch.setattr(scenarios, "_start_worker", interrupt_start)
    monkeypatch.setattr(scenarios, "_terminate_worker_group", lambda _process: False)
    monkeypatch.setattr(scenarios, "_close_descriptor", lambda _descriptor: True)

    with pytest.raises(KeyboardInterrupt) as caught:
        scenarios.run_scenarios(
            tmp_path,
            Path("/verified/pdf"),
            Path("/dependencies"),
            b"fixture",
            b"resource",
        )

    assert caught.value.__notes__ == [
        "downstream canary cleanup warning: worker residue may remain"
    ]


def test_failed_worker_terminates_spawned_descendant_with_stable_group(tmp_path, monkeypatch):
    package = tmp_path / "runtime/pdf"
    package.mkdir(parents=True)
    pid_file = tmp_path / "descendant.pid"
    (package / "__init__.py").write_text(
        "from pathlib import Path\n"
        "import subprocess, sys, time\n"
        f"child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
        f"Path({str(pid_file)!r}).write_text(str(child.pid), encoding='ascii')\n"
        "raise RuntimeError('fail after descendant readiness')\n",
        encoding="utf-8",
    )
    (package / "postprocess.py").write_text(
        "def postprocess(html, metadata=None): return html\n", encoding="utf-8"
    )
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    real_popen = subprocess.Popen
    workers: list[subprocess.Popen] = []

    def tracked_popen(*args, **kwargs):
        process = real_popen(*args, **kwargs)
        workers.append(process)
        return process

    monkeypatch.setattr(scenarios.subprocess, "Popen", tracked_popen)
    descendant_pid: int | None = None
    try:
        with pytest.raises(model.CanaryError, match="isolated scenario worker failed"):
            scenarios.run_scenarios(
                workspace,
                package,
                tmp_path,
                (ROOT / provenance.FIXTURE_PATH).read_bytes(),
                (ROOT / provenance.RESOURCE_PATH).read_bytes(),
            )
        descendant_pid = int(pid_file.read_text(encoding="ascii"))
        for _attempt in range(500):
            try:
                os.kill(descendant_pid, 0)
            except ProcessLookupError:
                break
            time.sleep(0.01)
        else:
            pytest.fail("worker descendant survived process-group termination")
    finally:
        for worker in workers:
            if worker.returncode is None:
                try:
                    os.killpg(worker.pid, 9)
                except ProcessLookupError:
                    pass
                try:
                    worker.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    worker.kill()
        if descendant_pid is not None:
            try:
                os.kill(descendant_pid, 9)
            except ProcessLookupError:
                pass


def _configure_success(monkeypatch, temp_parent: Path):
    def authorize(root, operation, environment, recipient):
        assert root == ROOT
        assert (operation, environment, recipient) == (
            "consumer_canary", TUPLE[1], TUPLE[2]
        )
        return {"git_tree": TREE}

    monkeypatch.setattr(cli, "entitlement_preflight", authorize)
    monkeypatch.setattr(cli, "load_candidate_inputs", lambda *_args: _inputs())
    snapshots = [_snapshot(), _snapshot()]
    monkeypatch.setattr(cli, "capture_snapshot", lambda *_args: snapshots.pop(0))
    monkeypatch.setattr(cli, "stage_verified_package", lambda *_args: Path("/verified/pdf"))
    monkeypatch.setattr(cli, "run_scenarios", lambda *_args: model.CHECK_IDS)


def test_entitlement_denial_precedes_registry_lease_temp_and_import(tmp_path, monkeypatch):
    def deny(root, operation, environment, recipient):
        assert root == ROOT
        assert (operation, environment, recipient) == (
            "consumer_canary", TUPLE[1], TUPLE[2]
        )
        raise PreflightError("denied", "authorization status is not_verified", 2)

    monkeypatch.setattr(cli, "entitlement_preflight", deny)
    monkeypatch.setattr(
        cli,
        "load_candidate_inputs",
        lambda *_args: pytest.fail("candidate inputs read before entitlement"),
    )
    monkeypatch.setattr(cli, "Lease", lambda *_args: pytest.fail("lease acquired before entitlement"))
    monkeypatch.setattr(cli, "run_ephemeral", lambda *_args: pytest.fail("temp allocated before entitlement"))

    with pytest.raises(model.CanaryError, match="not_verified"):
        cli.run(ROOT, _request(), tmp_path / "lease", tmp_path)


def test_denied_subprocess_imports_no_renderer_or_pdf(tmp_path):
    script = """
from pathlib import Path
import sys
from tools.distribution_entitlement import PreflightError
from tools.downstream_canary import cli, model
assert not any(name == 'pdf' or name.startswith('pdf.') or name.startswith('weasyprint') for name in sys.modules)
def deny(*args):
    raise PreflightError('denied', 'authorization status is not_verified', 2)
cli.entitlement_preflight = deny
request = model.RunRequest.create('private_consumer', 'consumer_environment', 'consumer_recipient', 'a' * 40, 'b' * 40, model.OPT_OUT)
try:
    cli.run(Path.cwd(), request, Path('/missing/lease'), Path('/missing/temp'))
except model.CanaryError:
    pass
else:
    raise AssertionError('denial expected')
assert not any(name == 'pdf' or name.startswith('pdf.') or name.startswith('weasyprint') for name in sys.modules)
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr


def test_coordinator_holds_lease_through_cleanup_final_validation_and_publication(
    tmp_path, monkeypatch
):
    _configure_success(monkeypatch, tmp_path)
    lease_path = tmp_path / "canary.lock"
    published: list[str] = []

    def publish(value: str) -> None:
        with pytest.raises(model.CanaryError, match="another canary"):
            with lifecycle.Lease(lease_path):
                pass
        published.append(value)

    cli.run(ROOT, _request(), lease_path, tmp_path, publish=publish)

    assert len(published) == 1
    assert json.loads(published[0])["status"] == "pass"
    with lifecycle.Lease(lease_path):
        pass


def test_authorized_coordinator_wires_real_inputs_provenance_staging_and_result(
    tmp_path, monkeypatch
):
    commit = _git_repo(tmp_path)
    tree = _git(tmp_path, "rev-parse", "HEAD^{tree}")
    request = model.RunRequest.create(*TUPLE, commit, commit, model.OPT_OUT)
    expected_inputs = provenance.load_candidate_inputs(tmp_path, request, tree)
    _install_synthetic_distribution(monkeypatch, tmp_path, commit)
    monkeypatch.setattr(
        cli, "entitlement_preflight", lambda *_args: {"git_tree": tree}
    )

    def renderer_stub(workspace, package_root, dependency_root, fixture, resource):
        assert package_root.is_relative_to(workspace)
        assert (package_root / "__init__.py").read_text(encoding="utf-8") == (
            "VALUE = 'candidate'\n"
        )
        assert dependency_root == tmp_path
        assert fixture == expected_inputs.fixture
        assert resource == expected_inputs.resource
        return model.CHECK_IDS

    monkeypatch.setattr(cli, "run_scenarios", renderer_stub)
    state = tmp_path / ".git/canary-state"
    temporary = tmp_path / ".git/canary-tmp"
    state.mkdir()
    temporary.mkdir()
    published: list[str] = []

    cli.run(
        tmp_path,
        request,
        state / "canary.lock",
        temporary,
        publish=published.append,
    )

    result = json.loads(published[0])
    assert result["input_digest"] == expected_inputs.input_digest
    assert result["candidate_tree"] == tree
    assert not list(temporary.iterdir())


def test_final_environment_mutation_publishes_no_result(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "entitlement_preflight", lambda *_args: {"git_tree": TREE})
    monkeypatch.setattr(cli, "load_candidate_inputs", lambda *_args: _inputs())
    snapshots = [_snapshot(), _snapshot(installed_digest="f" * 64)]
    monkeypatch.setattr(cli, "capture_snapshot", lambda *_args: snapshots.pop(0))
    monkeypatch.setattr(cli, "stage_verified_package", lambda *_args: Path("/verified/pdf"))
    monkeypatch.setattr(cli, "run_scenarios", lambda *_args: model.CHECK_IDS)
    published: list[str] = []

    with pytest.raises(model.CanaryError, match="changed"):
        cli.run(ROOT, _request(), tmp_path / "lease", tmp_path, publish=published.append)
    assert published == []


def test_real_cli_is_denied_before_touching_missing_consumer_paths(tmp_path):
    command = [
        sys.executable, "-m", "tools.downstream_canary",
        "--consumer", TUPLE[0], "--environment", "consumer_owned",
        "--recipient", "named_consumer", "--candidate", CANDIDATE,
        "--rollback", ROLLBACK, "--opt-out", model.OPT_OUT,
        "--lease-path", str(tmp_path / "missing-lease-parent/lease"),
        "--temp-parent", str(tmp_path / "missing-temp-parent"),
    ]
    result = subprocess.run(
        command, cwd=ROOT, check=False, capture_output=True, text=True, timeout=10
    )

    assert result.returncode == 2
    assert result.stdout == ""
    assert result.stderr == (
        "downstream canary: entitlement denied: authorization status is not_verified\n"
    )
    assert not (tmp_path / "missing-lease-parent").exists()
    assert not (tmp_path / "missing-temp-parent").exists()
