# Tables

Markdown tables work as-is. The pipeline adds:

- **Layouts** — column widths and alignment declared in YAML
- **Default widths registry** — header-name → width lookup for unspecified columns
- **Shared layouts** — load layouts from an external YAML file via `tables_include`
- **Auto-alignment** — numeric columns get right-aligned automatically
- **Section divider rows** — auto-detected and styled distinctly
- **Highlight modes** — row-level styling for tracked rows, direction markers, verdicts

## A plain markdown table

```markdown
| Day | Session | Duration | TSS |
|-----|---------|----------|-----|
| Mon | Recovery walk | 0:30 | 18 |
| Tue | Strength | 1:00 | 60 |
```

Renders with sensible defaults. No declaration needed.

## Declaring a layout

Layouts live under `tables:` in front matter (per-doc) or in a YAML file
referenced by `tables_include:` (shared). Each layout is keyed by name
and matched to actual tables by their header content.

```yaml
---
tables:
  weekly-schedule:
    css_class: weekly-schedule
    columns:
      - {name: Day}
      - {name: Session}
      - {name: Duration, align: right}
      - {name: TSS,      align: right}
---
```

Any markdown table whose header row matches `Day | Session | Duration |
TSS` gets the `weekly-schedule` layout: a `<colgroup>` injected with
normalised widths, alignment applied to header and data cells, and the
optional `css_class` added to `<table>`.

## Column fields

| Field | Type | Default | Description |
|---|---|---|---|
| `name` | str | — required — | Must match the header text exactly (case-insensitive) |
| `width` | int | from registry, or 15 | Unitless relative weight; normalised across columns to sum to 100% |
| `align` | str | left (or auto-right for numeric) | `left` / `right` / `center` |

## Default widths registry

`pdf/default_widths.yml` ships with ~80 header-name → width mappings so
layouts only need to specify `width:` for columns the registry doesn't
know about. Examples:

```yaml
"#":          6      # narrow numeric
"Week":       8      # short date-ish
"Day":       10
"Date":      14
"Duration":  12
"TSS":        8
"Team":      22
"Notes":     48      # wide prose
"Description": 48
"Action":    40
```

Project-level layouts override the registry. Layouts override per-doc
overrides. (Per-doc front-matter `tables:` wins over `tables_include:`
shared layouts which win over registry defaults.)

To extend the registry, edit `pdf/default_widths.yml` in the package —
benefits all projects using the pipeline.

## Sharing layouts across documents

When multiple docs in a project use the same table shape, define the
layout once in a shared file:

```yaml
# themes/tables.yml in your project
ladder:
  css_class: ladder
  columns:
    - {name: Team, width: 40}
    - {name: W, align: right}
    - {name: L, align: right}
    - {name: GF, align: right}
    - {name: GA, align: right}
    - {name: "%", align: right}
```

Then in each document:

```yaml
---
tables_include: themes/tables.yml
---
```

The path is cwd-relative first, then relative to the markdown file.

## Highlight modes

Per-layout `highlight:` field controls row-level highlighting:

| Value | Behaviour |
|---|---|
| `row` (default if tracked_rows is set) | Full row highlight via `<tr class="highlight">` |
| `bold-only` | Keep bold cells but no row-level class |
| `none` | Strip bold from matched cells, no highlight |

```yaml
tables:
  team-summary:
    highlight: bold-only
    columns: [...]
```

## Auto-alignment

The pipeline scans each column's cell content and auto-applies
`text-align: right` to columns where every cell is numeric (digits,
decimals, percentages, en-dashes, fractions, win-loss notation).

Disable with `auto_align_columns: false` in front matter if you want
manual control.

## Section divider rows

Rows where only the first cell has content (rest are empty) are auto-
detected and styled with `tr.table-section` — a tinted band that visually
breaks a long table into groups.

```markdown
| Division | Team | W | L |
|----------|------|---|---|
| 9U       |      |   |   |
| 9U Red   | Bilbies | 8 | 1 |
| 11U      |      |   |   |
| 11U Sec 1 | Koalas | 6 | 4 |
```

The `9U` and `11U` rows are detected as section dividers.

## Auto-highlight of bold rows

Opt-in via `auto_highlight_bold_rows: true`. Any row whose first cell is
bold gets `<tr class="highlight">`. Useful for retrospective reports
where bold marks tracked rows without needing a `tracked_rows:` list.

## Column CSS classes

Each `<col>` in a generated `<colgroup>` gets a class `col-<header-name-
lowercased-hyphenated>`. Use this for per-column CSS targeting:

```css
table.weekly-schedule col.col-tss { text-align: right; font-feature-settings: "tnum"; }
```
