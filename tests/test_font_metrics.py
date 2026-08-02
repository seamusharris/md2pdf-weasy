"""Determinism and package-data contract for table font measurement."""

import posixpath
import re
import tomllib
from importlib.metadata import files
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import unquote

import pdf
import pdf.table_transforms as transforms
from fontTools.ttLib import TTFont, TTLibError


def _clear_metric_cache():
    transforms._glyph_advances.cache_clear()


def test_fonttools_is_a_direct_runtime_dependency():
    project = tomllib.loads(
        (Path(__file__).parents[1] / "pyproject.toml").read_text(
            encoding="utf-8"
        )
    )
    dependencies = project["project"]["dependencies"]
    assert any(re.match(r"fonttools(?:\W|$)", value, re.IGNORECASE)
               for value in dependencies)


def test_real_bundled_body_and_header_glyph_metrics_are_used():
    _clear_metric_cache()
    body = transforms._glyph_advances(transforms._BODY_FONT_PATH)
    header = transforms._glyph_advances(transforms._HEADER_FONT_PATH)

    assert body and header
    assert transforms._measure_em("WWW") == sum(body[char] for char in "WWW")
    expected_header = (
        sum(header[char] for char in "TEAM") + 0.03 * len("Team")
    ) * transforms._HEADER_EM_SCALE
    assert transforms._measure_em("Team", header=True) == expected_header
    assert transforms._measure_em("WWW") != transforms._text_em("WWW")
    assert transforms._measure_em("Team", header=True) != \
        transforms._header_em("Team")


def test_measurement_fallback_is_deterministic_for_body_and_header(monkeypatch):
    monkeypatch.setattr(transforms, "_glyph_advances", lambda _path: None)

    assert transforms._measure_em("Warrandyte") == \
        transforms._text_em("Warrandyte")
    assert transforms._measure_em("Team", header=True) == \
        transforms._header_em("Team")


def test_missing_font_warns_once_after_the_failed_result_is_cached(
    tmp_path, caplog
):
    missing = str(tmp_path / "missing.otf")
    _clear_metric_cache()

    assert transforms._glyph_advances(missing) is None
    assert transforms._glyph_advances(missing) is None

    assert caplog.messages == [
        "font metrics: bundled font missing.otf is unavailable; "
        "using estimated widths"
    ]


def test_corrupt_font_warns_and_falls_back(tmp_path, caplog):
    corrupt = tmp_path / "corrupt.otf"
    corrupt.write_bytes(b"not an OpenType font")
    _clear_metric_cache()

    assert transforms._glyph_advances(str(corrupt)) is None
    assert caplog.messages == [
        "font metrics: bundled font corrupt.otf is unreadable; "
        "using estimated widths"
    ]


class _FakeHmtx:
    def __getitem__(self, _glyph):
        return 500, 0


class _FakeFont:
    def __init__(self, fail=False, cmap=None, units_per_em=1000,
                 missing_table=None):
        self.fail = fail
        self.cmap = {65: "A"} if cmap is None else cmap
        self.units_per_em = units_per_em
        self.missing_table = missing_table
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        self.closed = True

    def __getitem__(self, table):
        if table == self.missing_table:
            raise KeyError(table)
        if table == "head":
            return SimpleNamespace(unitsPerEm=self.units_per_em)
        if table == "hmtx":
            return _FakeHmtx()
        raise KeyError(table)

    def getBestCmap(self):
        if self.fail:
            raise TTLibError("bad cmap")
        return self.cmap


def test_font_resource_is_closed_after_successful_metric_extraction(
    tmp_path, monkeypatch
):
    font_path = tmp_path / "tracked.otf"
    font_path.touch()
    fake = _FakeFont()
    monkeypatch.setattr(transforms, "TTFont", lambda _path: fake)
    _clear_metric_cache()

    assert transforms._glyph_advances(str(font_path)) == {"A": 0.5}
    assert fake.closed


def test_font_resource_is_closed_when_table_extraction_fails(
    tmp_path, monkeypatch, caplog
):
    font_path = tmp_path / "broken-table.otf"
    font_path.touch()
    fake = _FakeFont(fail=True)
    monkeypatch.setattr(transforms, "TTFont", lambda _path: fake)
    _clear_metric_cache()

    assert transforms._glyph_advances(str(font_path)) is None
    assert fake.closed
    assert caplog.messages == [
        "font metrics: bundled font broken-table.otf is unreadable; "
        "using estimated widths"
    ]


