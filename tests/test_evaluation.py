"""Synthetic, reserved-domain fixtures only; no external data or downloads."""
import csv
import hashlib
import json
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
from types import SimpleNamespace

import pytest
import requests.sessions

from core.models import Intake
from evaluation.adapters.phiusiil import DatasetError, class_counts, load_dataset, select_records
from evaluation import evaluate
from evaluation.metrics import binary_metrics
from evaluation.reporting import write_reports

ROOT = Path(__file__).resolve().parents[1]


def csv_file(tmp_path, rows, columns=('URL', 'label'), name='fixture.csv'):
    path = tmp_path / name
    with path.open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow(columns)
        writer.writerows(rows)
    return path


@pytest.fixture
def fixture_csv(tmp_path):
    return csv_file(tmp_path, [
        ['https://identity.example@screened-phish.example/', '0'],
        ['https://plain-phish.example/', '0'],
        ['https://192.0.2.10/', '1'],
        ['https://plain-legitimate.example/', '1'],
    ])


def test_official_label_mapping_and_unused_columns(tmp_path):
    path = csv_file(tmp_path, [
        ['https://phish.example/', '0', 'Enter your password', '99'],
        ['https://legit.example/', '1', '', '0'],
    ], columns=('URL', 'label', 'Title', 'URLSimilarityIndex'))
    records = load_dataset(path).records
    assert {record.url: record.phishing for record in records} == {
        'https://phish.example/': True, 'https://legit.example/': False,
    }
    assert all(not hasattr(record, 'title') for record in records)


@pytest.mark.parametrize('columns', [('url', 'label'), ('URL', 'Label'), ('URL',), ('URL', 'label', 'URL')])
def test_bad_columns(columns, tmp_path):
    path = csv_file(tmp_path, [], columns)
    with pytest.raises(DatasetError, match='columns|column names'):
        load_dataset(path)


@pytest.mark.parametrize('label', ['', 'phishing', '2', '0.0', '=1+1'])
def test_invalid_labels_abort(label, tmp_path):
    path = csv_file(tmp_path, [['https://test.example/', label]])
    with pytest.raises(DatasetError, match='label must be 0 .* or 1'):
        load_dataset(path)


def test_preprocessing_counts_and_conflicts(tmp_path):
    rows = [
        ['https://GOOD.example', '0'], ['https://good.example/', '0'],
        ['https://conflict.example', '0'], ['https://CONFLICT.example/', '1'],
        ['https://conflict.example/', '0'],
        ['https://legit.example/', '1'], ['', '0'],
        ['javascript:alert(1)', '1'], ['not-a-url', '0'],
        ['https://bad host.example', '1'], ['https://[bad]', '0'],
    ]
    dataset = load_dataset(csv_file(tmp_path, rows))
    stats = dataset.statistics
    assert stats['original_rows'] == 11
    assert stats['empty_urls'] == 1 and stats['invalid_urls'] == 4
    assert stats['invalid_rows'] == 5 and stats['valid_rows'] == 6
    assert stats['removed_duplicate_rows'] == 1
    assert stats['conflicting_rows'] == 3 and stats['conflicting_url_groups'] == 1
    assert stats['cleaned_rows'] == 2
    assert stats['original_rows'] == sum(stats[key] for key in (
        'invalid_rows', 'removed_duplicate_rows', 'conflicting_rows', 'cleaned_rows'))
    assert {record.normalized_url for record in dataset.records} == {'https://good.example/', 'https://legit.example/'}
    assert dataset.sha256 == hashlib.sha256((tmp_path / 'fixture.csv').read_bytes()).hexdigest()


def test_dedupe_preserves_paths_queries_fragments_and_schemes(tmp_path):
    urls = ['http://same.example/', 'https://same.example/', 'https://same.example/path',
            'https://same.example/?a=1', 'https://same.example/#x', 'https://same.example:443/']
    dataset = load_dataset(csv_file(tmp_path, [[url, '0'] for url in urls]))
    assert len(dataset.records) == 6
    assert dataset.statistics['removed_duplicate_rows'] == 0


@pytest.mark.parametrize('rows', [[], [['', '0']], [['https://same.example', '0'], ['https://same.example/', '1']]])
def test_no_usable_records(rows, tmp_path):
    with pytest.raises(DatasetError, match='No usable records'):
        load_dataset(csv_file(tmp_path, rows))


@pytest.mark.parametrize('content', [b'URL,label\n"unterminated,0', b'URL,label\nhttps://a.example,0,extra',
                                      b'URL,label,Title\nhttps://a.example,0', b'\xff'])
def test_malformed_csv_or_encoding(content, tmp_path):
    path = tmp_path / 'bad.csv'
    path.write_bytes(content)
    with pytest.raises(DatasetError, match='CSV|field count'):
        load_dataset(path)


