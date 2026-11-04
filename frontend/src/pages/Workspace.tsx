import { Suspense, lazy, useState } from "react";
import {
  Box,
  Crosshair,
  Layers,
  Map as MapIcon,
  Mountain,
  PanelBottomClose,
  PanelBottomOpen,
  Scissors,
  ShieldCheck,
  Spline,
  Table2,
  Waves,
} from "lucide-react";
import LayerManager from "../components/LayerManager";
import PointTable from "../components/PointTable";
import PropertiesPanel from "../components/PropertiesPanel";
import { CrossSectionTab, ProfileTab, SurfaceControls, VolumeTab } from "../components/ComputationPanels";
import { useWorkspace, type ViewMode } from "../store/workspace";
import { Spinner, fmtInt } from "../components/ui";

// The three heavy viewers (deck.gl / MapLibre / three.js) are code-split so the
// initial workspace shell loads instantly and each renderer is fetched on demand.
const PlanCanvas = lazy(() => import("../components/PlanCanvas"));
const GisCanvas = lazy(() => import("../components/GisCanvas"));
const Scene3D = lazy(() => import("../components/Scene3D"));

function CanvasFallback() {
  return (
    <div className="absolute inset-0 flex items-center justify-center gap-2 text-[11px] text-muted">
      <Spinner /> در حال آماده‌سازی نمایشگر…
    </div>
  );
}

type DockTab = "points" | "profile" | "volumes" | "sections";

const MODES: { key: ViewMode; label: string; icon: typeof MapIcon }[] = [
  { key: "plan", label: "پلان", icon: MapIcon },
  { key: "gis", label: "نقشه مکانی", icon: Crosshair },
  { key: "3d", label: "3D", icon: Box },
];

const TABS: { key: DockTab; label: string; icon: typeof Table2 }[] = [
  { key: "points", label: "نقاط", icon: Table2 },
  { key: "profile", label: "نیمرخ", icon: Spline },
  { key: "volumes", label: "خاک‌برداری و خاک‌ریزی", icon: Scissors },
  { key: "sections", label: "مقاطع", icon: Waves },
];

