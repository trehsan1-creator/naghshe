import { useEffect, useState } from "react";
import {
  CheckCheck,
  ClipboardCopy,
  Database,
  Info,
  LocateFixed,
  Save,
  SlidersHorizontal,
  XCircle,
} from "lucide-react";
import { api } from "../lib/api";
import { useWorkspace } from "../store/workspace";
import type { PointStatus } from "../lib/types";
import { Empty, KeyValue, Panel, StatusBadge, fmt, fmtInt } from "./ui";

export default function PropertiesPanel() {
  const selected = useWorkspace((s) => s.selectedPoint);
  return <div className="h-full flex flex-col gap-2 min-h-0">{selected ? <PointEditor /> : <ProjectFacts />}</div>;
}

function PointEditor() {
  const point = useWorkspace((s) => s.selectedPoint)!;
  const selectPoint = useWorkspace((s) => s.selectPoint);
  const refreshPoints = useWorkspace((s) => s.refreshPoints);
  const toast = useWorkspace((s) => s.toast);
  const projectId = useWorkspace((s) => s.project?.id);

  const [draft, setDraft] = useState({
    code: point.code,
    description: point.description,
    elevation: point.elevation === null ? "" : String(point.elevation),
    status: point.status as PointStatus,
  });

  useEffect(() => {
    setDraft({
      code: point.code,
      description: point.description,
      elevation: point.elevation === null ? "" : String(point.elevation),
      status: point.status as PointStatus,
    });
  }, [point.id, point.code, point.description, point.elevation, point.status]);

  const dirty =
    draft.code !== point.code ||
    draft.description !== point.description ||
    String(point.elevation ?? "") !== draft.elevation ||
    draft.status !== point.status;

  const save = async () => {
    if (!projectId) return;
    try {
      const payload: Record<string, unknown> = {
        code: draft.code,
        description: draft.description,
        status: draft.status,
      };
      if (draft.elevation !== "") payload.elevation = Number(draft.elevation);
      const updated = await api.patchPoint(projectId, point.id, payload);
      selectPoint({ ...point, ...updated });
      await refreshPoints();
      toast("success", `Point ${point.point_number} saved (v${updated.version})`);
    } catch (error) {
      toast("error", `Update failed: ${(error as Error).message}`);
    }
  };

  const copy = async () => {
    const text = `${point.point_number}\t${point.code}\t${point.easting.toFixed(3)}\t${point.northing.toFixed(3)}\t${
      point.elevation?.toFixed(3) ?? ""
    }`;
    await navigator.clipboard?.writeText(text);
    toast("info", "مختصات و مشخصات نقطه کپی شد");
  };

  const flags: string[] = point.qa_flags ? JSON.parse(point.qa_flags) : [];

  return (
    <>
      <Panel
        title={`Point ${point.point_number}`}
        icon={<LocateFixed size={12} />}
        right={
          <>
            <StatusBadge status={point.status} />
            <span className="chip">v{point.version}</span>
          </>
        }
      >
        <div className="p-2.5 space-y-2.5">
          <div className="grid grid-cols-2 gap-1.5">
            {[
              ["مختصات شرقی", fmt(point.easting)],
              ["مختصات شمالی", fmt(point.northing)],
              ["ارتفاع", fmt(point.elevation)],
              ["لایه", point.layer || "—"],
            ].map(([label, value]) => (
              <div key={label} className="bg-panel2/60 border border-edge/70 rounded px-2 py-1">
                <div className="text-[9px] uppercase tracking-[0.1em] text-muted">{label}</div>
                <div className="font-mono tabular text-[11px] text-ink">{value}</div>
              </div>
            ))}
          </div>

          <div>
            <label className="label">کد برداشت</label>
            <input
              className="field font-mono"
              value={draft.code}
              onChange={(event) => setDraft({ ...draft, code: event.target.value.toUpperCase() })}
            />
          </div>
          <div>
            <label className="label">شرح</label>
            <input
              className="field"
              value={draft.description}
              onChange={(event) => setDraft({ ...draft, description: event.target.value })}
            />
          </div>
          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="label">ارتفاع (متر)</label>
              <input
                className="field font-mono"
                value={draft.elevation}
                onChange={(event) => setDraft({ ...draft, elevation: event.target.value })}
                placeholder="—"
              />
            </div>
            <div>
              <label className="label">وضعیت</label>
              <select
                className="field"
                value={draft.status}
                onChange={(event) => setDraft({ ...draft, status: event.target.value as PointStatus })}
              >
                {["RAW", "VALIDATED", "APPROVED", "REJECTED"].map((status) => (
                  <option key={status} value={status}>
                    {status}
                  </option>
                ))}
              </select>
            </div>
          </div>

          {flags.length > 0 && (
            <div className="rounded border border-amber/30 bg-amber/5 px-2 py-1.5">
              <div className="text-[9px] uppercase tracking-[0.12em] text-amber/80 mb-1">پرچم‌های کنترل کیفیت</div>
              <div className="flex flex-wrap gap-1">
                {flags.map((flag) => (
                  <span key={flag} className="chip !text-[9px] text-amber border-amber/30">
                    {flag}
                  </span>
                ))}
              </div>
            </div>
          )}

          <div className="flex items-center gap-1.5">
            <button className="btn-primary flex-1" onClick={() => void save()} disabled={!dirty}>
              <Save size={12} /> Save
            </button>
            <button className="btn-ghost" onClick={() => void copy()} title="کپی به‌صورت TSV">
              <ClipboardCopy size={13} />
            </button>
          </div>
          <div className="flex gap-1.5">
            <button
              className="btn flex-1 !h-7 !text-[10px] hover:!text-lime"
              onClick={() => {
                setDraft({ ...draft, status: "APPROVED" });
              }}
            >
              <CheckCheck size={11} /> Approve
            </button>
            <button
              className="btn flex-1 !h-7 !text-[10px] hover:!text-danger"
              onClick={() => {
                setDraft({ ...draft, status: "REJECTED" });
              }}
            >
              <XCircle size={11} /> Reject
            </button>
          </div>
          <div className="text-[9px] text-muted font-mono leading-relaxed border-t border-edge/60 pt-2">
            source order #{point.source_order}
            {point.line_no !== null && point.line_no !== undefined ? ` · line ${point.line_no}` : ""}
            <br />
            id {point.id.slice(0, 12)}…
          </div>
        </div>
      </Panel>

      <Panel title="تبار داده" className="flex-1 min-h-0" icon={<Info size={12} />}>
        <div className="px-3 py-2 text-[10px] text-muted leading-relaxed space-y-1.5">
          <p>
            This point sits in the <span className="text-cyan">{point.status}</span> tier. Edits bump the
            version and mark every dependent surface, volume, profile and DXF export{" "}
            <span className="text-amber">منسوخ</span> تا زمان بازسازی.
          </p>
          <p>دادهٔ خام فایل ورودی هرگز بازنویسی نمی‌شود؛ اصلاحات فقط روی رکورد پردازش‌شده اعمال می‌شوند.</p>
        </div>
      </Panel>
    </>
  );
}

