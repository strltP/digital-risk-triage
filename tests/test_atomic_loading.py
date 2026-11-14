"""A failed import must not leave half-reviewed samples or alter existing evidence."""
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
import sqlite3

from PIL import Image
import pytest

from core.database import Database
from core.dataset_loader import load_sample_dataset, read_sample_cases
from core.evidence import save_evidence
from core.models import Intake, utc_now


@pytest.mark.parametrize('failure_stage', ['creation', 'review'])
def test_runtime_failure_rolls_back_whole_import_and_retry_is_safe(failure_stage, monkeypatch, tmp_path):
    db = Database(tmp_path / 'cases.sqlite3')
    first = read_sample_cases()[0]
    existing = db.create_case(first.intake, demo_key=first.key, observed_at='2024-01-01T00:00:00Z')
    db.update_review(existing, notes='Keep the investigator edit', status='Reviewing', verdict='Inconclusive')
    db.create_case(Intake('Other', title='Preserved manual case', notes='Manual notes'))
    image = BytesIO()
    Image.new('RGB', (2, 2), 'navy').save(image, format='PNG')
    evidence = save_evidence(db, tmp_path / 'evidence', existing, original_name='user-test.png',
                             content=image.getvalue(), source_url=first.intake.url, observed_at=utc_now())
    before = db.list_cases()
    with db.connection() as conn:
        schema_before = list(conn.execute('SELECT sql FROM sqlite_master WHERE sql IS NOT NULL ORDER BY name'))
        schema_before = [row[0] for row in schema_before]
    original_create, original_review = db.create_case, db.update_review
    calls = 0

    def failing_create(*args, **kwargs):
        nonlocal calls
        case_id = original_create(*args, **kwargs)
        calls += 1
        if calls == 3:
            raise sqlite3.OperationalError('Injected storage failure after creating a case')
        return case_id

    def failing_review(*args, **kwargs):
        original_review(*args, **kwargs)
        if kwargs['status'] == 'Escalated':
            raise sqlite3.OperationalError('Injected failure after an escalated review')

    with monkeypatch.context() as patch:
        patch.setattr(db, 'create_case' if failure_stage == 'creation' else 'update_review',
                      failing_create if failure_stage == 'creation' else failing_review)
        with pytest.raises(sqlite3.OperationalError, match='Injected'):
            load_sample_dataset(db)
    assert db.list_cases() == before
    restarted = Database(db.path)
    assert restarted.list_cases() == before
    assert restarted.list_evidence(existing) == [evidence]
    assert (tmp_path / 'evidence' / evidence['filename']).read_bytes() == image.getvalue()
    assert load_sample_dataset(db) == 99
    assert len(db.list_cases()) == 101
    for original in before:
        assert db.get_case(original['case_id']) == original
    assert load_sample_dataset(restarted) == 0
    with db.connection() as conn:
        assert [row[0] for row in conn.execute('SELECT sql FROM sqlite_master WHERE sql IS NOT NULL ORDER BY name')] == schema_before


def test_transaction_rolls_back_public_operations_and_resets_connection(tmp_path):
    db = Database(tmp_path / 'cases.sqlite3')
    with pytest.raises(RuntimeError, match='Nested'):
        with db.transaction():
            db.create_case(Intake('Other', title='Uncommitted case'))
            with db.transaction():
                pass
    assert db.list_cases() == []
    with db.transaction():
        case_id = db.create_case(Intake('Other', title='Committed case'))
        db.update_review(case_id, notes='Draft review', status='Reviewing', verdict='Inconclusive')
        assert db.get_case(case_id)['status'] == 'Reviewing'
    assert Database(db.path).get_case(case_id)['status'] == 'Reviewing'


def test_two_importers_do_not_race_on_existing_keys(tmp_path):
    path = tmp_path / 'cases.sqlite3'
    Database(path)

    def import_cases(_):
        return load_sample_dataset(Database(path))

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(import_cases, range(2))) == [0, 100]
    cases = Database(path).list_cases()
    assert len(cases) == len({case['demo_key'] for case in cases}) == 100
    fixtures = {case.key: case for case in read_sample_cases()}
    for case in cases:
        fixture = fixtures[case['demo_key']]
        assert (case['notes'], case['status'], case['verdict']) == (fixture.intake.notes, fixture.status, fixture.verdict)
