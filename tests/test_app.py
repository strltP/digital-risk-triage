"""Exercise Streamlit widgets against an isolated local database."""
from pathlib import Path

from streamlit.testing.v1 import AppTest

from core.database import Database

APP = Path(__file__).resolve().parents[1] / 'app.py'


def labeled(elements, label):
    return next(item for item in elements if item.label == label)


def test_investigator_workflow(monkeypatch, tmp_path):
    monkeypatch.setenv('DRT_DATA_DIR', str(tmp_path))
    app = AppTest.from_file(str(APP), default_timeout=20).run()
    assert not app.exception
    labeled(app.button, 'Analyze observation').click().run()
    assert app.error  # Invalid empty intake is handled visibly.
    labeled(app.text_input, 'Protected brand name').set_value('Astervale')
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

    labeled(restarted.button, 'Load 12 simulated demo cases').click().run()
    assert not restarted.exception
    assert len(db.list_cases()) == 13
    labeled(restarted.button, 'Load 12 simulated demo cases').click().run()
    assert len(db.list_cases()) == 13
    for section in ('New Investigation', 'Case Queue', 'Case Review & Evidence', 'Dashboard & Reports'):
        restarted.radio[0].set_value(section).run()
        assert not restarted.exception
