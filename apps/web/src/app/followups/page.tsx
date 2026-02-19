import { fetchAnalyticsFollowups } from "@/lib/api";
import { HorizontalBar } from "@/components/dashboard/Charts";
import { PriorityBadge, StatusBadge } from "@/components/dashboard/Badges";
import { PageHeader } from "@/components/ui/PageHeader";

function getStatusTone(status: string): "neutral" | "info" | "success" | "warning" | "danger" {
  if (status === "overdue") {
    return "danger";
  }
  if (status === "due_soon") {
    return "warning";
  }
  if (status === "scheduled") {
    return "info";
  }
  if (status === "complete") {
    return "success";
  }
  return "neutral";
}

function getFollowupPriority(status: string): "none" | "low" | "medium" | "high" | "critical" {
  if (status === "overdue") {
    return "critical";
  }
  if (status === "due_soon" || status === "insufficient_data") {
    return "high";
  }
  if (status === "scheduled") {
    return "medium";
  }
  if (status === "complete") {
    return "low";
  }
  return "none";
}

export default async function FollowupsPage() {
  const followups = await fetchAnalyticsFollowups();
  const statusCounts = followups.items.reduce<Record<string, number>>((acc, item) => {
    acc[item.status] = (acc[item.status] || 0) + 1;
    return acc;
  }, {});
  const chartMax = Math.max(followups.items.length, 1);

  return (
    <section className="page">
      <PageHeader
        title="Follow-up Monitor"
        description="Tracks due and overdue follow-ups based on protocol windows."
      />

      <div className="kpi-strip">
        <div className="kpi-pill">
          <span className="kpi-pill__label">Overdue</span>
          <span className="kpi-pill__value">{followups.overdue_count}</span>
        </div>
        <div className="kpi-pill">
          <span className="kpi-pill__label">Due Soon</span>
          <span className="kpi-pill__value">{followups.due_soon_count}</span>
        </div>
        <div className="kpi-pill">
          <span className="kpi-pill__label">Rows</span>
          <span className="kpi-pill__value">{followups.items.length}</span>
        </div>
      </div>

      <article className="panel">
        <div className="panel__header">
          <h2>Status Distribution</h2>
          <p>Counts by follow-up urgency class.</p>
        </div>
        <div className="panel__body panel__body--compact">
          <HorizontalBar
            label="Overdue Follow-ups"
            value={statusCounts.overdue || 0}
            max={chartMax}
            color="var(--color-danger-600)"
          />
          <HorizontalBar
            label="Due Soon Follow-ups"
            value={statusCounts.due_soon || 0}
            max={chartMax}
            color="var(--color-warning-600)"
          />
          <HorizontalBar
            label="Scheduled Follow-ups"
            value={statusCounts.scheduled || 0}
            max={chartMax}
            color="var(--color-primary-500)"
          />
          <HorizontalBar
            label="Complete Follow-ups"
            value={statusCounts.complete || 0}
            max={chartMax}
            color="var(--color-success-600)"
          />
        </div>
      </article>

      <div className="table-wrap" style={{ maxHeight: "72vh" }}>
        <table className="data-table">
          <thead>
            <tr>
              <th>Patient</th>
              <th>Group</th>
              <th>Next Visit</th>
              <th>Due Date</th>
              <th>Status</th>
              <th>Priority</th>
              <th>Days Until Due</th>
              <th>Days Overdue</th>
            </tr>
          </thead>
          <tbody>
            {followups.items.map((item) => (
              <tr key={item.patient_id}>
                <td>{item.patient_id}</td>
                <td>{item.svt_status === "with_svt" ? "SVT" : "Non-SVT"}</td>
                <td>{item.next_visit || "-"}</td>
                <td>{item.due_date || "-"}</td>
                <td>
                  <StatusBadge label={item.status} tone={getStatusTone(item.status)} />
                </td>
                <td>
                  <PriorityBadge level={getFollowupPriority(item.status)} />
                </td>
                <td>{item.days_until_due ?? "-"}</td>
                <td>{item.days_overdue > 0 ? item.days_overdue : "-"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
