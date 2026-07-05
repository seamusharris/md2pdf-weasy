# Callouts

A blockquote that starts with a known bold keyword becomes a coloured
left-bordered callout box. Keywords are detected case-insensitively and
the colour comes from the bundled palette.

## Built-in keywords

| Keyword(s) | CSS class | Default colour | Use |
|---|---|---|---|
| `Note:` / `Info:` | `info` | navy `#1e3a5f` | Informational |
| `Tip:` / `Success:` | `tip` | teal `#1a7a6d` | Tips, suggestions |
| `Important:` / `Key:` / `Highlight:` | `important` | purple `#6b3fa0` | Important context |
| `Caution:` / `Attention:` | `caution` | amber `#946b00` | Heads-up |
| `Warning:` | `warning` | red `#d94040` (or theme override) | Errors, hard rules |
| anything else | `default-aside` | grey `#666` | Plain blockquote |

`Note:` and `Info:` both map to the single `info` class — there is no
separate `note` tier. Blockquotes that match no keyword get
`class="default-aside"`, which renders with the base blockquote styling
(grey border, light grey background).

## Syntax

```markdown
> **Note:** This becomes a navy info callout.

> **Warning:** This becomes a red warning callout.

> **Tip:** Multi-paragraph callouts work too.
>
> This second paragraph stays inside the same callout box.
```

The bold keyword is what activates the colour. The trailing colon is
**optional** — `> **Note** text` classifies the same as `> **Note:** text`.
Whitespace around the keyword and colon is tolerated. A plain (non-bold)
blockquote whose text simply starts with `Note:` — or with the `⚠`
warning sign — also gets the `info` class as a fallback (this exists for
compatibility with generated schedule content).

## GitHub-style alerts

The pipeline also recognises GitHub-style alert syntax. This is standard
markdown that renders as visible text in basic renderers and gets styled
in GitHub and in our pipeline:

```markdown
> [!NOTE]
> Content here.

> [!WARNING]
> Something to watch out for.
```

Recognised types and the tier each maps to:

| Marker | CSS class |
|---|---|
| `[!NOTE]` | `info` |
| `[!TIP]` | `tip` |
| `[!IMPORTANT]` | `important` |
| `[!WARNING]` | `warning` |
| `[!CAUTION]` | `caution` |

The `[!TYPE]` marker itself is stripped from the rendered output; only
the content that follows it remains. The type name is case-insensitive.

## Direction-arrow callouts

A blockquote that starts with a `▲` or `▼` arrow (and matches none of the
keywords above) gets `class="up"` or `class="down"` respectively. The
arrow is preserved in the rendered text; the class is what themes hook
into. Only themes that define `--color-up` / `--color-down` (currently
`regrading`) give these a colour — elsewhere the class is a no-op.

```markdown
> ▲ Possums are trending toward promotion.

> ▼ Bilbies are trending toward demotion.
```

Because the arrow check only fires when no keyword matched,
`> ▼ **Warning:** ...` still gets warning styling.

## Extending with custom keywords

Add `extra_callout_keywords:` in front matter. It maps a built-in **tier
name** to a **list of additional bold keywords** to treat as that tier:

```yaml
---
extra_callout_keywords:
  tip: ["Recipe"]          # treat "Recipe:" as a tip-coloured callout
  important: ["Decision"]  # "Decision:" → purple
  warning: ["Risk"]        # "Risk:" → red
---
```

The keys are the built-in tier names (`info`, `tip`, `important`,
`caution`, `warning`); the values are lists of extra keywords, each
matched the same way as the built-ins (bold, optional colon,
case-insensitive). You can't introduce a new colour through this map —
only reuse an existing tier. To introduce a new colour, override the CSS
variable in your theme and add a new CSS class rule.

## Adjacent callouts

Consecutive blockquotes get extra spacing so they don't visually merge.

## How the post-processor decides

`pdf/blockquotes.py` (`classify_blockquotes`) checks each `<blockquote>`,
in order:

1. A GitHub-style `[!TYPE]` marker at the start → that tier (marker
   removed).
2. Any built-in or `extra_callout_keywords` keyword appearing as
   `<strong>Keyword</strong>` (colon optional) → that tier.
3. A leading `▲` / `▼` arrow → `up` / `down`.
4. Plain text starting with `Note:` or `⚠` → `info`.
5. Otherwise → `default-aside`.

Whitespace and punctuation around the keyword are tolerated; the regex
allows for slight markdown rendering variations.
