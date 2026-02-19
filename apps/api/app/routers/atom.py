import logging
from typing import AsyncGenerator

from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import StreamingResponse

from app.schemas.common import ApiEnvelope
from app.services.atom_service import atom_service, ChatRequest
from app.services.patient_library import get_patient_detail
from app.config import settings

router = APIRouter(prefix="/atom", tags=["atom"])
logger = logging.getLogger(__name__)

@router.post("/chat")
async def chat(request: ChatRequest) -> StreamingResponse:
    # Optional: Enhance context here if patient_id is provided but context is missing
    # For now, we assume frontend sends the context or we rely on the service to fetch it if we change the contract.
    
    return StreamingResponse(
        atom_service.stream_chat(request),
        media_type="text/event-stream"
    )
