"""Fresh-process regression for WeasyPrint native-state teardown."""

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path


def test_repeated_real_renders_collect_and_exit_cleanly() -> None:
    """A written PDF is not a pass if native teardown kills the process."""
    fixture = Path("tests/visual/table-widths.md").resolve()
    child = textwrap.dedent(
        f"""
        import gc
        from pdf.render import _prepare_render, _render_document

        prepared = _prepare_render({str(fixture)!r})
        for _ in range(12):
            document = _render_document(prepared)
            pdf = document.write_pdf(pdf_variant="pdf/ua-1")
            if not pdf.startswith(b"%PDF-"):
                raise RuntimeError("render did not return a PDF")
            del document, pdf
        gc.collect()
        gc.collect()
        """
    )

    try:
        result = subprocess.run(
            [sys.executable, "-X", "faulthandler", "-c", child],
            cwd=Path(__file__).resolve().parents[1],
            text=True,
            capture_output=True,
            timeout=120,
        )
    except subprocess.TimeoutExpired as exc:
        raise AssertionError(
            "repeated-render child did not exit within 120 seconds"
        ) from exc

    assert result.returncode == 0, (
        "repeated-render child did not exit cleanly "
        f"(return code {result.returncode})\n"
        f"stdout:\n{result.stdout[-4000:]}\n"
        f"stderr:\n{result.stderr[-4000:]}"
    )
