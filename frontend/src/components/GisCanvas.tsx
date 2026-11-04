import { useEffect, useMemo, useRef, useState } from "react";
import maplibregl from "maplibre-gl";
import { Info, Layers2, MapPinned, X } from "lucide-react";
import { api } from "../lib/api";
import type { GeoJsonFeatureCollection } from "../lib/types";
import { useWorkspace } from "../store/workspace";
import { STATUS_FA } from "../lib/i18n";

/**
 * نقشه پایه — هیچ‌کدام از این سرویس‌ها کلید API نمی‌خواهند.
 * برای سرویس تجاری (MapTiler/Mapbox/…)، آدرس XYZ را در VITE_TILE_URL بگذارید؛
 * آن‌گاه گزینهٔ «سرویس سفارشی» به‌صورت خودکار در همین پنل ظاهر می‌شود.
 */
type BasemapKind = "none" | "carto" | "osm" | "custom";

const CUSTOM_TILE_URL = import.meta.env.VITE_TILE_URL as string | undefined;
const CUSTOM_TILE_ATTRIBUTION =
  (import.meta.env.VITE_TILE_ATTRIBUTION as string | undefined) ?? "سرویس نقشه پایه سفارشی";

const BASEMAPS: Record<BasemapKind, { label: string; tiles: string[]; attribution?: string }> = {
  none: { label: "بدون نقشه پایه", tiles: [] },
  carto: {
    label: "کارتو تیره",
    tiles: [
      "https://a.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png",
      "https://b.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png",
      "https://c.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png",
    ],
    attribution: '© OpenStreetMap · © CARTO',
  },
  osm: {
    label: "اوپن‌استریت‌مپ",
    tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
    attribution: "© OpenStreetMap contributors",
  },
  custom: {
    label: "سرویس سفارشی",
    tiles: CUSTOM_TILE_URL ? [CUSTOM_TILE_URL] : [],
    attribution: CUSTOM_TILE_ATTRIBUTION,
  },
};

const STORAGE_KEY = "surveypro.basemap";
const EMPTY_FC: GeoJsonFeatureCollection = { type: "FeatureCollection", features: [] };

function buildStyle(kind: BasemapKind): maplibregl.StyleSpecification {
  const basemap = BASEMAPS[kind];
  const hasRaster = basemap.tiles.length > 0;
  const style: maplibregl.StyleSpecification = {
    version: 8,
    sources: {},
    layers: [{ id: "bg", type: "background", paint: { "background-color": "#0d0f12" } }],
  };
  if (hasRaster) {
    style.sources.basemap = {
      type: "raster",
      tiles: basemap.tiles,
      tileSize: 256,
      attribution: basemap.attribution,
    };
    style.layers.push({
      id: "basemap",
      type: "raster",
      source: "basemap",
      paint: { "raster-opacity": 0.9, "raster-saturation": -0.15, "raster-brightness-max": 0.8 },
    });
  }
  return style;
}

