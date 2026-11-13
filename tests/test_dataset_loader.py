"""JSON schema errors must be reported before any case is inserted or changed."""
from copy import deepcopy
import hashlib
import json

import pytest

from core.database import Database
from core.dataset_loader import DEFAULT_DATASET, DatasetError, load_sample_dataset, read_sample_cases
from core.models import Intake


@pytest.fixture
def document():
    return json.loads(DEFAULT_DATASET.read_text(encoding='utf-8'))


@pytest.fixture
def db(tmp_path):
    db = Database(tmp_path / 'cases.sqlite3')
    case_id = db.create_case(Intake('Other', title='Existing manual investigation', notes='Keep initial notes'))
    db.update_review(case_id, notes='Retain this manual verdict and timestamp.',
                     status='Validated', verdict='Confirmed violation')
    return db


def write_dataset(tmp_path, document):
    path = tmp_path / 'sample.json'
    path.write_text(json.dumps(document, ensure_ascii=False), encoding='utf-8')
    return path


def test_json_preserves_all_original_scenario_content(document):
    records = document['cases']
    assert len(records) == len({record['case_key'] for record in records}) == 100
    assert not any({'category', 'priority'} & record.keys() for record in records)
    # Captured from the Python fixtures before extraction. Protect every key,
    # input string, review note, intended verdict and record order, not just counts.
    digest = hashlib.sha256(json.dumps(records, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    assert digest == 'f9d228d3d754a5dc937c726461dc7ddd33122c1f7f16e4c7f8bca1f95a4788cc'
    assert len(read_sample_cases()) == 100


def test_default_dataset_path_is_independent_of_working_directory(monkeypatch, tmp_path, db):
    monkeypatch.chdir(tmp_path)
    assert len(read_sample_cases()) == 100
    assert load_sample_dataset(db) == 100
    assert len(db.list_cases()) == 101


@pytest.mark.parametrize('field', [
    'case_key', 'source_type', 'url', 'brand', 'official_domain', 'title', 'description',
    'review_status', 'review_verdict', 'review_notes',
])
def test_missing_case_fields_do_not_import_part_of_dataset(field, document, db, tmp_path):
    del document['cases'][-1][field]
    before = db.list_cases()
    with pytest.raises(DatasetError, match=f'Sample case 100: Missing fields: {field}'):
        load_sample_dataset(db, write_dataset(tmp_path, document))
    assert db.list_cases() == before


@pytest.mark.parametrize(('field', 'value', 'message'), [
    ('case_key', '', 'case_key must be nonempty'),
    ('title', None, 'fields must be strings'),
    ('source_type', 'Unsupported source', 'supported source type'),
    ('url', 'https://live.example.com/', 'reserved .example domains'),
    ('url', 'https://bad host.example', 'whitespace'),
    ('url', 'javascript:alert(1)', 'HTTP and HTTPS'),
    ('brand', 'Unrecognized brand', 'supported fictional brand'),
    ('official_domain', 'lumifern.example', 'matching official'),
    ('review_status', 'Closed', 'Unsupported review_status'),
    ('review_verdict', 'Automatic finding', 'Unsupported review_status or review_verdict'),
    ('review_status', 'Validated', 'requires verdict'),
    ('review_status', 'Escalated', 'requires verdict'),
    ('review_status', 'False Positive', 'requires verdict'),
    ('category', 'Potential phishing', 'unsupported fields: category'),
    ('priority', 'High', 'unsupported fields: priority'),
])
def test_invalid_late_record_preserves_existing_records(field, value, message, document, db, tmp_path):
    document['cases'][-1][field] = value
    before = db.list_cases()
    with pytest.raises(DatasetError, match=message):
        load_sample_dataset(db, write_dataset(tmp_path, document))
    assert db.list_cases() == before


@pytest.mark.parametrize('status', ['Reviewing', 'Validated', 'Escalated', 'False Positive'])
def test_reviewed_cases_require_notes(status, document, db, tmp_path):
    record = next(record for record in document['cases'] if record['review_status'] == status)
    record['review_notes'] = '   '
    before = db.list_cases()
    with pytest.raises(DatasetError, match='supporting review_notes'):
        load_sample_dataset(db, write_dataset(tmp_path, document))
    assert db.list_cases() == before


def test_duplicate_case_keys_rejected_before_import(document, db, tmp_path):
    document['cases'].append(deepcopy(document['cases'][0]))
    before = db.list_cases()
    with pytest.raises(DatasetError, match="Duplicate case_key 'demo-v1-01'"):
        load_sample_dataset(db, write_dataset(tmp_path, document))
    assert db.list_cases() == before


@pytest.mark.parametrize(('document', 'message'), [
    ([], 'must be an object'),
    ({'cases': []}, 'dataset_version, description and cases'),
    ({'dataset_version': '2.0', 'description': 'Fictional sample', 'cases': []}, 'Unsupported sample dataset_version'),
    ({'dataset_version': '1.0', 'description': '', 'cases': []}, 'description must be a nonempty string'),
    ({'dataset_version': '1.0', 'description': 'Fictional sample', 'cases': {}}, 'cases must be a nonempty list'),
    ({'dataset_version': '1.0', 'description': 'Fictional sample', 'cases': []}, 'cases must be a nonempty list'),
    ({'dataset_version': '1.0', 'description': 'Fictional sample', 'cases': [None]}, 'Each case must be an object'),
])
def test_invalid_top_level_or_record_shape(document, message, db, tmp_path):
    before = db.list_cases()
    with pytest.raises(DatasetError, match=message):
        load_sample_dataset(db, write_dataset(tmp_path, document))
    assert db.list_cases() == before


@pytest.mark.parametrize(('content', 'message'), [
    (None, 'Sample dataset not found'),
    (b'{"cases": [', 'Invalid JSON.*line 1, column'),
    (b'\xff', 'as UTF-8'),
])
def test_missing_malformed_or_unreadable_json(content, message, db, tmp_path):
    path = tmp_path / 'broken.json'
    if content is not None:
        path.write_bytes(content)
    before = db.list_cases()
    with pytest.raises(DatasetError, match=message):
        load_sample_dataset(db, path)
    assert db.list_cases() == before
