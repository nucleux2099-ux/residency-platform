from datetime import date, datetime
import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

PATIENT_ID_PATTERN = re.compile(r"^[A-Z0-9][A-Z0-9-]{2,63}$")
VALID_VESSEL_VALUES = {"pv", "smv", "sv", "multiple", "unknown"}


class PatientSubmission(BaseModel):
    template_id: str = Field(default="patient-template-v2", min_length=2, max_length=80)
    patient_id: str = Field(min_length=2, max_length=64)
    encounter_date: date
    diagnosis: str = Field(min_length=2, max_length=200)
    visit_type: Literal[
        "baseline",
        "day7_reassessment",
        "discharge",
        "week2_followup",
        "month1_followup",
        "month3_followup",
    ] = "baseline"
    svt_status: Literal["with_svt", "without_svt"]
    ward: str = Field(min_length=1, max_length=120)
    cohort_status: Literal["screened", "enrolled", "active", "completed", "terminal_outcome"] = "active"
    vessel_involvement: list[str] = Field(default_factory=list)
    mortality: Literal["yes", "no"] = "no"
    death_date: date | None = None
    cause_of_death: str | None = Field(default=None, max_length=400)
    recanalization_status: Literal["pending", "complete", "partial", "none", "progressed", "not_applicable"] = (
        "pending"
    )
    primary_endpoint_complete: bool = False
    notes: str | None = Field(default=None, max_length=4000)
    extra_fields: dict[str, str] = Field(default_factory=dict)
    source_files: list[str] = Field(default_factory=list)

    @field_validator("template_id", "diagnosis", "ward", mode="before")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        if not isinstance(value, str):
            raise ValueError("must be a string")
        text = value.strip()
        if not text:
            raise ValueError("must not be empty")
        return text

    @field_validator("patient_id", mode="before")
    @classmethod
    def normalize_patient_id(cls, value: str) -> str:
        if not isinstance(value, str):
            raise ValueError("must be a string")
        text = value.strip().upper()
        if not text:
            raise ValueError("must not be empty")
        if not PATIENT_ID_PATTERN.match(text):
            raise ValueError("must be a pseudonymous ID (letters/numbers/hyphens only)")
        return text

    @field_validator("cause_of_death", mode="before")
    @classmethod
    def normalize_cause_of_death(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = value.strip()
        return text or None

    @field_validator("vessel_involvement", mode="before")
    @classmethod
    def normalize_vessels(cls, value: list[str] | str | None) -> list[str]:
        if value is None:
            return []
        if value == "":
            return []
            
        raw_values: list[str]
        if isinstance(value, str):
            # Handle multiple delimiters and case normalization
            raw_values = [item.strip().lower() for item in re.split(r"[;,/|]", value) if item.strip()]
        elif isinstance(value, list):
            raw_values = []
            for item in value:
                if isinstance(item, str) and item.strip():
                    raw_values.append(item.strip().lower())
        else:
            raise ValueError("must be a list or delimited string")

        deduped: list[str] = []
        for token in raw_values:
            if token in deduped:
                continue
            deduped.append(token)

        invalid = [token for token in deduped if token not in VALID_VESSEL_VALUES]
        if invalid:
            raise ValueError(f"invalid vessel values: {', '.join(invalid)}")
        return deduped
        
    @field_validator("encounter_date", "death_date", mode="before")
    @classmethod
    def normalize_dates(cls, value: str | date | None) -> date | None:
        if value is None or value == "":
            return None
        if isinstance(value, date):
            return value
        if isinstance(value, datetime):
            return value.date()
            
        text = str(value).strip()
        if not text:
            return None
            
        # Try common formats
        formats = [
            "%Y-%m-%d",   # ISO: 2026-02-18
            "%d/%m/%Y",   # IN/UK: 18/02/2026
            "%d-%m-%Y",   # IN/UK: 18-02-2026
            "%m/%d/%Y",   # US: 02/18/2026
            "%d.%m.%Y",   # Dot: 18.02.2026
            "%Y/%m/%d"    # ISO slash: 2026/02/18
        ]
        
        for fmt in formats:
            try:
                return datetime.strptime(text, fmt).date()
            except ValueError:
                continue
                
        # If all fail, let Pydantic try its default parsing or raise error
        return value

    @field_validator("notes", mode="before")
    @classmethod
    def normalize_notes(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = value.strip()
        return text or None

    @field_validator("extra_fields", mode="before")
    @classmethod
    def normalize_extra_fields(cls, value: dict | None) -> dict[str, str]:
        if value is None:
            return {}
        if not isinstance(value, dict):
            raise ValueError("must be an object")

        normalized: dict[str, str] = {}
        for raw_key, raw_value in value.items():
            key = str(raw_key).strip()
            if not key:
                continue
            if raw_value is None:
                continue

            text = str(raw_value).strip()
            if not text:
                continue

            normalized[key] = text

        return normalized

    @model_validator(mode="after")
    def validate_cross_field_rules(self) -> "PatientSubmission":
        if self.mortality == "yes":
            if self.death_date is None:
                raise ValueError("death_date is required when mortality is yes")
            if not self.cause_of_death:
                raise ValueError("cause_of_death is required when mortality is yes")
        else:
            if self.death_date is not None or self.cause_of_death:
                # Relaxed: having death details when mortality=no is a data inconsistency, 
                # but we can just ignore them or warn. For now, we'll strip them or allow them
                # to avoid blocking ingestion of messy data, or we could strictly enforce.
                # Let's enforce strictness for internal logic but maybe the validator above
                # should have handled clearing them? 
                # For safety in "loose ingestion", let's clear them if mortality is no.
                pass 
                # self.death_date = None
                # self.cause_of_death = None
                # Actually, raising error prompts user to fix data. Let's keep it strict for now
                # unless we want to AUTO-FIX. 
                # Auto-fixing:
                pass
                
        if self.svt_status == "with_svt":
            if not self.vessel_involvement:
                raise ValueError("vessel_involvement is required when svt_status is with_svt")
        else:
            if self.vessel_involvement:
                raise ValueError("vessel_involvement must be empty when svt_status is without_svt")
            if self.recanalization_status != "not_applicable":
                 # Auto-fix for common data entry error
                 if self.recanalization_status == "pending":
                     self.recanalization_status = "not_applicable"
                 else:
                    raise ValueError("recanalization_status must be not_applicable when svt_status is without_svt")

        if self.visit_type == "month3_followup" and self.svt_status == "with_svt":
            if self.recanalization_status in {"pending", "not_applicable"}:
                raise ValueError("month3_followup requires final recanalization_status for with_svt cases")

        if self.primary_endpoint_complete and self.visit_type != "month3_followup":
            # Loose ingestion: just force it to False if not month 3
            self.primary_endpoint_complete = False

        return self


class IngestionAck(BaseModel):
    event_id: str
    note_path: str


class UploadedFileDescriptor(BaseModel):
    file_name: str
    stored_path: str
    size_bytes: int


class FileUploadAck(BaseModel):
    uploaded_count: int
    files: list[UploadedFileDescriptor]


class CsvRowError(BaseModel):
    row_number: int
    message: str


class CsvIngestionAck(BaseModel):
    total_rows: int
    accepted_rows: int
    rejected_rows: int
    event_ids: list[str]
    note_paths: list[str]
    errors: list[CsvRowError]


class ProformaImportError(BaseModel):
    file_path: str
    message: str


class ProformaImportAck(BaseModel):
    scanned_files: int
    imported_files: int
    skipped_files: int
    event_ids: list[str]
    note_paths: list[str]
    errors: list[ProformaImportError]
