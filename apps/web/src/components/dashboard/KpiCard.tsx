import { LucideIcon } from "lucide-react";

interface KpiCardProps {
  label: string;
  value: string | number;
  icon?: LucideIcon;
  trend?: {
    value: number;
    label: string;
  };
  status?: "default" | "info" | "success" | "warning" | "danger";
  tone?: "default" | "info" | "success" | "warning" | "danger";
  helperText?: string;
  helper?: string;
}

export function KpiCard({ label, value, icon: Icon, status = "default", tone, helperText, helper }: KpiCardProps) {
  const resolvedStatus = tone || status;
  const resolvedHelper = helperText || helper;
  const statusStyles = {
    default: "border-slate-200",
    info: "border-primary-200 bg-primary-50/30",
    success: "border-green-200 bg-green-50/30",
    warning: "border-orange-200 bg-orange-50/30",
    danger: "border-red-200 bg-red-50/30",
  };

  return (
    <div className={`
      relative overflow-hidden rounded-xl border bg-white p-5 shadow-sm transition-all hover:shadow-md
      ${statusStyles[resolvedStatus]}
    `}>
      <div className="flex items-center justify-between mb-2">
        <span className="text-sm font-semibold text-slate-500 tracking-wide uppercase">{label}</span>
        {Icon && <Icon className="w-5 h-5 text-slate-400" />}
      </div>

      <div className="flex items-baseline gap-2">
        <span className="text-3xl font-bold text-slate-900 tracking-tight">{value}</span>
      </div>

      {resolvedHelper && (
        <p className="mt-2 text-xs text-slate-400 font-medium">
          {resolvedHelper}
        </p>
      )}
    </div>
  );
}
