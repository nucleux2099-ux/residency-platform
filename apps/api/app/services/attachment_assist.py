from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.services.patient_document_index import (
    FILE_DATE_PATTERNS,
    LAB_TREND_METRICS,
    MARKER_SUPPORTED_EXTENSIONS,
    NUMBER_PATTERN,
    TEXT_EXTENSIONS,
    get_patient_document_indexer,
)

IMAGING_MODALITY_RULES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\b(?:mri|mrcp)\b", flags=re.IGNORECASE), "MRI/MRCP"),
    (re.compile(r"\b(?:cect|ncct|ct)\b", flags=re.IGNORECASE), "CT"),
    (re.compile(r"\b(?:usg|ultrasound|sonography)\b", flags=re.IGNORECASE), "USG"),
    (re.compile(r"\b(?:doppler|duplex)\b", flags=re.IGNORECASE), "Doppler"),
    (re.compile(r"\b(?:endoscopy|egd)\b", flags=re.IGNORECASE), "Endoscopy"),
]

IMAGING_FINDING_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\b(?:thromb|occlu|non[-\s]?opaci|filling defect)\b", flags=re.IGNORECASE),
    re.compile(r"\b(?:portal vein|splenic vein|smv|superior mesenteric vein|sv)\b", flags=re.IGNORECASE),
    re.compile(r"\b(?:ascites|splenomegaly|varices|collateral|portal hypertension)\b", flags=re.IGNORECASE),
    re.compile(r"\b(?:necrosis|pseudocyst|won|fluid collection|pseudoaneurysm|infarction)\b", flags=re.IGNORECASE),
]

CTSI_PATTERN = re.compile(
    r"(?:modified\s*(?:ctsi|ct\s*severity\s*index)|ctsi)\s*[:=-]?\s*(?P<value>\d{1,2}(?:\.\d+)?)",
    flags=re.IGNORECASE,
)
DATE_PATTERN = re.compile(
    r"(?<!\d)(?P<day>\d{1,2})[/-](?P<month>\d{1,2})[/-](?P<year>20\d{2})(?!\d)|"
    r"(?<!\d)(?P<year2>20\d{2})[/-](?P<month2>\d{1,2})[/-](?P<day2>\d{1,2})(?!\d)"
)


def _read_text_with_indexer(path: Path, max_chars: int) -> tuple[str | None, str, str | None]:
    extension = path.suffix.lower()
    file_item = {
        "extension": extension,
        "is_text": extension in TEXT_EXTENSIONS,
    }

    indexer = get_patient_document_indexer()
    if indexer is None:
        return None, "none", "Document indexer not initialized"

    text, extractor, error = indexer._extract_document_text(path, file_item)  # type: ignore[attr-defined]
    if text:
        return text[:max_chars], extractor, None
    return None, extractor, error or "Text extraction failed"


def _extract_date_from_name_or_text(file_name: str, text: str) -> str:
    for pattern in FILE_DATE_PATTERNS:
        match = pattern.search(file_name)
        if not match:
            continue
        try:
            year = int(match.group("year"))
            month = int(match.group("month"))
            day = int(match.group("day"))
            parsed = datetime(year=year, month=month, day=day, tzinfo=timezone.utc).date()
            return parsed.isoformat()
        except (TypeError, ValueError):
            continue

    for match in DATE_PATTERN.finditer(text):
        try:
            if match.group("year2"):
                year = int(match.group("year2"))
                month = int(match.group("month2"))
                day = int(match.group("day2"))
            else:
                year = int(match.group("year"))
                month = int(match.group("month"))
                day = int(match.group("day"))
            parsed = datetime(year=year, month=month, day=day, tzinfo=timezone.utc).date()
            return parsed.isoformat()
        except (TypeError, ValueError):
            continue

    return ""


def _parse_number_after_match(line: str, start: int) -> float | None:
    cleaned = line.replace(",", "")
    numbers = list(NUMBER_PATTERN.finditer(cleaned))
    if not numbers:
        return None

    ordered = [match for match in numbers if match.start() >= start] or numbers
    for match in ordered:
        token = match.group(0)
        try:
            value = float(token)
        except ValueError:
            continue
        if abs(value) > 100000:
            continue
        return round(value, 2)

    return None


def _extract_first_non_empty_line(text: str, max_chars: int = 180) -> str:
    for line in text.splitlines():
        cleaned = " ".join(line.split()).strip()
        if cleaned:
            return cleaned[:max_chars]
    return ""


def _parse_lab_entries(text: str, file_name: str) -> tuple[list[dict[str, str]], list[str]]:
    date_value = _extract_date_from_name_or_text(file_name, text)
    rows: list[dict[str, str]] = []
    seen_keys: set[str] = set()

    for metric in LAB_TREND_METRICS:
        label = str(metric.get("label") or metric.get("metric_key") or "Lab Metric")
        unit = str(metric.get("unit") or "").strip()
        patterns = metric.get("patterns") or []
        metric_key = str(metric.get("metric_key") or label).lower()
        found_value: float | None = None

        for raw_line in text.splitlines():
            line = " ".join(raw_line.split()).strip()
            if not line:
                continue

            for pattern in patterns:
                if not isinstance(pattern, re.Pattern):
                    continue
                match = pattern.search(line)
                if match is None:
                    continue

                parsed = _parse_number_after_match(line, match.end())
                if parsed is None:
                    continue
                found_value = parsed
                break

            if found_value is not None:
                break

        if found_value is None:
            continue

        signature = f"{metric_key}:{found_value}"
        if signature in seen_keys:
            continue
        seen_keys.add(signature)

        rows.append(
            {
                "date": date_value,
                "parameter": label,
                "value": f"{found_value:g}{f' {unit}' if unit else ''}",
            }
        )

    notes: list[str] = []
    if rows:
        notes.append(f"Auto-filled {len(rows)} laboratory values from OCR.")
    else:
        notes.append("No structured laboratory values detected from this attachment.")

    return rows[:18], notes


