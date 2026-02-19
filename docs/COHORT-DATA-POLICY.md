# Cohort and Data Policy

## Purpose

This policy defines canonical cohort counting and endpoint status rules for the SVT thesis platform.
All dashboard and export metrics must follow this policy.

---

## Canonical Patient Identifier

- Allowed identifier for platform analytics: pseudonymous Study ID only.
- Expected format: `AP-SVT-###` (or approved non-SVT control prefix as finalized by PI policy).
- PHI fields (name, CR number, phone, address) are disallowed in ingestion payloads.

---

## Cohort Status Definitions

1. `screened`
   - Evaluated for eligibility.
   - Not counted in enrolled denominator.

2. `enrolled`
   - Consent obtained and Study ID assigned.
   - Counted in enrolled denominator.

3. `active`
   - Enrolled and still in protocol follow-up window.

4. `completed`
   - Reached 3-month endpoint with outcome documented.

5. `terminal_outcome`
   - Deceased, consent withdrawn, or lost to follow-up after documented attempts.
   - Counted as closed, not active.

---

## Endpoint Rules

- Primary endpoint: SVT recanalization status at month 3 window.
- If `mortality=yes`, `death_date` and `cause_of_death` are mandatory.
- Each patient timeline must have ordered visit events:
  - baseline
  - day7_reassessment (optional by protocol applicability)
  - discharge
  - week2_followup
  - month1_followup
  - month3_followup

---

## Source of Truth

- Event stream (`apps/api/data/patient_events.jsonl`) is system-of-record for platform state.
- CSV/markdown artifacts are secondary outputs and must not override event truth.
- Projection service is responsible for:
  - latest patient state
  - denominator counts
  - completeness and overdue flags

---

## Conflict Resolution

When denominator mismatch is detected:
1. Generate conflict report by Study ID.
2. Resolve against event timeline + consent evidence.
3. Mark correction event in audit trail.
4. Refresh projections and re-run exports.

---

## Operational Controls

- Run PHI scan before monthly analytics freeze:
  - `pnpm run scan:phi --fail-on-findings`
- If scan fails:
  - `pnpm run redact:phi`
  - `pnpm run scan:phi --fail-on-findings`
- Block release of snapshot/export if PHI findings are unresolved.
- Maintain schema version in every exported dataset manifest.
