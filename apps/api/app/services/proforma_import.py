from __future__ import annotations

import re
from datetime import date, datetime
from pathlib import Path
from typing import Iterable

from app.schemas.patient import PatientSubmission, ProformaImportAck, ProformaImportError
from app.services.event_store import append_submission, read_events
from app.services.note_writer import write_patient_note
from app.services.patient_validator import validate_submission_against_template
from app.services.template_registry import get_template

PROFORMA_GLOBS = [
    "02-Data-Collection/Active-Cases/**/Patient-Proforma-*.md",
    "04-Print-Ready/Proforma-Sheets/**/*.md",
]

DATE_FORMATS = [
    "%d-%B-%Y",
    "%d-%b-%Y",
    "%d-%m-%Y",
    "%Y-%m-%d",
]

KEY_VALUE_PATTERN = re.compile(r"^\*\*(.+?)\*\*:\s*(.+)$")


def _sanitize_key(raw: str) -> str:
    token = raw.strip().lower()
    token = re.sub(r"\*\*|`", "", token)
    token = re.sub(r"[^a-z0-9]+", "_", token)
    token = re.sub(r"(^|_)\d+_", r"\1", token)
    return token.strip("_")


def _clean_value(raw: str) -> str:
    text = raw.strip()
    text = re.sub(r"\*\*", "", text)
    return text.strip()


def _split_table_row(line: str) -> list[str]:
    return [part.strip() for part in line.strip().strip("|").split("|")]


def _is_separator_row(line: str) -> bool:
    token = line.strip()
    if not token.startswith("|"):
        return False
    allowed = {"|", "-", ":", " "}
    return set(token).issubset(allowed)


