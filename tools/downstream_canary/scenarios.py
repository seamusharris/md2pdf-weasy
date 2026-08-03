"""Sanitized public-API scenarios executed from verified ephemeral bytes."""

from __future__ import annotations

import contextlib
from dataclasses import dataclass
import importlib
from importlib.machinery import BuiltinImporter, FrozenImporter, PathFinder
import importlib.util
import io
import os
from pathlib import Path
import select
import signal
import subprocess
import sys
import sysconfig
from typing import Any, Callable, Iterator

from .model import CanaryError, CHECK_IDS


THEMES = ("alpine", "wnc", "regrading", "neutral", "compact")
RESOURCE_NAME = "canary-resource.svg"
WORKER_TIMEOUT_SECONDS = 300
WORKER_TERMINATE_SECONDS = 2


def _safe_import_paths(package_root: Path, dependency_root: Path) -> list[str]:
    paths = [str(package_root.parent), str(dependency_root)]
    for key in ("stdlib", "platstdlib"):
        value = sysconfig.get_path(key)
        if value and value not in paths:
            paths.append(value)
    extension_path = sysconfig.get_config_var("DESTSHARED")
    if extension_path and extension_path not in paths:
        paths.append(extension_path)
    return paths


def _verify_loaded_origins(package_root: Path) -> None:
    for name, module in tuple(sys.modules.items()):
        if name != "pdf" and not name.startswith("pdf."):
            continue
        try:
            origin = Path(module.__file__).resolve(strict=True)
        except (AttributeError, OSError, TypeError) as exc:
            raise CanaryError("API invalid", "installed public API origin is unavailable", 9) from exc
        if not origin.is_relative_to(package_root):
            raise CanaryError("API invalid", "imported package does not match verified provenance", 9)


@contextlib.contextmanager
def _load_api(
    package_root: Path,
    dependency_root: Path,
) -> Iterator[dict[str, Callable[..., Any]]]:
    """Load only the staged candidate package while preserving caller imports."""

    try:
        expected_origin = (package_root / "__init__.py").resolve(strict=True)
        spec = PathFinder.find_spec("pdf", [str(package_root.parent)])
        origin = Path(spec.origin).resolve(strict=True) if spec and spec.origin else None
    except (ImportError, OSError, TypeError) as exc:
        raise CanaryError("API invalid", "verified public API origin is unavailable", 9) from exc
    if spec is None or spec.loader is None or origin != expected_origin:
        raise CanaryError("API invalid", "verified public API origin is invalid", 9)

    previous_path = sys.path[:]
    previous_meta_path = sys.meta_path[:]
    previous_modules = {
        name: module
        for name, module in sys.modules.items()
        if name == "pdf" or name.startswith("pdf.")
    }
    for name in previous_modules:
        del sys.modules[name]
    try:
        sys.path[:] = _safe_import_paths(package_root, dependency_root)
        sys.meta_path[:] = [BuiltinImporter, FrozenImporter, PathFinder]
        package = importlib.util.module_from_spec(spec)
        sys.modules["pdf"] = package
        spec.loader.exec_module(package)
        postprocess_module = importlib.import_module("pdf.postprocess")
        _verify_loaded_origins(package_root)
        names = ("build_pdf", "build_html", "md_to_html", "parse_front_matter")
        api = {name: getattr(package, name, None) for name in names}
        api["postprocess"] = getattr(postprocess_module, "postprocess", None)
        if not all(callable(value) for value in api.values()):
            raise CanaryError("API invalid", "ratified Python API is incomplete", 9)
        yield api  # type: ignore[misc]
    except CanaryError:
        raise
    except (AttributeError, ImportError, OSError, TypeError) as exc:
        raise CanaryError("API invalid", "installed public API is unavailable", 9) from exc
    finally:
        for name in tuple(sys.modules):
            if name == "pdf" or name.startswith("pdf."):
                del sys.modules[name]
        sys.modules.update(previous_modules)
        sys.meta_path[:] = previous_meta_path
        sys.path[:] = previous_path


