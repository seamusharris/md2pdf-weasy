"""Smoke tests — render the sample doc with each bundled theme.

These catch "did I break the bundle" type regressions: theme files
loading correctly, fonts resolving, the rendering pipeline completing
without exception. They don't verify visual fidelity — that needs the
human eye.
"""

from pathlib import Path

import pytest

from pdf.render import build_pdf, parse_front_matter

SAMPLE_MD = Path(__file__).parent / "sample.md"


@pytest.fixture
def sample_with_theme(tmp_path):
    """Returns a callable that writes sample.md with a given theme into tmp_path."""
    def _make(theme):
        original = SAMPLE_MD.read_text(encoding="utf-8")
        metadata, body = parse_front_matter(original)
        metadata['theme'] = theme
        # Reconstruct the doc with the theme set
        import yaml
        front = yaml.safe_dump(metadata, default_flow_style=False, sort_keys=False)
        path = tmp_path / f"sample-{theme}.md"
        path.write_text(f"---\n{front}---\n\n{body}\n", encoding="utf-8")
        return path
    return _make


def _is_valid_pdf(path: Path) -> bool:
    """Quick sanity: file exists, starts with PDF magic, has reasonable size."""
    if not path.exists():
        return False
    if path.stat().st_size < 1024:
        return False
    with open(path, "rb") as f:
        magic = f.read(5)
    return magic == b"%PDF-"


@pytest.mark.parametrize("theme", ["alpine", "wnc", "regrading", "neutral", "compact"])
def test_render_with_theme(sample_with_theme, tmp_path, theme):
    md_path = sample_with_theme(theme)
    pdf_path = tmp_path / f"out-{theme}.pdf"
    build_pdf(str(md_path), str(pdf_path))
    assert _is_valid_pdf(pdf_path), f"theme '{theme}' did not produce a valid PDF"


def test_render_without_theme_uses_bundled_defaults(tmp_path):
    """Sanity: a document with no theme: front matter still renders."""
    md_path = tmp_path / "no-theme.md"
    md_path.write_text(
        "---\ntitle: No theme\n---\n\n# Heading\n\nBody text.\n",
        encoding="utf-8",
    )
    pdf_path = tmp_path / "no-theme.pdf"
    build_pdf(str(md_path), str(pdf_path))
    assert _is_valid_pdf(pdf_path)


def test_render_features_in_sample(tmp_path):
    """Render the sample doc with the default theme; confirms callouts,
    tables, task lists, page-break markers, and typography all process
    without crashing."""
    pdf_path = tmp_path / "sample-default.pdf"
    build_pdf(str(SAMPLE_MD), str(pdf_path))
    assert _is_valid_pdf(pdf_path)
    # Should have at least 2 pages because of the explicit page-break marker
    # (file size is a rough proxy — > 5KB suggests multiple pages with content)
    assert pdf_path.stat().st_size > 5000
