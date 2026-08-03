# Bundled fonts

The package ships with five font families: two commercial Adobe fonts
(personal-use licensed), one Anthropic OFL font as fallback, and two
Google OFL fonts used by the `wnc` theme.

## What's bundled

| Family | Files | Licence | Used by |
|---|---|---|---|
| **Minion Pro** | 64 OTF | Adobe, personal-use only | Bundled body default + alpine theme |
| **Myriad Pro** | 30 OTF | Adobe, personal-use only | Bundled heading/UI default + alpine theme |
| **AntSerif** | 4 TTF | OFL | Fallback serif, available to any theme |
| **Montserrat** | 2 variable TTF | OFL | `wnc` theme headings |
| **Open Sans** | 2 variable TTF | OFL | `wnc` theme body |

Total: ~102 files, ~21 MB on disk. The full Minion (both widths × all
four optical sizes × four weights × two styles) and most of Myriad
(three widths × five weights × two styles — only SemiExtended omitted)
ship so themes and overlays can reach for any cut without surprise
fallbacks.

## Licensing — read this

The Adobe Minion Pro and Myriad Pro fonts are licensed for personal use
by the package owner. They **must not be redistributed**. Practical
implications:

- The `md2pdf-weasy` GitHub repo is private and must stay private.
- Don't ship the package to PyPI without removing Minion/Myriad first.
- If a third party needs to use the renderer, point them at the OFL
  fonts only.

The repository does not contain the governing Adobe EULA, acquisition record,
or per-environment/per-recipient evidence. Distribution entitlement is therefore
**not verified**, including for package artifacts, consumer canaries, CI/shared
runners, private registries, and source transfers. Do not treat a private repo,
a recipient's Adobe subscription, or Adobe's generic PDF-embedding guidance as
authorization to transfer these font files.

See [Proprietary distribution entitlement](distribution-entitlement.md) for the
decision matrix, required evidence, consumer-owned procedure, current official
Adobe guidance, and the fail-closed preflight. Changing the matrix to authorize
any operation requires separate explicit approval; do not attach licence
documents or font files to the repository.

The OFL fonts (AntSerif, Montserrat, Open Sans) can be freely
redistributed.

## Minion Pro — optical sizes × widths

Minion is split into eight font-family names: four optical sizes ×
two widths (normal and condensed). CSS picks the right cut for each
size range; pair with a condensed family when columns are tight.

| Family name | Optical | Width | Suitable for |
|---|---|---|---|
| `"Minion Caption"` | 6-8pt | normal | Table cells, fine print |
| `"Minion Pro"` | 9-13pt | normal | Body text |
| `"Minion Subhead"` | 14-24pt | normal | Section headers |
| `"Minion Display"` | 25pt+ | normal | Document titles |
| `"Minion Condensed Caption"` | 6-8pt | condensed | Dense tables |
| `"Minion Condensed"` | 9-13pt | condensed | Narrow-column body |
| `"Minion Condensed Subhead"` | 14-24pt | condensed | Tight sidebar heads |
| `"Minion Condensed Display"` | 25pt+ | condensed | Compact titles |

Each family has the full weight axis: Regular (400), Medium (500),
Semibold (600), Bold (700), each with matching italic. That's eight
cuts per family, 64 files in total.

The bundled `style.css` wires the normal-width families to elements by
default:

```css
body  { font-family: "Minion Pro", "AntSerif", "Georgia", "Times New Roman", serif; }
table { font-family: "Minion Caption", "Minion Pro", "AntSerif", "Georgia", serif; }
```

## Myriad Pro — weights × widths

Myriad ships in three widths (normal, semi-condensed, condensed) at five
weights each. The semi-extended width is not bundled.

| Family name | Width | Weights |
|---|---|---|
| `"Myriad Pro"` | normal | Light (300), Regular, Semibold, Bold, Black (900) |
| `"Myriad SemiCondensed"` | between normal and condensed | Light, Regular, Semibold, Bold, Black |
| `"Myriad Condensed"` | tight | Light, Regular, Semibold, Bold, Black |

Each weight has an italic. **There is no Medium (500) cut in Myriad
Pro — Adobe ships no Medium for this family.** Browsers asked for `500`
will fall back to nearest. Use Minion's 500 if you need a true Medium.

Used by default for headings, table headers, and UI labels. The
condensed widths are available for tight columns and dense data tables.

## Variable fonts

Montserrat and Open Sans ship as variable TTFs — one file per style
(upright vs italic) supporting the full weight range continuously.

```css
@font-face {
    font-family: "Montserrat";
    src: url("../fonts/Montserrat%5Bwght%5D.ttf") format("truetype-variations");
    font-weight: 100 900;
    font-style: normal;
}
```

Filenames contain `[wght]` (Montserrat) or `[wdth,wght]` (Open Sans);
the brackets must be URL-encoded as `%5B` and `%5D` in `url()`.

## Adding a font

1. Drop the file in `pdf/fonts/<filename>`
2. Add an `@font-face` declaration in `pdf/styles/style.css` (or in a
   theme file if the font is theme-specific)
3. Reference the family name in element selectors that should use it

Paths in `url()` are relative to the CSS file. Since stylesheets live
in `pdf/styles/`, font URLs use `../fonts/...`.

## Where this lives in code

- Font files: `pdf/fonts/`
- `@font-face` declarations: `pdf/styles/style.css` (defaults) and
  `pdf/styles/wnc.css` (Montserrat + Open Sans for the wnc theme)
- Default element wiring: `pdf/styles/style.css` body / heading / table
  / blockquote sections
