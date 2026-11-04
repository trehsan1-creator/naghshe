import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import DeckGL from "@deck.gl/react";
import { OrthographicView } from "@deck.gl/core";
import type { Layer, PickingInfo } from "@deck.gl/core";
import {
  PathLayer,
  PolygonLayer,
  ScatterplotLayer,
  TextLayer,
} from "@deck.gl/layers";
import type { SurveyPoint } from "../lib/types";
import {
  STATUS_HEX,
  centroid,
  codeColor,
  elevationColor,
  extentOfPoints,
  fitOrthoZoom,
  hexToRgb,
  layerHex,
} from "../lib/plot";
import { useWorkspace } from "../store/workspace";

interface ViewState {
  target: [number, number, number];
  zoom: number;
  rotationX?: number;
}

const view = new OrthographicView({ id: "plan", flipY: true, controller: true });

function useElementSize<T extends HTMLElement>() {
  const ref = useRef<T | null>(null);
  const [size, setSize] = useState({ width: 0, height: 0 });

  useEffect(() => {
    const element = ref.current;
    if (!element) return;
    const observer = new ResizeObserver((entries) => {
      const rect = entries[0]?.contentRect;
      if (rect) setSize({ width: rect.width, height: rect.height });
    });
    observer.observe(element);
    setSize({ width: element.clientWidth, height: element.clientHeight });
    return () => observer.disconnect();
  }, []);

  return { ref, size };
}

