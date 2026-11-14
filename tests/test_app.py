"""Exercise Streamlit widgets against an isolated local database."""
from pathlib import Path
import csv
from io import BytesIO, StringIO
from types import SimpleNamespace

from openpyxl import load_workbook
from PIL import Image
import pytest
from streamlit.dataframe_util import convert_arrow_bytes_to_pandas_df
from streamlit.testing.v1 import AppTest

from core.database import Database
from core.models import Intake
from core.presentation import short_case_id

APP = Path(__file__).resolve().parents[1] / 'app.py'


def labeled(elements, label):
    return next(item for item in elements if item.label == label)


def select_queue_case(app, case_id):
    table = next(table for table in app.dataframe if table.key and table.key.startswith('queue_rows_'))
    index = app.session_state['queue_row_ids'].index(case_id)
    app.session_state[table.key] = {'selection': {'rows': [index], 'columns': [], 'cells': []}}
    app.run()


def test_investigator_workflow(monkeypatch, tmp_path):
    monkeypatch.setenv('DRT_DATA_DIR', str(tmp_path))
    app = AppTest.from_file(str(APP), default_timeout=20).run()
    assert not app.exception
    labeled(app.button, 'Analyze observation').click().run()
    assert app.error  # Invalid empty intake is handled visibly.
    labeled(app.text_input, 'Protected brand name (optional)').set_value('Astervale')
    labeled(app.text_input, 'Suspicious URL').set_value('https://astervale-security.example/login')
    labeled(app.text_input, 'Official brand domain (optional)').set_value('astervale.example')
    labeled(app.text_area, 'Description or suspicious content').set_value('Verify your account. Enter your password within 2 hours.')
    labeled(app.button, 'Analyze observation').click().run()
    assert not app.exception
    assert any('High is a review priority' in message.value for message in app.info)
    labeled(app.button, 'Save as new case').click().run()
    assert not app.exception
    db = Database(tmp_path / 'cases.sqlite3')
    case_id = db.list_cases()[0]['case_id']
    assert len(db.list_cases()) == 1

    app.radio[0].set_value('Case Review & Evidence').run()
    assert not app.exception
    timestamp_label = 'Evidence observation timestamp (UTC ISO 8601)'
    labeled(app.text_input, timestamp_label).set_value('2020-01-02T03:04:05Z')
    labeled(app.button, 'Attach screenshot').click().run()
    assert any('Choose a screenshot' in error.value for error in app.error)
    # Failed submissions and reruns must preserve the investigator's entry.
    app.run()
    assert labeled(app.text_input, timestamp_label).value == '2020-01-02T03:04:05Z'
    labeled(app.text_area, 'Investigator notes').set_value('Manually verified fictional supporting material.')
    labeled(app.selectbox, 'Review status').set_value('Escalated')
    labeled(app.selectbox, 'Manual verdict').set_value('Confirmed violation')
    labeled(app.button, 'Save review').click().run()
    assert any('before escalating' in error.value for error in app.error)
    assert db.get_case(case_id)['status'] == 'New'
    labeled(app.selectbox, 'Review status').set_value('Validated')
    labeled(app.button, 'Save review').click().run()
    assert not app.exception
    assert db.get_case(case_id)['status'] == 'Validated'
    labeled(app.selectbox, 'Review status').set_value('Escalated')
    labeled(app.button, 'Save review').click().run()
    assert db.get_case(case_id)['status'] == 'Escalated'
    assert not app.exception

    # A completely new Streamlit session still sees the existing case.
    restarted = AppTest.from_file(str(APP), default_timeout=20).run()
    restarted.radio[0].set_value('Case Queue').run()
    assert not restarted.exception
    assert len(restarted.dataframe[0].value) == 1
    labeled(restarted.selectbox, 'Status filter').set_value('False Positive').run()
    assert not restarted.dataframe
    restarted.radio[0].set_value('Dashboard & Reports').run()
    assert not restarted.exception
    assert restarted.metric[0].value == '1'
    assert restarted.metric[2].value == '1'
    assert len(restarted.get('download_button')) == 2

    labeled(restarted.button, 'Load Sample Dataset').click().run()
    assert not restarted.exception
    assert len(db.list_cases()) == 101
    labeled(restarted.button, 'Load Sample Dataset').click().run()
    assert len(db.list_cases()) == 101
    for section in ('New Investigation', 'Case Queue', 'Case Review & Evidence', 'Dashboard & Reports'):
        restarted.radio[0].set_value(section).run()
        assert not restarted.exception


