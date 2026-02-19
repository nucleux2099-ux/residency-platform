from __future__ import annotations

import json
import re
import shlex
import shutil
import subprocess
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.services.patient_library import build_patient_catalog

MARKER_SUPPORTED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}
TEXT_EXTENSIONS = {".md", ".txt", ".csv", ".json", ".yaml", ".yml"}
LAB_ABNORMAL_PATTERNS = [
    re.compile(r"\((?:H|L|HH|LL)\)"),
    re.compile(r"\b(?:critical|abnormal|elevated|raised|deranged|high|low|markedly)\b", flags=re.IGNORECASE),
    re.compile(r"\b(?:h|l|hh|ll)\b", flags=re.IGNORECASE),
]
FILE_DATE_PATTERNS = [
    re.compile(r"(?<!\d)(?P<year>20\d{2})[-_.](?P<month>\d{1,2})[-_.](?P<day>\d{1,2})(?!\d)"),
    re.compile(r"(?<!\d)(?P<day>\d{1,2})[-_.](?P<month>\d{1,2})[-_.](?P<year>20\d{2})(?!\d)"),
]
NUMBER_PATTERN = re.compile(r"[-+]?\d+(?:\.\d+)?")
LAB_TREND_METRICS: list[dict[str, Any]] = [
    {
        "metric_key": "hb",
        "label": "Hemoglobin",
        "unit": "g/dL",
        "patterns": [re.compile(r"\b(?:hb|hgb|ha?emoglobin)\b", flags=re.IGNORECASE)],
        "normal_min": 10.0,
        "normal_max": 16.5,
    },
    {
        "metric_key": "wbc",
        "label": "WBC / TLC",
        "unit": "10^3/uL",
        "patterns": [re.compile(r"\b(?:wbc|tlc|total\s+leucocyte|total\s+leukocyte)\b", flags=re.IGNORECASE)],
        "normal_min": 4.0,
        "normal_max": 11.0,
    },
    {
        "metric_key": "platelets",
        "label": "Platelets",
        "unit": "10^3/uL",
        "patterns": [re.compile(r"\b(?:platelet(?:s)?|plt)\b", flags=re.IGNORECASE)],
        "normal_min": 150.0,
        "normal_max": 450.0,
    },
    {
        "metric_key": "crp",
        "label": "CRP",
        "unit": "mg/L",
        "patterns": [re.compile(r"\b(?:crp|c[\s-]?reactive\s+protein)\b", flags=re.IGNORECASE)],
        "normal_min": 0.0,
        "normal_max": 6.0,
    },
    {
        "metric_key": "bilirubin_total",
        "label": "Bilirubin Total",
        "unit": "mg/dL",
        "patterns": [re.compile(r"\b(?:total\s+bilirubin|bilirubin\s+total)\b", flags=re.IGNORECASE)],
        "normal_min": 0.2,
        "normal_max": 1.2,
    },
    {
        "metric_key": "ast",
        "label": "AST / SGOT",
        "unit": "U/L",
        "patterns": [re.compile(r"\b(?:ast|sgot)\b", flags=re.IGNORECASE)],
        "normal_min": 0.0,
        "normal_max": 40.0,
    },
    {
        "metric_key": "alt",
        "label": "ALT / SGPT",
        "unit": "U/L",
        "patterns": [re.compile(r"\b(?:alt|sgpt)\b", flags=re.IGNORECASE)],
        "normal_min": 0.0,
        "normal_max": 40.0,
    },
    {
        "metric_key": "alp",
        "label": "ALP",
        "unit": "U/L",
        "patterns": [re.compile(r"\b(?:alp|alkaline\s+phosphatase)\b", flags=re.IGNORECASE)],
        "normal_min": 44.0,
        "normal_max": 147.0,
    },
]


