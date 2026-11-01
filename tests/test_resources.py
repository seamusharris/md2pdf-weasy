"""Explicit resource contexts and the actual nested-fetch access boundary."""
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from pdf.resources import (
    ResourceAccessError, ResourceContext, ResourceEvent, make_url_fetcher,
)


@pytest.fixture
def resource_tree(tmp_path):
    root = tmp_path / "allowed"
    base = root / "document"
    base.mkdir(parents=True)
    outside = tmp_path / "outside.txt"
    outside.write_text("outside document contents", encoding="utf-8")
    return root, base, outside


@pytest.mark.parametrize("as_uri", [False, True])
def test_context_normalizes_absolute_directory(tmp_path, as_uri):
    directory = tmp_path / "spaces café 100%"
    directory.mkdir()
    value = directory.as_uri() if as_uri else str(directory)
    context = ResourceContext(value)
    assert context.base_dir == directory.resolve()
    assert context.base_url == directory.as_uri() + "/"
    with pytest.raises(FrozenInstanceError):
        context.base_dir = tmp_path


@pytest.mark.parametrize("value", [
    ".", "relative/path", "file:relative/path", "https://example.test/docs/",
    "file://remote.test/tmp/", "file://user@localhost/tmp/",
    "file://localhost:22/tmp/", "file:///tmp/?query", "file:///tmp/#fragment",
])
def test_context_rejects_ambiguous_or_nonlocal_bases(value):
    with pytest.raises(ResourceAccessError):
        ResourceContext(value)


def test_context_rejects_nonexistent_directory_and_file(tmp_path):
    regular_file = tmp_path / "file"
    regular_file.touch()
    for value in (tmp_path / "missing", regular_file):
        with pytest.raises(ResourceAccessError):
            ResourceContext(value)


def test_context_accepts_localhost_file_uri(tmp_path):
    context = ResourceContext(tmp_path.as_uri().replace("file:///", "file://localhost/"))
    assert context.base_dir == tmp_path.resolve()


def test_allowed_root_is_absolute_existing_directory_containing_base(resource_tree):
    root, base, outside = resource_tree
    for invalid in ("relative", root / "missing", outside, outside.parent / "other"):
        with pytest.raises(ResourceAccessError):
            ResourceContext(base, invalid)
    sibling = root / "sibling"
    sibling.mkdir()
    with pytest.raises(ResourceAccessError, match="outside allowed_root"):
        ResourceContext(base, sibling)


@pytest.mark.parametrize("kind", ["include", "image", "style"])
def test_relative_resolution_ignores_cwd(resource_tree, monkeypatch, tmp_path, kind):
    root, base, _ = resource_tree
    context = ResourceContext(base, root)
    name = "shared café.yml"
    target = base / name
    target.touch()
    other = tmp_path / "cwd"
    other.mkdir()
    (other / name).write_text("wrong file", encoding="utf-8")
    monkeypatch.chdir(other)
    assert context.resolve_path("shared%20caf%C3%A9.yml", kind=kind) == target


def test_literal_path_and_url_escaping_are_distinct(tmp_path):
    context = ResourceContext(tmp_path)
    for name in ("a b.svg", "café.svg", "100%.svg", "literal%20.svg", "hash#mark.svg"):
        target = tmp_path / name
        target.touch()
        assert context.resolve_path(target) == target
        assert context.resolve_path(target.as_uri()) == target
        assert context.resolve_url(target) == target.as_uri()
    assert context.resolve_path("literal%2520.svg") == tmp_path / "literal%20.svg"
    assert context.resolve_path("100%.svg") == tmp_path / "100%.svg"
    assert context.resolve_url("a%20b.svg#part") == (tmp_path / "a b.svg").as_uri() + "#part"


def test_absolute_references_do_not_change_base(resource_tree):
    root, base, _ = resource_tree
    absolute = root / "separate.png"
    absolute.touch()
    context = ResourceContext(base, root)
    assert context.resolve_path(str(absolute)) == absolute
    assert context.resolve_path(absolute.as_uri()) == absolute


