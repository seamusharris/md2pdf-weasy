"""Fixture transforms and bounded HTML/PDF/raster artifact generation."""

from __future__ import annotations

import os
from pathlib import Path
import sys
from typing import Any

from PIL import Image, ImageDraw
import yaml

from .model import (
    MAX_IMAGE_BYTES, MAX_PAGES_PER_MODE, MODE_IDS, CompatibilityError,
    sha256_file, validate_image_limits, validate_total_pixels,
)
from .process import run_bounded
from .structure import html_evidence, pdf_evidence


RASTER_DPI = 144


def _front_matter(source: str, updates: dict[str, Any]) -> str:
    if not source.startswith("---\n"):
        raise CompatibilityError("fixture is missing front matter", category="verify", phase="fixture")
    marker = source.find("\n---\n", 4)
    if marker < 0:
        raise CompatibilityError("fixture front matter is unterminated", category="verify", phase="fixture")
    metadata = yaml.safe_load(source[4:marker]) or {}
    if not isinstance(metadata, dict):
        raise CompatibilityError("fixture front matter must be a mapping", category="verify", phase="fixture")
    metadata.update(updates)
    return "---\n" + yaml.safe_dump(metadata, sort_keys=False, allow_unicode=True) + "---\n" + source[marker + 5:]


def source_for_mode(mode: str, source: str) -> str:
    if mode not in MODE_IDS:
        raise CompatibilityError(f"unknown mode: {mode}", category="verify", phase="fixture")
    if mode == "current-legacy":
        return _front_matter(source, {"table_widths": False})
    if mode == "current-explicit":
        return _front_matter(source, {"columns": {"Venue": "12em"}})
    return source


def render(mode: str, source: Path, target: Path, legacy_parent: Path, current_parent: Path) -> dict[str, Any]:
    target.mkdir(mode=0o700)
    env = dict(os.environ)
    env.update({"LC_ALL": "C.UTF-8", "LANG": "C.UTF-8", "TZ": "UTC", "SOURCE_DATE_EPOCH": "0"})
    env["PYTHONPATH"] = str(legacy_parent if mode == "v0.1.0" else current_parent)
    html, pdf = target / "document.html", target / "document.pdf"
    run_bounded((sys.executable, "-m", "pdf", str(source), str(html), "--html"), cwd=target, env=env,
                category="render", phase="render-html", case=mode)
    run_bounded((sys.executable, "-m", "pdf", str(source), str(pdf)), cwd=target, env=env,
                category="render", phase="render-pdf", case=mode)
    html_fact, pdf_fact = html_evidence(html), pdf_evidence(pdf, case=mode)
    prefix = target / "page"
    run_bounded(("pdftoppm", "-png", "-r", str(RASTER_DPI), str(pdf), str(prefix)), cwd=target,
                category="raster", phase="raster", case=mode)
    images = sorted(target.glob("page-*.png"))
    if len(images) != pdf_fact["pages"] or len(images) > MAX_PAGES_PER_MODE:
        raise CompatibilityError("raster page set is incomplete", category="raster", phase="raster", case=mode)
    pixels, raster = 0, []
    for image_path in images:
        image_bytes = image_path.stat().st_size
        try:
            with Image.open(image_path) as image:
                image.verify()
            with Image.open(image_path) as image:
                width, height = image.size
        except (OSError, Image.DecompressionBombError) as exc:
            raise CompatibilityError(
                "raster image is invalid", category="raster", phase="image-preflight", case=mode,
            ) from exc
        pixels += validate_image_limits(image_bytes, width, height)
        raster.append({"path": str(image_path.relative_to(target.parent.parent)), "width": width, "height": height,
                       "sha256": sha256_file(image_path, limit=MAX_IMAGE_BYTES)})
    return {"id": mode, "html": html_fact, "pdf": pdf_fact, "rasters": raster, "decoded_pixels": pixels}


def contact_sheet(candidate: Path, cases: list[dict[str, Any]]) -> dict[str, Any]:
    pages = [(case["id"], path) for case in cases
             for path in sorted((candidate / "artifacts" / case["id"]).glob("page-*.png"))]
    if not pages:
        raise CompatibilityError("no raster pages for contact sheet", category="raster", phase="contact-sheet")
    validate_total_pixels(sum(case["decoded_pixels"] for case in cases))
    thumb_width, label_height, gap = 300, 28, 12
    thumbs = []
    for label, path in pages:
        with Image.open(path) as original:
            ratio = thumb_width / original.width
            thumbs.append((label, original.convert("RGB").resize((thumb_width, max(1, round(original.height * ratio))))))
    columns = min(5, len(thumbs))
    rows = (len(thumbs) + columns - 1) // columns
    cell_height = max(image.height for _, image in thumbs) + label_height
    sheet = Image.new("RGB", (columns * (thumb_width + gap) + gap, rows * (cell_height + gap) + gap), "white")
    draw = ImageDraw.Draw(sheet)
    for index, (label, thumb) in enumerate(thumbs):
        x, y = gap + (index % columns) * (thumb_width + gap), gap + (index // columns) * (cell_height + gap)
        draw.text((x, y), label, fill="black")
        sheet.paste(thumb, (x, y + label_height))
    path = candidate / "contact-sheet.png"
    sheet.save(path, format="PNG", optimize=True)
    if path.stat().st_size > MAX_IMAGE_BYTES:
        raise CompatibilityError("contact sheet exceeds safe size limit", category="raster", phase="contact-sheet")
    return {"path": path.name, "width": sheet.width, "height": sheet.height, "sha256": sha256_file(path)}
