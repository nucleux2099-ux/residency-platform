from csv import DictReader
from io import StringIO
from pathlib import Path

from pydantic import ValidationError

from app.schemas.patient import CsvIngestionAck, CsvRowError, PatientSubmission
from app.services.event_store import append_submission
from app.services.note_writer import write_patient_note
from app.services.patient_validator import validate_submission_against_template
from app.services.template_registry import get_template

KNOWN_SUBMISSION_KEYS = set(PatientSubmission.model_fields.keys())


def _normalize_csv_row(row: dict[str | None, str | None]) -> dict:
    payload: dict = {}
    extra_fields: dict[str, str] = {}

    for key, value in row.items():
        if key is None:
            continue
        key = key.strip()
        raw = (value or "").strip()
        
        # Skip truly empty keys
        if not key:
            continue
            
        # Treat empty strings as missing/None for optional logic later
        # But we need them to be keys in the dict if we want to pass them to pydantic
        # Pydantic v2 handles missing keys better than empty strings for some types (like Dates)
        if not raw:
            continue

        if key in KNOWN_SUBMISSION_KEYS:
            if key in {"source_files", "vessel_involvement"}:
                payload[key] = [item.strip() for item in raw.split(";") if item.strip()] if raw else []
            elif key == "primary_endpoint_complete":
                # Handle boolean string
                payload[key] = raw.lower() in ("true", "yes", "1", "t")
            elif raw:
                payload[key] = raw
        elif raw:
            extra_fields[key] = raw

    if "template_id" not in payload:
        payload["template_id"] = "patient-proforma-v3"
    
    # Ensure required enum/boolean fields have defaults if missing from CSV
    if "primary_endpoint_complete" not in payload:
        payload["primary_endpoint_complete"] = False
        
    if extra_fields:
        payload["extra_fields"] = extra_fields

    return payload


def ingest_patient_csv(
    csv_bytes: bytes,
    event_store_path: Path,
    templates_dir: Path,
    notes_root: Path,
    vault_root: Path,
) -> CsvIngestionAck:
    text = csv_bytes.decode("utf-8-sig")
    reader = DictReader(StringIO(text))

    errors: list[CsvRowError] = []
    event_ids: list[str] = []
    note_paths: list[str] = []

    total_rows = 0

    for row_number, row in enumerate(reader, start=2):
        payload = _normalize_csv_row(row)

        if not payload or not any(payload.values()):
            continue

        total_rows += 1

        try:
            submission = PatientSubmission.model_validate(payload)
        except ValidationError as exc:
            errors.append(CsvRowError(row_number=row_number, message=str(exc)))
            continue

        template = get_template(templates_dir, submission.template_id)
        if template is None:
            errors.append(
                CsvRowError(
                    row_number=row_number,
                    message=f"Template not found: {submission.template_id}",
                )
            )
            continue

        template_errors = validate_submission_against_template(submission, template)
        if template_errors:
            errors.append(
                CsvRowError(
                    row_number=row_number,
                    message="; ".join(template_errors),
                )
            )
            continue

        event_id = append_submission(event_store_path, submission)
        note_path = write_patient_note(notes_root, vault_root, submission, event_id)
        event_ids.append(event_id)
        note_paths.append(str(note_path))

    accepted_rows = len(event_ids)
    rejected_rows = len(errors)

    return CsvIngestionAck(
        total_rows=total_rows,
        accepted_rows=accepted_rows,
        rejected_rows=rejected_rows,
        event_ids=event_ids,
        note_paths=note_paths,
        errors=errors,
    )
