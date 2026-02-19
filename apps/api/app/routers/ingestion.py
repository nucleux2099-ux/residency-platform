from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile

from app.config import settings
from app.schemas.common import ApiEnvelope
from app.schemas.patient import (
    AttachmentAssistReviewPayload,
    CsvIngestionAck,
    FileUploadAck,
    IngestionAck,
    PatientSubmission,
    ProformaImportAck,
)
from app.services.csv_ingestion import ingest_patient_csv
from app.services.event_store import append_submission, read_events
from app.services.file_store import save_uploads
from app.services.note_writer import write_patient_note
from app.services.patient_validator import validate_submission_against_template
from app.services.attachment_assist import analyze_ingestion_attachment
from app.services.attachment_assist_jobs import get_attachment_assist_job_manager
from app.services.case_registry import get_case_detail, list_cases
from app.services.proforma_import import import_vault_proformas
from app.services.template_registry import get_template

router = APIRouter(prefix="/ingestion", tags=["ingestion"])


@router.post("/patient", response_model=ApiEnvelope[IngestionAck])
def ingest_patient(payload: PatientSubmission) -> ApiEnvelope[IngestionAck]:
    template = get_template(settings.templates_path, payload.template_id)
    if template is None:
        raise HTTPException(status_code=400, detail=f"Template not found: {payload.template_id}")

    errors = validate_submission_against_template(payload, template)
    if errors:
        raise HTTPException(status_code=422, detail={"template_errors": errors})

    event_id = append_submission(settings.event_store, payload)
    note_path = write_patient_note(settings.auto_notes_root, settings.vault_root_path, payload, event_id)
    return ApiEnvelope(data=IngestionAck(event_id=event_id, note_path=str(note_path)))


@router.post("/files", response_model=ApiEnvelope[FileUploadAck])
async def upload_source_files(
    files: list[UploadFile] = File(...),
    patient_id: str | None = Form(default=None),
) -> ApiEnvelope[FileUploadAck]:
    if not files:
        raise HTTPException(status_code=400, detail="At least one file is required")

    uploaded = await save_uploads(settings.uploads_root, files, patient_id)
    return ApiEnvelope(data=FileUploadAck(uploaded_count=len(uploaded), files=uploaded))


@router.post("/attachment-assist", response_model=ApiEnvelope[dict])
async def ingestion_attachment_assist(
    file: UploadFile = File(...),
    section: str = Form(...),
    patient_id: str | None = Form(default=None),
) -> ApiEnvelope[dict]:
    normalized_section = section.strip().lower()
    if normalized_section not in {"lab", "imaging"}:
        raise HTTPException(status_code=400, detail="section must be either 'lab' or 'imaging'")

    uploaded = await save_uploads(settings.uploads_root, [file], patient_id)
    if not uploaded:
        raise HTTPException(status_code=500, detail="Failed to store uploaded file")

    descriptor = uploaded[0]
    stored_path = Path(descriptor.stored_path).resolve()
    analysis = analyze_ingestion_attachment(
        stored_path=stored_path,
        original_file_name=descriptor.file_name,
        section=normalized_section,
        max_chars=max(settings.document_max_chars, 20000),
    )

    payload = {
        "uploaded_file": descriptor.model_dump(),
        **analysis,
    }
    return ApiEnvelope(data=payload)


