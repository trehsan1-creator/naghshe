import { useMemo } from "react";
import {
  Boxes,
  CircleDot,
  Eye,
  EyeOff,
  GitBranch,
  Mountain,
  Route,
  Spline,
  Tag,
  Triangle,
} from "lucide-react";
import { useWorkspace } from "../store/workspace";
import { Panel, StatusBadge, fmtInt } from "./ui";
import { codeColor, layerHex } from "../lib/plot";

const LAYER_ROWS = [
  { key: "points", label: "Survey points", icon: CircleDot },
  { key: "labels", label: "Point numbers", icon: Tag },
  { key: "linework", label: "Field-to-finish linework", icon: Route },
  { key: "breaklines", label: "3D breaklines", icon: Spline },
  { key: "tin", label: "TIN mesh", icon: Triangle },
  { key: "contoursMajor", label: "Contours (index)", icon: Mountain },
  { key: "contoursMinor", label: "Contours (intermediate)", icon: Mountain },
  { key: "boundary", label: "Surface boundary", icon: Boxes },
] as const;

export default function LayerManager() {
  const layers = useWorkspace((s) => s.layers);
  const toggleLayer = useWorkspace((s) => s.toggleLayer);
  const points = useWorkspace((s) => s.points);
  const project = useWorkspace((s) => s.project);
  const surfaces = useWorkspace((s) => s.surfaces);
  const loadSurface = useWorkspace((s) => s.loadSurface);
  const surface = useWorkspace((s) => s.surface);
  const viewMode = useWorkspace((s) => s.viewMode);

  const codeUsage = useMemo(() => {
    const usage = new Map<string, { count: number; layer: string }>();
    for (const point of points) {
      const entry = usage.get(point.code || "(none)");
      if (entry) entry.count += 1;
      else usage.set(point.code || "(none)", { count: 1, layer: point.layer });
    }
    return [...usage.entries()].sort((a, b) => b[1].count - a[1].count).slice(0, 14);
  }, [points]);

  return (
    <div className="h-full flex flex-col gap-2 min-h-0">
      <Panel title="Layers" className="shrink-0" icon={<Boxes size={12} />}>
        <ul className="py-1">
          {LAYER_ROWS.map(({ key, label, icon: Icon }) => {
            const active = layers[key];
            const disabled = viewMode === "3d" && (key === "labels" || key === "linework");
            return (
              <li key={key}>
                <button
                  className="w-full flex items-center gap-2 px-2.5 py-[5px] hover:bg-panel2/70 transition-colors group disabled:opacity-40"
                  onClick={() => toggleLayer(key)}
                  disabled={disabled}
                >
                  <Icon size={12} className={active ? "text-cyan" : "text-muted/60"} />
                  <span className={`text-[11px] ${active ? "text-ink" : "text-muted"} truncate`}>{label}</span>
                  <span className="ml-auto text-muted/70 group-hover:text-ink">
                    {active ? <Eye size={11} /> : <EyeOff size={11} />}
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
      </Panel>

      <Panel
        title="Code legend"
        className="shrink-0"
        right={<span className="text-[9px] text-muted font-mono">{codeUsage.length}</span>}
        icon={<Tag size={12} />}
      >
        <ul className="py-1 max-h-[172px] overflow-auto">
          {codeUsage.map(([code, info]) => (
            <li key={code} className="flex items-center gap-2 px-2.5 py-[3px]">
              <span
                className="w-2 h-2 rounded-sm shrink-0"
                style={{ background: codeColor(code, project?.code_mappings ?? []) }}
              />
              <span className="text-[10px] font-mono text-ink/80 truncate">{code || "(none)"}</span>
              <span className="ml-auto text-[9px] font-mono text-muted">{info.count}</span>
              <span
                className="w-1.5 h-1.5 rounded-full shrink-0"
                style={{ background: layerHex(info.layer, project?.code_mappings ?? []) }}
                title={info.layer}
              />
            </li>
          ))}
          {codeUsage.length === 0 && <li className="px-3 py-2 text-[10px] text-muted">No points loaded</li>}
        </ul>
      </Panel>

      <Panel
        title="Derived outputs"
        className="flex-1 min-h-[140px]"
        right={
          <span className="text-[9px] font-mono text-muted">
            {surfaces.filter((s) => s.kind === "surface").length} surfaces
          </span>
        }
        icon={<GitBranch size={12} />}
      >
        <ul className="divide-y divide-edge/50">
          {surfaces.map((item) => {
            const isActive = surface?.output?.id === item.id;
            return (
              <li key={item.id}>
                <button
                  className={`w-full text-left px-2.5 py-1.5 hover:bg-panel2/70 transition-colors ${
                    isActive ? "bg-cyan/5 shadow-[inset_2px_0_0_0_#38BDF8]" : ""
                  }`}
                  onClick={() => {
                    if (item.kind === "surface" && !isActive) void loadSurface(item.id);
                  }}
                  title={item.kind === "surface" ? "Load this surface into the canvas" : item.summary ? JSON.stringify(item.summary) : undefined}
                >
                  <div className="flex items-center gap-1.5">
                    <span className="text-[10px] font-mono uppercase text-cyan/90">{item.kind}</span>
                    <StatusBadge status={item.status} className="!h-[15px] !text-[9px]" />
                    <span className="ml-auto text-[9px] font-mono text-muted">{fmtInt(item.source_point_count)}p</span>
                  </div>
                  <div className="text-[10px] text-ink/80 truncate mt-0.5">{item.name}</div>
                  <div className="text-[9px] text-muted font-mono truncate">
                    {Object.entries(item.summary ?? {})
                      .slice(0, 3)
                      .map(([key, value]) => `${key} ${typeof value === "number" ? Math.round(value * 100) / 100 : value}`)
                      .join(" · ")}
                  </div>
                </button>
              </li>
            );
          })}
          {surfaces.length === 0 && (
            <li className="px-3 py-3 text-[10px] text-muted leading-relaxed">
              No derived outputs yet. Build a TIN surface to create contours, volumes, profiles and DXF exports.
            </li>
          )}
        </ul>
      </Panel>
    </div>
  );
}