def test_queue_opens_selected_case_and_restores_filters(monkeypatch, tmp_path):
    monkeypatch.setenv('DRT_DATA_DIR', str(tmp_path))
    db = Database(tmp_path / 'cases.sqlite3')
    older = db.create_case(Intake('Website', 'https://older.example', 'Astervale', title='Older case'))
    newer = db.create_case(Intake('Other', brand='', description='Reported online abuse to review.'))
    db.update_review(older, notes='Initial investigation', status='Reviewing', verdict='Inconclusive')
    app = AppTest.from_file(str(APP), default_timeout=20).run()
    app.radio[0].set_value('Case Review & Evidence').run()
    assert labeled(app.selectbox, 'Select case').value == newer
    app.radio[0].set_value('Case Queue').run()
    labeled(app.selectbox, 'Status filter').set_value('Reviewing')
    labeled(app.selectbox, 'Priority filter').set_value('Low')
    labeled(app.selectbox, 'Source filter').set_value('Website').run()
    assert app.session_state['queue_row_ids'] == [older]
    assert app.dataframe[0].value.iloc[0]['Title'] == 'Older case'
    assert app.dataframe[0].value.iloc[0]['Status'] == 'Reviewing'
    assert app.dataframe[0].value.iloc[0]['Case ID'] == older[:12]
    labeled(app.button, 'Open selected case').click().run()
    assert not app.exception
    assert app.radio[0].value == 'Case Review & Evidence'
    assert labeled(app.selectbox, 'Select case').value == older
    # Save a review: reruns must stay on the case opened from the queue.
    labeled(app.text_area, 'Investigator notes').set_value('Continued investigation')
    labeled(app.button, 'Save review').click().run()
    assert not app.exception
    assert labeled(app.selectbox, 'Select case').value == older
    assert db.get_case(older)['notes'] == 'Continued investigation'
    labeled(app.button, 'Back to Case Queue').click().run()
    assert not app.exception
    assert app.radio[0].value == 'Case Queue'
    assert labeled(app.selectbox, 'Status filter').value == 'Reviewing'
    assert labeled(app.selectbox, 'Priority filter').value == 'Low'
    assert labeled(app.selectbox, 'Source filter').value == 'Website'
    labeled(app.selectbox, 'Status filter').set_value('False Positive').run()
    assert not app.dataframe
    assert not any(button.label == 'Open selected case' for button in app.button)
    # The original independent case picker still works.
    app.radio[0].set_value('Case Review & Evidence').run()
    labeled(app.selectbox, 'Select case').set_value(newer).run()
    assert labeled(app.selectbox, 'Select case').value == newer
    assert not app.exception


def test_brandless_intake_save_and_open(monkeypatch, tmp_path):
    monkeypatch.setenv('DRT_DATA_DIR', str(tmp_path))
    app = AppTest.from_file(str(APP), default_timeout=20).run()
    labeled(app.text_input, 'Suspicious URL').set_value('https://account-alert.example/login')
    labeled(app.text_area, 'Description or suspicious content').set_value('Verify your account. Enter your password within 2 hours.')
    labeled(app.button, 'Analyze observation').click().run()
    assert not app.error
    assert any('High is a review priority' in info.value for info in app.info)
    labeled(app.button, 'Save as new case').click().run()
    cases = Database(tmp_path / 'cases.sqlite3').list_cases()
    assert len(cases) == 1
    assert cases[0]['brand'] == ''
    assert cases[0]['category'] == 'Potential phishing'
    app.radio[0].set_value('Case Queue').run()
    labeled(app.button, 'Open selected case').click().run()
    assert labeled(app.selectbox, 'Select case').value == cases[0]['case_id']
    assert not app.exception


