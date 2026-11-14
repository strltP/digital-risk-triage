import pytest
from core.database import Database
from core.models import Intake, STATUSES, VERDICTS


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


@pytest.mark.parametrize('status', STATUSES)
@pytest.mark.parametrize('verdict', VERDICTS)
def test_status_verdict_contract_and_failed_updates_preserve_record(db, status, verdict):
    case_id = new_case(db)
    if status == 'Escalated':
        db.update_review(case_id, notes='Supporting review context', status='Validated', verdict='Confirmed violation')
    before = db.get_case(case_id)
    allowed = {
        'New': {'Pending review'},
        'Reviewing': {'Pending review', 'Inconclusive', 'No violation found'},
        'Validated': {'Confirmed violation'}, 'Escalated': {'Confirmed violation'},
        'False Positive': {'No violation found'},
    }
    if verdict in allowed[status]:
        db.update_review(case_id, notes='Supporting review context', status=status, verdict=verdict)
        assert Database(db.path).get_case(case_id)['verdict'] == verdict
    else:
        with pytest.raises(ValueError):
            db.update_review(case_id, notes='Supporting review context', status=status, verdict=verdict)
        assert Database(db.path).get_case(case_id) == before


def test_provisional_no_violation_requires_notes_but_drafts_remain_allowed(db):
    case_id = new_case(db)
    before = db.get_case(case_id)
    with pytest.raises(ValueError, match='supporting notes'):
        db.update_review(case_id, notes=' ', status='Reviewing', verdict='No violation found')
    assert db.get_case(case_id) == before
    for verdict in ('Pending review', 'Inconclusive'):
        db.update_review(case_id, notes='', status='Reviewing', verdict=verdict)
    db.update_review(case_id, notes='Provisional clearance; another reported detail remains open.',
                     status='Reviewing', verdict='No violation found')


@pytest.mark.parametrize(('status', 'verdict'), [('New', 'Pending review'), ('Reviewing', 'Inconclusive'),
                                               ('False Positive', 'No violation found')])
def test_reopening_clears_validation_across_restarts(db, status, verdict):
    case_id = new_case(db)
    db.update_review(case_id, notes='Supporting fictional review', status='Validated', verdict='Confirmed violation')
    db.update_review(case_id, notes='Previous escalation rationale', status='Escalated', verdict='Confirmed violation')
    db.update_review(case_id, notes='Reassessed the reported context', status=status, verdict=verdict)
    restarted = Database(db.path)
    assert restarted.get_case(case_id)['validated_at'] is None
    before = restarted.get_case(case_id)
    with pytest.raises(ValueError, match='before escalating'):
        restarted.update_review(case_id, notes='Needs a new validation', status='Escalated', verdict='Confirmed violation')
    assert restarted.get_case(case_id) == before


def test_preliminary_category_and_priority_never_assign_a_human_verdict(db):
    high = db.create_case(Intake('Website', 'https://account-alert.example',
                                description='Verify your account. Enter your password within 2 hours.'))
    low = db.create_case(Intake('Website', 'https://ordinary.example', description='Routine product information'))
    for case_id, priority in ((high, 'High'), (low, 'Low')):
        case = db.get_case(case_id)
        assert case['priority'] == priority
        assert case['status'] == 'New' and case['verdict'] == 'Pending review'
        assert case['validated_at'] is None
    assert db.get_case(low)['category'] == 'Other suspicious content'
    assert not db.get_case(low)['indicators']
    db.update_review(low, notes='Reported copied page; the fictional exercise establishes an authorized reference.',
                     status='False Positive', verdict='No violation found')
    assert db.get_case(low)['priority'] == 'Low'


def test_old_status_combination_remains_readable_without_automatic_cleanup(db):
    case_id = new_case(db)
    with db.connection() as conn:
        conn.execute("UPDATE cases SET verdict='Inconclusive' WHERE case_id=?", (case_id,))
    before = db.get_case(case_id)
    assert Database(db.path).get_case(case_id) == before
    assert before['status'] == 'New' and before['verdict'] == 'Inconclusive'
    db.update_review(case_id, notes='Continue the existing investigation', status='Reviewing', verdict='Inconclusive')
