# Bundled fonts

The package ships with five font families: two commercial Adobe fonts
(personal-use licensed), one Anthropic OFL font as fallback, and two
Google OFL fonts used by the `wnc` theme.

## What's bundled

| Family | Files | Licence | Used by |
|---|---|---|---|
| **Minion Pro** | 23 OTF | Adobe, personal-use only | Bundled body default + alpine theme |
| **Myriad Pro** | 20 OTF | Adobe, personal-use only | Bundled heading/UI default + alpine theme |
| **AntSerif** | 4 TTF | OFL | Fallback serif, available to any theme |
| **Montserrat** | 2 variable TTF | OFL | `wnc` theme headings |
| **Open Sans** | 2 variable TTF | OFL | `wnc` theme body |

Total: ~51 files, ~10 MB on disk.

## Licensing — read this

The Adobe Minion Pro and Myriad Pro fonts are licensed for personal use
by the package owner. They **must not be redistributed**. Practical
implications:

- The `md2pdf-weasy` GitHub repo is private and must stay private.
- Don't ship the package to PyPI without removing Minion/Myriad first.
- If a third party needs to use the renderer, point them at the OFL
  fonts only.

The OFL fonts (AntSerif, Montserrat, Open Sans) can be freely
redistributed.

## Minion Pro — optical sizes

Minion is declared as four separate font-family names so CSS can pick
the right cut for each size range:

| Family name | Optical | Suitable for |
|---|---|---|
| `"Minion Caption"` | 6-8pt | Table cells, fine print |
| `"Minion Pro"` | 9-13pt | Body text |
| `"Minion Subhead"` | 14-24pt | Section headers |
| `"Minion Display"` | 25pt+ | Document titles |

The bundled `style.css` wires these to elements by default:

```css
body { font-family: "Minion Pro", "AntSerif", "Georgia", serif; }
table { font-family: "Minion Caption", "Minion Pro", "Georgia", serif; }
```

Each optical has Regular, Italic, Bold, Bold-Italic; the Regular optical
also has Medium and Semibold weights for nuanced body emphasis.

## Myriad Pro — widths

Myriad ships in three widths plus extra weights:

| Family name | Width | Weights |
|---|---|---|
| `"Myriad Pro"` | standard | Light, Regular, Semibold, Bold, Black |
| `"Myriad SemiCondensed"` | between standard and condensed | Regular, Bold |
| `"Myriad Condensed"` | tight | Regular, Semibold, Bold |

Used by default for headings, table headers, and UI labels. The
condensed widths are available for tight columns when needed.

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
