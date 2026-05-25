---
title: "Alpine Theme — Style Guide"
subtitle: "Outdoor / training-manual aesthetic"
theme: alpine
h2_page_break: true
toc: false
---

## Overview

The **alpine theme** is muted and restrained. A single warning red is the
only loud colour; everything else is greys, slates, and earth tones. Suited
to documents where content carries the meaning and the type should stay
out of the way — training manuals, reference cards, journals.

- **Body type:** Minion Pro (Caption / Regular / Subhead / Display opticals)
- **Headings:** Myriad Pro
- **Link colour:** muted navy (`#14376b`)
- **Warning red:** `#c0392b` (slightly orange-leaning, alpine-specific)

Sub-headings are softened to weight 600 (vs the bundled 700 default for
h1/h2), giving a two-tier hierarchy that reads less blocky than all-bold.


## Palette

### Core

<table style="border: none">
<tr>
<td style="background: var(--color-link); color: white; width: 90px; padding: 8mm 3mm; text-align: center; border-radius: 2pt"><strong>link</strong></td>
<td style="padding-left: 4mm">muted navy<br><code>#14376b</code></td>
<td style="background: var(--color-warn); color: white; width: 90px; padding: 8mm 3mm; text-align: center; border-radius: 2pt"><strong>warn</strong></td>
<td style="padding-left: 4mm">alpine red<br><code>#c0392b</code></td>
<td style="background: var(--color-accent); color: white; width: 90px; padding: 8mm 3mm; text-align: center; border-radius: 2pt"><strong>accent</strong></td>
<td style="padding-left: 4mm">info navy<br><code>#1e3a5f</code></td>
</tr>
</table>

### Session-type palette

Used wherever a session is categorised by what kind of work it is — day
cards in the daily reference, programme overview tables. All four sit at
roughly L=27-41% with saturations 15-34% — coherent muted family.

<table style="border: none">
<tr>
<td style="background: var(--color-session-recovery); color: white; width: 120px; padding: 8mm 3mm; text-align: center; border-radius: 2pt"><strong>recovery</strong></td>
<td style="padding-left: 4mm; padding-right: 8mm">wet-stone teal<br><code>#5a7872</code></td>
<td style="background: var(--color-session-strength); color: white; width: 120px; padding: 8mm 3mm; text-align: center; border-radius: 2pt"><strong>strength</strong></td>
<td style="padding-left: 4mm">muted terracotta<br><code>#875E4A</code></td>
</tr>
<tr>
<td style="background: var(--color-session-aerobic); color: white; width: 120px; padding: 8mm 3mm; text-align: center; border-radius: 2pt"><strong>aerobic</strong></td>
<td style="padding-left: 4mm; padding-right: 8mm">slate sky<br><code>#4a6a87</code></td>
<td style="background: var(--color-session-long-hike); color: white; width: 120px; padding: 8mm 3mm; text-align: center; border-radius: 2pt"><strong>long-hike</strong></td>
<td style="padding-left: 4mm">deep evergreen<br><code>#2d5c3e</code></td>
</tr>
</table>

### Traffic-light palette

Status row tinting for daily monitoring tables. Dark colours for text,
light tints for backgrounds.

<table style="border: none">
<tr>
<td style="background: var(--color-tl-green); color: white; width: 100px; padding: 6mm 3mm; text-align: center"><strong>tl-green</strong></td>
<td style="background: var(--color-tl-green-tint); padding: 6mm 3mm; text-align: center">tl-green-tint</td>
<td style="padding-left: 4mm"><code>#2d7a4a</code> / <code>#e8f3eb</code></td>
</tr>
<tr>
<td style="background: var(--color-tl-amber); color: white; width: 100px; padding: 6mm 3mm; text-align: center"><strong>tl-amber</strong></td>
<td style="background: var(--color-tl-amber-tint); padding: 6mm 3mm; text-align: center">tl-amber-tint</td>
<td style="padding-left: 4mm"><code>#b87333</code> / <code>#fdf2e3</code></td>
</tr>
<tr>
<td style="background: var(--color-tl-red); color: white; width: 100px; padding: 6mm 3mm; text-align: center"><strong>tl-red</strong></td>
<td style="background: var(--color-tl-red-tint); padding: 6mm 3mm; text-align: center">tl-red-tint</td>
<td style="padding-left: 4mm"><code>#c0392b</code> / <code>#fbe9e7</code></td>
</tr>
</table>


## Typography

Body text sits at 10pt with 1.45 line-height. The Caption optical kicks in
automatically for table cells at 9pt. Italics like *this* and **bold** like
**this** read clearly. A [hyperlink](https://example.com) takes on the
muted navy link colour. Inline `code` uses a monospace stack. Em -- dashes
and digit ranges 6-8 are upgraded by the ASCII-to-Unicode pass.

### Heading hierarchy

h3 and h4 below — semibold (600) rather than bold (700) for a softer
sub-tier.

#### h4 sub-subsection

The hierarchy is: h1 22pt bold → h2 17pt bold → h3 14pt semibold → h4 12pt
semibold. Size carries most of the weight, weight differentiation handles
the rest.


## Callouts

> **Note:** Informational callout. Navy border, light navy background. Use
> for context, cross-references, and background that supports the main
> flow without breaking it.

> **Tip:** Suggestion callout. Teal border. Use for shortcuts or "you
> could also..." asides.

> **Important:** High-priority callout. Purple border. Use for things the
> reader must understand.

> **Caution:** Heads-up callout. Amber border. Use for situations where
> something could go wrong.

> **Warning:** Hard rule callout. Red border with alpine red. Use for
> errors and absolute requirements.


## Tables

Cells use Minion Caption at 9pt for legibility at small sizes. Headers
use Myriad Pro semibold, uppercase, slightly tracked.

### Weekly schedule

| Day | Session | Duration | TSS |
|-----|---------|---------:|----:|
| Mon | Active Recovery — Walk + Balance | 0:35 | 18 |
| Tue | Foundation Strength | 1:00 | 60 |
| Wed | Z2 Aerobic Base Run/Hike (hilly) | 1:15 | 68 |
| Thu | Z1 Recovery Run/Walk | 0:40 | 27 |
| Fri | Foundation Strength + Walk | 1:25 | 73 |
| Sat | Z2 Hike Hilly Terrain | 1:30 | 83 |
| Sun | Z2 Hike Hilly Terrain (2,500ft gain) | 3:00 | 173 |

### Traffic-light status

The alpine theme's `tr.tl-*` classes tint rows by status. Used in the
prep & recovery program's daily monitoring guide.

<table>
<thead>
<tr><th>Status</th><th>Criteria</th><th>Action</th></tr>
</thead>
<tbody>
<tr class="tl-green"><td>GREEN</td><td>Stiffness clears within 10 min</td><td>Full training as planned</td></tr>
<tr class="tl-amber"><td>AMBER</td><td>Stiffness takes 10-30 min to clear</td><td>Reduce intensity, skip long calf stretches</td></tr>
<tr class="tl-red"><td>RED</td><td>Pain or stiffness &gt;30 min</td><td>Rest day or very light activity only</td></tr>
</tbody>
</table>


## Lists

A bulleted list at 10pt body size:

- First item with substantive content
- Second item with `inline code` mixed in
- Third item with [a link](https://example.com)

A task list — checkboxes intentionally tickable on paper:

- [ ] Unchecked task
- [x] Checked task
- [ ] Third task

A definition list:

Term
:   Definition of the term, spanning more than one line so wrap behaviour
    is visible.

Another term
:   A second definition with different content.