class PatientDocumentIndexer:
    def __init__(
        self,
        vault_root: Path,
        event_store_path: Path,
        index_path: Path,
        marker_command: str,
        scan_interval_sec: float,
        marker_timeout_sec: int,
        max_document_chars: int,
        binary_per_cycle_limit: int,
    ) -> None:
        self.vault_root = vault_root.resolve()
        self.event_store_path = event_store_path
        self.index_path = index_path
        self.marker_command = marker_command.strip() or "marker_single"
        self.scan_interval_sec = max(scan_interval_sec, 5.0)
        self.marker_timeout_sec = max(marker_timeout_sec, 10)
        self.max_document_chars = max(max_document_chars, 10_000)
        self.binary_per_cycle_limit = max(binary_per_cycle_limit, 1)
        self._marker_mode: str | None = None

        self._state_lock = threading.RLock()
        self._cycle_lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

        self._index: dict[str, Any] = {
            "version": 1,
            "updated_at": None,
            "last_cycle_started_at": None,
            "last_cycle_finished_at": None,
            "last_cycle_error": None,
            "documents": {},
        }

        self._load_index()

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    def _load_index(self) -> None:
        if not self.index_path.exists():
            return

        try:
            raw = self.index_path.read_text(encoding="utf-8")
            parsed = json.loads(raw)
        except (OSError, json.JSONDecodeError):
            return

        if not isinstance(parsed, dict):
            return

        documents = parsed.get("documents")
        if not isinstance(documents, dict):
            documents = {}

        with self._state_lock:
            self._index = {
                "version": 1,
                "updated_at": parsed.get("updated_at"),
                "last_cycle_started_at": parsed.get("last_cycle_started_at"),
                "last_cycle_finished_at": parsed.get("last_cycle_finished_at"),
                "last_cycle_error": parsed.get("last_cycle_error"),
                "documents": documents,
            }

    def _save_index(self) -> None:
        snapshot: dict[str, Any]
        with self._state_lock:
            snapshot = {
                "version": 1,
                "updated_at": self._index.get("updated_at"),
                "last_cycle_started_at": self._index.get("last_cycle_started_at"),
                "last_cycle_finished_at": self._index.get("last_cycle_finished_at"),
                "last_cycle_error": self._index.get("last_cycle_error"),
                "documents": self._index.get("documents", {}),
            }

        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        self.index_path.write_text(json.dumps(snapshot, ensure_ascii=True), encoding="utf-8")

    @staticmethod
    def _document_key(patient_key: str, file_id: str) -> str:
        return f"{patient_key}::{file_id}".lower()

    @staticmethod
    def _path_signature(path: Path) -> str | None:
        try:
            stat = path.stat()
        except OSError:
            return None
        return f"{stat.st_size}:{stat.st_mtime_ns}"

    @staticmethod
    def _is_searchable(file_item: dict[str, Any]) -> bool:
        extension = str(file_item.get("extension") or "").lower()
        if bool(file_item.get("is_text")):
            return True
        return extension in MARKER_SUPPORTED_EXTENSIONS

    @staticmethod
    def _coerce_text(text: str) -> str:
        return "\n".join(line.rstrip() for line in text.splitlines()).strip()

    def _extract_from_text_file(self, path: Path) -> tuple[str | None, str | None]:
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            return None, str(exc)
        return self._coerce_text(content), None

    def _extract_from_marker(self, path: Path) -> tuple[str | None, str | None]:
        base_command = shlex.split(self.marker_command)
        if not base_command:
            return None, "Marker command is empty"

        marker_binary = shutil.which(base_command[0])
        if marker_binary is None:
            return None, f"Marker command not found: {base_command[0]}"

        with tempfile.TemporaryDirectory(prefix="marker_extract_") as tmp_dir:
            mode = self._marker_mode or "flag_output_dir"
            command = (
                [marker_binary, *base_command[1:], str(path), "--output_dir", tmp_dir]
                if mode == "flag_output_dir"
                else [marker_binary, *base_command[1:], str(path), tmp_dir]
            )

            try:
                completed = subprocess.run(
                    command,
                    capture_output=True,
                    text=True,
                    timeout=self.marker_timeout_sec,
                    check=False,
                )
            except (OSError, subprocess.TimeoutExpired) as exc:
                return None, str(exc)

            if completed.returncode != 0:
                stderr = (completed.stderr or "").strip()
                stdout = (completed.stdout or "").strip()
                message = stderr or stdout or f"marker exited with code {completed.returncode}"

                # Detect CLI argument style mismatch only once, then reuse the right mode.
                if mode == "flag_output_dir" and any(
                    token in message.lower() for token in {"unrecognized arguments", "too few arguments", "usage:"}
                ):
                    fallback_command = [marker_binary, *base_command[1:], str(path), tmp_dir]
                    try:
                        completed = subprocess.run(
                            fallback_command,
                            capture_output=True,
                            text=True,
                            timeout=self.marker_timeout_sec,
                            check=False,
                        )
                    except (OSError, subprocess.TimeoutExpired) as exc:
                        return None, str(exc)

                    if completed.returncode != 0:
                        stderr = (completed.stderr or "").strip()
                        stdout = (completed.stdout or "").strip()
                        return None, stderr or stdout or f"marker exited with code {completed.returncode}"

                    self._marker_mode = "positional_output_dir"
                else:
                    return None, message
            else:
                self._marker_mode = "flag_output_dir"

            extracted = self._read_marker_output(Path(tmp_dir))
            if extracted:
                return extracted, None

            return None, "Marker returned success but no text output was produced"

    def _read_marker_output(self, output_dir: Path) -> str:
        text_candidates: list[str] = []

        for extension in ("*.md", "*.txt"):
            for candidate in output_dir.rglob(extension):
                try:
                    text = candidate.read_text(encoding="utf-8", errors="replace").strip()
                except OSError:
                    continue
                if text:
                    text_candidates.append(text)

        if text_candidates:
            best = max(text_candidates, key=len)
            return self._coerce_text(best)

        for candidate in output_dir.rglob("*.json"):
            try:
                payload = json.loads(candidate.read_text(encoding="utf-8", errors="replace"))
            except (OSError, json.JSONDecodeError):
                continue

            values = self._extract_text_values(payload)
            if values:
                return self._coerce_text("\n\n".join(values))

        return ""

    def _extract_text_values(self, payload: Any) -> list[str]:
        collected: list[str] = []

        if isinstance(payload, str):
            token = payload.strip()
            if token:
                collected.append(token)
            return collected

        if isinstance(payload, list):
            for item in payload:
                collected.extend(self._extract_text_values(item))
            return collected

        if isinstance(payload, dict):
            for key, value in payload.items():
                if isinstance(key, str) and key.lower() in {"text", "markdown", "content", "ocr_text"}:
                    collected.extend(self._extract_text_values(value))
                elif isinstance(value, (dict, list)):
                    collected.extend(self._extract_text_values(value))
            return collected

        return collected

    def _extract_from_pdftotext(self, path: Path) -> tuple[str | None, str | None]:
        command = shutil.which("pdftotext")
        if command is None:
            return None, "pdftotext command not available"

        try:
            completed = subprocess.run(
                [command, "-layout", str(path), "-"],
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return None, str(exc)

        if completed.returncode != 0:
            stderr = (completed.stderr or "").strip()
            stdout = (completed.stdout or "").strip()
            return None, stderr or stdout or f"pdftotext exited with code {completed.returncode}"

        text = self._coerce_text(completed.stdout or "")
        if not text:
            return None, "pdftotext produced empty output"
        return text, None

    def _extract_from_tesseract(self, path: Path) -> tuple[str | None, str | None]:
        command = shutil.which("tesseract")
        if command is None:
            return None, "tesseract command not available"

        try:
            completed = subprocess.run(
                [command, str(path), "stdout"],
                capture_output=True,
                text=True,
                timeout=90,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return None, str(exc)

        if completed.returncode != 0:
            stderr = (completed.stderr or "").strip()
            stdout = (completed.stdout or "").strip()
            return None, stderr or stdout or f"tesseract exited with code {completed.returncode}"

        text = self._coerce_text(completed.stdout or "")
        if not text:
            return None, "tesseract produced empty output"
        return text, None

    def _extract_document_text(self, path: Path, file_item: dict[str, Any]) -> tuple[str | None, str, str | None]:
        extension = str(file_item.get("extension") or "").lower()

        if bool(file_item.get("is_text")) or extension in TEXT_EXTENSIONS:
            text, error = self._extract_from_text_file(path)
            if text:
                return text, "native_text", None
            return None, "native_text", error or "Unable to read text file"

        if extension in MARKER_SUPPORTED_EXTENSIONS:
            text, marker_error = self._extract_from_marker(path)
            if text:
                return text, "marker", None

            if extension == ".pdf":
                fallback_text, fallback_error = self._extract_from_pdftotext(path)
                if fallback_text:
                    return fallback_text, "pdftotext", None
                return None, "marker", f"{marker_error or 'Marker extraction failed'}; {fallback_error or 'pdftotext failed'}"

            fallback_text, fallback_error = self._extract_from_tesseract(path)
            if fallback_text:
                return fallback_text, "tesseract", None

            return None, "marker", f"{marker_error or 'Marker extraction failed'}; {fallback_error or 'tesseract failed'}"

        return None, "unsupported", f"Unsupported extension for OCR indexing: {extension}"

    def _build_document_record(
        self,
        patient_card: dict[str, Any],
        file_item: dict[str, Any],
        signature: str,
        text: str,
        extractor: str,
    ) -> dict[str, Any]:
        truncated = len(text) > self.max_document_chars
        if truncated:
            text = text[: self.max_document_chars]

        return {
            "patient_key": patient_card.get("patient_key"),
            "patient_display_name": patient_card.get("display_name"),
            "study_id": patient_card.get("study_id"),
            "case_bucket": patient_card.get("case_bucket"),
            "svt_status": patient_card.get("svt_status"),
            "file_id": file_item.get("file_id"),
            "file_name": file_item.get("file_name"),
            "relative_path": file_item.get("relative_path"),
            "category": file_item.get("category"),
            "mime_type": file_item.get("mime_type"),
            "extension": file_item.get("extension"),
            "updated_at": file_item.get("updated_at"),
            "size_bytes": file_item.get("size_bytes"),
            "signature": signature,
            "status": "indexed",
            "error": None,
            "extractor": extractor,
            "indexed_at": self._now_iso(),
            "text": text,
            "text_chars": len(text),
            "truncated": truncated,
        }

    def _build_failure_record(
        self,
        patient_card: dict[str, Any],
        file_item: dict[str, Any],
        signature: str | None,
        extractor: str,
        error: str,
    ) -> dict[str, Any]:
        return {
            "patient_key": patient_card.get("patient_key"),
            "patient_display_name": patient_card.get("display_name"),
            "study_id": patient_card.get("study_id"),
            "case_bucket": patient_card.get("case_bucket"),
            "svt_status": patient_card.get("svt_status"),
            "file_id": file_item.get("file_id"),
            "file_name": file_item.get("file_name"),
            "relative_path": file_item.get("relative_path"),
            "category": file_item.get("category"),
            "mime_type": file_item.get("mime_type"),
            "extension": file_item.get("extension"),
            "updated_at": file_item.get("updated_at"),
            "size_bytes": file_item.get("size_bytes"),
            "signature": signature,
            "status": "failed",
            "error": error,
            "extractor": extractor,
            "indexed_at": self._now_iso(),
            "text": "",
            "text_chars": 0,
            "truncated": False,
        }

    def _build_pending_record(
        self,
        patient_card: dict[str, Any],
        file_item: dict[str, Any],
        signature: str | None,
        reason: str,
    ) -> dict[str, Any]:
        return {
            "patient_key": patient_card.get("patient_key"),
            "patient_display_name": patient_card.get("display_name"),
            "study_id": patient_card.get("study_id"),
            "case_bucket": patient_card.get("case_bucket"),
            "svt_status": patient_card.get("svt_status"),
            "file_id": file_item.get("file_id"),
            "file_name": file_item.get("file_name"),
            "relative_path": file_item.get("relative_path"),
            "category": file_item.get("category"),
            "mime_type": file_item.get("mime_type"),
            "extension": file_item.get("extension"),
            "updated_at": file_item.get("updated_at"),
            "size_bytes": file_item.get("size_bytes"),
            "signature": signature,
            "status": "pending",
            "error": reason,
            "extractor": "queued",
            "indexed_at": self._now_iso(),
            "text": "",
            "text_chars": 0,
            "truncated": False,
        }

    def run_index_cycle(self, force: bool = False, patient_key: str | None = None, file_id: str | None = None) -> dict[str, Any]:
        acquired = self._cycle_lock.acquire(blocking=False)
        if not acquired:
            return self.status()

        try:
            cycle_started = self._now_iso()
            with self._state_lock:
                self._index["last_cycle_started_at"] = cycle_started
                self._index["last_cycle_error"] = None

            catalog = build_patient_catalog(self.vault_root, self.event_store_path)
            target_patient = (patient_key or "").strip().lower()
            target_file = (file_id or "").strip().lower()

            with self._state_lock:
                documents = dict(self._index.get("documents", {}))

            all_searchable_keys: set[str] = set()
            binary_extractions_this_cycle = 0

            for entry in catalog:
                patient_card = entry.get("patient", {})
                files = entry.get("files", [])
                current_patient_key = str(patient_card.get("patient_key") or "").strip().lower()
                if not current_patient_key:
                    continue

                for file_item in files:
                    if not isinstance(file_item, dict):
                        continue

                    current_file_id = str(file_item.get("file_id") or "").strip().lower()
                    if not current_file_id:
                        continue

                    if not self._is_searchable(file_item):
                        continue

                    document_key = self._document_key(current_patient_key, current_file_id)
                    all_searchable_keys.add(document_key)

                    if target_patient and current_patient_key != target_patient:
                        continue
                    if target_file and current_file_id != target_file:
                        continue

                    relative_path = str(file_item.get("relative_path") or "").strip()
                    if not relative_path:
                        continue

                    path = (self.vault_root / relative_path).resolve()
                    if not path.exists() or not path.is_file() or not path.is_relative_to(self.vault_root):
                        documents[document_key] = self._build_failure_record(
                            patient_card=patient_card,
                            file_item=file_item,
                            signature=None,
                            extractor="none",
                            error="File is missing or outside vault root",
                        )
                        continue

                    signature = self._path_signature(path)
                    if signature is None:
                        continue

                    existing = documents.get(document_key)
                    if (
                        not force
                        and isinstance(existing, dict)
                        and str(existing.get("signature") or "") == signature
                        and str(existing.get("status") or "") == "indexed"
                    ):
                        # Refresh metadata without re-extracting text if file content didn't change.
                        existing.update(
                            {
                                "patient_display_name": patient_card.get("display_name"),
                                "study_id": patient_card.get("study_id"),
                                "case_bucket": patient_card.get("case_bucket"),
                                "svt_status": patient_card.get("svt_status"),
                                "category": file_item.get("category"),
                                "updated_at": file_item.get("updated_at"),
                                "size_bytes": file_item.get("size_bytes"),
                                "mime_type": file_item.get("mime_type"),
                                "extension": file_item.get("extension"),
                                "file_name": file_item.get("file_name"),
                                "relative_path": file_item.get("relative_path"),
                            }
                        )
                        documents[document_key] = existing
                        continue

                    is_binary_source = not bool(file_item.get("is_text"))
                    if (
                        is_binary_source
                        and not force
                        and not target_patient
                        and not target_file
                        and binary_extractions_this_cycle >= self.binary_per_cycle_limit
                    ):
                        documents[document_key] = self._build_pending_record(
                            patient_card=patient_card,
                            file_item=file_item,
                            signature=signature,
                            reason="Queued for upcoming cycle (binary extraction throttle)",
                        )
                        continue

                    text, extractor, error = self._extract_document_text(path, file_item)
                    if text:
                        documents[document_key] = self._build_document_record(
                            patient_card=patient_card,
                            file_item=file_item,
                            signature=signature,
                            text=text,
                            extractor=extractor,
                        )
                        if is_binary_source:
                            binary_extractions_this_cycle += 1
                    else:
                        documents[document_key] = self._build_failure_record(
                            patient_card=patient_card,
                            file_item=file_item,
                            signature=signature,
                            extractor=extractor,
                            error=error or "Extraction failed",
                        )
                        if is_binary_source:
                            binary_extractions_this_cycle += 1

            if not target_patient and not target_file:
                stale_keys = [key for key in documents if key not in all_searchable_keys]
                for stale_key in stale_keys:
                    documents.pop(stale_key, None)

            cycle_finished = self._now_iso()
            with self._state_lock:
                self._index["documents"] = documents
                self._index["updated_at"] = cycle_finished
                self._index["last_cycle_finished_at"] = cycle_finished
                self._index["last_cycle_error"] = None

            self._save_index()
            return self.status()

        except Exception as exc:  # noqa: BLE001
            cycle_finished = self._now_iso()
            with self._state_lock:
                self._index["last_cycle_finished_at"] = cycle_finished
                self._index["last_cycle_error"] = str(exc)
            self._save_index()
            return self.status()
        finally:
            self._cycle_lock.release()

    def _background_loop(self) -> None:
        self.run_index_cycle(force=False)
        while not self._stop_event.wait(self.scan_interval_sec):
            self.run_index_cycle(force=False)

    def start(self) -> None:
        with self._state_lock:
            if self._thread and self._thread.is_alive():
                return
            self._stop_event.clear()
            thread = threading.Thread(target=self._background_loop, name="patient-document-indexer", daemon=True)
            self._thread = thread
            thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        thread = self._thread
        if thread and thread.is_alive():
            thread.join(timeout=5)

    def status(self) -> dict[str, Any]:
        with self._state_lock:
            documents = list((self._index.get("documents") or {}).values())
            indexed_count = sum(1 for item in documents if str(item.get("status") or "") == "indexed")
            failed_count = sum(1 for item in documents if str(item.get("status") or "") == "failed")
            pending_count = max(len(documents) - indexed_count - failed_count, 0)
            return {
                "documents_total": len(documents),
                "documents_indexed": indexed_count,
                "documents_failed": failed_count,
                "documents_pending": pending_count,
                "last_cycle_started_at": self._index.get("last_cycle_started_at"),
                "last_cycle_finished_at": self._index.get("last_cycle_finished_at"),
                "last_cycle_error": self._index.get("last_cycle_error"),
                "updated_at": self._index.get("updated_at"),
                "scan_interval_sec": self.scan_interval_sec,
                "marker_command": self.marker_command,
                "binary_per_cycle_limit": self.binary_per_cycle_limit,
                "running": bool(self._thread and self._thread.is_alive()),
            }

    def search(self, query: str, patient_key: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        query_text = query.strip().lower()
        if not query_text:
            return []

        tokens = [token for token in query_text.split() if token]
        if not tokens:
            return []

        target_patient = (patient_key or "").strip().lower()

        with self._state_lock:
            documents = list((self._index.get("documents") or {}).values())

        matches: list[dict[str, Any]] = []
        for document in documents:
            if str(document.get("status") or "") != "indexed":
                continue

            doc_patient_key = str(document.get("patient_key") or "").lower()
            if target_patient and doc_patient_key != target_patient:
                continue

            text = str(document.get("text") or "")
            if not text:
                continue

            file_name = str(document.get("file_name") or "")
            search_blob = f"{file_name}\n{text}".lower()
            if not all(token in search_blob for token in tokens):
                continue

            score = 0
            for token in tokens:
                score += search_blob.count(token)
                if token in file_name.lower():
                    score += 5

            snippet = self._build_snippet(text, tokens)
            matches.append(
                {
                    "patient_key": document.get("patient_key"),
                    "patient_display_name": document.get("patient_display_name"),
                    "study_id": document.get("study_id"),
                    "case_bucket": document.get("case_bucket"),
                    "svt_status": document.get("svt_status"),
                    "file_id": document.get("file_id"),
                    "file_name": file_name,
                    "relative_path": document.get("relative_path"),
                    "category": document.get("category"),
                    "score": score,
                    "snippet": snippet,
                    "updated_at": document.get("updated_at"),
                }
            )

        matches.sort(key=lambda item: (int(item.get("score") or 0), str(item.get("updated_at") or "")), reverse=True)
        return matches[: max(1, min(limit, 200))]

    @staticmethod
    def _build_snippet(text: str, tokens: list[str], radius: int = 160) -> str:
        lowered = text.lower()
        first_index = -1
        for token in tokens:
            index = lowered.find(token)
            if index >= 0 and (first_index < 0 or index < first_index):
                first_index = index

        if first_index < 0:
            snippet = text[: radius * 2]
        else:
            start = max(first_index - radius, 0)
            end = min(first_index + radius, len(text))
            snippet = text[start:end]

        return " ".join(snippet.split())

    @staticmethod
    def _extract_first_text_line(text: str, max_chars: int = 220) -> str:
        for line in text.splitlines():
            cleaned = " ".join(line.split()).strip()
            if cleaned:
                return cleaned[:max_chars]
        return ""

    @staticmethod
    def _extract_abnormal_lines(text: str, limit: int = 4) -> list[str]:
        if not text:
            return []

        rows: list[str] = []
        seen: set[str] = set()
        for raw_line in text.splitlines():
            line = " ".join(raw_line.split()).strip()
            if not line:
                continue
            if len(line) > 260:
                line = f"{line[:257]}..."

            if not any(pattern.search(line) for pattern in LAB_ABNORMAL_PATTERNS):
                continue

            dedupe_key = line.lower()
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            rows.append(line)
            if len(rows) >= limit:
                break

        return rows

    @staticmethod
    def _extract_date_from_filename(file_name: str) -> str | None:
        for pattern in FILE_DATE_PATTERNS:
            match = pattern.search(file_name)
            if not match:
                continue
            try:
                year = int(match.group("year"))
                month = int(match.group("month"))
                day = int(match.group("day"))
                parsed = datetime(year=year, month=month, day=day, tzinfo=timezone.utc)
            except (ValueError, TypeError):
                continue
            return parsed.date().isoformat()
        return None

    @staticmethod
    def _parse_iso_datetime(value: str | None) -> datetime | None:
        if not value:
            return None
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None

    def _resolve_document_date(self, document: dict[str, Any]) -> str | None:
        file_name = str(document.get("file_name") or "")
        from_file = self._extract_date_from_filename(file_name)
        if from_file:
            return from_file

        for key in ("updated_at", "indexed_at"):
            parsed = self._parse_iso_datetime(str(document.get(key) or ""))
            if parsed is not None:
                return parsed.date().isoformat()

        return None

    @staticmethod
    def _parse_metric_value_from_line(line: str, match_end: int) -> float | None:
        if not line:
            return None

        candidates = list(NUMBER_PATTERN.finditer(line.replace(",", "")))
        if not candidates:
            return None

        prioritized = [candidate for candidate in candidates if candidate.start() >= match_end]
        ordered = prioritized or candidates

        for candidate in ordered:
            token = candidate.group(0)
            try:
                value = float(token)
            except ValueError:
                continue
            if abs(value) > 100000:
                continue
            return value

        return None

    @staticmethod
    def _classify_metric_value(metric: dict[str, Any], value: float) -> str:
        lower = metric.get("normal_min")
        upper = metric.get("normal_max")

        if isinstance(lower, (int, float)) and value < float(lower):
            return "low"
        if isinstance(upper, (int, float)) and value > float(upper):
            return "high"
        return "normal"

    def _extract_metric_point(self, metric: dict[str, Any], document: dict[str, Any], source_date: str | None) -> dict[str, Any] | None:
        if str(document.get("status") or "") != "indexed":
            return None

        text = str(document.get("text") or "")
        if not text:
            return None

        patterns = metric.get("patterns")
        if not isinstance(patterns, list) or not patterns:
            return None

        for raw_line in text.splitlines():
            line = " ".join(raw_line.split()).strip()
            if not line:
                continue

            for pattern in patterns:
                if not isinstance(pattern, re.Pattern):
                    continue
                match = pattern.search(line)
                if match is None:
                    continue

                value = self._parse_metric_value_from_line(line=line, match_end=match.end())
                if value is None:
                    continue

                rounded = round(value, 2)
                return {
                    "source_date": source_date,
                    "file_id": document.get("file_id"),
                    "file_name": document.get("file_name"),
                    "relative_path": document.get("relative_path"),
                    "value": rounded,
                    "status": self._classify_metric_value(metric, rounded),
                    "line": line[:280],
                }

        return None

    def get_extracted_document(self, patient_key: str, file_id: str, max_chars: int = 120000) -> dict[str, Any] | None:
        key = self._document_key(patient_key.strip().lower(), file_id.strip().lower())
        with self._state_lock:
            document = (self._index.get("documents") or {}).get(key)
            if not isinstance(document, dict):
                return None
            snapshot = dict(document)

        text = str(snapshot.get("text") or "")
        truncated = len(text) > max_chars
        if truncated:
            text = text[:max_chars]

        return {
            "patient_key": snapshot.get("patient_key"),
            "file_id": snapshot.get("file_id"),
            "file_name": snapshot.get("file_name"),
            "relative_path": snapshot.get("relative_path"),
            "category": snapshot.get("category"),
            "status": snapshot.get("status"),
            "error": snapshot.get("error"),
            "extractor": snapshot.get("extractor"),
            "indexed_at": snapshot.get("indexed_at"),
            "content": text,
            "content_truncated": truncated,
            "text_chars": snapshot.get("text_chars"),
            "mime_type": snapshot.get("mime_type"),
            "extension": snapshot.get("extension"),
        }

    def list_patient_documents(self, patient_key: str) -> list[dict[str, Any]]:
        target = patient_key.strip().lower()
        if not target:
            return []

        with self._state_lock:
            documents = list((self._index.get("documents") or {}).values())

        rows: list[dict[str, Any]] = []
        for document in documents:
            if str(document.get("patient_key") or "").strip().lower() != target:
                continue

            rows.append(
                {
                    "patient_key": document.get("patient_key"),
                    "file_id": document.get("file_id"),
                    "file_name": document.get("file_name"),
                    "relative_path": document.get("relative_path"),
                    "category": document.get("category"),
                    "status": document.get("status"),
                    "error": document.get("error"),
                    "extractor": document.get("extractor"),
                    "indexed_at": document.get("indexed_at"),
                    "updated_at": document.get("updated_at"),
                    "text_chars": document.get("text_chars"),
                    "truncated": document.get("truncated"),
                }
            )

        status_rank = {"indexed": 2, "pending": 1, "failed": 0}
        rows.sort(
            key=lambda item: (
                status_rank.get(str(item.get("status") or "").lower(), -1),
                str(item.get("updated_at") or ""),
                str(item.get("file_name") or "").lower(),
            ),
            reverse=True,
        )
        return rows

    def list_patient_lab_timeline(self, patient_key: str, limit: int = 80) -> list[dict[str, Any]]:
        target = patient_key.strip().lower()
        if not target:
            return []

        with self._state_lock:
            documents = list((self._index.get("documents") or {}).values())

        timeline: list[dict[str, Any]] = []
        for document in documents:
            if str(document.get("patient_key") or "").strip().lower() != target:
                continue
            if str(document.get("category") or "").strip().lower() != "lab_report":
                continue

            status = str(document.get("status") or "")
            text = str(document.get("text") or "") if status == "indexed" else ""
            highlights = self._extract_abnormal_lines(text)
            summary = self._extract_first_text_line(text)

            file_name = str(document.get("file_name") or "")
            lab_date = self._extract_date_from_filename(file_name)
            updated_at = str(document.get("updated_at") or "") or None
            indexed_at = str(document.get("indexed_at") or "") or None
            sort_date = lab_date or updated_at or indexed_at

            timeline.append(
                {
                    "patient_key": document.get("patient_key"),
                    "file_id": document.get("file_id"),
                    "file_name": file_name,
                    "relative_path": document.get("relative_path"),
                    "status": status,
                    "error": document.get("error"),
                    "extractor": document.get("extractor"),
                    "updated_at": updated_at,
                    "indexed_at": indexed_at,
                    "lab_date": lab_date,
                    "source_date": sort_date,
                    "summary": summary or None,
                    "abnormal_markers": len(highlights),
                    "highlight_lines": highlights,
                    "text_chars": int(document.get("text_chars") or 0),
                }
            )

        timeline.sort(
            key=lambda item: (
                str(item.get("source_date") or ""),
                str(item.get("updated_at") or ""),
                str(item.get("file_name") or "").lower(),
            ),
            reverse=True,
        )
        return timeline[: max(1, min(limit, 200))]

    def list_patient_lab_trends(self, patient_key: str, limit_reports: int = 120) -> dict[str, Any]:
        target = patient_key.strip().lower()
        if not target:
            return {"reports_considered": 0, "points_total": 0, "metrics": []}

        with self._state_lock:
            documents = list((self._index.get("documents") or {}).values())

        lab_documents: list[dict[str, Any]] = []
        for document in documents:
            if str(document.get("patient_key") or "").strip().lower() != target:
                continue
            if str(document.get("category") or "").strip().lower() != "lab_report":
                continue
            if str(document.get("status") or "").strip().lower() != "indexed":
                continue
            if not str(document.get("text") or "").strip():
                continue
            lab_documents.append(document)

        lab_documents.sort(
            key=lambda item: (
                str(self._resolve_document_date(item) or ""),
                str(item.get("updated_at") or ""),
                str(item.get("file_name") or "").lower(),
            ),
            reverse=True,
        )
        lab_documents = lab_documents[: max(1, min(limit_reports, 300))]

        points_by_metric: dict[str, list[dict[str, Any]]] = {str(metric["metric_key"]): [] for metric in LAB_TREND_METRICS}

        for document in lab_documents:
            source_date = self._resolve_document_date(document)
            for metric in LAB_TREND_METRICS:
                point = self._extract_metric_point(metric=metric, document=document, source_date=source_date)
                if point is None:
                    continue
                points_by_metric[str(metric["metric_key"])].append(point)

        metrics_payload: list[dict[str, Any]] = []
        total_points = 0

        for metric in LAB_TREND_METRICS:
            metric_key = str(metric["metric_key"])
            points = points_by_metric.get(metric_key, [])
            points.sort(
                key=lambda item: (
                    str(item.get("source_date") or ""),
                    str(item.get("file_name") or "").lower(),
                )
            )
            if not points:
                continue

            total_points += len(points)
            latest = points[-1]
            previous = points[-2] if len(points) > 1 else None
            delta = round(float(latest["value"]) - float(previous["value"]), 2) if previous else None

            if delta is None:
                trend_direction = "single"
            elif abs(delta) < 0.01:
                trend_direction = "flat"
            elif delta > 0:
                trend_direction = "up"
            else:
                trend_direction = "down"

            abnormal_points = sum(1 for point in points if str(point.get("status") or "") != "normal")
            metrics_payload.append(
                {
                    "metric_key": metric_key,
                    "label": metric.get("label"),
                    "unit": metric.get("unit"),
                    "points": points[-24:],
                    "points_count": len(points),
                    "abnormal_points": abnormal_points,
                    "latest_value": latest.get("value"),
                    "latest_status": latest.get("status"),
                    "latest_date": latest.get("source_date"),
                    "delta": delta,
                    "trend_direction": trend_direction,
                }
            )

        metrics_payload.sort(
            key=lambda item: (
                int(item.get("abnormal_points") or 0),
                int(item.get("points_count") or 0),
                str(item.get("label") or ""),
            ),
            reverse=True,
        )

        return {
            "reports_considered": len(lab_documents),
            "points_total": total_points,
            "metrics": metrics_payload,
        }

    def reindex(self, force: bool = True, patient_key: str | None = None, file_id: str | None = None) -> dict[str, Any]:
        return self.run_index_cycle(force=force, patient_key=patient_key, file_id=file_id)


_INDEXER: PatientDocumentIndexer | None = None
_INDEXER_LOCK = threading.Lock()


def initialize_patient_document_indexer(
    vault_root: Path,
    event_store_path: Path,
    index_path: Path,
    marker_command: str,
    scan_interval_sec: float,
    marker_timeout_sec: int,
    max_document_chars: int,
    binary_per_cycle_limit: int,
) -> PatientDocumentIndexer:
    global _INDEXER
    with _INDEXER_LOCK:
        if _INDEXER is not None:
            return _INDEXER

        _INDEXER = PatientDocumentIndexer(
            vault_root=vault_root,
            event_store_path=event_store_path,
            index_path=index_path,
            marker_command=marker_command,
            scan_interval_sec=scan_interval_sec,
            marker_timeout_sec=marker_timeout_sec,
            max_document_chars=max_document_chars,
            binary_per_cycle_limit=binary_per_cycle_limit,
        )
        _INDEXER.start()
        return _INDEXER


def get_patient_document_indexer() -> PatientDocumentIndexer | None:
    return _INDEXER


def shutdown_patient_document_indexer() -> None:
    global _INDEXER
    with _INDEXER_LOCK:
        if _INDEXER is None:
            return
        _INDEXER.stop()
        _INDEXER = None
