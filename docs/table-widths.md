---
title: "Table Column Widths"
subtitle: How columns are typed, grouped, and sized — a complete reference
toc: true
toc_depth: 2
---

## The goal

Tables should have **sensible, consistent widths for similar content — across
and within tables — regardless of the exact content in any one table.** A goals
column should be the same width in every ladder, whether this week's scores
reached 40 or 400; a rank column should be narrow everywhere; a `Team` column
should be the same width as the `Home`/`Away` columns in a sibling table.

The old default (WeasyPrint's content-based `table-layout: auto`) sized every
table to its own content, so the same kind of column came out a different width
in every table, and small tables sprawled across the page. This system fixes
that.

> **Note:** This is automatic. You don't declare anything to get good widths —
> read on only if you want to understand or override the behaviour.

## How it works, in one paragraph

Every table without an explicit layout is processed column by column. Each
column is **classified by its content** into a semantic *type*. Numeric types
(numbers, codes, dates…) get an absolute width from a shared **em ladder**.
Wider types (short labels, names, prose) get a width shared **per column
identity across the whole document** — every `Division` column matches, and all
team columns (`Team`/`Home`/`Away`) share one width. Every column is fixed, so a
table **sizes to its content** instead of stretching one column to fill the
page. The result: the same kind of column is the same width in every table.

## Acceptance contract

This section is the normative contract for the automatic-width pass. Later
correctness work is accepted against these rules; where an implementation gap
exists, the rule here is the intended behaviour.

### Implementation status

The core classification, grouping, declared-layout/colgroup precedence, basic
em fitting, portrait/landscape budgets, and document-wide identities are
implemented. The remaining gaps are intentionally visible rather than blurred
into the current behaviour:

| Area | Current revision | Contract work |
|---|---|---|
| Invalid controls | Type and semantic validation share one non-mutating normalizer. Invalid parsed or direct-call values warn and use the documented fallback. | Implemented by T-004 |
| Exact widths | Numeric and em-string values are normalized, emitted, and fitted from one exact em value. Boundary totals, mixed columns, orientation budgets, and fixed-only overflow are covered. | Implemented by T-005 / ISS-003 |
| Structural preservation | One shared guard leaves empty, spanning, ragged, and existing-colgroup tables alone across declared and automatic layouts. Captions stay first, all body groups participate in analysis, semantic attributes are preserved, and repeat passes are idempotent. | Implemented by T-006 |
| Classification and overrides | All semantic types, mixed/empty/long content, normalized headers and identities, precedence, opt-outs, and repeat processing are covered at the emitted-HTML contract. | Implemented by T-007 |
| Font metrics | Directly required fontTools reads the packaged body/header fonts with closed resources and cached results. Missing or unreadable resources warn before using deterministic estimates; distribution tests cover every shipped style and referenced font. | Implemented by T-008 |
| Visual PDF evidence | A wholly synthetic nine-case matrix covers every bundled theme plus declared, legacy, portrait-stress, and landscape variants. Deterministic geometry, wrapping, orientation, tagged-PDF, content-order, raster, manifest, promotion, and retention checks accompany full-page human review. | Implemented by T-009; see [visual acceptance evidence](visual-acceptance/README.md) |

### Activation and precedence

- Automatic widths are on when `table_widths` is absent or `true`.
- The YAML boolean `false` disables them. The string aliases `off`, `none`, and
  `legacy` also disable them after trimming whitespace and ignoring case.
- Any other malformed control value logs a warning and uses the safe default:
  automatic widths remain on.
- A matching layout declared under `tables:` runs first and wins. An
  author-supplied `<colgroup>` also wins. The automatic pass must not replace,
  append to, or reinterpret either colgroup.
- `columns:` overrides apply only to tables still eligible for automatic
  widths. Header keys are matched case-insensitively with whitespace
  normalised.
- Headerless or empty tables, and tables whose colspan, rowspan, or ragged row
  shape cannot be represented by one fixed column per header, pass through
  unchanged. Running the pass again is a no-op for a table it already handled.

Width processing is presentational. It may add a `<colgroup>` and a `fit` class,
but must preserve captions, header and body groups, header cells and their
`scope`/`id`/`headers` associations, row and cell order, and existing HTML or
ARIA attributes. In particular, inserting a colgroup must not move an existing
caption from its semantic first-child position.

### Classification and grouping

- Classification is content-first. Every non-empty body cell must match a
  specialised type; the header may break a tie or set a minimum width, but must
  not override contradictory content.
- Numeric types use the shared em ladder. Within each table, every column of
  the same numeric type uses the widest required rung for that type.
- `label`, `text`, and `prose` are wide types. Their natural width is grouped by
  normalised header across the whole document. Headers containing a team/entity
  word (`Team`, `Home`, `Away`, `Opponent`, `Club`, `Name`, or `Player`) share
  the single team identity.
- A valid `columns:` entry may select a known type or an exact width. A numeric
  exact width means em. A string exact width is supported only when it is a
  positive finite decimal followed by `em` (for example `12em`). Booleans,
  zero, negative or non-finite numbers, other CSS units, expressions, and
  arbitrary strings warn and fall back to automatic classification. Restricting
  exact widths to table em keeps page-fit accounting deterministic.
- A malformed `columns:` value warns and behaves as `{}`; one malformed entry
  must not discard other valid entries.

### Fitting and page model

- The fitting budget defaults to about `54.8em` for A4 portrait and `82.2em`
  for A4 landscape, matching the bundled 18 mm side margins and 9 pt tables.
- `page_width_em` takes precedence over that default only when it is a positive,
  finite number. Invalid values warn and use the orientation-derived budget.
- Natural width is the exact sum of token rungs, explicit em widths, and wide
  identity widths. A table at or below the budget shrinks to that content width
  rather than stretching across the page.
- When the natural width exceeds the budget, explicit widths and numeric ladder
  widths remain fixed. Automatically sized wide columns give up space, with the
  widest columns reduced first. If the fixed columns alone cannot fit, the pass
  preserves them and reports that the table still exceeds the budget.
- `orientation: landscape` changes both the rendered A4 page and the fitting
  budget. Matching is case-insensitive. Any other value warns and uses
  portrait. A valid `page_width_em` changes only the fitting budget; it does not
  change the physical page size.

### Alignment and diagnostics

Width and alignment are independent passes. Disabling `auto_align_columns`
must not disable widths, and disabling widths must not disable alignment.
Declared-layout alignment remains authoritative.

Normal width assignment is silent. Invalid width controls produce a warning
that names the field and safe fallback without echoing document content. If an
otherwise valid portrait table is scaled, one document-level info message
reports the number of affected tables, widest natural width, available budget,
and suggests landscape. Landscape or custom-width overflow is still reported,
but does not repeat an inapplicable landscape suggestion.

### Representative acceptance examples

With no width front matter, these two tables share one document-wide team
identity: `Team`, `Home`, and `Away` receive the same natural width, while the
stat columns share a ladder rung within their own table.

```markdown
| Team | W | L |
|---|---:|---:|
| Warrandyte Wallabies | 12 | 2 |

| Home | Away | Score |
|---|---|---:|
| Donvale Devils | Warrandyte Wallabies | 38-45 |
```

An explicit layout or author colgroup takes precedence; the remaining table is
automatic. The `Venue` override is exact because it uses the supported em
grammar.

```yaml
---
tables:
  ladder:
    columns:
      - {name: Team, width: 40}
      - {name: W, width: 10}
columns:
  Venue: 12em
---
```

These controls are equivalent opt-outs:

```yaml
table_widths: false
# or: table_widths: OFF
# or: table_widths: none
# or: table_widths: legacy
```

For a genuinely wide document, landscape changes the PDF page and its default
budget. A custom positive budget overrides only the fitting calculation:

```yaml
---
orientation: landscape
page_width_em: 76
---
```

## Column types

A column's type comes from what's *in* it, not its header name — so `W`,
`Wins`, and `Played` all type the same, and a header can't lie about its
content.

| Type | What it matches | Example cells |
|---|---|---|
| stat | numbers up to 3 digits, short codes | `12`, `486`, `+176`, `W`, `H` |
| num | numbers of 4+ digits | `1,234`, `9999` |
| pct | percentages, or a `%` header | `58%`, `150.5` |
| score | score/record patterns | `45-38`, `5-3-0`, `W +7` |
| time | clock times | `9:00`, `7:30 pm` |
| date | calendar dates | `14 Jun`, `2026-07-05` |
| label | short non-wrapping text | `15U`, `Final`, `Active` |
| text | names | `Warrandyte Wallabies` |
| prose | sentences | `Would have flagged — strong case` |

The first six are **numeric** types (em-ladder width). `label`, `text` and
`prose` are **wide** types — sized by document-level identity (below).

## The width ladder (numeric columns)

Numeric widths come from a small ladder of rungs, in `em` (so they scale with
the table's font size — a compact theme retunes them for free):

| Rung | Width | Typical use |
|---|---|---|
| w1 | 2.5em | 2-digit numbers, `#` |
| w2 | 3em | ranks, `P` `W` `GF` `Pts` |
| w3 | 3.5em | 4-digit numbers, `0:30` |
| w4 | 4.5em | `45-38`, `14 Jun` |
| w5 | 5.5em | wide headers, `112-108` |
| w6 | 7em | ISO dates |
| w7 | 9em | widest numeric headers |

Each type has a canonical rung; the actual rung is bumped up if the column's
content or its **header** needs more room, then snapped to the ladder. So a
column is never narrower than its type's baseline and never clips its header.

## Grouping: same type, same width

Within a table, all numeric columns of one type resolve **together** to a
single width — the widest member sets it, everyone matches. In this ladder,
`Pos P W L D GF GA GD Pts` are all `stat`, so they are all identical:

| Pos | Team | P | W | L | D | GF | GA | GD | Pts |
|---|---|---|---|---|---|---|---|---|---|
| 1 | Warrandyte Wallabies | 14 | 12 | 2 | 0 | 486 | 310 | +176 | 24 |
| 8 | Park Orchards United | 14 | 2 | 12 | 0 | 205 | 498 | -293 | 4 |

A smaller ladder gets the **same** stat width — the numeric columns line up with
the ones above even though this table has fewer columns:

| Pos | Team | W | L | GF | Pts |
|---|---|---|---|---|---|
| 1 | Donvale Devils | 12 | 2 | 402 | 24 |
| 5 | Nunawading Saints | 6 | 8 | 288 | 12 |

## Wide columns: one width per identity, document-wide

Wide columns (`label`/`text`/`prose`) don't flex — they get a fixed width that
is the **widest that identity needs anywhere in the document**. Two rules give
the identity:

- **Team-like headers** — `Team`, `Home`, `Away`, `Opponent`, `Club`, `Name`,
  `Player` — all share one width. So a summary's `Team` column is exactly as
  wide as the `Home`/`Away` columns in the schedule tables.
- **Everything else** is keyed by its (normalised) header, so every `Division`
  column across the document is the same width.

Because every column is fixed, a table **sizes to its content**: it shrinks
when it doesn't need the full page rather than stretching one column to fill it.

| Time | Court | Home | Away |
|---|---|---|---|
| 9:00 AM | 5 | Manningham 15U Champ | Mornington Peninsula 15U |
| 9:18 AM | 11 | Warrandyte Wallabies | Donvale Devils |

An all-numeric table (no wide column) simply shrinks to the sum of its rungs:

| Rd | Ct | GF | GA | Result |
|---|---|---|---|---|
| 1 | 5 | 42 | 38 | W |
| 2 | 11 | 29 | 41 | L |

### When a table is too wide

If a table's natural width exceeds the fitting budget, automatically sized wide
columns give up space, with the widest reduced first. Numeric ladder widths and
explicit author widths stay fixed, so a table made too wide by fixed columns can
still exceed the budget. A scaled portrait table produces the landscape
suggestion described in the contract; landscape and custom-budget diagnostics
do not repeat that suggestion when it is inapplicable.

## Page orientation

The overflow-fit uses the A4 page width. For documents with genuinely wide
tables, switch to landscape in the front matter — wide columns then keep their
full document-wide width without scaling:

```yaml
---
orientation: landscape
---
```

A positive, finite `page_width_em: <number>` overrides the fitting budget
directly if you use a non-standard page or margins. It does not change the
physical PDF page size.

## Quick configuration recipes

Nothing is required for good defaults. These recipes use the valid forms from
the [acceptance contract](#acceptance-contract):

- **Disable for a document** — front matter `table_widths: false`, or the
  case-insensitive string alias `off`, `none`, or `legacy`.
- **Force a column's type** — front matter maps header → type:

  ```yaml
  columns:
    Division: label     # type it as a fixed label, not a name
    Assessment: prose   # treat as a prose column
  ```

- **Pin an exact width** — give a positive finite number (interpreted as em) or
  a positive decimal `em` string instead of a type:

  ```yaml
  columns:
    Venue: 12em
  ```

- **Declare a full layout** — the `tables:` front-matter layouts (see
  [tables.md](tables.md)) still take precedence over the automatic pass, for
  cases needing explicit per-column widths, alignment, or a CSS class.

Overrides are keyed on the header name (case- and whitespace-insensitive).

For documents upgrading from the tagged renderer, see the
[v0.1.0 rendering migration guide](v0.1.0-migration.md). It distinguishes the
narrow automatic-width opt-out from a full rollback and records the synthetic
legacy/current comparison evidence.

## Notes and guards

- Tables with **colspans**, **rowspans**, or ragged rows are left on auto layout
  (a fixed colgroup would misrender them).
- Captions, table structure, header associations, reading order, and existing
  HTML/ARIA attributes are preserved; the pass adds only presentational width
  markup.
- Long tokens and URLs **wrap inside** their column rather than bleeding over
  the neighbour.
- Column **alignment** (numbers right, short codes centred) is applied
  independently — see [tables.md](tables.md).
- A column's type can always be pinned with the `columns:` override above if the
  automatic choice isn't what you want.
