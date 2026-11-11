import pytest
from core.database import Database
from core.models import Intake


@pytest.fixture
def db(tmp_path):
    return Database(tmp_path / 'cases.sqlite3')


def new_case(db):
    return db.create_case(Intake('Website', 'https://example.com', 'Astervale', description='Normal store'))


def test_create_read_persist_filter_and_update(db):
    case_id = new_case(db)
    case = Database(db.path).get_case(case_id)
    assert case['status'] == 'New'
    assert case['verdict'] == 'Pending review'
    assert case['observed_at'].endswith('+00:00')
    assert case['created_at'] == case['updated_at']
    db.update_review(case_id, notes="Analyst's review", status='Reviewing', verdict='Inconclusive')
    assert db.get_case(case_id)['notes'] == "Analyst's review"
    assert db.get_case(case_id)['updated_at'] > case['updated_at']
    assert len(db.list_cases(status='Reviewing', priority='Low', source_type='Website')) == 1
    assert db.list_cases(status='New') == []
    assert db.get_case('missing') is None
    with pytest.raises(ValueError):
        db.list_cases(status="' OR 1=1")


def test_validation_required_before_escalation(db):
    case_id = new_case(db)
    with pytest.raises(ValueError, match='before escalating'):
        db.update_review(case_id, notes='Checked sources', status='Escalated', verdict='Confirmed violation')
    with pytest.raises(ValueError, match='supporting notes'):
        db.update_review(case_id, notes='', status='Validated', verdict='Confirmed violation')
    with pytest.raises(ValueError):
        db.update_review(case_id, notes='Checked sources', status='Validated', verdict='Pending review')
    db.update_review(case_id, notes='Manually verified supporting evidence', status='Validated', verdict='Confirmed violation')
    validated = db.get_case(case_id)['validated_at']
    db.update_review(case_id, notes='Escalation rationale', status='Escalated', verdict='Confirmed violation')
    assert db.get_case(case_id)['validated_at'] == validated
    db.update_review(case_id, notes='Reopening investigation', status='Reviewing', verdict='Inconclusive')
    with pytest.raises(ValueError):
        db.update_review(case_id, notes='Must validate again', status='Escalated', verdict='Confirmed violation')


def test_false_positive_and_bad_updates(db):
    case_id = new_case(db)
    with pytest.raises(ValueError):
        db.update_review(case_id, notes='benign', status='False Positive', verdict='Pending review')
    db.update_review(case_id, notes='Authorized by owner', status='False Positive', verdict='No violation found')
    assert db.get_case(case_id)['status'] == 'False Positive'
    with pytest.raises(ValueError, match='not found'):
        db.update_review('missing', notes='', status='Reviewing', verdict='Pending review')


def test_demo_key_is_idempotent(db):
    data = Intake('Other', brand='Astervale', description='SIMULATED demonstration content')
    first = db.create_case(data, demo_key='one')
    assert db.create_case(data, demo_key='one') == first
    assert len(db.list_cases()) == 1
