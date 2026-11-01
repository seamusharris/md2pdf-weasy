# Python and native compatibility

## Supported range

md2pdf-weasy 0.3.1 supports:

- Python `>=3.11,<3.15`;
- WeasyPrint `>=70`;
- Pango 1.54 or newer for repeated rendering.

These are support ranges, not a lock file. The exact versions used for a
release check are recorded separately below so a failure can be reproduced
without implying that every supported installation must use those exact
versions. Cairo, Fontconfig, HarfBuzz, GLib and libffi are native system
dependencies resolved by WeasyPrint and Pango rather than Python package
metadata.

Python 3.15 and later are not claimed as supported until they have completed
the same native-process and rendering checks. WeasyPrint versions before 70 are
not supported even if a particular render appears to succeed.

## Why Python 3.14 was previously excluded

The original compatibility investigation used macOS arm64, Python 3.14.6,
WeasyPrint 68.1 and Pango 1.58.0. Two of 10 fresh full-suite processes and two
of 20 fresh theme-suite processes exited abnormally after their assertions had
completed. Python 3.13.13 completed 10/10 and 20/20 equivalent processes, so
0.3.0 conservatively declared `>=3.11,<3.14`.

Later upstream evidence identified a native lifetime defect that strongly
matches the historical symptoms. WeasyPrint 63.1–69 attached a CFFI finalizer
to a Fontconfig configuration and also released the same reference explicitly.
Pango 1.54 and newer releases its own reference when the font map is finalized,
so garbage collection or interpreter shutdown could release the configuration
twice. The defect was reproduced upstream on Python 3.13 as well, showing that
it is not specific to Python 3.14.

The original local crash report and native stack were not retained, and the
failure no longer reproduces on demand with the updated native stack. The
upstream defect is therefore the best-supported explanation, not a proven
post-mortem attribution for every historical local exit.

