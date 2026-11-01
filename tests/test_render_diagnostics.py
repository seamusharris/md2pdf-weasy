"""Integration contracts for diagnostics and explicit resource contexts."""

from __future__ import annotations

import inspect
import json
import sys
from pathlib import Path

import pytest
import yaml

import pdf
from pdf import render
from pdf.diagnostics import (
    BuildResult,
    DiagnosticsReport,
    StrictDiagnosticsError,
)
from pdf.resources import ResourceAccessError, ResourceContext


_TABLE = """| Team | W |
|---|---:|
| North | 8 |
"""


class _Document:
    def __init__(self, payload=b"%PDF-fake"):
        self.payload = payload

    def write_pdf(self, output_path=None, *, pdf_variant=None):
        assert pdf_variant == "pdf/ua-1"
        if output_path is None:
            return self.payload
        Path(output_path).write_bytes(self.payload)


def _ambiguous_markdown(*, sentinel="North"):
    metadata = {
        "tables": {
            "club": {"columns": [
                {"name": "Team", "width": 3},
                {"name": "W", "width": 1},
            ]},
            "tracking": {"columns": [
                {"name": "Team", "width": 1},
                {"name": "W", "width": 1},
            ]},
        },
    }
    return f"---\n{yaml.safe_dump(metadata)}---\n" + _TABLE.replace("North", sentinel)


def test_new_apis_are_additive_and_legacy_signatures_remain_exact():
    assert list(inspect.signature(render.build_pdf).parameters) == [
        "md_path", "output_path", "style_path", "base_style_path", "base_url",
    ]
    assert list(inspect.signature(render.md_to_html).parameters) == [
        "md_content", "metadata",
    ]
    assert pdf.build_pdf_with_result is render.build_pdf_with_result
    assert pdf.build_pdf_from_markdown is render.build_pdf_from_markdown
    assert pdf.ResourceContext is ResourceContext


def test_result_api_observes_actual_layout_without_exposing_body(tmp_path, monkeypatch):
    sentinel = "PRIVATE_BODY_71259"
    source = tmp_path / "report.md"
    output = tmp_path / "report.pdf"
    source.write_text(_ambiguous_markdown(sentinel=sentinel), encoding="utf-8")
    monkeypatch.setattr(render, "_render_document", lambda prepared: _Document())

    result = render.build_pdf_with_result(str(source), str(output))

    assert isinstance(result, BuildResult)
    assert result.output_path == str(output)
    assert output.read_bytes() == b"%PDF-fake"
    table = result.diagnostics["tables"][0]
    assert table["origin"] == "declared"
    assert table["layout_key"] == "club"
    assert table["matching_layout_keys"] == ["club", "tracking"]
    assert "tables.match_ambiguous" in {
        item["code"] for item in result.diagnostics["diagnostics"]
    }
    assert sentinel not in json.dumps(result.diagnostics, allow_nan=False)


def test_legacy_result_diagnostics_redact_embedded_and_remote_image_secrets(
    tmp_path, monkeypatch,
):
    source = tmp_path / "report.md"
    output = tmp_path / "report.pdf"
    source.write_text(
        '<img src="data:text/plain,PRIVATE_BODY_71259">\n'
        '<img src="https://user:secret@example.test/a.svg?token=PRIVATE#body">',
        encoding="utf-8",
    )
    monkeypatch.setattr(render, "_render_document", lambda prepared: _Document())

    result = render.build_pdf_with_result(str(source), str(output))

    encoded = json.dumps(result.diagnostics, allow_nan=False)
    assert "PRIVATE_BODY_71259" not in encoded
    assert "user:secret" not in encoded
    assert "token=PRIVATE" not in encoded
    references = {
        item["reference"] for item in result.diagnostics["resources"]
        if item["kind"] == "image"
    }
    assert references == {
        "data:[redacted]", "https://example.test/a.svg",
    }


def test_selected_strict_code_preserves_existing_output_and_carries_report(
    tmp_path, monkeypatch,
):
    source = tmp_path / "report.md"
    output = tmp_path / "report.pdf"
    source.write_text(_ambiguous_markdown(), encoding="utf-8")
    output.write_bytes(b"existing")
    monkeypatch.setattr(
        render,
        "_render_document",
        lambda prepared: pytest.fail("strict validation must run before rendering"),
    )

    with pytest.raises(StrictDiagnosticsError) as caught:
        render.build_pdf_with_result(
            str(source), str(output),
            strict_codes={"tables.match_ambiguous"},
        )

    assert output.read_bytes() == b"existing"
    assert caught.value.codes == ("tables.match_ambiguous",)
    assert caught.value.report["tables"][0]["layout_key"] == "club"


