# Domain features

Four opt-in features for documents that need status-coded tables or
row-level highlighting. All are dormant unless their corresponding
front-matter key is set — alpine training docs don't use any of them;
netball regrading reports use all four.

## `tracked_rows`

Highlights any row whose cells contain one of the listed strings.
Domain-neutral: tracks teams, players, weeks, products, anything.

```yaml
---
tracked_rows:
  - "WNC Possums"
  - "WNC Bilbies"
---
```

Matched rows get `<tr class="highlight">`. The bundled palette colours
this navy-tinted; themes can override `--color-highlight`.

The matcher is case-insensitive and tolerates typographic variants
(hyphen vs en-dash) since typography conversion may have transformed
the text in the HTML.

`tracked_teams` is accepted as a deprecated alias; it logs a warning
and behaves identically.

## `direction_markers`

Scans bold table cells for embedded direction markers and converts them
to row-level CSS classes.

```yaml
---
direction_markers: true
---
```

```markdown
| Team                       | Risk | Recommendation |
|----------------------------|------|----------------|
| **{up}▲ Possums**          | 12%  | Promote — strong    |
| **{up}{mod}▲ Wallabies**   | 28%  | Promote — moderate  |
| **{up}{watch}Kookaburras** | 35%  | Lean promote — watch next cycle |
| **{down}{watch}Echidnas**  | 45%  | Lean demote — watch next cycle  |
| **{down}{mod}▼ Hawks**     | 58%  | Demote — moderate   |
| **{down}▼ Bilbies**        | 67%  | Demote — strong     |
| Unmarked team              | 31%  | No recommendation   |
```

Markers must be inside `<strong>` cells (markdown `**...**`). Direction
markers come first, optionally followed by a tier marker:

| Marker | Class | Default colour |
|---|---|---|
| `{up}` | `tr.highlight-up` | strong green |
| `{up}{mod}` | `tr.highlight-mod-up` | medium green |
| `{up}{watch}` | `tr.highlight-watch-up` | very light green |
| `{down}` | `tr.highlight-down` | strong pink |
| `{down}{mod}` | `tr.highlight-mod-down` | medium pink |
| `{down}{watch}` | `tr.highlight-watch-down` | very light pink |

Three confidence tiers per direction: **strong** (saturated, bold text),
**moderate** (medium tint, bold text), **watch** (very light tint, no
bold — subtle "monitor next cycle" indication).

`{mod}` and `{watch}` always follow a direction marker; on their own
they're not recognised and the marker text will appear literally in
the cell.

Cells without a direction marker (whether plain text or just `**bold**`)
are left unchanged.

Colours come from the bundled `--color-up`, `--color-mod-up`,
`--color-watch-up`, `--color-down`, `--color-mod-down`,
`--color-watch-down` variables.

## `risk_tables`

For each table matching a listed CSS class, the post-processor reads
percentage cells and colour-codes them — `.risk-high` (≥50%, red),
`.risk-med` (25-49%, amber), `.risk-low` (<25%, green).

Two scan modes:

- **`last`** *(default)* — only the last `<td>` of each data row is read.
  Use when the table has one explicit "Risk" column.
- **`all`** — every `<td>` is read. Use when every numeric column is a
  risk percentage (e.g. risk-by-age-and-boundary).

### Single-column risk (default)

```yaml
---
tables:
  swap-summary:
    css_class: swap-summary
    columns:
      - {name: Section}
      - {name: Team, width: 30}
      - {name: Likelihood, align: right}
      - {name: Risk, align: right}
risk_tables: ["swap-summary"]
---
```

```markdown
| Section | Team | Likelihood | Risk |
|---------|------|-----------:|-----:|
| 11U S1  | A    | Likely     | 67%  |
| 13U S2  | B    | Possible   | 32%  |
| 15U S1  | C    | Likely     | 18%  |
```

Only the **Risk** cells get coloured.

### Whole-table risk (`columns: all`)

```yaml
---
tables:
  risk-promotion:
    css_class: risk-promotion
    columns:
      - {name: Boundary}
      - {name: 11U, align: right}
      - {name: 13U, align: right}
      - {name: 15U, align: right}
risk_tables:
  - {class: risk-promotion, columns: all}
---
```

```markdown
| Boundary | 11U | 13U | 15U |
|----------|----:|----:|----:|
| Into S1  | 58% | 55% | 71% |
| Into S2  | 21% | 21% | 27% |
```

Every percentage cell gets coloured by its own value.

### Notes

- Bare strings in `risk_tables` (e.g. `["swap-summary"]`) are shorthand
  for `{class: swap-summary, columns: last}` — back-compat.
- Only tables whose CSS class is listed are processed — the
  post-processor doesn't guess.
- Cells that don't begin with `\d+%` are left alone (so heading-row
  text and labels are safe).

## Verdict rows

Three CSS classes for retrospective tables: success / warning / failure.
Applied directly via inline HTML in markdown (the pipeline supports
`md_in_html`).

```markdown
<table>
<thead>
<tr><th>Decision</th><th>Outcome</th><th>Notes</th></tr>
</thead>
<tbody>
<tr class="verdict-success"><td>Promote Possums</td><td>Won 6 of 9</td><td>Right call</td></tr>
<tr class="verdict-warning"><td>Hold Bilbies</td><td>3-3 record</td><td>Borderline</td></tr>
<tr class="verdict-failure"><td>Promote Wallabies</td><td>1-8 record</td><td>Wrong call</td></tr>
</tbody>
</table>
```

Background colours: success green (`--color-verdict-ok`), warning amber
(`--color-verdict-warn`), failure pink (`--color-verdict-fail`).

## Why these are in the package

They originated for netball regrading reports but the mechanisms are
generic — "highlight rows matching a list", "scan for markers, apply
classes", "colour cells by threshold", "outcome colours". Other projects
can use any combination by setting the front-matter keys.

The `regrading` named theme restates the highlight styling for clarity
at the theme level but the CSS classes and variables are always available
in the bundled `style.css`.
