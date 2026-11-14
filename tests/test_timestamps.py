"""Observation dates describe source events; creation/update dates describe storage."""
from datetime import datetime, timezone

import pytest

from core.database import Database
from core.models import Intake, observation_time, utc_now


@pytest.mark.parametrize(('value', 'expected'), [
    ('2025-01-06T08:00:00Z', '2025-01-06T08:00:00+00:00'),
    ('2025-01-06T15:00:00+07:00', '2025-01-06T08:00:00+00:00'),
    ('2025-01-05T22:30:00-09:30', '2025-01-06T08:00:00+00:00'),
    ('2025-01-06T08:00:00.123456Z', '2025-01-06T08:00:00.123456+00:00'),
])
def test_observation_time_normalizes_utc(value, expected):
    assert observation_time(value) == expected


@pytest.mark.parametrize('value', [None, 123, False, '', 'not a date', '2025-01-06',
                                  '2025-01-06T08:00:00', '2025-02-30T08:00:00Z',
                                  '2099-01-01T00:00:00Z', '0001-01-01T00:00:00+01:00'])
def test_observation_time_rejects_invalid_future_or_unrepresentable_values(value):
    with pytest.raises(ValueError):
        observation_time(value)


def test_case_observation_and_storage_dates_are_separate_and_survive_review(tmp_path):
    db = Database(tmp_path / 'cases.sqlite3')
    before = utc_now()
    case_id = db.create_case(Intake('Website', 'https://history.example'),
                             observed_at='2025-01-06T15:00:00+07:00')
    case = db.get_case(case_id)
    assert case['observed_at'] == '2025-01-06T08:00:00+00:00'
    assert before <= case['created_at'] <= utc_now()
    assert case['created_at'] == case['updated_at']
    assert datetime.fromisoformat(case['observed_at']) < datetime.fromisoformat(case['created_at'])
    db.update_review(case_id, notes='Started review', status='Reviewing', verdict='Inconclusive')
    reviewed = Database(db.path).get_case(case_id)
    assert reviewed['observed_at'] == case['observed_at']
    assert reviewed['created_at'] == case['created_at']
    assert reviewed['updated_at'] > case['updated_at']


def test_default_observation_date_still_matches_creation(tmp_path):
    db = Database(tmp_path / 'cases.sqlite3')
    before = datetime.now(timezone.utc)
    case_id = db.create_case(Intake('Other', title='New reported observation'))
    case = db.get_case(case_id)
    assert case['observed_at'] == case['created_at'] == case['updated_at']
    assert before <= datetime.fromisoformat(case['observed_at']) <= datetime.now(timezone.utc)


@pytest.mark.parametrize('value', ['', '2025-01-06T08:00:00', '2099-01-01T00:00:00Z', 123])
def test_bad_case_timestamp_never_changes_database(value, tmp_path):
    db = Database(tmp_path / 'cases.sqlite3')
    db.create_case(Intake('Other', title='Existing investigator case'))
    before = db.list_cases()
    with pytest.raises(ValueError):
        db.create_case(Intake('Website', 'https://bad-time.example'), observed_at=value)
    assert db.list_cases() == before


def test_duplicate_key_never_replaces_observation_or_storage_times(tmp_path):
    db = Database(tmp_path / 'cases.sqlite3')
    intake = Intake('Other', title='Existing sample case')
    case_id = db.create_case(intake, demo_key='existing', observed_at='2024-01-01T00:00:00Z')
    before = db.get_case(case_id)
    assert db.create_case(intake, demo_key='existing', observed_at='2025-01-01T00:00:00Z') == case_id
    assert Database(db.path).get_case(case_id) == before
