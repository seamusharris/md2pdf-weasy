---
title: "Style Guide"
subtitle: "Colour, Typography & Spacing Reference"
theme: regrading
toc: true
toc_depth: 2
h2_page_break: true
---

## Chart Palette

The `COLOURS` array in `charts/theme.py` provides eight colours for line, bar, and area chart series.

| Index | Name | Hex | Swatch | Notes |
|-------|------|-----|--------|-------|
| 0 | Blue | `#4a7fb5` | <span style="display:inline-block;width:40px;height:14px;background:#4a7fb5;border-radius:2px;vertical-align:middle;"></span> | Stable anchor |
| 1 | Amber | `#e8a838` | <span style="display:inline-block;width:40px;height:14px;background:#e8a838;border-radius:2px;vertical-align:middle;"></span> | Stable anchor |
| 2 | Green | `#5a9e6f` | <span style="display:inline-block;width:40px;height:14px;background:#5a9e6f;border-radius:2px;vertical-align:middle;"></span> | |
| 3 | Red | `#d96464` | <span style="display:inline-block;width:40px;height:14px;background:#d96464;border-radius:2px;vertical-align:middle;"></span> | |
| 4 | Purple | `#8b6bb5` | <span style="display:inline-block;width:40px;height:14px;background:#8b6bb5;border-radius:2px;vertical-align:middle;"></span> | |
| 5 | Teal | `#3aadad` | <span style="display:inline-block;width:40px;height:14px;background:#3aadad;border-radius:2px;vertical-align:middle;"></span> | |
| 6 | Brown | `#c97b3d` | <span style="display:inline-block;width:40px;height:14px;background:#c97b3d;border-radius:2px;vertical-align:middle;"></span> | |
| 7 | Sea | `#4a9e87` | <span style="display:inline-block;width:40px;height:14px;background:#4a9e87;border-radius:2px;vertical-align:middle;"></span> | |

Positions 0 (blue) and 1 (amber) are stable anchors -- they keep their meaning across chart types. The remaining six rotate freely for additional series.


## Semantic Colours

Two tiers in `charts/theme.py`: fill-tier colours for SVG elements and text-tier variants darkened for WCAG AA (4.5:1 contrast on white).

### Fill tier

| Constant | Hex | Swatch | Usage |
|----------|-----|--------|-------|
| `COLOUR_POSITIVE` | `#3a9a5b` | <span style="display:inline-block;width:40px;height:14px;background:#3a9a5b;border-radius:2px;vertical-align:middle;"></span> | Positive change, gains, new players |
| `COLOUR_NEGATIVE` | `#d94040` | <span style="display:inline-block;width:40px;height:14px;background:#d94040;border-radius:2px;vertical-align:middle;"></span> | Negative change, losses, players left |
| `COLOUR_NEUTRAL` | `#888` | <span style="display:inline-block;width:40px;height:14px;background:#888;border-radius:2px;vertical-align:middle;"></span> | Baseline, unchanged, previous values |

### Text tier (WCAG AA)

| Constant | Hex | Swatch | Contrast | Usage |
|----------|-----|--------|----------|-------|
| `COLOUR_POSITIVE_TEXT` | `#32854f` | <span style="display:inline-block;width:40px;height:14px;background:#32854f;border-radius:2px;vertical-align:middle;"></span> | 4.6:1 | Result text, delta arrows, inline text |
| `COLOUR_NEGATIVE_TEXT` | `#c43c3c` | <span style="display:inline-block;width:40px;height:14px;background:#c43c3c;border-radius:2px;vertical-align:middle;"></span> | 4.6:1 | Result text, delta arrows, inline text |
| `COLOUR_NEUTRAL_TEXT` | `#767676` | <span style="display:inline-block;width:40px;height:14px;background:#767676;border-radius:2px;vertical-align:middle;"></span> | 4.5:1 | Draw results, neutral deltas |


## Grey Hierarchy

Six greys from dark to light in `charts/theme.py`. Each has a specific role -- darker greys carry more visual weight for more important text.

| Constant | Hex | Swatch | Usage |
|----------|-----|--------|-------|
| `GREY_TEXT` | `#555` | <span style="display:inline-block;width:40px;height:14px;background:#555;border-radius:2px;vertical-align:middle;"></span> | Value labels, legend text, bold annotations |
| `GREY_LABEL` | `#888` | <span style="display:inline-block;width:40px;height:14px;background:#888;border-radius:2px;vertical-align:middle;"></span> | Axis labels, secondary text, tick labels |
| `GREY_MUTED` | `#aaa` | <span style="display:inline-block;width:40px;height:14px;background:#aaa;border-radius:2px;vertical-align:middle;"></span> | Small-multiples y-labels, gap band text, null cell text |
| `GREY_AXIS` | `#ccc` | <span style="display:inline-block;width:40px;height:14px;background:#ccc;border-radius:2px;vertical-align:middle;"></span> | Axis lines, tick marks, connector lines |
| `GREY_GRID` | `#e0e0e0` | <span style="display:inline-block;width:40px;height:14px;background:#e0e0e0;border-radius:2px;vertical-align:middle;"></span> | Grid lines, row separators, header underlines |
| `GREY_NULL` | `#f5f5f5` | <span style="display:inline-block;width:40px;height:14px;background:#f5f5f5;border-radius:2px;vertical-align:middle;border:1px solid #ddd;"></span> | Null/empty cell backgrounds in heatmaps |


