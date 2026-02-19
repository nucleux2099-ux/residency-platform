from __future__ import annotations

import hashlib
import mimetypes
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.services.event_store import read_events

PATIENT_COLLECTION_ROOTS: list[tuple[str, Path, str]] = [
    ("active", Path("02-Data-Collection") / "Active-Cases", "Active Cases"),
    ("completed", Path("02-Data-Collection") / "Completed-Cases", "Completed Cases"),
]
TEXT_EXTENSIONS = {".md", ".txt", ".csv", ".json", ".yaml", ".yml"}
SKIP_TOP_LEVEL_DIRS = {"inbox"}

LAB_KEYWORDS = {
    "lab",
    "hemat",
    "biochem",
    "bacter",
    "myco",
    "coag",
    "virol",
    "blood",
    "patholog",
    "cytolog",
    "drf",
    "bgt",
    "hpe",
    "urine",
    "parasit",
    "immun",
}
IMAGING_KEYWORDS = {"ct", "mri", "mrcp", "ncct", "cect", "usg", "imaging", "scan", "loopogram"}
DISCHARGE_KEYWORDS = {"discharge", "death summary", "handover"}

STUDY_ID_PATTERNS = [
    re.compile(r"\*\*study\s*id\*\*\s*:\s*`?([A-Za-z0-9\-]+)`?", flags=re.IGNORECASE),
    re.compile(r"study\s*id\s*:\s*`?([A-Za-z0-9\-]+)`?", flags=re.IGNORECASE),
]


