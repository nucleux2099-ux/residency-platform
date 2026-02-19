# Residency Platform Implementation Roadmap

## Context

This roadmap is customized for the AIIMS Bhopal SVT thesis workflow:
- Prospective observational study.
- Target cohort: 32.
- Primary endpoint: SVT recanalization at 3 months.
- Current risk areas: PHI leakage in markdown artifacts, cohort denominator drift, and dev-runtime instability.

Repository root:
`/Users/sarathchandrabhatla/Library/Mobile Documents/iCloud~md~obsidian/Documents/Thesis2099/residency-platform`

---

## Guiding Principles

1. Protocol-first data model (not generic form-first modeling).
2. De-identification by design (PHI never enters analytics payloads).
3. Single source of truth (event stream + projections drive dashboard and exports).
4. Missingness is a top KPI (not just an afterthought).
5. Reproducible thesis outputs (snapshot + deterministic export).

---

## Phase 0 - Governance and Runtime Hardening

Duration: 2-3 days

### Goals
- Stop developer runtime blockers (watch reload loops, node drift).
- Add PHI control guardrails before scaling ingestion.
- Freeze operating definitions for cohort and endpoint states.

### Deliverables
1. Stable local run scripts (API/Web).
2. Node LTS pinning and setup notes.
3. PHI scan script for markdown/csv guard checks.
4. Cohort registry policy document (canonical denominator rules).

### Tasks
- Add API dev command that restricts reload scope to `app/` and excludes `.venv`.
- Add Node version pin (`.nvmrc`) and package engines.
- Add PHI scanner script for common leakage tokens (name/contact/CR/MRN patterns).
- Define canonical cohort rules:
  - enrollment = consented and assigned Study ID.
  - active = enrolled and not completed/withdrawn/deceased/LTFU.
  - completed = has primary endpoint or terminal outcome.

### Definition of Done
- API dev server runs >10 minutes with no watch-loop reload from `.venv`.
- Web app starts with installed dependencies on supported Node LTS.
- PHI scan command runs and produces machine-readable output.
- Written cohort policy accepted as source-of-truth rule set for dashboard metrics.

---

## Phase 1 - Schema and Ingestion Hardening

Duration: 1-1.5 weeks

### Goals
- Move from generic intake to thesis-grade, timepoint-aware ingestion.
- Enforce quality at write-time (not cleanup-time).

### Deliverables
1. `patient-template.v2` schema aligned to protocol timepoints.
2. Extended `PatientSubmission` model with visit context and endpoint fields.
3. Strong validator with cross-field checks.
4. CSV ingestion with row-level actionable errors.

### Timepoint Model
- baseline
- day7_reassessment
- discharge
- week2_followup
- month1_followup
- month3_followup

### Core Validation Rules
- `patient_id` must match pseudonymous Study ID format.
- `mortality=yes` requires `death_date` and `cause_of_death`.
- Follow-up visit dates must satisfy configured windows.
- `with_svt` events must include vessel involvement detail.
- Notes and free text should fail on obvious PHI patterns.

### Definition of Done
- Invalid submissions blocked with precise error payloads.
- CSV batch shows accepted/rejected rows with causes.
- Required completeness score computable per patient timeline.
- No new PHI leaks accepted through API layer.

---

## Phase 2 - Dashboard, Cohort Ops, and Alerts

Duration: 1 week

### Goals
- Turn dashboard into daily residency operations console.
- Surface protocol-risk and missingness in real time.

### Deliverables
1. New analytics projections backend.
2. Dashboard panels:
   - Enrollment progress.
   - Follow-up due/overdue.
   - Completeness by timepoint.
   - Safety events and mortality.
   - Recanalization trend.
3. New UI routes:
   - `/cohort`
   - `/followups`
   - `/data-quality`

### Definition of Done
- Dashboard numbers derive from projected event data only.
- Overdue follow-up list updates without manual recalculation.
- Data quality panel flags missing critical fields and conflicts.

---

## Phase 3 - Thesis Exports and Snapshot Locking

Duration: 4-5 days

### Goals
- Generate thesis-ready outputs from the platform, reproducibly.

### Deliverables
1. Monthly locked snapshots (json/csv).
2. Export commands for:
   - cohort table.
   - SVT subgroup outcomes.
   - follow-up adherence.
   - safety events.
3. Metadata manifest (schema version, generated timestamp, source signature).

### Definition of Done
- Same snapshot always yields identical table outputs.
- Each analytic claim traceable to source data fields.

---

## Phase Sequencing and Dependencies

1. Complete Phase 0 before broadening ingestion scope.
2. Complete Phase 1 before expanding dashboard KPI set.
3. Complete Phase 2 before final publication automation.
4. Keep Phase 3 export format stable once thesis writing starts.

---

## Execution Checklist (Immediate)

### Slice A (now)
- [x] Add runtime hardening scripts and Node LTS pinning.
- [x] Add PHI scan utility and command.
- [x] Document API/Web startup commands.

### Slice B
- [x] Implement `patient-template.v2`.
- [x] Add schema + validator extensions for timepoint ingestion.

### Slice C
- [x] Build projections and advanced analytics endpoints.
- [x] Add cohort/followup/data-quality pages.

### Slice D
- [x] Add semantic design tokens and responsive app shell styling.
- [x] Upgrade dashboard KPI cards and risk panels to reusable visual components.
- [x] Apply shared page headers and table/panel treatment across core analytics screens.

---

## Risks and Mitigations

- Risk: Cohort mismatch across sources.
  - Mitigation: canonical registry + projection layer conflicts report.
- Risk: PHI in historic markdown remains.
  - Mitigation: scanner + cleanup backlog + ingestion-time PHI blocks.
- Risk: Dev environment instability (node/python drift).
  - Mitigation: pinned versions + explicit startup scripts.

---

## Ownership

Primary owner: Dr Sarath Chandrabhatla  
Implementation agent: Codex  
Operating model: iterative delivery with phase gates
