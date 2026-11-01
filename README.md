# md2pdf-weasy

Markdown → PDF via WeasyPrint, with YAML front-matter control over
table layouts, blockquote callouts, page breaks, and typography. Ships
with curated fonts (Adobe Minion Pro + Myriad Pro for serif body and
sans companion, plus AntSerif, Montserrat, Open Sans) and four named
themes.

**Private package** — this repository is an owner-controlled backup and must
remain private. The bundled Adobe fonts (Minion Pro and Myriad Pro) are
commercial font software: use the repository only on machines covered by an
appropriate Adobe licence, and do not publish or share the font files. The OFL
fonts (AntSerif, Montserrat, and Open Sans) can be redistributed freely.

## Current release

Version 0.3.1 supports Python 3.14 by requiring WeasyPrint 70 or newer, which
contains the upstream fix for a Fontconfig lifetime bug that strongly matches
the earlier intermittent teardown crashes. It includes all table-width and
preset work from 0.3.0 and preserves the existing Python and command-line
interfaces. This remains a private package; it is not intended for publication
to a public package registry while it contains the Adobe font files.

## Install

Clone the private repository onto an owner-controlled, appropriately licensed
machine, then use the development setup below. Do not publish this package to
PyPI or another public registry while it contains the Adobe font files.

Requires Python 3.11–3.14, WeasyPrint 70+, and WeasyPrint's system libraries
(Cairo + Pango). Pango 1.54 or newer is supported for repeated rendering; older
Pango versions can leak Fontconfig state with WeasyPrint 70. On macOS:
`brew install pango`. See [Python and native compatibility](docs/python-compatibility.md)
for the tested stack, historical failure evidence, and support boundary.

## Development

Self-contained venv inside the repo — two commands from a fresh clone:

```bash
make setup      # creates .venv/, installs package + test extras editable
make test       # ~500 tests, ~15s
make examples   # renders examples/**/*.md → PDF beside each source
```

The `make` targets all use `.venv/bin/python` so they work without
activating the venv. Use this venv when running ad-hoc commands too —
e.g. `.venv/bin/python -m pdf input.md output.pdf`.

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
- **[Public API and CLI](docs/public-api.md)** — supported callables, signatures, entry points, and failure behavior
- **[Front matter](docs/front-matter.md)** — every supported field, with types and examples
- **[Themes](docs/themes.md)** — the four named themes + how to add your own (per-theme style guides in `examples/styleguides/`)
- **[Tables](docs/tables.md)** — layouts, default widths registry, alignment, highlight modes, section dividers
- **[Callouts](docs/callouts.md)** — blockquote callouts, keyword detection, custom keywords
- **[Typography](docs/typography.md)** — ASCII → Unicode conversions, embedded page-break markers
- **[Images and figures](docs/images.md)** — captions, full-width and full-page figures, two- and three-across layouts
- **[Domain features](docs/domain-features.md)** — `tracked_rows`, `direction_markers`, `risk_tables`, verdict CSS classes
- **[Fonts](docs/fonts.md)** — bundled families, licences, adding more

## CLI

Installed as both `python -m pdf` and the `md2pdf` console script (from
`pyproject.toml`'s `[project.scripts]`). The two are equivalent.

```
python -m pdf input.md [output.pdf]        # or: md2pdf input.md [output.pdf]
    -o, --output-dir DIR    output to a directory instead of next to the input
    -s, --style PATH        optional CSS overlay loaded after the base style
    -b, --base-style PATH   replace the bundled base style.css (default: bundled)
        --html              emit styled HTML instead of PDF
```

Batch mode: pass multiple markdown files (or a glob) to convert each one
beside its source (or into `--output-dir`):

```bash
python -m pdf *.md
python -m pdf report.md schedule.md --output-dir out/
```

The explicit-output form (`input.md output.pdf`) applies only when exactly
two arguments are given and the second ends in the output extension
(`.pdf`, or `.html` with `--html`).

## Python API

```python
from pdf.render import build_pdf

# Full pipeline: markdown file → PDF file
build_pdf("input.md", "output.pdf")

# Resolve relative Markdown images/links from an explicit source directory
build_pdf("input.md", "output.pdf", base_url="/absolute/source/directory/")
```

Relative Markdown image paths resolve from the Markdown file's directory by
default. Standalone images become captioned figures; see
[Images and figures](docs/images.md) for full-width, full-page, and grid
layouts.

See [docs/getting-started.md](docs/getting-started.md) for the lower-level
pipeline, and [docs/public-api.md](docs/public-api.md) for the supported API and
CLI compatibility contract.