def _bundle(tmp_path):
    bundle = tmp_path / "bundle with spaces"
    bundle.mkdir()
    (bundle / "tables.yml").write_text(yaml.safe_dump({
        "shared": {"columns": [
            {"name": "Team", "width": 4},
            {"name": "W", "width": 1},
        ]},
    }), encoding="utf-8")
    (bundle / "overlay.css").write_text(
        "body { color: #123456; background-image: url('pixel.png'); }",
        encoding="utf-8",
    )
    (bundle / "pixel.png").write_bytes(b"fixture")
    (bundle / "wnc.css").write_text("body { --context-theme: yes; }", encoding="utf-8")
    source = bundle / "report.md"
    source.write_text(
        "---\ntables_include: tables.yml\ntheme: wnc\n---\n"
        "![Pixel](pixel.png)\n\n" + _TABLE,
        encoding="utf-8",
    )
    return bundle, source


def test_explicit_context_ignores_conflicting_cwd_and_preserves_css_bases(
    tmp_path, monkeypatch,
):
    bundle, source = _bundle(tmp_path)
    context = ResourceContext(bundle, bundle)
    results = []

    for name in ("cwd-a", "cwd-b"):
        cwd = tmp_path / name
        cwd.mkdir()
        (cwd / "tables.yml").write_text("wrong: {}", encoding="utf-8")
        (cwd / "overlay.css").write_text("body { color: red; }", encoding="utf-8")
        (cwd / "wnc.css").write_text("body { --wrong: yes; }", encoding="utf-8")
        monkeypatch.chdir(cwd)
        captured = {}

        def fake_render(prepared):
            captured["prepared"] = prepared
            return _Document()

        monkeypatch.setattr(render, "_render_document", fake_render)
        output = tmp_path / f"{name}.pdf"
        result = render.build_pdf_with_result(
            str(source), str(output), style_path="overlay.css",
            resource_context=context,
        )
        results.append((result, captured["prepared"], output.read_bytes()))

    first, second = results
    assert first[2] == second[2]
    assert first[0].diagnostics == second[0].diagnostics
    assert first[0].diagnostics["tables"][0]["layout_source"] == "tables_include"
    assert "--context-theme: yes" in first[1].css
    assert "--wrong" not in first[1].css
    assert len(first[1].style_layers) == 3
    assert first[1].style_layers[0].base_url == Path(render.DEFAULT_STYLE).parent.as_uri() + "/"
    assert first[1].style_layers[1].base_url == bundle.as_uri() + "/"
    assert first[1].style_layers[2].base_url == bundle.as_uri() + "/"
    assert first[1].html_base_url == bundle.as_uri() + "/"


def test_explicit_context_real_render_is_identical_across_conflicting_cwds(
    tmp_path, monkeypatch,
):
    bundle = tmp_path / "portable bundle"
    bundle.mkdir()
    (bundle / "tables.yml").write_text(yaml.safe_dump({
        "shared": {"columns": [
            {"name": "Team", "width": 4},
            {"name": "W", "width": 1},
        ]},
    }), encoding="utf-8")
    (bundle / "mark.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24">'
        '<rect width="24" height="24" fill="#123456"/></svg>',
        encoding="utf-8",
    )
    (bundle / "overlay.css").write_text(
        "table { border-top: 2px solid #123456; }",
        encoding="utf-8",
    )
    (bundle / "wnc.css").write_text(
        "h1 { color: #123456; }",
        encoding="utf-8",
    )
    source = bundle / "report.md"
    source.write_text(
        "---\ntables_include: tables.yml\ntheme: wnc\n---\n"
        "# Context check\n\n![Mark](mark.svg)\n\n" + _TABLE,
        encoding="utf-8",
    )
    context = ResourceContext(bundle, bundle)
    rendered = []

    for name in ("unrelated-a", "unrelated-b"):
        cwd = tmp_path / name
        cwd.mkdir()
        (cwd / "tables.yml").write_text("wrong: {}", encoding="utf-8")
        (cwd / "mark.svg").write_text("not an svg", encoding="utf-8")
        (cwd / "overlay.css").write_text("body { color: red; }", encoding="utf-8")
        (cwd / "wnc.css").write_text("body { display: none; }", encoding="utf-8")
        monkeypatch.chdir(cwd)
        output = tmp_path / f"{name}.pdf"
        render.build_pdf_with_result(
            str(source), str(output), style_path="overlay.css",
            resource_context=context,
        )
        rendered.append(output.read_bytes())

    assert rendered[0] == rendered[1]


