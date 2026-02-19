import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from app.schemas.patient import PatientSubmission


def _ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def append_submission(path: Path, submission: PatientSubmission) -> str:
    _ensure_parent(path)
    event_id = f"evt_{uuid4().hex}"
    record = {
        "event_id": event_id,
        "event_type": "patient_submission",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "payload": submission.model_dump(mode="json"),
    }

    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=True) + "\n")

    return event_id


def read_events(path: Path) -> list[dict]:
    if not path.exists():
        return []

    events: list[dict] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    return events
