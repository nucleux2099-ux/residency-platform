from __future__ import annotations

import json
import queue
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.services.attachment_assist import analyze_ingestion_attachment


class AttachmentAssistJobManager:
    def __init__(self, jobs_path: Path, uploads_root: Path, max_chars: int) -> None:
        self.jobs_path = jobs_path
        self.uploads_root = uploads_root.resolve()
        self.max_chars = max(max_chars, 20_000)

        self._lock = threading.RLock()
        self._queue: queue.Queue[str] = queue.Queue()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

        self._jobs: dict[str, dict[str, Any]] = {}
        self._updated_at: str | None = None
        self._load()

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    def _load(self) -> None:
        if not self.jobs_path.exists():
            return

        try:
            raw = self.jobs_path.read_text(encoding="utf-8")
            payload = json.loads(raw)
        except (OSError, json.JSONDecodeError):
            return

        if not isinstance(payload, dict):
            return

        jobs = payload.get("jobs")
        if not isinstance(jobs, dict):
            jobs = {}

        with self._lock:
            self._jobs = {}
            for job_id, job in jobs.items():
                if not isinstance(job_id, str) or not isinstance(job, dict):
                    continue
                snapshot = dict(job)
                snapshot["job_id"] = job_id
                status = str(snapshot.get("status") or "").strip().lower()
                if status in {"queued", "processing"}:
                    snapshot["status"] = "queued"
                    snapshot["updated_at"] = self._now_iso()
                    self._queue.put(job_id)
                self._jobs[job_id] = snapshot
            self._updated_at = str(payload.get("updated_at") or "") or None

    def _save(self) -> None:
        with self._lock:
            payload = {
                "version": 1,
                "updated_at": self._updated_at,
                "jobs": self._jobs,
            }

        self.jobs_path.parent.mkdir(parents=True, exist_ok=True)
        self.jobs_path.write_text(json.dumps(payload, ensure_ascii=True), encoding="utf-8")

    def start(self) -> None:
        with self._lock:
            if self._thread and self._thread.is_alive():
                return
            self._stop_event.clear()
            self._thread = threading.Thread(target=self._worker_loop, name="attachment-assist-worker", daemon=True)
            self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        thread = self._thread
        if thread and thread.is_alive():
            thread.join(timeout=5)

    def _ensure_upload_path(self, stored_path: str) -> Path:
        candidate = Path(stored_path).resolve()
        if not candidate.exists() or not candidate.is_file():
            raise ValueError("Stored upload file does not exist")
        if not candidate.is_relative_to(self.uploads_root):
            raise ValueError("Stored upload file is outside uploads root")
        return candidate

    def create_job(self, section: str, patient_id: str | None, uploaded_file: dict[str, Any]) -> dict[str, Any]:
        normalized_section = section.strip().lower()
        if normalized_section not in {"lab", "imaging"}:
            raise ValueError("section must be either 'lab' or 'imaging'")

        file_name = str(uploaded_file.get("file_name") or "").strip()
        stored_path = str(uploaded_file.get("stored_path") or "").strip()
        size_bytes = int(uploaded_file.get("size_bytes") or 0)
        if not file_name or not stored_path:
            raise ValueError("uploaded_file must include file_name and stored_path")

        resolved_path = self._ensure_upload_path(stored_path)
        patient_token = (patient_id or "").strip().upper() or None
        now = self._now_iso()
        job_id = f"ajob_{uuid4().hex}"
        job = {
            "job_id": job_id,
            "status": "queued",
            "section": normalized_section,
            "patient_id": patient_token,
            "created_at": now,
            "updated_at": now,
            "started_at": None,
            "finished_at": None,
            "error": None,
            "uploaded_file": {
                "file_name": file_name,
                "stored_path": str(resolved_path),
                "size_bytes": size_bytes,
            },
            "result": None,
            "review": {
                "status": "not_ready",
                "decision": None,
                "reviewed_at": None,
                "reviewer_note": None,
                "applied_payload": None,
            },
        }

        with self._lock:
            self._jobs[job_id] = job
            self._updated_at = now
            self._save()
            self._queue.put(job_id)
            return dict(job)

    def list_jobs(self, patient_id: str | None, status: str | None, limit: int) -> list[dict[str, Any]]:
        token_patient = (patient_id or "").strip().upper()
        token_status = (status or "").strip().lower()

        with self._lock:
            jobs = list(self._jobs.values())

        rows = []
        for job in jobs:
            if token_patient and str(job.get("patient_id") or "").upper() != token_patient:
                continue
            if token_status and str(job.get("status") or "").lower() != token_status:
                continue
            rows.append(job)

        rows.sort(
            key=lambda item: (
                str(item.get("created_at") or ""),
                str(item.get("job_id") or ""),
            ),
            reverse=True,
        )
        return [dict(item) for item in rows[: max(1, min(limit, 300))]]

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        token = job_id.strip()
        if not token:
            return None

        with self._lock:
            job = self._jobs.get(token)
            return dict(job) if isinstance(job, dict) else None

    def set_review(
        self,
        job_id: str,
        decision: str,
        reviewer_note: str | None,
        applied_payload: dict[str, Any] | None,
    ) -> dict[str, Any]:
        token = job_id.strip()
        if not token:
            raise KeyError("job_id is required")

        normalized_decision = decision.strip().lower()
        if normalized_decision not in {"accepted", "rejected"}:
            raise ValueError("decision must be 'accepted' or 'rejected'")

        with self._lock:
            job = self._jobs.get(token)
            if not isinstance(job, dict):
                raise KeyError(f"Job not found: {token}")

            if str(job.get("status") or "") != "completed":
                raise ValueError("Review can only be recorded for completed jobs")

            review = job.get("review")
            if not isinstance(review, dict):
                review = {}

            review.update(
                {
                    "status": normalized_decision,
                    "decision": normalized_decision,
                    "reviewed_at": self._now_iso(),
                    "reviewer_note": (reviewer_note or "").strip() or None,
                    "applied_payload": applied_payload or {},
                }
            )
            job["review"] = review
            job["updated_at"] = self._now_iso()

            self._jobs[token] = job
            self._updated_at = str(job["updated_at"])
            self._save()
            return dict(job)

    def retry_job(self, job_id: str) -> dict[str, Any]:
        token = job_id.strip()
        if not token:
            raise KeyError("job_id is required")

        with self._lock:
            job = self._jobs.get(token)
            if not isinstance(job, dict):
                raise KeyError(f"Job not found: {token}")

            job["status"] = "queued"
            job["updated_at"] = self._now_iso()
            job["started_at"] = None
            job["finished_at"] = None
            job["error"] = None
            job["result"] = None
            job["review"] = {
                "status": "not_ready",
                "decision": None,
                "reviewed_at": None,
                "reviewer_note": None,
                "applied_payload": None,
            }
            self._jobs[token] = job
            self._updated_at = str(job["updated_at"])
            self._save()
            self._queue.put(token)
            return dict(job)

    def _worker_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                job_id = self._queue.get(timeout=1.0)
            except queue.Empty:
                continue
            self._process_job(job_id)

    def _process_job(self, job_id: str) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if not isinstance(job, dict):
                return
            if str(job.get("status") or "") != "queued":
                return

            started_at = self._now_iso()
            job["status"] = "processing"
            job["started_at"] = started_at
            job["updated_at"] = started_at
            job["error"] = None
            self._jobs[job_id] = job
            self._updated_at = started_at
            self._save()

        try:
            uploaded_file = job.get("uploaded_file") or {}
            stored_path = self._ensure_upload_path(str(uploaded_file.get("stored_path") or ""))
            analysis = analyze_ingestion_attachment(
                stored_path=stored_path,
                original_file_name=str(uploaded_file.get("file_name") or stored_path.name),
                section=str(job.get("section") or ""),
                max_chars=self.max_chars,
            )
            extraction_status = str(analysis.get("extraction_status") or "failed").lower()
            status = "completed" if extraction_status == "ok" else "failed"
            error = analysis.get("extraction_error") if status == "failed" else None
        except Exception as exc:  # noqa: BLE001
            analysis = None
            status = "failed"
            error = str(exc)

        finished_at = self._now_iso()
        with self._lock:
            current = self._jobs.get(job_id)
            if not isinstance(current, dict):
                return

            current["status"] = status
            current["finished_at"] = finished_at
            current["updated_at"] = finished_at
            current["error"] = error
            current["result"] = analysis

            review = current.get("review")
            if not isinstance(review, dict):
                review = {}
            review["status"] = "pending_review" if status == "completed" else "not_ready"
            current["review"] = review

            self._jobs[job_id] = current
            self._updated_at = finished_at
            self._save()


_JOB_MANAGER: AttachmentAssistJobManager | None = None
_JOB_MANAGER_LOCK = threading.Lock()


def initialize_attachment_assist_job_manager(
    jobs_path: Path,
    uploads_root: Path,
    max_chars: int,
) -> AttachmentAssistJobManager:
    global _JOB_MANAGER
    with _JOB_MANAGER_LOCK:
        if _JOB_MANAGER is not None:
            return _JOB_MANAGER
        _JOB_MANAGER = AttachmentAssistJobManager(
            jobs_path=jobs_path,
            uploads_root=uploads_root,
            max_chars=max_chars,
        )
        _JOB_MANAGER.start()
        return _JOB_MANAGER


def get_attachment_assist_job_manager() -> AttachmentAssistJobManager | None:
    return _JOB_MANAGER


def shutdown_attachment_assist_job_manager() -> None:
    global _JOB_MANAGER
    with _JOB_MANAGER_LOCK:
        if _JOB_MANAGER is None:
            return
        _JOB_MANAGER.stop()
        _JOB_MANAGER = None
