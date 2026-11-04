import { useMemo, useState } from "react";
import { Layers2, Mountain, Ruler, Scissors, Waves } from "lucide-react";
import { useWorkspace } from "../store/workspace";
import { Empty, Spinner, Stat, fmt, fmtInt } from "./ui";
import { CrossSectionChart, ProfileChart, VolumeBars } from "./charts";
import type { DerivedOutput } from "../lib/types";

function SurfaceSelect({
  label,
  value,
  onChange,
  surfaces,
  allowEmpty,
  placeholder = "— none —",
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  surfaces: DerivedOutput[];
  allowEmpty?: boolean;
  placeholder?: string;
}) {
  return (
    <div className="min-w-0">
      <label className="label">{label}</label>
      <select className="field font-mono !text-[10px]" value={value} onChange={(event) => onChange(event.target.value)}>
        {(allowEmpty || value === "") && <option value="">{placeholder}</option>}
        {surfaces.map((s) => (
          <option key={s.id} value={s.id}>
            {s.name} · {s.summary?.triangles ?? "?"} tri · {s.status}
          </option>
        ))}
      </select>
    </div>
  );
}

export function ProfileTab() {
  const surface = useWorkspace((s) => s.surface);
  const surfaces = useWorkspace((s) => s.surfaces);
  const profile = useWorkspace((s) => s.profile);
  const computeProfile = useWorkspace((s) => s.computeProfile);
  const busy = useWorkspace((s) => s.busy);
  const [interval, setInterval] = useState(5);
  const [designId, setDesignId] = useState("");

  const surfaceOptions = surfaces.filter((s) => s.kind === "surface");

  return (
    <div className="h-full flex flex-col min-h-0">
      <div className="h-9 shrink-0 flex items-center gap-2 px-2 border-b border-edge">
        <Ruler size={12} className="text-muted" />
        <span className="text-[10px] uppercase tracking-[0.14em] text-muted">نیمرخ طولی</span>
        <div className="ms-3 flex items-end gap-2">
          <div>
            <select
              className="field !h-6 !text-[10px]"
              value={interval}
              onChange={(event) => setInterval(Number(event.target.value))}
            >
              {[1, 2, 2.5, 5, 10, 20, 25].map((value) => (
                <option key={value} value={value}>
                  station {value} m
                </option>
              ))}
            </select>
          </div>
          <select
            className="field !h-6 !text-[10px] font-mono max-w-[220px]"
            value={designId}
            onChange={(event) => setDesignId(event.target.value)}
          >
            <option value="">بدون سطح طراحی</option>
            {surfaceOptions
              .filter((s) => s.id !== surface?.output?.id)
              .map((s) => (
                <option key={s.id} value={s.id}>
                  design: {s.name}
                </option>
              ))}
          </select>
          <button
            className="btn !h-6 !text-[10px]"
            disabled={!surface || Boolean(busy)}
            onClick={() =>
              surface &&
              void computeProfile({
                surface_id: surface.output?.id,
                design_surface_id: designId || undefined,
                station_interval: interval,
                offsets: [0, -1.5, 1.5],
                feature_name: "CL",
              })
            }
          >
            {busy ? <Spinner /> : <Ruler size={11} />} Sample
          </button>
        </div>
        <span className="ms-auto text-[9px] font-mono text-muted">
          centreline: surveyed CL linework (auto-resolved)
        </span>
      </div>
      <div className="flex-1 min-h-0 overflow-auto">
        {profile ? (
          <ProfileChart profile={profile} />
        ) : (
          <Empty
            title="هنوز نیمرخی محاسبه نشده است"
            hint={
              surface
                ? "Sample the surface along the surveyed centreline to get existing and design elevations per station."
                : "Build a TIN surface first — the profile is sampled from the triangulated mesh."
            }
          />
        )}
      </div>
    </div>
  );
}

