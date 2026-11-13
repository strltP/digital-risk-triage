"""Dataset coverage, legacy compatibility and provenance round trips."""
from collections import Counter, defaultdict
import csv
from io import BytesIO, StringIO
from urllib.parse import urlsplit

from openpyxl import load_workbook
from PIL import Image
import pytest

from core.database import Database
from core.demo import LEGACY_SCENARIOS, SCENARIOS, load_demo
from core.evidence import save_evidence
from core.models import Intake, SOURCES, STATUSES, VERDICTS, utc_now
from core.reporting import export_csv, export_excel
from core.risk_rules import assess
from core.sample_scenarios import BRANDS


@pytest.fixture
def db(tmp_path):
    return Database(tmp_path / 'cases.sqlite3')


def test_fresh_sample_distribution_safety_and_rule_engine(db):
    assert load_demo(db) == 100
    cases = db.list_cases()
    assert len(cases) == 100
    assert len({case['demo_key'] for case in cases}) == 100
    assert Counter(case['category'] for case in cases) == {
        'Potential phishing': 25, 'Potential brand impersonation': 25,
        'Potential counterfeit listing': 20, 'Potential trademark misuse': 15,
        'Other suspicious content': 15,
    }
    assert Counter(case['priority'] for case in cases) == {'High': 16, 'Medium': 69, 'Low': 15}
    assert set(case['source_type'] for case in cases) == set(SOURCES)
    assert set(case['status'] for case in cases) == set(STATUSES)
    assert set(case['verdict'] for case in cases) == set(VERDICTS)
    for field in ('title', 'description', 'source_url'):
        assert len({case[field] for case in cases}) == 100
    assert {case['brand'] for case in cases} == set(BRANDS)
    for case in cases:
        assert case['is_demo'] == 1
        assert urlsplit(case['source_url']).hostname.endswith('.example')
        assert case['official_domain'] == BRANDS[case['brand']]
        assert case['official_domain'].endswith('.example')
        assert 'fictional' in case['notes'].lower()
        assert not db.list_evidence(case['case_id'])
        expected = assess(Intake(case['source_type'], case['source_url'], case['brand'],
                                case['official_domain'], case['title'], case['description'], case['notes']))
        assert (case['category'], case['priority'], case['indicators'], case['explanation']) == (
            expected.category, expected.priority, expected.indicators, expected.explanation)


def test_reviews_follow_public_validation_transitions(db, monkeypatch):
    transitions = defaultdict(list)
    update = db.update_review

    def tracked(case_id, **review):
        update(case_id, **review)  # A real invalid transition must fail this test.
        transitions[case_id].append(review['status'])

    monkeypatch.setattr(db, 'update_review', tracked)
    assert load_demo(db) == 100
    fixtures = {scenario.key: scenario for scenario in SCENARIOS}
    for case in db.list_cases():
        scenario = fixtures[case['demo_key']]
        assert case['status'] == scenario.status
        assert case['verdict'] == scenario.verdict
        if case['status'] == 'Escalated':
            assert transitions[case['case_id']] == ['Validated', 'Escalated']
        if case['status'] in ('Validated', 'Escalated'):
            assert case['verdict'] == 'Confirmed violation' and case['validated_at']
            assert 'Fictional sample review:' in case['notes']
        else:
            assert case['validated_at'] is None
        if case['status'] == 'False Positive':
            assert case['verdict'] == 'No violation found'
            assert 'Fictional sample review:' in case['notes']


def test_upgrade_original_12_preserves_entire_records_and_evidence(db, tmp_path):
    # Reproduce the original loader's keys, title prefix and review states.
    for index, (source, url, brand, official, title, content, disposition) in enumerate(LEGACY_SCENARIOS, 1):
        case_id = db.create_case(Intake(source, url, brand, official, '[SIMULATED] ' + title, content,
                                       'SIMULATED DEMO — fictional scenario; no real evidence or allegation.'),
                                 demo_key=f'demo-v1-{index:02d}')
        if disposition:
            db.update_review(case_id, notes='SIMULATED REVIEW: ' + disposition,
                             status='False Positive', verdict='No violation found')
        elif index == 4:
            db.update_review(case_id, notes='SIMULATED DEMO — checking claimed authorization; no verdict yet.',
                             status='Reviewing', verdict='Inconclusive')
    legacy = next(case for case in db.list_cases() if case['demo_key'] == 'demo-v1-01')
    db.update_review(legacy['case_id'], notes='User review: retain my completed decision.',
                     status='Validated', verdict='Confirmed violation')
    db.update_review(legacy['case_id'], notes='User escalation rationale: retain this note.',
                     status='Escalated', verdict='Confirmed violation')
    # Simulate a user-modified intake field; the loader must not rewrite it.
    with db.connection() as conn:
        conn.execute('UPDATE cases SET title=? WHERE case_id=?',
                     ('[SIMULATED] User-edited account observation', legacy['case_id']))
    image = BytesIO()
    Image.new('RGB', (3, 3), 'navy').save(image, format='PNG')
    evidence = save_evidence(db, tmp_path / 'evidence', legacy['case_id'],
                             original_name='user-test-upload.png', content=image.getvalue(),
                             source_url=legacy['source_url'], observed_at=utc_now(),
                             description='User-supplied test image; preserve bytes and metadata.')
    manual = db.create_case(Intake('Other', title='Manual investigation retained during sample upgrade', notes='User notes'))
    before = {case['case_id']: case for case in db.list_cases()}
    evidence_before = db.list_evidence(legacy['case_id'])
    assert load_demo(db) == 88
    assert len(db.list_cases()) == 101
    assert sum(case['is_demo'] for case in db.list_cases()) == 100
    restarted = Database(db.path)
    assert load_demo(restarted) == 0
    for case_id, snapshot in before.items():
        assert restarted.get_case(case_id) == snapshot
    assert restarted.get_case(manual)['is_demo'] == 0
    assert restarted.list_evidence(legacy['case_id']) == evidence_before
    assert (tmp_path / 'evidence' / evidence['filename']).read_bytes() == image.getvalue()
    rows = {row['case_id']: row for row in csv.DictReader(StringIO(export_csv(restarted).decode('utf-8-sig')))}
    assert evidence['filename'] in rows[legacy['case_id']]['evidence_references']
    assert rows[legacy['case_id']]['analyst_notes'] == before[legacy['case_id']]['notes']


def test_repeated_load_preserves_all_100_records(db):
    assert load_demo(db) == 100
    before = db.list_cases()
    assert load_demo(db) == 0
    assert Database(db.path).list_cases() == before


def test_sample_provenance_in_csv_and_excel(db):
    load_demo(db)
    manual = db.create_case(Intake('Other', title='Ordinary investigator intake'))
    csv_rows = list(csv.DictReader(StringIO(export_csv(db).decode('utf-8-sig'))))
    book = load_workbook(BytesIO(export_excel(db)))
    sheet_rows = list(book['Cases'].values)
    excel_rows = [dict(zip(sheet_rows[0], values)) for values in sheet_rows[1:]]
    for rows in (csv_rows, excel_rows):
        assert len(rows) == 101
        samples = [row for row in rows if row['case_id'] != manual]
        assert len(samples) == 100
        assert all(row['data_label'] == 'SIMULATED DEMO' for row in samples)
        assert all('fictional' in row['analyst_notes'].lower() for row in samples)
        assert next(row for row in rows if row['case_id'] == manual)['data_label'] == 'Investigator intake'
        assert all(row['evidence_references'] in ('', None) for row in samples)
    assert book['Evidence'].max_row == 1  # No fabricated evidence is seeded.
