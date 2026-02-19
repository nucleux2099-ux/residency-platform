from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers.analytics import router as analytics_router
from app.routers.health import router as health_router
from app.routers.ingestion import router as ingestion_router
from app.routers.patients import router as patients_router
from app.routers.templates import router as templates_router
from app.routers.vault import router as vault_router
from app.routers.atom import router as atom_router
from app.services.attachment_assist_jobs import (
    initialize_attachment_assist_job_manager,
    shutdown_attachment_assist_job_manager,
)
from app.services.patient_document_index import initialize_patient_document_indexer, shutdown_patient_document_indexer


@asynccontextmanager
async def lifespan(_: FastAPI):
    initialize_patient_document_indexer(
        vault_root=settings.vault_root_path,
        event_store_path=settings.event_store,
        index_path=settings.document_index,
        marker_command=settings.marker_command,
        scan_interval_sec=settings.document_scan_interval_sec,
        marker_timeout_sec=settings.marker_timeout_sec,
        max_document_chars=settings.document_max_chars,
        binary_per_cycle_limit=settings.document_binary_per_cycle_limit,
    )
    initialize_attachment_assist_job_manager(
        jobs_path=settings.attachment_assist_jobs,
        uploads_root=settings.uploads_root,
        max_chars=settings.document_max_chars,
    )
    try:
        yield
    finally:
        shutdown_attachment_assist_job_manager()
        shutdown_patient_document_indexer()


app = FastAPI(title="Residency API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(vault_router)
app.include_router(templates_router)
app.include_router(ingestion_router)
app.include_router(patients_router)
app.include_router(analytics_router)
app.include_router(atom_router)