def _detect_modality(file_name: str, text: str) -> str:
    blob = f"{file_name}\n{text[:2500]}"
    for pattern, label in IMAGING_MODALITY_RULES:
        if pattern.search(blob):
            return label
    return "Imaging"


def _collect_imaging_findings(text: str, limit: int = 4) -> list[str]:
    findings: list[str] = []
    seen: set[str] = set()

    for raw_line in text.splitlines():
        line = " ".join(raw_line.split()).strip()
        if not line:
            continue
        if len(line) > 260:
            line = f"{line[:257]}..."
        if not any(pattern.search(line) for pattern in IMAGING_FINDING_PATTERNS):
            continue
        key = line.lower()
        if key in seen:
            continue
        seen.add(key)
        findings.append(line)
        if len(findings) >= limit:
            break

    if not findings:
        first = _extract_first_non_empty_line(text, max_chars=220)
        if first:
            findings.append(first)

    return findings


def _build_imaging_extra_fields(text: str) -> dict[str, str]:
    lowered = text.lower()
    extra: dict[str, str] = {}

    def has(*tokens: str) -> bool:
        return all(token in lowered for token in tokens)

    if has("portal vein") and ("thromb" in lowered or "occlu" in lowered):
        extra["splanchnic_venous_assessment__portal_vein_pv"] = "Thrombosis/occlusion suggested on imaging report"
    if ("smv" in lowered or "superior mesenteric vein" in lowered) and ("thromb" in lowered or "occlu" in lowered):
        extra["splanchnic_venous_assessment__smv"] = "Thrombosis/occlusion suggested on imaging report"
    if ("splenic vein" in lowered or re.search(r"\bsv\b", lowered)) and ("thromb" in lowered or "occlu" in lowered):
        extra["splanchnic_venous_assessment__splenic_vein_sv"] = "Thrombosis/occlusion suggested on imaging report"
    if "ascites" in lowered:
        extra["portal_hypertensive_changes__ascites"] = "present on imaging report"
    if "splenomegaly" in lowered:
        extra["portal_hypertensive_changes__splenomegaly"] = "present on imaging report"
    if "varices" in lowered:
        extra["portal_hypertensive_changes__varices"] = "present on imaging report"

    ctsi_match = CTSI_PATTERN.search(text)
    if ctsi_match:
        extra["overall_findings__modified_ctsi"] = ctsi_match.group("value")

    if "pseudocyst" in lowered or "won" in lowered:
        extra["overall_findings__pseudocyst_won"] = "present on imaging report"

    return extra


def _parse_imaging_entries(text: str, file_name: str) -> tuple[list[dict[str, str]], dict[str, str], list[str]]:
    date_value = _extract_date_from_name_or_text(file_name, text)
    modality = _detect_modality(file_name, text)
    findings = _collect_imaging_findings(text)
    extra_fields = _build_imaging_extra_fields(text)

    row: dict[str, str] = {
        "date": date_value,
        "modality": modality,
        "findings": "; ".join(findings[:3]).strip(),
    }

    notes: list[str] = []
    if row["findings"]:
        notes.append("Imaging findings were drafted from OCR text.")
    else:
        notes.append("No structured imaging findings were detected from this attachment.")

    if extra_fields:
        notes.append(f"Suggested {len(extra_fields)} vascular/imaging field updates.")

    return [row], extra_fields, notes


def analyze_ingestion_attachment(
    stored_path: Path,
    original_file_name: str,
    section: str,
    max_chars: int,
) -> dict[str, Any]:
    extension = stored_path.suffix.lower()
    if extension not in TEXT_EXTENSIONS and extension not in MARKER_SUPPORTED_EXTENSIONS:
        return {
            "section": section,
            "extraction_status": "failed",
            "extractor": "unsupported",
            "extraction_error": f"Unsupported file extension: {extension}",
            "extracted_text_preview": "",
            "suggestions": {
                "lab_entries": [],
                "imaging_entries": [],
                "extra_fields": {},
                "review_notes": ["Upload a PDF, image, markdown, or text report for auto-fill."],
            },
        }

    text, extractor, error = _read_text_with_indexer(stored_path, max_chars=max_chars)
    if not text:
        return {
            "section": section,
            "extraction_status": "failed",
            "extractor": extractor,
            "extraction_error": error or "Unable to extract text from uploaded report",
            "extracted_text_preview": "",
            "suggestions": {
                "lab_entries": [],
                "imaging_entries": [],
                "extra_fields": {},
                "review_notes": ["OCR extraction failed. You can still attach this file and enter values manually."],
            },
        }

    lab_entries: list[dict[str, str]] = []
    imaging_entries: list[dict[str, str]] = []
    extra_fields: dict[str, str] = {}
    review_notes: list[str] = []

    normalized_section = section.strip().lower()
    if normalized_section == "lab":
        lab_entries, review_notes = _parse_lab_entries(text, original_file_name)
    elif normalized_section == "imaging":
        imaging_entries, extra_fields, review_notes = _parse_imaging_entries(text, original_file_name)
    else:
        review_notes.append("Section was not recognized for structured auto-fill.")

    review_notes.append("Review and confirm every auto-filled value before final submission.")

    return {
        "section": normalized_section,
        "extraction_status": "ok",
        "extractor": extractor,
        "extraction_error": None,
        "extracted_text_preview": text[:2500],
        "suggestions": {
            "lab_entries": lab_entries,
            "imaging_entries": imaging_entries,
            "extra_fields": extra_fields,
            "review_notes": review_notes,
        },
    }