## Age Group Colours

Seven colours for 9U--Open age groups in `reporting/theme.py`. The 15U position uses gold instead of yellow for visibility on white backgrounds.

| Age | Hex | Swatch |
|-----|-----|--------|
| 9U | `#6db8d0` | <span style="display:inline-block;width:40px;height:14px;background:#6db8d0;border-radius:2px;vertical-align:middle;"></span> |
| 11U | `#5ab89e` | <span style="display:inline-block;width:40px;height:14px;background:#5ab89e;border-radius:2px;vertical-align:middle;"></span> |
| 13U | `#6aaa4c` | <span style="display:inline-block;width:40px;height:14px;background:#6aaa4c;border-radius:2px;vertical-align:middle;"></span> |
| 15U | `#d4b34a` | <span style="display:inline-block;width:40px;height:14px;background:#d4b34a;border-radius:2px;vertical-align:middle;"></span> |
| 17U | `#e0923a` | <span style="display:inline-block;width:40px;height:14px;background:#e0923a;border-radius:2px;vertical-align:middle;"></span> |
| 21U | `#d06060` | <span style="display:inline-block;width:40px;height:14px;background:#d06060;border-radius:2px;vertical-align:middle;"></span> |
| Open | `#9670b8` | <span style="display:inline-block;width:40px;height:14px;background:#9670b8;border-radius:2px;vertical-align:middle;"></span> |


## Club Colours

Club-specific colours in `reporting/theme.py` for cross-club comparison charts.

| Club | Abbrev | Hex | Swatch |
|------|--------|-----|--------|
| Warrandyte | WDT | `#cc2222` | <span style="display:inline-block;width:40px;height:14px;background:#cc2222;border-radius:2px;vertical-align:middle;"></span> |
| Deep Creek | DC | `#2266aa` | <span style="display:inline-block;width:40px;height:14px;background:#2266aa;border-radius:2px;vertical-align:middle;"></span> |
| Doncaster | DNC | `#228833` | <span style="display:inline-block;width:40px;height:14px;background:#228833;border-radius:2px;vertical-align:middle;"></span> |
| Donvale | DON | `#8833aa` | <span style="display:inline-block;width:40px;height:14px;background:#8833aa;border-radius:2px;vertical-align:middle;"></span> |
| East Doncaster | EDNC | `#ee8800` | <span style="display:inline-block;width:40px;height:14px;background:#ee8800;border-radius:2px;vertical-align:middle;"></span> |
| Eltham Panthers | EP | `#333333` | <span style="display:inline-block;width:40px;height:14px;background:#333333;border-radius:2px;vertical-align:middle;"></span> |
| Manningham | MNA | `#0088aa` | <span style="display:inline-block;width:40px;height:14px;background:#0088aa;border-radius:2px;vertical-align:middle;"></span> |
| Eastern United | EUN | `#cc4400` | <span style="display:inline-block;width:40px;height:14px;background:#cc4400;border-radius:2px;vertical-align:middle;"></span> |
| Melbourne East | MENA | `#2255bb` | <span style="display:inline-block;width:40px;height:14px;background:#2255bb;border-radius:2px;vertical-align:middle;"></span> |
| Gippsland Storm | GIPP | `#006633` | <span style="display:inline-block;width:40px;height:14px;background:#006633;border-radius:2px;vertical-align:middle;"></span> |
| Casey NA | CASY | `#8b0000` | <span style="display:inline-block;width:40px;height:14px;background:#8b0000;border-radius:2px;vertical-align:middle;"></span> |


## Specialised Palettes

### Movement waterfall

Colours for player movement waterfall charts in `reporting/theme.py`.

| Key | Hex | Swatch | Usage |
|-----|-----|--------|-------|
| `base` | `#888` | <span style="display:inline-block;width:40px;height:14px;background:#888;border-radius:2px;vertical-align:middle;"></span> | Previous season total |
| `left` | `#d94040` | <span style="display:inline-block;width:40px;height:14px;background:#d94040;border-radius:2px;vertical-align:middle;"></span> | Players who left |
| `new` | `#3a9a5b` | <span style="display:inline-block;width:40px;height:14px;background:#3a9a5b;border-radius:2px;vertical-align:middle;"></span> | New players |
| `current` | `#cc2222` | <span style="display:inline-block;width:40px;height:14px;background:#cc2222;border-radius:2px;vertical-align:middle;"></span> | Current season total (club colour) |

