export interface ApiEnvelope<T> {
  version: "v1";
  ts: string;
  data: T;
}

export interface AnalyticsSummary {
  cohort_target: number;
  total_patients: number;
  enrolled_patients: number;
  active_patients: number;
  completed_patients: number;
  terminal_outcomes: number;
  svt_patients: number;
  non_svt_patients: number;
  endpoint_completed: number;
  endpoint_completion_rate: number;
  followups_overdue: number;
  followups_due_soon: number;
  average_completeness: number;
  total_submissions: number;
}

export interface VaultTreeNode {
  name: string;
  path: string;
  is_dir: boolean;
  children: VaultTreeNode[];
}

export interface VaultStreamEvent {
  signature: string;
  folders: string[];
  updated_at: string;
}

export interface PatientSubmission {
  template_id?: string;
  patient_id: string;
  encounter_date: string;
  diagnosis: string;
  visit_type:
    | "baseline"
    | "day7_reassessment"
    | "discharge"
    | "week2_followup"
    | "month1_followup"
    | "month3_followup";
  svt_status: "with_svt" | "without_svt";
  ward: string;
  cohort_status: "screened" | "enrolled" | "active" | "completed" | "terminal_outcome";
  vessel_involvement?: Array<"pv" | "smv" | "sv" | "multiple" | "unknown">;
  mortality?: "yes" | "no";
  death_date?: string;
  cause_of_death?: string;
  recanalization_status?: "pending" | "complete" | "partial" | "none" | "progressed" | "not_applicable";
  primary_endpoint_complete?: boolean;
  notes?: string;
  extra_fields?: Record<string, string>;
  source_files?: string[];
}

export interface TemplateDescriptor {
  template_id: string;
  version: number;
  title: string;
  required_fields: string[];
}

export interface TemplateFieldDescriptor {
  key: string;
  label: string;
  type: "string" | "date" | "enum" | "enum_list" | "object" | string;
  options?: Array<string | boolean>;
  required_when?: Record<string, string | boolean>;
}

export interface TemplateDetail extends TemplateDescriptor {
  fields: TemplateFieldDescriptor[];
}

export interface CohortPatientRow {
  patient_id: string;
  cohort_status: string;
  svt_status: "with_svt" | "without_svt";
  ward: string;
  diagnosis: string;
  latest_visit: string;
  last_encounter_date: string | null;
  event_count: number;
  visits_completed: string[];
  missing_required_visits: string[];
  completeness_pct: number;
  recanalization_status: string;
  primary_endpoint_complete: boolean;
  mortality: "yes" | "no";
  death_date: string | null;
  cause_of_death: string | null;
  vessel_involvement: string[];
  template_id: string;
}

export interface CohortAnalytics {
  target: number;
  enrolled: number;
  active: number;
  completed: number;
  terminal_outcomes: number;
  patients: CohortPatientRow[];
}

export interface FollowupItem {
  patient_id: string;
  cohort_status: string;
  svt_status: "with_svt" | "without_svt";
  last_encounter_date: string | null;
  next_visit: string | null;
  due_date: string | null;
  status: "overdue" | "due_soon" | "scheduled" | "complete" | "insufficient_data";
  days_until_due: number | null;
  days_overdue: number;
}

export interface FollowupAnalytics {
  overdue_count: number;
  due_soon_count: number;
  items: FollowupItem[];
}

export interface DataQualityItem {
  patient_id: string;
  template_id: string;
  completeness_pct: number;
  missing_required_visits: string[];
  issue_count: number;
  issues: string[];
}

export interface DataQualityAnalytics {
  average_completeness: number;
  patients_with_issues: number;
  issues_by_type: Record<string, number>;
  items: DataQualityItem[];
}

export interface UploadedFileDescriptor {
  file_name: string;
  stored_path: string;
  size_bytes: number;
}

export interface FileUploadAck {
  uploaded_count: number;
  files: UploadedFileDescriptor[];
}

export interface IngestionAssistLabEntry {
  date: string;
  parameter: string;
  value: string;
}

export interface IngestionAssistImagingEntry {
  date: string;
  modality: string;
  findings: string;
}

export interface IngestionAssistSuggestions {
  lab_entries: IngestionAssistLabEntry[];
  imaging_entries: IngestionAssistImagingEntry[];
  extra_fields: Record<string, string>;
  review_notes: string[];
}

export interface IngestionAttachmentAssistAck {
  uploaded_file: UploadedFileDescriptor;
  section: "lab" | "imaging" | string;
  extraction_status: "ok" | "failed" | string;
  extractor: string;
  extraction_error: string | null;
  extracted_text_preview: string;
  suggestions: IngestionAssistSuggestions;
}

export interface CsvRowError {
  row_number: number;
  message: string;
}

export interface CsvIngestionAck {
  total_rows: number;
  accepted_rows: number;
  rejected_rows: number;
  event_ids: string[];
  note_paths: string[];
  errors: CsvRowError[];
}

export interface IngestionAck {
  event_id: string;
  note_path: string;
}

