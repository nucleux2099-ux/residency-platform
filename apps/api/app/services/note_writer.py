import re
from datetime import datetime, timezone
from pathlib import Path

from app.schemas.patient import PatientSubmission

SAFE_TEXT_PATTERN = re.compile(r"[^A-Za-z0-9_.-]+")


def _sanitize(value: str) -> str:
    cleaned = SAFE_TEXT_PATTERN.sub("_", value.strip())
    return cleaned.strip("._") or "unknown"


def _relative_display_path(path: Path, vault_root: Path) -> str:
    try:
        return str(path.relative_to(vault_root))
    except ValueError:
        return str(path)


def write_patient_note(
    notes_root: Path,
    vault_root: Path,
    submission: PatientSubmission,
    event_id: str,
) -> Path:
    notes_root.mkdir(parents=True, exist_ok=True)

    encounter_date = submission.encounter_date.isoformat()
    safe_patient = _sanitize(submission.patient_id)
    filename = f"{encounter_date}-{safe_patient}-{event_id}.md"
    note_path = notes_root / filename

    created_at = datetime.now(timezone.utc).isoformat()

    source_files = submission.source_files or []
    source_lines = "\n".join(f"- {name}" for name in source_files) if source_files else "- None"
    vessels = ", ".join(submission.vessel_involvement) if submission.vessel_involvement else "None"
    extra_fields = submission.extra_fields or {}
    extra_lines = "\n".join(f"- {key}: {value}" for key, value in sorted(extra_fields.items())) if extra_fields else "- None"

    display_path = _relative_display_path(note_path, vault_root)

    lines = [
        "---",
        'type: "patient-ingestion"',
        f'event_id: "{event_id}"',
        f'patient_id: "{submission.patient_id}"',
        f'encounter_date: "{encounter_date}"',
        f'svt_status: "{submission.svt_status}"',
        f'ward: "{submission.ward}"',
        f'template_id: "{submission.template_id}"',
        f'created_at: "{created_at}"',
        "tags:",
        "  - thesis",
        "  - patient-ingestion",
        "---",
        "",
        f"# Patient Ingestion Log: {submission.patient_id}",
        "",
        "## Summary",
        f"- Event ID: `{event_id}`",
        f"- Encounter Date: {encounter_date}",
        f"- Diagnosis: {submission.diagnosis}",
        f"- Visit Type: {submission.visit_type}",
        f"- Cohort Status: {submission.cohort_status}",
        f"- SVT Status: {submission.svt_status}",
        f"- Vessel Involvement: {vessels}",
        f"- Mortality: {submission.mortality}",
        f"- Recanalization Status: {submission.recanalization_status}",
        f"- Primary Endpoint Complete: {submission.primary_endpoint_complete}",
        f"- Ward: {submission.ward}",
        "",
        "## Notes",
        submission.notes or "No additional notes provided.",
        "",
        "## Proforma Fields",
        extra_lines,
        "",
        "## Source Files",
        source_lines,
        "",
        "## Vault Context",
        "- [[02-Data-Collection]]",
        "- [[05-Logs]]",
        f"- Saved at `{display_path}`",
        "",
    ]

    note_path.write_text("\n".join(lines), encoding="utf-8")
    return note_path
