---
title: "Design System Architecture"
subtitle: "Palette, marks, and typography tokens — where they live, how they sync, how md2pdf-weasy consumes them"
toc: true
toc_depth: 2
h2_page_break: true
---

## The problem in three sentences

Within one project, a design value (a netball position colour, a brand mark, a typography token) should appear identically across every consumer — PDF reports, a hypothetical website, Python chart code, future tools — without anyone copying it manually. **And** when the same value is shared across multiple projects (a personal brand green, a shared semantic positive / negative convention, a logo used in every PDF you produce), every project should pick up the same canonical version, and updating it should propagate everywhere automatically. **And** the mechanism for that sharing should be lightweight enough that it actually gets used rather than abandoned for "I'll just copy it again."

This document maps the options for getting there at all three layers — within-project sync, cross-project sharing, and asset types beyond palette — the choices involved, and the changes (if any) md2pdf-weasy needs to support them.


## How CSS loads today in md2pdf-weasy

Before discussing changes, the current cascade. The package loads CSS in this exact order in `pdf/render.py`:

| Order | Layer | Source |
|---|---|---|
| 1 | Base | bundled `pdf/styles/style.css` — package defaults: `--color-*`, layout, typography |
| 2 | CLI overlay | only if `--style PATH` is passed at the command line |
| 3 | Theme | `alpine.css` / `regrading.css` / etc., from front-matter `theme:` |
| 4 | Front-matter rules | synthesised from `h2_page_break:` etc. |

Two things this reveals are important to the rest of the document:

> **Note:** The CLI `--style` overlay loads *before* the theme. The theme overrides the overlay, not the other way around. Fine for theme intent. Wrong direction if the overlay is a project palette that wants to win over the theme's defaults.

> **Note:** There is no `style:` front-matter field today. A doc can't declare an overlay without invoking it from the command line. This is a real gap if we want each doc to pull in its project palette automatically.


## The conceptual model

Two distinct layers of styling, with clear ownership.

### Themes are package-level visual style

Themes live in the package. They express opinion on:

