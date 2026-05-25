#!/usr/bin/env python3
"""Render per-theme style-guide PDFs from docs/themes/*.md into samples/.

Each theme has its own style guide in docs/themes/<theme>.md showing the
features specific to that theme (palette swatches, table treatments,
typography decisions). These render to samples/<theme>.pdf for visual
review.

Run:
    python tools/render-samples.py

Output:
    samples/alpine.pdf
    samples/wnc.pdf
    samples/regrading.pdf
    samples/neutral.pdf
    samples/compact.pdf

The samples/ directory is gitignored. Re-run after any change you want to
visually verify; nothing is committed.
"""

from __future__ import annotations

from pathlib import Path

from pdf.render import build_pdf

ROOT = Path(__file__).resolve().parent.parent
THEMES_DIR = ROOT / "docs" / "themes"
OUTPUT_DIR = ROOT / "samples"


def main() -> None:
    OUTPUT_DIR.mkdir(exist_ok=True)
    sources = sorted(THEMES_DIR.glob("*.md"))
    if not sources:
        raise SystemExit(f"No theme style guides found in {THEMES_DIR}")

    for src in sources:
        out = OUTPUT_DIR / f"{src.stem}.pdf"
        build_pdf(str(src), str(out))

    print(f"\nRendered {len(sources)} theme style guides in {OUTPUT_DIR.relative_to(ROOT)}/")
    for src in sources:
        print(f"  • {src.stem}.pdf")


if __name__ == "__main__":
    main()
