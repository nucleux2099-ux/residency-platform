import re
from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile

from app.schemas.patient import UploadedFileDescriptor

SAFE_TEXT_PATTERN = re.compile(r"[^A-Za-z0-9_.-]+")


def _sanitize(value: str) -> str:
    cleaned = SAFE_TEXT_PATTERN.sub("_", value.strip())
    return cleaned.strip("._") or "unknown"


def _sanitize_filename(file_name: str) -> str:
    if not file_name:
        return "upload.bin"

    base = Path(file_name).name
    return _sanitize(base)


async def save_uploads(
    uploads_root: Path,
    files: list[UploadFile],
    patient_id: str | None,
) -> list[UploadedFileDescriptor]:
    target = uploads_root / (_sanitize(patient_id) if patient_id else "unassigned")
    target.mkdir(parents=True, exist_ok=True)

    uploaded: list[UploadedFileDescriptor] = []

    for incoming in files:
        original_name = _sanitize_filename(incoming.filename or "upload.bin")
        stored_name = f"{uuid4().hex}_{original_name}"
        destination = target / stored_name

        content = await incoming.read()
        destination.write_bytes(content)

        uploaded.append(
            UploadedFileDescriptor(
                file_name=original_name,
                stored_path=str(destination),
                size_bytes=len(content),
            )
        )

    return uploaded
