---
title: "Typography Options"
subtitle: "Before/after comparison of remaining typographic decisions"
toc: true
toc_depth: 2
h2_page_break: true
---

## How to read this doc

Each section pairs the **current** package default with a **proposed** alternative. Both blocks are rendered side by side on the page (or stacked) so you can compare them directly. The "current" block uses today's bundled style; the "proposed" block fakes the alternative via inline styles to simulate what would land if we adopted it.

After reviewing, tell me which proposals to apply and I'll roll them into the base stylesheet.


## Option 1 — H1 (document title)

The document title currently uses Myriad Pro Bold at 22pt. The proposed alternative is Minion Display Bold at 22pt — Adobe's Display optical cut, drawn specifically for titling sizes with wider counters, more elegant terminals, and a calmer presence. Pairs naturally with the Minion body. Shifts the document's typographic identity from "modern sans-titled" to "book-like serif".

<div style="text-align:center; margin: 8mm 0 4mm 0; padding: 6mm 0; border-top: 0.5pt solid #ddd; border-bottom: 0.5pt solid #ddd;">
  <div style="font-family: 'Myriad Pro', sans-serif; font-weight: 700; font-size: 22pt; color: #000; letter-spacing: 0.005em;">Quarterly Review — Q2 2026</div>
  <div style="font-family: 'Myriad Pro', sans-serif; font-weight: 400; font-size: 8pt; color: #999; margin-top: 4mm; letter-spacing: 0.05em; text-transform: uppercase;">Current — Myriad Pro Bold 22pt</div>
</div>

<div style="text-align:center; margin: 4mm 0 8mm 0; padding: 6mm 0; border-top: 0.5pt solid #ddd; border-bottom: 0.5pt solid #ddd;">
  <div style="font-family: 'Minion Display', serif; font-weight: 700; font-size: 22pt; color: #000;">Quarterly Review — Q2 2026</div>
  <div style="font-family: 'Myriad Pro', sans-serif; font-weight: 400; font-size: 8pt; color: #999; margin-top: 4mm; letter-spacing: 0.05em; text-transform: uppercase;">Proposed — Minion Display Bold 22pt</div>
</div>


## Option 2 — Subtitle (paired with Option 1)

If H1 goes serif (Option 1 accepted), the subtitle should follow to match — the proposal is Minion Display Italic 13pt. If H1 stays sans, keep the current Myriad Pro Light Italic 11pt.

<div style="text-align:center; margin: 8mm 0 4mm 0; padding: 6mm 0; border-top: 0.5pt solid #ddd; border-bottom: 0.5pt solid #ddd;">
  <div style="font-family: 'Myriad Pro', sans-serif; font-weight: 700; font-size: 22pt; color: #000; letter-spacing: 0.005em;">Quarterly Review — Q2 2026</div>
  <div style="font-family: 'Myriad Pro', sans-serif; font-weight: 300; font-style: italic; font-size: 11pt; color: #999; margin-top: 3mm;">Performance commentary and outlook</div>
  <div style="font-family: 'Myriad Pro', sans-serif; font-weight: 400; font-size: 8pt; color: #999; margin-top: 4mm; letter-spacing: 0.05em; text-transform: uppercase;">Current pair — Myriad title + Myriad Light Italic subtitle</div>
</div>

<div style="text-align:center; margin: 4mm 0 8mm 0; padding: 6mm 0; border-top: 0.5pt solid #ddd; border-bottom: 0.5pt solid #ddd;">
  <div style="font-family: 'Minion Display', serif; font-weight: 700; font-size: 22pt; color: #000;">Quarterly Review — Q2 2026</div>
  <div style="font-family: 'Minion Display', serif; font-weight: 400; font-style: italic; font-size: 13pt; color: #555; margin-top: 3mm;">Performance commentary and outlook</div>
  <div style="font-family: 'Myriad Pro', sans-serif; font-weight: 400; font-size: 8pt; color: #999; margin-top: 4mm; letter-spacing: 0.05em; text-transform: uppercase;">Proposed pair — Minion Display Bold + Minion Display Italic</div>
</div>


## Option 5 — H4

Currently H4 is Myriad Pro Semibold (600) at 12pt — same family and weight as H2/H3, distinguished only by size. Two proposed alternatives.

### 5a — Regular weight with widened letter-spacing

Drops the weight from Semibold to Regular (400) and widens letter-spacing to 0.06em. Reads as a quiet sub-heading rather than a stacked-bold tier.

