# Callouts

A blockquote that starts with a known bold keyword becomes a coloured
left-bordered callout box. Keywords are detected case-insensitively and
the colour comes from the bundled palette.

## Built-in keywords

| Keyword | CSS class | Default colour | Use |
|---|---|---|---|
| `Note:` / `Info:` | `note` / `info` | navy `#1e3a5f` | Informational |
| `Tip:` | `tip` | teal `#1a7a6d` | Tips, suggestions |
| `Important:` | `important` | purple `#6b3fa0` | Important context |
| `Caution:` | `caution` | amber `#946b00` | Heads-up |
| `Warning:` | `warning` | red `#d94040` (or theme override) | Errors, hard rules |
| anything else | `default` | grey `#666` | Plain blockquote |

## Syntax

```markdown
> **Note:** This becomes a navy info callout.

> **Warning:** This becomes a red warning callout.

> **Tip:** Multi-paragraph callouts work too.
>
> This second paragraph stays inside the same callout box.
```

The bold keyword + colon is what activates the colour. Without the bold
or without the colon, you get a plain blockquote.

## Extending with custom keywords

Add `extra_callout_keywords:` in front matter:

```yaml
---
extra_callout_keywords:
  Recipe: tip          # treat "Recipe:" as a tip-coloured callout
  Decision: important  # "Decision:" → purple
  Risk: warning        # "Risk:" → red
---
```

Maps keyword (without the colon) to one of the built-in CSS class names.
You can't introduce a new colour through this map — only reuse an
existing one. To introduce a new colour, override the CSS variable in
your theme and add a new CSS class rule.

## Adjacent callouts

Consecutive blockquotes get extra spacing so they don't visually merge.

## How the post-processor decides

`pdf/blockquotes.py` looks at the first text run inside each `<blockquote>`
for a pattern like `<strong>Keyword:</strong>`. If the keyword is in the
built-in or `extra_callout_keywords` map, the blockquote gets that CSS
class. Otherwise it stays as `class="default"`.

Whitespace and punctuation around the keyword are tolerated; the regex
allows for slight markdown rendering variations.
