"""Manually supplied images only; validate content before writing local files."""
from hashlib import sha256
from io import BytesIO
from pathlib import Path
import re
import warnings
from uuid import uuid4

from PIL import Image, UnidentifiedImageError

from core.database import Database
from core.models import observation_time, utc_now
from core.url_analysis import normalize_url

MAX_BYTES = 5 * 1024 * 1024
MAX_PIXELS = 20_000_000


def evidence_path(directory: str | Path, filename: str) -> Path:
    if not re.fullmatch(r"[0-9a-f]{32}\.(?:png|jpg)", filename):
        raise ValueError("Invalid evidence reference.")
    root = Path(directory).resolve()
    path = (root / filename).resolve()
    if path.parent != root:
        raise ValueError("Evidence reference leaves the evidence directory.")
    return path


def save_evidence(db: Database, directory: str | Path, case_id: str, *, original_name: str,
                  content: bytes, source_url: str, observed_at: str, description: str = "") -> dict:
    if db.get_case(case_id) is None:
        raise ValueError("Select an existing case before uploading evidence.")
    if not content or len(content) > MAX_BYTES:
        raise ValueError("Upload a nonempty PNG/JPG screenshot no larger than 5 MiB.")
    original_name = original_name.replace("\\", "/").split("/")[-1]
    if not original_name or len(original_name) > 255 or any(ord(c) < 32 for c in original_name):
        raise ValueError("Screenshot filename is invalid or too long.")
    suffix = Path(original_name).suffix.lower()
    allowed = {".png": "PNG", ".jpg": "JPEG", ".jpeg": "JPEG"}
    if suffix not in allowed:
        raise ValueError("Only .png, .jpg, and .jpeg screenshots are supported.")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(content)) as picture:
                fmt = picture.format
                if fmt != allowed[suffix]:
                    raise ValueError("Screenshot extension does not match the image content.")
                if picture.width * picture.height > MAX_PIXELS:
                    raise ValueError("Screenshot exceeds the 20-megapixel limit.")
                if getattr(picture, "n_frames", 1) != 1:
                    raise ValueError("Upload a still screenshot, not an animated image.")
                picture.verify()
            with Image.open(BytesIO(content)) as picture:
                picture.load()
    except (UnidentifiedImageError, OSError, SyntaxError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise ValueError("The upload is not a valid, readable PNG/JPG screenshot.") from exc
    observed_at = observation_time(observed_at)
    source_url = source_url.strip()
    if source_url:
        normalize_url(source_url)
    if len(description) > 2000:
        raise ValueError("Evidence description exceeds 2,000 characters.")
    identifier = uuid4().hex
    extension = "png" if fmt == "PNG" else "jpg"
    filename = f"{identifier}.{extension}"
    metadata = dict(evidence_id=identifier, case_id=case_id, filename=filename,
                    original_name=original_name, mime_type=f"image/{'png' if fmt == 'PNG' else 'jpeg'}",
                    size_bytes=len(content), sha256=sha256(content).hexdigest(), source_url=source_url,
                    observed_at=observed_at, uploaded_at=utc_now(), description=description.strip())
    root = Path(directory)
    root.mkdir(parents=True, exist_ok=True)
    path = evidence_path(root, filename)
    with path.open("xb") as target:
        target.write(content)
    try:
        db.add_evidence_metadata(metadata)
    except Exception:
        path.unlink(missing_ok=True)
        raise
    return metadata