WeasyPrint 70 removes the duplicate finalizer. The relevant primary sources
are [WeasyPrint issue #2843](https://github.com/Kozea/WeasyPrint/issues/2843),
the [upstream fix](https://github.com/Kozea/WeasyPrint/commit/9877813), and the
follow-up [Pango version analysis](https://github.com/Kozea/WeasyPrint/issues/2986).
The follow-up also demonstrates that WeasyPrint 70 can retain Fontconfig state
with Pango older than 1.54, which is why this project supports Pango 1.54+ for
repeated rendering.

No process-wide `FontConfiguration` cache, render lock, forced native cleanup,
retry, or abnormal-exit suppression is used. Those approaches can hide the
failure or introduce cross-document font contamination and unbounded native
state. The dependency floor selects the upstream lifetime fix instead.

## 0.3.1 verification stack

The release investigation recorded this exact macOS stack:

| Component | Recorded version |
|---|---:|
| macOS | 27.2 (arm64), Darwin 27.2.0 |
| Homebrew Python | 3.14.8 (`python@3.14` 3.14.8_2) |
| WeasyPrint | 70.0 |
| Pango / Pangocairo | 1.58.2 |
| Cairo | 1.18.6 |
| Fontconfig | 2.18.3 |
| HarfBuzz | 14.6.0 |
| GLib / GObject | 2.90.1 |
| libffi | 3.8.0 (pkg-config API 3.4-rc1) |
| cffi | 2.0.0 |
| pydyf | 0.12.1 |
| tinycss2 | 1.5.1 |
| cssselect2 | 0.9.0 |
| fontTools | 4.63.0 |
| Pillow | 12.2.0 |
| pypdf | 6.14.2 |
| Python-Markdown | 3.10.2 |
| PyMdown Extensions | 10.21.3 |
| PyYAML | 6.0.3 |

The renderer process actually loaded these principal native libraries:

| Component | Loaded path |
|---|---|
| Pango | `/opt/homebrew/Cellar/pango/1.58.2/lib/libpango-1.0.0.dylib` |
| Fontconfig | `/opt/homebrew/Cellar/fontconfig/2.18.3/lib/libfontconfig.1.dylib` |
| HarfBuzz | `/opt/homebrew/Cellar/harfbuzz/14.6.0/lib/libharfbuzz.0.dylib` |
| GLib | `/opt/homebrew/Cellar/glib/2.90.1/lib/libglib-2.0.0.dylib` |
| GObject | `/opt/homebrew/Cellar/glib/2.90.1/lib/libgobject-2.0.0.dylib` |
| libffi | `/usr/lib/libffi.dylib` |

Cairo and Pangocairo were recorded as installed native dependencies but were
not loaded by this WeasyPrint 70 render path. Recording both the package-manager
versions and the libraries actually loaded avoids treating an installed library
as proof that the process used it.

Validation on 1 November 2026 used normal, non-editable candidate installs; no
run used `--ignore-requires-python`. Each supported Python completed the final
518-test suite:

| Python | Interpreter source | Full suite |
|---|---|---:|
| 3.11.17 | temporary uv-managed CPython | 518 passed |
| 3.12.15 | temporary uv-managed CPython | 518 passed |
| 3.13.13 | temporary uv-managed CPython | 518 passed |
| 3.14.8 | Homebrew `python@3.14` | 518 passed |

The temporary uv-managed Python 3.11–3.13 builds required
`DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib` to discover Homebrew's native
libraries. Homebrew Python 3.14 discovered its sibling libraries without that
override. This is an interpreter-distribution setup detail, not an additional
Python package constraint.

The 3.11–3.14 latest-compatible environments resolved the declared dependency
ranges on the day of testing: WeasyPrint 70.0, cffi 2.1.1, cssselect2 0.10.1, pydyf 0.13.0,
fontTools 4.68.0, Pillow 13.0.0, pypdf 6.21.4, Python-Markdown 3.11.2,
PyMdown Extensions 12.3 and PyYAML 6.0.3. These exact versions record the
test conditions; they are not additional pins. Python 3.14 was checked both
with this current resolution and with the controlled versions in the table
above.

Fresh-process checks on Homebrew Python 3.14.8 produced:

- 100/100 clean exits for the upstream 50-render plus `gc.collect()` pattern
  with WeasyPrint 70.0;
- 50/50 clean focused processes, each completing eight real theme and image
  render tests (400 tests total);
- 10/10 clean full-suite processes at the then-current 517-test count (5,170
  tests total), followed by the final 518-test suite including the retained
  native-lifecycle regression;
- identical four-page tagged PDFs from the installed `md2pdf` and
  `python -m pdf` entry points;
- a passed visual-acceptance candidate with source digest
  `bae412b62c6c584ad07786fc0e2de122fd744f243e808be6b32cd6f761d83c65`:
  nine PDFs and 36 full-size pages, all inspected without a visual regression.

The inspected PDFs embed and subset the expected Minion, Myriad and Montserrat
families. These fonts are also installed on the licensed test workstation, so
this proves the effective PDF typography but does not independently prove that
each face was loaded from the package's bundled file rather than Fontconfig's
system inventory. Bundled-font isolation is a separate rendering concern, not
part of the Python 3.14 lifetime decision.

For comparison, the historical WeasyPrint 68.1 forced-collection pattern also
completed 100/100 times on the newer Python 3.14.8/Pango 1.58.2 stack. The old
failure therefore did not reproduce on demand after the native stack changed.
That result does not make 68.1 safe: the earlier local abnormal exits and the
upstream double-release implementation remain direct evidence of an
intermittent lifetime defect, and upstream 70 is the version containing its
fix.

Successful PDF creation alone is not sufficient: every stress child must exit
cleanly, because the historical failure occurred during garbage collection or
process teardown.

## Rechecking compatibility

Use a new temporary virtual environment for each Python and dependency
combination. Do not install with `--ignore-requires-python`; a normal install is
part of the compatibility gate. Keep the existing project and consumer virtual
environments unchanged.

For a candidate release:

1. record the Python build, WeasyPrint and Python dependency versions, plus
   `pkg-config --modversion` output for Pango, Cairo, Fontconfig, HarfBuzz, GLib,
   GObject and libffi and the paths actually loaded by a rendering process;
2. run the complete pytest suite in one process;
3. run fresh-process repetitions of the theme, font, table and image render
   tests and check return codes or terminating signals;
4. run the upstream forced-collection pattern (many renders followed by
   `gc.collect()`) in fresh processes; `tests/test_native_lifecycle.py` is the
   bounded in-suite regression for this lifecycle;
5. generate and verify the visual-acceptance matrix, then inspect every PDF and
   full-size page before promotion;
6. perform a normal non-editable install and exercise both `md2pdf` and
   `python -m pdf`.

Any timeout, signal, nonzero exit, incomplete PDF or visual regression blocks
support. Preserve a minimal reproducer and crash report if a failure occurs;
do not turn retries into a passing result.