<div style="margin: 6mm 0 4mm 0; padding: 4mm 6mm; border-top: 0.5pt solid #ddd; border-bottom: 0.5pt solid #ddd;">
  <div style="font-family: 'Myriad Pro', sans-serif; font-weight: 600; font-size: 12pt; color: #000; letter-spacing: 0.005em;">Methodology &amp; assumptions</div>
  <div style="font-family: 'Minion Pro', serif; font-size: 11pt; line-height: 1.45; color: #333; margin-top: 2mm;">Each team is scored on win-loss record, goal average percentage, average margin, and how they compare to teams in adjacent sections.</div>
  <div style="font-family: 'Myriad Pro', sans-serif; font-weight: 400; font-size: 8pt; color: #999; margin-top: 4mm; letter-spacing: 0.05em; text-transform: uppercase;">Current — Myriad Pro Semibold 12pt</div>
</div>

<div style="margin: 4mm 0 6mm 0; padding: 4mm 6mm; border-top: 0.5pt solid #ddd; border-bottom: 0.5pt solid #ddd;">
  <div style="font-family: 'Myriad Pro', sans-serif; font-weight: 400; font-size: 12pt; color: #000; letter-spacing: 0.06em;">Methodology &amp; assumptions</div>
  <div style="font-family: 'Minion Pro', serif; font-size: 11pt; line-height: 1.45; color: #333; margin-top: 2mm;">Each team is scored on win-loss record, goal average percentage, average margin, and how they compare to teams in adjacent sections.</div>
  <div style="font-family: 'Myriad Pro', sans-serif; font-weight: 400; font-size: 8pt; color: #999; margin-top: 4mm; letter-spacing: 0.05em; text-transform: uppercase;">Proposed 5a — Regular 12pt, wide tracking</div>
</div>

### 5b — Small caps via font-variant

Keeps Semibold but switches to all-small-caps (renders as a horizontal label).

<div style="margin: 6mm 0; padding: 4mm 6mm; border-top: 0.5pt solid #ddd; border-bottom: 0.5pt solid #ddd;">
  <div style="font-family: 'Myriad Pro', sans-serif; font-weight: 600; font-size: 11pt; color: #000; font-variant-caps: all-small-caps; letter-spacing: 0.04em;">Methodology &amp; assumptions</div>
  <div style="font-family: 'Minion Pro', serif; font-size: 11pt; line-height: 1.45; color: #333; margin-top: 2mm;">Each team is scored on win-loss record, goal average percentage, average margin, and how they compare to teams in adjacent sections.</div>
  <div style="font-family: 'Myriad Pro', sans-serif; font-weight: 400; font-size: 8pt; color: #999; margin-top: 4mm; letter-spacing: 0.05em; text-transform: uppercase;">Proposed 5b — Semibold 11pt small-caps</div>
</div>


## Option 6 — H5 / H6 (currently unstyled)

H5 and H6 don't have explicit rules — they inherit the h1-h6 default (Semibold + browser default size, which means ~10pt for h5 and ~7.5pt for h6, awkward against an 11pt body). The proposal: give them a clear "label" tier using Myriad SemiCondensed Semibold uppercase, letter-spaced. Below h4 in weight presence but above body in semantic role.

<div style="margin: 6mm 0; padding: 4mm 6mm; border-top: 0.5pt solid #ddd; border-bottom: 0.5pt solid #ddd;">
  <div style="font-family: 'Myriad Pro', sans-serif; font-weight: 600; font-size: 10pt; color: #000;">Risk profile</div>
  <div style="font-family: 'Minion Pro', serif; font-size: 11pt; line-height: 1.45; color: #333; margin-top: 1.5mm;">The S1 boundary is structurally harder than other section boundaries.</div>
  <div style="font-family: 'Myriad Pro', sans-serif; font-weight: 400; font-size: 8pt; color: #999; margin-top: 4mm; letter-spacing: 0.05em; text-transform: uppercase;">Current H5 — browser default-ish</div>
</div>

<div style="margin: 6mm 0; padding: 4mm 6mm; border-top: 0.5pt solid #ddd; border-bottom: 0.5pt solid #ddd;">
  <div style="font-family: 'Myriad SemiCondensed', sans-serif; font-weight: 600; font-size: 9.5pt; color: #000; text-transform: uppercase; letter-spacing: 0.08em;">Risk profile</div>
  <div style="font-family: 'Minion Pro', serif; font-size: 11pt; line-height: 1.45; color: #333; margin-top: 2mm;">The S1 boundary is structurally harder than other section boundaries.</div>
  <div style="font-family: 'Myriad Pro', sans-serif; font-weight: 400; font-size: 8pt; color: #999; margin-top: 4mm; letter-spacing: 0.05em; text-transform: uppercase;">Proposed — Myriad SemiCondensed Semibold uppercase letter-spaced</div>
</div>


## Option 8 — Definition list terms (`<dt>`)

Definition terms are currently Bold (700) and inherit the body Minion Pro. Two proposals: stay serif but soften, or go sans for a glossary-book look.