def _parse_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value

    text = str(value).strip()
    if not text:
        return None

    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _parse_date(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if "T" in text:
        text = text.split("T", 1)[0]
    return text


def _safe_path_key(path: Path) -> str:
    return path.as_posix().strip().lower()


def _slugify(value: str) -> str:
    token = re.sub(r"[^a-zA-Z0-9]+", "-", value).strip("-").lower()
    return token or "patient"


def _patient_key(relative_folder: Path) -> str:
    payload = relative_folder.as_posix().lower().encode("utf-8")
    digest = hashlib.sha1(payload).hexdigest()[:10]
    return f"{_slugify(relative_folder.name)}-{digest}"


def _file_id(relative_path: Path) -> str:
    payload = relative_path.as_posix().lower().encode("utf-8")
    return hashlib.sha1(payload).hexdigest()[:12]


def _is_hidden(path: Path) -> bool:
    return any(part.startswith(".") for part in path.parts)


def _directory_has_visible_files(path: Path) -> bool:
    try:
        for child in path.iterdir():
            if child.name.startswith("."):
                continue
            if child.is_file():
                return True
    except OSError:
        return False
    return False


def _iter_patient_directories(collection_root: Path, root_label: str) -> list[tuple[str, Path]]:
    patient_entries: list[tuple[str, Path]] = []

    try:
        top_level_dirs = sorted(
            [path for path in collection_root.iterdir() if path.is_dir() and not path.name.startswith(".")],
            key=lambda path: path.name.lower(),
        )
    except OSError:
        return patient_entries

    for top_level in top_level_dirs:
        if top_level.name.lower() in SKIP_TOP_LEVEL_DIRS:
            continue

        try:
            nested_dirs = sorted(
                [path for path in top_level.iterdir() if path.is_dir() and not path.name.startswith(".")],
                key=lambda path: path.name.lower(),
            )
        except OSError:
            nested_dirs = []

        if nested_dirs:
            nested_patient_dirs = [nested for nested in nested_dirs if _directory_has_visible_files(nested)]
            if nested_patient_dirs:
                for nested in nested_patient_dirs:
                    if nested.name.lower() in SKIP_TOP_LEVEL_DIRS:
                        continue
                    patient_entries.append((top_level.name, nested))
                continue

        has_files = _directory_has_visible_files(top_level)
        if has_files or not nested_dirs:
            patient_entries.append((root_label, top_level))
            continue

        for nested in nested_dirs:
            if nested.name.lower() in SKIP_TOP_LEVEL_DIRS:
                continue
            patient_entries.append((top_level.name, nested))

    return patient_entries


def _infer_svt_status(folder_name: str) -> str:
    lowered = folder_name.lower()
    if "without svt" in lowered:
        return "without_svt"
    if "with svt" in lowered:
        return "with_svt"
    return "unknown"


def _classify_file(filename: str, extension: str) -> str:
    lowered = filename.lower()

    if "patient-proforma" in lowered:
        return "proforma"
    if extension in TEXT_EXTENSIONS:
        return "note"

    if any(token in lowered for token in DISCHARGE_KEYWORDS):
        return "discharge"
    if any(token in lowered for token in IMAGING_KEYWORDS):
        return "imaging"
    if any(token in lowered for token in LAB_KEYWORDS):
        return "lab_report"

    return "attachment"


def _extract_source_folder(payload: dict[str, Any]) -> Path | None:
    extra_fields = payload.get("extra_fields")
    if isinstance(extra_fields, dict):
        source_path = extra_fields.get("source_proforma_path")
        if isinstance(source_path, str) and source_path.strip():
            return Path(source_path.strip()).parent

    source_files = payload.get("source_files")
    if isinstance(source_files, list) and source_files:
        first = source_files[0]
        if isinstance(first, str) and first.strip():
            return Path(first.strip()).parent

    return None


def _event_summary(event: dict[str, Any]) -> dict[str, Any] | None:
    payload = event.get("payload")
    if not isinstance(payload, dict):
        return None

    patient_id = str(payload.get("patient_id", "")).strip().upper()
    if not patient_id:
        return None

    source_folder = _extract_source_folder(payload)

    return {
        "patient_id": patient_id,
        "diagnosis": str(payload.get("diagnosis", "")).strip() or None,
        "cohort_status": str(payload.get("cohort_status", "")).strip() or None,
        "visit_type": str(payload.get("visit_type", "")).strip() or None,
        "svt_status": str(payload.get("svt_status", "")).strip() or None,
        "encounter_date": _parse_date(payload.get("encounter_date")),
        "updated_at": (_parse_datetime(event.get("created_at")) or datetime.now(timezone.utc)).isoformat(),
        "template_id": str(payload.get("template_id", "")).strip() or None,
        "ward": str(payload.get("ward", "")).strip() or None,
        "source_folder_key": _safe_path_key(source_folder) if source_folder else None,
    }


def _event_sort_key(event: dict[str, Any]) -> tuple[str, str]:
    return (str(event.get("encounter_date") or ""), str(event.get("updated_at") or ""))


def _build_event_context(event_store_path: Path) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]], dict[str, list[dict[str, Any]]]]:
    events = read_events(event_store_path)
    latest_by_patient: dict[str, dict[str, Any]] = {}
    latest_by_folder: dict[str, dict[str, Any]] = {}
    history_by_patient: dict[str, list[dict[str, Any]]] = {}

    for event in events:
        summary = _event_summary(event)
        if summary is None:
            continue

        patient_id = str(summary["patient_id"])
        source_folder_key = summary.get("source_folder_key")

        history_item = {key: value for key, value in summary.items() if key != "source_folder_key"}
        history_by_patient.setdefault(patient_id, []).append(history_item)

        previous_patient = latest_by_patient.get(patient_id)
        if previous_patient is None or _event_sort_key(summary) >= _event_sort_key(previous_patient):
            latest_by_patient[patient_id] = summary

        if source_folder_key:
            previous_folder = latest_by_folder.get(source_folder_key)
            if previous_folder is None or _event_sort_key(summary) >= _event_sort_key(previous_folder):
                latest_by_folder[source_folder_key] = summary

    for items in history_by_patient.values():
        items.sort(key=_event_sort_key, reverse=True)

    return latest_by_patient, latest_by_folder, history_by_patient


def _extract_study_id_from_text(content: str) -> str | None:
    for pattern in STUDY_ID_PATTERNS:
        match = pattern.search(content)
        if match:
            return match.group(1).strip().upper()
    return None


def _read_study_id(patient_dir: Path) -> str | None:
    text_files = sorted([path for path in patient_dir.glob("*.md") if path.is_file()], key=lambda path: path.name.lower())

    for path in text_files:
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        study_id = _extract_study_id_from_text(content)
        if study_id:
            return study_id

    return None


