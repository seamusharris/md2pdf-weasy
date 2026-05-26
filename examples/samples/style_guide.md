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
| 0 | Blue | `#4a7fb5` | <span class="swatch" style="background:#4a7fb5"></span> | Stable anchor |
| 1 | Amber | `#e8a838` | <span class="swatch" style="background:#e8a838"></span> | Stable anchor |
| 2 | Green | `#5a9e6f` | <span class="swatch" style="background:#5a9e6f"></span> | |
| 3 | Red | `#d96464` | <span class="swatch" style="background:#d96464"></span> | |
| 4 | Purple | `#8b6bb5` | <span class="swatch" style="background:#8b6bb5"></span> | |
| 5 | Teal | `#3aadad` | <span class="swatch" style="background:#3aadad"></span> | |
| 6 | Brown | `#c97b3d` | <span class="swatch" style="background:#c97b3d"></span> | |
| 7 | Sea | `#4a9e87` | <span class="swatch" style="background:#4a9e87"></span> | |

Positions 0 (blue) and 1 (amber) are stable anchors -- they keep their meaning across chart types. The remaining six rotate freely for additional series.


## Semantic Colours

Two tiers in `charts/theme.py`: fill-tier colours for SVG elements and text-tier variants darkened for WCAG AA (4.5:1 contrast on white).

### Fill tier

| Constant | Hex | Swatch | Usage |
|----------|-----|--------|-------|
| `COLOUR_POSITIVE` | `#3a9a5b` | <span class="swatch" style="background:#3a9a5b"></span> | Positive change, gains, new players |
| `COLOUR_NEGATIVE` | `#d94040` | <span class="swatch" style="background:#d94040"></span> | Negative change, losses, players left |
| `COLOUR_NEUTRAL` | `#888` | <span class="swatch" style="background:#888"></span> | Baseline, unchanged, previous values |

### Text tier (WCAG AA)

| Constant | Hex | Swatch | Contrast | Usage |
|----------|-----|--------|----------|-------|
| `COLOUR_POSITIVE_TEXT` | `#32854f` | <span class="swatch" style="background:#32854f"></span> | 4.6:1 | Result text, delta arrows, inline text |
| `COLOUR_NEGATIVE_TEXT` | `#c43c3c` | <span class="swatch" style="background:#c43c3c"></span> | 4.6:1 | Result text, delta arrows, inline text |
| `COLOUR_NEUTRAL_TEXT` | `#767676` | <span class="swatch" style="background:#767676"></span> | 4.5:1 | Draw results, neutral deltas |


## Grey Hierarchy

Six greys from dark to light in `charts/theme.py`. Each has a specific role -- darker greys carry more visual weight for more important text.

| Constant | Hex | Swatch | Usage |
|----------|-----|--------|-------|
| `GREY_TEXT` | `#555` | <span class="swatch" style="background:#555"></span> | Value labels, legend text, bold annotations |
| `GREY_LABEL` | `#888` | <span class="swatch" style="background:#888"></span> | Axis labels, secondary text, tick labels |
| `GREY_MUTED` | `#aaa` | <span class="swatch" style="background:#aaa"></span> | Small-multiples y-labels, gap band text, null cell text |
| `GREY_AXIS` | `#ccc` | <span class="swatch" style="background:#ccc"></span> | Axis lines, tick marks, connector lines |
| `GREY_GRID` | `#e0e0e0` | <span class="swatch" style="background:#e0e0e0"></span> | Grid lines, row separators, header underlines |
| `GREY_NULL` | `#f5f5f5` | <span class="swatch" style="background:#f5f5f5; border:1px solid #ddd"></span> | Null/empty cell backgrounds in heatmaps |


## Age Group Colours

Seven colours for 9U--Open age groups in `reporting/theme.py`. The 15U position uses gold instead of yellow for visibility on white backgrounds.

| Age | Hex | Swatch |
|-----|-----|--------|
| 9U | `#6db8d0` | <span class="swatch" style="background:#6db8d0"></span> |
| 11U | `#5ab89e` | <span class="swatch" style="background:#5ab89e"></span> |
| 13U | `#6aaa4c` | <span class="swatch" style="background:#6aaa4c"></span> |
| 15U | `#d4b34a` | <span class="swatch" style="background:#d4b34a"></span> |
| 17U | `#e0923a` | <span class="swatch" style="background:#e0923a"></span> |
| 21U | `#d06060` | <span class="swatch" style="background:#d06060"></span> |
| Open | `#9670b8` | <span class="swatch" style="background:#9670b8"></span> |


## Club Colours

