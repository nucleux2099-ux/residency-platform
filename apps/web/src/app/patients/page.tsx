"use client";

import { useEffect, useMemo, useState } from "react";
import {
  fetchPatientDocumentIndexStatus,
  fetchPatientDocumentSearch,
  fetchPatientExtractedFile,
  fetchPatientFilePreview,
  fetchPatientIndexedFiles,
  fetchPatientLabTrends,
  fetchPatientLabTimeline,
  fetchPatientLibraryCards,
  fetchPatientLibraryDetail,
  getPatientFileUrl,
  triggerPatientDocumentReindex
} from "@/lib/api";
import { PageHeader } from "@/components/ui/PageHeader";
import {
  PatientDocumentIndexStatus,
  PatientDocumentSearchHit,
  PatientExtractedDocument,
  PatientIndexedFileSummary,
  PatientLabTrendMetric,
  PatientLabTrendPayload,
  PatientLabTimelineItem,
  PatientFilePreview,
  PatientLibraryCard,
  PatientLibraryDetail,
  PatientLibraryFile
} from "@/lib/types";

type SvtFilter = "all" | "with_svt" | "without_svt" | "unknown";
type BucketFilter = "all" | "active" | "completed";
type FileFilter = "notes" | "labs" | "all";
type SearchScope = "all" | "selected";
type CardSort = "updated" | "name" | "labs" | "files";

