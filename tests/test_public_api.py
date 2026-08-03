"""Compatibility contracts for the ratified Python and CLI surface."""

from __future__ import annotations

import inspect
from pathlib import Path
import subprocess
import sys
import tomllib

import pytest

import pdf
import pdf.__main__ as module_entry
from pdf import render
from pdf.postprocess import postprocess


def _parameters(function):
    return list(inspect.signature(function).parameters)


def test_public_callable_signatures_and_reexports_are_stable():
    assert _parameters(render.build_pdf) == [
        "md_path", "output_path", "style_path", "base_style_path", "base_url",
    ]
    assert _parameters(render.build_html) == [
        "md_path", "output_path", "style_path", "base_style_path",
    ]
    assert _parameters(render.md_to_html) == ["md_content", "metadata"]
    assert _parameters(render.parse_front_matter) == ["content"]
    assert _parameters(postprocess) == ["html", "metadata"]
    assert pdf.build_pdf is render.build_pdf
    assert pdf.build_html is render.build_html
    assert pdf.md_to_html is render.md_to_html
    assert pdf.parse_front_matter is render.parse_front_matter


def test_builders_keep_default_outputs_and_pdf_only_base_url(tmp_path, monkeypatch):
    markdown = tmp_path / "report.md"
    markdown.write_text("# Contract\n", encoding="utf-8")

    class Document:
        def write_pdf(self, output_path, *, pdf_variant=None):
            Path(output_path).write_bytes(b"pdf")

    monkeypatch.setattr(render, "_render_document", lambda prepared: Document())
    assert render.build_pdf(str(markdown)) == str(markdown.with_suffix(".pdf"))
    assert render.build_html(str(markdown)) == str(markdown.with_suffix(".html"))
    assert "base_url" in inspect.signature(render.build_pdf).parameters
    assert "base_url" not in inspect.signature(render.build_html).parameters


def test_cli_entry_points_share_main_and_exclude_base_url(capsys, monkeypatch):
    metadata = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    assert metadata["project"]["scripts"]["md2pdf"] == "pdf.render:main"
    assert module_entry.main is render.main
    monkeypatch.setattr(sys, "argv", ["md2pdf", "--help"])
    with pytest.raises(SystemExit) as caught:
        render.main()
    assert caught.value.code == 0
    help_text = capsys.readouterr().out
    assert "--html" in help_text
    assert "--base-url" not in help_text


def test_deprecated_tracked_teams_alias_warns_and_new_key_wins(caplog):
    assert render._tracked_rows({"tracked_teams": ["Old"]}) == ["Old"]
    assert any("deprecated" in message for message in caplog.messages)
    caplog.clear()
    assert render._tracked_rows({
        "tracked_rows": ["New"], "tracked_teams": ["Old"],
    }) == ["New"]
    assert caplog.messages == []


@pytest.mark.parametrize("builder", [render.build_pdf, render.build_html])
def test_builders_propagate_missing_input_and_stylesheet(builder, tmp_path):
    missing = tmp_path / "missing.md"
    with pytest.raises(FileNotFoundError):
        builder(str(missing))
    markdown = tmp_path / "source.md"
    markdown.write_text("# Source\n", encoding="utf-8")
    with pytest.raises(FileNotFoundError):
        builder(str(markdown), style_path=str(tmp_path / "missing.css"))


def test_builders_propagate_render_and_output_failures(tmp_path, monkeypatch):
    markdown = tmp_path / "source.md"
    markdown.write_text("# Source\n", encoding="utf-8")
    monkeypatch.setattr(
        render, "_render_document",
        lambda prepared: (_ for _ in ()).throw(RuntimeError("render failed")),
    )
    with pytest.raises(RuntimeError, match="render failed"):
        render.build_pdf(str(markdown))
    with pytest.raises(FileNotFoundError):
        render.build_html(
            str(markdown), str(tmp_path / "missing-parent" / "output.html"),
        )


def test_markdown_conversion_failure_propagates_unchanged(tmp_path, monkeypatch):
    markdown_path = tmp_path / "source.md"
    markdown_path.write_text("# Source\n", encoding="utf-8")
    failure = RuntimeError("markdown failed")

    def fail_markdown(*args, **kwargs):
        raise failure

    monkeypatch.setattr(render.markdown, "markdown", fail_markdown)
    with pytest.raises(RuntimeError, match="markdown failed") as caught:
        render.build_html(str(markdown_path))
    assert caught.value is failure


def test_pdf_write_failure_propagates_unchanged(tmp_path, monkeypatch):
    markdown_path = tmp_path / "source.md"
    markdown_path.write_text("# Source\n", encoding="utf-8")
    failure = OSError("PDF write failed")

    class Document:
        def write_pdf(self, output_path, *, pdf_variant=None):
            raise failure

    monkeypatch.setattr(render, "_render_document", lambda prepared: Document())
    with pytest.raises(OSError, match="PDF write failed") as caught:
        render.build_pdf(str(markdown_path))
    assert caught.value is failure


@pytest.mark.parametrize("content, warning", [
    ("---\ntitle: [unterminated\n---\n# Body\n", "not valid YAML"),
    ("---\n- one\n- two\n---\n# Body\n", "did not parse to a mapping"),
])
def test_invalid_front_matter_warns_and_falls_back(caplog, content, warning):
    assert render.parse_front_matter(content) == ({}, content)
    assert any(warning in message for message in caplog.messages)


def test_mistyped_supported_field_warns_then_propagates_downstream(tmp_path, caplog):
    markdown_path = tmp_path / "source.md"
    markdown_path.write_text(
        "---\ntables_include:\n  - not-a-path\n---\n# Source\n", encoding="utf-8",
    )
    with pytest.raises(TypeError):
        render.build_html(str(markdown_path))
    assert any("tables_include" in message for message in caplog.messages)


def test_cli_batch_stops_at_first_failure_and_keeps_prior_output(
    tmp_path, monkeypatch,
):
    first, failing, later = [tmp_path / name for name in (
        "first.md", "failing.md", "later.md",
    )]
    calls = []

    def build(md_path, output_path=None, **kwargs):
        calls.append(md_path)
        if md_path == str(failing):
            raise FileNotFoundError(md_path)
        Path(md_path).with_suffix(".pdf").write_bytes(b"complete")

    monkeypatch.setattr(render, "build_pdf", build)
    monkeypatch.setattr(sys, "argv", ["md2pdf", str(first), str(failing), str(later)])
    with pytest.raises(FileNotFoundError):
        render.main()
    assert calls == [str(first), str(failing)]
    assert first.with_suffix(".pdf").read_bytes() == b"complete"
    assert not later.with_suffix(".pdf").exists()


def test_both_cli_processes_report_missing_input_consistently(tmp_path):
    missing = tmp_path / "missing.md"
    console = Path(sys.executable).with_name("md2pdf")
    commands = ([str(console), str(missing)], [sys.executable, "-m", "pdf", str(missing)])
    results = [subprocess.run(command, text=True, capture_output=True) for command in commands]
    assert [result.returncode != 0 for result in results] == [True, True]
    assert all(result.stdout == "" for result in results)
    assert all("FileNotFoundError" in result.stderr for result in results)
    assert all(str(missing) in result.stderr for result in results)