Club-specific colours in `reporting/theme.py` for cross-club comparison charts.

| Club | Abbrev | Hex | Swatch |
|------|--------|-----|--------|
| Warrandyte | WDT | `#cc2222` | <span class="swatch" style="background:#cc2222"></span> |
| Deep Creek | DC | `#2266aa` | <span class="swatch" style="background:#2266aa"></span> |
| Doncaster | DNC | `#228833` | <span class="swatch" style="background:#228833"></span> |
| Donvale | DON | `#8833aa` | <span class="swatch" style="background:#8833aa"></span> |
| East Doncaster | EDNC | `#ee8800` | <span class="swatch" style="background:#ee8800"></span> |
| Eltham Panthers | EP | `#333333` | <span class="swatch" style="background:#333333"></span> |
| Manningham | MNA | `#0088aa` | <span class="swatch" style="background:#0088aa"></span> |
| Eastern United | EUN | `#cc4400` | <span class="swatch" style="background:#cc4400"></span> |
| Melbourne East | MENA | `#2255bb` | <span class="swatch" style="background:#2255bb"></span> |
| Gippsland Storm | GIPP | `#006633` | <span class="swatch" style="background:#006633"></span> |
| Casey NA | CASY | `#8b0000` | <span class="swatch" style="background:#8b0000"></span> |


## Specialised Palettes

### Movement waterfall

Colours for player movement waterfall charts in `reporting/theme.py`.

| Key | Hex | Swatch | Usage |
|-----|-----|--------|-------|
| `base` | `#888` | <span class="swatch" style="background:#888"></span> | Previous season total |
| `left` | `#d94040` | <span class="swatch" style="background:#d94040"></span> | Players who left |
| `new` | `#3a9a5b` | <span class="swatch" style="background:#3a9a5b"></span> | New players |
| `current` | `#cc2222` | <span class="swatch" style="background:#cc2222"></span> | Current season total (club colour) |

### Heatmap gradient

Three-stop gradient for win-rate heatmaps.

| Stop | Hex | Swatch |
|------|-----|--------|
| Low | `#d06060` | <span class="swatch" style="background:#d06060"></span> |
| Mid | `#ecd05c` | <span class="swatch" style="background:#ecd05c"></span> |
| High | `#3a9a5b` | <span class="swatch" style="background:#3a9a5b"></span> |

### Finals progression

Background badges for finals grid (`_trends_finals.py`).

| Tier | Background | Swatch | Text |
|------|-----------|--------|------|
| Missed | `#E0E0E0` | <span class="swatch" style="background:#E0E0E0"></span> | `#999` (intentionally muted) |
| Lost SF | `#e8a8a8` | <span class="swatch" style="background:#e8a8a8"></span> | `#6a2020` |
| Lost GF | `#d87070` | <span class="swatch" style="background:#d87070"></span> | `#fff` |
| Premiership | Club colour | | `#fff` |

Section tier gradient (green to blue, L36% to L79%):

| Section | Hex | Swatch |
|---------|-----|--------|
| Section 1 | `#2d8a4e` | <span class="swatch" style="background:#2d8a4e"></span> |
| Section 2 | `#4a9f6e` | <span class="swatch" style="background:#4a9f6e"></span> |
| Section 3 | `#78c2ad` | <span class="swatch" style="background:#78c2ad"></span> |
| Section 4 | `#a8d8ea` | <span class="swatch" style="background:#a8d8ea"></span> |

### Tenure bands

10-step cool blue gradient in `_trends_players.py` (lighter = newer).

| Band | Hex | Swatch |
|------|-----|--------|
| 1 yr | `#d4e8f0` | <span class="swatch" style="background:#d4e8f0"></span> |
| 2 yr | `#a8d8ea` | <span class="swatch" style="background:#a8d8ea"></span> |
| 3 yr | `#78c2ad` | <span class="swatch" style="background:#78c2ad"></span> |
| 4 yr | `#4a9f6e` | <span class="swatch" style="background:#4a9f6e"></span> |
| 5 yr | `#4a7fb5` | <span class="swatch" style="background:#4a7fb5"></span> |
| 6 yr | `#3a6a9f` | <span class="swatch" style="background:#3a6a9f"></span> |
| 7 yr | `#2d5f8a` | <span class="swatch" style="background:#2d5f8a"></span> |
| 8 yr | `#1f4e7a` | <span class="swatch" style="background:#1f4e7a"></span> |
| 9 yr | `#1a3a5f` | <span class="swatch" style="background:#1a3a5f"></span> |
| 10+ yr | `#0f2440` | <span class="swatch" style="background:#0f2440"></span> |