### Heatmap gradient

Three-stop gradient for win-rate heatmaps.

| Stop | Hex | Swatch |
|------|-----|--------|
| Low | `#d06060` | <span style="display:inline-block;width:40px;height:14px;background:#d06060;border-radius:2px;vertical-align:middle;"></span> |
| Mid | `#ecd05c` | <span style="display:inline-block;width:40px;height:14px;background:#ecd05c;border-radius:2px;vertical-align:middle;"></span> |
| High | `#3a9a5b` | <span style="display:inline-block;width:40px;height:14px;background:#3a9a5b;border-radius:2px;vertical-align:middle;"></span> |

### Finals progression

Background badges for finals grid (`_trends_finals.py`).

| Tier | Background | Swatch | Text |
|------|-----------|--------|------|
| Missed | `#E0E0E0` | <span style="display:inline-block;width:40px;height:14px;background:#E0E0E0;border-radius:2px;vertical-align:middle;"></span> | `#999` (intentionally muted) |
| Lost SF | `#e8a8a8` | <span style="display:inline-block;width:40px;height:14px;background:#e8a8a8;border-radius:2px;vertical-align:middle;"></span> | `#6a2020` |
| Lost GF | `#d87070` | <span style="display:inline-block;width:40px;height:14px;background:#d87070;border-radius:2px;vertical-align:middle;"></span> | `#fff` |
| Premiership | Club colour | | `#fff` |

Section tier gradient (green to blue, L36% to L79%):

| Section | Hex | Swatch |
|---------|-----|--------|
| Section 1 | `#2d8a4e` | <span style="display:inline-block;width:40px;height:14px;background:#2d8a4e;border-radius:2px;vertical-align:middle;"></span> |
| Section 2 | `#4a9f6e` | <span style="display:inline-block;width:40px;height:14px;background:#4a9f6e;border-radius:2px;vertical-align:middle;"></span> |
| Section 3 | `#78c2ad` | <span style="display:inline-block;width:40px;height:14px;background:#78c2ad;border-radius:2px;vertical-align:middle;"></span> |
| Section 4 | `#a8d8ea` | <span style="display:inline-block;width:40px;height:14px;background:#a8d8ea;border-radius:2px;vertical-align:middle;"></span> |

### Tenure bands

10-step cool blue gradient in `_trends_players.py` (lighter = newer).

| Band | Hex | Swatch |
|------|-----|--------|
| 1 yr | `#d4e8f0` | <span style="display:inline-block;width:40px;height:14px;background:#d4e8f0;border-radius:2px;vertical-align:middle;"></span> |
| 2 yr | `#a8d8ea` | <span style="display:inline-block;width:40px;height:14px;background:#a8d8ea;border-radius:2px;vertical-align:middle;"></span> |
| 3 yr | `#78c2ad` | <span style="display:inline-block;width:40px;height:14px;background:#78c2ad;border-radius:2px;vertical-align:middle;"></span> |
| 4 yr | `#4a9f6e` | <span style="display:inline-block;width:40px;height:14px;background:#4a9f6e;border-radius:2px;vertical-align:middle;"></span> |
| 5 yr | `#4a7fb5` | <span style="display:inline-block;width:40px;height:14px;background:#4a7fb5;border-radius:2px;vertical-align:middle;"></span> |
| 6 yr | `#3a6a9f` | <span style="display:inline-block;width:40px;height:14px;background:#3a6a9f;border-radius:2px;vertical-align:middle;"></span> |
| 7 yr | `#2d5f8a` | <span style="display:inline-block;width:40px;height:14px;background:#2d5f8a;border-radius:2px;vertical-align:middle;"></span> |
| 8 yr | `#1f4e7a` | <span style="display:inline-block;width:40px;height:14px;background:#1f4e7a;border-radius:2px;vertical-align:middle;"></span> |
| 9 yr | `#1a3a5f` | <span style="display:inline-block;width:40px;height:14px;background:#1a3a5f;border-radius:2px;vertical-align:middle;"></span> |
| 10+ yr | `#0f2440` | <span style="display:inline-block;width:40px;height:14px;background:#0f2440;border-radius:2px;vertical-align:middle;"></span> |

Bands 3--4 share the section tier teal/green colours. Band 5 reuses `COLOURS[0]` blue.


## PDF Colours

CSS variables defined in `:root` of `pdf/styles/style.css`. Override any variable in a theme overlay to re-skin the entire document.

### Core palette

| Variable | Hex | Swatch | Usage |
|----------|-----|--------|-------|
| `--color-text` | `#333` | <span style="display:inline-block;width:40px;height:14px;background:#333;border-radius:2px;vertical-align:middle;"></span> | Body text |
| `--color-heading` | `#000` | <span style="display:inline-block;width:40px;height:14px;background:#000;border-radius:2px;vertical-align:middle;"></span> | Heading text |
| `--color-link` | `#2c5282` | <span style="display:inline-block;width:40px;height:14px;background:#2c5282;border-radius:2px;vertical-align:middle;"></span> | Hyperlinks (muted navy) |