def test_balanced_deterministic_sampling(tmp_path):
    rows = [[f'https://p{index}.example/', '0'] for index in range(20)]
    rows += [[f'https://l{index}.example/', '1'] for index in range(30)]
    dataset = load_dataset(csv_file(tmp_path, rows))
    first = select_records(dataset.records, 10, 42)
    assert first == select_records(dataset.records, 10, 42)
    assert first != select_records(dataset.records, 10, 43)
    assert class_counts(first) == {'phishing': 5, 'legitimate': 5}
    assert len({record.normalized_url for record in first}) == 10
    assert select_records(dataset.records, None) == dataset.records


@pytest.mark.parametrize('size', [0, -2, 3, 1000])
def test_invalid_or_insufficient_sample_size(size, fixture_csv):
    with pytest.raises(DatasetError, match='positive even|per class'):
        select_records(load_dataset(fixture_csv).records, size)
    with pytest.raises(DatasetError, match='empty dataset'):
        select_records([], 2)


def test_metrics_independent_hand_calculation():
    metrics = binary_metrics([1] * 5 + [0] * 5, [1, 1, 0, 0, 0, 1, 0, 0, 0, 0])
    assert [metrics[key] for key in ('tp', 'fp', 'tn', 'fn')] == [2, 1, 4, 3]
    assert metrics['accuracy'] == pytest.approx(0.6)
    assert metrics['precision'] == pytest.approx(2 / 3)
    assert metrics['recall'] == pytest.approx(0.4)
    assert metrics['f1'] == pytest.approx(0.5)
    assert metrics['specificity'] == pytest.approx(0.8)
    assert metrics['false_positive_rate'] == pytest.approx(0.2)
    assert metrics['confusion_matrix']['values'] == [[4, 1], [3, 2]]
    assert not metrics['undefined_metrics']


def test_zero_denominators_are_explicit():
    metrics = binary_metrics([True, False], [False, False])
    assert metrics['precision'] == metrics['recall'] == metrics['f1'] == 0.0
    assert metrics['undefined_metrics'] == ['precision']
    empty = binary_metrics([], [])
    assert set(empty['undefined_metrics']) == {'accuracy', 'precision', 'recall', 'f1', 'specificity', 'false_positive_rate'}
    one_class = binary_metrics([True], [True])
    assert set(one_class['undefined_metrics']) == {'specificity', 'false_positive_rate'}
    assert one_class['precision'] == one_class['recall'] == one_class['f1'] == 1.0
    with pytest.raises(ValueError, match='equal lengths'):
        binary_metrics([True], [])
    with pytest.raises(ValueError, match='binary integer'):
        binary_metrics(['phishing'], [True])


def test_only_category_controls_protocol_a_prediction(monkeypatch):
    monkeypatch.setattr(evaluate, 'assess', lambda intake: SimpleNamespace(
        category='Other suspicious content', priority='High', indicators=['URL indicator']))
    assert evaluate.predict('https://test.example/', 'assessment')[0] is False
    monkeypatch.setattr(evaluate, 'assess', lambda intake: SimpleNamespace(
        category='Potential phishing', priority='Low', indicators=[]))
    assert evaluate.predict('https://test.example/', 'assessment')[0] is True


def test_actual_url_indicator_screening():
    assert evaluate.predict('https://ordinary.example/', 'url-screening') == (False, [])
    flagged, indicators = evaluate.predict('https://192.0.2.10/', 'url-screening')
    assert flagged and any('IP address' in signal for signal in indicators)
    with pytest.raises(ValueError, match='Unknown'):
        evaluate.predict('https://ordinary.example/', 'unknown')


def test_no_fabricated_fields_or_label_leakage(monkeypatch, tmp_path):
    seen = []
    original = evaluate.assess

    def captured(intake):
        seen.append(intake)
        return original(intake)

    monkeypatch.setattr(evaluate, 'assess', captured)
    for label in ('0', '1'):
        path = csv_file(tmp_path, [['https://ordinary.example/', label, 'Enter your password. Verify your account.', '100']],
                        columns=('URL', 'label', 'Title', 'URLSimilarityIndex'))
        evaluate.run_benchmark(path, sample_size=None)
    assert seen == [Intake('Website', url='https://ordinary.example/')] * 2


