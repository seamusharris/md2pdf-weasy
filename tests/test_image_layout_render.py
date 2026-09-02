"""Real-render geometry checks for the public image-layout contract."""

from pathlib import Path

import pytest
from PIL import Image
from pypdf import PdfReader

from pdf.render import _prepare_render, _render_document


def _walk(box):
    yield box
    for child in getattr(box, "children", ()):
        yield from _walk(child)


def _classes(box) -> set[str]:
    element = getattr(box, "element", None)
    return set(element.get("class", "").split()) if element is not None else set()


def _write_images(root: Path) -> None:
    for number in range(1, 9):
        dimensions = (800, 1200) if number == 8 else (800, 500)
        Image.new("RGB", dimensions, (20 * number, 80, 140)).save(
            root / f"{number}.png"
        )


def test_all_image_layouts_render_with_expected_a4_geometry(tmp_path):
    _write_images(tmp_path)
    markdown = tmp_path / "image-layouts.md"
    output = tmp_path / "image-layouts.pdf"
    markdown.write_text(
        '''# Image layouts

## Wide

![Wide](1.png "Wide caption"){.figure-wide}

## Narrow

![Narrow](2.png "Narrow caption"){.figure-narrow}

<!-- page-break -->

## Two across

<div class="figure-grid figure-grid-2" markdown="1">

![First](3.png "First caption")

![Second](4.png "Second caption")

</div>

<!-- page-break -->

## Three across

<div class="figure-grid figure-grid-3" markdown="1">

![Third](5.png "Third caption")

![Fourth](6.png "Fourth caption")

![Fifth](7.png "Fifth caption")

</div>

## Full page

![Page](8.png "Full-page caption"){.figure-page}
''',
        encoding="utf-8",
    )

    document = _render_document(_prepare_render(str(markdown)))
    document.write_pdf(output, pdf_variant="pdf/ua-1")

    assert len(document.pages) == 4
    reader = PdfReader(output)
    assert len(reader.pages) == 4
    # WeasyPrint may expose the shared image resource dictionary from every
    # page; count distinct embedded image names rather than per-page views.
    assert len({
        image.name for page in reader.pages for image in page.images
    }) == 8

    page_boxes = [list(_walk(page._page_box)) for page in document.pages]
    wide = next(box for box in page_boxes[0] if "figure-wide" in _classes(box))
    narrow = next(box for box in page_boxes[0] if "figure-narrow" in _classes(box))
    full_page = next(
        box for box in page_boxes[3] if "figure-page" in _classes(box)
    )

    assert wide.width == pytest.approx(
        document.pages[0]._page_box.width, abs=1
    )
    assert narrow.width == pytest.approx(wide.width * 0.66, abs=1)
    assert narrow.margin_left == pytest.approx(narrow.margin_right, abs=0.1)
    assert narrow.margin_left > 100
    assert full_page.width == pytest.approx(wide.width, abs=1)
    assert full_page.height > 800

    two_up = [
        box for box in page_boxes[1]
        if getattr(box, "element_tag", None) == "figure"
    ]
    three_up = [
        box for box in page_boxes[2]
        if getattr(box, "element_tag", None) == "figure"
    ]
    assert len(two_up) == 2
    assert len(three_up) == 3
    assert two_up[0].width == pytest.approx(two_up[1].width, abs=0.1)
    assert three_up[0].width == pytest.approx(three_up[1].width, abs=0.1)
    assert three_up[1].width == pytest.approx(three_up[2].width, abs=0.1)
    assert two_up[0].position_x < two_up[1].position_x
    assert (
        three_up[0].position_x
        < three_up[1].position_x
        < three_up[2].position_x
    )
