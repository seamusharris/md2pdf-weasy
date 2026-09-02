# md2pdf-weasy

Markdown → PDF via WeasyPrint, with YAML front-matter control over
table layouts, blockquote callouts, page breaks, and typography. Ships
with curated fonts (Adobe Minion Pro + Myriad Pro for serif body and
sans companion, plus AntSerif, Montserrat, Open Sans) and four named
themes.

**Private package** — bundled Adobe fonts (Minion Pro, Myriad Pro) are
personal-use licensed; do not redistribute. Distribution entitlement for a
package artifact, another environment, or any recipient is currently **not
verified**; see the [distribution decision and preflight](docs/distribution-entitlement.md).
The OFL fonts (AntSerif, Montserrat, Open Sans) can be redistributed freely.

## Install

The existing owner may use an already-installed checkout only inside its
already-authorized local environment. Do not clone, install, package, or send
this font-bearing source tree to another environment or recipient on the
strength of this README. The current entitlement preflight rejects those
operations until separately approved evidence is recorded.

Requires Python 3.11–3.13 and WeasyPrint's system libraries (Cairo +
Pango). Python 3.14 is currently excluded because the validated macOS
native stack can crash intermittently during Pango/Fontconfig teardown.
On macOS: `brew install pango`.

## Development

Self-contained venv inside the repo — two commands from a fresh clone:

```bash
make setup      # creates .venv/, installs package + test extras editable
make test       # ~80 tests, ~2s
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
- **[v0.1.0 rendering migration](docs/v0.1.0-migration.md)** — compatibility evidence, table-width controls, and rollback warnings
- **[Callouts](docs/callouts.md)** — blockquote callouts, keyword detection, custom keywords
- **[Typography](docs/typography.md)** — ASCII → Unicode conversions, embedded page-break markers
- **[Images and figures](docs/images.md)** — captions, full-width and full-page figures, two- and three-across layouts
- **[Domain features](docs/domain-features.md)** — `tracked_rows`, `direction_markers`, `risk_tables`, verdict CSS classes
- **[Fonts](docs/fonts.md)** — bundled families, licences, adding more
- **[Distribution entitlement](docs/distribution-entitlement.md)** — Adobe-font environment/recipient matrix and fail-closed preflight
- **[Downstream canary](docs/downstream-canary.md)** — guarded consumer-owned API, resource, theme, opt-out, and rollback coverage

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
pipeline, and [docs/public-api.md](docs/public-api.md) for the ratified API and
CLI compatibility contract.
