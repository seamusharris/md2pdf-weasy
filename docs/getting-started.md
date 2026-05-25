# Getting started

## Install

For local dev (changes in `~/Repos/md2pdf-weasy/` take effect immediately
in any project whose venv has installed it):

```bash
pip install -e ~/Repos/md2pdf-weasy
```

For a stable pinned version:

```bash
pip install "md2pdf-weasy @ git+ssh://git@github.com/seamusharris/md2pdf-weasy.git@v0.1.0"
```

WeasyPrint needs Pango + Cairo on the system. On macOS: `brew install pango`.

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

## What to explore next

- [front-matter.md](front-matter.md) — every supported field
- [tables.md](tables.md) — table layouts and column widths
- [themes.md](themes.md) — the four bundled themes and how to add your own
- [callouts.md](callouts.md) — blockquote callout keywords