### Table chrome

| Variable | Hex | Swatch | Usage |
|----------|-----|--------|-------|
| `--color-border` | `#555` | <span style="display:inline-block;width:40px;height:14px;background:#555;border-radius:2px;vertical-align:middle;"></span> | Cell borders |
| `--color-border-heavy` | `#444` | <span style="display:inline-block;width:40px;height:14px;background:#444;border-radius:2px;vertical-align:middle;"></span> | Header bottom border |
| `--color-border-light` | `#bbb` | <span style="display:inline-block;width:40px;height:14px;background:#bbb;border-radius:2px;vertical-align:middle;"></span> | Section divider borders |
| `--color-header-bg` | `#e8e8e8` | <span style="display:inline-block;width:40px;height:14px;background:#e8e8e8;border-radius:2px;vertical-align:middle;"></span> | `<th>` background |
| `--color-section-bg` | `#f2f2f2` | <span style="display:inline-block;width:40px;height:14px;background:#f2f2f2;border-radius:2px;vertical-align:middle;border:1px solid #ddd;"></span> | Section divider row background |

<table style="width:70%; font-size:8.5pt; line-height:1.4; border-collapse:collapse;">
<tr>
<th style="font-size:9pt; font-weight:700; background:#e8e8e8; border:0.5pt solid #555; border-bottom:1pt solid #444; padding:3.5pt 5pt; text-align:left;">Team</th>
<th style="font-size:9pt; font-weight:700; background:#e8e8e8; border:0.5pt solid #555; border-bottom:1pt solid #444; padding:3.5pt 5pt; text-align:center;">P</th>
<th style="font-size:9pt; font-weight:700; background:#e8e8e8; border:0.5pt solid #555; border-bottom:1pt solid #444; padding:3.5pt 5pt; text-align:center;">W</th>
<th style="font-size:9pt; font-weight:700; background:#e8e8e8; border:0.5pt solid #555; border-bottom:1pt solid #444; padding:3.5pt 5pt; text-align:center;">L</th>
<th style="font-size:9pt; font-weight:700; background:#e8e8e8; border:0.5pt solid #555; border-bottom:1pt solid #444; padding:3.5pt 5pt; text-align:center;">Pts</th>
</tr>
<tr style="background:#d8e1ee; font-weight:700;">
<td style="border:0.5pt solid #555; padding:3.5pt 5pt;">Warrandyte 1</td>
<td style="border:0.5pt solid #555; padding:3.5pt 5pt; text-align:center;">14</td>
<td style="border:0.5pt solid #555; padding:3.5pt 5pt; text-align:center;">10</td>
<td style="border:0.5pt solid #555; padding:3.5pt 5pt; text-align:center;">3</td>
<td style="border:0.5pt solid #555; padding:3.5pt 5pt; text-align:center;">42</td>
</tr>
<tr>
<td style="border:0.5pt solid #555; padding:3.5pt 5pt;">Eltham 1</td>
<td style="border:0.5pt solid #555; padding:3.5pt 5pt; text-align:center;">14</td>
<td style="border:0.5pt solid #555; padding:3.5pt 5pt; text-align:center;">8</td>
<td style="border:0.5pt solid #555; padding:3.5pt 5pt; text-align:center;">5</td>
<td style="border:0.5pt solid #555; padding:3.5pt 5pt; text-align:center;">34</td>
</tr>
<tr>
<td style="border:0.5pt solid #555; padding:3.5pt 5pt;">Donvale 1</td>
<td style="border:0.5pt solid #555; padding:3.5pt 5pt; text-align:center;">14</td>
<td style="border:0.5pt solid #555; padding:3.5pt 5pt; text-align:center;">5</td>
<td style="border:0.5pt solid #555; padding:3.5pt 5pt; text-align:center;">8</td>
<td style="border:0.5pt solid #555; padding:3.5pt 5pt; text-align:center;">22</td>
</tr>
</table>

Highlighted row shows `--color-highlight` (tracked team). Header uses `--color-header-bg` with `--color-border-heavy` bottom border. Cells use `--color-border`.

### Row highlights -- regrading

Three-tier system with green/pink symmetry. Pink is intentionally over-saturated to compensate for weaker perceptual vividness of red/pink vs green at equal HSL saturation.

