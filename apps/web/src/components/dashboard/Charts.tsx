interface HorizontalBarProps {
  label: string;
  value: number;
  max: number;
  color?: string;
}

export function HorizontalBar({ label, value, max, color = "var(--accent)" }: HorizontalBarProps) {
  const safeMax = max <= 0 ? 1 : max;
  const pct = Math.max(0, Math.min(100, (value / safeMax) * 100));

  return (
    <div className="chart-row">
      <div className="chart-row__meta">
        <span>{label}</span>
        <strong>
          {value}/{max}
        </strong>
      </div>
      <div className="chart-track">
        <div
          className="chart-fill"
          style={{
            width: `${pct}%`,
            background: color
          }}
        />
      </div>
    </div>
  );
}

interface PercentageBarProps {
  value: number;
}

export function PercentageBar({ value }: PercentageBarProps) {
  const pct = Math.max(0, Math.min(100, value));
  const color = pct >= 90 ? "#027a48" : pct >= 70 ? "#b54708" : "#b42318";

  return (
    <div className="percentage-bar">
      <div className="percentage-bar__track">
        <div className="percentage-bar__fill" style={{ width: `${pct}%`, background: color }} />
      </div>
      <span className="percentage-bar__label">{pct}%</span>
    </div>
  );
}
