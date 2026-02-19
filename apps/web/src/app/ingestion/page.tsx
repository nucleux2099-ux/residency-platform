"use client";

import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import {
  createAttachmentAssistJob,
  fetchAttachmentAssistJob,
  fetchIngestionCase,
  fetchIngestionCases,
  fetchTemplates,
  importVaultProformas,
  reviewAttachmentAssistJob,
  retryAttachmentAssistJob,
  submitPatient,
  submitPatientCsv,
  uploadPatientFiles
} from "@/lib/api";
import { PageHeader } from "@/components/ui/PageHeader";
import {
  CsvIngestionAck,
  IngestionAttachmentAssistJob,
  IngestionCaseDetail,
  IngestionCaseSummary,
  ProformaImportAck,
  TemplateDescriptor
} from "@/lib/types";

type WorkflowPane = "wizard" | "cases" | "import" | "csv";
type AttachmentAssistSection = "lab" | "imaging";

type VisitType =
  | "baseline"
  | "day7_reassessment"
  | "discharge"
  | "week2_followup"
  | "month1_followup"
  | "month3_followup";

type SvtStatus = "with_svt" | "without_svt";
type CohortStatus = "screened" | "enrolled" | "active" | "completed" | "terminal_outcome";
type MortalityStatus = "yes" | "no";
type RecanalizationStatus = "pending" | "complete" | "partial" | "none" | "progressed" | "not_applicable";

interface WizardState {
  template_id: string;
  patient_id: string;
  encounter_date: string;
  diagnosis: string;
  visit_type: VisitType;
  svt_status: SvtStatus;
  vessel_involvement: string;
  ward: string;
  cohort_status: CohortStatus;
  mortality: MortalityStatus;
  death_date: string;
  cause_of_death: string;
  recanalization_status: RecanalizationStatus;
  primary_endpoint_complete: boolean;
  notes: string;
  extra_fields: Record<string, string>;
}

interface MetricEntry {
  id: string;
  date: string;
  parameter: string;
  value: string;
}

interface ImagingEntry {
  id: string;
  date: string;
  modality: string;
  findings: string;
}

interface InterventionEntry {
  id: string;
  date: string;
  intervention: string;
  indication: string;
  remarks: string;
}

interface FlagWithDuration {
  label: string;
  key: string;
  durationKey: string;
}

interface SavedDraft {
  id: string;
  label: string;
  saved_at: string;
  step_index: number;
  wizard: WizardState;
  lab_rows: MetricEntry[];
  imaging_rows: ImagingEntry[];
  intervention_rows: InterventionEntry[];
}

const DRAFT_STORAGE_KEY = "residency.ingestion.drafts.v1";

const WIZARD_STEPS = [
  { title: "Demographics", description: "Study basics, patient demographics, addictions" },
  { title: "Clinical Profile", description: "Symptoms, comorbidities, etiology, AP severity" },
  { title: "Investigations", description: "Labs, imaging, SVT mapping, vascular findings" },
  { title: "Management", description: "Treatment, interventions, anticoagulation, outcomes" },
  { title: "Follow-up & Review", description: "Follow-up status, attachments, final QA" }
];

const FEATURE_FLAGS: FlagWithDuration[] = [
  { label: "Vomiting", key: "clinical_details__vomiting", durationKey: "clinical_details__vomiting_duration" },
  { label: "Fever", key: "clinical_details__fever", durationKey: "clinical_details__fever_duration" },
  {
    label: "Abdominal Distension",
    key: "clinical_details__abdominal_distension",
    durationKey: "clinical_details__abdominal_distension_duration"
  },
  { label: "Jaundice", key: "clinical_details__jaundice", durationKey: "clinical_details__jaundice_duration" },
  { label: "Chest Pain", key: "clinical_details__chest_pain", durationKey: "clinical_details__chest_pain_duration" },
  { label: "Dyspnoea", key: "clinical_details__dyspnoea", durationKey: "clinical_details__dyspnoea_duration" },
  {
    label: "Hematemesis",
    key: "clinical_details__hematemesis",
    durationKey: "clinical_details__hematemesis_duration"
  },
  {
    label: "Melena / Haematochezia",
    key: "clinical_details__melena_haematochezia",
    durationKey: "clinical_details__melena_haematochezia_duration"
  },
  { label: "Ascites", key: "clinical_details__ascites", durationKey: "clinical_details__ascites_duration" },
  {
    label: "Splenomegaly",
    key: "clinical_details__splenomegaly",
    durationKey: "clinical_details__splenomegaly_duration"
  }
];

const COMORBIDITY_FLAGS: FlagWithDuration[] = [
  { label: "DM", key: "comorbidities__dm", durationKey: "comorbidities__dm_duration" },
  { label: "HTN", key: "comorbidities__htn", durationKey: "comorbidities__htn_duration" },
  { label: "CAD", key: "comorbidities__cad", durationKey: "comorbidities__cad_duration" },
  { label: "Obesity", key: "comorbidities__obesity", durationKey: "comorbidities__obesity_duration" },
  { label: "COPD", key: "comorbidities__copd", durationKey: "comorbidities__copd_duration" },
  { label: "CLD", key: "comorbidities__cld", durationKey: "comorbidities__cld_duration" },
  {
    label: "Thyroid Disorder",
    key: "comorbidities__thyroid_disorder",
    durationKey: "comorbidities__thyroid_disorder_duration"
  },
  {
    label: "Known Coagulopathy",
    key: "comorbidities__known_coagulopathy_disorder",
    durationKey: "comorbidities__known_coagulopathy_disorder_duration"
  }
];

const YES_NO_OPTIONS = [
  { value: "", label: "--" },
  { value: "yes", label: "Yes" },
  { value: "no", label: "No" }
];

const INITIAL_WIZARD_STATE: WizardState = {
  template_id: "patient-proforma-v3",
  patient_id: "",
  encounter_date: "",
  diagnosis: "",
  visit_type: "baseline",
  svt_status: "without_svt",
  vessel_involvement: "",
  ward: "Gastro Surgery Ward",
  cohort_status: "active",
  mortality: "no",
  death_date: "",
  cause_of_death: "",
  recanalization_status: "not_applicable",
  primary_endpoint_complete: false,
  notes: "",
  extra_fields: {}
};

