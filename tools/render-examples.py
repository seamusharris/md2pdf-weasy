#!/usr/bin/env python3
"""Render example PDFs for visual review.

Two flavours of example, both under examples/:

  • examples/styleguides/<theme>.md — per-theme style guides showing what
    each theme exposes (palette swatches, table treatments, typography).
  • examples/samples/<name>.md — real-world test documents using a chosen
    theme (data-heavy architecture docs, regrading reports, etc).

Rendered PDFs are written alongside each source markdown file and are
gitignored. Re-run after any change you want to visually verify.

Run:
    python tools/render-examples.py
"""

from __future__ import annotations

from pathlib import Path

from pdf.render import build_pdf

ROOT = Path(__file__).resolve().parent.parent
EXAMPLES_DIR = ROOT / "examples"


def _render_dir(src_dir: Path) -> int:
    sources = sorted(src_dir.glob("*.md"))
    if not sources:
        return 0
    for src in sources:
        build_pdf(str(src), str(src.with_suffix(".pdf")))
    print(f"\nRendered {len(sources)} files in {src_dir.relative_to(ROOT)}/")
    for src in sources:
        print(f"  • {src.stem}.pdf")
    return len(sources)


def main() -> None:
    total = 0
    for sub in sorted(p for p in EXAMPLES_DIR.iterdir() if p.is_dir()):
        total += _render_dir(sub)
    if total == 0:
        raise SystemExit(f"No source markdown found under {EXAMPLES_DIR}/")


if __name__ == "__main__":
    main()
