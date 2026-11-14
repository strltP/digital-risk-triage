"""Presentation filtering and ordering never change stored metadata."""
from copy import deepcopy

import pytest

from core.presentation import filter_data_source, format_timestamp, plain_markdown, queue_view, short_case_id


def case(identifier, priority='Low', status='New', observed='2025-01-06T08:00:00Z', **extra):
    return {'case_id': identifier, 'priority': priority, 'status': status, 'observed_at': observed,
            'title': 'Account observation', 'brand': 'Astervale', 'source_url': 'https://source.example/path',
            'is_demo': 0, **extra}


def test_triage_order_is_deterministic_and_preserves_records():
    rows = [case('F', 'Low'), case('E', 'Medium'),
            case('D', 'High', 'Validated', '2025-02-06T08:00:00Z'),
            case('C', 'High', 'Reviewing', '2025-01-07T08:00:00Z'),
            case('B', 'High'), case('A', 'High')]
    before = deepcopy(rows)
    assert [row['case_id'] for row in queue_view(rows)] == ['C', 'A', 'B', 'D', 'E', 'F']
    assert queue_view(rows) == queue_view(list(reversed(rows)))
    assert [row['case_id'] for row in queue_view(rows, sort='Priority low to high')] == ['F', 'E', 'C', 'A', 'B', 'D']
    assert rows == before


def test_observation_order_uses_actual_instants_with_stable_id_ties():
    rows = [case('B', observed='2025-01-06T15:00:00+07:00'), case('A'),
            case('C', observed='2025-01-07T08:00:00Z')]
    assert [row['case_id'] for row in queue_view(rows, sort='Newest observed')] == ['C', 'A', 'B']
    assert [row['case_id'] for row in queue_view(rows, sort='Oldest observed')] == ['A', 'B', 'C']


@pytest.mark.parametrize('query', ['ACCOUNT', 'drt-abcdef123456', 'ASTERvale', 'SOURCE.EXAMPLE/path'])
def test_search_matches_title_full_id_brand_and_url_case_insensitively(query):
    match = case('DRT-abcdef123456')
    other = case('DRT-other', title='Unrelated item', brand='Northpetal', source_url='https://different.example')
    assert queue_view([other, match], query) == [match]
    assert queue_view([other, match], 'no match here') == []


def test_data_source_scope_and_empty_results():
    manual, sample = case('manual'), case('sample', is_demo=1)
    rows = [manual, sample]
    assert filter_data_source(rows, 'Investigator intake') == [manual]
    assert filter_data_source(rows, 'Sample Data') == [sample]
    assert filter_data_source(rows, 'All cases') == rows
    assert queue_view(filter_data_source(rows, 'Sample Data'), 'manual') == []
    with pytest.raises(ValueError):
        filter_data_source(rows, 'Unknown')
    with pytest.raises(ValueError):
        queue_view(rows, sort='Unknown')


@pytest.mark.parametrize(('value', 'expected'), [
    ('2025-01-06T08:00:00.123456+00:00', '06 Jan 2025, 08:00 UTC'),
    ('2025-01-06T15:00:00+07:00', '06 Jan 2025, 08:00 UTC'),
    ('2025-01-06T08:00:00Z', '06 Jan 2025, 08:00 UTC'),
    (None, 'Not recorded'), ('bad timestamp', 'Unrecognized time'),
    ('2025-01-06T08:00:00', 'Unrecognized time'),
])
def test_timestamp_display_is_utc_and_never_assumes_a_timezone(value, expected):
    assert format_timestamp(value) == expected


def test_short_ids_and_literal_markdown_leave_original_values_intact():
    identifier = 'DRT-12345678abcdefgh12345678abcdefgh'
    assert short_case_id(identifier) == 'DRT-12345678'
    assert identifier.endswith('abcdefgh')
    assert plain_markdown('![submitted title](https://image.example)') == r'\!\[submitted title\]\(https://image\.example\)'