def test_sample_presentation_preserves_legacy_and_manual_titles(monkeypatch, tmp_path):
    from core.demo import load_demo

    monkeypatch.setenv('DRT_DATA_DIR', str(tmp_path))
    db = Database(tmp_path / 'cases.sqlite3')
    legacy = db.create_case(Intake('Website', 'https://astervale-security.example/login',
                                  title='[SIMULATED] Legacy account alert'), demo_key='demo-v1-01')
    manual = db.create_case(Intake('Other', title='[SIMULATED] Investigator supplied title'))
    assert load_demo(db) == 99
    app = AppTest.from_file(str(APP), default_timeout=20).run()
    app.radio[0].set_value('Case Queue').run()
    assert not app.exception
    table = app.dataframe[0].value.set_index('Case ID')
    assert len(table) == 101
    assert table.loc[short_case_id(legacy), 'Title'] == 'Legacy account alert'
    assert table.loc[short_case_id(legacy), 'Data'] == 'Sample Data'
    assert table.loc[short_case_id(manual), 'Title'] == '[SIMULATED] Investigator supplied title'
    assert table.loc[short_case_id(manual), 'Data'] == 'Investigator intake'
    assert set(table['Source']) == {'Website', 'Social Media', 'Marketplace', 'Other'}
    select_queue_case(app, legacy)
    labeled(app.button, 'Open selected case').click().run()
    assert not app.exception
    assert not app.warning
    assert any('Sample Investigation' in caption.value for caption in app.caption)
    assert any(heading.value == 'Legacy account alert' for heading in app.subheader)
    assert not any('[SIMULATED]' in option for option in labeled(app.selectbox, 'Select case').options
                   if 'Investigator supplied' not in option)
    assert db.get_case(legacy)['title'] == '[SIMULATED] Legacy account alert'
    app.radio[0].set_value('Dashboard & Reports').run()
    assert not app.exception
    assert [metric.value for metric in app.metric] == ['101', '67', '21', '13']
    assert any('100 Sample Data' in caption.value and '1 Investigator intake' in caption.value
               for caption in app.caption)


def test_sample_dataset_error_is_visible_without_changing_cases(monkeypatch, tmp_path):
    from core import dataset_loader

    monkeypatch.setenv('DRT_DATA_DIR', str(tmp_path))
    monkeypatch.setattr(dataset_loader, 'DEFAULT_DATASET', tmp_path / 'missing-samples.json')
    db = Database(tmp_path / 'cases.sqlite3')
    db.create_case(Intake('Other', title='Existing investigator observation', notes='Preserve my notes'))
    before = db.list_cases()
    app = AppTest.from_file(str(APP), default_timeout=20).run()
    labeled(app.button, 'Load Sample Dataset').click().run()
    assert not app.exception
    assert any('Sample dataset not found' in error.value for error in app.error)
    assert db.list_cases() == before
    app.radio[0].set_value('Case Queue').run()
    assert not app.exception
    assert len(app.dataframe[0].value) == 1


