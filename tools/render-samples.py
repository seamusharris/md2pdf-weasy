#!/usr/bin/env python3
"""Render tests/sample.md with each bundled theme into samples/ for visual
review.

Smoke tests confirm the pipeline doesn't crash; this script produces
inspectable PDFs so a human can confirm typography, palette, spacing, and
layout look right after a change.

Run:
    python tools/render-samples.py

Output:
    samples/sample-alpine.pdf
    samples/sample-wnc.pdf
    samples/sample-regrading.pdf
    samples/sample-neutral.pdf
    samples/sample-compact.pdf
    samples/sample-default.pdf    (no theme: front matter, bundled defaults)

The samples/ directory is gitignored. Re-run after any change you want to
visually verify; nothing is committed.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from pdf.render import build_pdf, parse_front_matter

ROOT = Path(__file__).resolve().parent.parent
SAMPLE_MD = ROOT / "tests" / "sample.md"
OUTPUT_DIR = ROOT / "samples"

THEMES = ["alpine", "wnc", "regrading", "neutral", "compact", None]


def render_with_theme(theme: str | None) -> Path:
    """Generate sample-<theme>.pdf in the samples directory."""
    name = theme or "default"

    text = SAMPLE_MD.read_text(encoding="utf-8")
    metadata, body = parse_front_matter(text)
    if theme:
        metadata["theme"] = theme
    else:
        metadata.pop("theme", None)

    front = yaml.safe_dump(metadata, default_flow_style=False, sort_keys=False)
    intermediate_md = OUTPUT_DIR / f"sample-{name}.md"
    intermediate_md.write_text(f"---\n{front}---\n\n{body}\n", encoding="utf-8")

    pdf_path = OUTPUT_DIR / f"sample-{name}.pdf"
    build_pdf(str(intermediate_md), str(pdf_path))

    intermediate_md.unlink()   # don't leave intermediate markdown around
    return pdf_path


def main() -> None:
    OUTPUT_DIR.mkdir(exist_ok=True)
    rendered = []
    for theme in THEMES:
        path = render_with_theme(theme)
        rendered.append(path.name)
    print(f"\nRendered {len(rendered)} samples in {OUTPUT_DIR.relative_to(ROOT)}/")
    for name in rendered:
        print(f"  • {name}")


if __name__ == "__main__":
    main()