export default function Workspace() {
  const viewMode = useWorkspace((s) => s.viewMode);
  const setViewMode = useWorkspace((s) => s.setViewMode);
  const runQa = useWorkspace((s) => s.runQa);
  const qa = useWorkspace((s) => s.qa);
  const points = useWorkspace((s) => s.points);
  const surface = useWorkspace((s) => s.surface);
  const surfaces = useWorkspace((s) => s.surfaces);
  const exaggeration = useWorkspace((s) => s.verticalExaggeration);
  const setExaggeration = useWorkspace((s) => s.setVerticalExaggeration);
  const busy = useWorkspace((s) => s.busy);
  const [tab, setTab] = useState<DockTab>("points");
  const [dockOpen, setDockOpen] = useState(true);
  const [fitKey, setFitKey] = useState(0);

  const counts = points.reduce<Record<string, number>>((acc, point) => {
    acc[point.status] = (acc[point.status] ?? 0) + 1;
    return acc;
  }, {});

  return (
    <div className="h-full flex flex-col min-h-0">
      <div className="workspace-toolbar h-10 shrink-0 border-b border-edge bg-panel flex items-center gap-2 px-2">
        <div className="flex items-center rounded border border-edge overflow-hidden">
          {MODES.map(({ key, label, icon: Icon }) => (
            <button
              key={key}
              onClick={() => setViewMode(key)}
              className={`h-6 px-2 flex items-center gap-1 text-[10px] uppercase tracking-[0.1em] transition-colors ${
                viewMode === key ? "bg-cyan/15 text-cyan" : "text-muted hover:text-ink hover:bg-panel2"
              }`}
            >
              <Icon size={11} /> {label}
            </button>
          ))}
        </div>

        <button className="btn-ghost !h-7 !px-1.5" onClick={() => setFitKey((k) => k + 1)} title="نمایش کامل محدوده">
          <Crosshair size={13} />
        </button>

        <div className="w-px h-5 bg-edge" />

        <button className="btn !h-7 !text-[10px]" onClick={() => void runQa()} disabled={Boolean(busy)}>
          {busy ? <Spinner /> : <ShieldCheck size={12} />} اجرای کنترل کیفیت
          {qa && <span className="ms-1 text-[9px] text-amber">{qa.flags.length}</span>}
        </button>

        <div className="flex items-center gap-1.5 text-[9px] font-mono text-muted ms-1">
          <span className="w-1.5 h-1.5 rounded-full bg-lime inline-block" /> {fmtInt(counts.APPROVED ?? 0)}
          <span className="w-1.5 h-1.5 rounded-full bg-cyan inline-block ms-1" /> {fmtInt(counts.VALIDATED ?? 0)}
          <span className="w-1.5 h-1.5 rounded-full bg-muted inline-block ms-1" /> {fmtInt(counts.RAW ?? 0)}
          <span className="w-1.5 h-1.5 rounded-full bg-danger inline-block ms-1" /> {fmtInt(counts.REJECTED ?? 0)}
        </div>

        {viewMode === "3d" && (
          <div className="flex items-center gap-1.5 ms-2">
            <span className="text-[9px] uppercase tracking-[0.1em] text-muted">Z ×</span>
            <input
              type="range"
              min={1}
              max={12}
              step={0.5}
              value={exaggeration}
              onChange={(event) => setExaggeration(Number(event.target.value))}
              className="w-24 accent-cyan"
            />
            <span className="text-[9px] font-mono text-cyan w-6">{exaggeration.toFixed(1)}</span>
          </div>
        )}

        <div className="ms-auto flex items-center gap-1.5">
          <span className="text-[9px] font-mono text-muted hidden lg:flex items-center gap-1">
            <Mountain size={11} /> {surface ? `شبکه مثلثی · ${fmtInt(Number(surface.mesh.stats.triangles ?? 0))} مثلث` : "بدون سطح"}
            <span className="text-edge">·</span>
            <Layers size={11} /> {surfaces.length} خروجی مشتق‌شده
          </span>
          <button
            className="btn-ghost !h-7 !px-1.5"
            onClick={() => setDockOpen((open) => !open)}
            title={dockOpen ? "بستن پنل داده" : "بازکردن پنل داده"}
          >
            {dockOpen ? <PanelBottomClose size={13} /> : <PanelBottomOpen size={13} />}
          </button>
        </div>
      </div>

      <div className="workspace-layout flex-1 min-h-0 flex">
        <aside className="workspace-layers w-[248px] shrink-0 p-2 pe-1 min-h-0">
          <LayerManager />
        </aside>

        <section className="workspace-canvas flex-1 min-w-0 min-h-0 flex flex-col gap-2 p-2">
          <div className="panel relative flex-1 min-h-0 overflow-hidden grid-bg">
            <Suspense fallback={<CanvasFallback />}>
              {viewMode === "plan" && <PlanCanvas key={`plan-${fitKey}`} />}
              {viewMode === "gis" && <GisCanvas />}
              {viewMode === "3d" && <Scene3D />}
            </Suspense>
          </div>

          {dockOpen && (
            <div className="panel h-[262px] shrink-0 flex flex-col overflow-hidden">
              <div className="h-8 shrink-0 flex items-center border-b border-edge bg-panel2/40">
                {TABS.map(({ key, label, icon: Icon }) => (
                  <button
                    key={key}
                    onClick={() => setTab(key)}
                    className={`h-full px-3 flex items-center gap-1.5 text-[10px] uppercase tracking-[0.1em] border-e border-edge transition-colors ${
                      tab === key
                        ? "text-cyan bg-cyan/5 shadow-[inset_0_-2px_0_0_#38BDF8]"
                        : "text-muted hover:text-ink"
                    }`}
                  >
                    <Icon size={11} /> {label}
                  </button>
                ))}
                <span className="ms-auto px-2 text-[9px] font-mono text-muted">
                  {tab === "points" ? "جدول نقاط قابل ویرایش" : "مشتق‌شده از سطح فعال"}
                </span>
              </div>
              <div className="flex-1 min-h-0">
                {tab === "points" && <PointTable />}
                {tab === "profile" && <ProfileTab />}
                {tab === "volumes" && <VolumeTab />}
                {tab === "sections" && <CrossSectionTab />}
              </div>
            </div>
          )}
        </section>

        <aside className="workspace-properties w-[306px] shrink-0 p-2 ps-1 min-h-0 flex flex-col gap-2">
          <div className="flex-1 min-h-0">
            <PropertiesPanel />
          </div>
          <SurfaceControls />
        </aside>
      </div>
    </div>
  );
}