@pytest.fixture
def populated_app(monkeypatch, tmp_path):
    from core.dataset_loader import load_sample_dataset

    monkeypatch.setenv('DRT_DATA_DIR', str(tmp_path))
    db = Database(tmp_path / 'cases.sqlite3')
    load_sample_dataset(db)
    high = db.create_case(Intake('Website', 'https://manual-alert.example/account', 'Astervale',
                                 'astervale.example', 'Manual account request',
                                 'Verify your account. Enter your password within 2 hours.'),
                          observed_at='2025-03-03T15:00:00.123456+07:00')
    low = db.create_case(Intake('Other', 'https://notes.example/reference', 'Northpetal',
                                title='Manual product note'), observed_at='2025-03-01T08:00:00Z')
    cleared = db.create_case(Intake('Website', 'https://catalogue.example/guide', title='Cleared catalogue report'))
    db.update_review(cleared, notes='The fictional report described an authorized catalogue reference.',
                     status='False Positive', verdict='No violation found')
    app = AppTest.from_file(str(APP), default_timeout=20).run()
    return app, db, {'high': high, 'low': low, 'cleared': cleared}


def test_queue_data_source_composes_with_filters_search_sort_and_return(populated_app):
    app, db, ids = populated_app
    before = db.list_cases()
    app.radio[0].set_value('Case Queue').run()
    labeled(app.selectbox, 'Data source').set_value('Investigator intake')
    labeled(app.selectbox, 'Status filter').set_value('New')
    labeled(app.selectbox, 'Priority filter').set_value('High')
    labeled(app.selectbox, 'Source filter').set_value('Website')
    labeled(app.text_input, 'Search cases').set_value('MANUAL-ALERT.EXAMPLE')
    labeled(app.selectbox, 'Sort cases').set_value('Oldest observed').run()
    assert not app.exception
    assert app.session_state['queue_row_ids'] == [ids['high']]
    assert app.dataframe[0].value.iloc[0]['Data'] == 'Investigator intake'
    assert app.dataframe[0].value.iloc[0]['Observed (UTC)'] == '03 Mar 2025, 08:00 UTC'
    labeled(app.button, 'Open selected case').click().run()
    assert labeled(app.selectbox, 'Select case').value == ids['high']
    app.radio[0].set_value('Dashboard & Reports').run()
    app.radio[0].set_value('Case Review & Evidence').run()
    assert labeled(app.selectbox, 'Select case').value == ids['high']
    labeled(app.button, 'Back to Case Queue').click().run()
    assert labeled(app.selectbox, 'Data source').value == 'Investigator intake'
    assert labeled(app.selectbox, 'Status filter').value == 'New'
    assert labeled(app.selectbox, 'Priority filter').value == 'High'
    assert labeled(app.selectbox, 'Source filter').value == 'Website'
    assert labeled(app.text_input, 'Search cases').value == 'MANUAL-ALERT.EXAMPLE'
    assert labeled(app.selectbox, 'Sort cases').value == 'Oldest observed'
    labeled(app.selectbox, 'Data source').set_value('Sample Data').run()
    assert not app.exception and not app.dataframe
    assert not any(button.label == 'Open selected case' for button in app.button)
    assert labeled(app.selectbox, 'Status filter').value == 'New'
    assert db.list_cases() == before


@pytest.mark.parametrize('query_field', ['title', 'case_id', 'brand', 'source_url'])
def test_queue_search_and_empty_state(populated_app, query_field):
    app, db, ids = populated_app
    high = db.get_case(ids['high'])
    app.radio[0].set_value('Case Queue').run()
    labeled(app.selectbox, 'Data source').set_value('Investigator intake')
    labeled(app.text_input, 'Search cases').set_value(high[query_field].swapcase()).run()
    assert app.session_state['queue_row_ids'] == [ids['high']]
    labeled(app.text_input, 'Search cases').set_value('no case matches this query').run()
    assert not app.exception and not app.dataframe
    assert any('No cases match' in message.value for message in app.info)
    assert not any(button.label == 'Open selected case' for button in app.button)