def test_source_text_uses_context_for_include_image_and_style(tmp_path, monkeypatch):
    bundle, source = _bundle(tmp_path)
    content = source.read_text(encoding="utf-8")
    output = tmp_path / "memory.pdf"
    monkeypatch.setattr(render, "_render_document", lambda prepared: _Document())

    result = render.build_pdf_from_markdown(
        content,
        str(output),
        resource_context=ResourceContext(bundle, bundle),
        style_path="overlay.css",
    )

    assert output.read_bytes() == b"%PDF-fake"
    kinds = {item["kind"] for item in result.diagnostics["resources"]}
    assert {"tables_include", "image", "style", "theme", "base_style"} <= kinds


def test_context_and_base_url_are_mutually_exclusive(tmp_path):
    source = tmp_path / "report.md"
    source.write_text("# Report", encoding="utf-8")
    with pytest.raises(ValueError, match="cannot be used together"):
        render.build_pdf_with_result(
            str(source),
            base_url=tmp_path.as_uri() + "/",
            resource_context=ResourceContext(tmp_path),
        )


def test_missing_image_remains_fatal_and_exposes_resolution_report(tmp_path, monkeypatch):
    source = tmp_path / "report.md"
    source.write_text("![Missing](missing.png)", encoding="utf-8")
    monkeypatch.setattr(
        render,
        "_render_document",
        lambda prepared: pytest.fail("missing image must fail before rendering"),
    )

    with pytest.raises(FileNotFoundError) as caught:
        render.build_pdf_with_result(
            str(source),
            resource_context=ResourceContext(tmp_path, tmp_path),
        )

    assert any(
        item["kind"] == "image" and item["status"] == "missing"
        for item in caught.value.diagnostics["resources"]
    )


def test_explicit_style_cannot_escape_allowed_root(tmp_path):
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    source = bundle / "report.md"
    source.write_text("# Report", encoding="utf-8")
    outside = tmp_path / "outside.css"
    outside.write_text("body {}", encoding="utf-8")

    with pytest.raises(ResourceAccessError):
        render.build_pdf_with_result(
            str(source),
            style_path=str(outside),
            resource_context=ResourceContext(bundle, bundle),
        )


def test_explicit_renderer_loads_packaged_fonts_through_guarded_fetcher(tmp_path):
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    output = tmp_path / "font-check.pdf"

    result = render.build_pdf_from_markdown(
        "# Packaged font check\n\nBody text.",
        str(output),
        resource_context=ResourceContext(bundle, bundle),
    )

    assert output.read_bytes().startswith(b"%PDF-")
    assert any(
        item["kind"] == "fetch"
        and item["status"] == "resolved"
        and "/pdf/fonts/" in (item.get("path") or "")
        for item in result.diagnostics["resources"]
    )


def test_nested_css_escape_is_rejected_before_pdf_is_written(tmp_path):
    allowed = tmp_path / "allowed"
    bundle = allowed / "bundle"
    bundle.mkdir(parents=True)
    outside = tmp_path / "outside.png"
    outside.write_bytes(b"not read")
    (bundle / "overlay.css").write_text(
        'body { background-image: url("../../outside.png"); }',
        encoding="utf-8",
    )
    output = tmp_path / "blocked.pdf"

    with pytest.raises(ResourceAccessError) as caught:
        render.build_pdf_from_markdown(
            "# Blocked nested resource",
            str(output),
            resource_context=ResourceContext(bundle, allowed),
            style_path="overlay.css",
        )

    assert not output.exists()
    assert any(
        item["kind"] == "fetch" and item["status"] == "blocked"
        for item in caught.value.diagnostics["resources"]
    )


