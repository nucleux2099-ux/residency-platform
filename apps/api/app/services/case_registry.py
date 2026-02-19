from __future__ import annotations

from datetime import date, datetime
from typing import Any


def _parse_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text:
        return None
    if "T" in text:
        text = text.split("T", 1)[0]
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


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


def _summary_from_event(event: dict[str, Any]) -> dict[str, Any] | None:
    payload = event.get("payload")
    if not isinstance(payload, dict):
        return None

    patient_id = str(payload.get("patient_id", "")).strip().upper()
    if not patient_id:
        return None

    encounter = _parse_date(payload.get("encounter_date"))
    created_at = _parse_datetime(event.get("created_at"))

    return {
        "patient_id": patient_id,
        "event_id": str(event.get("event_id", "")),
        "encounter_date": encounter.isoformat() if encounter else None,
        "visit_type": str(payload.get("visit_type", "baseline")),
        "svt_status": str(payload.get("svt_status", "without_svt")),
        "cohort_status": str(payload.get("cohort_status", "active")),
        "diagnosis": str(payload.get("diagnosis", "")),
        "ward": str(payload.get("ward", "")),
        "template_id": str(payload.get("template_id", "")),
        "updated_at": created_at.isoformat() if created_at else None,
        "_sort_date": encounter.isoformat() if encounter else "",
        "_sort_ts": created_at.isoformat() if created_at else "",
    }


def build_case_index(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    latest_by_patient: dict[str, dict[str, Any]] = {}
    event_count: dict[str, int] = {}

    for event in events:
        summary = _summary_from_event(event)
        if summary is None:
            continue

        patient_id = summary["patient_id"]
        event_count[patient_id] = event_count.get(patient_id, 0) + 1

        previous = latest_by_patient.get(patient_id)
        if previous is None:
            latest_by_patient[patient_id] = summary
            continue

        previous_key = (previous["_sort_date"], previous["_sort_ts"])
        current_key = (summary["_sort_date"], summary["_sort_ts"])
        if current_key >= previous_key:
            latest_by_patient[patient_id] = summary

    items: list[dict[str, Any]] = []
    for patient_id, summary in latest_by_patient.items():
        cleaned = {k: v for k, v in summary.items() if not k.startswith("_")}
        cleaned["event_count"] = event_count.get(patient_id, 1)
        items.append(cleaned)

    items.sort(key=lambda item: ((item.get("updated_at") or ""), item["patient_id"]), reverse=True)
    return items


def list_cases(events: list[dict[str, Any]], query: str | None, limit: int) -> list[dict[str, Any]]:
    indexed = build_case_index(events)
    if query:
        token = query.strip().lower()
        if token:
            filtered: list[dict[str, Any]] = []
            for item in indexed:
                fields = [item.get("patient_id", ""), item.get("diagnosis", ""), item.get("ward", "")]
                joined = " ".join(str(value).lower() for value in fields)
                if token in joined:
                    filtered.append(item)
            indexed = filtered

    return indexed[: max(1, min(limit, 500))]


def get_case_detail(events: list[dict[str, Any]], patient_id: str) -> dict[str, Any] | None:
    normalized = patient_id.strip().upper()
    if not normalized:
        return None

    matching: list[dict[str, Any]] = []
    for event in events:
        payload = event.get("payload")
        if not isinstance(payload, dict):
            continue
        if str(payload.get("patient_id", "")).strip().upper() != normalized:
            continue
        matching.append(event)

    if not matching:
        return None

    matching.sort(
        key=lambda event: (
            str(_parse_date((event.get("payload") or {}).get("encounter_date")) or ""),
            str(_parse_datetime(event.get("created_at")) or ""),
        )
    )

    latest = matching[-1]
    payload = latest.get("payload") if isinstance(latest.get("payload"), dict) else {}
    summary = _summary_from_event(latest) or {"patient_id": normalized}
    summary_clean = {k: v for k, v in summary.items() if not k.startswith("_")}

    history: list[dict[str, Any]] = []
    for event in matching:
        row = _summary_from_event(event)
        if row is None:
            continue
        history.append({k: v for k, v in row.items() if not k.startswith("_")})

    history.sort(key=lambda item: ((item.get("encounter_date") or ""), (item.get("updated_at") or "")), reverse=True)

    return {
        "summary": summary_clean,
        "payload": payload,
        "history": history,
    }
