import {
  AnalyticsSummary,
  ApiEnvelope,
  CohortAnalytics,
  CsvIngestionAck,
  DataQualityAnalytics,
  FileUploadAck,
  FollowupAnalytics,
  IngestionAttachmentAssistAck,
  IngestionAttachmentAssistJob,
  IngestionCaseDetail,
  IngestionCaseSummary,
  IngestionAck,
  PatientDocumentIndexStatus,
  PatientDocumentSearchHit,
  PatientExtractedDocument,
  PatientIndexedFileSummary,
  PatientLabTrendPayload,
  PatientLabTimelineItem,
  PatientFilePreview,
  PatientLibraryCard,
  PatientLibraryDetail,
  PatientSubmission,
  ProformaImportAck,
  TemplateDetail,
  TemplateDescriptor,
  VaultStreamEvent,
  VaultTreeNode
} from "./types";

export const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

console.log(`[API Config] Using Base URL: '${API_BASE_URL}'`);

async function getJson<T>(path: string): Promise<T> {
  const url = (`${API_BASE_URL}${path}`);
  console.log(`[API Request] Fetching: ${url}`);
  try {
    const res = await fetch(url, { cache: "no-store" });
    if (!res.ok) {
      console.error(`[API Error] ${res.status} ${res.statusText} for ${url}`);
      throw new Error(`Request failed: ${res.status}`);
    }
    const body = (await res.json()) as ApiEnvelope<T>;
    return body.data;
  } catch (err) {
    console.error(`[API Network Error] Failed to fetch ${url}:`, err);
    throw err;
  }
}

async function postFormData<T>(path: string, formData: FormData): Promise<T> {
  const res = await fetch(`${API_BASE_URL}${path}`, {
    method: "POST",
    body: formData
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `Request failed: ${res.status}`);
  }

  const body = (await res.json()) as ApiEnvelope<T>;
  return body.data;
}

export function fetchAnalyticsSummary() {
  return getJson<AnalyticsSummary>("/analytics/summary");
}

export function fetchAnalyticsCohort() {
  return getJson<CohortAnalytics>("/analytics/cohort");
}

export function fetchAnalyticsFollowups() {
  return getJson<FollowupAnalytics>("/analytics/followups");
}

export function fetchAnalyticsDataQuality() {
  return getJson<DataQualityAnalytics>("/analytics/data-quality");
}

export function fetchVaultTree() {
  return getJson<VaultTreeNode>("/vault/tree");
}

export function fetchVaultFolders() {
  return getJson<string[]>("/vault/folders");
}

export function fetchTemplates() {
  return getJson<TemplateDescriptor[]>("/templates");
}

export function fetchTemplateDetail(templateId: string) {
  return getJson<TemplateDetail>(`/templates/${encodeURIComponent(templateId)}`);
}

export function openVaultStream(
  onUpdate: (event: VaultStreamEvent) => void,
  onError?: () => void
): EventSource {
  const source = new EventSource(`${API_BASE_URL}/vault/stream`);

  source.addEventListener("vault_tree", (event) => {
    const messageEvent = event as MessageEvent<string>;
    const payload = JSON.parse(messageEvent.data) as VaultStreamEvent;
    onUpdate(payload);
  });

  if (onError) {
    source.onerror = () => onError();
  }

  return source;
}

export async function submitPatient(payload: PatientSubmission) {
  const res = await fetch(`${API_BASE_URL}/ingestion/patient`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify(payload)
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || "Failed to submit patient data");
  }

  return (await res.json()) as ApiEnvelope<IngestionAck>;
}

export async function uploadPatientFiles(files: File[], patientId?: string) {
  const formData = new FormData();
  for (const file of files) {
    formData.append("files", file);
  }

  if (patientId) {
    formData.append("patient_id", patientId);
  }

  return postFormData<FileUploadAck>("/ingestion/files", formData);
}

export async function assistIngestionAttachment(
  file: File,
  section: "lab" | "imaging",
  patientId?: string
) {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("section", section);
  if (patientId) {
    formData.append("patient_id", patientId);
  }

  return postFormData<IngestionAttachmentAssistAck>("/ingestion/attachment-assist", formData);
}

export async function createAttachmentAssistJob(
  file: File,
  section: "lab" | "imaging",
  patientId?: string
) {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("section", section);
  if (patientId) {
    formData.append("patient_id", patientId);
  }

  return postFormData<IngestionAttachmentAssistJob>("/ingestion/attachment-assist/jobs", formData);
}

export function fetchAttachmentAssistJobs(patientId?: string, status?: string, limit = 50) {
  const params = new URLSearchParams();
  params.set("limit", String(limit));
  if (patientId && patientId.trim()) {
    params.set("patient_id", patientId.trim());
  }
  if (status && status.trim()) {
    params.set("status", status.trim());
  }
  return getJson<IngestionAttachmentAssistJob[]>(`/ingestion/attachment-assist/jobs?${params.toString()}`);
}

export function fetchAttachmentAssistJob(jobId: string) {
  return getJson<IngestionAttachmentAssistJob>(`/ingestion/attachment-assist/jobs/${encodeURIComponent(jobId)}`);
}

