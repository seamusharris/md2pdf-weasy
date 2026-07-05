"""The table cell's asymmetric vertical padding is *derived from the body
font's metrics*, not eyeballed. These tests make that derivation an enforced
invariant: they recompute the expected split from the bundled OTF and fail if
the font is swapped, the values are hand-edited inconsistently, or the
redistribution stops being a pure redistribution.

This is the "single source of truth" the values need — the font is a hidden
input to the `0.5 / 0.3` literals in style.css, and this test keeps the
provenance (and the maths) attached to them.
"""

import os
import re

from fontTools.ttLib import TTFont

import pdf

_PKG = os.path.dirname(pdf.__file__)
_CSS = os.path.join(_PKG, 'styles', 'style.css')
# The regular body-cell face (style.css @font-face: "Minion Caption" 400).
_FONT = os.path.join(_PKG, 'fonts', 'MinionPro-Capt.otf')

# The symmetric padding budget the asymmetric split redistributes (2 × 0.4em).
_BUDGET_EM = 0.8


def _metric_offset_em():
    """Downward shift (em) that visually centres caps/figures: half the
    difference between the descender void below the baseline and the slack
    above the cap height."""
    font = TTFont(_FONT)
    upm = font['head'].unitsPerEm
    ascent = font['hhea'].ascent / upm
    descent = -font['hhea'].descent / upm          # hhea descent is negative
    cap = font['OS/2'].sCapHeight / upm
    ascent_slack = ascent - cap
    return (descent - ascent_slack) / 2


def _css_cell_padding_em():
    """(top, bottom) em values from the 3-value cell padding in style.css."""
    css = open(_CSS, encoding='utf-8').read()
    m = re.search(r'padding:\s*([\d.]+)em\s+[\d.]+em\s+([\d.]+)em\s*;', css)
    assert m, "expected a 3-value em cell padding in style.css"
    return float(m.group(1)), float(m.group(2))


class TestCellPaddingTracksFontMetrics:

    def test_redistribution_not_reduction(self):
        # top + bottom must equal the symmetric budget, so the painted box
        # (height, background, borders) is byte-for-byte unchanged and only the
        # glyphs shift. This is the invariant that's easy to break by hand.
        top, bottom = _css_cell_padding_em()
        assert round(top + bottom, 4) == _BUDGET_EM

    def test_split_matches_the_font_descender(self):
        # The asymmetry must match what the bundled font actually needs. Swap
        # the caption font (different descender ratio) and this fails until the
        # split is recomputed — the numbers can't silently outlive the font.
        top, bottom = _css_cell_padding_em()
        implied_offset = (top - bottom) / 2
        assert abs(implied_offset - _metric_offset_em()) < 0.02
