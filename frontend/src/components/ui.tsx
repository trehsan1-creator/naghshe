import clsx from "clsx";
import type { ReactNode } from "react";
import { X } from "lucide-react";
import type { PointStatus } from "../lib/types";
import { STATUS_FA, num, int } from "../lib/i18n";

export const fmt = num;
export const fmtInt = int;

export function Panel({
  title,
  right,
  children,
  className,
  bodyClassName,
  icon,
}: {
  title?: ReactNode;
  right?: ReactNode;
  children: ReactNode;
  className?: string;
  bodyClassName?: string;
  icon?: ReactNode;
}) {
  return (
    <section className={clsx("panel flex flex-col min-h-0 overflow-hidden", className)}>
      {title !== undefined && (
        <header className="panel-title">
          {icon}
          <span className="truncate">{title}</span>
          <div className="ms-auto flex items-center gap-1 normal-case tracking-normal">{right}</div>
        </header>
      )}
      <div className={clsx("flex-1 min-h-0 overflow-auto", bodyClassName)}>{children}</div>
    </section>
  );
}

const statusStyles: Record<string, string> = {
  RAW: "border-muted/40 text-muted bg-muted/5",
  VALIDATED: "border-cyan/50 text-cyan bg-cyan/10",
  APPROVED: "border-lime/50 text-lime bg-lime/10",
  REJECTED: "border-danger/50 text-danger bg-danger/10",
  CURRENT: "border-lime/50 text-lime bg-lime/10",
  OUTDATED: "border-amber/50 text-amber bg-amber/10",
  committed: "border-lime/40 text-lime bg-lime/10",
  analysed: "border-cyan/40 text-cyan bg-cyan/10",
  uploaded: "border-muted/40 text-muted bg-muted/5",
};

export function StatusBadge({ status, className }: { status: string; className?: string }) {
  const label = STATUS_FA[status] ?? status;
  return (
    <span
      title={status}
      className={clsx(
        "inline-flex items-center h-[18px] px-1.5 rounded border text-[10px] font-medium whitespace-nowrap",
        statusStyles[status] ?? "border-edge text-muted",
        className,
      )}
    >
      {label}
    </span>
  );
}

export function StatusDot({ status }: { status: PointStatus | string }) {
  const color =
    status === "APPROVED"
      ? "#A3E635"
      : status === "VALIDATED"
        ? "#38BDF8"
        : status === "REJECTED"
          ? "#F87171"
          : "#8A94A6";
  return <span className="inline-block w-1.5 h-1.5 rounded-full" style={{ background: color }} />;
}

export function SeverityDot({ severity }: { severity?: string | null }) {
  if (!severity || severity === "ok") return <span className="text-muted/40">·</span>;
  const color = severity === "error" ? "#F87171" : severity === "warning" ? "#FBBF24" : "#8A94A6";
  return (
    <span
      className="inline-block w-1.5 h-1.5 rounded-full"
      style={{ background: color, boxShadow: `0 0 6px ${color}66` }}
      title={severity}
    />
  );
}

export function Stat({
  label,
  value,
  unit,
  tone = "ink",
}: {
  label: string;
  value: ReactNode;
  unit?: string;
  tone?: "ink" | "cyan" | "pink" | "lime" | "amber" | "danger";
}) {
  const toneClass = {
    ink: "text-ink",
    cyan: "text-cyan",
    pink: "text-pink",
    lime: "text-lime",
    amber: "text-amber",
    danger: "text-danger",
  }[tone];
  return (
    <div className="px-3 py-2 border-e border-edge/70 last:border-e-0 min-w-0">
      <div className="text-[9px] uppercase tracking-[0.12em] text-muted truncate">{label}</div>
      <div className={clsx("text-sm font-mono tabular truncate", toneClass)}>
        {value}
        {unit && <span className="text-[10px] text-muted ms-0.5">{unit}</span>}
      </div>
    </div>
  );
}

export function Spinner({ className }: { className?: string }) {
  return (
    <span
      className={clsx(
        "inline-block w-3 h-3 rounded-full border-2 border-cyan/30 border-t-cyan animate-spin",
        className,
      )}
    />
  );
}

export function Empty({ title, hint, action }: { title: string; hint?: string; action?: ReactNode }) {
  return (
    <div className="h-full flex flex-col items-center justify-center gap-2 p-6 text-center">
      <div className="text-xs text-muted tracking-[0.06em]">{title}</div>
      {hint && <div className="text-[11px] text-muted/70 max-w-sm leading-relaxed">{hint}</div>}
      {action}
    </div>
  );
}

export function Modal({
  title,
  onClose,
  children,
  width = "max-w-lg",
}: {
  title: string;
  onClose: () => void;
  children: ReactNode;
  width?: string;
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-6">
      <div className={clsx("panel w-full shadow-2xl", width)}>
        <header className="panel-title">
          {title}
          <button className="ms-auto btn-ghost !h-6 !px-1.5" onClick={onClose} aria-label="بستن">
            <X size={13} />
          </button>
        </header>
        <div className="p-4">{children}</div>
      </div>
    </div>
  );
}

export function KeyValue({ rows }: { rows: [string, ReactNode][] }) {
  return (
    <dl className="divide-y divide-edge/60 text-xs">
      {rows.map(([key, value]) => (
        <div key={key} className="flex items-baseline gap-3 px-3 py-1.5">
          <dt className="w-28 shrink-0 text-[10px] tracking-[0.06em] text-muted">{key}</dt>
          <dd className="font-mono tabular text-ink/90 break-all">{value}</dd>
        </div>
      ))}
    </dl>
  );
}
