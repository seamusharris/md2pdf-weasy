# md2pdf-weasy

Markdown → PDF via WeasyPrint, with YAML front-matter control over table
layouts, blockquote callouts, page breaks, and typography. Ships with a
curated set of fonts (Adobe Minion Pro + Myriad Pro for serif body and
sans companion, plus AntSerif and Montserrat / Open Sans) and four named
themes.

**Private package** — bundled Adobe fonts (Minion Pro, Myriad Pro) are
personal-use licensed; do not redistribute. The OFL fonts (AntSerif,
Montserrat, Open Sans) can be redistributed freely.

## Install

Editable for local dev:

```bash
pip install -e ~/Repos/md2pdf-weasy
```

Pinned to a tagged release for reproducibility:

```bash
pip install "md2pdf-weasy @ git+ssh://git@github.com/seamusharris/md2pdf-weasy.git@v0.1.0"
```

Requires Python 3.11+ and WeasyPrint's system libraries (Cairo + Pango).
On macOS: `brew install pango`.

## Usage

```bash
# Renders with bundled defaults + the alpine named theme
python -m pdf input.md output.pdf
```

Front matter selects a named theme and configures table layouts:

```yaml
---
title: "Document Title"
subtitle: "Optional subtitle"
theme: alpine               # named theme (see below)
tables_include: themes/tables.yml   # shared table layouts
h2_page_break: true         # each major section starts a new page
toc: false
---
```

## Named themes

Selected via `theme: <name>` in document front matter.

| Theme | When to use |
|---|---|
| `alpine` | Outdoor / training-manual aesthetic. Muted palette with one warning red, session-type and traffic-light colour vars for status-coded content. |
| `wnc` | Warrandyte Netball Club brand. Brand red anchor, navy links, Montserrat headings + Open Sans body, position/age/programme palettes. |
| `regrading` | Dense, table-heavy analysis reports. Tighter padding, restated highlight/verdict row styling. |
| `neutral` | Minimal — the bundled defaults. No domain accents. |
| `compact` | Smaller table padding only (orthogonal to the others; can stack). |

## Opt-in features (any theme)

Activated by setting the corresponding front-matter key. All are
domain-neutral and dormant when unused.

| Front matter | Effect |
|---|---|
| `tracked_rows: ["WNC Possums", ...]` | Highlights any row whose cells contain one of the strings. CSS class `tr.highlight` applied. |
| `direction_markers: true` | Scans bold cells for `{up}`, `{down}`, `{mod}` markers; applies `tr.highlight-{up,down,mod-up,mod-down}` row classes. |
| `risk_tables: ["swap-summary", ...]` | On tables matching the CSS class, colour-codes the last column's percentage cell: red (≥50%), amber (25-49%), green (<25%). |
| Verdict rows | Apply `<tr class="verdict-success">` / `verdict-warning` / `verdict-failure` directly in markdown for retrospective tables. |

`tracked_teams` is accepted as a deprecated alias for `tracked_rows`.

## Shared table layouts

Documents can pull in a YAML file of named column layouts:

```yaml
tables_include: themes/tables.yml
```

```yaml
# themes/tables.yml
ladder:
  css_class: ladder
  columns:
    - {name: Team, width: 40}
    - {name: W, width: 8, align: right}
    - {name: L, width: 8, align: right}
    - {name: GF, width: 10, align: right}
    - {name: GA, width: 10, align: right}
    - {name: "%", width: 16, align: right}
```

Tables in the document whose header row matches a layout's column names
get that layout applied automatically. Per-document `tables:` entries
override shared layouts by name.

Columns without an explicit `width:` get a sensible default from
`default_widths.yml` (a header-name → width registry, e.g. `"W" → 6`,
`"Notes" → 48`).

## Blockquote callouts

Bold keywords at the start of a blockquote apply coloured styling:

```markdown
> **Note:** Info-tier navy callout.
> **Tip:** Teal callout.
> **Important:** Purple callout.
> **Caution:** Amber callout.
> **Warning:** Red callout.
```

## Markdown extensions

Loaded by default: tables, fenced_code, smarty, sane_lists, def_list,
footnotes, attr_list, abbr, md_in_html, and from pymdown-extensions:
`pymdownx.tasklist`, `pymdownx.tilde`, `pymdownx.mark`.

So `- [ ]` task lists, `~~strikethrough~~`, and `==highlight==` all work
out of the box.

## Python API

```python
from pdf.render import build_pdf, md_to_html, parse_front_matter

# Full pipeline: markdown file → PDF file
build_pdf("input.md", "output.pdf")

# Stepwise
text, metadata = parse_front_matter(open("input.md").read())
html = md_to_html(text, metadata)

from pdf.postprocess import postprocess
html = postprocess(html, metadata)
```

## Bundled fonts

| Family | Files | License | Notes |
|---|---|---|---|
| Minion Pro | 23 files (4 optical sizes × multiple weights) | Adobe, personal-use | Body serif |
| Myriad Pro | 20 files (standard, condensed, semicondensed) | Adobe, personal-use | Sans companion |
| AntSerif | 4 files | OFL | Fallback serif |
| Montserrat | 2 variable TTFs (upright + italic) | OFL | wnc theme heading |
| Open Sans | 2 variable TTFs (upright + italic) | OFL | wnc theme body |

## CLI flags

```
python -m pdf input.md [output.pdf]
    --output-dir DIR    output to a directory instead of next to the input
    --style PATH        optional CSS overlay loaded after the base style
    --base-style PATH   replace the bundled base style.css (default: bundled)
    --html              emit styled HTML instead of PDF
```

Multiple markdown files convert in batch; `make`-style dependency tracking
is best done in the consumer's own Makefile.
