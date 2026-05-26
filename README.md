# md2pdf-weasy

Markdown → PDF via WeasyPrint, with YAML front-matter control over
table layouts, blockquote callouts, page breaks, and typography. Ships
with curated fonts (Adobe Minion Pro + Myriad Pro for serif body and
sans companion, plus AntSerif, Montserrat, Open Sans) and four named
themes.

**Private package** — bundled Adobe fonts (Minion Pro, Myriad Pro) are
personal-use licensed; do not redistribute. The OFL fonts (AntSerif,
Montserrat, Open Sans) can be redistributed freely.

## Install

```bash
# editable, for local dev
pip install -e ~/Repos/md2pdf-weasy

# pinned, for reproducibility
pip install "md2pdf-weasy @ git+ssh://git@github.com/seamusharris/md2pdf-weasy.git@v0.1.0"
```

Requires Python 3.11+ and WeasyPrint's system libraries (Cairo + Pango).
On macOS: `brew install pango`.

## Use

```yaml
---
title: "My Document"
theme: alpine
---

## Section

Body text with a [link](https://example.com).

> **Note:** A keyword blockquote becomes a callout.
```

```bash
python -m pdf input.md output.pdf
```

## Documentation

Topic-based reference docs in [`docs/`](docs/):

- **[Getting started](docs/getting-started.md)** — install, first render, what the pipeline does
- **[Front matter](docs/front-matter.md)** — every supported field, with types and examples
- **[Themes](docs/themes.md)** — the four named themes + how to add your own (per-theme style guides in `examples/styleguides/`)
- **[Tables](docs/tables.md)** — layouts, default widths registry, alignment, highlight modes, section dividers
- **[Callouts](docs/callouts.md)** — blockquote callouts, keyword detection, custom keywords
- **[Typography](docs/typography.md)** — ASCII → Unicode conversions, embedded page-break markers
- **[Domain features](docs/domain-features.md)** — `tracked_rows`, `direction_markers`, `risk_tables`, verdict CSS classes
- **[Fonts](docs/fonts.md)** — bundled families, licences, adding more

## CLI

```
python -m pdf input.md [output.pdf]
    --output-dir DIR    output to a directory instead of next to the input
    --style PATH        optional CSS overlay loaded after the base style
    --base-style PATH   replace the bundled base style.css (default: bundled)
    --html              emit styled HTML instead of PDF
```

## Python API

```python
from pdf.render import build_pdf

# Full pipeline: markdown file → PDF file
build_pdf("input.md", "output.pdf")
```

See [docs/getting-started.md](docs/getting-started.md) for the lower-level
API (parse front matter / convert to HTML / post-process / render).
