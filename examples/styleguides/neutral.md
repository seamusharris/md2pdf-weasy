---
title: "Neutral Theme — Style Guide"
subtitle: "Bundled defaults with no theme overrides"
theme: neutral
h2_page_break: true
toc: false
---

## Overview

The **neutral theme** is effectively a marker — its CSS file is
near-empty, deliberately. Selecting `theme: neutral` in front matter
signals "this document uses the bundle's defaults, no domain accents."

This style guide therefore shows what the bundled `style.css` provides
out of the box — the substrate every other theme layers on top of.

- **Body type:** Minion Pro (Caption optical at table sizes)
- **Headings:** Myriad Pro
- **Link colour:** muted navy (`#2c5282` — bundled default)
- **Warning red:** `#d94040` (bundled default)

If you're starting a new project and haven't picked a brand yet, neutral
is the right starting point.


## Callout palette (bundled)

Five tiers. These appear in every theme — the wnc and regrading themes
keep them; the alpine theme overrides only the warn red.

<table style="border: none">
<tr>
<td style="background: var(--color-accent); color: white; width: 100px; padding: 6mm 3mm; text-align: center"><strong>info</strong></td>
<td style="background: var(--color-accent-tint); padding: 6mm 3mm; text-align: center; width: 100px">info-tint</td>
<td style="padding-left: 4mm"><code>#1e3a5f</code> / <code>#edf1f7</code></td>
</tr>
<tr>
<td style="background: var(--color-tip); color: white; width: 100px; padding: 6mm 3mm; text-align: center"><strong>tip</strong></td>
<td style="background: var(--color-tip-tint); padding: 6mm 3mm; text-align: center; width: 100px">tip-tint</td>
<td style="padding-left: 4mm"><code>#1a7a6d</code> / <code>#e8f6f3</code></td>
</tr>
<tr>
<td style="background: var(--color-important); color: white; width: 100px; padding: 6mm 3mm; text-align: center"><strong>important</strong></td>
<td style="background: var(--color-important-tint); padding: 6mm 3mm; text-align: center; width: 100px">important-tint</td>
<td style="padding-left: 4mm"><code>#6b3fa0</code> / <code>#f0e8f5</code></td>
</tr>
<tr>
<td style="background: var(--color-caution); color: white; width: 100px; padding: 6mm 3mm; text-align: center"><strong>caution</strong></td>
<td style="background: var(--color-caution-tint); padding: 6mm 3mm; text-align: center; width: 100px">caution-tint</td>
<td style="padding-left: 4mm"><code>#946b00</code> / <code>#fef9e7</code></td>
</tr>
<tr>
<td style="background: var(--color-warn); color: white; width: 100px; padding: 6mm 3mm; text-align: center"><strong>warning</strong></td>
<td style="background: var(--color-warn-tint); padding: 6mm 3mm; text-align: center; width: 100px">warning-tint</td>
<td style="padding-left: 4mm"><code>#d94040</code> / <code>#fdf0f0</code></td>
</tr>
</table>


## Typography

Body text at 10pt, line-height 1.45. Inline `code`, **bold**, *italic*,
[hyperlinks](https://example.com). The pipeline upgrades ASCII typography
to Unicode: em -- dashes, arrows ->, digit ranges 6-8, smart "quotes",
and ellipses... all converted automatically.

### Heading hierarchy

The bundled hierarchy is h1 → h2 → h3 → h4 with sizes 22 / 17 / 14 / 12pt,
all in Myriad Pro 700 except h3/h4 which step down to 600 for a softer
two-tier feel.

#### h4 example

Sub-subsection. Same Myriad family, 600 weight, 12pt.


## Callouts

> **Note:** Info callout — navy border, light navy background.

> **Tip:** Tip callout — teal.

> **Important:** Important callout — purple.

> **Caution:** Caution callout — amber.

> **Warning:** Warning callout — red. The neutral theme keeps the bundled
> `#d94040` red rather than overriding to a different shade.


## Tables

Bundled table styling: muted grey borders, light-grey header band, left-
aligned by default, numeric columns auto-right-aligned.

| Day | Session | Duration | TSS |
|-----|---------|---------:|----:|
| Mon | Active Recovery | 0:35 | 18 |
| Tue | Foundation Strength | 1:00 | 60 |
| Wed | Z2 Aerobic Base | 1:15 | 68 |
| Thu | Recovery Walk | 0:40 | 27 |
| Fri | Foundation Strength | 1:25 | 73 |
| Sat | Z2 Hike | 1:30 | 83 |
| Sun | Long Hike (2,500ft gain) | 3:00 | 173 |


## Lists

- Bulleted list at body size
- Second item with `inline code`
- Third item with [a link](https://example.com)

Task lists:

- [ ] Unchecked
- [x] Checked
- [ ] Another unchecked

Definition list:

Term
:   A definition that wraps across multiple lines to show indentation.

Another term
:   Second definition.