@pytest.mark.parametrize("reference_kind", ["dotdot", "encoded", "absolute", "uri", "symlink"])
def test_allowed_root_blocks_all_local_escape_forms(resource_tree, reference_kind):
    root, base, outside = resource_tree
    link = base / "link.txt"
    link.symlink_to(outside)
    references = {
        "dotdot": "../../outside.txt",
        "encoded": "%2e%2e/%2e%2e/outside.txt",
        "absolute": str(outside),
        "uri": outside.as_uri(),
        "symlink": "link.txt",
    }
    context = ResourceContext(base, root)
    events = []
    reference = references[reference_kind]
    with pytest.raises(ResourceAccessError) as caught:
        context.resolve_path(reference, kind="include", on_resource=events.append)
    assert caught.value.reference == reference
    assert caught.value.kind == "include"
    assert events == [ResourceEvent("include", "blocked", reference)]
    assert outside.read_text() not in str(events)


def test_symlinked_base_and_root_use_real_paths(resource_tree):
    root, base, outside = resource_tree
    alias = outside.parent / "alias"
    alias.symlink_to(root, target_is_directory=True)
    context = ResourceContext(alias / "document", alias)
    assert context.base_dir == base
    assert context.allowed_root == root
    inside_link = base / "inside"
    inside_link.symlink_to(root, target_is_directory=True)
    assert context.resolve_path("inside/document/file.txt") == base / "file.txt"


def test_without_root_explicit_outside_paths_are_allowed(resource_tree):
    _, base, outside = resource_tree
    assert ResourceContext(base).resolve_path("../../outside.txt") == outside


@pytest.mark.parametrize("reference", [
    "file://other-host/tmp/private", "file:relative", "bad%00path", "bad%FFpath",
])
def test_invalid_local_references_are_rejected(tmp_path, reference):
    with pytest.raises(ResourceAccessError):
        ResourceContext(tmp_path).resolve_path(reference)


def test_resolution_reports_missing_and_safe_remote_metadata(tmp_path):
    context = ResourceContext(tmp_path)
    events = []
    missing = context.resolve_path("missing.svg", kind="image", on_resource=events.append)
    assert missing == tmp_path / "missing.svg"
    assert events[-1].to_dict() == {
        "kind": "image", "status": "missing", "reference": "missing.svg",
        "path": str(missing),
    }
    references = (
        "https://user:secret@example.test/a.svg?private=data#fragment",
        "data:image/svg+xml,private document contents",
        "//user:secret@example.test/remote.svg?private=data#fragment",
    )
    for reference in references:
        assert context.resolve_url(reference, on_resource=events.append) == reference
    assert events[-3].reference == "https://example.test/a.svg"
    assert events[-2] == ResourceEvent("resource", "embedded", "data:[redacted]")
    assert events[-1].reference == "//example.test/remote.svg"
    assert events[-1].status == "remote"
    assert "secret" not in str(events)
    assert "private document contents" not in str(events)


def test_resource_event_sanitizes_every_construction_path():
    assert ResourceEvent(
        "image", "remote",
        "https://user:secret@example.test/a.svg?token=private#contents",
    ).reference == "https://example.test/a.svg"
    assert ResourceEvent(
        "image", "embedded", "data:text/plain,private document contents",
    ).reference == "data:[redacted]"


def test_fetcher_checks_real_path_before_delegating(resource_tree):
    root, base, outside = resource_tree
    calls, events = [], []
    fetch = make_url_fetcher(ResourceContext(base, root),
                             fetcher=lambda url: calls.append(url), on_resource=events.append)
    with pytest.raises(ResourceAccessError):
        fetch(outside.as_uri())
    with pytest.raises(FileNotFoundError):
        fetch((base / "missing.svg").as_uri())
    assert calls == []
    assert [event.status for event in events] == ["blocked", "missing"]


def test_fetcher_forwards_arguments_and_canonical_url(tmp_path):
    target = tmp_path / "100% café.txt"
    target.touch()
    calls, events = [], []
    result = {"string": b"resource"}

    def delegate(url, *args, **kwargs):
        calls.append((url, args, kwargs))
        return result

    fetch = make_url_fetcher(ResourceContext(tmp_path), fetcher=delegate,
                             on_resource=events.append)
    assert fetch(target.as_uri() + "#part", 42, timeout=5) is result
    assert calls == [(target.as_uri(), (42,), {"timeout": 5})]
    assert events[0].status == "resolved"


