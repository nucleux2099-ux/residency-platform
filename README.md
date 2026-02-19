# Residency Platform (Thesis Vault Frontend)

Starter monorepo for a React frontend + FastAPI backend that sits on top of your thesis vault.

## Structure
- `apps/web`: Next.js frontend with dashboard, cohort ops, follow-up monitor, data quality, patient library, vault, and ingestion tabs
- `apps/api`: FastAPI service for vault indexing, template ingestion, and analytics summary
- `packages/shared`: JSON schemas and shared domain artifacts

## Quick Start
1. Use Node LTS from `.nvmrc`:
   - `nvm install`
   - `nvm use`
2. Copy `.env.example` to `.env` and adjust paths.
3. Install JS deps: `pnpm install`
4. Setup API venv once: `pnpm run setup:api`
5. Start API (reload scoped to `apps/api/app` to avoid `.venv` watch loops):
   - `pnpm run dev:api`
6. Start web (separate terminal):
   - `pnpm run dev:web`
7. Run PHI scan before analytics/export work:
   - `pnpm run scan:phi`
8. If PHI findings exist, redact and re-scan:
   - `pnpm run redact:phi`
   - `pnpm run scan:phi --fail-on-findings`

## Notes
- The API currently stores ingestion events in `apps/api/data/patient_events.jsonl` for local development.
- `VAULT_ROOT` should point to your Obsidian vault root.
- Sample CSV for batch ingestion:
  - `packages/shared/templates/patient-template.v1.sample.csv`
  - `packages/shared/templates/patient-template.v2.sample.csv`
  - `packages/shared/templates/patient-proforma-v3.sample.csv`
- To backfill existing vault proformas into analytics, use:
  - `curl -X POST http://127.0.0.1:8000/ingestion/import-proformas`
- Auto-generated ingestion notes are written to `05-Logs/Auto-Patient-Entries` by default.
- Ingestion tab now supports:
  - Protocol-aligned multi-step patient logging wizard
  - Autosave drafts with resume
  - Case browser to reopen/edit existing patient entries
  - Per-patient attachment upload in submit flow
- Patient library tab now supports:
  - Live patient cards from `02-Data-Collection/Active-Cases`
  - In-app reader for proforma/notes and inline PDF lab report preview
  - Linked event history from ingestion event store
  - Marker-first OCR index + search over Active and Completed case documents
- Node `>=20 <21` is required by workspace package engines.
- Governance docs:
  - `docs/IMPLEMENTATION-ROADMAP.md`
  - `docs/COHORT-DATA-POLICY.md`
  - `docs/PROTOCOL-INGESTION-MAPPING.md`
