# Images and figures

Local PNG, JPEG, GIF and SVG images are embedded in PDF output by WeasyPrint.
Relative paths resolve from the directory containing the Markdown file. A
missing local image fails the build before PDF rendering.

The additive result APIs can instead use one explicit `ResourceContext` for
images, table includes and user styles. Relative image paths then resolve only
from that context, independently of cwd and the Markdown file's location. An
optional allowed root follows symlinks before rejecting escapes. See
[Diagnostics and explicit resources](diagnostics-and-resources.md).

## Captioned figures

A standalone Markdown image becomes a semantic figure. Use the image alt text
for accessibility and the optional Markdown title for the visible caption:

```markdown
![Players standing behind a premiership shield](images/team.jpg "The 1978 Robins premiership team")
```

When no title is supplied, the alt text is also used as the caption.

## Layouts

Add one supported class with Python-Markdown's attribute-list syntax:

```markdown
![Team](images/team.jpg "Full text-width photograph"){.figure-wide}

![Portrait](images/portrait.jpg "Centred, narrower photograph"){.figure-narrow}

![Newspaper page](images/diary.jpg "Source facsimile"){.figure-page}
```

- `figure-wide` uses the full text width.
- `figure-narrow` uses two-thirds of the text width and is centred.
- `figure-page` starts and ends on a new page and fits a large facsimile
  within the printable area.

For two or three figures across one row, place ordinary standalone images in a
Markdown-enabled HTML container:

```html
<div class="figure-grid figure-grid-2" markdown="1">

![First team](images/team-a.jpg "First team")

![Second team](images/team-b.jpg "Second team")

</div>
```

Use `figure-grid-3` for three across. Grids are kept together on one page and
use smaller captions. Prefer two across for photographs with identifiable
people; three across is intended for small supporting images.

Author-written HTML `<figure>` elements are preserved unchanged, so generated
documents may use richer captions with separate credit spans when required.

## Deliberate limits

The first image contract does not provide edge-to-edge bleed or text-wrapped
floating images. Both make print pagination and reading order less reliable.
Remote HTTP images are left to WeasyPrint, but archival documents should use
local, versioned files for reproducibility.