def test_missing_required_font_table_warns_closes_and_falls_back(
    tmp_path, monkeypatch, caplog
):
    font_path = tmp_path / "missing-table.otf"
    font_path.touch()
    fake = _FakeFont(missing_table="hmtx")
    monkeypatch.setattr(transforms, "TTFont", lambda _path: fake)
    _clear_metric_cache()

    assert transforms._glyph_advances(str(font_path)) is None
    assert fake.closed
    assert caplog.messages == [
        "font metrics: bundled font missing-table.otf is unreadable; "
        "using estimated widths"
    ]


def test_font_open_oserror_warns_and_falls_back(tmp_path, monkeypatch, caplog):
    font_path = tmp_path / "io-error.otf"
    font_path.touch()

    def fail_open(_path):
        raise OSError("unreadable")

    monkeypatch.setattr(transforms, "TTFont", fail_open)
    _clear_metric_cache()

    assert transforms._glyph_advances(str(font_path)) is None
    assert caplog.messages == [
        "font metrics: bundled font io-error.otf is unreadable; "
        "using estimated widths"
    ]


def test_font_without_unicode_cmap_warns_closes_and_falls_back(
    tmp_path, monkeypatch, caplog
):
    font_path = tmp_path / "no-cmap.otf"
    font_path.touch()
    fake = _FakeFont(cmap={})
    monkeypatch.setattr(transforms, "TTFont", lambda _path: fake)
    _clear_metric_cache()

    assert transforms._glyph_advances(str(font_path)) is None
    assert fake.closed
    assert caplog.messages == [
        "font metrics: bundled font no-cmap.otf is unreadable; "
        "using estimated widths"
    ]


def test_font_with_zero_units_per_em_warns_closes_and_falls_back(
    tmp_path, monkeypatch, caplog
):
    font_path = tmp_path / "zero-upm.otf"
    font_path.touch()
    fake = _FakeFont(units_per_em=0)
    monkeypatch.setattr(transforms, "TTFont", lambda _path: fake)
    _clear_metric_cache()

    assert transforms._glyph_advances(str(font_path)) is None
    assert fake.closed
    assert caplog.messages == [
        "font metrics: bundled font zero-upm.otf is unreadable; "
        "using estimated widths"
    ]


def test_installed_distribution_contains_all_shipped_styles_and_fonts():
    package_root = Path(pdf.__file__).parent
    distribution_files = {
        str(path).replace("\\", "/") for path in files("md2pdf-weasy") or []
    }
    shipped = [
        *package_root.joinpath("styles").glob("*.css"),
        *package_root.joinpath("fonts").glob("*.otf"),
        *package_root.joinpath("fonts").glob("*.ttf"),
    ]

    for path in shipped:
        relative = f"pdf/{path.relative_to(package_root).as_posix()}"
        assert relative in distribution_files


def test_every_shipped_stylesheet_font_url_resolves_to_packaged_data():
    package_root = Path(pdf.__file__).parent
    distribution_files = {
        str(path).replace("\\", "/") for path in files("md2pdf-weasy") or []
    }

    for stylesheet in package_root.joinpath("styles").glob("*.css"):
        css = stylesheet.read_text(encoding="utf-8")
        for raw_url in re.findall(r"url\([\"']?([^\"')]+)", css):
            if not raw_url.startswith("../fonts/"):
                continue
            relative = unquote(posixpath.normpath(
                f"pdf/styles/{raw_url}"
            ))
            assert relative in distribution_files, (
                f"{stylesheet.name} references unpackaged {relative}"
            )


def test_metric_source_fonts_are_packaged_and_readable():
    distribution_files = {
        str(path).replace("\\", "/") for path in files("md2pdf-weasy") or []
    }
    for font_path in (
        transforms._BODY_FONT_PATH,
        transforms._HEADER_FONT_PATH,
    ):
        assert f"pdf/fonts/{Path(font_path).name}" in distribution_files
        with TTFont(font_path) as font:
            assert font["head"].unitsPerEm > 0
            assert font.getBestCmap()