def test_fetcher_preserves_remote_data_policy_without_prefetch(tmp_path):
    calls, events = [], []
    fetch = make_url_fetcher(ResourceContext(tmp_path),
                             fetcher=lambda url: calls.append(url) or {"string": b""},
                             on_resource=events.append)
    assert calls == []
    for url in ("https://example.test/image.png", "data:text/plain,private contents"):
        fetch(url)
    assert calls == ["https://example.test/image.png", "data:text/plain,private contents"]
    assert [event.status for event in events] == ["remote", "embedded"]
    assert "private contents" not in str(events)


def test_fetcher_records_failure_without_exception_or_file_contents(tmp_path):
    events = []

    def fail(url):
        raise RuntimeError("private document contents")

    fetch = make_url_fetcher(ResourceContext(tmp_path), fetcher=fail, on_resource=events.append)
    with pytest.raises(RuntimeError):
        fetch("https://example.test/image.svg")
    assert [event.status for event in events] == ["failed"]
    assert "private document contents" not in str(events)


def test_fetcher_only_exempts_packaged_styles_and_fonts(resource_tree):
    import pdf.resources as resources

    root, base, _ = resource_tree
    context = ResourceContext(base, root)
    fetch = make_url_fetcher(context, fetcher=lambda url: {"redirected_url": url})
    package = Path(resources.__file__).resolve().parent
    for path in (package / "styles/style.css", package / "fonts/AntSerif-Regular.ttf"):
        assert fetch(path.as_uri())["redirected_url"] == path.as_uri()
        with pytest.raises(ResourceAccessError):
            context.resolve_path(path)
    with pytest.raises(ResourceAccessError):
        fetch((package / "resources.py").as_uri())


def test_packaged_exception_cannot_follow_escaping_symlink(resource_tree, monkeypatch):
    import pdf.resources as resources

    root, base, outside = resource_tree
    trusted = outside.parent / "packaged-styles"
    trusted.mkdir()
    (trusted / "escape.css").symlink_to(outside)
    monkeypatch.setattr(resources, "_TRUSTED_PACKAGE_ROOTS", (trusted,))
    fetch = make_url_fetcher(ResourceContext(base, root), fetcher=lambda url: pytest.fail("fetched"))
    with pytest.raises(ResourceAccessError):
        fetch((trusted / "escape.css").as_uri())


def test_default_fetcher_reads_local_file_lazily(tmp_path):
    target = tmp_path / "café 100%.txt"
    target.write_bytes(b"local resource")
    result = make_url_fetcher(ResourceContext(tmp_path))(target.as_uri())
    # WeasyPrint 70 returns a response object; older supported releases used
    # a dictionary. Preserve the delegate response rather than translating it.
    stream = result["file_obj"] if isinstance(result, dict) else result
    try:
        assert stream.read() == b"local resource"
    finally:
        stream.close()


@pytest.mark.parametrize("kind", ["import", "background", "font", "svg"])
def test_actual_weasyprint_nested_fetches_cannot_escape(resource_tree, kind):
    from weasyprint import CSS, HTML
    from weasyprint.text.fonts import FontConfiguration

    root, base, outside = resource_tree
    events = []
    fetch = make_url_fetcher(ResourceContext(base, root), on_resource=events.append)
    url = outside.as_uri()
    css = ""
    body = "<p>Resource boundary</p>"
    if kind == "import":
        css = f'@import url("{url}");'
    elif kind == "background":
        css = f'p {{ background-image: url("{url}"); }}'
    elif kind == "font":
        css = f'@font-face {{font-family: Escape; src: url("{url}");}} p {{font-family: Escape;}}'
    else:
        svg = base / "nested.svg"
        svg.write_text(
            '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20">'
            f'<image href="{url}" width="20" height="20"/></svg>', encoding="utf-8",
        )
        body = '<img src="nested.svg">'
    font_config = FontConfiguration()
    HTML(string=body, base_url=base.as_uri() + "/", url_fetcher=fetch).write_pdf(
        stylesheets=[CSS(string=css, base_url=base.as_uri() + "/", url_fetcher=fetch,
                         font_config=font_config)], font_config=font_config,
    )
    denied = [event for event in events if event.status == "blocked"]
    assert any(event.reference == url for event in denied), events
    assert outside.read_text() not in str(events)