export function VolumeTab() {
  const surface = useWorkspace((s) => s.surface);
  const surfaces = useWorkspace((s) => s.surfaces);
  const volume = useWorkspace((s) => s.volume);
  const computeVolumes = useWorkspace((s) => s.computeVolumes);
  const busy = useWorkspace((s) => s.busy);
  const [cellSize, setCellSize] = useState(0.5);
  const [existingId, setExistingId] = useState("");
  const [proposedId, setProposedId] = useState("");
  const [method, setMethod] = useState<"grid" | "average_end_area">("grid");

  const surfaceOptions = useMemo(() => surfaces.filter((s) => s.kind === "surface"), [surfaces]);
  const existing = existingId || surface?.output?.id || surfaceOptions[0]?.id || "";
  const proposed = proposedId || surfaceOptions.find((s) => s.id !== existing)?.id || "";

  const run = () => {
    if (!existing || !proposed) return;
    void computeVolumes({
      existing_surface_id: existing,
      proposed_surface_id: proposed,
      method,
      cell_size: cellSize,
    });
  };

  return (
    <div className="h-full flex flex-col min-h-0">
      <div className="h-9 shrink-0 flex items-center gap-2 px-2 border-b border-edge">
        <Scissors size={12} className="text-muted" />
        <span className="text-[10px] uppercase tracking-[0.14em] text-muted">خاک‌برداری و خاک‌ریزی</span>
        <select
          className="field !h-6 !text-[10px] font-mono max-w-[210px] ms-2"
          value={existing}
          onChange={(event) => setExistingId(event.target.value)}
        >
          {surfaceOptions.map((s) => (
            <option key={s.id} value={s.id}>
              existing: {s.name}
            </option>
          ))}
        </select>
        <select
          className="field !h-6 !text-[10px] font-mono max-w-[210px]"
          value={proposed}
          onChange={(event) => setProposedId(event.target.value)}
        >
          {surfaceOptions.map((s) => (
            <option key={s.id} value={s.id}>
              proposed: {s.name}
            </option>
          ))}
        </select>
        <select
          className="field !h-6 !w-24 !text-[10px]"
          value={method}
          onChange={(event) => setMethod(event.target.value as "grid" | "average_end_area")}
        >
          <option value="grid">شبکه</option>
          <option value="average_end_area">مساحت انتهایی</option>
        </select>
        <select
          className="field !h-6 !w-20 !text-[10px]"
          value={cellSize}
          onChange={(event) => setCellSize(Number(event.target.value))}
        >
          {[0.25, 0.5, 1, 2].map((value) => (
            <option key={value} value={value}>
              {value} m
            </option>
          ))}
        </select>
        <button className="btn !h-6 !text-[10px]" onClick={run} disabled={!existing || !proposed || Boolean(busy)}>
          {busy ? <Spinner /> : <Scissors size={11} />} Compute
        </button>
        <span className="ms-auto text-[9px] font-mono text-muted">
          grid prismoidal method · overlap-clipped
        </span>
      </div>

      <div className="flex-1 min-h-0 overflow-auto p-2">
        {volume ? (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-2">
            <div>
              <div className="grid grid-cols-3 border border-edge rounded overflow-hidden mb-2">
                <Stat label="خاک‌برداری" value={fmt(volume.cut_m3, 2)} unit="m³" tone="lime" />
                <Stat label="خاک‌ریزی" value={fmt(volume.fill_m3, 2)} unit="m³" tone="pink" />
                <Stat
                  label="خالص"
                  value={fmt(volume.net_m3, 2)}
                  unit="m³"
                  tone={volume.net_m3 >= 0 ? "cyan" : "amber"}
                />
              </div>
              <VolumeBars volume={volume} />
              <div className="grid grid-cols-2 gap-x-3 gap-y-1 mt-2 text-[10px] font-mono">
                {[
                  ["cell", `${fmt(volume.cell_size ?? cellSize, 2)} m`],
                  ["cut area", `${fmt(volume.cut_area_m2, 1)} m²`],
                  ["fill area", `${fmt(volume.fill_area_m2, 1)} m²`],
                  ["total area", `${fmt(volume.total_area_m2, 1)} m²`],
                  ["max cut", `${fmt(volume.max_cut_depth, 3)} m`],
                  ["max fill", `${fmt(volume.max_fill_depth, 3)} m`],
                  ["mean cut", `${fmt(volume.mean_cut_depth, 3)} m`],
                  ["overlap", `${fmt(volume.overlap_area_m2, 1)} m²`],
                ].map(([label, value]) => (
                  <div key={label} className="flex justify-between border-b border-edge/40 py-0.5">
                    <span className="text-muted">{label}</span>
                    <span className="text-ink/90 tabular">{value}</span>
                  </div>
                ))}
              </div>
            </div>
            <div>
              <div className="text-[9px] uppercase tracking-[0.14em] text-muted mb-1">توزیع عمق</div>
              <DepthHistogram volume={volume} />
              {volume.sections && volume.sections.length > 0 && (
                <div className="mt-2">
                  <div className="text-[9px] uppercase tracking-[0.14em] text-muted mb-1">
                    End-area sections ({volume.sections.length})
                  </div>
                  <table className="w-full text-[10px] font-mono">
                    <thead>
                      <tr className="text-muted text-[9px] uppercase">
                        <th className="text-start font-normal py-0.5">ایستگاه</th>
                        <th className="text-end font-normal">cut m²</th>
                        <th className="text-end font-normal">fill m²</th>
                      </tr>
                    </thead>
                    <tbody>
                      {volume.sections.map((section) => (
                        <tr key={section.station} className="border-t border-edge/40">
                          <td className="py-0.5">{fmt(section.station, 1)}</td>
                          <td className="text-end text-lime">{fmt(section.cut_area_m2, 3)}</td>
                          <td className="text-end text-pink">{fmt(section.fill_area_m2, 3)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </div>
        ) : (
          <Empty
            title="حجمی محاسبه نشده است"
            hint="Select the existing and proposed surfaces. Both TINs are intersected, then cut and fill are integrated on a prismoidal grid clipped to the overlap."
          />
        )}
      </div>
    </div>
  );
}

function DepthHistogram({ volume }: { volume: { max_cut_depth?: number; max_fill_depth?: number; cut_m3: number; fill_m3: number; cut_area_m2?: number; fill_area_m2?: number } }) {
  const bins = [
    {
      label: "cut",
      value: volume.cut_area_m2 ?? 0,
      color: "#A3E635",
      note: `max ${fmt(volume.max_cut_depth ?? 0, 3)} m`,
    },
    {
      label: "fill",
      value: volume.fill_area_m2 ?? 0,
      color: "#F472B6",
      note: `max ${fmt(volume.max_fill_depth ?? 0, 3)} m`,
    },
  ];
  const max = Math.max(...bins.map((b) => b.value), 1);
  return (
    <div className="flex items-end gap-6 h-32 border border-edge rounded p-2 bg-base/60">
      {bins.map((bin) => (
        <div key={bin.label} className="flex-1 flex flex-col items-center justify-end h-full gap-1">
          <span className="text-[10px] font-mono text-ink/80">{fmt(bin.value, 1)} m²</span>
          <div
            className="w-full rounded-sm"
            style={{ height: `${Math.max((bin.value / max) * 70, 2)}%`, background: `${bin.color}55`, border: `1px solid ${bin.color}` }}
          />
          <span className="text-[9px] font-mono uppercase tracking-wider" style={{ color: bin.color }}>
            {bin.label}
          </span>
          <span className="text-[8px] font-mono text-muted">{bin.note}</span>
        </div>
      ))}
    </div>
  );
}

export function CrossSectionTab() {
  const surface = useWorkspace((s) => s.surface);
  const surfaces = useWorkspace((s) => s.surfaces);
  const crossSections = useWorkspace((s) => s.crossSections);
  const computeCrossSections = useWorkspace((s) => s.computeCrossSections);
  const busy = useWorkspace((s) => s.busy);
  const [interval, setInterval] = useState(10);
  const [width, setWidth] = useState(6);
  const [designId, setDesignId] = useState("");

  const surfaceOptions = surfaces.filter((s) => s.kind === "surface");

  return (
    <div className="h-full flex flex-col min-h-0">
      <div className="h-9 shrink-0 flex items-center gap-2 px-2 border-b border-edge">
        <Waves size={12} className="text-muted" />
        <span className="text-[10px] uppercase tracking-[0.14em] text-muted">مقاطع عرضی</span>
        <select
          className="field !h-6 !w-24 !text-[10px] ms-2"
          value={interval}
          onChange={(event) => setInterval(Number(event.target.value))}
        >
          {[5, 10, 15, 20, 25].map((value) => (
            <option key={value} value={value}>
              every {value} m
            </option>
          ))}
        </select>
        <select className="field !h-6 !w-24 !text-[10px]" value={width} onChange={(event) => setWidth(Number(event.target.value))}>
          {[3, 4, 6, 8, 10, 15].map((value) => (
            <option key={value} value={value}>
              ±{value} m
            </option>
          ))}
        </select>
        <select
          className="field !h-6 !max-w-[200px] !text-[10px] font-mono"
          value={designId}
          onChange={(event) => setDesignId(event.target.value)}
        >
          <option value="">بدون سطح طراحی</option>
          {surfaceOptions
            .filter((s) => s.id !== surface?.output?.id)
            .map((s) => (
              <option key={s.id} value={s.id}>
                design: {s.name}
              </option>
            ))}
        </select>
        <button
          className="btn !h-6 !text-[10px]"
          disabled={!surface || Boolean(busy)}
          onClick={() =>
            surface &&
            void computeCrossSections({
              surface_id: surface.output?.id,
              design_surface_id: designId || undefined,
              station_interval: interval,
              left: width,
              right: width,
              samples: 61,
              feature_name: "CL",
            })
          }
        >
          {busy ? <Spinner /> : <Waves size={11} />} Extract
        </button>
        <span className="ms-auto text-[9px] font-mono text-muted">
          perpendicular to the surveyed centreline · 61 samples
        </span>
      </div>
      <div className="flex-1 min-h-0 overflow-auto p-2">
        {crossSections ? (
          <div className="grid grid-cols-1 xl:grid-cols-2 gap-2">
            {crossSections.sections.map((section) => (
              <CrossSectionChart key={section.station} section={section.existing} station={section.station} />
            ))}
            {crossSections.average_end_area && (
              <div className="panel p-2 text-[10px] font-mono col-span-full">
                <div className="text-[9px] uppercase tracking-[0.14em] text-muted mb-1">روش مساحت میانگین انتهایی</div>
                <div className="flex flex-wrap gap-4">
                  {[
                    ["cut", `${fmt(crossSections.average_end_area.cut_m3, 2)} m³`, "text-lime"],
                    ["fill", `${fmt(crossSections.average_end_area.fill_m3, 2)} m³`, "text-pink"],
                    ["net", `${fmt(crossSections.average_end_area.net_m3, 2)} m³`, "text-cyan"],
                    ["length", `${fmt(crossSections.average_end_area.length_m, 2)} m`, "text-ink"],
                  ].map(([label, value, tone]) => (
                    <span key={label} className="flex items-baseline gap-1.5">
                      <span className="text-muted uppercase text-[9px]">{label}</span>
                      <span className={tone}>{value}</span>
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>
        ) : (
          <Empty
            title="مقطعی استخراج نشده است"
            hint="Extract perpendicular sections through the TIN anywhere along the alignment; optional design surface shows the cut/fill prism."
          />
        )}
      </div>
    </div>
  );
}

export function SurfaceControls() {
  const project = useWorkspace((s) => s.project);
  const surface = useWorkspace((s) => s.surface);
  const buildSurface = useWorkspace((s) => s.buildSurface);
  const busy = useWorkspace((s) => s.busy);
  const pointCount = useWorkspace((s) => s.points.length);
  const [boundary, setBoundary] = useState(project?.tin_boundary_mode ?? "concave_hull");
  const [interval, setInterval] = useState(project?.contour_interval ?? 0.1);
  const [useBreaklines, setUseBreaklines] = useState(true);
  const [majorEvery, setMajorEvery] = useState(5);

  return (
    <div className="panel shrink-0">
      <div className="panel-title">
        <Mountain size={12} />
        Surface
        <span className="ms-auto text-[9px] font-mono text-muted normal-case tracking-normal">
          {fmtInt(pointCount)} pts
        </span>
      </div>
      <div className="p-2.5 space-y-2">
        <div className="grid grid-cols-2 gap-2">
          <div>
            <label className="label">مرز محدوده</label>
            <select className="field !h-7 !text-[10px]" value={boundary} onChange={(e) => setBoundary(e.target.value)}>
              <option value="concave_hull">پوستهٔ مقعر</option>
              <option value="convex_hull">پوستهٔ محدب</option>
            </select>
          </div>
          <div>
            <label className="label">فاصلهٔ منحنی میزان (متر)</label>
            <select
              className="field !h-7 !text-[10px]"
              value={interval}
              onChange={(e) => setInterval(Number(e.target.value))}
            >
              {[0.05, 0.1, 0.2, 0.25, 0.5, 1].map((value) => (
                <option key={value} value={value}>
                  {value}
                </option>
              ))}
            </select>
          </div>
        </div>
        <div className="grid grid-cols-2 gap-2">
          <div>
            <label className="label">منحنی شاخص در هر</label>
            <select className="field !h-7 !text-[10px]" value={majorEvery} onChange={(e) => setMajorEvery(Number(e.target.value))}>
              {[4, 5, 10].map((value) => (
                <option key={value} value={value}>
                  {value} th
                </option>
              ))}
            </select>
          </div>
          <label className="flex items-end gap-1.5 pb-1 text-[10px] text-muted">
            <input
              type="checkbox"
              className="accent-cyan"
              checked={useBreaklines}
              onChange={(e) => setUseBreaklines(e.target.checked)}
            />
            breaklines
          </label>
        </div>
        <button
          className="btn-primary w-full !h-7"
          onClick={() =>
            void buildSurface({
              boundary_mode: boundary,
              contour_interval: interval,
              major_every: majorEvery,
              use_breaklines: useBreaklines,
              contour_method: "grid",
            })
          }
          disabled={Boolean(busy)}
        >
          {busy ? <Spinner /> : <Layers2 size={12} />} ساخت شبکه مثلثی مقید
        </button>
        {surface && (
          <div className="grid grid-cols-2 gap-1 text-[9px] font-mono">
            {[
              ["tri", fmtInt(Number(surface.mesh.stats.triangles ?? 0))],
              ["constraints", fmtInt(Number(surface.mesh.stats.constraint_edges ?? 0))],
              ["area", `${fmt(Number(surface.stats.area_m2 ?? 0), 1)} m²`],
              ["contours", fmtInt(surface.contours.length)],
            ].map(([label, value]) => (
              <div key={label} className="flex justify-between bg-panel2/60 rounded px-1.5 py-0.5">
                <span className="text-muted">{label}</span>
                <span className="text-ink/90">{value}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