function formatDate(value: string | null): string {
  if (!value) {
    return "-";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleDateString(undefined, { day: "2-digit", month: "short", year: "numeric" });
}

function formatBytes(bytes: number): string {
  if (bytes <= 0) {
    return "0 B";
  }
  if (bytes < 1024) {
    return `${bytes} B`;
  }
  const kb = bytes / 1024;
  if (kb < 1024) {
    return `${kb.toFixed(1)} KB`;
  }
  const mb = kb / 1024;
  return `${mb.toFixed(1)} MB`;
}

function statusTone(status: string | null): "neutral" | "info" | "success" | "warning" {
  const value = (status || "").toLowerCase();
  if (value === "completed") {
    return "success";
  }
  if (value === "active" || value === "enrolled") {
    return "info";
  }
  if (value === "terminal_outcome") {
    return "warning";
  }
  return "neutral";
}

function svtLabel(status: PatientLibraryCard["svt_status"]): string {
  if (status === "with_svt") {
    return "SVT";
  }
  if (status === "without_svt") {
    return "Non-SVT";
  }
  return "Unclassified";
}

function categoryLabel(file: PatientLibraryFile): string {
  if (file.category === "lab_report") {
    return "Lab report";
  }
  if (file.category === "proforma") {
    return "Proforma";
  }
  if (file.category === "imaging") {
    return "Imaging";
  }
  if (file.category === "discharge") {
    return "Discharge";
  }
  if (file.category === "note") {
    return "Note";
  }
  return "Attachment";
}

function bucketLabel(bucket: "active" | "completed"): string {
  return bucket === "active" ? "Active" : "Completed";
}

function indexStatusLabel(status: string | null): string {
  const value = (status || "").toLowerCase();
  if (value === "indexed") {
    return "Indexed";
  }
  if (value === "pending") {
    return "Pending";
  }
  if (value === "failed") {
    return "Failed";
  }
  return "Unknown";
}

function indexStatusTone(status: string | null): "indexed" | "pending" | "failed" | "unknown" {
  const value = (status || "").toLowerCase();
  if (value === "indexed") {
    return "indexed";
  }
  if (value === "pending") {
    return "pending";
  }
  if (value === "failed") {
    return "failed";
  }
  return "unknown";
}

function abnormalTone(count: number): "indexed" | "pending" {
  return count > 0 ? "pending" : "indexed";
}

function formatMetricValue(value: number | null | undefined): string {
  if (typeof value !== "number" || Number.isNaN(value)) {
    return "-";
  }
  if (Math.abs(value) >= 100) {
    return value.toFixed(1);
  }
  if (Math.abs(value) >= 10) {
    return value.toFixed(2);
  }
  return value.toFixed(2);
}

function trendBadgeTone(status: string | null): "indexed" | "pending" | "failed" | "unknown" {
  const value = (status || "").toLowerCase();
  if (value === "normal") {
    return "indexed";
  }
  if (value === "high" || value === "low") {
    return "pending";
  }
  return "unknown";
}

function buildSparkline(values: number[], width = 200, height = 52, padding = 6): string {
  if (values.length === 0) {
    return "";
  }
  if (values.length === 1) {
    const midY = height / 2;
    return `${padding},${midY} ${width - padding},${midY}`;
  }

  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = Math.max(max - min, 0.001);
  const stepX = (width - padding * 2) / (values.length - 1);

  return values
    .map((value, index) => {
      const x = padding + stepX * index;
      const y = height - padding - ((value - min) / range) * (height - padding * 2);
      return `${x.toFixed(2)},${y.toFixed(2)}`;
    })
    .join(" ");
}

function daysSince(dateText: string | null): number | null {
  if (!dateText) {
    return null;
  }
  const date = new Date(dateText);
  if (Number.isNaN(date.getTime())) {
    return null;
  }
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  return Math.floor(diffMs / (1000 * 60 * 60 * 24));
}

export default function PatientsPage() {
  const [query, setQuery] = useState("");
  const [svtFilter, setSvtFilter] = useState<SvtFilter>("all");
  const [bucketFilter, setBucketFilter] = useState<BucketFilter>("all");
  const [cardSort, setCardSort] = useState<CardSort>("updated");
  const [cards, setCards] = useState<PatientLibraryCard[]>([]);
  const [cardsLoading, setCardsLoading] = useState(true);
  const [cardsError, setCardsError] = useState("");

  const [selectedPatientKey, setSelectedPatientKey] = useState("");
  const [detail, setDetail] = useState<PatientLibraryDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState("");

  const [fileFilter, setFileFilter] = useState<FileFilter>("notes");
  const [fileQuery, setFileQuery] = useState("");
  const [selectedFileId, setSelectedFileId] = useState("");
  const [preview, setPreview] = useState<PatientFilePreview | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState("");
  const [extracted, setExtracted] = useState<PatientExtractedDocument | null>(null);
  const [extractedLoading, setExtractedLoading] = useState(false);
  const [extractedError, setExtractedError] = useState("");

  const [searchText, setSearchText] = useState("");
  const [searchScope, setSearchScope] = useState<SearchScope>("all");
  const [searchHits, setSearchHits] = useState<PatientDocumentSearchHit[]>([]);
  const [searchLoading, setSearchLoading] = useState(false);
  const [searchError, setSearchError] = useState("");
  const [pendingFileSelection, setPendingFileSelection] = useState<{ patientKey: string; fileId: string } | null>(null);

  const [indexStatus, setIndexStatus] = useState<PatientDocumentIndexStatus | null>(null);
  const [indexStatusError, setIndexStatusError] = useState("");
  const [reindexing, setReindexing] = useState(false);
  const [indexedFilesById, setIndexedFilesById] = useState<Record<string, PatientIndexedFileSummary>>({});
  const [indexedFilesLoading, setIndexedFilesLoading] = useState(false);
  const [indexedFilesError, setIndexedFilesError] = useState("");
  const [labTimeline, setLabTimeline] = useState<PatientLabTimelineItem[]>([]);
  const [labTimelineLoading, setLabTimelineLoading] = useState(false);
  const [labTimelineError, setLabTimelineError] = useState("");
  const [labTimelineQuery, setLabTimelineQuery] = useState("");
  const [labTimelineAbnormalOnly, setLabTimelineAbnormalOnly] = useState(false);
  const [labTrends, setLabTrends] = useState<PatientLabTrendPayload | null>(null);
  const [labTrendsLoading, setLabTrendsLoading] = useState(false);
  const [labTrendsError, setLabTrendsError] = useState("");

  useEffect(() => {
    let mounted = true;

    const loadCards = (silent: boolean) => {
      if (!silent) {
        setCardsLoading(true);
      }
      setCardsError("");

      fetchPatientLibraryCards(
        query,
        svtFilter === "all" ? undefined : svtFilter,
        bucketFilter === "all" ? undefined : bucketFilter,
        300
      )
        .then((items) => {
          if (!mounted) {
            return;
          }
          setCards(items);
        })
        .catch((err: Error) => {
          if (!mounted) {
            return;
          }
          setCards([]);
          setCardsError(err.message || "Failed to load patient library");
        })
        .finally(() => {
          if (!mounted) {
            return;
          }
          if (!silent) {
            setCardsLoading(false);
          }
        });
    };

    const timeout = setTimeout(() => loadCards(false), 200);
    const interval = window.setInterval(() => loadCards(true), 12000);

    return () => {
      mounted = false;
      clearTimeout(timeout);
      window.clearInterval(interval);
    };
  }, [bucketFilter, query, svtFilter]);

  const displayCards = useMemo(() => {
    const items = [...cards];
    if (cardSort === "name") {
      items.sort((a, b) => a.display_name.localeCompare(b.display_name));
      return items;
    }
    if (cardSort === "labs") {
      items.sort((a, b) => {
        if (b.lab_report_count !== a.lab_report_count) {
          return b.lab_report_count - a.lab_report_count;
        }
        return (b.last_updated_at || "").localeCompare(a.last_updated_at || "");
      });
      return items;
    }
    if (cardSort === "files") {
      items.sort((a, b) => {
        if (b.file_count !== a.file_count) {
          return b.file_count - a.file_count;
        }
        return (b.last_updated_at || "").localeCompare(a.last_updated_at || "");
      });
      return items;
    }
    items.sort((a, b) => (b.last_updated_at || "").localeCompare(a.last_updated_at || ""));
    return items;
  }, [cards, cardSort]);

  useEffect(() => {
    if (displayCards.length === 0) {
      setSelectedPatientKey("");
      setDetail(null);
      return;
    }

    const exists = displayCards.some((card) => card.patient_key === selectedPatientKey);
    if (!exists) {
      setSelectedPatientKey(displayCards[0].patient_key);
    }
  }, [displayCards, selectedPatientKey]);

  useEffect(() => {
    if (!selectedPatientKey) {
      return;
    }

    setDetailLoading(true);
    setDetailError("");

    fetchPatientLibraryDetail(selectedPatientKey)
      .then((result) => {
        setDetail(result);
      })
      .catch((err: Error) => {
        setDetail(null);
        setDetailError(err.message || "Failed to load patient detail");
      })
      .finally(() => setDetailLoading(false));
  }, [selectedPatientKey]);

  useEffect(() => {
    if (!detail) {
      setIndexedFilesById({});
      setIndexedFilesError("");
      setIndexedFilesLoading(false);
      return;
    }

    let mounted = true;
    setIndexedFilesLoading(true);
    setIndexedFilesError("");

    fetchPatientIndexedFiles(detail.patient.patient_key)
      .then((items) => {
        if (!mounted) {
          return;
        }
        const next: Record<string, PatientIndexedFileSummary> = {};
        for (const item of items) {
          if (item.file_id) {
            next[item.file_id] = item;
          }
        }
        setIndexedFilesById(next);
      })
      .catch((err: Error) => {
        if (!mounted) {
          return;
        }
        setIndexedFilesById({});
        setIndexedFilesError(err.message || "File index status unavailable");
      })
      .finally(() => {
        if (!mounted) {
          return;
        }
        setIndexedFilesLoading(false);
      });

    return () => {
      mounted = false;
    };
  }, [detail]);

  useEffect(() => {
    if (!detail) {
      setLabTimeline([]);
      setLabTimelineError("");
      setLabTimelineLoading(false);
      setLabTimelineQuery("");
      setLabTimelineAbnormalOnly(false);
      return;
    }

    let mounted = true;
    setLabTimelineLoading(true);
    setLabTimelineError("");

    fetchPatientLabTimeline(detail.patient.patient_key, 120)
      .then((items) => {
        if (!mounted) {
          return;
        }
        setLabTimeline(items);
      })
      .catch((err: Error) => {
        if (!mounted) {
          return;
        }
        setLabTimeline([]);
        setLabTimelineError(err.message || "Lab timeline unavailable");
      })
      .finally(() => {
        if (!mounted) {
          return;
        }
        setLabTimelineLoading(false);
      });

    return () => {
      mounted = false;
    };
  }, [detail]);

  useEffect(() => {
    if (!detail) {
      setLabTrends(null);
      setLabTrendsError("");
      setLabTrendsLoading(false);
      return;
    }

    let mounted = true;
    setLabTrendsLoading(true);
    setLabTrendsError("");

    fetchPatientLabTrends(detail.patient.patient_key, 140)
      .then((payload) => {
        if (!mounted) {
          return;
        }
        setLabTrends(payload);
      })
      .catch((err: Error) => {
        if (!mounted) {
          return;
        }
        setLabTrends(null);
        setLabTrendsError(err.message || "Lab trends unavailable");
      })
      .finally(() => {
        if (!mounted) {
          return;
        }
        setLabTrendsLoading(false);
      });

    return () => {
      mounted = false;
    };
  }, [detail]);

  useEffect(() => {
    if (!detail) {
      setSelectedFileId("");
      setFileQuery("");
      return;
    }

    if (
      pendingFileSelection &&
      pendingFileSelection.patientKey === detail.patient.patient_key &&
      detail.files.some((item) => item.file_id === pendingFileSelection.fileId)
    ) {
      setFileFilter("all");
      setSelectedFileId(pendingFileSelection.fileId);
      setPendingFileSelection(null);
      return;
    }

    const preferredFileId =
      detail.patient.selected_note_file_id || detail.notes[0]?.file_id || detail.lab_reports[0]?.file_id || detail.files[0]?.file_id;

    if (preferredFileId) {
      setSelectedFileId(preferredFileId);
    }

    if (detail.notes.length > 0) {
      setFileFilter("notes");
    } else if (detail.lab_reports.length > 0) {
      setFileFilter("labs");
    } else {
      setFileFilter("all");
    }
    setFileQuery("");
  }, [detail, pendingFileSelection]);

  const selectedFile = useMemo(() => {
    if (!detail || !selectedFileId) {
      return null;
    }
    return detail.files.find((file) => file.file_id === selectedFileId) || null;
  }, [detail, selectedFileId]);

  const visibleFiles = useMemo(() => {
    if (!detail) {
      return [] as PatientLibraryFile[];
    }

    let files = detail.files;
    if (fileFilter === "notes") {
      files = detail.files.filter((file) => file.category === "proforma" || file.category === "note");
    } else if (fileFilter === "labs") {
      files = detail.files.filter((file) => file.category === "lab_report");
    }

    const queryToken = fileQuery.trim().toLowerCase();
    if (queryToken) {
      files = files.filter((file) =>
        [file.file_name, file.relative_path, file.category].join(" ").toLowerCase().includes(queryToken)
      );
    }

    return [...files].sort((a, b) => (b.updated_at || "").localeCompare(a.updated_at || ""));
  }, [detail, fileFilter, fileQuery]);

  const selectedFileIndexStatus = useMemo(() => {
    if (!selectedFile) {
      return null;
    }
    return indexedFilesById[selectedFile.file_id] || null;
  }, [indexedFilesById, selectedFile]);

  const visibleLabTimeline = useMemo(() => {
    const token = labTimelineQuery.trim().toLowerCase();

    return labTimeline.filter((item) => {
      if (labTimelineAbnormalOnly && item.abnormal_markers <= 0) {
        return false;
      }
      if (!token) {
        return true;
      }
      return [item.file_name, item.summary || "", item.highlight_lines.join(" "), item.relative_path]
        .join(" ")
        .toLowerCase()
        .includes(token);
    });
  }, [labTimeline, labTimelineAbnormalOnly, labTimelineQuery]);

  const trendMetrics = useMemo(() => {
    if (!labTrends?.metrics) {
      return [] as PatientLabTrendMetric[];
    }
    return labTrends.metrics.slice(0, 8);
  }, [labTrends]);

  const activeCaseCards = useMemo(() => {
    return [...cards]
      .filter((card) => card.case_bucket === "active")
      .sort((a, b) => (b.last_updated_at || "").localeCompare(a.last_updated_at || ""))
      .slice(0, 8);
  }, [cards]);

  const completedCaseCards = useMemo(() => {
    return [...cards]
      .filter((card) => card.case_bucket === "completed")
      .sort((a, b) => (b.last_updated_at || "").localeCompare(a.last_updated_at || ""))
      .slice(0, 8);
  }, [cards]);

  const pinnedAlerts = useMemo(() => {
    const alerts: Array<{ severity: "high" | "medium" | "low"; message: string; patientKey?: string }> = [];

    if (indexStatus && indexStatus.documents_failed > 0) {
      alerts.push({
        severity: "high",
        message: `${indexStatus.documents_failed} indexed files failed OCR. Re-index queue review needed.`
      });
    }

    for (const card of cards) {
      if (card.cohort_status === "terminal_outcome") {
        alerts.push({
          severity: "high",
          message: `${card.display_name}: terminal outcome marker present.`,
          patientKey: card.patient_key
        });
      }
      if (card.case_bucket === "active" && card.lab_report_count === 0) {
        alerts.push({
          severity: "medium",
          message: `${card.display_name}: no lab report documents attached.`,
          patientKey: card.patient_key
        });
      }
      if (card.case_bucket === "active" && card.note_count === 0) {
        alerts.push({
          severity: "medium",
          message: `${card.display_name}: missing proforma/note file.`,
          patientKey: card.patient_key
        });
      }
      if (card.case_bucket === "active") {
        const idleDays = daysSince(card.last_encounter_date);
        if (typeof idleDays === "number" && idleDays > 21) {
          alerts.push({
            severity: "low",
            message: `${card.display_name}: last encounter ${idleDays} days ago.`,
            patientKey: card.patient_key
          });
        }
      }
    }

    const severityRank = { high: 3, medium: 2, low: 1 };
    return alerts
      .sort((a, b) => severityRank[b.severity] - severityRank[a.severity])
      .slice(0, 10);
  }, [cards, indexStatus]);

  useEffect(() => {
    if (!detail || !selectedFile) {
      setPreview(null);
      setPreviewError("");
      setExtracted(null);
      setExtractedError("");
      return;
    }

    if (selectedFile.is_text) {
      setExtracted(null);
      setExtractedError("");
      setExtractedLoading(false);
      setPreviewLoading(true);
      setPreviewError("");

      fetchPatientFilePreview(detail.patient.patient_key, selectedFile.file_id)
        .then((result) => {
          setPreview(result);
        })
        .catch((err: Error) => {
          setPreview(null);
          setPreviewError(err.message || "Failed to load note preview");
        })
        .finally(() => setPreviewLoading(false));
      return;
    }

    setPreview(null);
    setPreviewError("");
    setPreviewLoading(false);
    setExtractedLoading(true);
    setExtractedError("");

    fetchPatientExtractedFile(detail.patient.patient_key, selectedFile.file_id, 120000)
      .then((result) => {
        setExtracted(result);
      })
      .catch((err: Error) => {
        setExtracted(null);
        setExtractedError(err.message || "Failed to load OCR text");
      })
      .finally(() => setExtractedLoading(false));
  }, [detail, selectedFile]);

  useEffect(() => {
    if (!searchText.trim() || searchText.trim().length < 2) {
      setSearchHits([]);
      setSearchError("");
      setSearchLoading(false);
      return;
    }

    let mounted = true;
    const timeout = setTimeout(() => {
      setSearchLoading(true);
      setSearchError("");
      fetchPatientDocumentSearch(
        searchText.trim(),
        searchScope === "selected" ? selectedPatientKey || undefined : undefined,
        40
      )
        .then((items) => {
          if (!mounted) {
            return;
          }
          setSearchHits(items);
        })
        .catch((err: Error) => {
          if (!mounted) {
            return;
          }
          setSearchHits([]);
          setSearchError(err.message || "Search failed");
        })
        .finally(() => {
          if (!mounted) {
            return;
          }
          setSearchLoading(false);
        });
    }, 220);

    return () => {
      mounted = false;
      clearTimeout(timeout);
    };
  }, [searchScope, searchText, selectedPatientKey]);

  useEffect(() => {
    let mounted = true;

    const loadStatus = (silent: boolean) => {
      if (!silent) {
        setIndexStatusError("");
      }

      fetchPatientDocumentIndexStatus()
        .then((status) => {
          if (!mounted) {
            return;
          }
          setIndexStatus(status);
          setIndexStatusError("");
        })
        .catch((err: Error) => {
          if (!mounted) {
            return;
          }
          setIndexStatusError(err.message || "Indexer status unavailable");
        });
    };

    loadStatus(false);
    const interval = window.setInterval(() => loadStatus(true), 12000);

    return () => {
      mounted = false;
      window.clearInterval(interval);
    };
  }, []);

  const totals = useMemo(() => {
    return {
      patientCount: cards.length,
      activePatients: cards.filter((item) => item.case_bucket === "active").length,
      completedPatients: cards.filter((item) => item.case_bucket === "completed").length,
      labs: cards.reduce((total, item) => total + item.lab_report_count, 0),
      notes: cards.reduce((total, item) => total + item.note_count, 0),
      files: cards.reduce((total, item) => total + item.file_count, 0)
    };
  }, [cards]);

  const selectedFileUrl = selectedFile && detail ? getPatientFileUrl(detail.patient.patient_key, selectedFile.file_id) : "";

  async function handleReindexClick() {
    setReindexing(true);
    try {
      const status = await triggerPatientDocumentReindex(true);
      setIndexStatus(status);
      setIndexStatusError("");
    } catch (error) {
      const message = error instanceof Error ? error.message : "Re-index request failed";
      setIndexStatusError(message);
    } finally {
      setReindexing(false);
    }
  }

  function openPatientFile(patientKey: string, fileId: string, filter: FileFilter) {
    setFileFilter(filter);
    if (detail && patientKey === detail.patient.patient_key) {
      setSelectedFileId(fileId);
      return;
    }
    setSelectedPatientKey(patientKey);
    setPendingFileSelection({ patientKey, fileId });
  }

  function handleSearchHitSelect(hit: PatientDocumentSearchHit) {
    openPatientFile(hit.patient_key, hit.file_id, "all");
  }

  function handleTimelineSelect(item: PatientLabTimelineItem) {
    openPatientFile(item.patient_key, item.file_id, "labs");
  }

  function handleTrendPointSelect(patientKey: string, fileId: string) {
    openPatientFile(patientKey, fileId, "labs");
  }

  return (
    <section className="page">
      <PageHeader
        title="Patient Library"
        description="Live vault patient cards with linked proformas, lab reports, and attachment reader for daily thesis logging."
      />

      <div className="kpi-strip">
        <div className="kpi-pill">
          <span className="kpi-pill__label">Patients</span>
          <span className="kpi-pill__value">{totals.patientCount}</span>
        </div>
        <div className="kpi-pill">
          <span className="kpi-pill__label">Active</span>
          <span className="kpi-pill__value">{totals.activePatients}</span>
        </div>
        <div className="kpi-pill">
          <span className="kpi-pill__label">Completed</span>
          <span className="kpi-pill__value">{totals.completedPatients}</span>
        </div>
        <div className="kpi-pill">
          <span className="kpi-pill__label">Lab Reports</span>
          <span className="kpi-pill__value">{totals.labs}</span>
        </div>
        <div className="kpi-pill">
          <span className="kpi-pill__label">Notes</span>
          <span className="kpi-pill__value">{totals.notes}</span>
        </div>
        <div className="kpi-pill">
          <span className="kpi-pill__label">Total Files</span>
          <span className="kpi-pill__value">{totals.files}</span>
        </div>
      </div>

      <section className="panel">
        <div className="panel__header">
          <h2>Lab Report Search</h2>
          <p>Marker-first OCR index with live search across Active and Completed case files.</p>
        </div>
        <div className="panel__body panel__body--compact">
          <div className="patient-search-controls">
            <input
              type="search"
              value={searchText}
              placeholder="Search lab findings, values, or report text..."
              onChange={(event) => setSearchText(event.target.value)}
            />
            <select value={searchScope} onChange={(event) => setSearchScope(event.target.value as SearchScope)}>
              <option value="all">All patients</option>
              <option value="selected" disabled={!selectedPatientKey}>
                Current patient
              </option>
            </select>
            <button type="button" onClick={handleReindexClick} disabled={reindexing}>
              {reindexing ? "Re-indexing..." : "Re-index now"}
            </button>
          </div>

          {indexStatus ? (
            <div className="patient-index-status">
              <span>{indexStatus.documents_indexed} indexed</span>
              <span>{indexStatus.documents_failed} failed</span>
              <span>{indexStatus.documents_total} searchable docs</span>
              <span>{indexStatus.running ? "Indexer running" : "Indexer stopped"}</span>
            </div>
          ) : null}
          {indexStatusError ? <p className="wizard-error">{indexStatusError}</p> : null}

          {searchLoading ? <p className="text-muted">Searching indexed documents...</p> : null}
          {searchError ? <p className="wizard-error">{searchError}</p> : null}

          {searchText.trim().length >= 2 ? (
            <div className="patient-search-results">
              {searchHits.map((hit) => (
                <button key={`${hit.patient_key}-${hit.file_id}-${hit.relative_path}`} type="button" onClick={() => handleSearchHitSelect(hit)}>
                  <strong>
                    {hit.patient_display_name || hit.patient_key} - {hit.file_name}
                  </strong>
                  <small>
                    {hit.study_id || "Study ID pending"} - {hit.case_bucket || "unknown"} - score {hit.score}
                  </small>
                  <p>{hit.snippet}</p>
                </button>
              ))}
              {!searchLoading && searchHits.length === 0 ? <p className="text-muted">No document matches found.</p> : null}
            </div>
          ) : (
            <p className="text-muted">Type at least 2 characters to search OCR-indexed content.</p>
          )}
        </div>
      </section>

      <section className="panel">
        <div className="panel__header">
          <h2>Case Console</h2>
          <p>Split board for Active and Completed cases with pinned alerts for immediate action.</p>
        </div>
        <div className="panel__body panel__body--compact">
          <div className="case-console-layout">
            <div className="case-console-column">
              <div className="case-console-column__header">
                <h3>Active Cases</h3>
                <span>{activeCaseCards.length}</span>
              </div>
              <div className="case-console-card-list">
                {activeCaseCards.map((card) => (
                  <button
                    key={`active-${card.patient_key}`}
                    type="button"
                    className="case-console-card"
                    onClick={() => setSelectedPatientKey(card.patient_key)}
                  >
                    <strong>{card.display_name}</strong>
                    <small>{card.study_id || "Study ID pending"}</small>
                    <p>{card.diagnosis || "Diagnosis pending"}</p>
                    <div className="patient-file-row__chips">
                      <span className="patient-file-ocr-badge">{card.lab_report_count} labs</span>
                      <span className="patient-file-ocr-badge">{card.note_count} notes</span>
                      <span className="patient-file-ocr-badge">{formatDate(card.last_encounter_date)}</span>
                    </div>
                  </button>
                ))}
                {activeCaseCards.length === 0 ? <p className="text-muted">No active cases in current filter.</p> : null}
              </div>
            </div>

            <div className="case-console-column">
              <div className="case-console-column__header">
                <h3>Completed Cases</h3>
                <span>{completedCaseCards.length}</span>
              </div>
              <div className="case-console-card-list">
                {completedCaseCards.map((card) => (
                  <button
                    key={`completed-${card.patient_key}`}
                    type="button"
                    className="case-console-card case-console-card--completed"
                    onClick={() => setSelectedPatientKey(card.patient_key)}
                  >
                    <strong>{card.display_name}</strong>
                    <small>{card.study_id || "Study ID pending"}</small>
                    <p>{card.diagnosis || "Diagnosis pending"}</p>
                    <div className="patient-file-row__chips">
                      <span className="patient-file-ocr-badge">{card.lab_report_count} labs</span>
                      <span className="patient-file-ocr-badge">{card.note_count} notes</span>
                      <span className="patient-file-ocr-badge">{formatDate(card.last_encounter_date)}</span>
                    </div>
                  </button>
                ))}
                {completedCaseCards.length === 0 ? <p className="text-muted">No completed cases available yet.</p> : null}
              </div>
            </div>

            <div className="case-console-alerts">
              <div className="case-console-column__header">
                <h3>Pinned Alerts</h3>
                <span>{pinnedAlerts.length}</span>
              </div>
              <div className="case-console-alert-list">
                {pinnedAlerts.map((alert, index) => (
                  <button
                    key={`alert-${index}-${alert.message}`}
                    type="button"
                    className={`case-console-alert case-console-alert--${alert.severity}`}
                    onClick={() => {
                      if (alert.patientKey) {
                        setSelectedPatientKey(alert.patientKey);
                      }
                    }}
                  >
                    <strong>{alert.severity.toUpperCase()}</strong>
                    <p>{alert.message}</p>
                  </button>
                ))}
                {pinnedAlerts.length === 0 ? <p className="text-muted">No alerts currently pinned.</p> : null}
              </div>
            </div>
          </div>
        </div>
      </section>

      <div className="patient-library-layout">
        <aside className="panel patient-catalog-panel">
          <div className="panel__header">
            <h2>Vault Patients</h2>
            <p>Search by patient name, study ID, or diagnosis.</p>
          </div>

          <div className="panel__body patient-catalog-body">
            <div className="patient-catalog-controls">
              <input
                type="search"
                value={query}
                placeholder="Search patients..."
                onChange={(event) => setQuery(event.target.value)}
              />
              <select value={svtFilter} onChange={(event) => setSvtFilter(event.target.value as SvtFilter)}>
                <option value="all">All groups</option>
                <option value="with_svt">SVT only</option>
                <option value="without_svt">Non-SVT only</option>
                <option value="unknown">Unclassified</option>
              </select>
              <select value={bucketFilter} onChange={(event) => setBucketFilter(event.target.value as BucketFilter)}>
                <option value="all">All buckets</option>
                <option value="active">Active cases</option>
                <option value="completed">Completed cases</option>
              </select>
              <select value={cardSort} onChange={(event) => setCardSort(event.target.value as CardSort)}>
                <option value="updated">Sort: Last updated</option>
                <option value="name">Sort: Name</option>
                <option value="labs">Sort: Labs count</option>
                <option value="files">Sort: File count</option>
              </select>
            </div>

            {cardsLoading ? <p className="text-muted">Loading patient cards...</p> : null}
            {cardsError ? <p className="wizard-error">{cardsError}</p> : null}

            <div className="patient-card-list">
              {displayCards.map((card) => {
                const active = card.patient_key === selectedPatientKey;
                return (
                  <button
                    key={card.patient_key}
                    type="button"
                    className={`patient-card${active ? " patient-card--active" : ""}`}
                    onClick={() => setSelectedPatientKey(card.patient_key)}
                  >
                    <div className="patient-card__header">
                      <h3>{card.display_name}</h3>
                      <span className="status-badge status-badge--neutral">{svtLabel(card.svt_status)}</span>
                    </div>
                    <p className="patient-card__subline">{card.study_id || "Study ID pending"}</p>
                    <p className="patient-card__meta">{card.diagnosis || "Diagnosis pending"}</p>
                    <p className="patient-card__meta">{card.latest_visit || "Visit pending"} | {card.ward || "Ward pending"}</p>
                    <div className="patient-card__stats">
                      <span>{card.lab_report_count} labs</span>
                      <span>{card.note_count} notes</span>
                      <span>{card.file_count} files</span>
                    </div>
                    <div className="patient-card__footer">
                      <span className={`status-badge status-badge--${statusTone(card.cohort_status)}`}>
                        {card.cohort_status || "unknown"}
                      </span>
                      <small>
                        {bucketLabel(card.case_bucket)} - {formatDate(card.last_updated_at)}
                      </small>
                    </div>
                  </button>
                );
              })}

              {!cardsLoading && displayCards.length === 0 ? <p className="text-muted">No patients found for this filter.</p> : null}
            </div>
          </div>
        </aside>

        <section className="panel patient-detail-panel">
          <div className="panel__header">
            <h2>Patient Reader</h2>
            <p>Open proformas, lab reports, and supporting notes directly from the vault.</p>
          </div>

          <div className="panel__body patient-detail-body">
            {detailLoading ? <p className="text-muted">Loading patient detail...</p> : null}
            {detailError ? <p className="wizard-error">{detailError}</p> : null}

            {!detailLoading && !detailError && detail ? (
              <>
                <div className="patient-summary-grid">
                  <div>
                    <strong>{detail.patient.display_name}</strong>
                    <p className="text-muted">{detail.patient.study_id || "Study ID not linked"}</p>
                  </div>
                  <div>
                    <strong>Case Bucket</strong>
                    <p className="text-muted">{bucketLabel(detail.patient.case_bucket)}</p>
                  </div>
                  <div>
                    <strong>Ward</strong>
                    <p className="text-muted">{detail.patient.ward || "-"}</p>
                  </div>
                  <div>
                    <strong>Visit</strong>
                    <p className="text-muted">{detail.patient.latest_visit || "-"}</p>
                  </div>
                  <div>
                    <strong>Encounter</strong>
                    <p className="text-muted">{formatDate(detail.patient.last_encounter_date)}</p>
                  </div>
                </div>

                <section className="patient-trends">
                  <div className="patient-trends__header">
                    <h3>Lab Trends</h3>
                    {labTrends ? (
                      <small>
                        {labTrends.metrics.length} metrics from {labTrends.reports_considered} indexed lab reports
                      </small>
                    ) : null}
                  </div>
                  {labTrendsLoading ? <p className="text-muted">Building trendlines from OCR data...</p> : null}
                  {labTrendsError ? <p className="wizard-error">{labTrendsError}</p> : null}
                  <div className="patient-trends__grid">
                    {trendMetrics.map((metric) => {
                      const points = metric.points.map((point) => point.value);
                      const latestPoint = metric.points[metric.points.length - 1];
                      const sparkline = buildSparkline(points);
                      return (
                        <article key={metric.metric_key} className="patient-trend-card">
                          <div className="patient-trend-card__head">
                            <div>
                              <strong>{metric.label}</strong>
                              <small>
                                {formatMetricValue(metric.latest_value)} {metric.unit}
                              </small>
                            </div>
                            <div className="patient-file-row__chips">
                              <span className={`patient-file-ocr-badge patient-file-ocr-badge--${trendBadgeTone(metric.latest_status)}`}>
                                {metric.latest_status}
                              </span>
                              {typeof metric.delta === "number" ? (
                                <span className="patient-file-ocr-badge">
                                  {metric.delta > 0 ? "+" : ""}
                                  {formatMetricValue(metric.delta)}
                                </span>
                              ) : null}
                            </div>
                          </div>
                          <svg viewBox="0 0 200 52" className="patient-trend-card__sparkline" role="img" aria-label={`${metric.label} trend`}>
                            <polyline points={sparkline} />
                          </svg>
                          <div className="patient-trend-card__points">
                            {metric.points.slice(-4).map((point) => (
                              <button
                                key={`${metric.metric_key}-${point.file_id}-${point.source_date || ""}`}
                                type="button"
                                onClick={() => handleTrendPointSelect(detail.patient.patient_key, point.file_id)}
                              >
                                <small>{formatDate(point.source_date)}</small>
                                <strong>{formatMetricValue(point.value)}</strong>
                              </button>
                            ))}
                          </div>
                          {latestPoint?.line ? <p className="patient-trend-card__line">{latestPoint.line}</p> : null}
                        </article>
                      );
                    })}
                    {!labTrendsLoading && trendMetrics.length === 0 ? (
                      <p className="text-muted">No trend metrics extracted yet from available lab reports.</p>
                    ) : null}
                  </div>
                </section>

                <section className="patient-lab-timeline">
                  <div className="patient-lab-timeline__header">
                    <h3>Lab Timeline</h3>
                    <div className="patient-lab-timeline__controls">
                      <input
                        type="search"
                        value={labTimelineQuery}
                        placeholder="Filter timeline..."
                        onChange={(event) => setLabTimelineQuery(event.target.value)}
                      />
                      <label>
                        <input
                          type="checkbox"
                          checked={labTimelineAbnormalOnly}
                          onChange={(event) => setLabTimelineAbnormalOnly(event.target.checked)}
                        />
                        Abnormal only
                      </label>
                    </div>
                  </div>
                  {labTimelineLoading ? <p className="text-muted">Loading lab timeline...</p> : null}
                  {labTimelineError ? <p className="wizard-error">{labTimelineError}</p> : null}
                  <div className="patient-lab-timeline__list">
                    {visibleLabTimeline.map((item) => (
                      <button
                        key={`${item.file_id}-${item.source_date || ""}`}
                        type="button"
                        className={`patient-lab-card${selectedFileId === item.file_id ? " patient-lab-card--active" : ""}`}
                        onClick={() => handleTimelineSelect(item)}
                      >
                        <div className="patient-lab-card__header">
                          <strong>{item.file_name}</strong>
                          <span>{formatDate(item.lab_date || item.updated_at || item.indexed_at)}</span>
                        </div>
                        <div className="patient-file-row__chips">
                          <span className={`patient-file-ocr-badge patient-file-ocr-badge--${indexStatusTone(item.status)}`}>
                            {indexStatusLabel(item.status)}
                          </span>
                          <span className={`patient-file-ocr-badge patient-file-ocr-badge--${abnormalTone(item.abnormal_markers)}`}>
                            {item.abnormal_markers} flagged
                          </span>
                          {item.extractor ? <span className="patient-file-ocr-badge">{item.extractor}</span> : null}
                        </div>
                        {item.summary ? <p>{item.summary}</p> : null}
                        {item.highlight_lines.length > 0 ? (
                          <div className="patient-lab-card__highlights">
                            {item.highlight_lines.slice(0, 2).map((line, idx) => (
                              <small key={`${item.file_id}-h-${idx}`}>{line}</small>
                            ))}
                          </div>
                        ) : null}
                      </button>
                    ))}
                    {!labTimelineLoading && visibleLabTimeline.length === 0 ? (
                      <p className="text-muted">No lab reports match this filter.</p>
                    ) : null}
                  </div>
                </section>

                <div className="patient-reader-shell">
                  <aside className="patient-files-panel">
                    <div className="patient-file-filters">
                      <button
                        type="button"
                        className={`ingestion-tab${fileFilter === "notes" ? " ingestion-tab--active" : ""}`}
                        onClick={() => setFileFilter("notes")}
                      >
                        Notes ({detail.notes.length})
                      </button>
                      <button
                        type="button"
                        className={`ingestion-tab${fileFilter === "labs" ? " ingestion-tab--active" : ""}`}
                        onClick={() => setFileFilter("labs")}
                      >
                        Labs ({detail.lab_reports.length})
                      </button>
                      <button
                        type="button"
                        className={`ingestion-tab${fileFilter === "all" ? " ingestion-tab--active" : ""}`}
                        onClick={() => setFileFilter("all")}
                      >
                        All ({detail.files.length})
                      </button>
                    </div>
                    <input
                      type="search"
                      className="patient-file-search"
                      value={fileQuery}
                      placeholder="Filter files in this patient..."
                      onChange={(event) => setFileQuery(event.target.value)}
                    />
                    {indexedFilesLoading ? <p className="text-muted">Loading index metadata...</p> : null}
                    {indexedFilesError ? <p className="wizard-error">{indexedFilesError}</p> : null}

                    <div className="patient-file-list">
                      {visibleFiles.map((file) => {
                        const active = file.file_id === selectedFileId;
                        const indexedFile = indexedFilesById[file.file_id];
                        return (
                          <button
                            key={file.file_id}
                            type="button"
                            className={`patient-file-row${active ? " patient-file-row--active" : ""}`}
                            onClick={() => setSelectedFileId(file.file_id)}
                          >
                            <div>
                              <strong>{file.file_name}</strong>
                              <small>
                                {categoryLabel(file)} - {formatBytes(file.size_bytes)}
                              </small>
                              {indexedFile ? (
                                <div className="patient-file-row__chips">
                                  <span className={`patient-file-ocr-badge patient-file-ocr-badge--${indexStatusTone(indexedFile.status)}`}>
                                    {indexStatusLabel(indexedFile.status)}
                                  </span>
                                  {indexedFile.extractor && indexedFile.extractor !== "none" ? (
                                    <span className="patient-file-ocr-badge">{indexedFile.extractor}</span>
                                  ) : null}
                                </div>
                              ) : null}
                            </div>
                            <span>{formatDate(file.updated_at)}</span>
                          </button>
                        );
                      })}

                      {visibleFiles.length === 0 ? <p className="text-muted">No files for this view.</p> : null}
                    </div>
                  </aside>

                  <article className="patient-reader-panel">
                    {selectedFile ? (
                      <>
                        <header className="patient-reader-header">
                          <div>
                            <h3>{selectedFile.file_name}</h3>
                            <p className="text-muted">
                              {categoryLabel(selectedFile)} - {selectedFile.relative_path}
                            </p>
                            {selectedFileIndexStatus ? (
                              <div className="patient-reader-meta">
                                <span className={`patient-file-ocr-badge patient-file-ocr-badge--${indexStatusTone(selectedFileIndexStatus.status)}`}>
                                  {indexStatusLabel(selectedFileIndexStatus.status)}
                                </span>
                                <span className="patient-file-ocr-badge">{selectedFileIndexStatus.extractor || "unknown"}</span>
                                <span className="patient-file-ocr-badge">{selectedFileIndexStatus.text_chars || 0} chars</span>
                                {selectedFileIndexStatus.error ? (
                                  <span className="patient-file-ocr-badge patient-file-ocr-badge--failed">Error</span>
                                ) : null}
                              </div>
                            ) : null}
                          </div>
                          <a href={selectedFileUrl} target="_blank" rel="noreferrer" className="sidebar__folder-link">
                            Open file
                          </a>
                        </header>

                        {selectedFile.is_text ? (
                          <div className="patient-note-view">
                            {previewLoading ? <p className="text-muted">Loading note preview...</p> : null}
                            {previewError ? <p className="wizard-error">{previewError}</p> : null}
                            {!previewLoading && !previewError && preview ? (
                              preview.preview_supported ? (
                                <>
                                  <pre className="patient-note-pre">{preview.content}</pre>
                                  {preview.truncated ? (
                                    <p className="text-muted">Preview truncated for performance. Use Open file for full note.</p>
                                  ) : null}
                                </>
                              ) : (
                                <p className="text-muted">{preview.message || "Preview unavailable."}</p>
                              )
                            ) : null}
                          </div>
                        ) : (
                          <>
                            {selectedFile.mime_type.startsWith("image/") ? (
                              <div className="patient-media-frame-wrap">
                                <img className="patient-image-preview" src={selectedFileUrl} alt={selectedFile.file_name} />
                              </div>
                            ) : selectedFile.mime_type.includes("pdf") ? (
                              <iframe
                                className="patient-media-frame"
                                title={selectedFile.file_name}
                                src={`${selectedFileUrl}#toolbar=0&navpanes=0`}
                              />
                            ) : (
                              <p className="text-muted">Inline preview not available for this file type. Use Open file.</p>
                            )}

                            <div className="patient-note-view">
                              <h4 className="patient-note-heading">OCR Extracted Text</h4>
                              {extractedLoading ? <p className="text-muted">Running OCR extraction...</p> : null}
                              {extractedError ? <p className="wizard-error">{extractedError}</p> : null}
                              {!extractedLoading && !extractedError && extracted ? (
                                extracted.status === "indexed" ? (
                                  <>
                                    <pre className="patient-note-pre">{extracted.content}</pre>
                                    {extracted.content_truncated ? (
                                      <p className="text-muted">Extracted text is truncated in view for performance.</p>
                                    ) : null}
                                  </>
                                ) : (
                                  <p className="text-muted">{extracted.error || "OCR text not available for this file yet."}</p>
                                )
                              ) : null}
                            </div>
                          </>
                        )}
                      </>
                    ) : (
                      <p className="text-muted">Select a file to open the reader.</p>
                    )}
                  </article>
                </div>

                {detail.event_history.length > 0 ? (
                  <div className="table-wrap">
                    <table className="data-table">
                      <thead>
                        <tr>
                          <th>Visit</th>
                          <th>Encounter</th>
                          <th>Cohort Status</th>
                          <th>Ward</th>
                          <th>Updated</th>
                        </tr>
                      </thead>
                      <tbody>
                        {detail.event_history.slice(0, 6).map((item) => (
                          <tr key={`${item.updated_at}-${item.visit_type}`}>
                            <td>{item.visit_type || "-"}</td>
                            <td>{formatDate(item.encounter_date)}</td>
                            <td>{item.cohort_status || "-"}</td>
                            <td>{item.ward || "-"}</td>
                            <td>{formatDate(item.updated_at)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : null}
              </>
            ) : null}

            {!detailLoading && !detailError && !detail ? (
              <p className="text-muted">Select a patient card to open their vault notes and reports.</p>
            ) : null}
          </div>
        </section>
      </div>
    </section>
  );
}
