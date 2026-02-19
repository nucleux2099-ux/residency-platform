from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_VAULT_ROOT = PROJECT_ROOT.parent
DEFAULT_TEMPLATES_DIR = PROJECT_ROOT / "packages" / "shared" / "templates"
DEFAULT_EVENT_STORE = PROJECT_ROOT / "apps" / "api" / "data" / "patient_events.jsonl"
DEFAULT_UPLOADS_DIR = PROJECT_ROOT / "apps" / "api" / "data" / "uploads"
DEFAULT_AUTO_NOTES_DIR = DEFAULT_VAULT_ROOT / "05-Logs" / "Auto-Patient-Entries"
DEFAULT_DOCUMENT_INDEX_PATH = PROJECT_ROOT / "apps" / "api" / "data" / "patient_document_index.json"
DEFAULT_ATTACHMENT_ASSIST_JOBS_PATH = PROJECT_ROOT / "apps" / "api" / "data" / "attachment_assist_jobs.json"


class Settings(BaseSettings):
    api_host: str = "127.0.0.1"
    api_port: int = 8000
    vault_root: Path = DEFAULT_VAULT_ROOT
    shared_templates_dir: Path = DEFAULT_TEMPLATES_DIR
    event_store_path: Path = DEFAULT_EVENT_STORE
    uploads_dir: Path = DEFAULT_UPLOADS_DIR
    auto_notes_dir: Path = DEFAULT_AUTO_NOTES_DIR
    document_index_path: Path = DEFAULT_DOCUMENT_INDEX_PATH
    attachment_assist_jobs_path: Path = DEFAULT_ATTACHMENT_ASSIST_JOBS_PATH
    document_scan_interval_sec: float = 90.0
    marker_command: str = "marker_single"
    marker_timeout_sec: int = 60
    document_max_chars: int = 500000
    document_binary_per_cycle_limit: int = 6
    cohort_target: int = 32
    tree_max_depth: int = 4
    vault_watch_interval_sec: float = 2.0

    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def vault_root_path(self) -> Path:
        return self.vault_root

    @property
    def templates_path(self) -> Path:
        return self.shared_templates_dir

    @property
    def event_store(self) -> Path:
        return self.event_store_path

    @property
    def uploads_root(self) -> Path:
        return self.uploads_dir

    @property
    def auto_notes_root(self) -> Path:
        return self.auto_notes_dir

    @property
    def document_index(self) -> Path:
        return self.document_index_path

    @property
    def attachment_assist_jobs(self) -> Path:
        return self.attachment_assist_jobs_path


settings = Settings()
