from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from typing import Any

PROTOCOL_VISITS = [
    "baseline",
    "day7_reassessment",
    "discharge",
    "week2_followup",
    "month1_followup",
    "month3_followup",
]
REQUIRED_VISITS = ["baseline", "discharge", "week2_followup", "month1_followup", "month3_followup"]
FOLLOWUP_PLAN = [
    ("week2_followup", 14, 3),
    ("month1_followup", 30, 7),
    ("month3_followup", 90, 14),
]


def _parse_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    if isinstance(value, datetime):
        return value.date()

    text = str(value).strip()
    if not text:
        return None

    if "T" in text:
        text = text.split("T", 1)[0]

    for candidate in (text, text.replace("/", "-")):
        try:
            return date.fromisoformat(candidate)
        except ValueError:
            continue
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


def _parse_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    text = str(value).strip().lower()
    if text in {"true", "1", "yes", "y"}:
        return True
    if text in {"false", "0", "no", "n"}:
        return False
    return default


def _normalize_vessels(raw: Any) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, list):
        values = raw
    else:
        values = [token.strip() for token in str(raw).replace(";", ",").split(",")]
    normalized = []
    for token in values:
        value = str(token).strip().lower()
        if not value:
            continue
        if value in normalized:
            continue
        normalized.append(value)
    return normalized


def _normalize_event(event: dict[str, Any]) -> dict[str, Any] | None:
    payload = event.get("payload")
    if not isinstance(payload, dict):
        return None

    patient_id = str(payload.get("patient_id", "")).strip().upper()
    if not patient_id:
        return None

    svt_status = str(payload.get("svt_status", "without_svt")).strip().lower()
    if svt_status not in {"with_svt", "without_svt"}:
        svt_status = "without_svt"

    visit_type = str(payload.get("visit_type", "baseline")).strip()
    if visit_type not in PROTOCOL_VISITS:
        visit_type = "baseline"

    cohort_status = str(payload.get("cohort_status", "active")).strip()
    if cohort_status not in {"screened", "enrolled", "active", "completed", "terminal_outcome"}:
        cohort_status = "active"

    mortality = str(payload.get("mortality", "no")).strip().lower()
    if mortality not in {"yes", "no"}:
        mortality = "no"

    death_date = _parse_date(payload.get("death_date"))
    if death_date is not None:
        mortality = "yes"

    recanalization_status = str(payload.get("recanalization_status", "")).strip()
    if not recanalization_status:
        recanalization_status = "pending" if svt_status == "with_svt" else "not_applicable"

    if svt_status == "without_svt":
        recanalization_status = "not_applicable"

    vessels = _normalize_vessels(payload.get("vessel_involvement"))
    if svt_status == "without_svt":
        vessels = []

    created_at = _parse_datetime(event.get("created_at"))
    encounter_date = _parse_date(payload.get("encounter_date"))

    return {
        "event_id": event.get("event_id"),
        "created_at": created_at,
        "encounter_date": encounter_date,
        "template_id": str(payload.get("template_id", "")).strip() or "unknown",
        "patient_id": patient_id,
        "diagnosis": str(payload.get("diagnosis", "")).strip(),
        "visit_type": visit_type,
        "svt_status": svt_status,
        "vessel_involvement": vessels,
        "ward": str(payload.get("ward", "")).strip(),
        "cohort_status": cohort_status,
        "mortality": mortality,
        "death_date": death_date.isoformat() if death_date else None,
        "cause_of_death": str(payload.get("cause_of_death", "")).strip() or None,
        "recanalization_status": recanalization_status,
        "primary_endpoint_complete": _parse_bool(payload.get("primary_endpoint_complete"), default=False),
        "notes_present": bool(str(payload.get("notes", "")).strip()),
    }


def _sort_key(event: dict[str, Any]) -> tuple[Any, ...]:
    encounter_date = event.get("encounter_date")
    created_at = event.get("created_at")
    return (
        encounter_date.isoformat() if isinstance(encounter_date, date) else "",
        created_at.isoformat() if isinstance(created_at, datetime) else "",
    )


def _compute_followup(today: date, visits_completed: set[str], reference_date: date | None) -> dict[str, Any]:
    if reference_date is None:
        return {"status": "insufficient_data", "next_visit": None, "due_date": None, "days_overdue": 0, "days_until_due": None}

    for visit_name, offset_days, grace_days in FOLLOWUP_PLAN:
        if visit_name in visits_completed:
            continue

        due_date = reference_date + timedelta(days=offset_days)
        overdue_cutoff = due_date + timedelta(days=grace_days)
        days_until_due = (due_date - today).days
        days_overdue = (today - due_date).days

        if today > overdue_cutoff:
            status = "overdue"
        elif days_until_due <= 7:
            status = "due_soon"
        else:
            status = "scheduled"

        return {
            "status": status,
            "next_visit": visit_name,
            "due_date": due_date.isoformat(),
            "days_overdue": max(days_overdue, 0),
            "days_until_due": days_until_due,
        }

    return {"status": "complete", "next_visit": None, "due_date": None, "days_overdue": 0, "days_until_due": None}


