# md2pdf-weasy

Markdown to styled PDF via WeasyPrint, with YAML front-matter control over
table layouts, blockquote callouts, page breaks, and typography.

## Installation

```bash
pip install ./pdf
```

Requires Python 3.11+ and a working WeasyPrint installation (which needs
system libraries — see [WeasyPrint docs](https://doc.courtbouillon.org/weasyprint/stable/first_steps.html)).

## CLI Usage

```bash
# Basic conversion
md2pdf input.md                     # writes input.pdf

# Specify output path
md2pdf input.md -o report.pdf

# Use a theme variant
md2pdf input.md --style compact
```

## Python API

```python
from pdf.render import build_pdf, md_to_html, parse_front_matter

# Full pipeline: markdown file -> PDF file
build_pdf("input.md", "output.pdf")

# Stepwise: parse front matter, convert to HTML, then render
text, metadata = parse_front_matter(open("input.md").read())
html = md_to_html(text, metadata)

# Post-process HTML before rendering (optional)
from pdf.postprocess import postprocess
html = postprocess(html, metadata)
```

## Front Matter

Control document styling via YAML front matter at the top of the markdown file:

```yaml
---
title: "Season Report"
subtitle: "2025 Spring"
style: compact            # base | compact | presentation
toc: true                 # generate table of contents
tables:
  schedule:
    columns:
      - { name: Time, width: 14 }
      - { name: Court, width: 6, align: center }
      - { name: Home, width: 28 }
---
```

Key front-matter fields: `title`, `subtitle`, `style`, `toc`,
`tables` (column widths/alignment), `tracked_teams` (bold-highlight rows),
`direction_markers` (up/down row colouring), `extra_callout_keywords`,
`risk_tables`, `auto_align_columns`, `auto_highlight_bold_rows`.

## Blockquote Callouts

Bold keywords at the start of a blockquote apply coloured styling:

```markdown
> **Note:** This gets an info-blue callout.
> **Warning:** This gets a red callout.
> **Tip:** Teal callout.
```

## Full Reference

See [docs/pdf_pipeline.md](../docs/pdf_pipeline.md) for comprehensive
documentation of all front-matter fields, table layouts, embedded markers,
and typography conversion.
