# Diagnostics and explicit resources

The existing `build_pdf`, `build_html`, `md_to_html`, `parse_front_matter` and
`postprocess` contracts remain unchanged. Two additive PDF APIs expose the
decisions made by the same rendering passes:

```python
from pdf import ResourceContext, build_pdf_from_markdown, build_pdf_with_result

context = ResourceContext(
    "/absolute/document-bundle",
    allowed_root="/absolute/document-bundle",
)

result = build_pdf_with_result(
    "/absolute/document-bundle/report.md",
    "report.pdf",
    resource_context=context,
)

memory_result = build_pdf_from_markdown(
    "---\ntables_include: tables.yml\n---\n\n# Report",
    "memory-report.pdf",
    resource_context=context,
)
```

Both return a frozen `BuildResult` with `output_path` and `diagnostics`. The
source-text API requires a context because there is no source-file directory to
use as an implicit base.

## Diagnostics schema

`BuildResult.diagnostics` is a JSON-safe mapping with `schema_version: 1` and
three deterministic, encounter-ordered arrays:

- `tables`: one entry per table, identified by a one-based document `index` and
  an existing author `id` when present;
- `resources`: explicitly resolved dependencies and resources actually requested
  through the WeasyPrint fetcher;
- `diagnostics`: stable codes with severity and the relevant table index or
  layout key.

Each table reports its origin (`declared`, `preset`, `author_colgroup`,
`automatic`, or `unchanged`), selected and competing layout keys, declaration
source, preset identifier, widths with their real unit, alignment with
provenance, fitting outcome, and any structural skip reason. Declared widths
are percentages; automatic widths are em values and may also identify their
emitted token class. Author colgroups are never relabelled as generated ones.

Diagnostics do not contain headers, body cells, captions, raw HTML, CSS, or
invalid supplied values. Explicit table IDs, layout keys, resource references
and resolved paths are included because they are the identifiers needed to act
on the report. Diagnostics are collected only by the result APIs or the CLI
options below; ordinary rendering does not emit a report.

The stable table codes are:

- `tables.include_missing`
- `tables.include_invalid`
- `tables.layout_invalid`
- `tables.match_ambiguous`
- `tables.required_unapplied`
- `tables.layout_unused`
- `tables.structure_unsupported`
- `tables.width_scaled`
- `tables.overflow_unresolved`

`tables.layout_unused` is informational. Included catalogues may intentionally
contain shapes not used by one document.

## Strict validation

Pass selected codes with `strict_codes`:

```python
build_pdf_with_result(
    "report.md",
    strict_codes={
        "tables.include_missing",
        "tables.match_ambiguous",
    },
)
```

Unknown codes are configuration errors. A selected diagnostic raises
`StrictDiagnosticsError`, whose `report` contains the complete diagnostics and
whose `codes` identifies the failures. Validation happens before WeasyPrint is
invoked or the output is opened, so an existing PDF remains untouched.
When malformed included YAML produces a selected `tables.include_invalid`, the
structured strict error is raised with the YAML parser error retained as its
cause; without that strict selection the existing parser exception still
propagates.

An individual layout can opt into application validation:

```yaml
tables:
  season-ladder:
    required: true
    preset: netball-ladder-v1
```

`required: true` succeeds only when that exact declaration is selected and
applied. A shadowed match, author colgroup, unsupported table structure or
header mismatch does not count. Without strict selection the code remains
observational and the existing permissive warning/fallback behavior continues.

## Explicit resource context

`ResourceContext` accepts an existing absolute local directory or a local
`file:` directory URI. Relative bases, remote bases and nonlocal `file://host/`
authorities are rejected. In explicit mode:

- relative `tables_include`, image, `style_path`, `base_style_path` and theme
  override references resolve only against the context;
- the working directory is never consulted for those dependencies;
- absolute paths and local file URIs remain absolute;
- remote and data URLs retain the existing WeasyPrint policy and are not
  prefetched by the context;
- each user stylesheet keeps its own directory as the base for `@import` and
  `url()` references;
- bundled styles and fonts keep their package base and remain available.

When `allowed_root` is set, resolution follows symlinks and rejects local paths
that escape the resolved root through `..`, an absolute reference, a file URI,
percent encoding or a symlink. The same check runs at actual WeasyPrint fetches,
covering nested CSS, fonts, images and SVG resources. Only the package's own
`pdf/styles` and `pdf/fonts` directories receive a narrow exception.

This is a local-file containment control, not a general sandbox. It does not
disable network access, limit resource size, isolate native libraries or defend
against a concurrently changing filesystem. Use a separate process/container
policy for untrusted documents.

The legacy mode is intentionally unchanged: includes remain cwd-first then
source-directory-relative, images default to the Markdown directory or the
existing `base_url`, and concatenated CSS URLs retain the bundled styles base.
The result API rejects a simultaneous `base_url` and `resource_context` instead
of inventing precedence.

## CLI

The PDF CLI adds:

```text
--resource-root DIR
--allowed-resource-root DIR
--diagnostics-json FILE
--strict
--strict-code CODE
```

`--strict` selects the documented default strict set; repeat `--strict-code` to
select individual codes. JSON is written to a sidecar, never mixed with the
existing `Created:` output. Strict failures still write the requested sidecar.
The sidecar cannot overwrite the input or PDF. JSON sidecars support exactly one
input document, including through an existing hardlink alias. Explicit contexts
and diagnostics are PDF-only because saved
HTML has no asset-copying or multi-base stylesheet contract.

Explicit table selection and portable bundle export are separate future
features. This context resolves dependencies but does not copy or rewrite them.