def test_native_row_selection_tracks_full_id_after_sort_and_review(populated_app):
    app, db, ids = populated_app
    app.radio[0].set_value('Case Queue').run()
    labeled(app.selectbox, 'Data source').set_value('Investigator intake').run()
    select_queue_case(app, ids['low'])
    assert app.session_state['queue_case'] == ids['low']
    old_key = app.dataframe[0].key
    labeled(app.selectbox, 'Sort cases').set_value('Priority low to high').run()
    assert app.dataframe[0].key != old_key
    assert app.session_state['queue_case'] == ids['low']
    labeled(app.button, 'Open selected case').click().run()
    assert labeled(app.selectbox, 'Select case').value == ids['low']
    labeled(app.text_area, 'Investigator notes').set_value('Fictional concern reviewed and cleared.')
    labeled(app.selectbox, 'Review status').set_value('False Positive')
    labeled(app.selectbox, 'Manual verdict').set_value('No violation found')
    labeled(app.button, 'Save review').click().run()
    assert labeled(app.selectbox, 'Select case').value == ids['low']
    labeled(app.button, 'Back to Case Queue').click().run()
    assert app.session_state['queue_case'] == ids['low']
    labeled(app.button, 'Open selected case').click().run()
    assert labeled(app.selectbox, 'Select case').value == ids['low']
    assert db.get_case(ids['low'])['status'] == 'False Positive'


def test_short_id_collisions_do_not_change_selection_identity(monkeypatch, tmp_path):
    monkeypatch.setenv('DRT_DATA_DIR', str(tmp_path))
    db = Database(tmp_path / 'cases.sqlite3')
    import core.database as database_module
    with monkeypatch.context() as patch:
        patch.setattr(database_module, 'uuid4', lambda: SimpleNamespace(hex='12345678' + 'a' * 24))
        first = db.create_case(Intake('Other', title='First matching short identifier'))
        patch.setattr(database_module, 'uuid4', lambda: SimpleNamespace(hex='12345678' + 'b' * 24))
        second = db.create_case(Intake('Other', title='Second matching short identifier'))
    app = AppTest.from_file(str(APP), default_timeout=20).run()
    app.radio[0].set_value('Case Queue').run()
    assert app.dataframe[0].value['Case ID'].nunique() == 1
    for case_id in (first, second):
        select_queue_case(app, case_id)
        labeled(app.button, 'Open selected case').click().run()
        assert labeled(app.selectbox, 'Select case').value == case_id
        assert any(code.value == case_id for code in app.code)
        labeled(app.button, 'Back to Case Queue').click().run()


def test_dashboard_chart_metrics_and_report_exports_share_data_source(populated_app, monkeypatch):
    import core.reporting as reporting

    app, db, ids = populated_app
    before = db.list_cases()
    captured = {}
    csv_export, excel_export = reporting.export_csv, reporting.export_excel

    def capture_csv(database, cases=None):
        captured['csv'] = csv_export(database, cases)
        return captured['csv']

    def capture_excel(database, cases=None):
        captured['excel'] = excel_export(database, cases)
        return captured['excel']

    monkeypatch.setattr(reporting, 'export_csv', capture_csv)
    monkeypatch.setattr(reporting, 'export_excel', capture_excel)
    app.radio[0].set_value('Dashboard & Reports').run()
    for data_source, metrics, expected_ids in (
        ('All cases', ['103', '68', '21', '14'], {case['case_id'] for case in before}),
        ('Sample Data', ['100', '66', '21', '13'], {case['case_id'] for case in before if case['is_demo']}),
        ('Investigator intake', ['3', '2', '0', '1'], set(ids.values())),
    ):
        labeled(app.selectbox, 'Data source').set_value(data_source).run()
        assert not app.exception
        assert [metric.value for metric in app.metric] == metrics
        assert all(button.proto.ignore_rerun for button in app.get('download_button'))
        chart = convert_arrow_bytes_to_pandas_df(app.get('vega_lite_chart')[0].proto.data.data)
        assert chart['Cases'].sum() == int(metrics[0])
        rows = list(csv.DictReader(StringIO(captured['csv'].decode('utf-8-sig'))))
        assert {row['case_id'] for row in rows} == expected_ids
        book = load_workbook(BytesIO(captured['excel']))
        assert {row[0] for row in list(book['Cases'].values)[1:]} == expected_ids
    assert chart['Cases'].tolist() == [1, 0, 0, 0, 2]
    labeled(app.selectbox, 'Priority filter').set_value('High').run()
    rows = list(csv.DictReader(StringIO(captured['csv'].decode('utf-8-sig'))))
    assert len(rows) == 1 and rows[0]['case_id'] == ids['high']
    assert rows[0]['data_label'] == 'Investigator intake'
    assert rows[0]['observed_at'] == '2025-03-03T08:00:00.123456+00:00'
    excel_rows = list(load_workbook(BytesIO(captured['excel']))['Cases'].values)
    assert excel_rows[1][excel_rows[0].index('observed_at')] == rows[0]['observed_at']
    assert [metric.value for metric in app.metric] == ['3', '2', '0', '1']
    labeled(app.selectbox, 'Status filter').set_value('False Positive').run()
    assert len(list(csv.DictReader(StringIO(captured['csv'].decode('utf-8-sig'))))) == 0
    assert not app.exception
    assert db.list_cases() == before