### 8a — Minion Pro Semibold (stay serif, lighter)

<div style="margin: 6mm 0; padding: 4mm 6mm; border-top: 0.5pt solid #ddd; border-bottom: 0.5pt solid #ddd;">
  <dl style="font-size: 9pt; line-height: 1.45;">
    <dt style="font-weight: 700; color: #000; margin-top: 0;">Thriving</dt>
    <dd style="margin-left: 8mm; margin-bottom: 2mm;">Promoted team finished near the top of their new section — top 40%.</dd>
    <dt style="font-weight: 700; color: #000; margin-top: 3mm;">Settled</dt>
    <dd style="margin-left: 8mm;">Demoted team finished in the lower half of their new section.</dd>
  </dl>
  <div style="font-family: 'Myriad Pro', sans-serif; font-weight: 400; font-size: 8pt; color: #999; margin-top: 4mm; letter-spacing: 0.05em; text-transform: uppercase;">Current — Minion Pro Bold 700</div>
</div>

<div style="margin: 6mm 0; padding: 4mm 6mm; border-top: 0.5pt solid #ddd; border-bottom: 0.5pt solid #ddd;">
  <dl style="font-size: 9pt; line-height: 1.45;">
    <dt style="font-weight: 600; color: #000; margin-top: 0;">Thriving</dt>
    <dd style="margin-left: 8mm; margin-bottom: 2mm;">Promoted team finished near the top of their new section — top 40%.</dd>
    <dt style="font-weight: 600; color: #000; margin-top: 3mm;">Settled</dt>
    <dd style="margin-left: 8mm;">Demoted team finished in the lower half of their new section.</dd>
  </dl>
  <div style="font-family: 'Myriad Pro', sans-serif; font-weight: 400; font-size: 8pt; color: #999; margin-top: 4mm; letter-spacing: 0.05em; text-transform: uppercase;">Proposed 8a — Minion Pro Semibold 600</div>
</div>

### 8b — Myriad Pro Semibold (sans terms, serif definitions)

<div style="margin: 6mm 0; padding: 4mm 6mm; border-top: 0.5pt solid #ddd; border-bottom: 0.5pt solid #ddd;">
  <dl style="font-size: 9pt; line-height: 1.45;">
    <dt style="font-family: 'Myriad Pro', sans-serif; font-weight: 600; color: #000; margin-top: 0;">Thriving</dt>
    <dd style="margin-left: 8mm; margin-bottom: 2mm;">Promoted team finished near the top of their new section — top 40%.</dd>
    <dt style="font-family: 'Myriad Pro', sans-serif; font-weight: 600; color: #000; margin-top: 3mm;">Settled</dt>
    <dd style="margin-left: 8mm;">Demoted team finished in the lower half of their new section.</dd>
  </dl>
  <div style="font-family: 'Myriad Pro', sans-serif; font-weight: 400; font-size: 8pt; color: #999; margin-top: 4mm; letter-spacing: 0.05em; text-transform: uppercase;">Proposed 8b — Myriad Pro Semibold (sans/serif pairing)</div>
</div>


## Option 10 — Table section divider rows

The `tr.table-section` class marks rows that act as headings inside a multi-section table. Current treatment: Bold serif body font, section-bg fill, light borders top + bottom. Proposed: Myriad Condensed Bold uppercase letter-spaced — reads as a chapter head inside the table.

<table style="width:100%; border-collapse:collapse; margin: 6mm 0 4mm 0;">
  <thead>
    <tr><th style="background:#e8e8e8; border:0.5pt solid #555; border-bottom:1pt solid #444; padding:3.5pt 5pt;">Team</th><th style="background:#e8e8e8; border:0.5pt solid #555; border-bottom:1pt solid #444; padding:3.5pt 5pt;">P</th><th style="background:#e8e8e8; border:0.5pt solid #555; border-bottom:1pt solid #444; padding:3.5pt 5pt;">W</th><th style="background:#e8e8e8; border:0.5pt solid #555; border-bottom:1pt solid #444; padding:3.5pt 5pt;">L</th><th style="background:#e8e8e8; border:0.5pt solid #555; border-bottom:1pt solid #444; padding:3.5pt 5pt;">Pts</th></tr>
  </thead>
  <tbody>
    <tr><td style="background:#f2f2f2; font-weight:700; border-top:1pt solid #bbb; border-bottom:1pt solid #bbb; padding:3.5pt 5pt;" colspan="5">Section 1</td></tr>
    <tr><td style="border:0.5pt solid #555; padding:3.5pt 5pt;">Warrandyte 1</td><td style="border:0.5pt solid #555; padding:3.5pt 5pt; text-align:center;">14</td><td style="border:0.5pt solid #555; padding:3.5pt 5pt; text-align:center;">10</td><td style="border:0.5pt solid #555; padding:3.5pt 5pt; text-align:center;">3</td><td style="border:0.5pt solid #555; padding:3.5pt 5pt; text-align:center;">42</td></tr>
    <tr><td style="background:#f2f2f2; font-weight:700; border-top:1pt solid #bbb; border-bottom:1pt solid #bbb; padding:3.5pt 5pt;" colspan="5">Section 2</td></tr>
    <tr><td style="border:0.5pt solid #555; padding:3.5pt 5pt;">Eltham 1</td><td style="border:0.5pt solid #555; padding:3.5pt 5pt; text-align:center;">14</td><td style="border:0.5pt solid #555; padding:3.5pt 5pt; text-align:center;">8</td><td style="border:0.5pt solid #555; padding:3.5pt 5pt; text-align:center;">5</td><td style="border:0.5pt solid #555; padding:3.5pt 5pt; text-align:center;">34</td></tr>
  </tbody>