def _collect_files(vault_root: Path, patient_dir: Path) -> list[dict[str, Any]]:
    files: list[dict[str, Any]] = []

    try:
        candidates = sorted(patient_dir.rglob("*"), key=lambda path: (path.is_dir(), path.name.lower()))
    except OSError:
        return files

    for path in candidates:
        if not path.is_file():
            continue

        try:
            relative_path = path.relative_to(vault_root)
        except ValueError:
            continue

        if _is_hidden(relative_path):
            continue

        extension = path.suffix.lower()
        mime_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        category = _classify_file(path.name, extension)

        try:
            stat = path.stat()
            size_bytes = stat.st_size
            updated_at = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat()
        except OSError:
            size_bytes = 0
            updated_at = None

        files.append(
            {
                "file_id": _file_id(relative_path),
                "file_name": path.name,
                "relative_path": relative_path.as_posix(),
                "extension": extension,
                "mime_type": mime_type,
                "category": category,
                "size_bytes": size_bytes,
                "updated_at": updated_at,
                "is_text": extension in TEXT_EXTENSIONS,
            }
        )

    files.sort(key=lambda item: (str(item.get("category") or ""), str(item.get("file_name") or "").lower()))
    return files


def _build_patient_record(
    vault_root: Path,
    case_bucket: str,
    cohort_label: str,
    patient_dir: Path,
    latest_by_patient: dict[str, dict[str, Any]],
    latest_by_folder: dict[str, dict[str, Any]],
    history_by_patient: dict[str, list[dict[str, Any]]],
) -> dict[str, Any] | None:
    try:
        relative_patient_dir = patient_dir.relative_to(vault_root)
    except ValueError:
        return None

    patient_key = _patient_key(relative_patient_dir)
    folder_key = _safe_path_key(relative_patient_dir)
    files = _collect_files(vault_root, patient_dir)

    note_files = [item for item in files if item["category"] in {"note", "proforma"}]
    lab_files = [item for item in files if item["category"] == "lab_report"]

    derived_study_id = _read_study_id(patient_dir)
    linked_event = latest_by_folder.get(folder_key)
    if linked_event is None and derived_study_id:
        linked_event = latest_by_patient.get(derived_study_id)

    study_id = str((linked_event or {}).get("patient_id") or derived_study_id or "").strip().upper() or None

    last_updated_candidates = [item.get("updated_at") for item in files if item.get("updated_at")]
    if linked_event and linked_event.get("updated_at"):
        last_updated_candidates.append(str(linked_event["updated_at"]))
    last_updated = max(last_updated_candidates) if last_updated_candidates else None

    selected_note_id = None
    if note_files:
        preferred = next((item for item in note_files if item["category"] == "proforma"), note_files[0])
        selected_note_id = preferred["file_id"]

    patient_card = {
        "patient_key": patient_key,
        "display_name": patient_dir.name,
        "study_id": study_id,
        "svt_status": _infer_svt_status(cohort_label),
        "cohort_folder": cohort_label,
        "case_bucket": case_bucket,
        "folder_path": relative_patient_dir.as_posix(),
        "diagnosis": (linked_event or {}).get("diagnosis"),
        "cohort_status": (linked_event or {}).get("cohort_status"),
        "latest_visit": (linked_event or {}).get("visit_type"),
        "last_encounter_date": (linked_event or {}).get("encounter_date"),
        "last_updated_at": last_updated,
        "template_id": (linked_event or {}).get("template_id"),
        "ward": (linked_event or {}).get("ward"),
        "file_count": len(files),
        "note_count": len(note_files),
        "lab_report_count": len(lab_files),
        "attachment_count": len([item for item in files if item["category"] == "attachment"]),
        "selected_note_file_id": selected_note_id,
    }

    history = history_by_patient.get(study_id or "", [])

    return {
        "patient": patient_card,
        "files": files,
        "notes": note_files,
        "lab_reports": lab_files,
        "event_history": history,
    }


