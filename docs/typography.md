# Typography and page-break markers

Two separate things happen before WeasyPrint sees your document:

1. **Typographic conversion** — plain-ASCII writing conventions are
   upgraded to proper Unicode characters.
2. **Page-break markers** — HTML comments embedded in markdown are
   converted to CSS that controls pagination.

## Typographic conversions

You can write naturally in ASCII; the output PDF gets proper typography.

| ASCII source | Output | Rule |
|---|---|---|
| ` -- ` (spaces around `--`) | ` — ` (em dash) | Surrounding spaces required |
| `->` | `→` (arrow) | Anywhere |
| `5m x 5m` | `5m × 5m` (multiplication) | Digit + `x` + digit pattern |
| `6-8` | `6–8` (en dash) | Digit-hyphen-digit |
| `"text"` | `"text"` (curly quotes) | Standard pairing rules |
| `don't` | `don't` (curly apostrophe) | Inside a word |
| `it's` | `it's` (curly apostrophe) | Followed by space/punctuation |
| `...` | `…` (ellipsis) | Three literal dots |

Conversion runs on markdown content only — HTML tags are skipped so
attributes don't get mangled.

You can still write the Unicode characters directly if you prefer. Both
work; the conversion just makes ASCII source render nicely without
manual character-picking.

## Page-break markers

Two HTML comments influence pagination. They're valid markdown,
invisible in non-rendering tools, and ignored by anything that doesn't
know to look for them.

### Force a page break

```markdown
Some content above the break.

<!-- page-break -->

## Next section starts on a new page
```

Converts to `<div style="break-before: page;"></div>`. Use sparingly —
prefer `h2_page_break: true` in front matter for section-level breaks.

### Suppress an automatic break

```markdown
<!-- no-page-break -->
## This h2 stays where it is, no forced page break
```

When `h2_page_break: true` is active, this marker lets a specific h2
stay in flow rather than starting a new page. Useful when a short
section would otherwise produce a near-empty page.

The marker must immediately precede the heading; whitespace between is
allowed.

## Heading-binding rules (bundled in style.css)

These exist whether or not you use the markers above:

- Headings have `break-after: avoid` and `break-inside: avoid` so a
  heading doesn't end up isolated at the bottom of a page
- `h2 + table`, `h3 + table`, `h4 + table` have `break-before: avoid` so
  a heading and its following table stay together
- The first `h2` inside `.content` has `break-before: auto` so it doesn't
  push to a new page when `h2_page_break: true` is on (the title would
  otherwise be alone)
- `orphans: 3` and `widows: 3` on body to avoid lone lines at page edges

## Where this lives in code

- Typographic conversion: `pdf/typography.py`
- Page-break markers: `pdf/postprocess.py:convert_page_breaks`
- Heading binding CSS: `pdf/styles/style.css` "Heading + content binding"
  section
