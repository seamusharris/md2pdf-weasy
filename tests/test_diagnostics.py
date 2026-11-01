"""Instrumentation observes actual passes without retaining table content."""

from copy import deepcopy
import inspect
import json

import pytest

from pdf.diagnostics import (
    BuildResult, DiagnosticsCollector, DiagnosticsReport, StrictDiagnosticsError, StrictPolicy,
    evaluate_strict,
)
from pdf.postprocess import _postprocess, postprocess
from pdf.table_presets import expand_table_presets


def table(headers=('Team', 'W'), cells=('North', '12'), *, attrs='', caption=''):
    return (f'<table{attrs}>{caption}<thead><tr>'
            + ''.join(f'<th>{value}</th>' for value in headers)
            + '</tr></thead><tbody><tr>'
            + ''.join(f'<td>{value}</td>' for value in cells)
            + '</tr></tbody></table>')


def observe(source=None, metadata=None, **kwargs):
    collector = DiagnosticsCollector(**kwargs)
    source = table() if source is None else source
    result = _postprocess(source, metadata, _collector=collector)
    assert result == postprocess(source, metadata)
    return result, collector.build_report()


def layout(**kwargs):
    return {'columns': [{'name': 'Team', 'width': 3}, {'name': 'W', 'width': 1, 'align': 'right'}], **kwargs}


def codes(report):
    return [item['code'] for item in report['diagnostics']]


def test_exact_public_signatures_and_report_shape():
    assert str(inspect.signature(postprocess)) == '(html, metadata=None)'
    _, report = observe()
    assert isinstance(report, DiagnosticsReport)
    assert report['schema_version'] == 1
    assert set(report) == {'schema_version', 'tables', 'resources', 'diagnostics'}
    assert report.to_dict() == report
    json.dumps(report.to_dict(), allow_nan=False)


@pytest.mark.parametrize('metadata', [None, {'table_widths': False},
    {'auto_align_columns': False}, {'columns': {'Team': '8em'}},
    {'tables': {'ladder': layout()}},
    {'tables': {'bad': {'columns': 'not columns'}}},
    {'tables': {'bad': {'preset': 'unknown-v1', 'required': True}}},
    {'tables': None}, {'tables': []},
])
def test_instrumentation_never_changes_html_or_input_metadata(metadata):
    before = deepcopy(metadata)
    observe(metadata=metadata)
    assert metadata == before


def test_declared_widths_alignment_sources_and_matching_order():
    _, report = observe(table(attrs=' id="standings"'),
                        {'tables': {'first': layout(), 'second': layout()}},
                        layout_sources={'first': 'tables_include', 'second': 'document'})
    record = report['tables'][0]
    assert (record['index'], record['id'], record['origin']) == (1, 'standings', 'declared')
    assert record['matching_layout_keys'] == ['first', 'second']
    assert record['layout_key'] == 'first'
    assert record['layout_source'] == 'tables_include'
    assert record['widths'] == [
        {'column_index': 1, 'value': 75.0, 'unit': '%', 'source': 'declared'},
        {'column_index': 2, 'value': 25.0, 'unit': '%', 'source': 'declared'},
    ]
    assert record['alignment'][1] == {'column_index': 2, 'value': 'right', 'source': 'declared'}
    assert codes(report) == ['tables.match_ambiguous', 'tables.layout_unused']


def test_automatic_widths_use_em_and_actual_token_class_and_fit():
    _, report = observe()
    record = report['tables'][0]
    assert record['origin'] == 'automatic'
    assert all(width['unit'] == 'em' for width in record['widths'])
    assert record['widths'][1]['token_class'].startswith('w')
    assert record['widths'][1]['rung'] >= 1
    assert record['fit']['outcome'] == 'fit'
    assert record['fit']['budget_em'] > record['fit']['emitted_total_em']
    assert record['alignment'][1]['source'] == 'automatic'


def test_author_colgroup_and_inline_alignment_are_not_claimed_as_automatic():
    source = table().replace('<table>', '<table><colgroup><col style="width:75%"><col style="width:4em"></colgroup>')
    source = source.replace('<td>12', '<td style="text-align:center">12')
    _, report = observe(source)
    record = report['tables'][0]
    assert record['origin'] == 'author_colgroup'
    assert record['skip_reason'] == 'existing-colgroup'
    assert [width['unit'] for width in record['widths']] == ['%', 'em']
    assert record['alignment'][1]['source'] == 'author'
    assert 'tables.structure_unsupported' not in codes(report)


@pytest.mark.parametrize(('source', 'reason'), [
    ('<table><tr><td>value</td></tr></table>', 'no-headers'),
    ('<table><tr><th>Team</th></tr></table>', 'no-body-rows'),
    (table().replace('<td>North', '<td colspan="2">North'), 'spanning-cells'),
    (table().replace('<td>12</td>', ''), 'ragged-rows'),
])
def test_structural_skip_reasons_are_explicit(source, reason):
    _, report = observe(source)
    assert report['tables'][0]['origin'] == 'unchanged'
    assert report['tables'][0]['skip_reason'] == reason
    assert codes(report) == ['tables.structure_unsupported']