def build_patient_catalog(vault_root: Path, event_store_path: Path) -> list[dict[str, Any]]:
    latest_by_patient, latest_by_folder, history_by_patient = _build_event_context(event_store_path)
    records: list[dict[str, Any]] = []

    for case_bucket, relative_root, root_label in PATIENT_COLLECTION_ROOTS:
        collection_root = (vault_root / relative_root).resolve()
        if not collection_root.exists() or not collection_root.is_dir():
            continue

        patient_entries = _iter_patient_directories(collection_root, root_label)
        for cohort_label, patient_dir in patient_entries:
            record = _build_patient_record(
                vault_root=vault_root,
                case_bucket=case_bucket,
                cohort_label=cohort_label,
                patient_dir=patient_dir,
                latest_by_patient=latest_by_patient,
                latest_by_folder=latest_by_folder,
                history_by_patient=history_by_patient,
            )
            if record is not None:
                records.append(record)

    records.sort(
        key=lambda item: (
            str(item["patient"].get("last_updated_at") or ""),
            str(item["patient"].get("display_name") or "").lower(),
        ),
        reverse=True,
    )
    return records


def list_patient_cards(
    vault_root: Path,
    event_store_path: Path,
    query: str | None,
    svt_status: str | None,
    case_bucket: str | None,
    limit: int,
) -> list[dict[str, Any]]:
    records = build_patient_catalog(vault_root, event_store_path)
    cards = [record["patient"] for record in records]

    query_token = (query or "").strip().lower()
    if query_token:
        cards = [
            card
            for card in cards
            if query_token
            in " ".join(
                [
                    str(card.get("display_name") or "").lower(),
                    str(card.get("study_id") or "").lower(),
                    str(card.get("diagnosis") or "").lower(),
                    str(card.get("cohort_folder") or "").lower(),
                ]
            )
        ]

    if svt_status in {"with_svt", "without_svt", "unknown"}:
        cards = [card for card in cards if card.get("svt_status") == svt_status]

    if case_bucket in {"active", "completed"}:
        cards = [card for card in cards if card.get("case_bucket") == case_bucket]

    return cards[: max(1, min(limit, 500))]


def get_patient_detail(vault_root: Path, event_store_path: Path, patient_key: str) -> dict[str, Any] | None:
    target_key = patient_key.strip().lower()
    if not target_key:
        return None

    records = build_patient_catalog(vault_root, event_store_path)
    for record in records:
        if str(record["patient"].get("patient_key", "")).lower() == target_key:
            return record

    return None


def resolve_patient_file(
    vault_root: Path,
    event_store_path: Path,
    patient_key: str,
    file_id: str,
) -> tuple[Path, dict[str, Any]] | None:
    detail = get_patient_detail(vault_root, event_store_path, patient_key)
    if detail is None:
        return None

    normalized_file_id = file_id.strip().lower()
    for file_item in detail.get("files", []):
        if str(file_item.get("file_id", "")).lower() != normalized_file_id:
            continue

        relative_text = str(file_item.get("relative_path", "")).strip()
        if not relative_text:
            continue

        candidate = (vault_root / relative_text).resolve()
        root = vault_root.resolve()
        if not candidate.exists() or not candidate.is_file():
            continue
        if not candidate.is_relative_to(root):
            continue

        return candidate, file_item

    return None


def read_patient_file_preview(
    vault_root: Path,
    event_store_path: Path,
    patient_key: str,
    file_id: str,
    max_chars: int = 120000,
) -> dict[str, Any] | None:
    resolved = resolve_patient_file(vault_root, event_store_path, patient_key, file_id)
    if resolved is None:
        return None

    path, file_item = resolved
    if not bool(file_item.get("is_text")):
        return {
            "file": file_item,
            "preview_supported": False,
            "content": "",
            "truncated": False,
            "message": "Preview is available for text notes only. Use inline viewer for PDF/image attachments.",
        }

    try:
        content = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {
            "file": file_item,
            "preview_supported": False,
            "content": "",
            "truncated": False,
            "message": "Unable to open the selected note file.",
        }

    truncated = len(content) > max_chars
    if truncated:
        content = content[:max_chars]

    return {
        "file": file_item,
        "preview_supported": True,
        "content": content,
        "truncated": truncated,
        "message": None,
    }
