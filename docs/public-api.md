# Public Python API and CLI contract

This document is the compatibility boundary for programmatic and command-line
consumers. It records the existing surface; it does not expand it.

## Supported Python callables

| Callable | Import path | Contract |
|---|---|---|
| `build_pdf(md_path, output_path=None, style_path=None, base_style_path=None, base_url=None)` | `pdf.render` or `pdf` | Write a PDF/UA-1 file, print `Created: <path>`, and return the output path. The default replaces the Markdown suffix with `.pdf`. |
| `build_html(md_path, output_path=None, style_path=None, base_style_path=None)` | `pdf.render` or `pdf` | Write styled HTML, print `Created: <path>`, and return the output path. The default replaces the suffix with `.html`. |
| `parse_front_matter(content)` | `pdf.render` or `pdf` | Return `(metadata, body)`. Missing front matter returns `({}, content)`; malformed/non-mapping front matter warns and returns the same fallback. |
| `md_to_html(md_content, metadata)` | `pdf.render` or `pdf` | Return one complete HTML document after typography, Markdown conversion, and post-processing. Non-mapping metadata and invalid width controls warn and fall back as documented. |
| `postprocess(html, metadata=None)` | `pdf.postprocess` | Return the transformed HTML string after the standalone HTML post-processing pipeline. |

The existing top-level `pdf` package also exports utilities such as
`resolve_tables_include`, `get_style_path`, `check_font`, `DEFAULT_STYLE`, and
`classify_marker_rows`. They remain available for compatibility, but are
advanced implementation utilities rather than part of the five-callable
ratified surface.

### `build_pdf` and `base_url`

`base_url` is a trailing optional parameter, so calls written before it was
added keep the meaning of every positional and keyword argument. When set, it
is passed to WeasyPrint's HTML resolver for relative images and links:

```python
from pdf.render import build_pdf

build_pdf(
    "reports/report.md",
    "out/report.pdf",
    base_url="file:///absolute/path/to/reports/",
)
```

This parameter is intentionally PDF-only. `build_html` saves markup instead of
asking WeasyPrint to resolve it; corresponding behavior would require a new
contract for `<base>` and copied assets. The CLI intentionally has no
`--base-url` option. Use the Python API when explicit PDF resource resolution
is required.

## Failure and warning behavior

The file-building callables do not wrap operational exceptions. Missing input
or stylesheet files, unwritable output paths, Markdown failures, and
WeasyPrint render/write failures propagate to the Python caller. A failed call
does not promise to remove an output partially created by an underlying
writer.

Content validation uses warnings and safe fallbacks where continuing is the
established contract:

- malformed or non-mapping YAML front matter warns and is treated as ordinary
  Markdown with empty metadata;
- unknown front-matter fields warn and are otherwise ignored;
- non-mapping metadata and invalid table-width controls passed to `md_to_html`
  or `postprocess` warn and use their documented normalized fallback.

Other mistyped supported fields are not uniformly normalized. They emit the
front-matter type warning when parsed, but a downstream operation may still
raise (for example, a non-string `tables_include`). That exception follows the
same propagation contract as file, Markdown, and render failures.

## Command-line API

The two supported entry points are equivalent and delegate to
`pdf.render.main`:

```text
md2pdf input.md [output.pdf]
python -m pdf input.md [output.pdf]
```

Both support `-o/--output-dir`, `-s/--style`, `-b/--base-style`, and `--html`.
The explicit-output form requires exactly two positional arguments and an
output suffix matching the selected mode. Otherwise inputs are processed in
argument order as a batch.

The CLI deliberately remains a thin synchronous wrapper. An uncaught builder
exception ends the process with a nonzero status and a traceback/diagnostic on
stderr. Batch processing stops at the first failed input: outputs completed
earlier remain, and later inputs are not attempted. There is no retry or
rollback contract.

## Deprecated compatibility alias

The front-matter key `tracked_teams` remains a deprecated alias for
`tracked_rows`. Using it emits a deprecation warning. If both keys are present,
`tracked_rows` wins. This is a content-schema alias, not another Python
callable or CLI entry point.
