# Residency API

## Run
1. `python -m venv .venv`
2. `.venv/bin/pip install -e .`
3. `.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload --reload-dir app --reload-exclude '.venv/*' --reload-exclude '**/__pycache__/*'`

## OCR/Search Notes
- Marker CLI is used first for PDF/image OCR (`MARKER_COMMAND`, default `marker_single`).
- If Marker fails, API attempts local fallback extraction (`pdftotext` for PDFs, `tesseract` for images when available).

## Endpoints
- `GET /health`
- `GET /vault/tree`
- `GET /vault/folders`
- `GET /vault/stream` (SSE)
- `GET /templates`
- `GET /templates/{template_id}`
- `POST /ingestion/patient`
- `POST /ingestion/files`
- `POST /ingestion/attachment-assist`
- `POST /ingestion/patient-csv`
- `POST /ingestion/import-proformas`
- `GET /ingestion/cases`
- `GET /ingestion/cases/{patient_id}`
- `GET /patients`
- `GET /patients/search`
- `GET /patients/index/status`
- `POST /patients/index/reindex`
- `GET /patients/{patient_key}/index-files`
- `GET /patients/{patient_key}/lab-timeline`
- `GET /patients/{patient_key}/lab-trends`
- `GET /patients/{patient_key}`
- `GET /patients/{patient_key}/files/{file_id}`
- `GET /patients/{patient_key}/files/{file_id}/preview`
- `GET /patients/{patient_key}/files/{file_id}/extracted`
- `GET /analytics/summary`
- `GET /analytics/cohort`
- `GET /analytics/followups`
- `GET /analytics/data-quality`
