# Front matter reference

Every supported front-matter field, what it does, and an example.

Front matter is YAML at the top of a markdown file, between `---` lines:

```yaml
---
title: "Document Title"
subtitle: "Optional subtitle"
theme: alpine
toc: true
---
```

Unknown or mistyped keys log a warning at render time but don't fail.

## Document metadata

| Field | Type | Default | Description |
|---|---|---|---|
| `title` | str | — | Rendered as `<h1>` at the top of the document |
| `subtitle` | str | — | Rendered as `<p class="doc-subtitle">` below the title |

## Theming

| Field | Type | Default | Description |
|---|---|---|---|
| `theme` | str | — | Name of a bundled theme to load after `style.css`. See [themes.md](themes.md). Currently: `alpine`, `wnc`, `regrading`, `neutral`, `compact`. |

The theme is looked up by name in the package's `styles/` directory.
Slashes, backslashes, and `..` are rejected for safety; only bare names.

## Layout

| Field | Type | Default | Description |
|---|---|---|---|
| `h2_page_break` | bool | false | When true, every `h2` starts on a new page. CSS is injected by `render.py` (`_front_matter_css`): `h2 { break-before: page; margin-top: 0; }` plus `h1 + h2 { break-before: auto; }` (so an `h2` right after the title stays on the cover). When there is **no** TOC, `.content > h2:first-child { break-before: auto; }` is also injected so the first content `h2` stays on the title page rather than leaving it near-empty. These rules are conditional — not part of the unconditional bundled `style.css`. |
| `toc` | bool | false | When true, generate a table of contents from the body headings (`h1` through `h{toc_depth}`) and insert it after the title. |
| `toc_depth` | int | 3 | Maximum heading depth to include in the TOC. Only meaningful when `toc: true`. |

## Tables

| Field | Type | Default | Description |
|---|---|---|---|
| `tables` | dict | `{}` | Per-document table layouts. See [tables.md](tables.md). |
| `tables_include` | str | — | Path to a shared YAML file of layouts. Resolved cwd-relative first, then relative to the markdown file. Per-doc `tables` overrides shared layouts by key. |
| `auto_align_columns` | bool | true | When true (default), auto-align columns by content: all-numeric columns get `class="num"` (right-aligned) and all-short (≤3-char) columns get `class="ctr"` (centred). Set false to disable. See [tables.md](tables.md). |
| `auto_highlight_bold_rows` | bool | false | When true, any table row containing a cell that is wholly wrapped in `**bold**` (inner text longer than 3 characters) gets `<tr class="highlight">`, and the bold markup on that cell is removed (the row CSS re-bolds it). Opt-in for retrospective reports. |

## Callouts

| Field | Type | Default | Description |
|---|---|---|---|
| `extra_callout_keywords` | dict | `{}` | Extend the keyword → CSS-class map for blockquote callouts. See [callouts.md](callouts.md). |

## Domain features (opt-in)

All four are dormant unless the corresponding key is set. See
[domain-features.md](domain-features.md) for full behaviour.

| Field | Type | Default | Description |
|---|---|---|---|
| `tracked_rows` | list[str] | — | Highlight any row whose cells contain one of these strings. Adds `<tr class="highlight">`. |
| `tracked_teams` | list[str] | — | Deprecated alias for `tracked_rows`. Warns on use. |
| `direction_markers` | bool | false | Scan bold cells for `{up}` / `{down}` markers, each optionally followed by `{mod}` or `{watch}`; apply `tr.highlight-up`, `tr.highlight-mod-up`, `tr.highlight-watch-up` etc. row classes. |
| `risk_tables` | list[str \| dict] | — | List of table specs. A bare string is a CSS class name whose matching table has its **last** column colour-coded; a dict `{class: <name>, columns: last \| all}` picks last-column (default) or every-cell scanning. Cells are coloured red ≥ 50%, amber 25-49%, green < 25%. See [domain-features.md](domain-features.md). |

## Example combining several

```yaml
---
title: "Season Report"
subtitle: "2025 Spring"
theme: wnc
h2_page_break: true
toc: true
toc_depth: 2
tables_include: themes/tables.yml
tracked_rows: ["WNC Possums", "WNC Bilbies"]
direction_markers: true
risk_tables: ["swap-summary"]
---

## Section heading
...
```
