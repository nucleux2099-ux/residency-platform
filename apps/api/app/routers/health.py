from fastapi import APIRouter

from app.schemas.common import ApiEnvelope

router = APIRouter(tags=["health"])


@router.get("/health", response_model=ApiEnvelope[dict])
def health() -> ApiEnvelope[dict]:
    return ApiEnvelope(data={"status": "ok"})
