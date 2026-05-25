# Themes

Themes are CSS files in the package's `styles/` directory. A document
selects one by setting `theme: <name>` in front matter — the renderer
loads `styles/<name>.css` after the base `style.css`.

## Bundled themes

| Name | Aesthetic | What it adds |
|---|---|---|
| `alpine` | Outdoor / training-manual | Muted palette, session-type colour vars (recovery / strength / aerobic / long-hike), traffic-light status colours, `tr.tl-green/amber/red` row tinting |
| `wnc` | Sports-club brand (Warrandyte Netball Club) | Brand red `#DC0032` anchor, navy links, Montserrat headings + Open Sans body, brand-red table headers, position/age/programme palettes as CSS vars |
| `regrading` | Dense data analysis | Tighter table padding, restated highlight/verdict row styling for clarity at the theme level |
| `neutral` | Minimal | Placeholder — uses bundled defaults with no overrides |
| `compact` | Smaller tables only | Orthogonal to the above; can stack via per-doc CSS, but the front-matter `theme:` field accepts only one name |

## Selecting a theme

```yaml
---
title: "Document Title"
theme: alpine
---
```

## How discovery works

The pipeline calls `get_style_path("<name>.css")` which:

1. Returns the path as-is if it's absolute or exists relative to cwd
2. Otherwise looks in `pdf/styles/<name>.css` inside the installed package

`theme:` values containing `/`, `\`, or `..` are rejected with a warning
(no path traversal).

## CSS layering

Every render loads, in order:

1. `--base-style` (default: bundled `style.css`)
2. `--style` (optional CSS overlay passed on the command line)
3. The named theme from `theme:` front matter (if set)
4. Front-matter-driven inline rules (e.g. `h2 { break-before: page }`
   when `h2_page_break: true`)

Later rules win where selectors collide. Use this to: layer a project
overlay on top of a bundled theme, or override one variable in an
otherwise-shared palette.

## Adding a new theme

Drop a CSS file in `pdf/styles/<your-theme>.css`. Convention:

```css
/* ============================================================================
   <your-theme>.css — one-line description

   Multi-line description of what this theme is for.
   ============================================================================ */


/* ── Palette ──────────────────────────────────────────────────────────── */

:root {
    /* override the variables you care about; inherit the rest from style.css */
    --color-link:  #14376b;
    --color-warn:  #c0392b;
    /* ... any new vars specific to this theme */
}


/* ── Type stack overrides (optional) ──────────────────────────────────── */

body { font-family: "Your Font", ...; }
h1, h2, h3, h4, h5, h6 { font-family: "Your Font", ...; }


/* ── Theme-specific component styling (optional) ──────────────────────── */

/* e.g. brand-red underline accent under h2s */
h2::after { content: ''; ... }
```

Then `theme: <your-theme>` in a document's front matter selects it.

## Examples

The bundled `alpine.css`, `wnc.css`, and `regrading.css` are the
canonical worked examples — read them to see the full scope of what
themes can change.
