import { KpiCard } from "@/components/dashboard/KpiCard";
import { HorizontalBar } from "@/components/dashboard/Charts";
import { PageHeader } from "@/components/ui/PageHeader";
import { fetchAnalyticsSummary } from "@/lib/api";

function getCompletenessTone(score: number): "success" | "warning" | "danger" {
  if (score >= 90) {
    return "success";
  }
  if (score >= 75) {
    return "warning";
  }
  return "danger";
}

export default async function DashboardPage() {
  const summary = await fetchAnalyticsSummary();
  const enrollmentPct =
    summary.cohort_target > 0 ? Math.round((summary.total_patients / summary.cohort_target) * 100) : 0;
  const endpointTone = summary.endpoint_completion_rate >= 80 ? "success" : "warning";
  const followupTone = summary.followups_overdue > 0 ? "danger" : "success";

  return (
    <section className="page">
      <PageHeader
        title="Live Analytics Dashboard"
        description="Daily control room for cohort progress, follow-up risk, and endpoint readiness."
      />

      <div className="kpi-grid">
        <KpiCard
          label="Enrolled Patients"
          value={summary.total_patients}
          helper={`${enrollmentPct}% of target ${summary.cohort_target}`}
          tone="info"
        />
        <KpiCard label="Active Patients" value={summary.active_patients} />
        <KpiCard label="Completed Patients" value={summary.completed_patients} tone="success" />
        <KpiCard label="Terminal Outcomes" value={summary.terminal_outcomes} tone="warning" />
        <KpiCard label="SVT Patients" value={summary.svt_patients} helper={`Non-SVT: ${summary.non_svt_patients}`} />
        <KpiCard label="Follow-ups Overdue" value={summary.followups_overdue} tone={followupTone} />
        <KpiCard
          label="Data Completeness"
          value={`${summary.average_completeness}%`}
          tone={getCompletenessTone(summary.average_completeness)}
        />
        <KpiCard
          label="Endpoint Completion"
          value={`${summary.endpoint_completion_rate}%`}
          tone={endpointTone}
          helper={`${summary.endpoint_completed} patients complete`}
        />
        <KpiCard label="Total Submissions" value={summary.total_submissions} />
      </div>

      <div className="panel-grid">
        <article className="panel">
          <div className="panel__header">
            <h2>Enrollment and Endpoint Runway</h2>
            <p>Progress against target and 3-month primary endpoint completion.</p>
          </div>
          <div className="panel__body panel__body--compact">
            <HorizontalBar
              label="Enrollment Progress"
              value={summary.total_patients}
              max={summary.cohort_target}
              color="var(--color-primary-500)"
            />
            <HorizontalBar
              label="Endpoint Completion"
              value={summary.endpoint_completed}
              max={summary.cohort_target}
              color="var(--color-success-600)"
            />
            <HorizontalBar
              label="Completed Cohort"
              value={summary.completed_patients}
              max={summary.cohort_target}
              color="var(--color-primary-700)"
            />
          </div>
        </article>

        <article className="panel">
          <div className="panel__header">
            <h2>Risk Signals</h2>
            <p>Operational burden from follow-ups and data quality drift.</p>
          </div>
          <div className="panel__body panel__body--compact">
            <HorizontalBar
              label="Overdue Follow-ups"
              value={summary.followups_overdue}
              max={Math.max(summary.total_patients, 1)}
              color="var(--color-danger-600)"
            />
            <HorizontalBar
              label="Due Soon Follow-ups"
              value={summary.followups_due_soon}
              max={Math.max(summary.total_patients, 1)}
              color="var(--color-warning-600)"
            />
            <HorizontalBar
              label="SVT Subgroup"
              value={summary.svt_patients}
              max={Math.max(summary.total_patients, 1)}
              color="var(--color-primary-600)"
            />
          </div>
        </article>
      </div>
    </section>
  );
}
