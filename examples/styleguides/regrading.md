---
title: "Regrading Theme — Style Guide"
subtitle: "Data-heavy analysis reports — netball regrading aesthetic"
theme: regrading
h2_page_break: true
toc: false
tables:
  swap-summary:
    css_class: swap-summary
    columns:
      - {name: Section, width: 16}
      - {name: Team, width: 24}
      - {name: Likelihood, width: 16}
      - {name: Risk, width: 16, align: right}
tracked_rows: ["Possums", "Bilbies"]
direction_markers: true
risk_tables: ["swap-summary"]
---

## Overview

The **regrading theme** is for dense analysis reports — promotion/demotion
recommendations, retrospective validation, multi-table per page. Tight
table padding, status-coded rows, tracked-row highlighting.

- **Body type:** Minion Pro (inherits from bundled defaults)
- **Headings:** Myriad Pro
- **Table padding:** tighter than default (2.5pt vs 3.5pt) — fits more
  rows per page without feeling cramped
- **Highlighting:** restates bundled tr.highlight-* / tr.verdict-* styling
  so the intent is explicit at the theme level

Three opt-in features from the package are typically active:
`tracked_rows`, `direction_markers`, `risk_tables`.


## Movement palette

Three tiers per direction — strong, moderate, watch. Three saturation
levels from a saturated pastel down to a very light tint.

<table style="border: none">
<tr>
<td style="background: var(--color-up); padding: 6mm 3mm; text-align: center; width: 110px; font-weight: bold">up</td>
<td style="background: var(--color-mod-up); padding: 6mm 3mm; text-align: center; width: 110px; font-weight: bold">mod-up</td>
<td style="background: var(--color-watch-up); padding: 6mm 3mm; text-align: center; width: 110px">watch-up</td>
</tr>
<tr>
<td style="background: var(--color-down); padding: 6mm 3mm; text-align: center; width: 110px; font-weight: bold">down</td>
<td style="background: var(--color-mod-down); padding: 6mm 3mm; text-align: center; width: 110px; font-weight: bold">mod-down</td>
<td style="background: var(--color-watch-down); padding: 6mm 3mm; text-align: center; width: 110px">watch-down</td>
</tr>
</table>

`up #a8dda8` · `mod-up #cce8cc` · `watch-up #e0f0e0`
`down #ddb0a8` · `mod-down #e8ccc6` · `watch-down #f0dedb`

Strong and moderate tiers also bold the row text; watch tier doesn't
(it's deliberately subtle).


## Verdict palette

For retrospective validation tables.

<table style="border: none">
<tr>
<td style="background: var(--color-verdict-ok); padding: 8mm 3mm; text-align: center; width: 140px"><strong>verdict-success</strong></td>
<td style="background: var(--color-verdict-warn); padding: 8mm 3mm; text-align: center; width: 140px"><strong>verdict-warning</strong></td>
<td style="background: var(--color-verdict-fail); padding: 8mm 3mm; text-align: center; width: 140px"><strong>verdict-failure</strong></td>
</tr>
</table>


## Tracked-row highlight

The `--color-highlight` (`#d8e1ee` — light navy) is used for rows
containing tracked strings. In this document the front matter sets
`tracked_rows: ["Possums", "Bilbies"]`, so any row containing those
strings gets the highlight.

<table style="border: none">
<tr>
<td style="background: var(--color-highlight); padding: 8mm 3mm; text-align: center; width: 180px"><strong>tracked-row highlight</strong></td>
<td style="padding-left: 4mm">light navy<br><code>#d8e1ee</code></td>
</tr>
</table>


## Promotion / demotion table

Direction markers in bold cells become row colours. Six valid
combinations: `{up}` / `{up}{mod}` / `{up}{watch}` and the matching
down variants. `{mod}` and `{watch}` always follow a direction;
they're not recognised on their own.

| Team             | Risk  | Recommendation |
|------------------|------:|----------------|
| **{up}▲ Kangaroos**       | 18% | Promote — strong record, 11W-1L |
| **{up}{mod}▲ Wallabies**  | 28% | Promote — moderate confidence |
| **{up}{watch}Possums**    | 31% | Watch — leaning up, monitor next cycle |
| **{down}{watch}Bilbies**  | 45% | Watch — leaning down, monitor next cycle |
| **{down}{mod}▼ Echidnas** | 58% | Demote — moderate confidence |
| **{down}▼ Quokkas**       | 73% | Demote — struggling, 1W-11L |


## Risk-coded cells

The `risk_tables: ["swap-summary"]` front-matter setting tells the
pipeline to scan the last column of any table with the `swap-summary`
CSS class. Percentages get `.risk-high` (≥50%, red), `.risk-med`
(25-49%, amber), `.risk-low` (<25%, green) cell backgrounds.

| Section | Team             | Likelihood | Risk  |
|---------|------------------|------------|------:|
| 11U S1  | Kangaroos        | Likely     | 18%   |
| 13U S2  | Wallabies        | Possible   | 32%   |
| 15U S1  | Possums          | Likely     | 67%   |
| 17U S2  | Bilbies          | Possible   | 45%   |
| Open A  | Quokkas          | Unlikely   | 12%   |


## Verdict / retrospective table

Inline HTML for `tr.verdict-*` classes. Used in retrospective validation
reports.

<table>
<thead>
<tr><th>Decision</th><th>Outcome</th><th>Notes</th></tr>
</thead>
<tbody>
<tr class="verdict-success"><td>Promote Kangaroos</td><td>Won 11 of 12</td><td>Right call — dominant in new section</td></tr>
<tr class="verdict-success"><td>Promote Wallabies</td><td>Won 8 of 12</td><td>Right call — competitive immediately</td></tr>
<tr class="verdict-warning"><td>Hold Possums</td><td>7-3-1 record</td><td>Borderline — could have gone either way</td></tr>
<tr class="verdict-warning"><td>Hold Bilbies</td><td>5-6-1 record</td><td>Borderline — section is fast</td></tr>
<tr class="verdict-failure"><td>Promote Echidnas</td><td>4-7 record</td><td>Wrong call — should have held</td></tr>
<tr class="verdict-failure"><td>Promote Quokkas</td><td>1-11 record</td><td>Wrong call — struggled badly</td></tr>
</tbody>
</table>


## Callouts

> **Note:** Standard callouts inherit from the bundled palette.

> **Warning:** Watch for promoted teams with <25% win rates in their new
> section — flag for review at the next regrading cycle.


## Direction-arrow callouts

A blockquote starting with `▲` or `▼` is classified automatically as an
`up` or `down` callout. The arrow stays in the rendered text; the class
gives the callout its direction-tinted border and background. Themes that
don't define `--color-up` / `--color-down` leave the callout in default
styling.

> ▲ **Wallabies** — 1st of 8 · 9W–0L · GA% 312 · +18 · Strong promote signal.

> ▼ **Quokkas** — 4th of 4 · 0W–3L · GA% 40 · -18 · Lost to 1st, 2nd, 3rd.

A keyword still wins over the arrow, so `> ▼ **Warning:** ...` is styled
as a warning, not a down callout.