def test_dashboard_empty_data_source(monkeypatch, tmp_path):
    monkeypatch.setenv('DRT_DATA_DIR', str(tmp_path))
    app = AppTest.from_file(str(APP), default_timeout=20).run()
    app.radio[0].set_value('Dashboard & Reports').run()
    labeled(app.selectbox, 'Data source').set_value('Investigator intake').run()
    assert not app.exception
    assert [metric.value for metric in app.metric] == ['0', '0', '0', '0']
    assert not app.get('vega_lite_chart') and not app.dataframe
    assert any('No cases in this data source' in message.value for message in app.info)


@pytest.mark.parametrize('timestamp', ['', '2025-01-06T15:00:00.123456+07:00'])
def test_manual_observation_time_survives_analyze_preview_save(timestamp, monkeypatch, tmp_path):
    monkeypatch.setenv('DRT_DATA_DIR', str(tmp_path))
    app = AppTest.from_file(str(APP), default_timeout=20).run()
    labeled(app.text_input, 'Suspicious URL').set_value('https://manual-time.example')
    labeled(app.text_input, 'Observation time (optional, UTC)').set_value(timestamp)
    labeled(app.button, 'Analyze observation').click().run()
    assert not app.exception and not app.error
    expected = '2025-01-06T08:00:00.123456+00:00' if timestamp else None
    assert app.session_state['pending_observed_at'] == expected
    assert any(('06 Jan 2025, 08:00 UTC' if timestamp else 'Automatic UTC time when saved') in caption.value
               for caption in app.caption)
    labeled(app.button, 'Save as new case').click().run()
    assert not app.exception
    case = Database(tmp_path / 'cases.sqlite3').list_cases()[0]
    assert case['observed_at'] == (expected or case['created_at'])


@pytest.mark.parametrize('timestamp', ['bad timestamp', '2025-01-06T08:00:00', '2099-01-01T00:00:00Z'])
def test_invalid_or_future_time_clears_previous_preview(timestamp, monkeypatch, tmp_path):
    monkeypatch.setenv('DRT_DATA_DIR', str(tmp_path))
    app = AppTest.from_file(str(APP), default_timeout=20).run()
    labeled(app.text_input, 'Suspicious URL').set_value('https://manual-time.example')
    labeled(app.button, 'Analyze observation').click().run()
    assert any(button.label == 'Save as new case' for button in app.button)
    labeled(app.text_input, 'Observation time (optional, UTC)').set_value(timestamp)
    labeled(app.button, 'Analyze observation').click().run()
    assert app.error and not app.exception
    assert not any(button.label == 'Save as new case' for button in app.button)
    assert Database(tmp_path / 'cases.sqlite3').list_cases() == []


