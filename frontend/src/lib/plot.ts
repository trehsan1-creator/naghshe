/** Colour ramps, ACI translation and viewport fitting helpers. */

import type { CodeMapping, SurveyPoint } from "./types";

export type RGB = [number, number, number];
export type RGBA = [number, number, number, number];

/** AutoCAD Color Index for the first 9 standard colours. */
const ACI: Record<number, string> = {
  0: "#000000",
  1: "#FF4D4D",
  2: "#FFE066",
  3: "#7CE38B",
  4: "#4DD8E8",
  5: "#5B8DEF",
  6: "#E879F9",
  7: "#E6EDF5",
  8: "#8A94A6",
  9: "#C3CAD6",
  30: "#F472B6",
  40: "#FBBF24",
  140: "#38BDF8",
  150: "#A3E635",
};

export function aciToHex(color: number): string {
  return ACI[color] ?? ACI[7];
}

export function hexToRgb(hex: string): RGB {
  const value = hex.replace("#", "");
  const n = parseInt(value.length === 3 ? value.replace(/(.)/g, "$1$1") : value, 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

export function withAlpha(rgb: RGB, alpha: number): RGBA {
  return [rgb[0], rgb[1], rgb[2], Math.round(alpha * 255)];
}

const FALLBACK_RAMP: string[] = [
  "#38BDF8",
  "#F472B6",
  "#A3E635",
  "#FBBF24",
  "#818CF8",
  "#2DD4BF",
  "#FB923C",
  "#E879F9",
  "#60A5FA",
  "#34D399",
];

function hashString(value: string): number {
  let h = 2166136261;
  for (let i = 0; i < value.length; i += 1) {
    h ^= value.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return Math.abs(h);
}

/** Colour for a field code: code library first, deterministic hash otherwise. */
export function codeColor(code: string, mappings: CodeMapping[] = []): string {
  const upper = (code || "?").toUpperCase();
  const direct = mappings.find((m) => m.code.toUpperCase() === upper);
  if (direct) return aciToHex(direct.color);
  const base = upper.split(/[ _-]/)[0];
  const byBase = mappings.find((m) => m.code.toUpperCase() === base);
  if (byBase) return aciToHex(byBase.color);
  return FALLBACK_RAMP[hashString(upper) % FALLBACK_RAMP.length];
}

export const STATUS_HEX: Record<string, string> = {
  RAW: "#8A94A6",
  VALIDATED: "#38BDF8",
  APPROVED: "#A3E635",
  REJECTED: "#F87171",
};

export const LAYER_HEX: Record<string, string> = {
  "S-POINT": "#8A94A6",
  "S-ELEV": "#A3E635",
  "S-CURB": "#F472B6",
  "S-SIDEWALK": "#38BDF8",
  "S-ROAD": "#FBBF24",
  "S-CONTOUR-MAJOR": "#E879F9",
  "S-CONTOUR-MINOR": "#6B7A8C",
  "S-BOUNDARY": "#38BDF8",
  "S-TREE": "#34D399",
  "S-UTILITY": "#FB923C",
  "S-CENTRELINE": "#FBBF24",
  "S-BREAKLINE": "#F472B6",
};

export function layerHex(layer: string, mappings: CodeMapping[] = []): string {
  if (LAYER_HEX[layer]) return LAYER_HEX[layer];
  const mapped = mappings.find((m) => m.layer === layer);
  if (mapped) return aciToHex(mapped.color);
  return FALLBACK_RAMP[hashString(layer) % FALLBACK_RAMP.length];
}

const RAMP_STOPS: { t: number; rgb: RGB }[] = [
  { t: 0.0, rgb: [56, 130, 246] },
  { t: 0.25, rgb: [56, 189, 248] },
  { t: 0.5, rgb: [163, 230, 53] },
  { t: 0.75, rgb: [251, 191, 36] },
  { t: 1.0, rgb: [244, 114, 182] },
];

/** Hypsometric elevation ramp (blue → cyan → lime → amber → pink). */
export function elevationColor(z: number, min: number, max: number): RGB {
  const span = max - min || 1;
  const t = Math.min(1, Math.max(0, (z - min) / span));
  for (let i = 1; i < RAMP_STOPS.length; i += 1) {
    const a = RAMP_STOPS[i - 1];
    const b = RAMP_STOPS[i];
    if (t <= b.t) {
      const k = (t - a.t) / (b.t - a.t || 1);
      return [
        Math.round(a.rgb[0] + (b.rgb[0] - a.rgb[0]) * k),
        Math.round(a.rgb[1] + (b.rgb[1] - a.rgb[1]) * k),
        Math.round(a.rgb[2] + (b.rgb[2] - a.rgb[2]) * k),
      ];
    }
  }
  return RAMP_STOPS[RAMP_STOPS.length - 1].rgb;
}

export interface Extent {
  minX: number;
  maxX: number;
  minY: number;
  maxY: number;
  minZ: number;
  maxZ: number;
}

export function extentOfPoints(points: SurveyPoint[]): Extent | null {
  if (!points.length) return null;
  let minX = Infinity;
  let maxX = -Infinity;
  let minY = Infinity;
  let maxY = -Infinity;
  let minZ = Infinity;
  let maxZ = -Infinity;
  for (const p of points) {
    minX = Math.min(minX, p.easting);
    maxX = Math.max(maxX, p.easting);
    minY = Math.min(minY, p.northing);
    maxY = Math.max(maxY, p.northing);
    if (p.elevation !== null && p.elevation !== undefined) {
      minZ = Math.min(minZ, p.elevation);
      maxZ = Math.max(maxZ, p.elevation);
    }
  }
  if (!Number.isFinite(minZ)) {
    minZ = 0;
    maxZ = 1;
  }
  return { minX, maxX, minY, maxY, minZ, maxZ };
}

/** Zoom that makes the extent fill a viewport of the given pixel size. */
export function fitOrthoZoom(extent: Extent, width: number, height: number, padding = 0.86) {
  const spanX = Math.max(extent.maxX - extent.minX, 1e-6);
  const spanY = Math.max(extent.maxY - extent.minY, 1e-6);
  const zoomX = Math.log2((Math.max(width, 1) * padding) / spanX);
  const zoomY = Math.log2((Math.max(height, 1) * padding) / spanY);
  return Math.min(zoomX, zoomY);
}

export function centroid(extent: Extent): [number, number] {
  return [(extent.minX + extent.maxX) / 2, (extent.minY + extent.maxY) / 2];
}

export function metersPerPixel(zoom: number) {
  return 1 / Math.pow(2, zoom);
}

/** Format a numeric table cell with sensible precision. */
export function num(value: unknown, digits = 3): string {
  if (value === null || value === undefined || value === "") return "—";
  const n = typeof value === "number" ? value : Number(value);
  if (Number.isNaN(n)) return String(value);
  if (Number.isInteger(n) && Math.abs(n) < 1e6) return String(n);
  return n.toFixed(digits);
}