def test_reports_and_baselines_on_synthetic_fixture(fixture_csv, tmp_path):
    summary = evaluate.run_benchmark(fixture_csv, sample_size=4)
    assert summary['sampling']['class_distribution'] == {'phishing': 2, 'legitimate': 2}
    assert summary['protocols']['assessment']['metrics']['confusion_matrix']['values'] == [[2, 0], [2, 0]]
    assert summary['protocols']['url-screening']['metrics']['confusion_matrix']['values'] == [[1, 1], [1, 1]]
    assert summary['baselines']['always-legitimate']['accuracy'] == 0.5
    assert summary['baselines']['always-phishing']['recall'] == 1.0
    output = tmp_path / 'results'
    write_reports(summary, output)
    assert json.loads((output / 'summary.json').read_text()) == summary
    report = (output / 'report.md').read_text()
    for heading in ('Executive summary', 'Dataset and provenance', 'Methodology', 'Preprocessing',
                    'Protocol results', 'Confusion matrices', 'Interpretation', 'False-positive', 'Limitations'):
        assert heading in report
    assert 'Undefined ratios (reported as 0.0): precision' in report
    assert 'URL-only' in report and '0 = phishing' in report
    with (output / 'confusion_matrix.csv').open() as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 16
    assert sum(int(row['count']) for row in rows if row['evaluation'] == 'url-screening') == 4
    for path in output.iterdir():
        text = path.read_text()
        for value in ('plain-phish.example', 'screened-phish.example', 'identity.example', '192.0.2.10'):
            assert value not in text
    assert summary['dataset']['sha256'] == hashlib.sha256(fixture_csv.read_bytes()).hexdigest()
    assert summary['protocols']['url-screening']['error_analysis']['false_positives']['count'] == 1
    repeated = evaluate.run_benchmark(fixture_csv, sample_size=4)
    assert repeated['protocols'] == summary['protocols']
    assert repeated['sampling'] == summary['sampling']


def test_evaluation_is_offline_and_preserves_existing_sqlite(monkeypatch, fixture_csv, tmp_path):
    runtime = tmp_path / 'runtime'
    runtime.mkdir()
    database = runtime / 'cases.sqlite3'
    with sqlite3.connect(database) as connection:
        connection.execute('CREATE TABLE cases (notes TEXT)')
        connection.execute('INSERT INTO cases VALUES (?)', ('Keep my investigation',))
    before = database.read_bytes()
    monkeypatch.setenv('DRT_DATA_DIR', str(runtime))

    def forbidden(*args, **kwargs):
        pytest.fail('Evaluation attempted network or SQLite access')

    monkeypatch.setattr(sqlite3, 'connect', forbidden)
    monkeypatch.setattr(socket, 'create_connection', forbidden)
    monkeypatch.setattr(socket.socket, 'connect', forbidden)
    monkeypatch.setattr(requests.sessions.Session, 'request', forbidden)
    assert evaluate.main(['--dataset', str(fixture_csv), '--sample-size', '4', '--output', str(tmp_path / 'reports')]) == 0
    assert database.read_bytes() == before
    assert sorted(path.name for path in runtime.iterdir()) == ['cases.sqlite3']


def test_cli_subprocess_does_not_import_streamlit_or_database(fixture_csv, tmp_path):
    script = (
        'import sys; from evaluation.evaluate import main; '
        'main(sys.argv[1:]); '
        'assert "streamlit" not in sys.modules; '
        'assert "core.database" not in sys.modules'
    )
    result = subprocess.run([sys.executable, '-c', script, '--dataset', str(fixture_csv), '--full',
                             '--output', str(tmp_path / 'subprocess-reports')], cwd=ROOT,
                            capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr
    assert 'Evaluated 4 records' in result.stdout


@pytest.mark.parametrize('arguments', [
    ['--sample-size', '3'], ['--sample-size', '0'], ['--sample-size', '-2'],
    ['--sample-size', '4', '--full'], ['--seed', 'invalid'], ['--protocol', 'invalid'],
])
def test_cli_invalid_arguments(arguments, fixture_csv, tmp_path):
    output = tmp_path / 'no-reports'
    with pytest.raises(SystemExit) as error:
        evaluate.main(['--dataset', str(fixture_csv), '--output', str(output), *arguments])
    assert error.value.code == 2
    assert not output.exists()


def test_missing_file_and_protocol_selection(tmp_path, fixture_csv):
    with pytest.raises(DatasetError, match='file not found'):
        load_dataset(tmp_path / 'missing.csv')
    with pytest.raises(SystemExit) as error:
        evaluate.main(['--dataset', str(tmp_path / 'missing.csv')])
    assert error.value.code == 2
    summary = evaluate.run_benchmark(fixture_csv, sample_size=None, protocol='url-screening')
    assert set(summary['protocols']) == {'url-screening'}


def test_cli_refuses_to_overwrite_input_file(tmp_path):
    path = csv_file(tmp_path, [['https://test.example/', '0']], name='confusion_matrix.csv')
    before = path.read_bytes()
    with pytest.raises(SystemExit) as error:
        evaluate.main(['--dataset', str(path), '--full', '--output', str(tmp_path)])
    assert error.value.code == 2
    assert path.read_bytes() == before