Bands 3--4 share the section tier teal/green colours. Band 5 reuses `COLOURS[0]` blue.


## PDF Colours

CSS variables defined in `:root` of `pdf/styles/style.css`. Override any variable in a theme overlay to re-skin the entire document.

### Core palette

| Variable | Hex | Swatch | Usage |
|----------|-----|--------|-------|
| `--color-text` | `#333` | <span class="swatch" style="background:#333"></span> | Body text |
| `--color-heading` | `#000` | <span class="swatch" style="background:#000"></span> | Heading text |
| `--color-link` | `#2c5282` | <span class="swatch" style="background:#2c5282"></span> | Hyperlinks (muted navy) |

### Table chrome

| Variable | Hex | Swatch | Usage |
|----------|-----|--------|-------|
| `--color-border` | `#555` | <span class="swatch" style="background:#555"></span> | Cell borders |
| `--color-border-heavy` | `#444` | <span class="swatch" style="background:#444"></span> | Header bottom border |
| `--color-border-light` | `#bbb` | <span class="swatch" style="background:#bbb"></span> | Section divider borders |
| `--color-header-bg` | `#e8e8e8` | <span class="swatch" style="background:#e8e8e8"></span> | `<th>` background |
| `--color-section-bg` | `#f2f2f2` | <span class="swatch" style="background:#f2f2f2; border:1px solid #ddd"></span> | Section divider row background |

<table>
<tr>
<th>Team</th>
<th class="ctr">P</th>
<th class="ctr">W</th>
<th class="ctr">L</th>
<th class="ctr">Pts</th>
</tr>
<tr class="highlight">
<td>Warrandyte 1</td>
<td class="ctr">14</td>
<td class="ctr">10</td>
<td class="ctr">3</td>
<td class="ctr">42</td>
</tr>
<tr>
<td>Eltham 1</td>
<td class="ctr">14</td>
<td class="ctr">8</td>
<td class="ctr">5</td>
<td class="ctr">34</td>
</tr>
<tr>
<td>Donvale 1</td>
<td class="ctr">14</td>
<td class="ctr">5</td>
<td class="ctr">8</td>
<td class="ctr">22</td>
</tr>
</table>

Highlighted row shows `--color-highlight` (tracked team). Header uses `--color-header-bg` with `--color-border-heavy` bottom border. Cells use `--color-border`.

### Row highlights -- regrading

Three-tier system with green/pink symmetry. Pink is intentionally over-saturated to compensate for weaker perceptual vividness of red/pink vs green at equal HSL saturation.

| Tier | Up | Swatch | Variable | Down | Swatch | Variable | Symmetry |
|------|----|--------|----------|------|--------|----------|----------|
| Strong | `#a8dda8` | <span class="swatch" style="background:#a8dda8"></span> | `--color-up` | `#ddb0a8` | <span class="swatch" style="background:#ddb0a8"></span> | `--color-down` | S44% L76% -- perfect |
| Moderate | `#cce8cc` | <span class="swatch" style="background:#cce8cc"></span> | `--color-mod-up` | `#e8ccc6` | <span class="swatch" style="background:#e8ccc6"></span> | `--color-mod-down` | L85% -- 5pp pink bias |
| Watch | `#e0f0e0` | <span class="swatch" style="background:#e0f0e0"></span> | `--color-watch-up` | `#f0dedb` | <span class="swatch" style="background:#f0dedb"></span> | `--color-watch-down` | L90% -- 7pp pink bias |

### Row highlights -- tracked team

| Variable | Hex | Swatch | Usage |
|----------|-----|--------|-------|
| `--color-highlight` | `#d8e1ee` | <span class="swatch" style="background:#d8e1ee"></span> | Tracked team row (light blue) |

### Row highlights -- verdict

| Verdict | Variable | Hex | Swatch | Reuses |
|---------|----------|-----|--------|--------|
| Success | `--color-verdict-ok` | `#e0f0e0` | <span class="swatch" style="background:#e0f0e0"></span> | = `--color-watch-up` |
| Warning | `--color-verdict-warn` | `#fff3cd` | <span class="swatch" style="background:#fff3cd"></span> | Unique -- warm amber |
| Failure | `--color-verdict-fail` | `#f0dedb` | <span class="swatch" style="background:#f0dedb"></span> | = `--color-watch-down` |

### Risk cells

