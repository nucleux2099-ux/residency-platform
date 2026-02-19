from fastapi import APIRouter

from app.config import settings
from app.schemas.common import ApiEnvelope
from app.services.event_store import read_events
from app.services.projections import build_analytics_projection

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/summary", response_model=ApiEnvelope[dict])
def analytics_summary() -> ApiEnvelope[dict]:
    events = read_events(settings.event_store)
    projection = build_analytics_projection(events, settings.cohort_target)
    summary = projection["summary"]
    summary["total_submissions"] = len(events)
    return ApiEnvelope(data=summary)


@router.get("/cohort", response_model=ApiEnvelope[dict])
def analytics_cohort() -> ApiEnvelope[dict]:
    projection = build_analytics_projection(read_events(settings.event_store), settings.cohort_target)
    return ApiEnvelope(data=projection["cohort"])


@router.get("/followups", response_model=ApiEnvelope[dict])
def analytics_followups() -> ApiEnvelope[dict]:
    projection = build_analytics_projection(read_events(settings.event_store), settings.cohort_target)
    return ApiEnvelope(data=projection["followups"])


@router.get("/data-quality", response_model=ApiEnvelope[dict])
def analytics_data_quality() -> ApiEnvelope[dict]:
    projection = build_analytics_projection(read_events(settings.event_store), settings.cohort_target)
    return ApiEnvelope(data=projection["data_quality"])
