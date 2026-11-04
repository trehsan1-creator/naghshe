import { useEffect, useMemo, useRef, useState } from "react";
import maplibregl from "maplibre-gl";
import { api } from "../lib/api";
import type { GeoJsonFeatureCollection } from "../lib/types";
import { useWorkspace } from "../store/workspace";

const BASE_STYLE: maplibregl.StyleSpecification = {
  version: 8,
  glyphs: "https://demotiles.maplibre.org/font/{fontstack}/{range}.pbf",
  sources: {
    basemap: {
      type: "raster",
      tiles: [
        "https://a.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png",
        "https://b.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png",
        "https://c.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png",
      ],
      tileSize: 256,
      attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> · © CARTO',
    },
  },
  layers: [
    { id: "bg", type: "background", paint: { "background-color": "#0d0f12" } },
    {
      id: "basemap",
      type: "raster",
      source: "basemap",
      paint: { "raster-opacity": 0.85, "raster-saturation": -0.2, "raster-brightness-max": 0.75 },
    },
  ],
};

const EMPTY_FC: GeoJsonFeatureCollection = { type: "FeatureCollection", features: [] };

export default function GisCanvas() {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const [ready, setReady] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [data, setData] = useState<GeoJsonFeatureCollection>(EMPTY_FC);
  const project = useWorkspace((s) => s.project);
  const points = useWorkspace((s) => s.points);
  const surface = useWorkspace((s) => s.surface);
  const layers = useWorkspace((s) => s.layers);
  const selectPoint = useWorkspace((s) => s.selectPoint);

  const me = useMemo(() => points, [points]);

  useEffect(() => {
    if (!project) return;
    let cancelled = false;
    api
      .geojson(project.id, surface?.output?.id ?? null)
      .then((collection) => {
        if (!cancelled) setData(collection);
      })
      .catch((err) => {
        if (!cancelled) setError((err as Error).message);
      });
    return () => {
      cancelled = true;
    };
  }, [project?.id, surface?.output?.id, me.length]);

  useEffect(() => {
    if (mapRef.current || !containerRef.current) return;
    const map = new maplibregl.Map({
      container: containerRef.current,
      style: BASE_STYLE,
      center: [4.66, 52.23],
      zoom: 15,
      attributionControl: { compact: true },
      maxPitch: 60,
    });
    mapRef.current = map;
    map.addControl(new maplibregl.NavigationControl({ visualizePitch: true }), "bottom-right");
    map.addControl(new maplibregl.ScaleControl({ unit: "metric" }), "bottom-left");
    map.on("load", () => setReady(true));
    map.on("error", (event) => {
      const message = (event as unknown as { error?: Error }).error?.message;
      if (message && !message.includes("tile")) setError(message);
    });
    return () => {
      map.remove();
      mapRef.current = null;
    };
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;

    const ensureSource = (id: string) => {
      if (!map.getSource(id)) {
        map.addSource(id, { type: "geojson", data: EMPTY_FC as never });
      }
    };
    ensureSource("points");
    ensureSource("linework");
    ensureSource("contours");
    ensureSource("boundary");

    (map.getSource("points") as maplibregl.GeoJSONSource).setData({
      type: "FeatureCollection",
      features: data.features.filter((f) => f.properties?.kind === "point"),
    } as never);
    (map.getSource("linework") as maplibregl.GeoJSONSource).setData({
      type: "FeatureCollection",
      features: data.features.filter((f) => f.properties?.kind === "linework"),
    } as never);
    (map.getSource("boundary") as maplibregl.GeoJSONSource).setData({
      type: "FeatureCollection",
      features: data.features.filter((f) => f.properties?.kind === "boundary"),
    } as never);
    (map.getSource("contours") as maplibregl.GeoJSONSource).setData({
      type: "FeatureCollection",
      features: data.features.filter((f) => f.properties?.kind === "contour"),
    } as never);

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
              `<div style="font-family:JetBrains Mono,monospace;font-size:11px;color:#E6EDF5">
                <b style="color:#38BDF8">${found.point_number}</b><br/>
                ${found.code || "—"} · Z ${found.elevation?.toFixed(3) ?? "—"}<br/>
                <span style="color:#8A94A6">${found.status}</span>
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
  }, [ready, data, layers, selectPoint]);

  return (
    <div className="absolute inset-0">
      <div ref={containerRef} className="absolute inset-0" />
      {error && (
        <div className="absolute top-3 left-3 panel px-2 py-1 text-[10px] text-amber bg-panel/95 max-w-xs">
          Basemap unavailable ({error}) — vector layers still active.
        </div>
      )}
      <div className="absolute top-3 right-3 panel bg-panel/90 px-2 py-1 text-[9px] font-mono text-muted text-right">
        <div>EPSG:4326 · Web GIS</div>
        <div>
          {data.features.filter((f) => f.properties?.kind === "point").length} pts ·{" "}
          {data.features.filter((f) => f.properties?.kind === "linework").length} lines
        </div>
      </div>
    </div>
  );
}