- Typography (font choices, weights, sizes)
- Spacing (compact vs roomy)
- Table density and chrome
- What `--color-up` and `--color-down` should look like for that theme's identity
- Theme-specific rules (e.g. the regrading theme's direction-arrow callouts)

Selected via `theme:`. Swappable. The same document with different themes produces visually distinct documents.

### Palettes are project-level colour values

Palettes belong to the project, not the package. They express:

- The project's chart colours (netball's 8 chart palette positions)
- Semantic project colours (positive / negative / neutral in the project's brand)
- Domain-specific colours (age-group colours, club colours, position colours)
- Optional overrides of package vars (re-tinting a theme to match the project's brand)

Not part of the package. Declared per-project, consumed by every doc in that project.

### The orthogonality

You can pair any theme with any palette:

- `theme: regrading` + netball palette → netball-branded regrading report
- `theme: wnc` + netball palette → netball-branded wnc-styled document
- `theme: regrading` + a different project's palette → same chrome, different colours

Themes stay project-agnostic. Palettes stay theme-agnostic. The cascade combines them.

### The naming convention that makes this work

| Namespace | Owned by | Examples |
|---|---|---|
| `--color-*` | Package + themes | `--color-up`, `--color-text`, `--color-link`, `--color-highlight` |
| `--palette-*` | Project | `--palette-positive`, `--palette-age-9u`, `--palette-position-goal-attack` |

Themes consume `--color-*`. Project palettes own `--palette-*`. Both can be referenced from doc body and from CSS overlays.

A project palette CAN override `--color-*` values to re-tint a theme — that's the "deep integration" case. Whether to do it is a project choice, not a package mandate.


## Three options for where palette values live

These are the only three structural choices. They're not mutually exclusive — a project can use Option 2 for its shared palette and still use Option 1 in a doc that demos literal hex values.

### Option 1 — Inline hex in the doc

Hex values live in each document.

```html
<span class="swatch" style="background:#4a7fb5"></span>
```

| | Detail |
|---|---|
| **Pro** | Self-contained. No separate file. No package change needed. |
| **Pro** | Works today — this is what the migrated `style_guide.md` sample does. |
| **Con** | Duplicates the project's other sources (Python, web). If netball's `charts/theme.py` defines `COLOURS = ["#4a7fb5", ...]`, the doc duplicates those values. Drift is inevitable. |
| **Con** | Documents that *consume* a palette colour (a regrading report tinting promoted teams in the project's positive green) have to inline the hex too, not reference a variable. |
| **Con** | Updating a colour means editing N documents. |

Best for: documents whose content IS the palette listing, and there are no other consumers of those values.

### Option 2 — Project palette as a CSS overlay file

The project ships a CSS file. Docs load it. Body content references vars.

```css
/* netball/palette/palette.css */
:root {
    --palette-chart-blue:   #4a7fb5;
    --palette-positive:     #3a9a5b;
    --palette-age-9u:       #6db8d0;
    /* ... */

    /* Optional: re-tint the regrading theme by overriding --color-* */
    --color-up:   var(--palette-positive);
    --color-down: var(--palette-negative);
}
```

```yaml
---
theme: regrading
palette_style: ../palette/palette.css   # new field, see "Required package changes"
---
```

```html
<!-- doc body -->
<span class="swatch" style="background:var(--palette-positive)"></span>
```

| | Detail |
|---|---|
| **Pro** | Single source per project. Every doc in the project references the same file. |
| **Pro** | Docs consuming the palette (not just documenting it) reference vars instead of hex — no duplication. |
| **Pro** | Change a colour once, every doc rebuilds with the new value. |
| **Pro** | Enables theme re-tinting via the `--color-*` override pattern. |
| **Pro** | The same `palette.css` can be loaded by a website — it's standard CSS. |
| **Con** | Still duplicates if other consumers (Python, JS) hardcode the same values rather than reading the CSS. See *cross-medium sync* below. |
| **Con** | Needs a package change: a front-matter field for "post-theme CSS overlay". |

Best for: projects with stable palettes used across multiple docs.

### Option 3 — Palette declared in front matter, package synthesises CSS

```yaml
---
title: "Style Guide"
theme: regrading
palette:
  chart-blue:   "#4a7fb5"
  positive:     "#3a9a5b"
  age-9u:       "#6db8d0"
---
```

The package reads `palette:`, generates `:root { --palette-chart-blue: #4a7fb5; ... }`, and appends it to the cascade after the theme.

| | Detail |
|---|---|
| **Pro** | More ergonomic for one-off or standalone documents — no separate file. |
| **Pro** | YAML reads more naturally than CSS for non-CSS-fluent authors. |
| **Pro** | Single-file documents stay single-file. |
| **Con** | Needs a package change (~20 lines: parse front matter key, emit CSS). |
| **Con** | Doesn't help when many docs share a palette — you'd duplicate the front-matter block. |
| **Con** | YAML in front matter limits what you can express (no `var()` references, no calculated values). |

Best for: standalone documents with a small palette that doesn't recur elsewhere.


## Three options for cross-medium sync (the netball-website-Python question)

Now the harder layer: if the palette needs to be the same in PDF, on a website, and in Python chart code, the single source of truth has to live *above* every consumer, not inside any one of them.

```
                  palette.yml  (source of truth)
                       │
       ┌───────────────┼───────────────┐
       ▼               ▼               ▼
  palette.css     palette.py       site.css
  (PDF pipeline)  (charts code)    (web bundle)
```

### A — Hand-sync

Edit each consumer's file separately. Trust yourself to keep them in step.

| | Detail |
|---|---|
| **Pro** | No tooling. |
| **Con** | Drift is inevitable. Even with discipline, the moment a colour gets tweaked, one consumer lags. |
| **Con** | Three places to remember when adding a new colour. |

Don't.

### B — YAML source, generated outputs

A neutral source file (YAML or TOML or JSON — YAML is most readable) lives in the project. A small generator script reads it and writes per-consumer outputs.

```
netball/
  palette/
    palette.yml          ← edit this
    palette.css          ← generated, consumed by md2pdf-weasy
    palette.py           ← generated, consumed by charts/theme.py
    site.css             ← generated, consumed by the website
    generate.py          ← the generator script (~30 lines)
```

Run the generator after any change. Each consumer reads its native format.

| | Detail |
|---|---|
| **Pro** | Each consumer stays in its own ecosystem (CSS for CSS readers, Python for Python). No runtime cross-dependencies. |
| **Pro** | Generator is project-internal — md2pdf-weasy doesn't need to know YAML exists. |
| **Pro** | Generated files can be committed to git, so every consumer works without running the generator (good for CI / fresh clones). |
| **Pro** | Easy to add new output formats (SCSS, Tailwind config, JSON for a JS bundle). |
| **Con** | Generator step has to be run when the YAML changes. Mitigate with a pre-commit hook or `make` target. |
| **Con** | If someone edits a generated file directly, the YAML drifts from reality. Mitigate with a comment header on generated files: "This file is generated. Edit palette.yml instead." |

This is the pragmatic sweet spot for any project of netball's size.

### C — Each consumer reads YAML at use-time

No generator. Every consumer parses the YAML directly.

- Python imports YAML via `yaml.safe_load`
- Web bundle imports JSON or YAML at build time
- md2pdf-weasy grows a `palette_yaml:` front-matter field that reads the file and synthesises CSS at render time

| | Detail |
|---|---|
| **Pro** | No generator step. Edit YAML, everyone picks it up on the next render or build. |
| **Pro** | The YAML structure IS the contract — visible to everyone. |
| **Pro** | Onboarding a new consumer means writing one YAML parser. |
| **Con** | Every consumer needs YAML parsing logic. Small but real. |
| **Con** | Renaming a key is a breaking change for every consumer simultaneously. |
| **Con** | Requires another package change (parse YAML file, emit CSS at render). |

Best for: small projects that don't want a generator step, or future expansion where the YAML becomes a published contract.

These three aren't exclusive either. The pragmatic recipe is **B + later C**: ship the generator now, and *separately* add YAML support to md2pdf-weasy later if the generator step becomes annoying enough to remove. The CSS output of (B) is still useful for the web consumer either way.


## Cross-project sharing

The previous section handled "one project, many consumers." This one handles "many projects, shared values." They're related but the decisions are different.

If multiple projects need the same colour (a personal brand green, a shared semantic positive / negative convention, a colour-blind-safe scale shared across reporting projects), the source of truth has to live *above* every project — not inside any one of them. And updates have to flow into each consuming project automatically, or at least with a single command.

### What's typically shared vs project-specific

A useful split before picking a mechanism:

| Layer | Examples | Sharing strategy |
|---|---|---|
| **Common conventions** | semantic positive / negative / neutral; WCAG-AA contrast variants of those | One shared source, used unchanged across many projects |
| **Personal brand** | "my projects all use this navy / this gold" | One shared source, used unchanged |
| **Project-specific** | netball positions, club colours, age groups | Owned by the project, not shared |
| **Doc-specific** | one report needs a specific extra colour for one chart | Owned by the doc, not even shared across the project |

A single project palette (netball's `palette.yml`) can compose multiple layers — pull in shared values and extend with project-specific ones. The composition mechanism is what we have to pick.

### Five structural options for cross-project sharing

#### X1 — Don't share. Each project owns its own everything.

Every project defines its full palette independently. If two projects use `#3a9a5b` for "positive", that's a coincidence.

| | Detail |
|---|---|
| **Pro** | Zero infrastructure. |
| **Pro** | Projects fully isolated — no cross-project dependencies. |
| **Con** | Drift inevitable. Personal brand green becomes "approximately the same shade" across projects within a year. |
| **Con** | Updating "my brand green" everywhere is a manual N-projects edit. |

Best for: solo work where cross-project consistency genuinely doesn't matter, or projects that don't share visual identity.

#### X2 — Shared palette as a versioned package (pip / npm)

Maintain `harris-palette` as its own repo. Publish to PyPI (and / or npm for web consumers). Each project depends on it.

```
harris-palette/         ← own repo, published to PyPI
  palette.yml
  generate.py
  src/harris_palette/   ← Python package with the values importable

netball/                ← depends on harris-palette
  pyproject.toml: dependencies = ["harris-palette"]
  palette/
    palette.yml         ← project-specific values
    generate.py         ← imports harris-palette and merges
```

| | Detail |
|---|---|
| **Pro** | Cleanest separation. Versioned releases. Visible dependency graph. |
| **Pro** | Web consumers can get the same values via npm if the package also publishes JS. |
| **Pro** | Each project pins a version, opts into upgrades on its own timeline. |
| **Con** | Package management ceremony. Publish workflow, version bumps, dependency declarations in every project. |
| **Con** | Slowest feedback loop: update shared palette → bump version → publish → upgrade each project. |
| **Con** | Cross-language sync (Python ↔ JS) still requires shared package to ship both, or the same YAML to be re-consumed by each. |

Best for: shared palette is genuinely product-grade infrastructure used by multiple unrelated projects (or other people).

#### X3 — Shared palette as a vendored file with sync command

The shared palette lives in one canonical repo (or a folder somewhere). Each consuming project copies in a snapshot, with a header comment marking it as vendored. A `make sync-palette` (or similar) target re-pulls the canonical version.

```
~/Repos/personal-palette/       ← single canonical source (git repo)
  palette.yml

netball/palette/
  shared-palette.yml            ← copy with "vendored from upstream — run make sync"
  palette.yml                   ← project-specific values
  generate.py                   ← reads both files, merges
  Makefile: sync-palette pulls latest from ~/Repos/personal-palette
```

| | Detail |
|---|---|
| **Pro** | No package manager. Plain files, plain make targets. |
| **Pro** | Each project has a local copy that works offline / without network. |
| **Pro** | Sync is explicit — you know when you're updating. |
| **Con** | Each project can drift from upstream until `make sync` is run. |
| **Con** | Need a convention for where the canonical source lives (a local repo path, a git URL, an S3 bucket). |

Best for: small ecosystems where everything is local, fast iteration matters more than versioning ceremony.

#### X4 — Shared palette via filesystem reference (symlink, submodule, relative path)

The shared file lives in one location. Projects reference it by relative path, symlink, or git submodule.

```
~/Repos/
  personal-palette/
    palette.yml              ← canonical
  netball/
    palette/
      generate.py            ← reads ../../personal-palette/palette.yml
      palette.yml            ← project-specific values
```

| | Detail |
|---|---|
| **Pro** | Single source of truth, no copying. |
| **Pro** | Edits in the canonical file immediately visible to every project. |
| **Con** | Brittle. Relative paths assume a specific filesystem layout. Move a repo, break the link. |
| **Con** | Git submodules add their own complexity (forget to update, detached HEAD problems). |
| **Con** | Symlinks don't survive `git clone` cleanly. |
| **Con** | Cross-machine collaboration breaks if directory layout differs. |

Best for: single-machine, single-author workflows where the layout is stable. Not recommended otherwise.

#### X5 — CSS @import chain (CSS-only solution)

Skip the YAML/Python sharing question entirely; do it just in CSS. Each project's palette CSS `@import`s a shared upstream stylesheet.

```css
/* netball/palette/palette.css */
@import url("../../shared-palette/shared-palette.css");

/* netball-specific overrides and additions */
:root {
    --palette-position-goal-attack: #cc2222;
    --palette-age-9u: #6db8d0;
    /* ... */
}
```

WeasyPrint supports CSS `@import` (it's standard CSS).

| | Detail |
|---|---|
| **Pro** | Standard CSS mechanism — no custom tooling. |
| **Pro** | Works for the PDF and web cases identically. |
| **Pro** | Composition is clear: upstream imports first, project overrides next. |
| **Con** | Doesn't help Python or other non-CSS consumers — they need their own sync mechanism. |
| **Con** | `@import` URLs need to resolve, which means relative paths or a known location. Same filesystem-layout problem as X4 for relative paths. |
| **Con** | Hex values live in CSS, so a YAML source still needs to exist if you want Python (or anything non-CSS) to consume them. |

Best for: when the only shared consumers are CSS-driven (PDF + web). Pairs well with X3 or X4 for the underlying file distribution.

### How these compose with the within-project sync options

The cross-project options layer above the within-project sync option (A / B / C from earlier). A few sensible combinations:

| Cross-project | Within-project | Result |
|---|---|---|
| X1 (no sharing) | B (YAML + generator) | Each project standalone, internally clean, no cross-project consistency |
| X3 (vendored file) | B (YAML + generator) | Shared YAML pulled in, then merged with project YAML, generator produces all outputs |
| X2 (versioned package) | B (YAML + generator) | Like X3 but with formal versioning and a package manager |
| X5 (CSS @import) | B with caveats | Works if all consumers are CSS-driven; falls apart if Python also needs the values |

> **Note:** Even with cross-project sharing, the within-project generator step is still the pragmatic centre. The generator merges shared and project-specific YAML, then writes per-consumer outputs. That's where the actual composition happens.

### What md2pdf-weasy needs to do for cross-project

The package's role doesn't change much. Cross-project sharing happens at the YAML/CSS file layer *above* the package. What md2pdf-weasy needs:

- The `palette_style:` field already proposed handles a single project palette CSS file, which is the merged output (shared + project-specific) from the within-project generator.
- *Optionally*, support `palette_style:` as a **list** so a doc can declare multiple overlays — e.g. `[shared.css, project.css]` — without needing a generator to merge them. This is a small extension (parse list vs string).
- CSS `@import` works natively in WeasyPrint, so the same effect can be achieved without package changes if projects prefer the @import approach.

So no extra package-level features are *required* for cross-project sharing — the convention-and-cascade model handles it. The only convenience the package could offer is a list-valued `palette_style:` field.


## Beyond palette — a design system repo

The discussion so far has been "palette as a shared thing." But the moment a palette repo exists, other shared assets want to live alongside it. The right framing isn't "palette repo" — it's **design system repo**: the canonical home for every value, asset, or token that defines visual identity across your projects.

### What naturally belongs in a design system repo

| Asset | Format | Git-friendly? | Notes |
|---|---|---|---|
| Colour palette | YAML / CSS | ✓ text | The starting point |
| Logos / brand marks | SVG | ✓ text | Vector scales perfectly in PDF |
| Icons | SVG | ✓ text | Same |
| Watermarks | SVG / small PNG | ✓ for SVG; ✓ for sensible PNG | Keep PNGs under ~100 KB |
| Typography tokens | YAML | ✓ text | Font choices, scale, letter-spacing — the type equivalent of a palette |
| Brand guidelines | Markdown | ✓ text | "When to use the wordmark vs the symbol" docs |

Everything on that list is text, small, and git-trackable. None of it requires LFS, none of it requires binary tooling.

### A realistic shape

```
~/Repos/design-system/                  ← single shared repo
  README.md                             ← what this is, how to consume it
  palette/
    palette.yml                         ← canonical palette
    palette.css                         ← generated
    palette.py                          ← generated
  marks/
    personal-symbol.svg                 ← simple geometric mark
    personal-wordmark.svg               ← name as logo
  type/
    type-tokens.yml                     ← font scale, weights, line-heights
    type-tokens.css                     ← generated
  generate.py                           ← reads all *.yml, writes outputs
  Makefile                              ← `make generate` regenerates everything

~/Repos/netball/                        ← project repo
  brand/
    logo.svg                            ← project-specific marks live here
  palette/
    palette.yml                         ← project-specific extensions
    palette.css                         ← generated (merges shared + project)
    palette.py                          ← generated
    generate.py                         ← imports from design-system
  docs/
    style_guide.md                      ← references var(--palette-*) and
                                          embeds ../../design-system/marks/personal-symbol.svg
```

### The one genuinely ambiguous call: project-specific marks

The colour split is clear (shared brand colours in design-system; project chart palettes in the project). For marks, there's a real choice:

- **Shared repo holds all marks** including the netball logo. One repo to maintain. Becomes a kitchen-sink over time.
- **Project marks stay in the project repo**. Shared repo stays focused on what's actually shared. Cross-project references need to know which repo to look in.

> **Important:** Recommended split — shared repo for *personal / organisational* marks (your own logo, your own brand symbol); project repo for *project-specific* marks (netball logo, club logos, anything bound to one project's domain). Keeps the shared repo focused on what's actually shared.

### How md2pdf-weasy renders graphics

For graphics in PDFs, the package already supports:

- Markdown image syntax: `![](path/to/logo.svg)` — works for SVG, PNG, JPG. WeasyPrint handles all of them.
- Inline `<img src="...">` in raw HTML embedded in markdown.
- Inline `<svg>...</svg>` directly in markdown (raw HTML allowed).

So **no package changes are needed** for embedding graphics in body content. As long as the file path resolves (relative from the doc, or absolute), it embeds correctly.

### Where the package would benefit from a small extension

Two places where the current pipeline doesn't quite reach:

1. **Logo in page header / footer.** Today's `@page { @bottom-right { content: "Page X/Y" } }` supports text only. WeasyPrint actually supports `content: url("path/to/logo.svg")` in `@page` margin boxes — but the package doesn't expose a way to declare a logo in front matter. A `header_logo:` or `footer_logo:` field would wire that in cleanly.

2. **Cover page from front matter.** Some documents want a full-bleed first page with logo + title + subtitle in a specific layout. Currently doable via inline HTML at the top of the markdown body, but a front-matter shortcut would be a nicer interface. (Optional — most users won't need it.)

Both are separate from the palette / sharing question. Worth flagging here as natural neighbours.

### Distributing the design system across projects

Same five mechanisms as the palette discussion (X1–X5), but applied to a tree of files rather than a single CSS file. For binary / SVG assets specifically:

- **X1** — each project copies the assets it needs. Drift problem.
- **X2** — design-system as a pip-installable package. Includes everything (CSS, SVGs as package data, Python modules). Clean but adds pip-install ceremony and a publish step for every change.
- **X3** — vendored copies with a `make sync-assets` command pulling from the shared repo. Pragmatic for solo work.
- **X4** — relative path or git submodule. Works on one machine, brittle across machines.
- **X5** — not applicable for binary/SVG assets.

For graphics, **X3 (vendored) or X4 (relative path / submodule)** are the realistic options. X2 adds disproportionate ceremony for an unpublished personal repo. X4 with git submodule is the cleanest of the brittle options if you're disciplined about updating.

### Composing palette + marks at render time

In practice, a project's doc front matter ends up referencing both:

```yaml
---
title: "Quarterly Report — Q2 2026"
theme: regrading
palette_style: ../palette/palette.css   # generated, includes shared + project palette
header_logo: ../../design-system/marks/personal-symbol.svg   # (proposed)
---
```

The PDF then has:

- Colours coming from the merged CSS (shared brand + netball-specific)
- Personal mark in the page header from the shared design-system repo
- Netball-specific marks (if any) embedded in body via markdown image references to the project's own `brand/` directory

Everything composes through the cascade and the file system. No central registry. No build step beyond the per-project YAML generator.


## How each option interacts with themes

This is the subtle part. Three different things can happen depending on what your palette touches.

### Shallow integration: palette declares `--palette-*` only

The palette adds project-namespace vars. The theme's CSS doesn't reference any of them. So the theme's visual identity is unchanged.

The doc body can use `var(--palette-X)` in swatches, inline styles, or anywhere markdown allows raw HTML. But the theme's chrome — the regrading move-up rows, the alpine callout borders — stays as the theme defines them.

### Deep integration: palette overrides `--color-*`

The palette doesn't just declare `--palette-*` — it also redefines package-namespace vars:

```css
:root {
    --palette-positive: #3a9a5b;          /* project namespace */
    --color-up:         var(--palette-positive);  /* override package var */
}
```

Now the regrading theme's promotion-highlight rows (which reference `var(--color-up)` in `regrading.css`) pick up the project's positive green automatically. The same theme produces a project-tinted document.

This is the strongest form of project-theme combination. The theme stays project-agnostic; the project re-tints it through the cascade.

### Where the palette layer sits in the cascade

For deep integration to work, the palette has to load *after* the theme. The proposed cascade with palette support:

| Order | Layer |
|---|---|
| 1 | Base style.css |
| 2 | Theme (alpine / regrading / etc.) |
| 3 | Project palette (new — Option 2 or 3) |
| 4 | Doc-specific overlay (optional) |

This is a meaningful change from the current order, where the CLI `--style` overlay loads *before* the theme.

> **Important:** If we keep CLI `--style` at its current position (pre-theme) and add `palette_style:` at the new position (post-theme), both fields exist with different cascade roles. That's a deliberate, useful split — `--style` for "set defaults the theme can override", `palette_style:` for "set values that win over the theme". Documenting the difference clearly is important.


## Required package changes by option

Concrete code-change scope for each:

| Option | What needs changing | Approx. LOC |
|---|---|---|
| **Option 1** (inline hex) | Nothing | 0 |
| **Option 2** (CSS overlay) | Add `palette_style:` front-matter field; load file after theme in cascade | ~10 in `render.py` |
| **Option 3** (FM palette) | Parse `palette:` YAML key; synthesise `:root { --palette-*: ... }` block; inject after theme | ~25 in `render.py` |
| **Sync option B** (generator) | Nothing in md2pdf-weasy. Project ships its own script. | 0 (package); ~30 (project) |
| **Sync option C** (YAML at render) | Add `palette_yaml:` front-matter field; parse YAML; emit CSS like Option 3 but from a file | ~35 in `render.py` |
| **Namespace convention** | Document `--palette-*` vs `--color-*` in `docs/`; possibly a lint warning if `palette_style:` defines a non-`--palette-*` var that overrides nothing | ~50 doc; ~0 lint (optional) |


## Decision points

Specific choices to make, in rough order of dependence. Earlier decisions constrain later ones.

### D1 — Adopt the `--palette-*` namespace convention?

If yes: every project that uses md2pdf-weasy follows the same naming. Themes are reusable across projects. Cross-project consistency is achievable.

If no: each project does its own thing. Themes can still be project-tinted via `--color-*` overrides, but there's no canonical way to declare project values.

**My recommendation:** yes. The cost is one doc page. The win is project portability.

### D2 — Add `palette_style:` as a post-theme CSS overlay field?

If yes: projects can declare their palette CSS in front matter, no CLI dance. Cascade puts it after the theme so projects can re-tint themes.

If no: projects either rely on CLI `--style` (which is in the wrong cascade position for deep integration) or inline hex everywhere.

**My recommendation:** yes. Smallest package change with the biggest payoff.

### D3 — Should the package eventually consume YAML directly (Option 3 + sync C)?

If yes: docs can declare palettes in front matter (Option 3) or reference a project YAML (sync C). No CSS regeneration step needed.

If no: projects use sync option B (generator → CSS) and md2pdf-weasy only sees CSS.

**My recommendation:** defer. Ship Option 2 + namespace convention first. Watch for projects where the CSS regeneration becomes painful. If pain emerges, add Option 3 (front-matter YAML); add YAML-file support last if needed.

### D4 — Encourage deep integration (overriding `--color-*` in project palettes)?

If yes: projects can re-tint themes by overriding package vars. The doc can recommend this pattern and even auto-document it.

If no: themes stay untouchable from outside the package. Projects only get to control `--palette-*` content.

**My recommendation:** yes, but document it as a deliberate choice. Some projects will want shallow integration (theme identity stays as the package ships it); others will want deep (project brand swallows the theme). Both are valid; let the project decide per-overlay.

### D5 — For netball specifically, which sync strategy?

Three real options:

- **B (YAML + generator)**: cleanest separation, small generator script, every consumer reads its native format.
- **C-via-Option-2 (handwritten CSS only, no YAML)**: simplest. Don't bother with a YAML source. Edit the CSS by hand and hope nothing else needs the same values. Works if netball's website doesn't exist yet or doesn't share the palette.
- **C-via-Option-3 (YAML at render)**: requires the eventual package change. Skip until D3 is decided.

**My recommendation:** B. Netball already has Python code that consumes these values (`charts/theme.py`). Single source there is a clear win. The generator script is small, and the generated CSS is useful for any future website too.

### D6 — Spin up a dedicated design-system repo?

The most consequential decision in the document. Drives every cross-project answer.

Three options:

- **No shared repo, ever.** Each project owns everything (X1). No cross-project consistency. Smallest infrastructure.
- **Shared YAML/CSS file living somewhere informal** (e.g., in your dotfiles, or as a folder in `~/Repos/`). Lightweight. Lacks discoverability and discipline.
- **Dedicated design-system repo.** Canonical home for palette, marks, type tokens. Discoverable, versionable, can publish to others if it ever matters. Recommended.

**My recommendation:** dedicated repo, but start tiny. Just a palette YAML and a generator. Add marks, type tokens, and other assets as the need arises, not before. The repo's value is in being the *named, known* place — not in being feature-complete on day one.


## Sequencing — a concrete path

Four phases, each independently useful and ordered so the earlier ones don't depend on the later ones.

### Phase 0 — Spin up the design-system repo

Smallest possible starting point:

1. Create `~/Repos/design-system/` (or wherever).
2. Add a `palette/palette.yml` with the values you genuinely want shared across projects (your personal brand colours, semantic conventions, etc. — don't try to be exhaustive).
3. Write a small `generate.py` that reads the YAML and writes `palette.css` and `palette.py`.
4. Commit. Push to a private remote if you want it cross-machine.

No marks, no type tokens yet — add them when the second consumer of those assets appears. The point of this phase is establishing the repo as the *known place*.

### Phase 1 — In md2pdf-weasy

1. Document the `--palette-*` vs `--color-*` namespace convention in `docs/themes.md` (or a new `docs/palettes.md`).
2. Add `palette_style:` front-matter field that loads a CSS file *after* the theme.
3. One commit each.

Total: small package change, foundational for everything else.

### Phase 2 — In netball

1. Create `netball/palette/palette.yml` with project-specific values.
2. Write `netball/palette/generate.py` that imports the shared design-system palette and merges it with the project-specific YAML to produce a single `palette.css` + `palette.py` for the project.
3. Pull in the shared design-system repo via your chosen distribution mechanism (X3 vendored / X4 submodule / X2 package — whichever you picked in D6).
4. Migrate `netball/charts/theme.py` to consume the generated `palette.py`.
5. Migrate `netball/docs/style_guide.md` and any other doc that uses brand colours to reference `var(--palette-X)`.
6. Add a pre-commit hook or `make` target to regenerate when the YAML changes.

Total: project-internal restructure. md2pdf-weasy doesn't change.

### Phase 3 — Optional, later

If sync becomes painful or you want native YAML support:

1. Add `palette:` front-matter field for inline YAML (Option 3).
2. Add `palette_yaml:` front-matter field for file-based YAML (sync C).
3. Add `header_logo:` / `footer_logo:` front-matter fields for `@page` margin-box graphics.

All build on Phase 1.

### Out of scope (for now)

- Auto-generation of palette swatch tables from `--palette-*` vars. Tempting but premature; useful once Phase 1 lands and at least one project is using it.
- A package registry of named palettes / design systems (shared across users via PyPI). Way over-engineered for personal use; revisit if you ever want to publish your system for others.
- Variable-name linting (warn if a project palette overrides a `--color-*` var that doesn't exist). Useful eventually; not blocking.
- Token formats beyond palette / type / marks (e.g., spacing tokens, motion tokens, elevation / shadow tokens). Possible additions to the design-system repo once the core is bedded in.


## TL;DR

- **Palettes and themes are orthogonal.** Themes are package-owned visual style. Palettes are project-owned values. The CSS cascade combines them.
- **The namespace convention is the linchpin.** `--color-*` for the package (themes can re-skin). `--palette-*` for the project (themes don't touch). This is what makes themes reusable across projects.
- **For cross-medium sync within a project** (PDF + web + Python), put the source of truth in a neutral format (YAML) and generate per-consumer outputs. Single source → multiple syncs.
- **For cross-project sharing**, spin up a dedicated design-system repo. Start tiny — just palette + a generator. Add marks, type tokens, and other assets as need arises. The repo's value is being the *named, known* place, not being feature-complete on day one.
- **The package change is small.** One new front-matter field (`palette_style:`) loaded after the theme. Everything else is convention and project-side scripting.
- **The recommended path** is Phase 0 (design-system repo, tiny) → Phase 1 (md2pdf-weasy package change) → Phase 2 (netball migration) → Phase 3 (optional later conveniences).
