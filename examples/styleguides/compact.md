---
title: "Compact Theme — Style Guide"
subtitle: "Tighter table padding for dense data documents"
theme: compact
h2_page_break: true
toc: false
---

## Overview

The **compact theme** is orthogonal to the others — it overrides only
table-cell padding and font sizes, leaving everything else (palette,
fonts, headings, callouts) at the bundled defaults.

Use compact when you need more rows per page than the standard 9pt/3.5pt
treatment allows, but don't need any other styling. The other themes
already include their own table density tweaks (regrading is similarly
tight, wnc takes the bundled padding); compact stands alone.

What changes from bundled defaults:

| Property | Bundled | Compact |
|----------|---------|---------|
| Table font-size | 9pt | 7.5pt |
| Table line-height | 1.4 | 1.25 |
| Header font-size | 8.5pt | 8pt |
| Cell padding | 3.5pt × 5pt | 2pt × 4pt |

Everything else inherits from the bundled `style.css` — same fonts, same
callout colours, same headings.


## Side-by-side comparison

A schedule table at compact density:

| Day | Session | Duration | TSS | Notes |
|-----|---------|---------:|----:|-------|
| Mon | Active Recovery | 0:35 | 18 | Walk + balance |
| Tue | Foundation Strength | 1:00 | 60 | Full circuit |
| Wed | Z2 Aerobic Base Run/Hike | 1:15 | 68 | Hilly terrain |
| Thu | Z1 Recovery Run/Walk | 0:40 | 27 | Easy on flats |
| Fri | Foundation Strength + Walk | 1:25 | 73 | + 25 min walk |
| Sat | Z2 Hike Hilly Terrain | 1:30 | 83 | Within Z2 |
| Sun | Z2 Hike (2,500ft gain) | 3:00 | 173 | Long session |

A ladder at compact density:

| Team             | P  | W  | L  | D | GF  | GA  | %     |
|------------------|----|----|----|---|-----|-----|-------|
| WNC Kangaroos    | 12 | 11 | 1  | 0 | 312 | 86  | 362.8 |
| WNC Wallabies    | 12 | 8  | 4  | 0 | 244 | 187 | 130.5 |
| WNC Possums      | 11 | 7  | 3  | 1 | 198 | 162 | 122.2 |
| WNC Bilbies      | 12 | 5  | 6  | 1 | 178 | 195 | 91.3  |
| WNC Echidnas     | 11 | 4  | 7  | 0 | 154 | 211 | 73.0  |
| WNC Quokkas      | 12 | 1  | 11 | 0 | 132 | 305 | 43.3  |


## Everything else is bundled defaults

Headings, body type, callouts, lists — all unchanged from the bundle.

> **Note:** A note callout in standard navy.

> **Warning:** A warning callout in standard red.

A bulleted list:

- First item
- Second item
- Third item

A task list:

- [ ] Unchecked
- [x] Checked
