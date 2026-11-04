import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { AlertTriangle, ArrowUpDown, Gauge, Save, ShieldCheck } from "lucide-react";
import { api } from "../lib/api";
import { useWorkspace } from "../store/workspace";
import { KeyValue, Panel, SeverityDot, Spinner, StatusBadge, fmt, fmtInt } from "../components/ui";
import type { QaReport } from "../lib/types";

export default function QaPage() {
  const navigate = useNavigate();
  const project = useWorkspace((s) => s.project);
  const points = useWorkspace((s) => s.points);
  const runQa = useWorkspace((s) => s.runQa);
  const busy = useWorkspace((s) => s.busy);
  const selectPoint = useWorkspace((s) => s.selectPoint);
  const toast = useWorkspace((s) => s.toast);
  const [report, setReport] = useState<(QaReport & { points_checked?: number; tolerances?: Record<string, number> }) | null>(null);
  const [tolerances, setتلورانس‌ها] = useState({
    duplicate_xy_tolerance: project?.duplicate_xy_tolerance ?? 0.005,
    duplicate_z_tolerance: project?.duplicate_z_tolerance ?? 0.02,
    z_mad_threshold: project?.z_mad_threshold ?? 3.5,
    local_z_step_threshold: project?.local_z_step_threshold ?? 1.5,
  });

  useEffect(() => {
    if (!project) return;
    api
      .runQa(project.id)
      .then((data) => setReport(data))
      .catch(() => undefined);
  }, [project?.id]);

  useEffect(() => {
    if (!project) return;
    setتلورانس‌ها({
      duplicate_xy_tolerance: project.duplicate_xy_tolerance,
      duplicate_z_tolerance: project.duplicate_z_tolerance,
      z_mad_threshold: project.z_mad_threshold,
      local_z_step_threshold: project.local_z_step_threshold,
    });
  }, [project?.id, project?.duplicate_xy_tolerance, project?.duplicate_z_tolerance, project?.z_mad_threshold, project?.local_z_step_threshold]);

  if (!project) return null;

  const flags = report?.flags ?? [];
  const byCode = flags.reduce<Record<string, number>>((acc, flag) => {
    acc[flag.code] = (acc[flag.code] ?? 0) + 1;
    return acc;
  }, {});
  const summary = report?.summary;

  const saveتلورانس‌ها = async () => {
    try {
      await api.updateProject(project.id, tolerances);
      const refreshed = await api.getProject(project.id);
      useWorkspace.setState({ project: refreshed });
      toast("success", "تلورانس‌ها saved — re-run QA/QC to apply");
    } catch (error) {
      toast("error", `Could not save tolerances: ${(error as Error).message}`);
    }
  };

  const jumpTo = (pointNumber: string) => {
    const point = points.find((p) => p.point_number === pointNumber);
    if (point) selectPoint(point);
    navigate(`/projects/${project.id}`);
  };

  return (
    <div className="h-full overflow-auto">
      <div className="max-w-[1500px] mx-auto p-4 space-y-3">
        <div className="flex items-end gap-3">
          <div>
            <div className="text-[10px] uppercase tracking-[0.2em] text-cyan/80">تضمین کیفیت</div>
            <h1 className="text-lg font-semibold tracking-tight mt-0.5">گزارش کنترل کیفیت</h1>
            <p className="text-[11px] text-muted mt-1">
              Axis reversal, coordinate duplicates, elevation outliers (robust MAD), local Z steps and unknown
              field codes — computed on the persisted point database.
            </p>
          </div>
          <button className="btn-primary ms-auto" onClick={() => void runQa()} disabled={Boolean(busy)}>
            {busy ? <Spinner /> : <ShieldCheck size={13} />} Re-run QA/QC
          </button>
        </div>

        <div className="grid grid-cols-2 lg:grid-cols-5 gap-2">
          {[
            { label: "نقاط بررسی‌شده", value: fmtInt(report?.points_checked ?? points.length), tone: "text-ink" },
            { label: "خطاها", value: fmtInt(summary?.flag_counts?.error ?? 0), tone: "text-danger" },
            { label: "هشدارها", value: fmtInt(summary?.flag_counts?.warning ?? 0), tone: "text-amber" },
            { label: "اطلاعات", value: fmtInt(summary?.flag_counts?.info ?? 0), tone: "text-muted" },
            { label: "نقاط علامت‌گذاری‌شده", value: fmtInt(summary?.flagged_points ?? 0), tone: "text-pink" },
          ].map((card) => (
            <div key={card.label} className="panel px-3 py-2">
              <div className="text-[9px] uppercase tracking-[0.14em] text-muted">{card.label}</div>
              <div className={`text-lg font-mono tabular ${card.tone}`}>{card.value}</div>
            </div>
          ))}
        </div>

        <div className="grid grid-cols-1 xl:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)] gap-3">
          <Panel
            title="یافته‌ها"
            icon={<AlertTriangle size={12} />}
            right={<span className="text-[9px] font-mono text-muted">{flags.length} findings</span>}
          >
            <ul className="divide-y divide-edge/50">
              {flags.map((flag, index) => (
                <li key={`${flag.code}-${index}`} className="px-2.5 py-2">
                  <div className="flex items-center gap-2">
                    <SeverityDot severity={flag.severity} />
                    <span className="text-[10px] font-mono uppercase tracking-wide text-ink/90">{flag.code}</span>
                    <span className={`text-[9px] font-mono sev-${flag.severity}`}>{flag.severity}</span>
                    {flag.metric !== null && flag.metric !== undefined && (
                      <span className="text-[9px] font-mono text-muted">metric {fmt(flag.metric, 4)}</span>
                    )}
                    <span className="ms-auto text-[9px] font-mono text-muted">
                      {flag.point_numbers.length} pt{flag.point_numbers.length === 1 ? "" : "s"}
                    </span>
                  </div>
                  <div className="text-[10px] text-muted leading-relaxed mt-1">{flag.message}</div>
                  {flag.suggestion && <div className="text-[10px] text-cyan/80 mt-0.5">→ {flag.suggestion}</div>}
                  {flag.point_numbers.length > 0 && (
                    <div className="flex flex-wrap gap-1 mt-1">
                      {flag.point_numbers.slice(0, 30).map((pointNumber) => (
                        <button
                          key={pointNumber}
                          className="chip hover:text-cyan hover:border-cyan/40"
                          onClick={() => jumpTo(pointNumber)}
                        >
                          {pointNumber}
                        </button>
                      ))}
                      {flag.point_numbers.length > 30 && (
                        <span className="chip">+{flag.point_numbers.length - 30}</span>
                      )}
                    </div>
                  )}
                </li>
              ))}
              {flags.length === 0 && (
                <li className="px-3 py-6 text-center text-[11px] text-lime">موردی یافت نشد — مجموعه‌داده از کنترل کیفیت سربلند بیرون آمد.</li>
              )}
            </ul>
          </Panel>

          <div className="space-y-3">
            <Panel title="آمار مجموعه‌داده" icon={<Gauge size={12} />}>
              <KeyValue
                rows={[
                  ["نقاط", fmtInt(summary?.points ?? points.length)],
                  ["دارای ارتفاع", fmtInt(summary?.with_elevation ?? 0)],
                  ["کدهای یکتا", fmtInt(summary?.unique_codes ?? 0)],
                  ["محدودهٔ شرقی", (summary?.extent_easting ?? []).map((v) => fmt(v, 2)).join(" → ") || "—"],
                  ["محدودهٔ شمالی", (summary?.extent_northing ?? []).map((v) => fmt(v, 2)).join(" → ") || "—"],
                  ["مساحت محدوده", `${fmt(summary?.convex_hull_area_m2 ?? null, 1)} m²`],
                  ["تراکم نقاط", `${fmt(summary?.point_density_per_ha ?? null, 0)} pts/ha`],
                ]}
              />
            </Panel>

            <Panel title="تشخیص جابه‌جایی محورها" icon={<ArrowUpDown size={12} />}>
              <div className="p-2.5">
                <div className="flex items-center gap-2">
                  <span
                    className={`chip ${summary?.axis_swap?.swap_suspected ? "!text-amber !border-amber/40" : "!text-lime !border-lime/40"}`}
                  >
                    {summary?.axis_swap?.swap_suspected ? "SWAP SUSPECTED" : "AXES OK"}
                  </span>
                  <span className="text-[9px] font-mono text-muted">
                    confidence {fmt((summary?.axis_swap?.confidence ?? 0) * 100, 0)}%
                  </span>
                </div>
                <p className="text-[10px] text-muted leading-relaxed mt-1.5">{summary?.axis_swap?.reason}</p>
              </div>
            </Panel>

            <Panel
              title="تلورانس‌ها"
              icon={<Gauge size={12} />}
              right={<StatusBadge status={project.dependency_state} />}
            >
              <div className="p-2.5 space-y-2">
                {[
                  ["duplicate_xy_tolerance", "Duplicate XY (m)", 0.001, 1, 0.001],
                  ["duplicate_z_tolerance", "Duplicate Z (m)", 0.001, 1, 0.001],
                  ["z_mad_threshold", "Z MAD threshold", 1, 10, 0.1],
                  ["local_z_step_threshold", "Local Z step (m)", 0.1, 10, 0.1],
                ].map(([key, label, min, max, step]) => (
                  <div key={key as string} className="flex items-center gap-2">
                    <label className="text-[10px] text-muted flex-1">{label}</label>
                    <input
                      type="number"
                      className="field !w-24 !h-7 font-mono !text-[10px]"
                      min={min as number}
                      max={max as number}
                      step={step as number}
                      value={tolerances[key as keyof typeof tolerances]}
                      onChange={(event) =>
                        setتلورانس‌ها({ ...tolerances, [key as string]: Number(event.target.value) })
                      }
                    />
                  </div>
                ))}
                <button className="btn w-full !h-7" onClick={() => void saveتلورانس‌ها()}>
                  <Save size={11} /> Save tolerances
                </button>
              </div>
            </Panel>

            {Object.keys(byCode).length > 0 && (
              <Panel title="یافته‌ها by code" icon={<AlertTriangle size={12} />}>
                <ul className="divide-y divide-edge/50">
                  {Object.entries(byCode)
                    .sort((a, b) => b[1] - a[1])
                    .map(([code, count]) => (
                      <li key={code} className="px-2.5 py-1 flex items-center gap-2 text-[10px] font-mono">
                        <span className="text-ink/80">{code}</span>
                        <span className="ms-auto text-muted">{count}</span>
                      </li>
                    ))}
                </ul>
              </Panel>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
