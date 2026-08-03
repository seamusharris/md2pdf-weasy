# Getting started

## Install

The package bundles non-redistributable Adobe font software. Distribution
entitlement for new package artifacts, environments, and recipients is currently
not verified, so this guide does not prescribe a clone or install command. An
existing owner may continue using an already-installed checkout only in its
already-authorized local environment. Before any new install/package workflow,
follow the [distribution entitlement decision](distribution-entitlement.md) and
obtain separate explicit approval for the exact environment and recipient.

If upgrading an existing v0.1.0 document, follow the
[rendering migration guide](v0.1.0-migration.md) for the automatic table-width
fallback, compatibility evidence, and accessibility-aware rollback guidance.

Python 3.11–3.13 is supported. Python 3.14 is currently excluded because
the validated macOS native stack can crash intermittently during
Pango/Fontconfig teardown. WeasyPrint also needs Pango + Cairo on the
system. On macOS: `brew install pango`.

## First render

```markdown
---
title: "My Document"
subtitle: "Optional subtitle"
theme: alpine
---

## Section heading

Body text with **bold** and *italic*. A [link](https://example.com).

| Column A | Column B |
|----------|----------|
| First    | Second   |

> **Note:** A blockquote starting with a keyword becomes a callout.
```

```bash
python -m pdf input.md output.pdf
```

That's it. The bundled `style.css` is the default base, the `alpine` named
theme is loaded via the front-matter `theme:` key, and you get a PDF.

## What's happening under the hood

1. YAML front matter is parsed
2. ASCII typography (`--`, `->`, `"text"`, `don't`, `...`) → proper Unicode
3. Markdown → HTML via `python-markdown` with a curated extension set
4. Post-processing applies table layouts, callout classes, row
   highlighting, page-break markers
5. CSS is concatenated (base + theme + front-matter-driven rules)
6. WeasyPrint renders HTML + CSS → PDF

## Python API

The high-level entry points live in `pdf.render`:

```python
from pdf.render import build_pdf, build_html

# markdown file → PDF file (returns the output path)
build_pdf("report.md", "report.pdf")

# same pipeline, but emit self-contained HTML (CSS inlined in <style>)
build_html("report.md", "report.html")
```

The output and stylesheet arguments correspond to the CLI options:

```python
build_pdf(
    "report.md",
    output_path="out/report.pdf",   # defaults to input with .pdf/.html
    style_path="overlay.css",        # optional overlay (== --style)
    base_style_path="style.css",     # base CSS (== --base-style; defaults to bundled)
)
```

`build_pdf` also has a trailing optional `base_url` parameter for resolving
relative URLs during WeasyPrint rendering. It is deliberately not exposed by
`build_html` or the CLI: saved HTML needs a separately designed `<base>`/asset
contract, while a CLI flag would be a new command-line API. See the
[public API and CLI contract](public-api.md) for exact signatures and failure
behavior.

If `output_path` is omitted it defaults to the input path with the
extension swapped.

### Lower-level pipeline

The stages `build_pdf` runs are exposed individually if you need to
intercept the HTML or metadata:

```python
from pdf.render import parse_front_matter, md_to_html
from pdf.postprocess import postprocess

content = open("report.md", encoding="utf-8").read()
metadata, body = parse_front_matter(content)   # (dict, remaining_markdown)
html = md_to_html(body, metadata)              # full HTML document string
```

- `parse_front_matter(content)` → `(metadata, body)`; also warns on
  unknown/mistyped front-matter keys.
- `md_to_html(body, metadata)` runs typographic conversion, source
  normalisation, markdown→HTML, and post-processing, returning a complete
  HTML document.
- `postprocess(html, metadata=…)` (in `pdf.postprocess`) is the HTML
  transform pass on its own — table layouts, callout classes, row
  highlighting, page-break markers — if you produce HTML by other means.

## What to explore next

- [front-matter.md](front-matter.md) — every supported field
- [tables.md](tables.md) — table layouts and column widths
- [v0.1.0-migration.md](v0.1.0-migration.md) — rendering compatibility and rollback
- [themes.md](themes.md) — the four bundled themes and how to add your own
- [callouts.md](callouts.md) — blockquote callout keywords
