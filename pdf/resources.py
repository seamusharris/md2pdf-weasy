"""Explicit local resource resolution and a WeasyPrint fetch boundary.

``allowed_root`` is a symlink-aware local-file access policy, not a general
sandbox: it does not limit network access, native libraries, resource sizes, or
concurrent filesystem changes. Install the returned fetcher on *both* HTML and
CSS objects so nested CSS, font, image and SVG requests use the same boundary.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable
from urllib.parse import unquote, urlsplit, urlunsplit


def _safe_reference(reference: str | Path) -> str:
    """Keep identifying metadata, never an embedded resource's contents."""
    if isinstance(reference, Path):
        return str(reference)
    value = str(reference)
    try:
        parsed = urlsplit(value)
    except ValueError:
        return "[invalid resource URL]"
    if parsed.scheme.lower() == "data":
        return "data:[redacted]"
    if parsed.scheme and parsed.scheme.lower() not in {"http", "https", "file"}:
        return f"{parsed.scheme.lower()}:[redacted]"
    if parsed.scheme.lower() in {"http", "https"} or parsed.netloc:
        # Tokens, credentials and document text in query/fragment are not useful
        # for local-file diagnostics.
        authority = parsed.netloc.rsplit("@", 1)[-1]
        return urlunsplit((parsed.scheme, authority, parsed.path, "", ""))
    if parsed.query or parsed.fragment:
        return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))
    return value


class ResourceAccessError(ValueError):
    """A resource or context violates the explicit local access policy."""

    def __init__(self, message: str, *, reference: str | Path, kind: str = "resource"):
        self.reference = _safe_reference(reference)
        self.kind = kind
        super().__init__(f"{message}: {self.reference}")


@dataclass(frozen=True)
class ResourceEvent:
    """Resource metadata only; no document, file, or embedded-URL contents."""

    kind: str
    status: str
    reference: str
    path: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "reference", _safe_reference(self.reference))

    def to_dict(self) -> dict[str, str | None]:
        return asdict(self)


ResourceCallback = Callable[[ResourceEvent], None]


def _emit(callback: ResourceCallback | None, kind: str, status: str,
          reference: str | Path, path: Path | None = None) -> None:
    if callback is not None:
        callback(ResourceEvent(kind, status, _safe_reference(reference),
                               str(path) if path is not None else None))


def _file_uri_path(value: str, *, kind: str) -> Path:
    parsed = urlsplit(value)
    if parsed.netloc.lower() not in {"", "localhost"}:
        raise ResourceAccessError("Nonlocal file authority is not supported",
                                  reference=value, kind=kind)
    try:
        path = Path(unquote(parsed.path, errors="strict"))
    except (UnicodeError, ValueError) as exc:
        raise ResourceAccessError("Invalid local file URI", reference=value,
                                  kind=kind) from exc
    if not path.is_absolute() or "\x00" in str(path):
        raise ResourceAccessError("File URI must contain an absolute local path",
                                  reference=value, kind=kind)
    return path


def _directory(value: str | Path, *, kind: str) -> Path:
    if isinstance(value, Path):
        path = value
    else:
        parsed = urlsplit(value)
        if parsed.scheme:
            if parsed.scheme.lower() != "file":
                raise ResourceAccessError("Directory must be local", reference=value,
                                          kind=kind)
            if parsed.query or parsed.fragment:
                raise ResourceAccessError("Directory URI cannot have a query or fragment",
                                          reference=value, kind=kind)
            path = _file_uri_path(value, kind=kind)
        else:
            path = Path(value)
    if not path.is_absolute() or "\x00" in str(path):
        raise ResourceAccessError("Directory must be an absolute local path",
                                  reference=value, kind=kind)
    try:
        resolved = path.resolve(strict=True)
    except (OSError, RuntimeError, ValueError) as exc:
        raise ResourceAccessError("Directory does not exist or cannot be resolved",
                                  reference=value, kind=kind) from exc
    if not resolved.is_dir():
        raise ResourceAccessError("Resource base must be a directory", reference=value,
                                  kind=kind)
    return resolved


_PACKAGE_DIR = Path(__file__).resolve().parent
_TRUSTED_PACKAGE_ROOTS = (_PACKAGE_DIR / "styles", _PACKAGE_DIR / "fonts")