def test_cli_writes_json_sidecar_without_mixing_created_output(tmp_path, monkeypatch, capsys):
    source = tmp_path / "report.md"
    output = tmp_path / "report.pdf"
    sidecar = tmp_path / "report.json"
    source.write_text(_TABLE, encoding="utf-8")
    monkeypatch.setattr(render, "_render_document", lambda prepared: _Document())
    monkeypatch.setattr(sys, "argv", [
        "md2pdf", str(source), str(output),
        "--diagnostics-json", str(sidecar),
    ])

    render.main()

    stdout = capsys.readouterr().out
    assert stdout == f"Created: {output}\n"
    payload = json.loads(sidecar.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
    assert payload["tables"][0]["origin"] == "automatic"


def test_cli_strict_failure_writes_json_but_no_pdf(tmp_path, monkeypatch):
    source = tmp_path / "report.md"
    output = tmp_path / "report.pdf"
    sidecar = tmp_path / "strict.json"
    source.write_text(_ambiguous_markdown(), encoding="utf-8")
    monkeypatch.setattr(
        render,
        "_render_document",
        lambda prepared: pytest.fail("strict validation must precede rendering"),
    )
    monkeypatch.setattr(sys, "argv", [
        "md2pdf", str(source), str(output),
        "--strict-code", "tables.match_ambiguous",
        "--diagnostics-json", str(sidecar),
    ])

    with pytest.raises(StrictDiagnosticsError):
        render.main()

    assert not output.exists()
    assert "tables.match_ambiguous" in {
        item["code"] for item in json.loads(sidecar.read_text())["diagnostics"]
    }


def test_cli_selected_invalid_include_writes_json_and_preserves_yaml_cause(
    tmp_path, monkeypatch,
):
    source = tmp_path / "report.md"
    output = tmp_path / "report.pdf"
    sidecar = tmp_path / "strict.json"
    include = tmp_path / "broken.yml"
    include.write_text("broken: [\n", encoding="utf-8")
    source.write_text(
        "---\ntables_include: broken.yml\n---\n" + _TABLE,
        encoding="utf-8",
    )
    monkeypatch.setattr(sys, "argv", [
        "md2pdf", str(source), str(output),
        "--strict-code", "tables.include_invalid",
        "--diagnostics-json", str(sidecar),
    ])

    with pytest.raises(StrictDiagnosticsError) as caught:
        render.main()

    assert isinstance(caught.value.__cause__, yaml.YAMLError)
    assert not output.exists()
    assert "tables.include_invalid" in {
        item["code"] for item in json.loads(sidecar.read_text())["diagnostics"]
    }


@pytest.mark.parametrize("target", ["input", "output"])
def test_cli_rejects_sidecar_overwrite_before_build(tmp_path, monkeypatch, target):
    source = tmp_path / "report.md"
    output = tmp_path / "report.pdf"
    source.write_text(_TABLE, encoding="utf-8")
    sidecar = source if target == "input" else output
    monkeypatch.setattr(sys, "argv", [
        "md2pdf", str(source), str(output),
        "--diagnostics-json", str(sidecar),
    ])
    monkeypatch.setattr(
        render,
        "build_pdf_with_result",
        lambda *args, **kwargs: pytest.fail("must reject before building"),
    )

    with pytest.raises(SystemExit) as caught:
        render.main()

    assert caught.value.code == 2
    assert source.exists()
    assert not output.exists()


@pytest.mark.parametrize("target", ["input", "output"])
def test_cli_rejects_existing_hardlink_sidecar_alias(tmp_path, monkeypatch, target):
    source = tmp_path / "report.md"
    output = tmp_path / "report.pdf"
    source.write_text(_TABLE, encoding="utf-8")
    if target == "output":
        output.write_bytes(b"existing pdf")
    protected = source if target == "input" else output
    sidecar = tmp_path / "alias.json"
    sidecar.hardlink_to(protected)
    monkeypatch.setattr(sys, "argv", [
        "md2pdf", str(source), str(output),
        "--diagnostics-json", str(sidecar),
    ])
    monkeypatch.setattr(
        render,
        "build_pdf_with_result",
        lambda *args, **kwargs: pytest.fail("must reject before building"),
    )

    with pytest.raises(SystemExit) as caught:
        render.main()

    assert caught.value.code == 2
    assert protected.read_bytes() == (
        _TABLE.encode("utf-8") if target == "input" else b"existing pdf"
    )


def test_cli_rejects_new_pdf_options_for_html_and_json_batch(tmp_path, monkeypatch):
    first = tmp_path / "first.md"
    second = tmp_path / "second.md"
    first.write_text("# First", encoding="utf-8")
    second.write_text("# Second", encoding="utf-8")
    monkeypatch.setattr(sys, "argv", [
        "md2pdf", str(first), "--html", "--strict",
    ])
    with pytest.raises(SystemExit) as html_error:
        render.main()
    assert html_error.value.code == 2

    monkeypatch.setattr(sys, "argv", [
        "md2pdf", str(first), str(second),
        "--diagnostics-json", str(tmp_path / "batch.json"),
    ])
    with pytest.raises(SystemExit) as batch_error:
        render.main()
    assert batch_error.value.code == 2
