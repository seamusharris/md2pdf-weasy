# Tables

Markdown tables work as-is. The pipeline adds:

- **Layouts** — column widths and alignment declared in YAML
- **Default widths registry** — header-name → width lookup for unspecified columns
- **Shared layouts** — load layouts from an external YAML file via `tables_include`
- **Named presets** — opt in to a versioned bundled layout without repeating columns
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

## Named table presets

A preset is a complete, versioned table layout, independent of the selected CSS
theme. It does not enable domain features or change page orientation:

```yaml
---
theme: wnc
tables:
  season-ladder:
    preset: netball-ladder-v1
---

| Team | P | W | L | D | GF | GA | % |
|---|---:|---:|---:|---:|---:|---:|---:|
| North | 12 | 8 | 4 | 0 | 244 | 187 | 130.5 |
```

`netball-ladder-v1` matches exactly those eight headers, in that order, using
the existing case-insensitive layout matcher. It adds `class="netball-ladder"`,
left-aligns `Team`, and right-aligns the seven numeric columns. Its explicit
relative weights are `24, 6, 6, 6, 6, 8, 8, 10`. The four match-count columns
share one proportion; `GF` and `GA` share another. Percentage values have a
separate, wider column. The weights are normalized to 100%, not interpreted
as em. Thus the same full table shape has stable proportions across reports,
not identical absolute column widths across different page sizes or shapes.

No other ladder shapes are inferred: a rank, points, extra column, missing
column, or reordered header requires a separate explicit layout. Existing
preset IDs are immutable; changed weights or header shapes require a new ID.
The package catalog's `schema_version: 1` describes the catalog format, not the
document or package version.

Explicit `css_class` and `highlight` fields override preset defaults. An
explicit `columns` list replaces the **entire** preset list; it is not merged
by index or name. For a frequently customized shape, define one complete
project layout in a shared `tables_include` file instead. Presets can themselves
be selected in that shared file.

Resolution and precedence:

1. Shared layouts are loaded using the existing `tables_include` rules.
2. Document layouts replace shared layouts by layout key, as complete entries.
3. Each referenced preset is expanded, then explicit fields on that entry win.
4. An author colgroup or unsupported table structure remains untouched.
5. Expanded layouts use the existing first-matching-header rule. If differently
   named entries match the same shape, the first entry wins, as before; a
   document replacement by key is not a global priority over every shared entry.
6. Unmatched eligible tables use automatic widths and top-level `columns`.

`table_widths: false` disables automatic widths only; it does not disable
explicit presets or layouts. Top-level `columns` overrides do not override a
matching preset's colgroup. Both direct Python processing entry points
(`md_to_html` and `postprocess`) expand presets; the public callable signatures
and CLI options are unchanged.

Preset identifiers must be bare versioned names, never paths or URLs. Unknown
or malformed preset references, unsupported override fields, invalid alignment
or highlighting, unsafe class names, empty replacement columns, and non-positive,
non-finite, boolean or non-numeric weights warn and skip only that layout.
The normal automatic-width fallback then applies if enabled; valid sibling
layouts remain available. Diagnostics do not include cell contents or supplied
values. Preset expansion leaves layouts without a `preset` field unchanged.
The renderer now validates all declared layouts before emission: valid legacy
layouts remain compatible, while malformed definitions warn and fall back
instead of crashing or emitting invalid widths. Catalog defects are operational
errors rather than silently ignored document controls.

No global default or theme automatically enables a preset. Existing documents
need no migration; add the reference only when you want this exact contract.

## Default widths registry

`pdf/default_widths.yml` ships with ~90 header-name → width mappings so
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

Precedence: per-doc front-matter `tables:` wins over `tables_include:`
shared layouts, which win over registry defaults. An explicit `width:` on
a column always overrides the registry lookup for that column.

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
| `none` | No row-level highlighting. Currently behaves identically to `bold-only` — bold cell content is **not** stripped. |

```yaml
tables:
  team-summary:
    highlight: bold-only
    columns: [...]
```

## Auto-alignment

The pipeline scans each column's cell content and adds an alignment class
to the `<td>` cells:

- Columns where every cell is numeric (digits, decimals, percentages,
  en-dashes, fractions, win-loss notation, or empty/`-`) get `class="num"`
  — right-aligned. A short numeric **first** column (rank/index) is
  centred instead.
- Columns where every cell is short text (≤3 characters, like `H`/`A` or
  `W`/`L`) get `class="ctr"` — centred.
- Everything else stays left-aligned (the default).

The `num` and `ctr` classes are styled in `style.css` (`td.num` →
right, `td.ctr` → center).

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
table.weekly-schedule col.col-tss { background: #fafafa; }
```

Note the CSS limitation: only a handful of properties (notably `width`,
`background`, `border`) apply through `<col>` elements — `text-align`
does **not** inherit from `<col>` to the cells. Real per-column alignment
comes from the cell-level classes (`td.num` / `td.ctr` from auto-align,
or the `align:` key on a column definition, which writes an inline
`text-align` onto each `th`/`td`).