| Tier | Up | Swatch | Variable | Down | Swatch | Variable | Symmetry |
|------|----|--------|----------|------|--------|----------|----------|
| Strong | `#a8dda8` | <span style="display:inline-block;width:40px;height:14px;background:#a8dda8;border-radius:2px;vertical-align:middle;"></span> | `--color-up` | `#ddb0a8` | <span style="display:inline-block;width:40px;height:14px;background:#ddb0a8;border-radius:2px;vertical-align:middle;"></span> | `--color-down` | S44% L76% -- perfect |
| Moderate | `#cce8cc` | <span style="display:inline-block;width:40px;height:14px;background:#cce8cc;border-radius:2px;vertical-align:middle;"></span> | `--color-mod-up` | `#e8ccc6` | <span style="display:inline-block;width:40px;height:14px;background:#e8ccc6;border-radius:2px;vertical-align:middle;"></span> | `--color-mod-down` | L85% -- 5pp pink bias |
| Watch | `#e0f0e0` | <span style="display:inline-block;width:40px;height:14px;background:#e0f0e0;border-radius:2px;vertical-align:middle;"></span> | `--color-watch-up` | `#f0dedb` | <span style="display:inline-block;width:40px;height:14px;background:#f0dedb;border-radius:2px;vertical-align:middle;"></span> | `--color-watch-down` | L90% -- 7pp pink bias |

### Row highlights -- tracked team

| Variable | Hex | Swatch | Usage |
|----------|-----|--------|-------|
| `--color-highlight` | `#d8e1ee` | <span style="display:inline-block;width:40px;height:14px;background:#d8e1ee;border-radius:2px;vertical-align:middle;"></span> | Tracked team row (light blue) |

### Row highlights -- verdict

| Verdict | Variable | Hex | Swatch | Reuses |
|---------|----------|-----|--------|--------|
| Success | `--color-verdict-ok` | `#e0f0e0` | <span style="display:inline-block;width:40px;height:14px;background:#e0f0e0;border-radius:2px;vertical-align:middle;"></span> | = `--color-watch-up` |
| Warning | `--color-verdict-warn` | `#fff3cd` | <span style="display:inline-block;width:40px;height:14px;background:#fff3cd;border-radius:2px;vertical-align:middle;"></span> | Unique -- warm amber |
| Failure | `--color-verdict-fail` | `#f0dedb` | <span style="display:inline-block;width:40px;height:14px;background:#f0dedb;border-radius:2px;vertical-align:middle;"></span> | = `--color-watch-down` |

### Risk cells

| Level | Variable | Hex | Swatch | Reuses |
|-------|----------|-----|--------|--------|
| Low (<25%) | `--color-up` | `#a8dda8` | <span style="display:inline-block;width:40px;height:14px;background:#a8dda8;border-radius:2px;vertical-align:middle;"></span> | = strong move-up |
| Medium (25--49%) | `--color-risk-med` | `#fff3e0` | <span style="display:inline-block;width:40px;height:14px;background:#fff3e0;border-radius:2px;vertical-align:middle;border:1px solid #ddd;"></span> | Unique -- light amber |
| High (>=50%) | `--color-down` | `#ddb0a8` | <span style="display:inline-block;width:40px;height:14px;background:#ddb0a8;border-radius:2px;vertical-align:middle;"></span> | = strong move-down |

### Blockquote callouts

Six-tier cool-to-warm progression. Border colours are dark (L25--55%); tints are very light (L93--97%).

| Tier | Border | Swatch | Variable | Background | Swatch | Variable |
|------|--------|--------|----------|------------|--------|----------|
| Default | `#666` | <span style="display:inline-block;width:40px;height:14px;background:#666;border-radius:2px;vertical-align:middle;"></span> | `--color-default` | `#f5f5f5` | <span style="display:inline-block;width:40px;height:14px;background:#f5f5f5;border-radius:2px;vertical-align:middle;border:1px solid #ddd;"></span> | `--color-default-tint` |
| Info / Note | `#1e3a5f` | <span style="display:inline-block;width:40px;height:14px;background:#1e3a5f;border-radius:2px;vertical-align:middle;"></span> | `--color-accent` | `#edf1f7` | <span style="display:inline-block;width:40px;height:14px;background:#edf1f7;border-radius:2px;vertical-align:middle;border:1px solid #ddd;"></span> | `--color-accent-tint` |
| Tip | `#1a7a6d` | <span style="display:inline-block;width:40px;height:14px;background:#1a7a6d;border-radius:2px;vertical-align:middle;"></span> | `--color-tip` | `#e8f6f3` | <span style="display:inline-block;width:40px;height:14px;background:#e8f6f3;border-radius:2px;vertical-align:middle;border:1px solid #ddd;"></span> | `--color-tip-tint` |
| Important | `#6b3fa0` | <span style="display:inline-block;width:40px;height:14px;background:#6b3fa0;border-radius:2px;vertical-align:middle;"></span> | `--color-important` | `#f0e8f5` | <span style="display:inline-block;width:40px;height:14px;background:#f0e8f5;border-radius:2px;vertical-align:middle;border:1px solid #ddd;"></span> | `--color-important-tint` |
| Caution | `#946b00` | <span style="display:inline-block;width:40px;height:14px;background:#946b00;border-radius:2px;vertical-align:middle;"></span> | `--color-caution` | `#fef9e7` | <span style="display:inline-block;width:40px;height:14px;background:#fef9e7;border-radius:2px;vertical-align:middle;border:1px solid #ddd;"></span> | `--color-caution-tint` |
| Warning | `#d94040` | <span style="display:inline-block;width:40px;height:14px;background:#d94040;border-radius:2px;vertical-align:middle;"></span> | `--color-warn` | `#fdf0f0` | <span style="display:inline-block;width:40px;height:14px;background:#fdf0f0;border-radius:2px;vertical-align:middle;border:1px solid #ddd;"></span> | `--color-warn-tint` |

