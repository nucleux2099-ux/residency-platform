export type SvtStatus = "with_svt" | "without_svt";
export type VisitType =
  | "baseline"
  | "day7_reassessment"
  | "discharge"
  | "week2_followup"
  | "month1_followup"
  | "month3_followup";
export type CohortStatus = "screened" | "enrolled" | "active" | "completed" | "terminal_outcome";
export type RecanalizationStatus = "pending" | "complete" | "partial" | "none" | "progressed" | "not_applicable";
export type VesselInvolvement = "pv" | "smv" | "sv" | "multiple" | "unknown";

export interface PatientSubmission {
  template_id?: string;
  patient_id: string;
  encounter_date: string;
  diagnosis: string;
  visit_type: VisitType;
  svt_status: SvtStatus;
  ward: string;
  cohort_status: CohortStatus;
  vessel_involvement?: VesselInvolvement[];
  mortality?: "yes" | "no";
  death_date?: string;
  cause_of_death?: string;
  recanalization_status?: RecanalizationStatus;
  primary_endpoint_complete?: boolean;
  notes?: string;
  source_files?: string[];
}