export default function GisCanvas() {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const tileErrors = useRef(0);
  const [ready, setReady] = useState(false);
  const [styleVersion, setStyleVersion] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [showHelp, setShowHelp] = useState(false);
  const [data, setData] = useState<GeoJsonFeatureCollection>(EMPTY_FC);
  // Start offline-first: the project vectors do not depend on any tile provider or API key.
  const [basemap, setBasemap] = useState<BasemapKind>("none");

  const project = useWorkspace((s) => s.project);
  const points = useWorkspace((s) => s.points);
  const surface = useWorkspace((s) => s.surface);
  const layers = useWorkspace((s) => s.layers);
  const selectPoint = useWorkspace((s) => s.selectPoint);

  const pointCount = points.length;
  const surfaceId = surface?.output?.id ?? null;

  // ---- داده‌های برداری (تجدید نظر شده با pyproj در سمت سرور) -------------------
  useEffect(() => {
    if (!project) return;
    let cancelled = false;
    api
      .geojson(project.id, surfaceId)
      .then((collection) => {
        if (!cancelled) {
          setData(collection);
          setError(null);
        }
      })
      .catch((err) => {
        if (!cancelled) setError((err as Error).message);
      });
    return () => {
      cancelled = true;
    };
  }, [project?.id, surfaceId, pointCount]);

  // ---- ساخت نقشه -------------------------------------------------------------
  useEffect(() => {
    if (mapRef.current || !containerRef.current) return;
    const map = new maplibregl.Map({
      container: containerRef.current,
      style: buildStyle(basemap),
      center: [4.66, 52.23],
      zoom: 15,
      attributionControl: { compact: true },
      maxPitch: 60,
    });
    mapRef.current = map;
    map.addControl(new maplibregl.NavigationControl({ visualizePitch: true }), "bottom-left");
    map.addControl(new maplibregl.ScaleControl({ unit: "metric" }), "bottom-right");
    const resizeObserver = new ResizeObserver(() => map.resize());
    resizeObserver.observe(containerRef.current);
    map.on("load", () => {
      map.resize();
      setReady(true);
      setStyleVersion((version) => version + 1);
    });
    map.on("error", (event) => {
      const sourceId = (event as unknown as { sourceId?: string }).sourceId;
      const message = (event as unknown as { error?: Error }).error?.message ?? "";
      if (sourceId === "basemap" || /tile|403|401|api.?key/i.test(message)) {
        tileErrors.current += 1;
        if (tileErrors.current >= 3) {
          setBasemap("none");
          setNotice(
            "نقشه پایه در دسترس نیست (شبکه یا محدودیت سرویس). لایه‌های برداری فعال هستند؛ می‌توانید نقشه پایه دیگری انتخاب کنید. هیچ کلید API لازم نیست.",
          );
        }
      }
    });
    return () => {
      resizeObserver.disconnect();
      map.remove();
      mapRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ---- تغییر نقشه پایه بدون از دست دادن لایه‌ها -------------------------------
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    window.localStorage.setItem(STORAGE_KEY, basemap);
    tileErrors.current = 0;
    map.setStyle(buildStyle(basemap), { diff: false });
    const onStyled = () => {
      map.resize();
      setStyleVersion((version) => version + 1);
    };
    map.once("style.load", onStyled);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [basemap]);

  // ---- لایه‌های برداری روی نقشه ----------------------------------------------
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;

    try {
      const ensureSource = (id: string) => {
        if (!map.getSource(id)) map.addSource(id, { type: "geojson", data: EMPTY_FC as never });
      };
      ensureSource("points");
      ensureSource("linework");
      ensureSource("contours");
      ensureSource("boundary");

      const subset = (kind: string) =>
        ({ type: "FeatureCollection", features: data.features.filter((f) => f.properties?.kind === kind) }) as never;
      (map.getSource("points") as maplibregl.GeoJSONSource).setData(subset("point"));
      (map.getSource("linework") as maplibregl.GeoJSONSource).setData(subset("linework"));
      (map.getSource("boundary") as maplibregl.GeoJSONSource).setData(subset("boundary"));
      (map.getSource("contours") as maplibregl.GeoJSONSource).setData(subset("contour"));

      if (!map.getLayer("boundary-fill")) {
        map.addLayer({
          id: "boundary-fill",
          type: "fill",
          source: "boundary",
          paint: { "fill-color": "#38BDF8", "fill-opacity": 0.06 },
        });
        map.addLayer({
          id: "boundary-line",
          type: "line",
          source: "boundary",
          paint: { "line-color": "#38BDF8", "line-width": 1.4, "line-opacity": 0.8 },
        });
        map.addLayer({
          id: "contours-minor",
          type: "line",
          source: "contours",
          filter: ["==", ["get", "is_major"], false],
          paint: { "line-color": "#7C8A9C", "line-width": 0.7, "line-opacity": 0.8 },
        });
        map.addLayer({
          id: "contours-major",
          type: "line",
          source: "contours",
          filter: ["==", ["get", "is_major"], true],
          paint: { "line-color": "#E879F9", "line-width": 1.4, "line-opacity": 0.95 },
        });
        map.addLayer({
          id: "linework",
          type: "line",
          source: "linework",
          paint: {
            "line-color": [
              "match",
              ["get", "layer"],
              "S-CURB",
              "#F472B6",
              "S-SIDEWALK",
              "#38BDF8",
              "S-CENTRELINE",
              "#FBBF24",
              "S-TREE",
              "#34D399",
              "#A3E635",
            ],
            "line-width": 2.2,
          },
        });
        map.addLayer({
          id: "points",
          type: "circle",
          source: "points",
          paint: {
            "circle-radius": ["interpolate", ["linear"], ["zoom"], 12, 2.2, 18, 5],
            "circle-color": [
              "match",
              ["get", "status"],
              "APPROVED",
              "#A3E635",
              "VALIDATED",
              "#38BDF8",
              "REJECTED",
              "#F87171",
              "#8A94A6",
            ],
            "circle-stroke-color": "#0d0f12",
            "circle-stroke-width": 0.6,
            "circle-opacity": 0.95,
          },
        });
        map.on("click", "points", (event) => {
          const feature = event.features?.[0];
          if (!feature) return;
          const id = feature.properties?.id as string | undefined;
          const found = id ? useWorkspace.getState().points.find((p) => p.id === id) : undefined;
          if (found) {
            selectPoint(found);
            new maplibregl.Popup({ closeButton: false, offset: 10 })
              .setLngLat(event.lngLat)
              .setHTML(
                `<div dir="rtl" style="font-family:Vazirmatn,sans-serif;font-size:11px;color:#E6EDF5">
                  <b style="color:#38BDF8">نقطه ${found.point_number}</b><br/>
                  کد ${found.code || "—"} · ارتفاع ${found.elevation?.toFixed(3) ?? "—"}<br/>
                  <span style="color:#8A94A6">${STATUS_FA[found.status] ?? found.status}</span>
                </div>`,
              )
              .addTo(map);
          }
        });
        map.on("mouseenter", "points", () => {
          map.getCanvas().style.cursor = "pointer";
        });
        map.on("mouseleave", "points", () => {
          map.getCanvas().style.cursor = "";
        });
      }

      const visibility = (id: string, visible: boolean) => {
        if (map.getLayer(id)) map.setLayoutProperty(id, "visibility", visible ? "visible" : "none");
      };
      visibility("points", layers.points);
      visibility("linework", layers.linework);
      visibility("contours-minor", layers.contoursMinor);
      visibility("contours-major", layers.contoursMajor);
      visibility("boundary-fill", layers.boundary);
      visibility("boundary-line", layers.boundary);

      if (data.bbox && data.bbox.length === 4) {
        const [minLon, minLat, maxLon, maxLat] = data.bbox;
        map.fitBounds(
          [
            [minLon, minLat],
            [maxLon, maxLat],
          ],
          { padding: 60, duration: 600, maxZoom: 19 },
        );
      }
    } catch (err) {
      setError((err as Error).message);
    }
  }, [ready, styleVersion, data, layers, selectPoint]);

  const options = useMemo(
    () => (Object.keys(BASEMAPS) as BasemapKind[]).filter((kind) => kind !== "custom" || CUSTOM_TILE_URL),
    [],
  );

  return (
    <div className="absolute inset-0">
      <div ref={containerRef} className="absolute inset-0" />

      <div className="absolute top-3 start-3 flex flex-col gap-1.5 max-w-[320px]">
        <div className="panel bg-panel/95 px-2 py-1.5">
          <div className="flex items-center gap-1.5 text-[10px] text-muted mb-1">
            <MapPinned size={11} /> نقشه پایه
            <span className="chip !text-[9px] !h-[15px] !text-lime !border-lime/40">بدون کلید API</span>
            <button
              className="ms-auto text-muted hover:text-cyan"
              onClick={() => setShowHelp((value) => !value)}
              title="توضیح دربارهٔ کلید API"
            >
              <Info size={12} />
            </button>
          </div>
          <div className="flex flex-wrap gap-1">
            {options.map((kind) => (
              <button
                key={kind}
                onClick={() => {
                  setNotice(null);
                  setBasemap(kind);
                }}
                className={`h-5 px-1.5 rounded border text-[9px] transition-colors ${
                  basemap === kind
                    ? "border-cyan/60 text-cyan bg-cyan/10"
                    : "border-edge text-muted hover:text-ink"
                }`}
              >
                {BASEMAPS[kind].label}
              </button>
            ))}
          </div>
        </div>

        {showHelp && (
          <div className="panel bg-panel/95 p-2 text-[10px] leading-relaxed text-muted">
            <div className="flex items-center gap-1 text-cyan mb-1">
              <Layers2 size={11} /> چرا کلید API لازم نیست؟
              <button className="ms-auto text-muted hover:text-ink" onClick={() => setShowHelp(false)}>
                <X size={11} />
              </button>
            </div>
            کاشی‌های «کارتو تیره» و «اوپن‌استریت‌مپ» آزاد و بدون کلید هستند. اگر سرویس تجاری
            (MapTiler، Mapbox، …) می‌خواهید، آدرس XYZ آن را در متغیر محیطی{" "}
            <span dir="ltr" className="font-mono text-ink/80">VITE_TILE_URL</span> بگذارید تا گزینهٔ
            «سرویس سفارشی» در همین پنل ظاهر شود. در حالت «بدون نقشه پایه» هیچ درخواست شبکه‌ای انجام
            نمی‌شود و فقط دادهٔ برداری پروژه نمایش داده می‌شود.
          </div>
        )}

        {notice && (
          <div className="panel bg-panel/95 border-amber/40 p-2 text-[10px] leading-relaxed text-amber">
            {notice}
          </div>
        )}
      </div>

      {error && (
        <div className="absolute top-3 end-3 panel bg-panel/95 px-2 py-1 text-[10px] text-danger max-w-[260px]">
          خطا در دریافت دادهٔ مکانی: {error}
        </div>
      )}

      <div className="absolute top-3 end-3 panel bg-panel/90 px-2 py-1 text-[9px] font-mono text-muted text-end">
        <div>EPSG:4326 · نقشه وب</div>
        <div>
          {data.features.filter((f) => f.properties?.kind === "point").length} نقطه ·{" "}
          {data.features.filter((f) => f.properties?.kind === "linework").length} خط
        </div>
      </div>
    </div>
  );
}
