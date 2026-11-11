import csv
from io import BytesIO, StringIO

from openpyxl import load_workbook
import pytest

from core.database import Database
from core.demo import load_demo
from core.models import CATEGORIES, Intake
from core.reporting import COLUMNS, export_csv, export_excel, safe_cell
from core.evidence import save_evidence
from core.models import utc_now
from PIL import Image


@pytest.fixture
def db(tmp_path):
    return Database(tmp_path / 'cases.db')


def test_demo_coverage_idempotence_and_preserves_edits(db):
    assert load_demo(db) == 12
    cases = db.list_cases()
    assert len(cases) == 12
    assert set(c['category'] for c in cases) == set(CATEGORIES)
    assert all(c['is_demo'] and '.example' in c['source_url'] for c in cases)
    assert len(db.list_cases(status='False Positive')) == 3
    assert not db.list_cases(status='Validated')
    db.update_review(cases[0]['case_id'], notes='Keep my edits', status='Reviewing', verdict='Inconclusive')
    assert load_demo(db) == 0
    assert len(db.list_cases()) == 12
    assert db.get_case(cases[0]['case_id'])['notes'] == 'Keep my edits'


@pytest.mark.parametrize('value', ['=1+1', '+SUM(A1:A2)', '-1+2', '@SUM(A1:A2)', '\tformula', ' \t=1+1', '\x00=1+1', '\ufeff=1+1'])
def test_formula_neutralization(value):
    assert safe_cell(value).startswith("'")


def test_reports_roundtrip_with_evidence_and_formula_injection(db, tmp_path):
    case_id = db.create_case(Intake('Website', 'https://example.com', 'Astervale',
                                  title='=HYPERLINK("https://example.com","click")', description='A normal description', notes='  +SUM(1,2)'))
    buf = BytesIO()
    Image.new('RGB', (2, 2)).save(buf, format='PNG')
    evidence = save_evidence(db, tmp_path / 'evidence', case_id, original_name='=danger.png', content=buf.getvalue(),
                             source_url='https://example.com', observed_at=utc_now())
    rows = list(csv.DictReader(StringIO(export_csv(db).decode('utf-8-sig'))))
    assert len(rows) == 1
    assert rows[0]['case_id'] == case_id
    assert rows[0]['title'].startswith("'")
    assert rows[0]['analyst_notes'].startswith("'")
    assert evidence['filename'] in rows[0]['evidence_references']
    book = load_workbook(BytesIO(export_excel(db)))
    assert book.sheetnames == ['Cases', 'Evidence']
    assert book['Cases'].max_row == 2
    assert book['Evidence'].max_row == 2
    for sheet in book:
        assert not any(cell.data_type == 'f' for row in sheet for cell in row)


def test_empty_and_filtered_reports(db):
    assert list(csv.reader(StringIO(export_csv(db).decode('utf-8-sig')))) == [COLUMNS]
    assert load_workbook(BytesIO(export_excel(db)))['Cases'].max_row == 1
    load_demo(db)
    rows = list(csv.DictReader(StringIO(export_csv(db, db.list_cases(status='False Positive')).decode('utf-8-sig'))))
    assert len(rows) == 3
    assert all(row['data_label'] == 'SIMULATED DEMO' for row in rows)


def test_unbranded_case_persists_review_and_exports(db):
    case_id = db.create_case(Intake('Website', 'https://account-alert.example',
                                    description='Verify your account. Enter your password within 2 hours.'))
    db.update_review(case_id, notes='General phishing investigation', status='Reviewing', verdict='Inconclusive')
    restarted = Database(db.path)
    assert restarted.get_case(case_id)['brand'] == ''
    rows = list(csv.DictReader(StringIO(export_csv(restarted).decode('utf-8-sig'))))
    assert rows[0]['brand'] == ''
    assert rows[0]['category'] == 'Potential phishing'
    assert rows[0]['status'] == 'Reviewing'
    book = load_workbook(BytesIO(export_excel(restarted)))
    headers = [cell.value for cell in book['Cases'][1]]
    values = dict(zip(headers, [cell.value for cell in book['Cases'][2]]))
    assert values['case_id'] == case_id
    assert values['brand'] is None
    assert values['priority'] == 'High'
