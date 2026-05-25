---
title: "Theme Sample"
subtitle: "Comprehensive content for visual review of each bundled theme"
h2_page_break: true
toc: false
tables:
  ladder:
    css_class: ladder
    columns:
      - {name: Team, width: 28, align: left}
      - {name: P}
      - {name: W}
      - {name: L}
      - {name: D}
      - {name: GF}
      - {name: GA}
      - {name: "%"}
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

## Typography and inline formatting

This first section exercises prose-level features. Body text in **bold**, *italic*,
and ***both***. An [external link](https://example.com) renders in the theme's
link colour. Inline `code` uses a monospace font. The pipeline upgrades ASCII
typography automatically: em -- dashes, arrows ->, digit ranges 6-8, "smart
quotes", apostrophes in don't, and ellipses... become proper Unicode.

A bulleted list:

- First item with some content
- Second item with `inline code` mixed in
- Third item with a [link](https://example.com)

A task list (rendered as ticked / unticked boxes):

- [ ] First task — not yet done
- [x] Second task — completed
- [ ] Third task — pending
- [x] Fourth task — also done

A definition list:

Term
:   A definition of the term, possibly spanning more than one line so you
    can see how the indentation handles wrapping body text.

Another term
:   A second definition with different content. Definition lists are useful
    for glossaries, parameter references, or short labelled explanations.

A paragraph using ~~strikethrough~~ and ==highlighted== text to verify the
pymdown-extensions are loaded.


## Callouts

Five callout tiers, cool-to-warm progression. Each is a blockquote starting
with a bold keyword and a colon.

> **Note:** Informational callout in info navy. Useful for context,
> cross-references, or supplementary background that doesn't break the
> reading flow.

> **Tip:** Tip callout in teal. For suggestions, shortcuts, or "you can
> also..." asides that help but aren't critical.

> **Important:** Important callout in purple. For points the reader must
> understand to use the document correctly.

> **Caution:** Caution callout in amber. For heads-up situations where
> something could go wrong if missed.

> **Warning:** Warning callout in red. For hard rules, errors, or things
> that will definitely break if ignored.


## Tables — schedule and progression

Common shapes used in training and reference documents.

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

### Exercise progression

| Level | Exercise | Description |
|------:|----------|-------------|
| 1 | Wall Push-Ups | Hands on wall, body at angle |
| 2 | Incline Push-Ups (high) | Hands on bench or sturdy table |
| 3 | Incline Push-Ups (low) | Hands on chair seat or low step |
| 4 | Knee Push-Ups | Full range of motion from knees |
| 5 | Eccentric Push-Ups | Lower slowly from toes, push up from knees |
| 6 | Full Push-Ups | From toes, full range of motion |


## Tables — sports ladder and fixture

The kinds of tables a sports-reporting project generates. The Ladder uses the
shared `ladder` layout declared in front matter. Rows containing "Possums" or
"Bilbies" are highlighted via the `tracked_rows` front-matter list.

### Season ladder

| Team             | P | W | L | D | GF  | GA  | %     |
|------------------|---|---|---|---|-----|-----|-------|
| WNC Kangaroos    | 12| 11| 1 | 0 | 312 | 86  | 362.8 |
| WNC Wallabies    | 12| 8 | 4 | 0 | 244 | 187 | 130.5 |
| WNC Possums      | 11| 7 | 3 | 1 | 198 | 162 | 122.2 |
| WNC Bilbies      | 12| 5 | 6 | 1 | 178 | 195 | 91.3  |
| WNC Echidnas     | 11| 4 | 7 | 0 | 154 | 211 | 73.0  |
| WNC Quokkas      | 12| 1 | 11| 0 | 132 | 305 | 43.3  |

### Saturday fixture

| Time  | Court | Home          | Away          |
|-------|------:|---------------|---------------|
| 09:00 | 1     | WNC Kangaroos | Other Club    |
| 09:00 | 2     | WNC Wallabies | Other Club    |
| 10:15 | 1     | WNC Possums   | Other Club    |
| 10:15 | 3     | WNC Bilbies   | Other Club    |
| 11:30 | 2     | WNC Echidnas  | Other Club    |
| 12:45 | 1     | WNC Quokkas   | Other Club    |


## Status, direction markers, and verdicts

Three different highlighting mechanisms.

### Traffic-light status

Status rows tinted via `tr.tl-green / tr.tl-amber / tr.tl-red` classes (HTML
inline). Alpine theme defines the colours; other themes show plain rows
because the variables aren't set.

<table>
<thead>
<tr><th>Status</th><th>Criteria</th><th>Action</th></tr>
</thead>
<tbody>
<tr class="tl-green"><td>GREEN</td><td>Stiffness clears within 10 min</td><td>Full training as planned</td></tr>
<tr class="tl-amber"><td>AMBER</td><td>Stiffness takes 10-30 min to clear</td><td>Reduce intensity</td></tr>
<tr class="tl-red"><td>RED</td><td>Pain or stiffness &gt;30 min</td><td>Rest day or very light only</td></tr>
</tbody>
</table>

### Direction markers in bold cells

The `direction_markers: true` front-matter flag scans bold cells for `{up}`,
`{down}`, `{mod}` markers and applies row classes. The bundled palette
colours these saturated green / pink / lighter shades.

| Team             | Risk  | Recommendation |
|------------------|------:|----------------|
| **{up}▲ Kangaroos** | 18%   | Promote — strong record |
| **{down}▼ Quokkas** | 67%   | Demote — struggling |
| **{mod}Wallabies** | 31%   | Watch — borderline |
| Possums          | 42%   | Hold |

### Verdict rows

For retrospective tables. Inline HTML with `verdict-success / verdict-warning
/ verdict-failure` row classes.

<table>
<thead>
<tr><th>Decision</th><th>Outcome</th><th>Notes</th></tr>
</thead>
<tbody>
<tr class="verdict-success"><td>Promote Kangaroos</td><td>Won 11 of 12</td><td>Right call</td></tr>
<tr class="verdict-warning"><td>Hold Possums</td><td>7-3-1 record</td><td>Borderline</td></tr>
<tr class="verdict-failure"><td>Promote Quokkas</td><td>1-11 record</td><td>Wrong call</td></tr>
</tbody>
</table>


## Risk-coded cells

The `risk_tables: ["swap-summary"]` front-matter list enables percentage
threshold colouring on tables matching that CSS class. Last column shows
risk percentage; cells get `.risk-high` (≥50%, red), `.risk-med` (25-49%,
amber), `.risk-low` (<25%, green) automatically.

| Section | Team             | Likelihood | Risk  |
|---------|------------------|------------|------:|
| 11U S1  | Kangaroos        | Likely     | 18%   |
| 13U S2  | Wallabies        | Possible   | 32%   |
| 15U S1  | Possums          | Likely     | 67%   |
| 17U S2  | Bilbies          | Possible   | 45%   |
| Open A  | Quokkas          | Unlikely   | 12%   |