</table>

<div style="font-family: 'Myriad Pro', sans-serif; font-weight: 400; font-size: 8pt; color: #999; margin-top: 2mm; letter-spacing: 0.05em; text-transform: uppercase;">Current — bold serif on section-bg</div>

<table style="width:100%; border-collapse:collapse; margin: 6mm 0 4mm 0;">
  <thead>
    <tr><th style="background:#e8e8e8; border:0.5pt solid #555; border-bottom:1pt solid #444; padding:3.5pt 5pt;">Team</th><th style="background:#e8e8e8; border:0.5pt solid #555; border-bottom:1pt solid #444; padding:3.5pt 5pt;">P</th><th style="background:#e8e8e8; border:0.5pt solid #555; border-bottom:1pt solid #444; padding:3.5pt 5pt;">W</th><th style="background:#e8e8e8; border:0.5pt solid #555; border-bottom:1pt solid #444; padding:3.5pt 5pt;">L</th><th style="background:#e8e8e8; border:0.5pt solid #555; border-bottom:1pt solid #444; padding:3.5pt 5pt;">Pts</th></tr>
  </thead>
  <tbody>
    <tr><td style="background:#f2f2f2; font-family:'Myriad Condensed', sans-serif; font-weight:700; font-size:9pt; text-transform:uppercase; letter-spacing:0.08em; border-top:1pt solid #bbb; border-bottom:1pt solid #bbb; padding:3pt 5pt;" colspan="5">Section 1</td></tr>
    <tr><td style="border:0.5pt solid #555; padding:3.5pt 5pt;">Warrandyte 1</td><td style="border:0.5pt solid #555; padding:3.5pt 5pt; text-align:center;">14</td><td style="border:0.5pt solid #555; padding:3.5pt 5pt; text-align:center;">10</td><td style="border:0.5pt solid #555; padding:3.5pt 5pt; text-align:center;">3</td><td style="border:0.5pt solid #555; padding:3.5pt 5pt; text-align:center;">42</td></tr>
    <tr><td style="background:#f2f2f2; font-family:'Myriad Condensed', sans-serif; font-weight:700; font-size:9pt; text-transform:uppercase; letter-spacing:0.08em; border-top:1pt solid #bbb; border-bottom:1pt solid #bbb; padding:3pt 5pt;" colspan="5">Section 2</td></tr>
    <tr><td style="border:0.5pt solid #555; padding:3.5pt 5pt;">Eltham 1</td><td style="border:0.5pt solid #555; padding:3.5pt 5pt; text-align:center;">14</td><td style="border:0.5pt solid #555; padding:3.5pt 5pt; text-align:center;">8</td><td style="border:0.5pt solid #555; padding:3.5pt 5pt; text-align:center;">5</td><td style="border:0.5pt solid #555; padding:3.5pt 5pt; text-align:center;">34</td></tr>
  </tbody>
</table>

<div style="font-family: 'Myriad Pro', sans-serif; font-weight: 400; font-size: 8pt; color: #999; margin-top: 2mm; letter-spacing: 0.05em; text-transform: uppercase;">Proposed — Myriad Condensed Bold uppercase letter-spaced</div>


## Decision summary

Tell me which to apply (and any tweaks):

- **Option 1** — H1 to Minion Display Bold?  (yes / no / keep)
- **Option 2** — Subtitle to Minion Display Italic? (only meaningful if Option 1 = yes)
- **Option 5** — H4 treatment? (5a regular + tracking / 5b small-caps / keep)
- **Option 6** — H5/H6 label tier? (yes / no)
- **Option 8** — `<dt>` treatment? (8a Minion Semibold / 8b Myriad Semibold / keep Bold)
- **Option 10** — section divider rows? (yes / no)
