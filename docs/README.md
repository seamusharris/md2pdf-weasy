# md2pdf-weasy documentation

Topic-based reference docs. The [project README](../README.md) is the
landing page; this directory is for depth.

## Contents

| Doc | What it covers |
|---|---|
| [getting-started.md](getting-started.md) | Install, first render, the minimum viable document |
| [python-compatibility.md](python-compatibility.md) | Supported Python, WeasyPrint, and native-library ranges; tested release stack and stability evidence |
| [diagnostics-and-resources.md](diagnostics-and-resources.md) | Structured table diagnostics, strict validation, and deterministic resource contexts |
| [public-api.md](public-api.md) | Supported Python callables and CLI entry points, including failure behavior |
| [front-matter.md](front-matter.md) | Every supported front-matter field, with types and examples |
| [themes.md](themes.md) | The four named themes (alpine, wnc, regrading, neutral) + compact; how to add your own |
| [tables.md](tables.md) | Per-document table layouts, `tables_include`, default widths registry, alignment, highlight modes, section dividers |
| [table-widths.md](table-widths.md) | Automatic typed column widths — how columns are classified, grouped to share a width, and sized; flex columns; overrides |
| [callouts.md](callouts.md) | Blockquote callouts, keyword detection, `extra_callout_keywords` |
| [typography.md](typography.md) | ASCII → Unicode conversions, embedded page-break markers |
| [images.md](images.md) | Captioned figures, full-width and full-page images, two- and three-across layouts |
| [domain-features.md](domain-features.md) | `tracked_rows`, `direction_markers`, `risk_tables`, verdict CSS classes |
| [fonts.md](fonts.md) | Bundled font families, licences, adding more |

## Conventions

- Each doc is reference-first: look up the syntax you need, with examples
  alongside.
- Code samples are runnable (front matter + a snippet of markdown that
  exercises the feature).
- When adding a new feature, add or extend the relevant doc — don't
  inflate the project README.
