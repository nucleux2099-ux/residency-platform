from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from app.config import settings
from app.schemas.common import ApiEnvelope
from app.services.patient_document_index import get_patient_document_indexer
from app.services.patient_library import (
    get_patient_detail,
    list_patient_cards,
    read_patient_file_preview,
    resolve_patient_file,
)

router = APIRouter(prefix="/patients", tags=["patients"])


@router.get("", response_model=ApiEnvelope[list[dict]])
def patient_cards(
    q: str | None = Query(default=None),
    svt_status: str | None = Query(default=None),
    case_bucket: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=500),
) -> ApiEnvelope[list[dict]]:
    data = list_patient_cards(
        vault_root=settings.vault_root_path,
        event_store_path=settings.event_store,
        query=q,
        svt_status=svt_status,
        case_bucket=case_bucket,
        limit=limit,
    )
    return ApiEnvelope(data=data)


@router.get("/search", response_model=ApiEnvelope[list[dict]])
def patient_document_search(
    q: str = Query(..., min_length=2),
    patient_key: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
) -> ApiEnvelope[list[dict]]:
    indexer = get_patient_document_indexer()
    if indexer is None:
        raise HTTPException(status_code=503, detail="Document indexer not initialized")

    results = indexer.search(query=q, patient_key=patient_key, limit=limit)
    return ApiEnvelope(data=results)


@router.get("/index/status", response_model=ApiEnvelope[dict])
def patient_index_status() -> ApiEnvelope[dict]:
    indexer = get_patient_document_indexer()
    if indexer is None:
        raise HTTPException(status_code=503, detail="Document indexer not initialized")
    return ApiEnvelope(data=indexer.status())


@router.post("/index/reindex", response_model=ApiEnvelope[dict])
def patient_index_reindex(
    force: bool = Query(default=True),
    patient_key: str | None = Query(default=None),
    file_id: str | None = Query(default=None),
) -> ApiEnvelope[dict]:
    indexer = get_patient_document_indexer()
    if indexer is None:
        raise HTTPException(status_code=503, detail="Document indexer not initialized")
    result = indexer.reindex(force=force, patient_key=patient_key, file_id=file_id)
    return ApiEnvelope(data=result)


@router.get("/{patient_key}", response_model=ApiEnvelope[dict])
def patient_detail(patient_key: str) -> ApiEnvelope[dict]:
    detail = get_patient_detail(
        vault_root=settings.vault_root_path,
        event_store_path=settings.event_store,
        patient_key=patient_key,
    )
    if detail is None:
        raise HTTPException(status_code=404, detail=f"Patient not found: {patient_key}")

    return ApiEnvelope(data=detail)


@router.get("/{patient_key}/files/{file_id}")
def patient_file(patient_key: str, file_id: str) -> FileResponse:
    resolved = resolve_patient_file(
        vault_root=settings.vault_root_path,
        event_store_path=settings.event_store,
        patient_key=patient_key,
        file_id=file_id,
    )
    if resolved is None:
        raise HTTPException(status_code=404, detail="File not found")

    path, metadata = resolved
    media_type = str(metadata.get("mime_type") or "application/octet-stream")

    return FileResponse(
        path,
        filename=path.name,
        media_type=media_type,
        content_disposition_type="inline",
    )


@router.get("/{patient_key}/files/{file_id}/preview", response_model=ApiEnvelope[dict])
def patient_file_preview(patient_key: str, file_id: str) -> ApiEnvelope[dict]:
    preview = read_patient_file_preview(
        vault_root=settings.vault_root_path,
        event_store_path=settings.event_store,
        patient_key=patient_key,
        file_id=file_id,
    )
    if preview is None:
        raise HTTPException(status_code=404, detail="File not found")

    return ApiEnvelope(data=preview)


@router.get("/{patient_key}/files/{file_id}/extracted", response_model=ApiEnvelope[dict])
def patient_file_extracted(patient_key: str, file_id: str, max_chars: int = Query(default=120000, ge=1000, le=1000000)) -> ApiEnvelope[dict]:
    indexer = get_patient_document_indexer()
    if indexer is None:
        raise HTTPException(status_code=503, detail="Document indexer not initialized")

    extracted = indexer.get_extracted_document(patient_key=patient_key, file_id=file_id, max_chars=max_chars)
    if extracted is None:
        raise HTTPException(status_code=404, detail="Extracted text not found")

    return ApiEnvelope(data=extracted)


@router.get("/{patient_key}/index-files", response_model=ApiEnvelope[list[dict]])
def patient_indexed_files(patient_key: str) -> ApiEnvelope[list[dict]]:
    indexer = get_patient_document_indexer()
    if indexer is None:
        raise HTTPException(status_code=503, detail="Document indexer not initialized")

    return ApiEnvelope(data=indexer.list_patient_documents(patient_key=patient_key))


@router.get("/{patient_key}/lab-timeline", response_model=ApiEnvelope[list[dict]])
def patient_lab_timeline(patient_key: str, limit: int = Query(default=80, ge=1, le=200)) -> ApiEnvelope[list[dict]]:
    indexer = get_patient_document_indexer()
    if indexer is None:
        raise HTTPException(status_code=503, detail="Document indexer not initialized")

    return ApiEnvelope(data=indexer.list_patient_lab_timeline(patient_key=patient_key, limit=limit))


@router.get("/{patient_key}/lab-trends", response_model=ApiEnvelope[dict])
def patient_lab_trends(patient_key: str, limit_reports: int = Query(default=120, ge=1, le=300)) -> ApiEnvelope[dict]:
    indexer = get_patient_document_indexer()
    if indexer is None:
        raise HTTPException(status_code=503, detail="Document indexer not initialized")

    return ApiEnvelope(data=indexer.list_patient_lab_trends(patient_key=patient_key, limit_reports=limit_reports))
