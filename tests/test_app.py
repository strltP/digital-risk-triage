"""Exercise Streamlit widgets against an isolated local database."""
from pathlib import Path

from streamlit.testing.v1 import AppTest

from core.database import Database
from core.models import Intake

APP = Path(__file__).resolve().parents[1] / 'app.py'


def labeled(elements, label):
    return next(item for item in elements if item.label == label)


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
    options = labeled(app.selectbox, 'Case to review').options
    assert len(options) == 1
    assert 'Older case' in options[0] and 'Reviewing' in options[0] and older[:12] in options[0]
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
    assert table.loc[legacy, 'Title'] == 'Legacy account alert'
    assert table.loc[legacy, 'Data'] == 'Sample Data'
    assert table.loc[manual, 'Title'] == '[SIMULATED] Investigator supplied title'
    assert table.loc[manual, 'Data'] == 'Investigator intake'
    assert set(table['Source']) == {'Website', 'Social Media', 'Marketplace', 'Other'}
    labeled(app.selectbox, 'Case to review').set_value(legacy)
    labeled(app.button, 'Open selected case').click().run()
    assert not app.exception
    assert not app.warning
    assert any('Sample Investigation' in caption.value for caption in app.caption)
    assert any(text.value == 'Legacy account alert' for text in app.text)
    assert not any('[SIMULATED]' in option for option in labeled(app.selectbox, 'Select case').options
                   if 'Investigator supplied' not in option)
    assert db.get_case(legacy)['title'] == '[SIMULATED] Legacy account alert'
    app.radio[0].set_value('Dashboard & Reports').run()
    assert not app.exception
    assert [metric.value for metric in app.metric] == ['101', '67', '21', '13']
    assert any('100 Sample Data' in caption.value and '1 Investigator intake' in caption.value
               for caption in app.caption)
