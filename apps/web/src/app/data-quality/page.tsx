import { fetchAnalyticsDataQuality } from "@/lib/api";
import { HorizontalBar, PercentageBar } from "@/components/dashboard/Charts";
import { PriorityBadge } from "@/components/dashboard/Badges";
import { PageHeader } from "@/components/ui/PageHeader";

function getQualityPriority(issueCount: number, completeness: number): "none" | "low" | "medium" | "high" | "critical" {
  if (issueCount >= 3 || completeness < 60) {
    return "critical";
  }
  if (issueCount >= 2 || completeness < 75) {
    return "high";
  }
  if (issueCount >= 1 || completeness < 90) {
    return "medium";
  }
  if (issueCount === 0) {
    return "low";
  }
  return "none";
}

export default async function DataQualityPage() {
  const dataQuality = await fetchAnalyticsDataQuality();
  const issueEntries = Object.entries(dataQuality.issues_by_type);
  const issueMax = Math.max(dataQuality.items.length, 1);

  return (
    <section className="page">
      <PageHeader
        title="Data Quality"
        description="Completeness and integrity checks for thesis event data."
      />

      <div className="kpi-strip">
        <div className="kpi-pill">
          <span className="kpi-pill__label">Average Completeness</span>
          <span className="kpi-pill__value">{dataQuality.average_completeness}%</span>
        </div>
        <div className="kpi-pill">
          <span className="kpi-pill__label">Patients with Issues</span>
          <span className="kpi-pill__value">{dataQuality.patients_with_issues}</span>
        </div>
      </div>

      <article className="panel">
        <div className="panel__header">
          <h2>Issue Types</h2>
          <p>Most frequent integrity signals in current submission set.</p>
        </div>
        <div className="panel__body panel__body--compact">
          {issueEntries.length === 0 ? (
            <p className="text-muted">No integrity issues detected.</p>
          ) : (
            <div className="panel__body--compact">
              {issueEntries
                .sort((a, b) => b[1] - a[1])
                .map(([key, value]) => (
                  <HorizontalBar
                    key={key}
                    label={key}
                    value={value}
                    max={issueMax}
                    color="var(--color-warning-600)"
                  />
                ))}
            </div>
          )}
        </div>
      </article>

      <div className="table-wrap" style={{ maxHeight: "60vh" }}>
        <table className="data-table">
          <thead>
            <tr>
              <th>Patient</th>
              <th>Template</th>
              <th>Completeness</th>
              <th>Issue Count</th>
              <th>Priority</th>
              <th>Issues</th>
              <th>Missing Visits</th>
            </tr>
          </thead>
          <tbody>
            {dataQuality.items.map((item) => (
              <tr key={item.patient_id}>
                <td>{item.patient_id}</td>
                <td>{item.template_id}</td>
                <td>
                  <PercentageBar value={item.completeness_pct} />
                </td>
                <td>{item.issue_count}</td>
                <td>
                  <PriorityBadge level={getQualityPriority(item.issue_count, item.completeness_pct)} />
                </td>
                <td>{item.issues.length ? item.issues.join(", ") : "-"}</td>
                <td>{item.missing_required_visits.length ? item.missing_required_visits.join(", ") : "-"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
