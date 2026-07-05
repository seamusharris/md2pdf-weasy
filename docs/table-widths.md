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
reached 40 or 400; a rank column should be narrow everywhere; a team-name
column should take whatever room is left.

The old default (WeasyPrint's content-based `table-layout: auto`) sized every
table to its own content, so the same kind of column came out a different width
in every table, and small tables sprawled across the page. The typed-width
system fixes that.

> **Note:** This is automatic. You don't declare anything to get good widths —
> read on only if you want to understand or override the behaviour.

## How it works, in one paragraph

Every table without an explicit layout is processed column by column. Each
column is **classified by its content** into a semantic *type*. Token types
(numbers, codes, dates…) get an **absolute width** from a shared *ladder*;
flexible types (names, prose) are left width-less to **absorb the remaining
space**. Columns of the same type in a table **share one width**, so similar
columns line up. Because the widths are absolute and keyed by type, the same
kind of column is the same width in every table and document.

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
| label | short non-wrapping text | `Home`, `Final`, `Active` |
| text | names — **flexible** | `Warrandyte Wallabies` |
| prose | sentences — **flexible** | `Would have flagged — strong case` |

The first seven are **token** types (fixed width). `text` and `prose` are
**flex** types (absorb the remainder).

## The width ladder

Token widths come from a small ladder of rungs, in `em` (so they scale with the
table's font size — a compact theme retunes them for free):

| Rung | Width | Typical use |
|---|---|---|
| w1 | 2.5em | 2-digit numbers, `#` |
| w2 | 3em | ranks, `P` `W` `GF` `Pts` |
| w3 | 3.5em | 4-digit numbers, `0:30` |
| w4 | 4.5em | `45-38`, `14 Jun`, short labels |
| w5 | 5.5em | wide headers, `112-108` |
| w6 | 7em | ISO dates, `Wednesday` |
| w7 | 9em | longest non-wrapping labels |

Each type has a canonical rung; the actual rung is bumped up if the column's
content or its **header** needs more room, then snapped to the ladder. So a
column is never narrower than its type's baseline and never clips its header.

## Grouping: same type, same width

This is the key to a clean grid. Within a table, all columns of one type are
resolved **together** to a single width — the widest member sets it, everyone
matches. In this ladder, `Pos P W L D GF GA GD Pts` are all `stat`, so they are
all identical, and `Team` (text) takes the rest:

| Pos | Team | P | W | L | D | GF | GA | GD | Pts |
|---|---|---|---|---|---|---|---|---|---|
| 1 | Warrandyte Wallabies | 14 | 12 | 2 | 0 | 486 | 310 | +176 | 24 |
| 8 | Park Orchards United | 14 | 2 | 12 | 0 | 205 | 498 | -293 | 4 |

A smaller ladder gets the **same** stat width — compare the numeric columns
here to the ones above; they line up even though this table has fewer columns:

| Pos | Team | W | L | GF | Pts |
|---|---|---|---|---|---|
| 1 | Donvale Devils | 12 | 2 | 402 | 24 |
| 5 | Nunawading Saints | 6 | 8 | 288 | 12 |

## Flexible columns absorb the remainder

A `text`/`prose` column takes whatever the token columns leave. So a table
with a flex column always fills the page width, and the flex column widens when
there are fewer columns (or in landscape) and narrows when there are more.
Tables with **two** flex columns split the remainder between them:

| Time | Court | Home | Away |
|---|---|---|---|
| 9:00 AM | 5 | Manningham 15U Champ | Mornington Peninsula 15U |
| 9:18 AM | 11 | Warrandyte Wallabies | Donvale Devils |

## All-token tables shrink to fit

When a table has **no** flex column, it would stretch across the page and the
extra space would inflate the fixed columns. Instead it shrinks to its natural
width:

| Rd | Ct | GF | GA | Result |
|---|---|---|---|---|
| 1 | 5 | 42 | 38 | W |
| 2 | 11 | 29 | 41 | L |

## Specifying and overriding

Nothing is required for good defaults. When you want to override:

- **Disable for a document** — front matter `table_widths: false`.
- **Force a column's type** — front matter maps header → type:

  ```yaml
  columns:
    Division: label     # keep fixed, don't let it flex against Home/Away
    Assessment: prose   # treat as a flexible prose column
  ```

- **Pin an exact width** — give a value instead of a type:

  ```yaml
  columns:
    Venue: 12em
  ```

- **Declare a full layout** — the `tables:` front-matter layouts (see
  [tables.md](tables.md)) still take precedence over the automatic pass, for
  cases needing explicit per-column widths, alignment, or a CSS class.

Overrides are keyed on the header name (case- and whitespace-insensitive).

## Notes and guards

- Tables with **colspans** or ragged rows are left on auto layout (a fixed
  colgroup would misrender them).
- Long tokens and URLs **wrap inside** their column rather than bleeding over
  the neighbour.
- Column **alignment** (numbers right, short codes centred) is applied
  independently — see [tables.md](tables.md).
- Headers that don't match the registry are sized by content; a column type
  can always be pinned with the `columns:` override above if the automatic
  choice isn't what you want.