def test_required_counts_only_a_selected_actually_applied_layout():
    metadata = {'tables': {'first': layout(), 'shadowed': layout(required=True)}}
    _, report = observe(metadata=metadata)
    assert 'tables.required_unapplied' in codes(report)
    source = table().replace('<td>North', '<td rowspan="2">North')
    _, report = observe(source, {'tables': {'required': layout(required=True)}})
    assert 'tables.required_unapplied' in codes(report)
    _, report = observe(metadata={'tables': {'required': layout(required=True)}})
    assert 'tables.required_unapplied' not in codes(report)


def test_required_presets_and_invalid_required_types():
    metadata = {'tables': {'preset': {'preset': 'netball-ladder-v1', 'required': True}}}
    expanded, warnings = expand_table_presets(metadata)
    assert not warnings
    columns = expanded['tables']['preset']['columns']
    _, report = observe(table([c['name'] for c in columns], ['North', '12', '8', '4', '0', '244', '187', '130.5']), metadata)
    assert report['tables'][0]['origin'] == 'preset'
    assert report['tables'][0]['preset_id'] == 'netball-ladder-v1'
    assert 'tables.required_unapplied' not in codes(report)
    _, report = observe(metadata={'tables': {'bad': {'preset': 'netball-ladder-v1', 'required': 'yes'}}})
    assert 'tables.layout_invalid' in codes(report)
    _, report = observe(metadata={'tables': {'bad': layout(required='yes')}})
    assert 'tables.layout_invalid' in codes(report)


def test_content_privacy_including_headers_captions_and_invalid_raw_values():
    sentinel = 'PRIVATE_SENTINEL_849213'
    source = table((sentinel, 'W'), (sentinel, '12'), caption=f'<caption>{sentinel}</caption>')
    _, report = observe(source, {'tables': {'invalid': {'preset': sentinel}},
                                 'columns': {sentinel: '8em'}})
    assert sentinel not in json.dumps(report)
    assert set(report['tables'][0]).isdisjoint({'headers', 'body', 'caption', 'html'})


def test_finite_json_for_extreme_fixed_overflow_and_selected_strict_codes():
    _, report = observe(metadata={'columns': {'Team': 1e308, 'W': 1e308}})
    json.dumps(report, allow_nan=False)
    assert report['tables'][0]['fit']['outcome'] == 'unresolved_overflow'
    assert report['tables'][0]['fit']['natural_total_em'] is None
    with pytest.raises(StrictDiagnosticsError) as exc:
        evaluate_strict(report, True)
    assert exc.value.report == report
    evaluate_strict(report, StrictPolicy({'tables.match_ambiguous'}))
    with pytest.raises(ValueError, match='unknown'):
        StrictPolicy({'typo'})


def test_unused_layouts_are_info_only_and_reports_are_repeatable_detached_values():
    collector = DiagnosticsCollector()
    source = table()
    _postprocess(source, {'tables': {'unused': {'columns': [{'name': 'Other'}]}}}, _collector=collector)
    first = collector.build_report()
    second = collector.build_report()
    assert first == second
    assert first['diagnostics'] == [{'code': 'tables.layout_unused', 'severity': 'info', 'layout_key': 'unused'}]
    evaluate_strict(first, True)
    first['tables'].clear()
    assert collector.build_report() == second


def test_disabled_widths_keep_alignment_and_stable_one_based_positions():
    _, report = observe(table() + table(attrs=' id="second"'), {'table_widths': False})
    assert [(r['index'], r['id']) for r in report['tables']] == [(1, None), (2, 'second')]
    assert all(r['skip_reason'] == 'widths-disabled' for r in report['tables'])
    assert all(r['alignment'][1]['source'] == 'automatic' for r in report['tables'])


def test_resource_events_keep_order_resolution_facts_and_exclude_payloads():
    from dataclasses import dataclass

    @dataclass
    class Event:
        kind: str
        status: str
        resolved_path: str

    collector = DiagnosticsCollector()
    collector.add_resource(Event('image', 'resolved', '/allowed/image.png'))
    collector.add_resource({'kind': 'tables_include', 'status': 'missing',
                            'reference': 'tables.yml', 'content': 'PRIVATE_PAYLOAD'})
    report = collector.build_report()
    assert [event['kind'] for event in report['resources']] == ['image', 'tables_include']
    assert 'PRIVATE_PAYLOAD' not in json.dumps(report)
    assert report['resources'][0]['resolved_path'] == '/allowed/image.png'


def test_build_result_is_frozen_and_contains_only_location_and_report():
    from dataclasses import FrozenInstanceError, fields
    result = BuildResult('/output/document.pdf', DiagnosticsCollector().build_report())
    assert [field.name for field in fields(result)] == ['output_path', 'diagnostics']
    with pytest.raises(FrozenInstanceError):
        result.output_path = '/other.pdf'


def test_scaled_widths_report_the_actual_emitted_total_and_selected_policy():
    _, report = observe(table(cells=('North metropolitan representative team', '12')),
                        {'page_width_em': 8})
    fit = report['tables'][0]['fit']
    assert fit['outcome'] == 'scaled'
    assert fit['natural_total_em'] > fit['budget_em']
    assert fit['emitted_total_em'] <= fit['budget_em']
    assert 'tables.width_scaled' in codes(report)
    evaluate_strict(report, True)
    with pytest.raises(StrictDiagnosticsError):
        evaluate_strict(report, StrictPolicy({'tables.width_scaled'}))


def test_data_id_is_not_mistaken_for_the_authored_table_id():
    _, report = observe(table(attrs=' data-id="not-an-id"'))
    assert report['tables'][0]['id'] is None