export default function PlanCanvas() {
  const { ref, size } = useElementSize<HTMLDivElement>();
  const points = useWorkspace((s) => s.points);
  const surface = useWorkspace((s) => s.surface);
  const linework = useWorkspace((s) => s.linework);
  const layers = useWorkspace((s) => s.layers);
  const project = useWorkspace((s) => s.project);
  const selected = useWorkspace((s) => s.selectedPoint);
  const selectPoint = useWorkspace((s) => s.selectPoint);

  const extent = useMemo(() => {
    if (surface?.extent) {
      return {
        minX: surface.extent.min_x,
        maxX: surface.extent.max_x,
        minY: surface.extent.min_y,
        maxY: surface.extent.max_y,
        minZ: surface.extent.min_z ?? 0,
        maxZ: surface.extent.max_z ?? 1,
      };
    }
    return extentOfPoints(points);
  }, [points, surface]);

  const extentKey = extent
    ? `${extent.minX.toFixed(2)}:${extent.maxX.toFixed(2)}:${extent.minY.toFixed(2)}:${extent.maxY.toFixed(2)}`
    : "empty";

  const [viewState, setViewState] = useState<ViewState>({ target: [0, 0, 0], zoom: 0 });

  useEffect(() => {
    if (!extent || size.width < 40 || size.height < 40) return;
    setViewState({
      target: [centroid(extent)[0], centroid(extent)[1], 0],
      zoom: fitOrthoZoom(extent, size.width, size.height),
      rotationX: 0,
    });
    // Re-fit only when the data extent or the canvas size changes materially.
  }, [extentKey, Math.round(size.width / 40), Math.round(size.height / 40)]);

  const mappings = project?.code_mappings ?? [];

  const handleClick = useCallback(
    (info: PickingInfo) => {
      if (info.object && (info.object as SurveyPoint).point_number) {
        selectPoint(info.object as SurveyPoint);
      }
    },
    [selectPoint],
  );

  const deckLayers = useMemo(() => {
    const result: Layer[] = [];
    if (!extent) return result;

    if (layers.tin && surface) {
      const { vertices, faces } = surface.mesh;
      const zSpan = surface.stats.max_z - surface.stats.min_z || 1;
      result.push(
        new PolygonLayer({
          id: "tin",
          data: faces,
          getPolygon: (face: number[]) =>
            face.map((i) => [vertices[i][0], vertices[i][1], vertices[i][2]]),
          getFillColor: (face: number[]) => {
            const z = (vertices[face[0]][2] + vertices[face[1]][2] + vertices[face[2]][2]) / 3;
            const color = elevationColor(
              z,
              surface.stats.min_z,
              surface.stats.min_z + zSpan,
            );
            return [color[0], color[1], color[2], 34];
          },
          getLineColor: [86, 110, 140, 90],
          stroked: true,
          filled: true,
          extruded: false,
          lineWidthMinPixels: 0.5,
          pickable: false,
          parameters: { depthCompare: "always", depthWriteEnabled: false },
        }),
      );
    }

    if (layers.contoursMinor || layers.contoursMajor) {
      const contours = surface?.contours.filter((c) => (c.is_major ? layers.contoursMajor : layers.contoursMinor)) ?? [];
      result.push(
        new PathLayer({
          id: "contours",
          data: contours,
          getPath: (c: (typeof contours)[number]) =>
            c.points.map((p) => [p[0], p[1]] as [number, number]),
          getColor: (c: (typeof contours)[number]) =>
            c.is_major ? [232, 121, 249, 235] : [120, 136, 156, 165],
          getWidth: (c: (typeof contours)[number]) => (c.is_major ? 1.9 : 1),
          widthUnits: "pixels",
          widthMinPixels: 0.6,
          pickable: false,
          parameters: { depthCompare: "always", depthWriteEnabled: false },
        }),
      );
    }

    if (layers.linework && linework) {
      result.push(
        new PathLayer({
          id: "linework",
          data: linework.features,
          getPath: (f: (typeof linework.features)[number]) =>
            f.vertices.map((v) => [v[0], v[1]] as [number, number]),
          getColor: (f: (typeof linework.features)[number]) => {
            const rgb = hexToRgb(layerHex(f.layer, mappings));
            return [...rgb, 225];
          },
          getWidth: 2.2,
          widthUnits: "pixels",
          widthMinPixels: 1.4,
          capRounded: true,
          jointRounded: true,
          pickable: true,
          parameters: { depthCompare: "always", depthWriteEnabled: false },
        }),
      );
    }

    if (layers.breaklines && surface) {
      result.push(
        new PathLayer({
          id: "breaklines",
          data: surface.breaklines,
          getPath: (b: { vertices: number[][] }) =>
            b.vertices.map((v) => [v[0], v[1]] as [number, number]),
          getColor: [244, 114, 182, 220],
          getWidth: 2.8,
          widthUnits: "pixels",
          widthMinPixels: 1.6,
          pickable: false,
          parameters: { depthCompare: "always", depthWriteEnabled: false },
        }),
      );
    }

    if (layers.boundary && surface?.boundary) {
      const ring = [...surface.boundary, surface.boundary[0]].map(
        (p) => [p[0], p[1]] as [number, number],
      );
      result.push(
        new PathLayer({
          id: "boundary",
          data: [ring],
          getPath: (path: [number, number][]) => path,
          getColor: [56, 189, 248, 190],
          getWidth: 1.6,
          widthUnits: "pixels",
          pickable: false,
          parameters: { depthCompare: "always", depthWriteEnabled: false },
        }),
      );
    }

    if (layers.points) {
      result.push(
        new ScatterplotLayer<SurveyPoint>({
          id: "points",
          data: points,
          getPosition: (p) => [p.easting, p.northing],
          getRadius: (p) => (p.id === selected?.id ? 6 : 3),
          radiusUnits: "pixels",
          getFillColor: (p) => {
            const hex =
              p.qa_severity === "error"
                ? "#F87171"
                : p.qa_severity === "warning"
                  ? "#FBBF24"
                  : codeColor(p.code, mappings);
            return [...hexToRgb(hex), 235];
          },
          getLineColor: (p) => (p.id === selected?.id ? [255, 255, 255, 255] : hexToRgb(STATUS_HEX[p.status] ?? "#8A94A6")),
          getLineWidth: (p) => (p.id === selected?.id ? 2 : 0.8),
          lineWidthUnits: "pixels",
          stroked: true,
          filled: true,
          pickable: true,
          autoHighlight: true,
          highlightColor: [56, 189, 248, 120],
          onClick: (info) => handleClick(info),
          parameters: { depthCompare: "always", depthWriteEnabled: false },
        }),
      );
    }

    if (layers.labels && points.length <= 1200) {
      result.push(
        new TextLayer<SurveyPoint>({
          id: "labels",
          data: points,
          getPosition: (p) => [p.easting, p.northing],
          getText: (p) => p.point_number,
          getSize: 9,
          sizeUnits: "pixels",
          getColor: [225, 232, 242, 200],
          getPixelOffset: [0, -9],
          fontFamily: "JetBrains Mono, ui-monospace, monospace",
          fontWeight: 500,
          billboard: false,
          pickable: false,
          parameters: { depthCompare: "always", depthWriteEnabled: false },
        }),
      );
    }

    return result;
  }, [points, surface, linework, layers, selected?.id, mappings, handleClick, extent]);

  const scaleBar = useMemo(() => {
    const mpp = 1 / Math.pow(2, viewState.zoom);
    const targets = [1, 2, 5, 10, 20, 25, 50, 100];
    const meters = targets.find((t) => t / mpp >= 60) ?? 100;
    return { meters, pixels: meters / mpp };
  }, [viewState.zoom]);

  return (
    <div ref={ref} className="absolute inset-0">
      <DeckGL
        views={view}
        viewState={viewState}
        controller={{ dragRotate: false, inertia: false, scrollZoom: { speed: 0.03, smooth: false } }}
        layers={deckLayers}
        onViewStateChange={(event) => {
          const next = event.viewState as unknown as ViewState;
          setViewState({
            target: [next.target[0], next.target[1], 0],
            zoom: next.zoom,
            rotationX: 0,
          });
        }}
        getCursor={({ isDragging, isHovering }) => (isDragging ? "grabbing" : isHovering ? "pointer" : "crosshair")}
        getTooltip={({ object }) => {
          const point = object as SurveyPoint | null;
          if (!point?.point_number) return null;
          return {
            className: "deck-tooltip",
            html: `<div style="color:#38BDF8;font-weight:600">${point.point_number}</div>
              <div>${point.code || "—"}</div>
              <div style="color:#8A94A6">X ${point.easting.toFixed(3)} · Y ${point.northing.toFixed(3)}</div>
              <div style="color:#8A94A6">Z ${point.elevation === null ? "—" : point.elevation.toFixed(3)}</div>`,
          };
        }}
      />

      <div className="absolute start-3 bottom-3 flex items-end gap-3 pointer-events-none select-none" dir="rtl">
        <div className="panel px-2 py-1.5 bg-panel/90">
          <div className="flex items-center gap-1.5">
            <div className="h-1.5 border-x border-t border-muted" style={{ width: Math.min(scaleBar.pixels, 220) }} />
          </div>
          <div className="text-[9px] font-mono text-muted mt-0.5">{scaleBar.meters} متر</div>
        </div>
        <div className="panel px-2 py-1.5 bg-panel/90 text-[9px] font-mono text-muted leading-relaxed">
          <div>
            نمای پلان · <span dir="ltr">EPSG:{project?.crs_epsg ?? "—"}</span>
          </div>
          <div>
            هر پیکسل = <span dir="ltr">{(1 / Math.pow(2, viewState.zoom)).toFixed(3)}</span> متر ·{" "}
            {points.length} نقطه
          </div>
        </div>
      </div>

      <div className="absolute end-3 top-3 panel bg-panel/90 px-2 py-1 text-[9px] font-mono text-muted">
        <div className="flex items-center gap-1.5">
          <span
            className="w-2 h-2 rounded-full"
            style={{ background: STATUS_HEX.APPROVED }}
          />
          تأییدشده
          <span className="w-2 h-2 rounded-full ms-1" style={{ background: STATUS_HEX.VALIDATED }} />
          اعتبارسنجی
          <span className="w-2 h-2 rounded-full ms-1" style={{ background: STATUS_HEX.RAW }} />
          خام
          <span className="w-2 h-2 rounded-full ms-1" style={{ background: STATUS_HEX.REJECTED }} />
          ردشده
        </div>
      </div>
    </div>
  );
}
