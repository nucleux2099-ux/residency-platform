interface StatusBadgeProps {
  label: string;
  tone?: "neutral" | "info" | "success" | "warning" | "danger";
}

export function StatusBadge({ label, tone = "neutral" }: StatusBadgeProps) {
  const normalizedLabel = label.replaceAll("_", " ");
  return (
    <span className={`status-badge status-badge--${tone}`}>{normalizedLabel}</span>
  );
}

interface PriorityBadgeProps {
  level: "none" | "low" | "medium" | "high" | "critical";
}

const LEVEL_TO_TONE: Record<PriorityBadgeProps["level"], StatusBadgeProps["tone"]> = {
  none: "neutral",
  low: "info",
  medium: "warning",
  high: "danger",
  critical: "danger"
};

export function PriorityBadge({ level }: PriorityBadgeProps) {
  const label = level === "none" ? "none" : `${level} priority`;
  return <StatusBadge label={label} tone={LEVEL_TO_TONE[level]} />;
}
