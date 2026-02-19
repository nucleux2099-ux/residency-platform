from fastapi import APIRouter, HTTPException

from app.config import settings
from app.schemas.common import ApiEnvelope
from app.services.template_registry import get_template, list_templates

router = APIRouter(tags=["templates"])


@router.get("/templates", response_model=ApiEnvelope[list[dict]])
def templates() -> ApiEnvelope[list[dict]]:
    return ApiEnvelope(data=list_templates(settings.templates_path))


@router.get("/templates/{template_id}", response_model=ApiEnvelope[dict])
def template_details(template_id: str) -> ApiEnvelope[dict]:
    template = get_template(settings.templates_path, template_id)
    if template is None:
        raise HTTPException(status_code=404, detail=f"Template not found: {template_id}")
    return ApiEnvelope(data=template)
