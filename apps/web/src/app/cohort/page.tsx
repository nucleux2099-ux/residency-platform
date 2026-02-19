import { fetchAnalyticsCohort } from "@/lib/api";
import { PriorityBadge, StatusBadge } from "@/components/dashboard/Badges";
import { HorizontalBar, PercentageBar } from "@/components/dashboard/Charts";
import { PageHeader } from "@/components/ui/PageHeader";

function getCohortTone(status: string): "neutral" | "info" | "success" | "warning" | "danger" {
  if (status === "completed") {
    return "success";
  }
  if (status === "active" || status === "enrolled") {
    return "info";
  }
  if (status === "terminal_outcome") {
    return "danger";
  }
  return "neutral";
}

function getPatientPriority(
  status: string,
  missingVisits: string[],
  endpointComplete: boolean
): "none" | "low" | "medium" | "high" | "critical" {
  if (status === "terminal_outcome") {
    return "critical";
  }
  if (missingVisits.length >= 2) {
    return "high";
  }
  if (missingVisits.length === 1) {
    return "medium";
  }
  if (!endpointComplete && status === "active") {
    return "low";
  }
  return "none";
}

export default async function CohortPage() {
  const cohort = await fetchAnalyticsCohort();
  const svtCount = cohort.patients.filter((item) => item.svt_status === "with_svt").length;
  const nonSvtCount = cohort.patients.length - svtCount;

  return (
    <section className="page">
      <PageHeader
        title="Cohort Operations"
        description="Canonical denominator and patient timeline status from event projections."
      />

      <div className="kpi-strip">
        <div className="kpi-pill">
          <span className="kpi-pill__label">Target</span>
          <span className="kpi-pill__value">{cohort.target}</span>
        </div>
        <div className="kpi-pill">
          <span className="kpi-pill__label">Enrolled</span>
          <span className="kpi-pill__value">{cohort.enrolled}</span>
        </div>
        <div className="kpi-pill">
          <span className="kpi-pill__label">Active</span>
          <span className="kpi-pill__value">{cohort.active}</span>
        </div>
        <div className="kpi-pill">
          <span className="kpi-pill__label">Completed</span>
          <span className="kpi-pill__value">{cohort.completed}</span>
        </div>
        <div className="kpi-pill">
          <span className="kpi-pill__label">Terminal Outcomes</span>
          <span className="kpi-pill__value">{cohort.terminal_outcomes}</span>
        </div>
      </div>

      <article className="panel">
        <div className="panel__header">
          <h2>Runway Snapshot</h2>
          <p>Enrollment, completion, and subgroup distribution.</p>
        </div>
        <div className="panel__body panel__body--compact">
          <HorizontalBar
            label="Enrollment Progress"
            value={cohort.enrolled}
            max={cohort.target}
            color="var(--color-primary-600)"
          />
          <HorizontalBar
            label="Completed Follow-up"
            value={cohort.completed}
            max={cohort.target}
            color="var(--color-success-600)"
          />
          <HorizontalBar
            label="SVT Mix"
            value={svtCount}
            max={Math.max(cohort.patients.length, 1)}
            color="var(--color-primary-700)"
          />
          <HorizontalBar
            label="Non-SVT Mix"
            value={nonSvtCount}
            max={Math.max(cohort.patients.length, 1)}
            color="var(--color-slate-500)"
          />
        </div>
      </article>

      <div className="table-wrap" style={{ maxHeight: "72vh" }}>
        <table className="data-table">
          <thead>
            <tr>
              <th>Patient</th>
              <th>Group</th>
              <th>Status</th>
              <th>Latest Visit</th>
              <th>Last Date</th>
              <th>Completeness</th>
              <th>Endpoint</th>
              <th>Missing Visits</th>
              <th>Priority</th>
            </tr>
          </thead>
          <tbody>
            {cohort.patients.map((patient) => (
              <tr key={patient.patient_id}>
                <td>{patient.patient_id}</td>
                <td>{patient.svt_status === "with_svt" ? "SVT" : "Non-SVT"}</td>
                <td>
                  <StatusBadge label={patient.cohort_status} tone={getCohortTone(patient.cohort_status)} />
                </td>
                <td>{patient.latest_visit}</td>
                <td>{patient.last_encounter_date || "-"}</td>
                <td>
                  <PercentageBar value={patient.completeness_pct} />
                </td>
                <td>
                  <StatusBadge label={patient.primary_endpoint_complete ? "complete" : "pending"} />
                </td>
                <td>{patient.missing_required_visits.length ? patient.missing_required_visits.join(", ") : "-"}</td>
                <td>
                  <PriorityBadge
                    level={getPatientPriority(
                      patient.cohort_status,
                      patient.missing_required_visits,
                      patient.primary_endpoint_complete
                    )}
                  />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