def _run_theme(
    api: dict[str, Callable[..., Any]],
    workspace: Path,
    template: str,
    theme: str,
) -> tuple[bool, str]:
    markdown = template.replace("__THEME__", theme)
    source = workspace / f"canary-{theme}.md"
    html_output = workspace / f"canary-{theme}.html"
    pdf_output = workspace / f"canary-{theme}.pdf"
    source.write_text(markdown, encoding="utf-8")
    metadata, body = api["parse_front_matter"](markdown)
    if (
        metadata.get("theme") != theme
        or metadata.get("title") != "Sanitized downstream canary"
        or metadata.get("lang") != "en-AU"
    ):
        raise CanaryError("canary failed", "front matter contract failed", 9)
    html = api["md_to_html"](body, metadata)
    api["build_html"](source, html_output)
    base_url = workspace.as_uri() + "/"
    api["build_pdf"](source, pdf_output, base_url=base_url)
    if not html_output.is_file() or not pdf_output.is_file():
        raise CanaryError("canary failed", "builder output contract failed", 9)
    return RESOURCE_NAME in html, base_url


def _assert_opt_out(api: dict[str, Callable[..., Any]]) -> None:
    output = api["postprocess"](
        "<table><thead><tr><th>Team</th><th>P</th></tr></thead>"
        "<tbody><tr><td>Harbour Owls</td><td>9</td></tr></tbody></table>",
        {"table_widths": False},
    )
    if "<colgroup" in output.lower():
        raise CanaryError("canary failed", "table-width opt-out contract failed", 9)


def _run_scenarios_in_process(
    workspace: Path,
    package_root: Path,
    dependency_root: Path,
    fixture: bytes,
    resource: bytes,
) -> tuple[str, ...]:
    try:
        template = fixture.decode("utf-8")
    except UnicodeError as exc:
        raise CanaryError("fixture invalid", "sanitized fixture is not UTF-8", 8) from exc
    if template.count("__THEME__") != 1:
        raise CanaryError("fixture invalid", "sanitized fixture theme marker is invalid", 8)
    try:
        (workspace / RESOURCE_NAME).write_bytes(resource)
    except OSError as exc:
        raise CanaryError("workspace unavailable", "sanitized resource could not be staged", 8) from exc
    observations: list[tuple[bool, str]] = []
    with contextlib.redirect_stdout(io.StringIO()), _load_api(package_root, dependency_root) as api:
        observations = [_run_theme(api, workspace, template, theme) for theme in THEMES]
        _assert_opt_out(api)
    relative_seen = any(relative for relative, _base_url in observations)
    base_urls = {base_url for _relative, base_url in observations}
    if not relative_seen or len(base_urls) != 1:
        raise CanaryError("canary failed", "relative resource or base_url contract failed", 9)
    return CHECK_IDS


def _signal_worker_group(group_id: int, signal_number: int) -> bool:
    try:
        os.killpg(group_id, signal_number)
    except ProcessLookupError:
        return True
    except OSError:
        return False
    return True


def _terminate_worker_group(process: subprocess.Popen) -> bool:
    """Terminate the group while its unreaped leader keeps the identity stable."""

    _signal_worker_group(process.pid, signal.SIGTERM)
    killed = _signal_worker_group(process.pid, signal.SIGKILL)
    try:
        process.wait(timeout=WORKER_TERMINATE_SECONDS)
    except (OSError, subprocess.TimeoutExpired):
        try:
            process.kill()
            process.wait(timeout=WORKER_TERMINATE_SECONDS)
        except (OSError, subprocess.TimeoutExpired):
            return False
    return killed


def _await_worker_status(descriptor: int) -> bytes:
    ready, _writable, _errors = select.select(
        [descriptor], [], [], WORKER_TIMEOUT_SECONDS
    )
    if not ready:
        raise subprocess.TimeoutExpired("downstream-canary-worker", WORKER_TIMEOUT_SECONDS)
    try:
        return os.read(descriptor, 2)
    except OSError as exc:
        raise CanaryError("canary failed", "isolated scenario worker failed", 9) from exc