### Result text classes

CSS classes in `style.css`, applied automatically by `table_transforms.py`.

| Class | Hex | Swatch | Constant | Contrast |
|-------|-----|--------|----------|----------|
| `.result-win` | `#32854f` | <span style="display:inline-block;width:40px;height:14px;background:#32854f;border-radius:2px;vertical-align:middle;"></span> | `COLOUR_POSITIVE_TEXT` | 4.6:1 |
| `.result-loss` | `#c43c3c` | <span style="display:inline-block;width:40px;height:14px;background:#c43c3c;border-radius:2px;vertical-align:middle;"></span> | `COLOUR_NEGATIVE_TEXT` | 4.6:1 |
| `.result-draw` | `#767676` | <span style="display:inline-block;width:40px;height:14px;background:#767676;border-radius:2px;vertical-align:middle;"></span> | `COLOUR_NEUTRAL_TEXT` | 4.5:1 |

### Delta arrows and status markers

Delta arrows (up/down superscript indicators in trend tables) use the text-tier constants: positive = `COLOUR_POSITIVE_TEXT`, negative = `COLOUR_NEGATIVE_TEXT`.

Status markers use fill-tier constants -- they are symbols, not readable text:

| Marker | Constant | Usage |
|--------|----------|-------|
| <span style="color:#d94040;font-weight:700;">†</span> partial season | `COLOUR_NEGATIVE` | Incomplete season superscript |
| <span style="color:#888;">‡</span> roster-only, footnotes | `COLOUR_NEUTRAL` | Informational marker |

### Muted UI

| Variable | Hex | Swatch | Usage |
|----------|-----|--------|-------|
| `--color-muted` | `#999` | <span style="display:inline-block;width:40px;height:14px;background:#999;border-radius:2px;vertical-align:middle;"></span> | Page numbers, light text |
| `--color-rule` | `#ddd` | <span style="display:inline-block;width:40px;height:14px;background:#ddd;border-radius:2px;vertical-align:middle;"></span> | Horizontal rules |
| `--color-code-bg` | `#f4f4f4` | <span style="display:inline-block;width:40px;height:14px;background:#f4f4f4;border-radius:2px;vertical-align:middle;border:1px solid #ddd;"></span> | Code / pre background |


## Chart Typography

SVG font scale and stroke weights in `charts/theme.py`. Font family: `AntSerif, Georgia, serif`.

### Font scale (small to large)

| Constant | Size | Usage |
|----------|------|-------|
| `FONT_MICRO` | 5.5pt | Legend annotations (timeline intensity) |
| `FONT_TINY` | 6pt | Waterfall/sankey bar values, gap band text |
| `FONT_SMALL` | 6.5pt | Year labels, small-multiples y-axis |
| `FONT_AXIS` | 7pt | x/y axis labels, tick labels, legend text |
| `FONT_LABEL` | 7.5pt | Value labels, column headers, cell values |
| `FONT_BODY` | 8.5pt | Bar chart row labels |
| `FONT_TITLE` | 10pt | Chart titles |

### Stroke weights (thin to thick)

| Constant | Weight | Usage |
|----------|--------|-------|
| `STROKE_GRID` | 0.5 | Grid lines, ticks, connectors |
| `STROKE_AXIS` | 1 | Axis lines, cell borders, dividers |
| `STROKE_LINE` | 2 | Data lines, legend lines |
| `STROKE_BOLD` | 2.5 | Dual-axis emphasis lines |


## PDF Typography

Heading scale, line-height formula, and table sizes from `pdf/styles/style.css`. Font: AntSerif (Anthropic Serif) with Georgia fallback.

### Heading scale

| Level | Size | Line-height | Role |
|-------|------|-------------|------|
| h1 | 22pt | 1.2 | Document title (used once, centred) |
| h2 | 17pt | 1.25 | Major sections |
| h3 | 14pt | 1.3 | Sub-sections (e.g. team, division) |
| h4 | 12pt | 1.35 | Detail headings (e.g. ladder, results) |
| body | 10pt | 1.45 | Standard paragraph text |
| list | 9pt | 1.45 | List items, slightly subordinate |
| th | 9pt | 1.4 | Table headers |
| td | 8.5pt | 1.4 | Table cells |
| footer | 8pt | -- | Page numbers |