function ProjectFacts() {
  const project = useWorkspace((s) => s.project);
  const surface = useWorkspace((s) => s.surface);
  const qa = useWorkspace((s) => s.qa);
  const pointsTotal = useWorkspace((s) => s.pointsTotal);
  if (!project) return null;

  const counters = project.counters;

  return (
    <>
      <Panel title="پروژه" icon={<Database size={12} />}>
        <KeyValue
          rows={[
            ["نام", project.name],
            ["کد پروژه", project.code || "—"],
            ["کارفرما", project.client || "—"],
            ["موقعیت", project.location || "—"],
            ["CRS", `EPSG:${project.crs_epsg}`],
            ["مبنای ارتفاعی", project.crs?.name ?? project.vertical_datum],
            ["قائم", project.vertical_datum],
            ["واحدها", `${project.linear_unit} / ${project.angle_unit}`],
            ["نقاط", fmtInt(counters?.points_total ?? pointsTotal)],
          ]}
        />
      </Panel>

      <Panel title="تلورانس‌ها" icon={<SlidersHorizontal size={12} />}>
        <KeyInfo project={project} />
      </Panel>

      {surface && (
        <Panel title="آمار سطح" className="min-h-0" icon={<Database size={12} />}>
          <KeyValue
            rows={[
              ["موتور", String(surface.mesh.stats.engine ?? "triangle")],
              ["مثلث‌ها", fmtInt(Number(surface.mesh.stats.triangles ?? 0))],
              ["رأس‌ها", fmtInt(Number(surface.mesh.stats.vertices ?? 0))],
              ["مساحت", `${fmt(Number(surface.stats.area_m2 ?? 0), 2)} m²`],
              ["Z range", `${fmt(Number(surface.stats.min_z ?? 0), 3)} → ${fmt(Number(surface.stats.max_z ?? 0), 3)}`],
              ["قیود", fmtInt(Number(surface.mesh.stats.constraint_edges ?? 0))],
              ["منحنی‌های میزان", fmtInt(surface.contours.length)],
              ["مرز", String(surface.mesh.boundary_source ?? "—")],
            ]}
          />
        </Panel>
      )}

      {!surface && (
        <Panel title="QA/QC" className="flex-1 min-h-0" icon={<Info size={12} />}>
          {qa ? (
            <KeyValue
              rows={[
                ["پرچم‌ها", fmtInt(qa.flags.length)],
                ["خطاها", String(qa.summary.flag_counts?.error ?? 0)],
                ["هشدارها", String(qa.summary.flag_counts?.warning ?? 0)],
                ["نقاط علامت‌دار", String(qa.summary.flagged_points ?? 0)],
                ["جابه‌جایی محورها", qa.summary.axis_swap?.swap_suspected ? "محتمل" : "هیچ‌کدام"],
                ["محدودهٔ شرقی", (qa.summary.extent_easting ?? []).map((v) => fmt(v, 1)).join(" → ") || "—"],
              ]}
            />
          ) : (
            <Empty
              title="نقطه‌ای انتخاب نشده است"
              hint="Click a point on the canvas or in the table to inspect and edit it. Run QA/QC to populate validation flags."
            />
          )}
        </Panel>
      )}
    </>
  );
}

function KeyInfo({ project }: { project: NonNullable<ReturnType<typeof useWorkspace.getState>["project"]> }) {
  return (
    <KeyValue
      rows={[
        ["تکرار افقی", `${fmt(project.duplicate_xy_tolerance, 3)} m`],
        ["تکرار ارتفاعی", `${fmt(project.duplicate_z_tolerance, 3)} m`],
        ["Z MAD", `×${fmt(project.z_mad_threshold, 2)}`],
        ["Z step", `${fmt(project.local_z_step_threshold, 2)} m`],
        ["مرز", project.tin_boundary_mode],
        ["Contour int.", `${fmt(project.contour_interval, 2)} m`],
        ["خطوط شکست", (project.breakline_codes ?? []).join(", ") || "—"],
      ]}
    />
  );
}