@router.post("/attachment-assist/jobs", response_model=ApiEnvelope[dict])
async def create_attachment_assist_job(
    file: UploadFile = File(...),
    section: str = Form(...),
    patient_id: str | None = Form(default=None),
) -> ApiEnvelope[dict]:
    normalized_section = section.strip().lower()
    if normalized_section not in {"lab", "imaging"}:
        raise HTTPException(status_code=400, detail="section must be either 'lab' or 'imaging'")

    manager = get_attachment_assist_job_manager()
    if manager is None:
        raise HTTPException(status_code=503, detail="Attachment assist job manager not initialized")

    uploaded = await save_uploads(settings.uploads_root, [file], patient_id)
    if not uploaded:
        raise HTTPException(status_code=500, detail="Failed to store uploaded file")

    descriptor = uploaded[0]
    try:
        job = manager.create_job(
            section=normalized_section,
            patient_id=patient_id,
            uploaded_file=descriptor.model_dump(),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return ApiEnvelope(data=job)


@router.get("/attachment-assist/jobs", response_model=ApiEnvelope[list[dict]])
def list_attachment_assist_jobs(
    patient_id: str | None = Query(default=None),
    status: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=300),
) -> ApiEnvelope[list[dict]]:
    manager = get_attachment_assist_job_manager()
    if manager is None:
        raise HTTPException(status_code=503, detail="Attachment assist job manager not initialized")
    return ApiEnvelope(data=manager.list_jobs(patient_id=patient_id, status=status, limit=limit))


@router.get("/attachment-assist/jobs/{job_id}", response_model=ApiEnvelope[dict])
def get_attachment_assist_job(job_id: str) -> ApiEnvelope[dict]:
    manager = get_attachment_assist_job_manager()
    if manager is None:
        raise HTTPException(status_code=503, detail="Attachment assist job manager not initialized")
    job = manager.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Attachment assist job not found: {job_id}")
    return ApiEnvelope(data=job)


@router.post("/attachment-assist/jobs/{job_id}/review", response_model=ApiEnvelope[dict])
def review_attachment_assist_job(job_id: str, payload: AttachmentAssistReviewPayload) -> ApiEnvelope[dict]:
    manager = get_attachment_assist_job_manager()
    if manager is None:
        raise HTTPException(status_code=503, detail="Attachment assist job manager not initialized")
    try:
        job = manager.set_review(
            job_id=job_id,
            decision=payload.decision,
            reviewer_note=payload.reviewer_note,
            applied_payload=payload.applied_payload,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return ApiEnvelope(data=job)


@router.post("/attachment-assist/jobs/{job_id}/retry", response_model=ApiEnvelope[dict])
def retry_attachment_assist_job(job_id: str) -> ApiEnvelope[dict]:
    manager = get_attachment_assist_job_manager()
    if manager is None:
        raise HTTPException(status_code=503, detail="Attachment assist job manager not initialized")
    try:
        job = manager.retry_job(job_id=job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return ApiEnvelope(data=job)


@router.post("/patient-csv", response_model=ApiEnvelope[CsvIngestionAck])
async def ingest_patient_csv_file(file: UploadFile = File(...)) -> ApiEnvelope[CsvIngestionAck]:
    name = (file.filename or "").lower()
    if not name.endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only .csv files are accepted")

    content = await file.read()
    result = ingest_patient_csv(
        content,
        settings.event_store,
        settings.templates_path,
        settings.auto_notes_root,
        settings.vault_root_path,
    )
    return ApiEnvelope(data=result)


@router.post("/import-proformas", response_model=ApiEnvelope[ProformaImportAck])
def import_existing_proformas() -> ApiEnvelope[ProformaImportAck]:
    try:
        result = import_vault_proformas(
            vault_root=settings.vault_root_path,
            event_store_path=settings.event_store,
            templates_dir=settings.templates_path,
            notes_root=settings.auto_notes_root,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return ApiEnvelope(data=result)


@router.get("/cases", response_model=ApiEnvelope[list[dict]])
def ingestion_cases(q: str | None = Query(default=None), limit: int = Query(default=100, ge=1, le=500)) -> ApiEnvelope[list[dict]]:
    events = read_events(settings.event_store)
    return ApiEnvelope(data=list_cases(events, q, limit))


@router.get("/cases/{patient_id}", response_model=ApiEnvelope[dict])
def ingestion_case_detail(patient_id: str) -> ApiEnvelope[dict]:
    events = read_events(settings.event_store)
    detail = get_case_detail(events, patient_id)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"Case not found: {patient_id}")
    return ApiEnvelope(data=detail)
