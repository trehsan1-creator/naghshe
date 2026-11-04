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
      <div className="min-h-9 shrink-0 flex flex-wrap items-center gap-2 px-2 py-1 border-b border-edge">
        <Scissors size={12} className="text-muted" />
        <span className="text-[10px] uppercase tracking-[0.14em] text-muted">خاک‌برداری و خاک‌ریزی</span>
        <select
          className="field !h-6 !text-[10px] font-mono max-w-[210px] ms-2"
          value={existing}
          onChange={(event) => setExistingId(event.target.value)}
        >
          {surfaceOptions.map((s) => (
            <option key={s.id} value={s.id}>
              وضع موجود: {s.name}
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
              سطح مقایسه: {s.name}
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
          {busy ? <Spinner /> : <Scissors size={11} />} محاسبه حجم
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
            title={surfaceOptions.length < 2 ? "برای مقایسه دو سطح لازم است" : "حجمی محاسبه نشده است"}
            hint={
              surfaceOptions.length < 2
                ? "از پنل سطح، فایل برداشت را انتخاب کنید و برای هر برداشت یک سطح جداگانه بسازید؛ سپس یکی را وضع موجود و دیگری را سطح مقایسه انتخاب کنید."
                : "دو سطح را انتخاب کنید. محاسبهٔ شبکه‌ای فقط محدودهٔ هم‌پوشان دو سطح را در نظر می‌گیرد."
            }
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
  const [sourceFileId, setSourceFileId] = useState("");
  const [surfaceName, setSurfaceName] = useState("");
  const importedFiles = (project?.files ?? []).filter((file) => file.imported_points > 0);

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
        <div>
          <label className="label">فایل برداشتِ این سطح</label>
          <select
            className="field !h-7 !text-[10px] w-full"
            aria-label="فایل برداشتِ این سطح"
            value={sourceFileId}
            onChange={(event) => {
              const fileId = event.target.value;
              setSourceFileId(fileId);
              const file = importedFiles.find((item) => item.id === fileId);
              if (file) setSurfaceName(`${file.original_filename.replace(/\.[^.]+$/, "")} · سطح`);
              else if (fileId === "__all__") setSurfaceName("سطح ترکیبی پروژه");
              else setSurfaceName("");
            }}
          >
            <option value="">انتخاب فایل برداشت…</option>
            {importedFiles.map((file) => (
              <option key={file.id} value={file.id}>
                {file.original_filename} · {fmtInt(file.imported_points)} نقطه
              </option>
            ))}
            <option value="__all__">همهٔ نقاط پروژه (ترکیب فایل‌ها)</option>
          </select>
          <p className="text-[9px] text-muted mt-1 leading-relaxed">
            برای مقایسهٔ دو برداشت، هر بار یک فایل را انتخاب و سطح جداگانه بسازید.
          </p>
        </div>
        <div>
          <label className="label">نام سطح (مثلاً برداشت قدیم / جدید)</label>
          <input
            className="field !h-7 !text-[10px] w-full"
            aria-label="نام سطح"
            value={surfaceName}
            onChange={(event) => setSurfaceName(event.target.value)}
            placeholder="نام‌گذاری سطح برای انتخاب در محاسبهٔ حجم"
          />
        </div>
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
              name: surfaceName.trim(),
              file_id: sourceFileId && sourceFileId !== "__all__" ? sourceFileId : undefined,
              boundary_mode: boundary,
              contour_interval: interval,
              major_every: majorEvery,
              use_breaklines: useBreaklines,
              contour_method: "grid",
            })
          }
          disabled={Boolean(busy) || !sourceFileId || !surfaceName.trim()}
        >
          {busy ? <Spinner /> : <Layers2 size={12} />} ساخت سطح از فایل انتخاب‌شده
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