function makeRowId() {
  return `row_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
}

function createMetricRow(): MetricEntry {
  return { id: makeRowId(), date: "", parameter: "", value: "" };
}

function createImagingRow(): ImagingEntry {
  return { id: makeRowId(), date: "", modality: "", findings: "" };
}

function createInterventionRow(): InterventionEntry {
  return { id: makeRowId(), date: "", intervention: "", indication: "", remarks: "" };
}

function toDisplayLabel(token: string) {
  return token
    .replaceAll("__", " - ")
    .replaceAll("_", " ")
    .replace(/\b\w/g, (match) => match.toUpperCase());
}

function asString(value: unknown, fallback = ""): string {
  if (typeof value === "string") {
    return value;
  }
  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  return fallback;
}

function asBoolean(value: unknown, fallback = false): boolean {
  if (typeof value === "boolean") {
    return value;
  }
  if (typeof value === "string") {
    const text = value.trim().toLowerCase();
    if (["true", "1", "yes", "y"].includes(text)) {
      return true;
    }
    if (["false", "0", "no", "n"].includes(text)) {
      return false;
    }
  }
  return fallback;
}

function parseJsonRows<T>(value: string | undefined): T[] {
  if (!value) {
    return [];
  }
  try {
    const parsed = JSON.parse(value) as unknown;
    if (Array.isArray(parsed)) {
      return parsed as T[];
    }
  } catch {
    return [];
  }
  return [];
}

function normalizeCaseRows(
  payload: Record<string, unknown>
): { extra: Record<string, string>; labRows: MetricEntry[]; imagingRows: ImagingEntry[]; interventionRows: InterventionEntry[] } {
  const payloadExtra = payload.extra_fields;
  const extra: Record<string, string> = {};

  if (payloadExtra && typeof payloadExtra === "object") {
    for (const [rawKey, rawValue] of Object.entries(payloadExtra as Record<string, unknown>)) {
      const key = rawKey.trim();
      if (!key) {
        continue;
      }
      const text = asString(rawValue).trim();
      if (!text) {
        continue;
      }
      extra[key] = text;
    }
  }

  const parsedLabs = parseJsonRows<MetricEntry>(extra.investigations__laboratory_entries_json);
  const parsedImaging = parseJsonRows<ImagingEntry>(extra.investigations__imaging_entries_json);
  const parsedInterventions = parseJsonRows<InterventionEntry>(extra.management__other_interventions_json);

  delete extra.investigations__laboratory_entries_json;
  delete extra.investigations__imaging_entries_json;
  delete extra.management__other_interventions_json;

  const labRows = parsedLabs.length > 0 ? parsedLabs.map((row) => ({ ...row, id: row.id || makeRowId() })) : [createMetricRow()];
  const imagingRows =
    parsedImaging.length > 0 ? parsedImaging.map((row) => ({ ...row, id: row.id || makeRowId() })) : [createImagingRow()];
  const interventionRows =
    parsedInterventions.length > 0
      ? parsedInterventions.map((row) => ({ ...row, id: row.id || makeRowId() }))
      : [createInterventionRow()];

  return { extra, labRows, imagingRows, interventionRows };
}

function mergeExtraFields(
  wizard: WizardState,
  labRows: MetricEntry[],
  imagingRows: ImagingEntry[],
  interventionRows: InterventionEntry[]
): Record<string, string> {
  const extra = { ...wizard.extra_fields };

  const cleanLab = labRows.filter((row) => row.date || row.parameter || row.value);
  const cleanImaging = imagingRows.filter((row) => row.date || row.modality || row.findings);
  const cleanInterventions = interventionRows.filter(
    (row) => row.date || row.intervention || row.indication || row.remarks
  );

  if (cleanLab.length > 0) {
    extra.investigations__laboratory_entries_json = JSON.stringify(cleanLab);
  }
  if (cleanImaging.length > 0) {
    extra.investigations__imaging_entries_json = JSON.stringify(cleanImaging);
  }
  if (cleanInterventions.length > 0) {
    extra.management__other_interventions_json = JSON.stringify(cleanInterventions);
  }

  return extra;
}

function getDraftIdFromWizard(wizard: WizardState): string {
  const patientId = wizard.patient_id.trim().toUpperCase();
  if (patientId) {
    return patientId;
  }
  return "WORKING-DRAFT";
}

function readSavedDrafts(): SavedDraft[] {
  if (typeof window === "undefined") {
    return [];
  }

  try {
    const raw = window.localStorage.getItem(DRAFT_STORAGE_KEY);
    if (!raw) {
      return [];
    }
    const parsed = JSON.parse(raw) as unknown;
    if (!Array.isArray(parsed)) {
      return [];
    }
    return parsed.filter((item): item is SavedDraft => Boolean(item && typeof item === "object"));
  } catch {
    return [];
  }
}

function writeSavedDrafts(drafts: SavedDraft[]) {
  if (typeof window === "undefined") {
    return;
  }
  window.localStorage.setItem(DRAFT_STORAGE_KEY, JSON.stringify(drafts));
}

export default function IngestionPage() {
  const [pane, setPane] = useState<WorkflowPane>("wizard");
  const [wizard, setWizard] = useState<WizardState>(INITIAL_WIZARD_STATE);
  const [stepIndex, setStepIndex] = useState(0);
  const [status, setStatus] = useState("Idle");
  const [submitting, setSubmitting] = useState(false);

  const [templates, setTemplates] = useState<TemplateDescriptor[]>([]);
  const [importStatus, setImportStatus] = useState("Idle");
  const [importResult, setImportResult] = useState<ProformaImportAck | null>(null);

  const [csvStatus, setCsvStatus] = useState("Idle");
  const [csvResult, setCsvResult] = useState<CsvIngestionAck | null>(null);

  const [attachments, setAttachments] = useState<File[]>([]);
  const [assistJobs, setAssistJobs] = useState<IngestionAttachmentAssistJob[]>([]);
  const [assistLoadingSection, setAssistLoadingSection] = useState<AttachmentAssistSection | null>(null);
  const [assistError, setAssistError] = useState("");
  const assistApplyingJobsRef = useRef<Record<string, boolean>>({});
  const assistHandledJobsRef = useRef<Record<string, boolean>>({});

  const [labRows, setLabRows] = useState<MetricEntry[]>([createMetricRow()]);
  const [imagingRows, setImagingRows] = useState<ImagingEntry[]>([createImagingRow()]);
  const [interventionRows, setInterventionRows] = useState<InterventionEntry[]>([createInterventionRow()]);

  const [drafts, setDrafts] = useState<SavedDraft[]>([]);
  const [draftsReady, setDraftsReady] = useState(false);

  const [caseQuery, setCaseQuery] = useState("");
  const [caseRows, setCaseRows] = useState<IngestionCaseSummary[]>([]);
  const [caseLoading, setCaseLoading] = useState(false);
  const [selectedCase, setSelectedCase] = useState<IngestionCaseDetail | null>(null);
  const [caseError, setCaseError] = useState("");

  useEffect(() => {
    fetchTemplates()
      .then((items) => {
        setTemplates(items);
        if (!items.find((item) => item.template_id === wizard.template_id) && items.length > 0) {
          setWizard((current) => ({ ...current, template_id: items[0].template_id }));
        }
      })
      .catch((err: Error) => setStatus(`Template load failed: ${err.message}`));
  }, [wizard.template_id]);

  useEffect(() => {
    setDrafts(readSavedDrafts());
    setDraftsReady(true);
  }, []);

  useEffect(() => {
    setCaseLoading(true);
    fetchIngestionCases(undefined, 150)
      .then((items) => {
        setCaseRows(items);
        setCaseError("");
      })
      .catch((err: Error) => setCaseError(err.message || "Failed to load cases"))
      .finally(() => setCaseLoading(false));
  }, []);

  useEffect(() => {
    if (!draftsReady) {
      return;
    }

    const timeout = setTimeout(() => {
      const draftId = getDraftIdFromWizard(wizard);
      const now = new Date().toISOString();
      const nextDraft: SavedDraft = {
        id: draftId,
        label: draftId,
        saved_at: now,
        step_index: stepIndex,
        wizard,
        lab_rows: labRows,
        imaging_rows: imagingRows,
        intervention_rows: interventionRows
      };

      setDrafts((current) => {
        const withoutCurrent = current.filter((item) => item.id !== draftId);
        const merged = [nextDraft, ...withoutCurrent].sort((a, b) => b.saved_at.localeCompare(a.saved_at)).slice(0, 12);
        writeSavedDrafts(merged);
        return merged;
      });
    }, 500);

    return () => window.clearTimeout(timeout);
  }, [draftsReady, wizard, stepIndex, labRows, imagingRows, interventionRows]);

  const currentStepErrors = useMemo(() => validateCurrentStep(stepIndex, wizard, labRows, imagingRows), [stepIndex, wizard, labRows, imagingRows]);
  const labAssistItems = useMemo(
    () => assistJobs.filter((item) => item.section === "lab"),
    [assistJobs]
  );
  const imagingAssistItems = useMemo(
    () => assistJobs.filter((item) => item.section === "imaging"),
    [assistJobs]
  );
  const assistedStoredPaths = useMemo(
    () =>
      Array.from(
        new Set(
          assistJobs
            .map((item) => item.uploaded_file.stored_path)
            .filter((item) => item && item.trim())
        )
      ),
    [assistJobs]
  );

  function setCoreField<K extends keyof WizardState>(key: K, value: WizardState[K]) {
    setWizard((current) => ({ ...current, [key]: value }));
  }

  function resetAssistJobs() {
    setAssistJobs([]);
    setAssistError("");
    assistApplyingJobsRef.current = {};
    assistHandledJobsRef.current = {};
  }

  function upsertAssistJobs(incoming: IngestionAttachmentAssistJob | IngestionAttachmentAssistJob[]) {
    const batch = Array.isArray(incoming) ? incoming : [incoming];
    if (batch.length === 0) {
      return;
    }

    setAssistJobs((current) => {
      const map = new Map(current.map((item) => [item.job_id, item]));
      let changed = false;

      for (const item of batch) {
        const previous = map.get(item.job_id);
        if (
          !previous ||
          previous.updated_at !== item.updated_at ||
          previous.status !== item.status ||
          previous.review.status !== item.review.status ||
          previous.error !== item.error
        ) {
          changed = true;
        }
        map.set(item.job_id, item);
      }

      if (!changed && map.size === current.length) {
        return current;
      }

      return Array.from(map.values()).sort((a, b) => b.created_at.localeCompare(a.created_at));
    });
  }

  async function handleAssistRetry(jobId: string) {
    try {
      const retried = await retryAttachmentAssistJob(jobId);
      delete assistApplyingJobsRef.current[jobId];
      delete assistHandledJobsRef.current[jobId];
      upsertAssistJobs(retried);
      setAssistError("");
      setStatus(`Retry queued for ${retried.uploaded_file.file_name}.`);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Retry failed";
      setAssistError(message);
      setStatus(`Retry failed: ${message}`);
    }
  }

  useEffect(() => {
    const pendingIds = assistJobs
      .filter((item) => item.status === "queued" || item.status === "processing")
      .map((item) => item.job_id);

    if (pendingIds.length === 0) {
      return;
    }

    let cancelled = false;

    const poll = async () => {
      const updates = await Promise.all(
        pendingIds.map(async (jobId) => {
          try {
            return await fetchAttachmentAssistJob(jobId);
          } catch {
            return null;
          }
        })
      );

      if (cancelled) {
        return;
      }

      const validUpdates = updates.filter((item): item is IngestionAttachmentAssistJob => item !== null);
      if (validUpdates.length > 0) {
        upsertAssistJobs(validUpdates);
      }
    };

    void poll();
    const timer = window.setInterval(() => {
      void poll();
    }, 1800);

    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [assistJobs]);

  function setExtraField(key: string, value: string) {
    setWizard((current) => ({
      ...current,
      extra_fields: {
        ...current.extra_fields,
        [key]: value
      }
    }));
  }

  function getExtraField(key: string): string {
    return wizard.extra_fields[key] || "";
  }

  function updateMetricRow(id: string, patch: Partial<MetricEntry>) {
    setLabRows((current) => current.map((item) => (item.id === id ? { ...item, ...patch } : item)));
  }

  function updateImagingRow(id: string, patch: Partial<ImagingEntry>) {
    setImagingRows((current) => current.map((item) => (item.id === id ? { ...item, ...patch } : item)));
  }

  function updateInterventionRow(id: string, patch: Partial<InterventionEntry>) {
    setInterventionRows((current) => current.map((item) => (item.id === id ? { ...item, ...patch } : item)));
  }

  function mergeLabAssistRows(rows: Array<{ date: string; parameter: string; value: string }>) {
    if (rows.length === 0) {
      return;
    }

    setLabRows((current) => {
      const existing = current.filter((row) => row.date || row.parameter || row.value);
      const seen = new Set(existing.map((row) => `${row.date}|${row.parameter.toLowerCase()}|${row.value.toLowerCase()}`));
      const additions = rows
        .filter((row) => row.parameter || row.value)
        .filter((row) => {
          const key = `${row.date}|${row.parameter.toLowerCase()}|${row.value.toLowerCase()}`;
          if (seen.has(key)) {
            return false;
          }
          seen.add(key);
          return true;
        })
        .map((row) => ({ id: makeRowId(), date: row.date || "", parameter: row.parameter || "", value: row.value || "" }));

      if (additions.length === 0) {
        return current;
      }

      const hasOnlyPlaceholder = current.length === 1 && !current[0].date && !current[0].parameter && !current[0].value;
      if (hasOnlyPlaceholder) {
        return additions;
      }
      return [...current, ...additions];
    });
  }

  function mergeImagingAssistRows(rows: Array<{ date: string; modality: string; findings: string }>) {
    if (rows.length === 0) {
      return;
    }

    setImagingRows((current) => {
      const existing = current.filter((row) => row.date || row.modality || row.findings);
      const seen = new Set(existing.map((row) => `${row.date}|${row.modality.toLowerCase()}|${row.findings.toLowerCase()}`));
      const additions = rows
        .filter((row) => row.modality || row.findings)
        .filter((row) => {
          const key = `${row.date}|${row.modality.toLowerCase()}|${row.findings.toLowerCase()}`;
          if (seen.has(key)) {
            return false;
          }
          seen.add(key);
          return true;
        })
        .map((row) => ({
          id: makeRowId(),
          date: row.date || "",
          modality: row.modality || "",
          findings: row.findings || "",
        }));

      if (additions.length === 0) {
        return current;
      }

      const hasOnlyPlaceholder = current.length === 1 && !current[0].date && !current[0].modality && !current[0].findings;
      if (hasOnlyPlaceholder) {
        return additions;
      }
      return [...current, ...additions];
    });
  }

  function applySuggestedExtraFields(extra: Record<string, string>) {
    const keys = Object.keys(extra);
    if (keys.length === 0) {
      return 0;
    }

    let appliedCount = 0;
    setWizard((current) => {
      const nextExtra = { ...current.extra_fields };
      for (const [key, value] of Object.entries(extra)) {
        const normalized = value.trim();
        if (!normalized) {
          continue;
        }
        if (nextExtra[key] && nextExtra[key].trim()) {
          continue;
        }
        nextExtra[key] = normalized;
        appliedCount += 1;
      }
      return { ...current, extra_fields: nextExtra };
    });

    return appliedCount;
  }

  useEffect(() => {
    const readyForReview = assistJobs.filter(
      (item) =>
        item.status === "completed" &&
        item.review.status === "pending_review" &&
        Boolean(item.result?.suggestions)
    );

    if (readyForReview.length === 0) {
      return;
    }

    for (const job of readyForReview) {
      if (assistHandledJobsRef.current[job.job_id] || assistApplyingJobsRef.current[job.job_id]) {
        continue;
      }

      assistApplyingJobsRef.current[job.job_id] = true;

      void (async () => {
        const suggestions = job.result?.suggestions;
        if (!suggestions) {
          delete assistApplyingJobsRef.current[job.job_id];
          return;
        }

        try {
          const labAdded = suggestions.lab_entries.length;
          const imagingAdded = suggestions.imaging_entries.length;

          if (labAdded > 0) {
            mergeLabAssistRows(suggestions.lab_entries);
          }
          if (imagingAdded > 0) {
            mergeImagingAssistRows(suggestions.imaging_entries);
          }
          const extraApplied = applySuggestedExtraFields(suggestions.extra_fields);

          const reviewed = await reviewAttachmentAssistJob(
            job.job_id,
            "accepted",
            "Auto-applied from ingestion wizard",
            {
              lab_rows_added: labAdded,
              imaging_rows_added: imagingAdded,
              extra_fields_applied: extraApplied,
            }
          );

          upsertAssistJobs(reviewed);
          assistHandledJobsRef.current[job.job_id] = true;
          setAssistError("");
          setStatus(
            `OCR completed for ${job.uploaded_file.file_name}: added ${labAdded + imagingAdded} rows and ${extraApplied} mapped fields.`
          );
        } catch (err) {
          const message = err instanceof Error ? err.message : "Unable to review OCR result";
          assistHandledJobsRef.current[job.job_id] = true;
          setAssistError(message);
          setStatus(`OCR review failed for ${job.uploaded_file.file_name}: ${message}`);
        } finally {
          delete assistApplyingJobsRef.current[job.job_id];
        }
      })();
    }
  }, [assistJobs]);

  async function handleAssistUpload(section: AttachmentAssistSection, files: FileList | null) {
    const selected = Array.from(files || []);
    if (selected.length === 0) {
      return;
    }

    setAssistLoadingSection(section);
    setAssistError("");

    try {
      let queuedCount = 0;
      for (const file of selected) {
        const queued = await createAttachmentAssistJob(file, section, wizard.patient_id.trim() || undefined);
        upsertAssistJobs(queued);
        delete assistHandledJobsRef.current[queued.job_id];
        delete assistApplyingJobsRef.current[queued.job_id];
        queuedCount += 1;
      }

      setStatus(`Queued ${queuedCount} ${section} OCR job${queuedCount === 1 ? "" : "s"}.`);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Attachment auto-fill failed";
      setAssistError(message);
      setStatus(`Attachment auto-fill failed: ${message}`);
    } finally {
      setAssistLoadingSection(null);
    }
  }

  function removeDraft(id: string) {
    setDrafts((current) => {
      const next = current.filter((item) => item.id !== id);
      writeSavedDrafts(next);
      return next;
    });
  }

  function loadDraft(draft: SavedDraft) {
    setWizard(draft.wizard);
    setStepIndex(Math.min(Math.max(draft.step_index, 0), WIZARD_STEPS.length - 1));
    setLabRows(draft.lab_rows.length > 0 ? draft.lab_rows : [createMetricRow()]);
    setImagingRows(draft.imaging_rows.length > 0 ? draft.imaging_rows : [createImagingRow()]);
    setInterventionRows(draft.intervention_rows.length > 0 ? draft.intervention_rows : [createInterventionRow()]);
    setAttachments([]);
    resetAssistJobs();
    setPane("wizard");
    setStatus(`Loaded draft ${draft.label}.`);
  }

  function startNewForm() {
    setWizard(INITIAL_WIZARD_STATE);
    setLabRows([createMetricRow()]);
    setImagingRows([createImagingRow()]);
    setInterventionRows([createInterventionRow()]);
    setAttachments([]);
    resetAssistJobs();
    setStepIndex(0);
    setStatus("New form started.");
  }

  async function refreshCases(search?: string) {
    setCaseLoading(true);
    setCaseError("");
    try {
      const items = await fetchIngestionCases(search, 150);
      setCaseRows(items);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to load cases";
      setCaseError(message);
    } finally {
      setCaseLoading(false);
    }
  }

  async function openCase(patientId: string) {
    setCaseError("");
    try {
      const detail = await fetchIngestionCase(patientId);
      setSelectedCase(detail);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to load case details";
      setCaseError(message);
    }
  }

  function loadCaseToWizard(detail: IngestionCaseDetail) {
    const payload = detail.payload || {};
    const { extra, labRows: rowsLab, imagingRows: rowsImaging, interventionRows: rowsIntervention } = normalizeCaseRows(payload);

    const vessel = payload.vessel_involvement;
    const vesselText = Array.isArray(vessel)
      ? vessel.map((value) => asString(value).trim()).filter(Boolean).join(", ")
      : asString(vessel);

    const loadedWizard: WizardState = {
      template_id: asString(payload.template_id, "patient-proforma-v3") || "patient-proforma-v3",
      patient_id: asString(payload.patient_id),
      encounter_date: asString(payload.encounter_date),
      diagnosis: asString(payload.diagnosis),
      visit_type: (asString(payload.visit_type, "baseline") as VisitType) || "baseline",
      svt_status: (asString(payload.svt_status, "without_svt") as SvtStatus) || "without_svt",
      vessel_involvement: vesselText,
      ward: asString(payload.ward, "Gastro Surgery Ward"),
      cohort_status: (asString(payload.cohort_status, "active") as CohortStatus) || "active",
      mortality: (asString(payload.mortality, "no") as MortalityStatus) || "no",
      death_date: asString(payload.death_date),
      cause_of_death: asString(payload.cause_of_death),
      recanalization_status:
        (asString(payload.recanalization_status, "not_applicable") as RecanalizationStatus) || "not_applicable",
      primary_endpoint_complete: asBoolean(payload.primary_endpoint_complete, false),
      notes: asString(payload.notes),
      extra_fields: extra
    };

    setWizard(loadedWizard);
    setLabRows(rowsLab);
    setImagingRows(rowsImaging);
    setInterventionRows(rowsIntervention);
    setAttachments([]);
    resetAssistJobs();
    setPane("wizard");
    setStepIndex(0);
    setStatus(`Loaded case ${detail.summary.patient_id}. Submitting will create a new revision event.`);
  }

  async function handleImportProformas() {
    setImportStatus("Importing vault proformas...");
    setImportResult(null);

    try {
      const result = await importVaultProformas();
      setImportResult(result);
      setImportStatus(
        `Import complete. Scanned ${result.scanned_files}, imported ${result.imported_files}, skipped ${result.skipped_files}.`
      );
      await refreshCases(caseQuery);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Unknown error";
      setImportStatus(`Import failed: ${message}`);
    }
  }

  async function handleCsvUpload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setCsvStatus("Processing CSV...");
    setCsvResult(null);

    const formData = new FormData(event.currentTarget);
    const csvFile = formData.get("patient_csv");

    if (!(csvFile instanceof File) || csvFile.size === 0) {
      setCsvStatus("Select a CSV file before submitting.");
      return;
    }

    try {
      const result = await submitPatientCsv(csvFile);
      setCsvResult(result);
      setCsvStatus(
        `CSV processed. Accepted ${result.accepted_rows}/${result.total_rows}, rejected ${result.rejected_rows}.`
      );
      event.currentTarget.reset();
      await refreshCases(caseQuery);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Unknown error";
      setCsvStatus(`CSV ingestion failed: ${message}`);
    }
  }

  async function submitWizard() {
    if (currentStepErrors.length > 0) {
      setStatus(`Cannot submit yet: ${currentStepErrors[0]}`);
      return;
    }

    setSubmitting(true);
    setStatus("Submitting patient record...");

    try {
      let storedFiles: string[] = [...assistedStoredPaths];

      if (attachments.length > 0) {
        setStatus("Uploading attachments...");
        const uploaded = await uploadPatientFiles(attachments, wizard.patient_id || undefined);
        storedFiles = [...storedFiles, ...uploaded.files.map((item) => item.stored_path)];
      }
      storedFiles = Array.from(new Set(storedFiles.filter((item) => item.trim())));

      const vesselInvolvement = wizard.vessel_involvement
        .split(/[;,]/)
        .map((item) => item.trim().toLowerCase())
        .filter((item) => item.length > 0) as Array<"pv" | "smv" | "sv" | "multiple" | "unknown">;

      const payload = {
        template_id: wizard.template_id,
        patient_id: wizard.patient_id.trim(),
        encounter_date: wizard.encounter_date,
        diagnosis: wizard.diagnosis.trim(),
        visit_type: wizard.visit_type,
        svt_status: wizard.svt_status,
        vessel_involvement: vesselInvolvement,
        ward: wizard.ward.trim(),
        cohort_status: wizard.cohort_status,
        mortality: wizard.mortality,
        death_date: wizard.death_date || undefined,
        cause_of_death: wizard.cause_of_death || undefined,
        recanalization_status: wizard.recanalization_status,
        primary_endpoint_complete: wizard.primary_endpoint_complete,
        notes: wizard.notes,
        extra_fields: mergeExtraFields(wizard, labRows, imagingRows, interventionRows),
        source_files: storedFiles
      };

      const result = await submitPatient(payload);
      setStatus(`Submission stored. Note created at: ${result.data.note_path}`);

      const submittedDraftId = getDraftIdFromWizard(wizard);
      removeDraft(submittedDraftId);
      setAttachments([]);
      resetAssistJobs();

      await refreshCases(caseQuery);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Unknown error";
      setStatus(`Submission failed: ${message}`);
    } finally {
      setSubmitting(false);
    }
  }

  function nextStep() {
    if (currentStepErrors.length > 0) {
      setStatus(`Fix this step first: ${currentStepErrors[0]}`);
      return;
    }
    setStepIndex((current) => Math.min(current + 1, WIZARD_STEPS.length - 1));
  }

  function previousStep() {
    setStepIndex((current) => Math.max(current - 1, 0));
  }

  function renderBooleanField(label: string, key: string, durationKey?: string) {
    return (
      <div className="input-group" key={key}>
        <label>{label}</label>
        <div style={{ display: "grid", gap: 8, gridTemplateColumns: durationKey ? "120px 1fr" : "120px" }}>
          <select value={getExtraField(key)} onChange={(event) => setExtraField(key, event.target.value)}>
            {YES_NO_OPTIONS.map((option) => (
              <option key={`${key}-${option.value}`} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
          {durationKey ? (
            <input
              placeholder="Duration / Details"
              value={getExtraField(durationKey)}
              onChange={(event) => setExtraField(durationKey, event.target.value)}
            />
          ) : null}
        </div>
      </div>
    );
  }

  function renderWizardStep() {
    if (stepIndex === 0) {
      return (
        <div className="wizard-content">
          <div className="form-card">
            <h3>Study Basics</h3>
            <div className="form-grid form-grid--two">
              <div className="input-group">
                <label>Template</label>
                <select value={wizard.template_id} onChange={(event) => setCoreField("template_id", event.target.value)}>
                  {templates.map((template) => (
                    <option key={template.template_id} value={template.template_id}>
                      {template.title} (v{template.version})
                    </option>
                  ))}
                </select>
              </div>
              <div className="input-group">
                <label>Study ID *</label>
                <input value={wizard.patient_id} onChange={(event) => setCoreField("patient_id", event.target.value)} />
              </div>
              <div className="input-group">
                <label>Assessment Date *</label>
                <input
                  type="date"
                  value={wizard.encounter_date}
                  onChange={(event) => setCoreField("encounter_date", event.target.value)}
                />
              </div>
              <div className="input-group">
                <label>Visit Type *</label>
                <select
                  value={wizard.visit_type}
                  onChange={(event) => setCoreField("visit_type", event.target.value as VisitType)}
                >
                  <option value="baseline">Baseline</option>
                  <option value="day7_reassessment">Day 7 Reassessment</option>
                  <option value="discharge">Discharge</option>
                  <option value="week2_followup">Week 2 Follow-up</option>
                  <option value="month1_followup">Month 1 Follow-up</option>
                  <option value="month3_followup">Month 3 Follow-up</option>
                </select>
              </div>
              <div className="input-group">
                <label>Diagnosis *</label>
                <input value={wizard.diagnosis} onChange={(event) => setCoreField("diagnosis", event.target.value)} />
              </div>
              <div className="input-group">
                <label>Ward *</label>
                <input value={wizard.ward} onChange={(event) => setCoreField("ward", event.target.value)} />
              </div>
              <div className="input-group">
                <label>Cohort Status</label>
                <select
                  value={wizard.cohort_status}
                  onChange={(event) => setCoreField("cohort_status", event.target.value as CohortStatus)}
                >
                  <option value="screened">Screened</option>
                  <option value="enrolled">Enrolled</option>
                  <option value="active">Active</option>
                  <option value="completed">Completed</option>
                  <option value="terminal_outcome">Terminal Outcome</option>
                </select>
              </div>
              <div className="input-group">
                <label>SVT Status *</label>
                <select value={wizard.svt_status} onChange={(event) => setCoreField("svt_status", event.target.value as SvtStatus)}>
                  <option value="without_svt">Without SVT</option>
                  <option value="with_svt">With SVT</option>
                </select>
              </div>
              <div className="input-group">
                <label>Vessel Involvement (comma separated)</label>
                <input
                  placeholder="pv, smv, sv, multiple, unknown"
                  value={wizard.vessel_involvement}
                  onChange={(event) => setCoreField("vessel_involvement", event.target.value)}
                />
              </div>
            </div>
          </div>

          <div className="form-card">
            <h3>Demographics</h3>
            <div className="form-grid form-grid--two">
              {[
                ["demographics__age_sex", "Age / Sex *"],
                ["demographics__cr_no", "CR Number"],
                ["demographics__contact_no", "Contact Number"],
                ["demographics__address", "Address"],
                ["demographics__opd_ipd", "OPD/IPD *"],
                ["demographics__date_of_admission", "Date of Admission *"],
                ["demographics__date_of_discharge", "Date of Discharge"],
                ["demographics__weight_height", "Weight / Height"],
                ["demographics__bmi", "BMI"],
                ["demographics__asa_classification", "ASA Classification"]
              ].map(([key, label]) => (
                <div className="input-group" key={key}>
                  <label>{label}</label>
                  <input value={getExtraField(key)} onChange={(event) => setExtraField(key, event.target.value)} />
                </div>
              ))}
            </div>
          </div>

          <div className="form-card">
            <h3>Addictions</h3>
            <div className="form-grid form-grid--two">
              {[
                ["addictions__alcohol", "Alcohol"],
                ["addictions__smoking", "Smoking"],
                ["addictions__tobacco_chewing", "Tobacco Chewing"],
                ["addictions__others", "Others"]
              ].map(([key, label]) => (
                <div className="input-group" key={key}>
                  <label>{label}</label>
                  <input value={getExtraField(key)} onChange={(event) => setExtraField(key, event.target.value)} />
                </div>
              ))}
            </div>
          </div>
        </div>
      );
    }

    if (stepIndex === 1) {
      return (
        <div className="wizard-content">
          <div className="form-card">
            <h3>Pain and Clinical Details</h3>
            <div className="form-grid form-grid--two">
              {[
                ["clinical_details__index_pain", "Index Pain Date"],
                ["clinical_details__current_pain", "Current Pain Duration"],
                ["clinical_details__pain_duration", "Pain Duration Detail"],
                ["clinical_details__pain_site", "Pain Site"],
                ["clinical_details__severity_vas_1_10", "VAS Score (1-10)"]
              ].map(([key, label]) => (
                <div className="input-group" key={key}>
                  <label>{label}</label>
                  <input value={getExtraField(key)} onChange={(event) => setExtraField(key, event.target.value)} />
                </div>
              ))}
            </div>
            <div className="form-grid form-grid--two" style={{ marginTop: 12 }}>
              {FEATURE_FLAGS.map((field) => renderBooleanField(field.label, field.key, field.durationKey))}
            </div>
          </div>

          <div className="form-card">
            <h3>Comorbidities</h3>
            <div className="form-grid form-grid--two">
              {COMORBIDITY_FLAGS.map((field) => renderBooleanField(field.label, field.key, field.durationKey))}
              <div className="input-group">
                <label>Other Comorbidities</label>
                <input
                  value={getExtraField("comorbidities__other")}
                  onChange={(event) => setExtraField("comorbidities__other", event.target.value)}
                />
              </div>
            </div>
          </div>

          <div className="form-card">
            <h3>Etiology and AP Severity</h3>
            <div className="form-grid form-grid--two">
              <div className="input-group">
                <label>Etiology of Acute Pancreatitis *</label>
                <input
                  placeholder="Alcohol / Biliary / Hypertriglyceridemia / Hypercalcemia / Post ERCP / Idiopathic / Other"
                  value={getExtraField("etiology_of_acute_pancreatitis__etiology")}
                  onChange={(event) => setExtraField("etiology_of_acute_pancreatitis__etiology", event.target.value)}
                />
              </div>
              <div className="input-group">
                <label>Revised Atlanta Severity Grade *</label>
                <select
                  value={getExtraField("acute_pancreatitis__revised_atlanta_severity_grade")}
                  onChange={(event) => setExtraField("acute_pancreatitis__revised_atlanta_severity_grade", event.target.value)}
                >
                  <option value="">--</option>
                  <option value="mild">Mild</option>
                  <option value="moderately_severe">Moderately Severe</option>
                  <option value="severe">Severe</option>
                </select>
              </div>
              <div className="input-group">
                <label>Modified CTSI</label>
                <input
                  value={getExtraField("acute_pancreatitis__modified_ct_severity_score")}
                  onChange={(event) => setExtraField("acute_pancreatitis__modified_ct_severity_score", event.target.value)}
                />
              </div>
              <div className="input-group">
                <label>Acute Pancreatitis Type</label>
                <select
                  value={getExtraField("acute_pancreatitis__type")}
                  onChange={(event) => setExtraField("acute_pancreatitis__type", event.target.value)}
                >
                  <option value="">--</option>
                  <option value="edematous_interstitial">Edematous (Interstitial)</option>
                  <option value="necrotizing">Necrotizing</option>
                </select>
              </div>
              <div className="input-group">
                <label>Pancreatic Necrosis</label>
                <input
                  placeholder="yes/no + sterile/infected"
                  value={getExtraField("acute_pancreatitis__pancreatic_necrosis")}
                  onChange={(event) => setExtraField("acute_pancreatitis__pancreatic_necrosis", event.target.value)}
                />
              </div>
              <div className="input-group">
                <label>GIT Complications</label>
                <input
                  placeholder="Perforation / Obstruction / Fistula / Ischemia / Bleeding / Other"
                  value={getExtraField("acute_pancreatitis__git_complications")}
                  onChange={(event) => setExtraField("acute_pancreatitis__git_complications", event.target.value)}
                />
              </div>
            </div>
          </div>
        </div>
      );
    }

    if (stepIndex === 2) {
      return (
        <div className="wizard-content">
          <div className="form-card">
            <h3>Laboratory Investigations</h3>
            <p className="text-muted">Capture each point as Date + Parameter + Value.</p>
            <div className="table-editor">
              {labRows.map((row) => (
                <div className="table-editor__row" key={row.id}>
                  <input type="date" value={row.date} onChange={(event) => updateMetricRow(row.id, { date: event.target.value })} />
                  <input
                    placeholder="Parameter"
                    value={row.parameter}
                    onChange={(event) => updateMetricRow(row.id, { parameter: event.target.value })}
                  />
                  <input placeholder="Value" value={row.value} onChange={(event) => updateMetricRow(row.id, { value: event.target.value })} />
                  <button type="button" onClick={() => setLabRows((current) => current.filter((item) => item.id !== row.id))}>
                    Remove
                  </button>
                </div>
              ))}
            </div>
            <button type="button" onClick={() => setLabRows((current) => [...current, createMetricRow()])}>
              + Add Lab Entry
            </button>

            <div className="assist-uploader">
              <strong>Auto-fill from Lab Attachment</strong>
              <p className="text-muted">
                Upload lab PDFs/images here. Marker OCR runs automatically and adds detected values into this table.
              </p>
              <input
                type="file"
                multiple
                accept=".pdf,image/*,.txt,.md"
                disabled={assistLoadingSection === "lab"}
                onChange={(event) => {
                  void handleAssistUpload("lab", event.target.files);
                  event.currentTarget.value = "";
                }}
              />
              {assistLoadingSection === "lab" ? <p className="text-muted">Processing lab attachment...</p> : null}
              {assistError ? <p className="wizard-error">{assistError}</p> : null}

              {labAssistItems.length > 0 ? (
                <div className="assist-uploader__list">
                  {labAssistItems.slice(0, 6).map((item) => (
                    <article key={`${item.uploaded_file.stored_path}-lab`} className="assist-uploader__item">
                      <strong>{item.uploaded_file.file_name}</strong>
                      <small>
                        {item.status} | review: {item.review.status} | {item.result?.extractor || "marker"}
                      </small>
                      {item.status === "failed" ? (
                        <p>OCR failed: {item.error || item.result?.extraction_error || "unknown error"}</p>
                      ) : item.status === "completed" ? (
                        <p>Added {item.result?.suggestions.lab_entries.length || 0} lab rows from this report.</p>
                      ) : (
                        <p>OCR is running. This card updates automatically.</p>
                      )}
                      {item.result?.suggestions.review_notes && item.result.suggestions.review_notes.length > 0 ? (
                        <ul>
                          {item.result.suggestions.review_notes.slice(0, 2).map((note) => (
                            <li key={`${item.uploaded_file.stored_path}-${note}`}>{note}</li>
                          ))}
                        </ul>
                      ) : null}
                      {item.status === "failed" ? (
                        <button type="button" onClick={() => void handleAssistRetry(item.job_id)}>
                          Retry OCR
                        </button>
                      ) : null}
                    </article>
                  ))}
                </div>
              ) : null}
            </div>
          </div>

          <div className="form-card">
            <h3>Imaging / Endoscopy</h3>
            <div className="table-editor">
              {imagingRows.map((row) => (
                <div className="table-editor__row" key={row.id}>
                  <input type="date" value={row.date} onChange={(event) => updateImagingRow(row.id, { date: event.target.value })} />
                  <input
                    placeholder="Modality"
                    value={row.modality}
                    onChange={(event) => updateImagingRow(row.id, { modality: event.target.value })}
                  />
                  <input
                    placeholder="Key findings"
                    value={row.findings}
                    onChange={(event) => updateImagingRow(row.id, { findings: event.target.value })}
                  />
                  <button
                    type="button"
                    onClick={() => setImagingRows((current) => current.filter((item) => item.id !== row.id))}
                  >
                    Remove
                  </button>
                </div>
              ))}
            </div>
            <button type="button" onClick={() => setImagingRows((current) => [...current, createImagingRow()])}>
              + Add Imaging Entry
            </button>

            <div className="assist-uploader">
              <strong>Auto-fill from Imaging Attachment</strong>
              <p className="text-muted">
                Upload CT/USG/MRI/endoscopy reports. OCR suggestions are mapped to imaging rows and vascular fields.
              </p>
              <input
                type="file"
                multiple
                accept=".pdf,image/*,.txt,.md"
                disabled={assistLoadingSection === "imaging"}
                onChange={(event) => {
                  void handleAssistUpload("imaging", event.target.files);
                  event.currentTarget.value = "";
                }}
              />
              {assistLoadingSection === "imaging" ? <p className="text-muted">Processing imaging attachment...</p> : null}
              {assistError ? <p className="wizard-error">{assistError}</p> : null}

              {imagingAssistItems.length > 0 ? (
                <div className="assist-uploader__list">
                  {imagingAssistItems.slice(0, 6).map((item) => (
                    <article key={`${item.uploaded_file.stored_path}-imaging`} className="assist-uploader__item">
                      <strong>{item.uploaded_file.file_name}</strong>
                      <small>
                        {item.status} | review: {item.review.status} | {item.result?.extractor || "marker"}
                      </small>
                      {item.status === "failed" ? (
                        <p>OCR failed: {item.error || item.result?.extraction_error || "unknown error"}</p>
                      ) : item.status === "completed" ? (
                        <p>
                          Added {item.result?.suggestions.imaging_entries.length || 0} imaging rows and{" "}
                          {Object.keys(item.result?.suggestions.extra_fields || {}).length} mapped fields.
                        </p>
                      ) : (
                        <p>OCR is running. This card updates automatically.</p>
                      )}
                      {item.result?.suggestions.review_notes && item.result.suggestions.review_notes.length > 0 ? (
                        <ul>
                          {item.result.suggestions.review_notes.slice(0, 2).map((note) => (
                            <li key={`${item.uploaded_file.stored_path}-${note}`}>{note}</li>
                          ))}
                        </ul>
                      ) : null}
                      {item.status === "failed" ? (
                        <button type="button" onClick={() => void handleAssistRetry(item.job_id)}>
                          Retry OCR
                        </button>
                      ) : null}
                    </article>
                  ))}
                </div>
              ) : null}
            </div>
          </div>

          <div className="form-card">
            <h3>SVT and Vascular Mapping</h3>
            <div className="form-grid form-grid--two">
              {[
                "overall_findings__pancreas",
                "overall_findings__necrosis_location",
                "overall_findings__necrosis_percent",
                "overall_findings__necrosis_site",
                "overall_findings__peripancreatic_fluid_collection",
                "overall_findings__pancreatic_fluid_collection",
                "overall_findings__pseudocyst_won",
                "overall_findings__modified_ctsi",
                "splanchnic_venous_assessment__thrombosis_locations",
                "splanchnic_venous_assessment__time_first_detection_days",
                "splanchnic_venous_assessment__portal_vein_pv",
                "splanchnic_venous_assessment__smv",
                "splanchnic_venous_assessment__splenic_vein_sv",
                "splanchnic_venous_assessment__smv_sv_confluence",
                "portal_hypertensive_changes__splenomegaly",
                "portal_hypertensive_changes__ascites",
                "portal_hypertensive_changes__varices",
                "portal_hypertensive_changes__collaterals",
                "portal_hypertensive_changes__portal_gastropathy",
                "vascular_complications__arterial_pseudoaneurysm",
                "vascular_complications__intra_abdominal_bleeding",
                "vascular_complications__bowel_ischemia",
                "vascular_complications__splenic_infarction"
              ].map((key) => (
                <div className="input-group" key={key}>
                  <label>{toDisplayLabel(key)}</label>
                  <input value={getExtraField(key)} onChange={(event) => setExtraField(key, event.target.value)} />
                </div>
              ))}
            </div>
          </div>
        </div>
      );
    }

    if (stepIndex === 3) {
      return (
        <div className="wizard-content">
          <div className="form-card">
            <h3>Management</h3>
            <div className="form-grid form-grid--two">
              <div className="input-group">
                <label>Conservative Management Components</label>
                <input
                  placeholder="ICU / PN / ionotropes / ventilator / HD / CRRT / other"
                  value={getExtraField("management__conservative")}
                  onChange={(event) => setExtraField("management__conservative", event.target.value)}
                />
              </div>
              <div className="input-group">
                <label>Intervention Performed *</label>
                <input
                  value={getExtraField("management__intervention")}
                  onChange={(event) => setExtraField("management__intervention", event.target.value)}
                />
              </div>
              <div className="input-group">
                <label>First Intervention</label>
                <input
                  value={getExtraField("management__first_intervention")}
                  onChange={(event) => setExtraField("management__first_intervention", event.target.value)}
                />
              </div>
              <div className="input-group">
                <label>First Intervention Date</label>
                <input
                  value={getExtraField("management__first_intervention_date")}
                  onChange={(event) => setExtraField("management__first_intervention_date", event.target.value)}
                />
              </div>
              <div className="input-group">
                <label>Time to First Intervention (days)</label>
                <input
                  value={getExtraField("management__time_to_first_intervention_days")}
                  onChange={(event) => setExtraField("management__time_to_first_intervention_days", event.target.value)}
                />
              </div>
              <div className="input-group">
                <label>Anticoagulation Therapy</label>
                <input
                  placeholder="yes/no + indication + initial + maintenance + duration"
                  value={getExtraField("management__anticoagulation_therapy")}
                  onChange={(event) => setExtraField("management__anticoagulation_therapy", event.target.value)}
                />
              </div>
            </div>
          </div>

          <div className="form-card">
            <h3>Other Interventions</h3>
            <div className="table-editor">
              {interventionRows.map((row) => (
                <div className="table-editor__row table-editor__row--five" key={row.id}>
                  <input
                    type="date"
                    value={row.date}
                    onChange={(event) => updateInterventionRow(row.id, { date: event.target.value })}
                  />
                  <input
                    placeholder="Intervention"
                    value={row.intervention}
                    onChange={(event) => updateInterventionRow(row.id, { intervention: event.target.value })}
                  />
                  <input
                    placeholder="Indication"
                    value={row.indication}
                    onChange={(event) => updateInterventionRow(row.id, { indication: event.target.value })}
                  />
                  <input
                    placeholder="Remarks"
                    value={row.remarks}
                    onChange={(event) => updateInterventionRow(row.id, { remarks: event.target.value })}
                  />
                  <button
                    type="button"
                    onClick={() => setInterventionRows((current) => current.filter((item) => item.id !== row.id))}
                  >
                    Remove
                  </button>
                </div>
              ))}
            </div>
            <button type="button" onClick={() => setInterventionRows((current) => [...current, createInterventionRow()])}>
              + Add Intervention
            </button>
          </div>

          <div className="form-card">
            <h3>Outcomes</h3>
            <div className="form-grid form-grid--two">
              {[
                "outcomes__icu_stay",
                "outcomes__total_hospital_stay",
                "outcomes__organ_failure",
                "outcomes__bowel_ischemia",
                "outcomes__bleeding",
                "outcomes__variceal_bleeding",
                "outcomes__splenic_infarction",
                "outcomes__bleeding_on_anticoagulation",
                "outcomes__readmission",
                "outcomes__mortality_in_hospital",
                "outcomes__mortality_after_discharge",
                "outcomes__mortality_cause"
              ].map((key) => (
                <div className="input-group" key={key}>
                  <label>{toDisplayLabel(key)}</label>
                  <input value={getExtraField(key)} onChange={(event) => setExtraField(key, event.target.value)} />
                </div>
              ))}
            </div>

            <div className="form-grid form-grid--two" style={{ marginTop: 10 }}>
              <div className="input-group">
                <label>Mortality</label>
                <select
                  value={wizard.mortality}
                  onChange={(event) => setCoreField("mortality", event.target.value as MortalityStatus)}
                >
                  <option value="no">No</option>
                  <option value="yes">Yes</option>
                </select>
              </div>
              <div className="input-group">
                <label>Date of Death</label>
                <input
                  type="date"
                  value={wizard.death_date}
                  onChange={(event) => setCoreField("death_date", event.target.value)}
                  disabled={wizard.mortality !== "yes"}
                />
              </div>
              <div className="input-group" style={{ gridColumn: "1 / -1" }}>
                <label>Cause of Death</label>
                <input
                  value={wizard.cause_of_death}
                  onChange={(event) => setCoreField("cause_of_death", event.target.value)}
                  disabled={wizard.mortality !== "yes"}
                />
              </div>
            </div>
          </div>
        </div>
      );
    }

    return (
      <div className="wizard-content">
        <div className="form-card">
          <h3>Follow-up</h3>
          <div className="form-grid form-grid--two">
            {[
              "follow_up__svt_assessment_date",
              "follow_up__svt_assessment_interval",
              "follow_up__progression_partial_to_total",
              "follow_up__progression_new_veins",
              "follow_up__progression_segmental_extension",
              "follow_up__recanalization",
              "follow_up__new_onset_thrombosis",
              "follow_up__persistence_of_svt",
              "follow_up__last_follow_up_date",
              "follow_up__duration_since_discharge"
            ].map((key) => (
              <div className="input-group" key={key}>
                <label>{toDisplayLabel(key)}</label>
                <input value={getExtraField(key)} onChange={(event) => setExtraField(key, event.target.value)} />
              </div>
            ))}
            <div className="input-group">
              <label>Recanalization Status</label>
              <select
                value={wizard.recanalization_status}
                onChange={(event) => setCoreField("recanalization_status", event.target.value as RecanalizationStatus)}
              >
                <option value="pending">Pending</option>
                <option value="complete">Complete</option>
                <option value="partial">Partial</option>
                <option value="none">None</option>
                <option value="progressed">Progressed</option>
                <option value="not_applicable">Not Applicable</option>
              </select>
            </div>
            <div className="input-group">
              <label>Primary Endpoint Complete</label>
              <label className="checkbox-row">
                <input
                  type="checkbox"
                  checked={wizard.primary_endpoint_complete}
                  onChange={(event) => setCoreField("primary_endpoint_complete", event.target.checked)}
                />
                Mark complete (typically month 3 follow-up)
              </label>
            </div>
          </div>
        </div>

        <div className="form-card">
          <h3>Attachments</h3>
          <p className="text-muted">Attach any additional files. Lab/imaging auto-fill uploads from step 3 are already included.</p>
          <input type="file" multiple onChange={(event) => setAttachments(Array.from(event.target.files || []))} />

          {assistJobs.length > 0 ? (
            <div className="assist-uploader__list" style={{ marginTop: 10 }}>
              {assistJobs.slice(0, 12).map((item) => (
                <article key={`${item.uploaded_file.stored_path}-review`} className="assist-uploader__item">
                  <strong>{item.uploaded_file.file_name}</strong>
                  <small>
                    {item.section} | {item.status} | review: {item.review.status}
                  </small>
                  <p>{item.uploaded_file.stored_path}</p>
                </article>
              ))}
            </div>
          ) : null}

          {attachments.length > 0 ? (
            <ul>
              {attachments.map((file) => (
                <li key={`${file.name}-${file.size}`}>{file.name}</li>
              ))}
            </ul>
          ) : (
            <p className="text-muted">No files selected.</p>
          )}
        </div>

        <div className="form-card">
          <h3>Clinical Notes</h3>
          <textarea
            rows={5}
            value={wizard.notes}
            onChange={(event) => setCoreField("notes", event.target.value)}
            placeholder="Any other relevant morbidity / complication / treatment notes"
          />
        </div>

        <div className="form-card">
          <h3>Review</h3>
          <div className="review-grid">
            <div>
              <strong>Study ID</strong>
              <p>{wizard.patient_id || "-"}</p>
            </div>
            <div>
              <strong>Assessment Date</strong>
              <p>{wizard.encounter_date || "-"}</p>
            </div>
            <div>
              <strong>Visit Type</strong>
              <p>{wizard.visit_type}</p>
            </div>
            <div>
              <strong>SVT Status</strong>
              <p>{wizard.svt_status}</p>
            </div>
            <div>
              <strong>Lab Entries</strong>
              <p>{labRows.filter((row) => row.date || row.parameter || row.value).length}</p>
            </div>
            <div>
              <strong>Imaging Entries</strong>
              <p>{imagingRows.filter((row) => row.date || row.modality || row.findings).length}</p>
            </div>
            <div>
              <strong>Attachments</strong>
              <p>{attachments.length + assistedStoredPaths.length}</p>
            </div>
            <div>
              <strong>Protocol Fields Captured</strong>
              <p>{Object.keys(wizard.extra_fields).length}</p>
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <section className="page">
      <PageHeader
        title="Data Ingestion"
        description="Protocol-driven, intuitive multi-step workflow for thesis case logging with autosave drafts, case reopening, and attachments."
      />

      <div className="ingestion-tabs">
        <button className={pane === "wizard" ? "ingestion-tab ingestion-tab--active" : "ingestion-tab"} onClick={() => setPane("wizard")}>
          Patient Logging Wizard
        </button>
        <button className={pane === "cases" ? "ingestion-tab ingestion-tab--active" : "ingestion-tab"} onClick={() => setPane("cases")}>
          Case Browser
        </button>
        <button className={pane === "import" ? "ingestion-tab ingestion-tab--active" : "ingestion-tab"} onClick={() => setPane("import")}>
          Import Existing Proformas
        </button>
        <button className={pane === "csv" ? "ingestion-tab ingestion-tab--active" : "ingestion-tab"} onClick={() => setPane("csv")}>
          CSV Batch Ingestion
        </button>
      </div>

      {pane === "wizard" ? (
        <div className="wizard-shell">
          <div className="draft-strip">
            <div>
              <strong>Autosave Drafts</strong>
              <p className="text-muted">Draft is auto-saved while you type. Load any unfinished case below.</p>
            </div>
            <button type="button" onClick={startNewForm}>
              Start New Form
            </button>
          </div>

          {drafts.length > 0 ? (
            <div className="draft-list">
              {drafts.map((draft) => (
                <div key={draft.id} className="draft-chip">
                  <div>
                    <strong>{draft.label}</strong>
                    <small>Saved {new Date(draft.saved_at).toLocaleString()}</small>
                  </div>
                  <div className="draft-chip__actions">
                    <button type="button" onClick={() => loadDraft(draft)}>
                      Resume
                    </button>
                    <button type="button" onClick={() => removeDraft(draft.id)}>
                      Delete
                    </button>
                  </div>
                </div>
              ))}
            </div>
          ) : null}

          <ol className="wizard-steps" aria-label="Ingestion wizard steps">
            {WIZARD_STEPS.map((step, index) => {
              const stateClass =
                index === stepIndex
                  ? "wizard-step wizard-step--active"
                  : index < stepIndex
                    ? "wizard-step wizard-step--done"
                    : "wizard-step";
              return (
                <li key={step.title} className={stateClass}>
                  <button type="button" onClick={() => setStepIndex(index)}>
                    <span className="wizard-step__index">{index + 1}</span>
                    <span>
                      <strong>{step.title}</strong>
                      <small>{step.description}</small>
                    </span>
                  </button>
                </li>
              );
            })}
          </ol>

          <div className="wizard-panel">{renderWizardStep()}</div>

          {currentStepErrors.length > 0 ? (
            <div className="wizard-error-list">
              <strong>Complete required fields before moving ahead:</strong>
              <ul>
                {currentStepErrors.map((error) => (
                  <li key={error}>{error}</li>
                ))}
              </ul>
            </div>
          ) : null}

          <p>{status}</p>

          <div className="wizard-actions">
            <button type="button" onClick={previousStep} disabled={stepIndex === 0 || submitting}>
              Previous
            </button>
            {stepIndex < WIZARD_STEPS.length - 1 ? (
              <button type="button" onClick={nextStep} disabled={submitting || currentStepErrors.length > 0}>
                Next Step
              </button>
            ) : (
              <button type="button" onClick={submitWizard} disabled={submitting || currentStepErrors.length > 0}>
                {submitting ? "Submitting..." : "Submit Patient Case"}
              </button>
            )}
          </div>
        </div>
      ) : null}

      {pane === "cases" ? (
        <div className="panel">
          <div className="panel__header">
            <h2>Case Browser and Re-open</h2>
            <p>Search existing imported/submitted cases and load them back into the wizard for editing.</p>
          </div>
          <div className="panel__body panel__body--compact">
            <div className="case-search-row">
              <input
                placeholder="Search by Study ID, diagnosis, ward"
                value={caseQuery}
                onChange={(event) => setCaseQuery(event.target.value)}
              />
              <button type="button" onClick={() => refreshCases(caseQuery)}>
                Search
              </button>
              <button type="button" onClick={() => refreshCases(undefined)}>
                Reset
              </button>
            </div>

            {caseLoading ? <p>Loading cases...</p> : null}
            {caseError ? <p className="wizard-error">{caseError}</p> : null}

            <div className="table-wrap" style={{ maxHeight: "50vh" }}>
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Study ID</th>
                    <th>Encounter</th>
                    <th>Visit</th>
                    <th>SVT</th>
                    <th>Diagnosis</th>
                    <th>Events</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {caseRows.map((row) => (
                    <tr key={`${row.patient_id}-${row.event_id}`}>
                      <td>{row.patient_id}</td>
                      <td>{row.encounter_date || "-"}</td>
                      <td>{row.visit_type}</td>
                      <td>{row.svt_status}</td>
                      <td>{row.diagnosis || "-"}</td>
                      <td>{row.event_count}</td>
                      <td>
                        <button type="button" onClick={() => openCase(row.patient_id)}>
                          Open
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {selectedCase ? (
              <div className="case-detail-card">
                <h3>{selectedCase.summary.patient_id}</h3>
                <p className="text-muted">
                  Latest visit: {selectedCase.summary.visit_type} | Encounter: {selectedCase.summary.encounter_date || "-"}
                </p>
                <div className="review-grid">
                  <div>
                    <strong>Diagnosis</strong>
                    <p>{selectedCase.summary.diagnosis || "-"}</p>
                  </div>
                  <div>
                    <strong>Ward</strong>
                    <p>{selectedCase.summary.ward || "-"}</p>
                  </div>
                  <div>
                    <strong>Cohort</strong>
                    <p>{selectedCase.summary.cohort_status}</p>
                  </div>
                  <div>
                    <strong>History Rows</strong>
                    <p>{selectedCase.history.length}</p>
                  </div>
                </div>
                <button type="button" onClick={() => loadCaseToWizard(selectedCase)}>
                  Load Into Wizard (Create New Revision)
                </button>
              </div>
            ) : null}
          </div>
        </div>
      ) : null}

      {pane === "import" ? (
        <div className="panel">
          <div className="panel__header">
            <h2>Backfill Existing Vault Proformas</h2>
            <p>Import all historical patient proforma markdown files into the analytics event stream.</p>
          </div>
          <div className="panel__body panel__body--compact">
            <button type="button" onClick={handleImportProformas} style={{ width: "fit-content", padding: "8px 14px" }}>
              Import Existing Vault Proformas
            </button>
            <p>{importStatus}</p>
            {importResult ? (
              <div className="review-grid">
                <div>
                  <strong>Scanned</strong>
                  <p>{importResult.scanned_files}</p>
                </div>
                <div>
                  <strong>Imported</strong>
                  <p>{importResult.imported_files}</p>
                </div>
                <div>
                  <strong>Skipped</strong>
                  <p>{importResult.skipped_files}</p>
                </div>
                <div>
                  <strong>Errors</strong>
                  <p>{importResult.errors.length}</p>
                </div>
              </div>
            ) : null}
            {importResult && importResult.errors.length > 0 ? (
              <div>
                <strong>Import Issues</strong>
                <ul>
                  {importResult.errors.slice(0, 15).map((error) => (
                    <li key={`${error.file_path}-${error.message}`}>
                      {error.file_path}: {error.message}
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
          </div>
        </div>
      ) : null}

      {pane === "csv" ? (
        <div className="panel">
          <div className="panel__header">
            <h2>CSV Batch Ingestion</h2>
            <p>Use this for bulk updates. Additional columns are preserved automatically.</p>
          </div>
          <div className="panel__body panel__body--compact">
            <form onSubmit={handleCsvUpload} style={{ display: "grid", gap: 10, maxWidth: 560 }}>
              <label>
                CSV File
                <input name="patient_csv" type="file" accept=".csv,text/csv" required style={{ width: "100%" }} />
              </label>
              <button type="submit" style={{ width: "fit-content", padding: "8px 14px" }}>
                Process CSV
              </button>
            </form>
            <p>{csvStatus}</p>
            {csvResult && csvResult.errors.length > 0 ? (
              <div>
                <strong>CSV Errors</strong>
                <ul>
                  {csvResult.errors.slice(0, 12).map((error, index) => (
                    <li key={`${error.row_number}-${index}`}>
                      Row {error.row_number}: {error.message}
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
          </div>
        </div>
      ) : null}
    </section>
  );
}

function validateCurrentStep(
  stepIndex: number,
  wizard: WizardState,
  labRows: MetricEntry[],
  imagingRows: ImagingEntry[]
): string[] {
  const errors: string[] = [];

  if (stepIndex === 0) {
    if (!wizard.patient_id.trim()) {
      errors.push("Study ID is required.");
    }
    if (!wizard.encounter_date.trim()) {
      errors.push("Assessment date is required.");
    }
    if (!wizard.diagnosis.trim()) {
      errors.push("Diagnosis is required.");
    }
    if (!wizard.ward.trim()) {
      errors.push("Ward is required.");
    }
    if (!wizard.extra_fields.demographics__age_sex?.trim()) {
      errors.push("Demographics: Age / Sex is required.");
    }
    if (!wizard.extra_fields.demographics__opd_ipd?.trim()) {
      errors.push("Demographics: OPD/IPD is required.");
    }
    if (!wizard.extra_fields.demographics__date_of_admission?.trim()) {
      errors.push("Demographics: Date of admission is required.");
    }
  }

  if (stepIndex === 1) {
    if (!wizard.extra_fields.etiology_of_acute_pancreatitis__etiology?.trim()) {
      errors.push("Etiology of acute pancreatitis is required.");
    }
    if (!wizard.extra_fields.acute_pancreatitis__revised_atlanta_severity_grade?.trim()) {
      errors.push("Revised Atlanta severity grade is required.");
    }
  }

  if (stepIndex === 2) {
    const hasLab = labRows.some((row) => row.date || row.parameter || row.value);
    if (!hasLab) {
      errors.push("At least one laboratory investigation entry is required.");
    }

    const hasImaging = imagingRows.some((row) => row.date || row.modality || row.findings);
    if (!hasImaging) {
      errors.push("At least one imaging/endoscopy entry is required.");
    }

    if (!wizard.extra_fields.splanchnic_venous_assessment__portal_vein_pv?.trim()) {
      errors.push("SVT mapping: Portal vein status is required.");
    }
    if (!wizard.extra_fields.splanchnic_venous_assessment__smv?.trim()) {
      errors.push("SVT mapping: SMV status is required.");
    }
    if (!wizard.extra_fields.splanchnic_venous_assessment__splenic_vein_sv?.trim()) {
      errors.push("SVT mapping: Splenic vein status is required.");
    }
  }

  if (stepIndex === 3) {
    if (!wizard.extra_fields.management__intervention?.trim()) {
      errors.push("Management: intervention status is required.");
    }
    if (!wizard.extra_fields.outcomes__total_hospital_stay?.trim()) {
      errors.push("Outcomes: total hospital stay is required.");
    }
    if (wizard.mortality === "yes") {
      if (!wizard.death_date.trim()) {
        errors.push("Death date is required when mortality is yes.");
      }
      if (!wizard.cause_of_death.trim()) {
        errors.push("Cause of death is required when mortality is yes.");
      }
    }
  }

  if (stepIndex === 4) {
    if (!wizard.extra_fields.follow_up__last_follow_up_date?.trim()) {
      errors.push("Follow-up: last follow-up date is required.");
    }
    if (!wizard.recanalization_status?.trim()) {
      errors.push("Recanalization status is required.");
    }
  }

  if (wizard.svt_status === "with_svt" && !wizard.vessel_involvement.trim()) {
    errors.push("Vessel involvement is required for SVT cases.");
  }

  return errors;
}
