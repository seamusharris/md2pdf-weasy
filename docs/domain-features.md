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
| Team             | Risk | Recommendation |
|------------------|------|----------------|
| **{up}▲ Possums** | 12%  | Promote        |
| **{down}▼ Bilbies** | 67%  | Demote        |
| **{mod}Wallabies** | 31%  | Watch          |
```

Markers in bold cells are stripped from the visible text and applied as
row classes:

| Marker | Class | Default colour |
|---|---|---|
| `{up}` | `tr.highlight-up` | strong green |
| `{down}` | `tr.highlight-down` | strong pink |
| `{mod-up}` or `{mod}` (in an up context) | `tr.highlight-mod-up` | medium green |
| `{mod-down}` or `{mod}` (in a down context) | `tr.highlight-mod-down` | medium pink |

Colours come from the bundled `--color-up` / `--color-down` /
`--color-mod-up` / `--color-mod-down` variables.

## `risk_tables`

For each table matching a listed CSS class, the post-processor reads the
last column's content as a percentage and colour-codes the cell.

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

The "Risk" column cells get `.risk-high` (≥50%, red), `.risk-med`
(25-49%, amber), or `.risk-low` (<25%, green).

Only tables whose CSS class is in the `risk_tables` list are processed —
the post-processor doesn't guess.

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
