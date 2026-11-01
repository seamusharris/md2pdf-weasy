# Public Python API and CLI contract

This document is the compatibility boundary for programmatic and command-line
consumers. The five legacy callables retain their exact signatures and return
values. The result-building APIs below are additive.

## Supported Python callables

| Callable | Import path | Contract |
|---|---|---|
| `build_pdf(md_path, output_path=None, style_path=None, base_style_path=None, base_url=None)` | `pdf.render` or `pdf` | Write a PDF/UA-1 file, print `Created: <path>`, and return the output path. The default replaces the Markdown suffix with `.pdf`. |
| `build_html(md_path, output_path=None, style_path=None, base_style_path=None)` | `pdf.render` or `pdf` | Write styled HTML, print `Created: <path>`, and return the output path. The default replaces the suffix with `.html`. |
| `parse_front_matter(content)` | `pdf.render` or `pdf` | Return `(metadata, body)`. Missing front matter returns `({}, content)`; malformed/non-mapping front matter warns and returns the same fallback. |
| `md_to_html(md_content, metadata)` | `pdf.render` or `pdf` | Return one complete HTML document after typography, Markdown conversion, and post-processing. Non-mapping metadata and invalid width controls warn and fall back as documented. |
| `postprocess(html, metadata=None)` | `pdf.postprocess` | Return the transformed HTML string after the standalone HTML post-processing pipeline. |
| `build_pdf_with_result(md_path, output_path=None, style_path=None, base_style_path=None, base_url=None, *, resource_context=None, strict_codes=())` | `pdf.render` or `pdf` | Write a PDF/UA-1 file and return `BuildResult(output_path, diagnostics)`. Without a resource context it preserves legacy resolution. |
| `build_pdf_from_markdown(md_content, output_path, *, resource_context, style_path=None, base_style_path=None, strict_codes=())` | `pdf.render` or `pdf` | Build from source text using a required explicit `ResourceContext`, then return `BuildResult`. |

The existing top-level `pdf` package also exports utilities such as
`resolve_tables_include`, `get_style_path`, `check_font`, `DEFAULT_STYLE`, and
`classify_marker_rows`. They remain available for compatibility, but are
advanced implementation utilities rather than part of the five-callable
legacy surface. `BuildResult`, `DiagnosticsReport`, `StrictPolicy`,
`StrictDiagnosticsError`, `ResourceContext`, and `ResourceAccessError` are
exported for the additive PDF APIs.

### `build_pdf` and `base_url`

`base_url` is a trailing optional parameter, so calls written before it was
added keep the meaning of every positional and keyword argument. When set, it
is passed to WeasyPrint's HTML resolver for relative images and links. When
omitted, it defaults to the directory containing the Markdown source, so
ordinary relative image paths work in both the API and CLI:

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
`--base-url` option. Use the Python API when an explicit override is required.

Before rendering, `build_pdf` validates every local `<img src>` resolved
against that base and raises `FileNotFoundError` if any file is absent. Remote
and data URLs are not treated as local files by this preflight.

The additive result API accepts the same `base_url` only in legacy resolution
mode. Supplying both `base_url` and `resource_context` raises `ValueError`.
See [Diagnostics and explicit resources](diagnostics-and-resources.md) for the
report schema, strict validation and local-resource rules.

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

The result APIs preserve those defaults. Selected strict diagnostic codes raise
`StrictDiagnosticsError` before rendering or opening the output and carry the
complete report on the exception. An unknown strict code is a configuration
error. Explicit resource-root violations raise `ResourceAccessError`; missing
images and styles remain fatal file errors. These exceptions also carry the
diagnostics collected before the failure when the runtime permits attributes on
the exception object.

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
PDF mode additionally supports `--resource-root`, `--allowed-resource-root`,
`--diagnostics-json`, `--strict`, and repeatable `--strict-code` options. The
JSON sidecar is restricted to one input and cannot overwrite the input or PDF.
Strict failures write the requested sidecar before returning a nonzero status.
These new options are rejected with `--html` because saved HTML has no resource
copying or multi-base stylesheet contract.
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
