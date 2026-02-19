# Protocol Ingestion Mapping (AIIMS SVT Thesis)

This mapping was built from extracted protocol text:
- `/Users/sarathchandrabhatla/Library/Mobile Documents/iCloud~md~obsidian/Documents/Thesis2099/05-Logs/Protocol-Extract/IHEC-Protocol.txt`
- `/Users/sarathchandrabhatla/Library/Mobile Documents/iCloud~md~obsidian/Documents/Thesis2099/05-Logs/Protocol-Extract/Patient-Proforma.txt`

## Protocol anchors used
- Primary / secondary objectives: lines 307-313.
- Inclusion criteria: line 337.
- Exclusion criteria: line 340.
- Sample size: line 359 (n = 32).
- Annexure patient proforma starts: line 784.
- Proforma sections:
  - Initial assessment / follow-up: line 789
  - Investigations: line 870
  - Management: line 983
  - Outcomes: line 1016
  - Last follow-up status: line 1054

## Wizard mapping

### Step 1 - Demographics
Protocol sections covered:
- Date, Study ID, demographics fields, addictions.

Stored as:
- Core fields: `patient_id`, `encounter_date`, `diagnosis`, `visit_type`, `svt_status`, `ward`, `cohort_status`
- Extra fields prefix: `demographics__*`, `addictions__*`

### Step 2 - Clinical Profile
Protocol sections covered:
- Clinical details (pain + associated symptoms)
- Comorbidities
- Etiology and AP severity block

Stored as:
- Extra fields prefix: `clinical_details__*`, `comorbidities__*`, `etiology_of_acute_pancreatitis__*`, `acute_pancreatitis__*`

### Step 3 - Investigations & SVT Mapping
Protocol sections covered:
- Lab investigations table
- Imaging/endoscopy table
- Overall findings and splanchnic venous assessment
- Portal hypertensive changes and vascular complications

Stored as:
- Structured rows serialized to JSON:
  - `investigations__laboratory_entries_json`
  - `investigations__imaging_entries_json`
- Extra fields prefix: `overall_findings__*`, `splanchnic_venous_assessment__*`, `portal_hypertensive_changes__*`, `vascular_complications__*`

### Step 4 - Management & Outcomes
Protocol sections covered:
- Conservative/interventional management
- Other interventions table
- Anticoagulation details
- Outcomes and morbidity

Stored as:
- Structured rows serialized to JSON:
  - `management__other_interventions_json`
- Extra fields prefix: `management__*`, `outcomes__*`

### Step 5 - Follow-up, Attachments, and Review
Protocol sections covered:
- Follow-up SVT assessment and progression/recanalization/new onset
- Last follow-up status
- Additional morbidity notes

Stored as:
- Core fields: `recanalization_status`, `primary_endpoint_complete`, `notes`
- Extra fields prefix: `follow_up__*`
- Attachments: uploaded via `/ingestion/files`, linked in `source_files`

## Existing vault backfill
- Endpoint: `POST /ingestion/import-proformas`
- Purpose: parse historical proforma markdown and append to event store.
- This allows dashboard/analytics pages to show previously recorded thesis cases.

## UX implementation status
- Multi-step wizard enforces required fields per protocol section before advancing.
- Drafts autosave in browser local storage and can be resumed/deleted.
- Existing cases can be searched and reopened from `GET /ingestion/cases` + `GET /ingestion/cases/{patient_id}`.
- Reopened cases load into wizard for revision; saving creates a new append-only event.