def build_analytics_projection(events: list[dict[str, Any]], cohort_target: int, today: date | None = None) -> dict[str, Any]:
    current_date = today or date.today()
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for event in events:
        normalized = _normalize_event(event)
        if normalized is None:
            continue
        grouped[normalized["patient_id"]].append(normalized)

    patients: list[dict[str, Any]] = []
    followup_items: list[dict[str, Any]] = []
    quality_items: list[dict[str, Any]] = []
    issues_counter: Counter[str] = Counter()

    for patient_id, patient_events in grouped.items():
        patient_events.sort(key=_sort_key)
        latest = patient_events[-1]

        visits_completed = {item["visit_type"] for item in patient_events}
        missing_required = [visit for visit in REQUIRED_VISITS if visit not in visits_completed]

        required_completed = len(REQUIRED_VISITS) - len(missing_required)
        completeness_pct = round((required_completed / len(REQUIRED_VISITS)) * 100, 1)

        baseline_date = next((item["encounter_date"] for item in patient_events if item["visit_type"] == "baseline"), None)
        discharge_date = next((item["encounter_date"] for item in patient_events if item["visit_type"] == "discharge"), None)
        reference_date = discharge_date or baseline_date

        followup = _compute_followup(current_date, visits_completed, reference_date)

        endpoint_complete = bool(latest["primary_endpoint_complete"]) or (
            "month3_followup" in visits_completed and latest["recanalization_status"] not in {"pending", "not_applicable"}
        )

        issues: list[str] = []
        if missing_required:
            issues.append("missing_required_visits")
        if latest["mortality"] == "yes" and (not latest["death_date"] or not latest["cause_of_death"]):
            issues.append("mortality_missing_details")
        if latest["svt_status"] == "with_svt" and not latest["vessel_involvement"]:
            issues.append("svt_missing_vessels")
        if latest["template_id"].endswith("v1"):
            issues.append("legacy_template")
        if latest["visit_type"] == "month3_followup" and latest["svt_status"] == "with_svt" and latest["recanalization_status"] == "pending":
            issues.append("month3_pending_recanalization")

        for issue in issues:
            issues_counter[issue] += 1

        patient_row = {
            "patient_id": patient_id,
            "cohort_status": latest["cohort_status"],
            "svt_status": latest["svt_status"],
            "ward": latest["ward"],
            "diagnosis": latest["diagnosis"],
            "latest_visit": latest["visit_type"],
            "last_encounter_date": latest["encounter_date"].isoformat() if isinstance(latest["encounter_date"], date) else None,
            "event_count": len(patient_events),
            "visits_completed": sorted(visits_completed),
            "missing_required_visits": missing_required,
            "completeness_pct": completeness_pct,
            "recanalization_status": latest["recanalization_status"],
            "primary_endpoint_complete": endpoint_complete,
            "mortality": latest["mortality"],
            "death_date": latest["death_date"],
            "cause_of_death": latest["cause_of_death"],
            "vessel_involvement": latest["vessel_involvement"],
            "template_id": latest["template_id"],
        }
        patients.append(patient_row)

        followup_items.append(
            {
                "patient_id": patient_id,
                "cohort_status": latest["cohort_status"],
                "svt_status": latest["svt_status"],
                "last_encounter_date": patient_row["last_encounter_date"],
                "next_visit": followup["next_visit"],
                "due_date": followup["due_date"],
                "status": followup["status"],
                "days_until_due": followup["days_until_due"],
                "days_overdue": followup["days_overdue"],
            }
        )

        quality_items.append(
            {
                "patient_id": patient_id,
                "template_id": latest["template_id"],
                "completeness_pct": completeness_pct,
                "missing_required_visits": missing_required,
                "issue_count": len(issues),
                "issues": issues,
            }
        )

    patients.sort(key=lambda item: item["patient_id"])
    followup_items.sort(key=lambda item: (item["status"], item["days_overdue"] * -1, item["patient_id"]))
    quality_items.sort(key=lambda item: (-item["issue_count"], item["completeness_pct"], item["patient_id"]))

    total_patients = len(patients)
    enrolled = sum(1 for item in patients if item["cohort_status"] in {"enrolled", "active", "completed", "terminal_outcome"})
    active = sum(1 for item in patients if item["cohort_status"] == "active")
    completed = sum(1 for item in patients if item["cohort_status"] == "completed")
    terminal_outcomes = sum(1 for item in patients if item["cohort_status"] == "terminal_outcome" or item["mortality"] == "yes")
    endpoint_complete_count = sum(1 for item in patients if item["primary_endpoint_complete"])
    with_svt = sum(1 for item in patients if item["svt_status"] == "with_svt")
    without_svt = total_patients - with_svt
    overdue_followups = sum(1 for item in followup_items if item["status"] == "overdue")
    due_soon_followups = sum(1 for item in followup_items if item["status"] == "due_soon")

    avg_completeness = round(
        sum(float(item["completeness_pct"]) for item in quality_items) / total_patients if total_patients else 0.0,
        1,
    )

    summary = {
        "cohort_target": cohort_target,
        "total_patients": total_patients,
        "enrolled_patients": enrolled,
        "active_patients": active,
        "completed_patients": completed,
        "terminal_outcomes": terminal_outcomes,
        "svt_patients": with_svt,
        "non_svt_patients": without_svt,
        "endpoint_completed": endpoint_complete_count,
        "endpoint_completion_rate": round((endpoint_complete_count / total_patients) * 100, 1) if total_patients else 0.0,
        "followups_overdue": overdue_followups,
        "followups_due_soon": due_soon_followups,
        "average_completeness": avg_completeness,
    }

    return {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "summary": summary,
        "cohort": {
            "target": cohort_target,
            "enrolled": enrolled,
            "active": active,
            "completed": completed,
            "terminal_outcomes": terminal_outcomes,
            "patients": patients,
        },
        "followups": {
            "overdue_count": overdue_followups,
            "due_soon_count": due_soon_followups,
            "items": followup_items,
        },
        "data_quality": {
            "average_completeness": avg_completeness,
            "patients_with_issues": sum(1 for item in quality_items if item["issue_count"] > 0),
            "issues_by_type": dict(issues_counter),
            "items": quality_items,
        },
    }