export interface ProformaImportError {
  file_path: string;
  message: string;
}

export interface ProformaImportAck {
  scanned_files: number;
  imported_files: number;
  skipped_files: number;
  event_ids: string[];
  note_paths: string[];
  errors: ProformaImportError[];
}

export interface IngestionCaseSummary {
  patient_id: string;
  event_id: string;
  encounter_date: string | null;
  visit_type: string;
  svt_status: string;
  cohort_status: string;
  diagnosis: string;
  ward: string;
  template_id: string;
  updated_at: string | null;
  event_count: number;
}

export interface IngestionCaseDetail {
  summary: IngestionCaseSummary;
  payload: Record<string, unknown>;
  history: IngestionCaseSummary[];
}

export interface PatientLibraryCard {
  patient_key: string;
  display_name: string;
  study_id: string | null;
  svt_status: "with_svt" | "without_svt" | "unknown";
  cohort_folder: string;
  case_bucket: "active" | "completed";
  folder_path: string;
  diagnosis: string | null;
  cohort_status: string | null;
  latest_visit: string | null;
  last_encounter_date: string | null;
  last_updated_at: string | null;
  template_id: string | null;
  ward: string | null;
  file_count: number;
  note_count: number;
  lab_report_count: number;
  attachment_count: number;
  selected_note_file_id: string | null;
}

export interface PatientLibraryFile {
  file_id: string;
  file_name: string;
  relative_path: string;
  extension: string;
  mime_type: string;
  category: "proforma" | "note" | "lab_report" | "imaging" | "discharge" | "attachment";
  size_bytes: number;
  updated_at: string | null;
  is_text: boolean;
}

export interface PatientLibraryEvent {
  patient_id: string;
  diagnosis: string | null;
  cohort_status: string | null;
  visit_type: string | null;
  svt_status: string | null;
  encounter_date: string | null;
  updated_at: string;
  template_id: string | null;
  ward: string | null;
}

export interface PatientLibraryDetail {
  patient: PatientLibraryCard;
  files: PatientLibraryFile[];
  notes: PatientLibraryFile[];
  lab_reports: PatientLibraryFile[];
  event_history: PatientLibraryEvent[];
}

export interface PatientFilePreview {
  file: PatientLibraryFile;
  preview_supported: boolean;
  content: string;
  truncated: boolean;
  message: string | null;
}

export interface PatientDocumentSearchHit {
  patient_key: string;
  patient_display_name: string | null;
  study_id: string | null;
  case_bucket: "active" | "completed" | null;
  svt_status: "with_svt" | "without_svt" | "unknown" | null;
  file_id: string;
  file_name: string;
  relative_path: string;
  category: string;
  score: number;
  snippet: string;
  updated_at: string | null;
}

export interface PatientDocumentIndexStatus {
  documents_total: number;
  documents_indexed: number;
  documents_failed: number;
  documents_pending: number;
  last_cycle_started_at: string | null;
  last_cycle_finished_at: string | null;
  last_cycle_error: string | null;
  updated_at: string | null;
  scan_interval_sec: number;
  marker_command: string;
  binary_per_cycle_limit: number;
  running: boolean;
}

export interface PatientExtractedDocument {
  patient_key: string;
  file_id: string;
  file_name: string;
  relative_path: string;
  category: string;
  status: "indexed" | "failed" | "pending" | string;
  error: string | null;
  extractor: string;
  indexed_at: string | null;
  content: string;
  content_truncated: boolean;
  text_chars: number;
  mime_type: string | null;
  extension: string | null;
}

export interface PatientIndexedFileSummary {
  patient_key: string;
  file_id: string;
  file_name: string;
  relative_path: string;
  category: string;
  status: "indexed" | "failed" | "pending" | string;
  error: string | null;
  extractor: string;
  indexed_at: string | null;
  updated_at: string | null;
  text_chars: number;
  truncated: boolean;
}

export interface PatientLabTimelineItem {
  patient_key: string;
  file_id: string;
  file_name: string;
  relative_path: string;
  status: "indexed" | "failed" | "pending" | string;
  error: string | null;
  extractor: string;
  updated_at: string | null;
  indexed_at: string | null;
  lab_date: string | null;
  source_date: string | null;
  summary: string | null;
  abnormal_markers: number;
  highlight_lines: string[];
  text_chars: number;
}

export interface PatientLabTrendPoint {
  source_date: string | null;
  file_id: string;
  file_name: string;
  relative_path: string;
  value: number;
  status: "high" | "low" | "normal" | string;
  line: string | null;
}

export interface PatientLabTrendMetric {
  metric_key: string;
  label: string;
  unit: string;
  points: PatientLabTrendPoint[];
  points_count: number;
  abnormal_points: number;
  latest_value: number;
  latest_status: "high" | "low" | "normal" | string;
  latest_date: string | null;
  delta: number | null;
  trend_direction: "up" | "down" | "flat" | "single" | string;
}

export interface PatientLabTrendPayload {
  reports_considered: number;
  points_total: number;
  metrics: PatientLabTrendMetric[];
}
