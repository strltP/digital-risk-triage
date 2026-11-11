from io import BytesIO
from unittest.mock import patch

from PIL import Image
import pytest

from core.database import Database
from core.evidence import MAX_BYTES, evidence_path, save_evidence
from core.models import Intake, utc_now


def png():
    buffer = BytesIO()
    Image.new('RGB', (4, 4), 'navy').save(buffer, format='PNG')
    return buffer.getvalue()


@pytest.fixture
def context(tmp_path):
    db = Database(tmp_path / 'cases.db')
    case_id = db.create_case(Intake('Website', 'https://example.com', 'Astervale'))
    return db, case_id, tmp_path / 'evidence'


def upload(context, **kwargs):
    db, case_id, folder = context
    return save_evidence(db, folder, case_id, **(dict(original_name='screenshot.png', content=png(),
                         source_url='https://example.com/page', observed_at=utc_now()) | kwargs))


def test_upload_and_safe_paths_and_metadata(context):
    db, case_id, folder = context
    metadata = upload(context, original_name='../../screenshot.png')
    path = evidence_path(folder, metadata['filename'])
    assert path.parent == folder
    assert path.read_bytes() == png()
    assert db.list_evidence(case_id)[0]['sha256'] == metadata['sha256']
    assert metadata['original_name'] == 'screenshot.png'
    assert metadata['source_url'] == 'https://example.com/page'
    for name in ('../screenshot.png', '/etc/passwd', 'a.svg'):
        with pytest.raises(ValueError):
            evidence_path(folder, name)


@pytest.mark.parametrize('kwargs', [
    {'content': b'not an image'}, {'content': b''}, {'original_name': 'image.svg'},
    {'original_name': 'image.jpg'}, {'content': b'x' * (MAX_BYTES + 1)},
    {'observed_at': '2020-01-01T10:00:00'}, {'observed_at': '2099-01-01T00:00:00Z'},
    {'source_url': 'javascript:alert(1)'},
])
def test_reject_bad_uploads(context, kwargs):
    with pytest.raises(ValueError):
        upload(context, **kwargs)
    assert context[0].list_evidence(context[1]) == []
    assert not context[2].exists()


def test_missing_case_and_database_failure_cleanup(context):
    db, case_id, folder = context
    with pytest.raises(ValueError, match='existing case'):
        save_evidence(db, folder, 'missing', original_name='a.png', content=png(), source_url='', observed_at=utc_now())
    with patch.object(db, 'add_evidence_metadata', side_effect=RuntimeError('test failure')):
        with pytest.raises(RuntimeError):
            upload(context)
    assert not list(folder.iterdir())