def _relative_path(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def _parse_best_date(raw: str | None) -> date | None:
    if not raw:
        return None

    candidates: list[str] = []
    for token in re.findall(r"\d{1,2}[-/](?:[A-Za-z]{3,10}|\d{1,2})[-/]\d{2,4}", raw):
        candidates.append(token)
    if re.match(r"^\d{4}-\d{2}-\d{2}$", raw.strip()):
        candidates.insert(0, raw.strip())
    if not candidates:
        candidates = [raw.strip()]

    for candidate in candidates:
        normalized = candidate.replace("/", "-").strip()
        for fmt in DATE_FORMATS:
            try:
                parsed = datetime.strptime(normalized, fmt).date()
                if parsed.year < 100:
                    parsed = parsed.replace(year=parsed.year + 2000)
                return parsed
            except ValueError:
                continue
    return None


def _extract_heading_block(text: str, heading: str) -> str:
    match = re.search(
        rf"{re.escape(heading)}\s*(.*?)(?=\n## |\n### |\n#### |\Z)",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not match:
        return ""
    return match.group(1).strip()


def _extract_study_id(text: str, fallback_path: Path) -> str:
    match = re.search(r"\*\*Study ID:\*\*\s*`?([A-Za-z0-9][A-Za-z0-9\-_/]*)`?", text, flags=re.IGNORECASE)
    if match:
        value = match.group(1).strip().upper().replace("/", "-")
        value = re.sub(r"[^A-Z0-9-]", "-", value)
        value = re.sub(r"-{2,}", "-", value).strip("-")
        if len(value) >= 3:
            return value

    stem = fallback_path.stem.upper()
    stem = re.sub(r"[^A-Z0-9]+", "-", stem)
    stem = re.sub(r"-{2,}", "-", stem).strip("-")
    return f"AUTO-{stem[-20:]}" if stem else f"AUTO-{abs(hash(str(fallback_path))) % 10_000_000:07d}"


def _detect_svt_status(text: str, path: Path) -> str:
    path_text = str(path).lower()
    if "without svt" in path_text or "non-svt" in path_text:
        return "without_svt"
    if "with svt" in path_text:
        return "with_svt"

    if re.search(r"\bnon[- ]svt\b", text, flags=re.IGNORECASE):
        return "without_svt"
    if re.search(r"\bsvt case\b", text, flags=re.IGNORECASE):
        return "with_svt"
    if re.search(r"\bvenous\s*-\s*thrombosis:\s*\[x\]\s*yes", text, flags=re.IGNORECASE):
        return "with_svt"

    return "without_svt"


def _detect_vessels(text: str, svt_status: str) -> list[str]:
    if svt_status != "with_svt":
        return []

    vessels: list[str] = []
    checks = [
        ("sv", r"(splenic vein|sv).*?(thromb|occlud|blocked|yes)"),
        ("pv", r"(portal vein|pv).*?(thromb|occlud|blocked|yes)"),
        ("smv", r"(superior mesenteric vein|smv).*?(thromb|occlud|blocked|yes)"),
    ]
    negative_tokens = ("no thromb", "patent", "[ ] yes")

    for vessel, pattern in checks:
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            start = max(0, match.start() - 40)
            end = min(len(text), match.end() + 60)
            snippet = text[start:end].lower()
            if any(token in snippet for token in negative_tokens):
                continue
            if vessel not in vessels:
                vessels.append(vessel)
            break

    if not vessels:
        return ["unknown"]
    return vessels


def _detect_mortality(text: str) -> tuple[str, date | None, str | None]:
    block = _extract_heading_block(text, "### Mortality")
    normalized = block.lower()

    if "[x] yes" in normalized:
        mortality = "yes"
    elif "[x] no" in normalized:
        mortality = "no"
    else:
        mortality = "no"

    death_date = None
    cause = None
    if mortality == "yes":
        date_match = re.search(r"(date|died|death).{0,20}:\s*([^\n]+)", block, flags=re.IGNORECASE)
        cause_match = re.search(r"(cause|reason).{0,20}:\s*([^\n]+)", block, flags=re.IGNORECASE)
        if date_match:
            death_date = _parse_best_date(date_match.group(2))
        if cause_match:
            cause = _clean_value(cause_match.group(2))
    return mortality, death_date, cause


def _detect_recanalization_status(text: str, svt_status: str) -> str:
    if svt_status != "with_svt":
        return "not_applicable"

    lowered = text.lower()
    if "partial recanal" in lowered:
        return "partial"
    if "complete recanal" in lowered or "full recanal" in lowered:
        return "complete"
    if "progressed" in lowered or "progression" in lowered:
        return "progressed"
    if "chronic occlusion" in lowered or "persistent thromb" in lowered or "occluded" in lowered:
        return "none"
    return "pending"


def _detect_primary_endpoint(text: str) -> bool:
    lowered = text.lower()
    if "primary endpoint complete" in lowered and "yes" in lowered:
        return True
    if "3 month follow-up" in lowered or "month3 follow-up" in lowered:
        return True
    return False


def _extract_assessment_type(text: str) -> str:
    match = re.search(r"\*\*Assessment Type:\*\*\s*([^\n]+)", text, flags=re.IGNORECASE)
    if not match:
        return "baseline"
    token = match.group(1).strip().lower()
    if "discharge" in token:
        return "discharge"
    if "month 3" in token or "3 month" in token:
        return "month3_followup"
    if "month 1" in token or "1 month" in token:
        return "month1_followup"
    if "week 2" in token or "2 week" in token:
        return "week2_followup"
    if "day 7" in token:
        return "day7_reassessment"
    return "baseline"


def _extract_extra_fields(text: str) -> dict[str, str]:
    lines = text.splitlines()
    extra: dict[str, str] = {}
    section_path: list[str] = []

    idx = 0
    while idx < len(lines):
        line = lines[idx].rstrip()
        stripped = line.strip()

        if stripped.startswith("#"):
            level = len(stripped) - len(stripped.lstrip("#"))
            title = stripped[level:].strip()
            if title:
                section_path = section_path[: max(level - 2, 0)]
                section_path.append(title)
            idx += 1
            continue

        kv_match = KEY_VALUE_PATTERN.match(stripped)
        if kv_match:
            key_parts = section_path + [kv_match.group(1)]
            key = _sanitize_key("__".join(key_parts))
            value = _clean_value(kv_match.group(2))
            if key and value:
                extra.setdefault(key, value)
            idx += 1
            continue

        if stripped.startswith("|") and idx + 1 < len(lines) and _is_separator_row(lines[idx + 1]):
            idx += 2
            row_index = 1
            while idx < len(lines) and lines[idx].strip().startswith("|"):
                cols = _split_table_row(lines[idx])
                if len(cols) >= 2:
                    row_key = cols[0] if cols[0] else f"row_{row_index}"
                    row_value = _clean_value(" | ".join(cols[1:]))
                    if row_value and row_value != "-":
                        key = _sanitize_key("__".join(section_path + [row_key]))
                        if key:
                            extra.setdefault(key, row_value)
                row_index += 1
                idx += 1
            continue

        idx += 1

    return extra


def _pick_first(extra: dict[str, str], contains: Iterable[str], default: str = "") -> str:
    lowered = [token.lower() for token in contains]
    for key, value in extra.items():
        key_lower = key.lower()
        if all(token in key_lower for token in lowered):
            return value
    return default


def parse_proforma_file(path: Path, vault_root: Path, template_id: str = "patient-proforma-v3") -> PatientSubmission:
    text = path.read_text(encoding="utf-8")
    extracted = _extract_extra_fields(text)

    patient_id = _extract_study_id(text, path)
    record_date = _parse_best_date(re.search(r"\*\*Date:\*\*\s*([^\n]+)", text, flags=re.IGNORECASE).group(1)) if re.search(r"\*\*Date:\*\*\s*([^\n]+)", text, flags=re.IGNORECASE) else None
    if record_date is None:
        record_date = datetime.fromtimestamp(path.stat().st_mtime).date()

    svt_status = _detect_svt_status(text, path)
    vessel_involvement = _detect_vessels(text, svt_status)
    mortality, death_date, cause_of_death = _detect_mortality(text)
    recanalization_status = _detect_recanalization_status(text, svt_status)
    endpoint_complete = _detect_primary_endpoint(text)

    path_lower = str(path).lower()
    if mortality == "yes":
        cohort_status = "terminal_outcome"
    elif "04-print-ready/proforma-sheets" in path_lower:
        cohort_status = "completed"
    else:
        cohort_status = "active"

    ward = _pick_first(extracted, ("opd", "ipd"), default="Gastro Surgery Ward")
    diagnosis = _pick_first(extracted, ("etiology",), default="Acute Pancreatitis")
    summary_block = _extract_heading_block(text, "## Summary")
    notes = "Imported from vault proforma sheet."
    if summary_block:
        notes = f"{notes}\n\n{summary_block[:2400]}"

    relative_source = _relative_path(path, vault_root)
    extracted["source_proforma_path"] = relative_source

    payload = {
        "template_id": template_id,
        "patient_id": patient_id,
        "encounter_date": record_date.isoformat(),
        "diagnosis": diagnosis[:200],
        "visit_type": _extract_assessment_type(text),
        "svt_status": svt_status,
        "ward": ward[:120] if ward else "Gastro Surgery Ward",
        "cohort_status": cohort_status,
        "vessel_involvement": vessel_involvement,
        "mortality": mortality,
        "death_date": death_date.isoformat() if death_date else None,
        "cause_of_death": cause_of_death,
        "recanalization_status": recanalization_status,
        "primary_endpoint_complete": endpoint_complete,
        "notes": notes,
        "extra_fields": extracted,
        "source_files": [relative_source],
    }

    return PatientSubmission.model_validate(payload)


def import_vault_proformas(
    vault_root: Path,
    event_store_path: Path,
    templates_dir: Path,
    notes_root: Path,
    template_id: str = "patient-proforma-v3",
) -> ProformaImportAck:
    template = get_template(templates_dir, template_id)
    if template is None:
        raise ValueError(f"Template not found: {template_id}")

    files: list[Path] = []
    for pattern in PROFORMA_GLOBS:
        files.extend(vault_root.glob(pattern))
    unique_files = sorted(set(files), key=lambda item: str(item).lower())

    existing_events = read_events(event_store_path)
    existing_sources: set[str] = set()
    existing_keys: set[tuple[str, str, str]] = set()

    for event in existing_events:
        payload = event.get("payload")
        if not isinstance(payload, dict):
            continue
        for source in payload.get("source_files", []) or []:
            existing_sources.add(str(source))
        patient_id = str(payload.get("patient_id", "")).strip().upper()
        encounter_date = str(payload.get("encounter_date", "")).strip()
        visit_type = str(payload.get("visit_type", "")).strip()
        if patient_id and encounter_date and visit_type:
            existing_keys.add((patient_id, encounter_date, visit_type))

    event_ids: list[str] = []
    note_paths: list[str] = []
    errors: list[ProformaImportError] = []
    skipped = 0

    for file_path in unique_files:
        rel_path = _relative_path(file_path, vault_root)
        if rel_path in existing_sources:
            skipped += 1
            continue

        try:
            submission = parse_proforma_file(file_path, vault_root, template_id=template_id)
        except Exception as exc:  # noqa: BLE001
            errors.append(ProformaImportError(file_path=rel_path, message=f"Parse failed: {exc}"))
            continue

        key = (submission.patient_id, submission.encounter_date.isoformat(), submission.visit_type)
        if key in existing_keys:
            skipped += 1
            continue

        template_errors = validate_submission_against_template(submission, template)
        if template_errors:
            errors.append(ProformaImportError(file_path=rel_path, message="; ".join(template_errors)))
            continue

        event_id = append_submission(event_store_path, submission)
        note_path = write_patient_note(notes_root, vault_root, submission, event_id)
        event_ids.append(event_id)
        note_paths.append(str(note_path))

        existing_sources.add(rel_path)
        existing_keys.add(key)

    return ProformaImportAck(
        scanned_files=len(unique_files),
        imported_files=len(event_ids),
        skipped_files=skipped,
        event_ids=event_ids,
        note_paths=note_paths,
        errors=errors,
    )