Size steps: -5, -3, -2, -2 (consistent acceleration). Line-height: 1.2 + 0.05 per level down from h1 (body reaches 1.45).

<div style="background:#fafafa; border:1px solid #e0e0e0; border-radius:3pt; padding:10pt 14pt; margin:4mm 0;">
<div style="font-size:22pt; font-weight:700; line-height:1.2;">Season Report 2025</div>
<div style="font-size:17pt; font-weight:700; line-height:1.25; margin-top:3mm;">Overview</div>
<div style="font-size:14pt; font-weight:700; line-height:1.3; margin-top:2.2mm;">11U Division 1</div>
<div style="font-size:12pt; font-weight:700; line-height:1.35; margin-top:3mm;">Ladder</div>
<div style="font-size:10pt; line-height:1.45; margin-top:1.5mm;">The team finished third with a 7&#8211;5 record across 14 rounds, including a strong run of five consecutive wins.</div>
<div style="font-size:9pt; line-height:1.45; margin-top:1.5mm; padding-left:4mm;">&bull; List items slightly smaller than body for visual subordination</div>
<div style="font-size:8pt; color:#999; margin-top:3mm;">Page 1/12</div>
<p style="font-size:7pt; color:#aaa; margin-top:4mm; border-top:0.5pt solid #ddd; padding-top:2mm;">h1+h2: 3mm &nbsp;|&nbsp; h2+h3: 2.2mm &nbsp;|&nbsp; h3+h4: 3mm (&#8209;&#8209;space-sm) &nbsp;|&nbsp; h4 &#8594; body: 1.5mm (&#8209;&#8209;space-xs)</p>
</div>

### Table sizes

| Property | Base | Compact override |
|----------|------|-----------------|
| td font-size | 8.5pt | 7.5pt |
| th font-size | 9pt | 8pt |
| th--td gap | +0.5pt | +0.5pt |
| padding | 3.5pt 5pt | 2pt 4pt |
| border | 0.5pt `#555` | 0.5pt `#555` |
| line-height | 1.4 | 1.25 |

**Base table** (td 8.5pt, th 9pt, padding 3.5pt 5pt):

<table style="width:70%; font-size:8.5pt; line-height:1.4; border-collapse:collapse;">
<tr>
<th style="font-size:9pt; font-weight:700; background:#e8e8e8; border:0.5pt solid #555; border-bottom:1pt solid #444; padding:3.5pt 5pt; text-align:left;">Team</th>
<th style="font-size:9pt; font-weight:700; background:#e8e8e8; border:0.5pt solid #555; border-bottom:1pt solid #444; padding:3.5pt 5pt; text-align:center;">P</th>
<th style="font-size:9pt; font-weight:700; background:#e8e8e8; border:0.5pt solid #555; border-bottom:1pt solid #444; padding:3.5pt 5pt; text-align:center;">W</th>
<th style="font-size:9pt; font-weight:700; background:#e8e8e8; border:0.5pt solid #555; border-bottom:1pt solid #444; padding:3.5pt 5pt; text-align:center;">L</th>
<th style="font-size:9pt; font-weight:700; background:#e8e8e8; border:0.5pt solid #555; border-bottom:1pt solid #444; padding:3.5pt 5pt; text-align:center;">Pts</th>
</tr>
<tr>
<td style="border:0.5pt solid #555; padding:3.5pt 5pt;">Warrandyte 1</td>
<td style="border:0.5pt solid #555; padding:3.5pt 5pt; text-align:center;">14</td>
<td style="border:0.5pt solid #555; padding:3.5pt 5pt; text-align:center;">10</td>
<td style="border:0.5pt solid #555; padding:3.5pt 5pt; text-align:center;">3</td>
<td style="border:0.5pt solid #555; padding:3.5pt 5pt; text-align:center;">42</td>
</tr>
<tr>
<td style="border:0.5pt solid #555; padding:3.5pt 5pt;">Eltham 1</td>
<td style="border:0.5pt solid #555; padding:3.5pt 5pt; text-align:center;">14</td>
<td style="border:0.5pt solid #555; padding:3.5pt 5pt; text-align:center;">8</td>
<td style="border:0.5pt solid #555; padding:3.5pt 5pt; text-align:center;">5</td>
<td style="border:0.5pt solid #555; padding:3.5pt 5pt; text-align:center;">34</td>
</tr>
</table>

**Compact table** (td 7.5pt, th 8pt, padding 2pt 4pt):

<table style="width:70%; font-size:7.5pt; line-height:1.25; border-collapse:collapse;">
<tr>
<th style="font-size:8pt; font-weight:700; background:#e8e8e8; border:0.5pt solid #555; border-bottom:1pt solid #444; padding:2pt 4pt; text-align:left;">Team</th>
<th style="font-size:8pt; font-weight:700; background:#e8e8e8; border:0.5pt solid #555; border-bottom:1pt solid #444; padding:2pt 4pt; text-align:center;">P</th>
<th style="font-size:8pt; font-weight:700; background:#e8e8e8; border:0.5pt solid #555; border-bottom:1pt solid #444; padding:2pt 4pt; text-align:center;">W</th>
<th style="font-size:8pt; font-weight:700; background:#e8e8e8; border:0.5pt solid #555; border-bottom:1pt solid #444; padding:2pt 4pt; text-align:center;">L</th>
<th style="font-size:8pt; font-weight:700; background:#e8e8e8; border:0.5pt solid #555; border-bottom:1pt solid #444; padding:2pt 4pt; text-align:center;">Pts</th>
</tr>
<tr>
<td style="border:0.5pt solid #555; padding:2pt 4pt;">Warrandyte 1</td>
<td style="border:0.5pt solid #555; padding:2pt 4pt; text-align:center;">14</td>
<td style="border:0.5pt solid #555; padding:2pt 4pt; text-align:center;">10</td>
<td style="border:0.5pt solid #555; padding:2pt 4pt; text-align:center;">3</td>
<td style="border:0.5pt solid #555; padding:2pt 4pt; text-align:center;">42</td>
</tr>
<tr>
<td style="border:0.5pt solid #555; padding:2pt 4pt;">Eltham 1</td>
<td style="border:0.5pt solid #555; padding:2pt 4pt; text-align:center;">14</td>
<td style="border:0.5pt solid #555; padding:2pt 4pt; text-align:center;">8</td>
<td style="border:0.5pt solid #555; padding:2pt 4pt; text-align:center;">5</td>
<td style="border:0.5pt solid #555; padding:2pt 4pt; text-align:center;">34</td>
</tr>
</table>


## Spacing System

All vertical spacing derives from `--space-unit` (3mm). Override any variable in an overlay to scale proportionally.

| Variable | Value | Multiple | Usage |
|----------|-------|----------|-------|
| `--space-xs` | 1.5mm | 0.5x | Heading to its content (all levels), p-to-p |
| `--space-sm` | 3mm | 1x | h4 margin-top, heading-to-table gap |
| `--space-md` | 4.5mm | 1.5x | Table margins, subtitle to content |
| `--space-lg` | 6mm | 2x | h2/h3 margin-top |
| `--space-xl` | 9mm | 3x | Reserved for overlays |

### Heading margins

| Level | margin-top | margin-bottom |
|-------|-----------|--------------|
| h1 (title) | 0 | `--space-sm` (3mm) |
| h2 (section) | `--space-lg` (6mm) | `--space-xs` (1.5mm) |
| h3 (team) | `--space-lg` (6mm) | `--space-xs` (1.5mm) |
| h4 (detail) | `--space-sm` (3mm) | `--space-xs` (1.5mm) |
| body / p | 0 | `--space-sm` (3mm) |

Hierarchy principle: headings bind downward (small margin-bottom) and repel upward (larger margin-top).

### Consecutive heading collapse

When headings appear back-to-back, the child's margin-top collapses so they read as one unit. Larger type needs more breathing room, so the collapse is graduated:

| Pair | Collapse to | Value |
|------|-----------|-------|
| h1 + h2 | 3mm | 3mm |
| h2 + h3 | 2.2mm | 2.2mm |
| h3 + h4 | `--space-sm` | 3mm |
| h4 + h5 | `--space-xs` | 1.5mm |


## Page Layout

### Page margins

All themes use the same A4 page with consistent margins. Only retrospective changes to landscape orientation.

| Edge | Value |
|------|-------|
| Top | 22mm (first page: 18mm) |
| Right | 18mm |
| Bottom | 25mm |
| Left | 18mm |

### Page break rules

Base rules (always active):

1. **Never break after a heading** -- headings pull content below them onto the same page.
2. **Keep heading + first content together** -- the first element after h2/h3 can't be pushed to the next page alone.
3. **Keep heading + first two paragraphs** -- short intros stay with their heading.

### Theme-specific overrides

| Theme | Rule | Why |
|-------|------|-----|
| Club | `h3 { break-before: page; margin-top: 0; }` | New page per team |
| Trends | `table { break-inside: auto; }` + `thead { display: table-header-group; }` | Long tables split with repeated headers |
| Regrading | `h2 { break-before: page; margin-top: 0; }` | New page per section |
| Retrospective | `table { break-inside: auto; }` | Long comparison tables split |
| Front matter | `h2 { break-before: page; margin-top: 0; }` | Via `h2_page_break: true` |

### Theme overlays

All themes share the same heading, body, and list sizes. Overlays only control layout.

| Theme overlay | What it overrides |
|---------------|------------------|
| `compact.css` | Table sizes (td 7.5pt, th 8pt, padding 2pt 4pt) + tighter margins |
| `style_club.css` | `h3 { break-before: page; }` + tighter margins |
| `style_trends.css` | `table { break-inside: auto; } thead { display: table-header-group; }` + tighter margins |