| Level | Variable | Hex | Swatch | Reuses |
|-------|----------|-----|--------|--------|
| Low (<25%) | `--color-up` | `#a8dda8` | <span class="swatch" style="background:#a8dda8"></span> | = strong move-up |
| Medium (25--49%) | `--color-risk-med` | `#fff3e0` | <span class="swatch" style="background:#fff3e0; border:1px solid #ddd"></span> | Unique -- light amber |
| High (>=50%) | `--color-down` | `#ddb0a8` | <span class="swatch" style="background:#ddb0a8"></span> | = strong move-down |

### Blockquote callouts

Six-tier cool-to-warm progression. Border colours are dark (L25--55%); tints are very light (L93--97%).

| Tier | Border | Swatch | Variable | Background | Swatch | Variable |
|------|--------|--------|----------|------------|--------|----------|
| Default | `#666` | <span class="swatch" style="background:#666"></span> | `--color-default` | `#f5f5f5` | <span class="swatch" style="background:#f5f5f5; border:1px solid #ddd"></span> | `--color-default-tint` |
| Info / Note | `#1e3a5f` | <span class="swatch" style="background:#1e3a5f"></span> | `--color-accent` | `#edf1f7` | <span class="swatch" style="background:#edf1f7; border:1px solid #ddd"></span> | `--color-accent-tint` |
| Tip | `#1a7a6d` | <span class="swatch" style="background:#1a7a6d"></span> | `--color-tip` | `#e8f6f3` | <span class="swatch" style="background:#e8f6f3; border:1px solid #ddd"></span> | `--color-tip-tint` |
| Important | `#6b3fa0` | <span class="swatch" style="background:#6b3fa0"></span> | `--color-important` | `#f0e8f5` | <span class="swatch" style="background:#f0e8f5; border:1px solid #ddd"></span> | `--color-important-tint` |
| Caution | `#946b00` | <span class="swatch" style="background:#946b00"></span> | `--color-caution` | `#fef9e7` | <span class="swatch" style="background:#fef9e7; border:1px solid #ddd"></span> | `--color-caution-tint` |
| Warning | `#d94040` | <span class="swatch" style="background:#d94040"></span> | `--color-warn` | `#fdf0f0` | <span class="swatch" style="background:#fdf0f0; border:1px solid #ddd"></span> | `--color-warn-tint` |

### Result text classes

CSS classes in `style.css`, applied automatically by `table_transforms.py`.

| Class | Hex | Swatch | Constant | Contrast |
|-------|-----|--------|----------|----------|
| `.result-win` | `#32854f` | <span class="swatch" style="background:#32854f"></span> | `COLOUR_POSITIVE_TEXT` | 4.6:1 |
| `.result-loss` | `#c43c3c` | <span class="swatch" style="background:#c43c3c"></span> | `COLOUR_NEGATIVE_TEXT` | 4.6:1 |
| `.result-draw` | `#767676` | <span class="swatch" style="background:#767676"></span> | `COLOUR_NEUTRAL_TEXT` | 4.5:1 |

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
| `--color-muted` | `#999` | <span class="swatch" style="background:#999"></span> | Page numbers, light text |
| `--color-rule` | `#ddd` | <span class="swatch" style="background:#ddd"></span> | Horizontal rules |
| `--color-code-bg` | `#f4f4f4` | <span class="swatch" style="background:#f4f4f4; border:1px solid #ddd"></span> | Code / pre background |


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

| Team | P | W | L | Pts |
|------|:-:|:-:|:-:|:-:|
| Warrandyte 1 | 14 | 10 | 3 | 42 |
| Eltham 1 | 14 | 8 | 5 | 34 |

**Compact table** (td 7.5pt, th 8pt, padding 2pt 4pt):

<table style="font-size:7.5pt; line-height:1.25;">
<tr>
<th style="padding:2pt 4pt">Team</th>
<th class="ctr" style="padding:2pt 4pt">P</th>
<th class="ctr" style="padding:2pt 4pt">W</th>
<th class="ctr" style="padding:2pt 4pt">L</th>
<th class="ctr" style="padding:2pt 4pt">Pts</th>
</tr>
<tr>
<td style="padding:2pt 4pt">Warrandyte 1</td>
<td class="ctr" style="padding:2pt 4pt">14</td>
<td class="ctr" style="padding:2pt 4pt">10</td>
<td class="ctr" style="padding:2pt 4pt">3</td>
<td class="ctr" style="padding:2pt 4pt">42</td>
</tr>
<tr>
<td style="padding:2pt 4pt">Eltham 1</td>
<td class="ctr" style="padding:2pt 4pt">14</td>
<td class="ctr" style="padding:2pt 4pt">8</td>
<td class="ctr" style="padding:2pt 4pt">5</td>
<td class="ctr" style="padding:2pt 4pt">34</td>
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