@pytest.mark.parametrize(('field', 'new_value'), [
    ('Observation time (optional, UTC)', '2025-02-01T08:00:00Z'),
    ('Suspicious URL', 'https://changed-observation.example'),
])
def test_unanalyzed_edits_cannot_save_a_stale_preview(field, new_value, monkeypatch, tmp_path):
    monkeypatch.setenv('DRT_DATA_DIR', str(tmp_path))
    app = AppTest.from_file(str(APP), default_timeout=20).run()
    labeled(app.text_input, 'Suspicious URL').set_value('https://original.example')
    labeled(app.text_input, 'Observation time (optional, UTC)').set_value('2025-01-06T08:00:00Z')
    labeled(app.button, 'Analyze observation').click().run()
    labeled(app.text_input, field).set_value(new_value)
    labeled(app.button, 'Save as new case').click().run()
    assert not app.exception
    assert any('Analyze again before saving' in message.value for message in app.warning)
    db = Database(tmp_path / 'cases.sqlite3')
    assert not db.list_cases()
    assert not any(button.label == 'Save as new case' for button in app.button)
    labeled(app.button, 'Analyze observation').click().run()
    labeled(app.button, 'Save as new case').click().run()
    case = db.list_cases()[0]
    assert case['observed_at'] == ('2025-02-01T08:00:00+00:00' if field.startswith('Observation') else '2025-01-06T08:00:00+00:00')
    assert case['source_url'] == ('https://changed-observation.example' if field == 'Suspicious URL' else 'https://original.example')


def test_review_displays_evidence_without_changing_metadata(populated_app, tmp_path):
    from core.evidence import save_evidence
    from core.models import utc_now

    app, db, ids = populated_app
    image = BytesIO()
    Image.new('RGB', (2, 2), 'navy').save(image, format='PNG')
    evidence = save_evidence(db, tmp_path / 'evidence', ids['high'], original_name='manual-test.png',
                             content=image.getvalue(), source_url='https://manual-alert.example/account', observed_at=utc_now())
    before = db.get_case(ids['high'])
    app.radio[0].set_value('Case Review & Evidence').run()
    labeled(app.selectbox, 'Select case').set_value(ids['high']).run()
    assert not app.exception
    assert app.get('image')
    assert any(code.value == ids['high'] for code in app.code)
    assert db.list_evidence(ids['high']) == [evidence]
    assert db.get_case(ids['high']) == before


def test_newly_saved_case_opens_instead_of_previous_review(populated_app):
    app, db, ids = populated_app
    app.radio[0].set_value('Case Review & Evidence').run()
    labeled(app.selectbox, 'Select case').set_value(ids['low']).run()
    app.radio[0].set_value('New Investigation').run()
    labeled(app.text_input, 'Suspicious URL').set_value('https://new-case.example')
    labeled(app.button, 'Analyze observation').click().run()
    labeled(app.button, 'Save as new case').click().run()
    created = next(case for case in db.list_cases() if case['source_url'] == 'https://new-case.example')
    app.radio[0].set_value('Case Review & Evidence').run()
    assert not app.exception
    assert labeled(app.selectbox, 'Select case').value == created['case_id']


@pytest.mark.parametrize('timestamp', ['2099-01-01T00:00:00Z', '2025-01-06T08:00:00'])
def test_invalid_timestamp_edit_at_save_is_rejected(timestamp, monkeypatch, tmp_path):
    monkeypatch.setenv('DRT_DATA_DIR', str(tmp_path))
    app = AppTest.from_file(str(APP), default_timeout=20).run()
    labeled(app.text_input, 'Suspicious URL').set_value('https://save-time.example')
    labeled(app.button, 'Analyze observation').click().run()
    labeled(app.text_input, 'Observation time (optional, UTC)').set_value(timestamp)
    labeled(app.button, 'Save as new case').click().run()
    assert app.error and not app.exception
    assert not any(button.label == 'Save as new case' for button in app.button)
    assert Database(tmp_path / 'cases.sqlite3').list_cases() == []
