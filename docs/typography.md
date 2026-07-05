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
| `5m x 5m` | `5m × 5m` (multiplication) | Digit(s) + `x` + **space** + digit; the space after `x` is required, so `5x5` is left alone |
| `6-8` | `6–8` (en dash) | Isolated digit-hyphen-digit only |
| `"text"` | `"text"` (curly quotes) | Standard pairing rules |
| `don't` | `don't` (curly apostrophe) | Inside a word |
| `teams'` | `teams'` (curly apostrophe) | Trailing apostrophe followed by space/punctuation |
| `...` | `…` (ellipsis) | Three literal dots |

The en-dash rule only fires on an **isolated** digit range — the pattern
requires no digit or hyphen on either side. This deliberately leaves
dates (`2024-05-01`) and win-loss-draw records (`5-3-0`) intact, since
those have a third hyphen-digit group adjacent to the middle hyphen.

Conversion runs on markdown content only — HTML tags are skipped so
attributes don't get mangled, and fenced/inline code is protected (see
[Source normalisation](#source-normalisation-for-generated-markdown)
below).

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
- `orphans: 3` and `widows: 3` on body to avoid lone lines at page edges

The "first `h2` stays on the title page" rule is **not** part of the
unconditional bundled CSS. It (`.content > h2:first-child { break-before:
auto; }`, plus `h1 + h2 { break-before: auto; }`) is injected by
`render.py` only when `h2_page_break: true` is set and there is no TOC —
see [front-matter.md](front-matter.md).

## Source normalisation for generated markdown

Machine-generated markdown often omits the blank lines python-markdown
needs to start a new block. Before conversion, `render.py` repairs two
common cases (`_separate_generated_blocks`):

- **Lists glued to a paragraph** — a list marker (`- `, `* `, `+ `, or
  `1. `) that starts on the line right after a non-blank line gets a blank
  line inserted before it, so it renders as a list rather than being
  swallowed into the preceding paragraph. Consecutive list items are left
  untouched, so genuinely tight lists stay tight.
- **Runs of bold-label field lines** — consecutive lines of the form
  `**Label:** value` (or `**Label**: value`) each get a blank line before
  them, so each field becomes its own paragraph instead of collapsing into
  one run-together block.

A blank is only inserted when a line is glued to a preceding non-blank
line, so already-separated content is never given a double blank.

Both this repair and the typographic conversion run on **raw markdown**,
so fenced code blocks (```` ``` ````/`~~~`) and inline code spans
(`` `...` ``) are stashed behind placeholders first and restored
afterward. Code samples therefore keep their literal `->`, quotes, digit
ranges, and line spacing untouched.

## Where this lives in code

- Typographic conversion: `pdf/typography.py`
- Source normalisation (block separation + code protection):
  `pdf/render.py` (`_separate_generated_blocks`, `_protect_code`)
- Page-break markers: `pdf/postprocess.py:convert_page_breaks`
- Heading binding CSS: `pdf/styles/style.css` "Heading + content binding"
  section