@dataclass
class _Worker:
    process: subprocess.Popen | None = None
    read_descriptor: int | None = None
    write_descriptor: int | None = None
    cleanup_ok: bool = True


def _close_descriptor(descriptor: int) -> bool:
    try:
        os.close(descriptor)
    except OSError:
        return False
    return True


def _start_worker(
    worker: _Worker,
    workspace: Path,
    package_root: Path,
    dependency_root: Path,
    fixture: bytes,
    resource: bytes,
) -> None:
    fixture_path = workspace / "worker-input.md"
    resource_path = workspace / "worker-input.svg"
    fixture_path.write_bytes(fixture)
    resource_path.write_bytes(resource)
    worker.read_descriptor, worker.write_descriptor = os.pipe()
    worker.process = subprocess.Popen(
        [
            sys.executable,
            "-I",
            str(Path(__file__).with_name("worker.py")),
            str(workspace),
            str(package_root),
            str(dependency_root),
            str(fixture_path),
            str(resource_path),
            str(worker.write_descriptor),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
        pass_fds=(worker.write_descriptor,),
    )


def _cleanup_worker(worker: _Worker) -> bool:
    cleanup_ok = worker.cleanup_ok
    if worker.process is not None and not _terminate_worker_group(worker.process):
        cleanup_ok = False
    for descriptor in (worker.read_descriptor, worker.write_descriptor):
        if descriptor is not None and not _close_descriptor(descriptor):
            cleanup_ok = False
    worker.read_descriptor = None
    worker.write_descriptor = None
    return cleanup_ok


@contextlib.contextmanager
def _managed_worker(
    workspace: Path,
    package_root: Path,
    dependency_root: Path,
    fixture: bytes,
    resource: bytes,
) -> Iterator[_Worker]:
    worker = _Worker()
    primary: BaseException | None = None
    try:
        _start_worker(worker, workspace, package_root, dependency_root, fixture, resource)
        yield worker
    except BaseException as exc:
        primary = exc
    finally:
        worker.cleanup_ok = _cleanup_worker(worker)
    if primary is not None:
        _raise_worker_failure(primary, worker.cleanup_ok)


def _raise_worker_failure(primary: BaseException, cleanup_ok: bool) -> None:
    if not isinstance(primary, Exception):
        if not cleanup_ok:
            primary.add_note("downstream canary cleanup warning: worker residue may remain")
        raise primary
    if isinstance(primary, CanaryError):
        raise CanaryError(
            primary.category,
            primary.detail,
            primary.exit_code,
            cleanup_warning=not cleanup_ok or primary.cleanup_warning,
        ) from primary
    raise CanaryError(
        "canary failed",
        "isolated scenario worker failed",
        9,
        cleanup_warning=not cleanup_ok,
    ) from primary


def _collect_worker_result(worker: _Worker) -> None:
    write_descriptor = worker.write_descriptor
    worker.write_descriptor = None
    if write_descriptor is None or not _close_descriptor(write_descriptor):
        worker.cleanup_ok = False
        raise CanaryError("canary failed", "isolated scenario worker failed", 9)
    if worker.read_descriptor is None:
        raise CanaryError("canary failed", "isolated scenario worker failed", 9)
    status = _await_worker_status(worker.read_descriptor)
    if status != b"P":
        raise CanaryError("canary failed", "isolated scenario worker failed", 9)


def run_scenarios(
    workspace: Path,
    package_root: Path,
    dependency_root: Path,
    fixture: bytes,
    resource: bytes,
) -> tuple[str, ...]:
    """Run candidate code in an isolated interpreter, never in the coordinator."""

    with _managed_worker(
        workspace, package_root, dependency_root, fixture, resource
    ) as worker:
        _collect_worker_result(worker)
    if not worker.cleanup_ok:
        raise CanaryError(
            "cleanup failed",
            "worker process residue may remain",
            10,
            cleanup_warning=True,
        )
    return CHECK_IDS