@dataclass(frozen=True)
class ResourceContext:
    """An explicit local directory, optionally restricted to ``allowed_root``.

    String references are URL references: percent escapes are decoded exactly
    once, so a literal ``%20`` filename is referenced as ``%2520``. Pass a Path
    for a literal filesystem name. Context directory strings are filesystem
    names unless they start with ``file:``. No operation falls back to cwd.
    """

    base_dir: Path | str
    allowed_root: Path | str | None = None

    def __post_init__(self) -> None:
        base = _directory(self.base_dir, kind="base")
        root = (None if self.allowed_root is None else
                _directory(self.allowed_root, kind="allowed_root"))
        if root is not None and not base.is_relative_to(root):
            raise ResourceAccessError("Resource base is outside allowed_root",
                                      reference=self.base_dir, kind="base")
        object.__setattr__(self, "base_dir", base)
        object.__setattr__(self, "allowed_root", root)

    @property
    def base_url(self) -> str:
        return self.base_dir.as_uri().rstrip("/") + "/"

    def _resolve(self, reference: str | Path, *, kind: str,
                 trusted_package_resources: bool = False) -> Path | None:
        if isinstance(reference, Path):
            path = reference
        else:
            try:
                parsed = urlsplit(reference)
            except ValueError as exc:
                raise ResourceAccessError("Invalid resource URL", reference=reference,
                                          kind=kind) from exc
            if parsed.scheme.lower() == "file":
                path = _file_uri_path(reference, kind=kind)
            elif parsed.scheme or parsed.netloc:
                return None
            else:
                try:
                    path = Path(unquote(parsed.path, errors="strict"))
                except (UnicodeError, ValueError) as exc:
                    raise ResourceAccessError("Invalid local resource path",
                                              reference=reference, kind=kind) from exc
        if "\x00" in str(path):
            raise ResourceAccessError("Invalid local resource path", reference=reference,
                                      kind=kind)
        try:
            resolved = (path if path.is_absolute() else self.base_dir / path).resolve()
        except (OSError, RuntimeError, ValueError) as exc:
            raise ResourceAccessError("Local resource cannot be resolved",
                                      reference=reference, kind=kind) from exc
        if self.allowed_root is not None and not resolved.is_relative_to(self.allowed_root):
            trusted = trusted_package_resources and any(
                resolved.is_relative_to(root) for root in _TRUSTED_PACKAGE_ROOTS
            )
            if not trusted:
                raise ResourceAccessError("Local resource is outside allowed_root",
                                          reference=reference, kind=kind)
        return resolved

    def resolve_path(self, reference: str | Path, *, kind: str = "resource",
                     on_resource: ResourceCallback | None = None) -> Path | None:
        """Resolve a local reference, or return None for remote/embedded URLs.

        Missing paths are returned (and reported as ``missing``), letting the
        caller apply its own missing-resource policy. A denied path always raises.
        """
        try:
            path = self._resolve(reference, kind=kind)
        except ResourceAccessError:
            _emit(on_resource, kind, "blocked", reference)
            raise
        if path is None:
            status = "embedded" if str(reference).lower().startswith("data:") else "remote"
        else:
            status = "resolved" if path.is_file() else "missing"
        _emit(on_resource, kind, status, reference, path)
        return path

    def resolve_url(self, reference: str | Path, *, kind: str = "resource",
                    on_resource: ResourceCallback | None = None) -> str:
        """Return a canonical file URI, preserving nonlocal URL policy."""
        path = self.resolve_path(reference, kind=kind, on_resource=on_resource)
        if path is None:
            return str(reference)
        url = path.as_uri()
        if isinstance(reference, str):
            parsed = urlsplit(reference)
            url = urlunsplit((*urlsplit(url)[:3], parsed.query, parsed.fragment))
        return url


def make_url_fetcher(context: ResourceContext, *, fetcher: Callable | None = None,
                     on_resource: ResourceCallback | None = None) -> Callable:
    """Wrap actual WeasyPrint URL fetches, including nested resource requests.

    Network and data URLs are delegated unchanged and are never prefetched.
    Bundled styles/fonts are the only local-root exception; their symlinks may
    not escape those packaged directories. The delegate is imported lazily.
    """
    delegate = fetcher

    def guarded_fetcher(url: str, *args, **kwargs):
        nonlocal delegate
        try:
            path = context._resolve(url, kind="fetch", trusted_package_resources=True)
        except ResourceAccessError:
            _emit(on_resource, "fetch", "blocked", url)
            raise
        if path is not None and not path.is_file():
            _emit(on_resource, "fetch", "missing", url, path)
            raise FileNotFoundError(f"Local resource file not found: {path}")
        if delegate is None:
            from weasyprint.urls import URLFetcher
            delegate = URLFetcher()
        try:
            # Forward canonical local URLs so the guard and fetcher address the
            # same decoded path. Fragments do not identify another file.
            result = delegate(path.as_uri() if path is not None else url, *args, **kwargs)
        except Exception:
            _emit(on_resource, "fetch", "failed", url, path)
            raise
        status = ("resolved" if path is not None else
                  "embedded" if url.lower().startswith("data:") else "remote")
        _emit(on_resource, "fetch", status, url, path)
        return result

    # WeasyPrint 70 consults this attribute when a custom fetcher raises. Keep
    # ordinary fetch failures non-fatal here and reject recorded local-policy
    # violations after rendering, because some resource consumers intentionally
    # recover from a failed image/font. The renderer's explicit-context path
    # never writes the resulting bytes before that final policy check.
    guarded_fetcher._fail_on_errors = False
    return guarded_fetcher