export async function reviewAttachmentAssistJob(
  jobId: string,
  decision: "accepted" | "rejected",
  reviewerNote?: string,
  appliedPayload?: Record<string, unknown>
) {
  const res = await fetch(`${API_BASE_URL}/ingestion/attachment-assist/jobs/${encodeURIComponent(jobId)}/review`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify({
      decision,
      reviewer_note: reviewerNote,
      applied_payload: appliedPayload || {}
    })
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `Request failed: ${res.status}`);
  }

  const body = (await res.json()) as ApiEnvelope<IngestionAttachmentAssistJob>;
  return body.data;
}

export async function retryAttachmentAssistJob(jobId: string) {
  const res = await fetch(`${API_BASE_URL}/ingestion/attachment-assist/jobs/${encodeURIComponent(jobId)}/retry`, {
    method: "POST"
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `Request failed: ${res.status}`);
  }

  const body = (await res.json()) as ApiEnvelope<IngestionAttachmentAssistJob>;
  return body.data;
}

export async function submitPatientCsv(file: File) {
  const formData = new FormData();
  formData.append("file", file);
  return postFormData<CsvIngestionAck>("/ingestion/patient-csv", formData);
}

export async function importVaultProformas() {
  const res = await fetch(`${API_BASE_URL}/ingestion/import-proformas`, {
    method: "POST"
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || "Failed to import proformas");
  }

  const body = (await res.json()) as ApiEnvelope<ProformaImportAck>;
  return body.data;
}

export function fetchIngestionCases(query?: string, limit = 100) {
  const params = new URLSearchParams();
  params.set("limit", String(limit));
  if (query && query.trim()) {
    params.set("q", query.trim());
  }
  return getJson<IngestionCaseSummary[]>(`/ingestion/cases?${params.toString()}`);
}

export function fetchIngestionCase(patientId: string) {
  return getJson<IngestionCaseDetail>(`/ingestion/cases/${encodeURIComponent(patientId)}`);
}

export function fetchPatientLibraryCards(
  query?: string,
  svtStatus?: "with_svt" | "without_svt" | "unknown",
  caseBucket?: "active" | "completed",
  limit = 200
) {
  const params = new URLSearchParams();
  params.set("limit", String(limit));
  if (query && query.trim()) {
    params.set("q", query.trim());
  }
  if (svtStatus) {
    params.set("svt_status", svtStatus);
  }
  if (caseBucket) {
    params.set("case_bucket", caseBucket);
  }
  return getJson<PatientLibraryCard[]>(`/patients?${params.toString()}`);
}

export function fetchPatientLibraryDetail(patientKey: string) {
  return getJson<PatientLibraryDetail>(`/patients/${encodeURIComponent(patientKey)}`);
}

export function fetchPatientFilePreview(patientKey: string, fileId: string) {
  return getJson<PatientFilePreview>(
    `/patients/${encodeURIComponent(patientKey)}/files/${encodeURIComponent(fileId)}/preview`
  );
}

export function fetchPatientExtractedFile(patientKey: string, fileId: string, maxChars = 120000) {
  return getJson<PatientExtractedDocument>(
    `/patients/${encodeURIComponent(patientKey)}/files/${encodeURIComponent(fileId)}/extracted?max_chars=${maxChars}`
  );
}

export function fetchPatientIndexedFiles(patientKey: string) {
  return getJson<PatientIndexedFileSummary[]>(`/patients/${encodeURIComponent(patientKey)}/index-files`);
}

export function fetchPatientLabTimeline(patientKey: string, limit = 80) {
  return getJson<PatientLabTimelineItem[]>(
    `/patients/${encodeURIComponent(patientKey)}/lab-timeline?limit=${limit}`
  );
}

export function fetchPatientLabTrends(patientKey: string, limitReports = 120) {
  return getJson<PatientLabTrendPayload>(
    `/patients/${encodeURIComponent(patientKey)}/lab-trends?limit_reports=${limitReports}`
  );
}

export function fetchPatientDocumentSearch(query: string, patientKey?: string, limit = 50) {
  const params = new URLSearchParams();
  params.set("q", query);
  params.set("limit", String(limit));
  if (patientKey) {
    params.set("patient_key", patientKey);
  }
  return getJson<PatientDocumentSearchHit[]>(`/patients/search?${params.toString()}`);
}

export function fetchPatientDocumentIndexStatus() {
  return getJson<PatientDocumentIndexStatus>("/patients/index/status");
}

export async function triggerPatientDocumentReindex(force = true, patientKey?: string, fileId?: string) {
  const params = new URLSearchParams();
  params.set("force", String(force));
  if (patientKey) {
    params.set("patient_key", patientKey);
  }
  if (fileId) {
    params.set("file_id", fileId);
  }

  const res = await fetch(`${API_BASE_URL}/patients/index/reindex?${params.toString()}`, {
    method: "POST"
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `Request failed: ${res.status}`);
  }

  const body = (await res.json()) as ApiEnvelope<PatientDocumentIndexStatus>;
  return body.data;
}

export function getPatientFileUrl(patientKey: string, fileId: string) {
  return `${API_BASE_URL}/patients/${encodeURIComponent(patientKey)}/files/${encodeURIComponent(fileId)}`;
}
