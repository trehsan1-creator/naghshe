import type { CrossSection, ProfileResult, VolumeResult } from "../lib/types";
import { fmt } from "./ui";

const W = 640;
const H = 190;
const PAD = { left: 44, right: 12, top: 12, bottom: 24 };

function niceTicks(min: number, max: number, count = 5): number[] {
  const span = max - min;
  if (span <= 0) return [min];
  const rawStep = span / count;
  const mag = Math.pow(10, Math.floor(Math.log10(rawStep)));
  const norm = rawStep / mag;
  const step = (norm >= 7.5 ? 10 : norm >= 3.5 ? 5 : norm >= 1.5 ? 2 : 1) * mag;
  const start = Math.ceil(min / step) * step;
  const ticks: number[] = [];
  for (let value = start; value <= max + step * 0.001; value += step) {
    ticks.push(Math.round(value * 1e6) / 1e6);
  }
  return ticks;
}

export function ProfileChart({ profile }: { profile: ProfileResult }) {
  const samples = profile.samples;
  const designKey = "0";
  const existing = samples.map((s) => s.offsets[designKey]?.elevation ?? null);
  const design = samples.map((s) => s.offsets[designKey]?.design_elevation ?? null);

  const values = [...existing, ...design].filter((v): v is number => v !== null);
  if (!samples.length || !values.length) {
    return <div className="p-3 text-[11px] text-muted">در امتداد مسیر نمونه‌ای وجود ندارد.</div>;
  }
  const zMin = Math.min(...values);
  const zMax = Math.max(...values);
  const pad = Math.max((zMax - zMin) * 0.12, 0.05);
  const yMin = zMin - pad;
  const yMax = zMax + pad;
  const xMax = profile.length_m || samples[samples.length - 1].station || 1;

  const sx = (station: number) => PAD.left + (station / xMax) * (W - PAD.left - PAD.right);
  const sy = (z: number) => H - PAD.bottom - ((z - yMin) / (yMax - yMin || 1)) * (H - PAD.top - PAD.bottom);

  const path = (series: (number | null)[]) => {
    let d = "";
    let drawing = false;
    series.forEach((value, index) => {
      if (value === null) {
        drawing = false;
        return;
      }
      const x = sx(samples[index].station);
      const y = sy(value);
      d += `${drawing ? "L" : "M"}${x.toFixed(1)},${y.toFixed(1)} `;
      drawing = true;
    });
    return d.trim();
  };

  const yTicks = niceTicks(yMin, yMax, 4);
  const xTicks = niceTicks(0, xMax, 6);
  const gain = ((H - PAD.top - PAD.bottom) / (yMax - yMin)) / ((W - PAD.left - PAD.right) / xMax);

  return (
    <div className="p-2">
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-auto" role="img" aria-label="نیمرخ طولی">
        <rect x={PAD.left} y={PAD.top} width={W - PAD.left - PAD.right} height={H - PAD.top - PAD.bottom} fill="#121417" />
        {yTicks.map((tick) => (
          <g key={`y${tick}`}>
            <line x1={PAD.left} x2={W - PAD.right} y1={sy(tick)} y2={sy(tick)} stroke="#252A33" strokeWidth={0.7} />
            <text x={PAD.left - 4} y={sy(tick) + 3} textAnchor="end" fontSize={8} fill="#8A94A6" fontFamily="monospace">
              {tick.toFixed(2)}
            </text>
          </g>
        ))}
        {xTicks.map((tick) => (
          <g key={`x${tick}`}>
            <line x1={sx(tick)} x2={sx(tick)} y1={PAD.top} y2={H - PAD.bottom} stroke="#1E232B" strokeWidth={0.6} />
            <text x={sx(tick)} y={H - PAD.bottom + 11} textAnchor="middle" fontSize={8} fill="#8A94A6" fontFamily="monospace">
              {tick.toFixed(0)}
            </text>
          </g>
        ))}
        <path d={path(existing)} fill="none" stroke="#38BDF8" strokeWidth={1.6} />
        {design.some((v) => v !== null) && (
          <path
            d={path(design)}
            fill="none"
            stroke="#F472B6"
            strokeWidth={1.5}
            strokeDasharray="5 3"
          />
        )}
        {samples.map((sample, index) =>
          existing[index] === null ? null : (
            <circle key={sample.station} cx={sx(sample.station)} cy={sy(existing[index] as number)} r={1.4} fill="#38BDF8" />
          ),
        )}
        <text x={PAD.left} y={H - 3} fontSize={8} fill="#8A94A6" fontFamily="monospace">
          station (m)
        </text>
        <text x={8} y={PAD.top + 6} fontSize={8} fill="#8A94A6" fontFamily="monospace">
          Z (m)
        </text>
      </svg>
      <div className="flex items-center gap-3 px-1 text-[9px] font-mono text-muted">
        <span className="flex items-center gap-1">
          <span className="w-3 h-[2px] bg-cyan inline-block" /> موجود
        </span>
        <span className="flex items-center gap-1">
          <span className="w-3 h-[2px] bg-pink inline-block" /> طرح
        </span>
        <span className="ms-auto">
          L {fmt(profile.length_m, 2)} m · Z {fmt(profile.min_elevation, 2)} → {fmt(profile.max_elevation, 2)} m ·
          x{(gain).toFixed(1)} v.e.
        </span>
      </div>
    </div>
  );
}

export function CrossSectionChart({ section, station }: { section: CrossSection; station: number }) {
  const width = 320;
  const height = 150;
  const pad = { left: 34, right: 8, top: 10, bottom: 18 };
  const pairs = section.offsets
    .map((offset, index) => ({ offset, z: section.elevations[index] }))
    .filter((p): p is { offset: number; z: number } => p.z !== null);

  if (pairs.length < 2) {
    return (
      <div className="panel p-2 text-[10px] text-muted">
        Section at {fmt(station, 1)} m — insufficient coverage.
      </div>
    );
  }

  const zMin = Math.min(...pairs.map((p) => p.z));
  const zMax = Math.max(...pairs.map((p) => p.z));
  const zPad = Math.max((zMax - zMin) * 0.25, 0.05);
  const xMin = Math.min(...pairs.map((p) => p.offset));
  const xMax = Math.max(...pairs.map((p) => p.offset));

  const sx = (offset: number) => pad.left + ((offset - xMin) / (xMax - xMin || 1)) * (width - pad.left - pad.right);
  const sy = (z: number) =>
    height - pad.bottom - ((z - (zMin - zPad)) / (zMax + zPad - (zMin - zPad) || 1)) * (height - pad.top - pad.bottom);

  return (
    <div className="panel">
      <div className="px-2 py-1 border-b border-edge/60 flex items-center text-[9px] font-mono text-muted">
        <span>STA {fmt(station, 1)} m</span>
        <span className="ms-auto">
          {xMin.toFixed(1)} … {xMax.toFixed(1)} m · ΔZ {fmt(zMax - zMin, 2)} m
        </span>
      </div>
      <svg viewBox={`0 0 ${width} ${height}`} className="w-full h-auto">
        <rect x={pad.left} y={pad.top} width={width - pad.left - pad.right} height={height - pad.top - pad.bottom} fill="#121417" />
        {niceTicks(zMin - zPad, zMax + zPad, 3).map((tick) => (
          <g key={tick}>
            <line
              x1={pad.left}
              x2={width - pad.right}
              y1={sy(tick)}
              y2={sy(tick)}
              stroke="#252A33"
              strokeWidth={0.6}
            />
            <text x={pad.left - 3} y={sy(tick) + 3} textAnchor="end" fontSize={7} fill="#8A94A6" fontFamily="monospace">
              {tick.toFixed(2)}
            </text>
          </g>
        ))}
        <line
          x1={sx(0)}
          x2={sx(0)}
          y1={pad.top}
          y2={height - pad.bottom}
          stroke="#F472B6"
          strokeWidth={0.7}
          strokeDasharray="3 2"
        />
        <path
          d={pairs.map((p, index) => `${index === 0 ? "M" : "L"}${sx(p.offset).toFixed(1)},${sy(p.z).toFixed(1)}`).join(" ")}
          fill="none"
          stroke="#38BDF8"
          strokeWidth={1.4}
        />
        <path
          d={`${pairs.map((p, index) => `${index === 0 ? "M" : "L"}${sx(p.offset).toFixed(1)},${sy(p.z).toFixed(1)}`).join(" ")} L${sx(xMax)},${height - pad.bottom} L${sx(xMin)},${height - pad.bottom} Z`}
          fill="#38BDF8"
          fillOpacity={0.07}
          stroke="none"
        />
        <text x={width / 2} y={height - 4} textAnchor="middle" fontSize={7} fill="#8A94A6" fontFamily="monospace">
          offset (m)
        </text>
      </svg>
    </div>
  );
}

export function VolumeBars({ volume }: { volume: VolumeResult }) {
  const total = volume.cut_m3 + volume.fill_m3 || 1;
  const rows = [
    { label: "خاک‌برداری", value: volume.cut_m3, color: "#A3E635" },
    { label: "خاک‌ریزی", value: volume.fill_m3, color: "#F472B6" },
  ];
  return (
    <div className="space-y-1.5">
      {rows.map((row) => (
        <div key={row.label} className="flex items-center gap-2 text-[10px] font-mono">
          <span className="w-8 text-muted">{row.label}</span>
          <div className="flex-1 h-2.5 rounded-sm bg-base border border-edge overflow-hidden">
            <div
              className="h-full"
              style={{ width: `${Math.max((row.value / total) * 100, 1)}%`, background: row.color }}
            />
          </div>
          <span className="w-20 text-end tabular" style={{ color: row.color }}>
            {fmt(row.value, 2)} m³
          </span>
        </div>
      ))}
      <div className="flex items-center justify-between text-[10px] font-mono border-t border-edge/60 pt-1.5">
        <span className="text-muted">Net ({volume.net_m3 >= 0 ? "مازاد خاک‌برداری" : "مازاد خاک‌ریزی"})</span>
        <span className={volume.net_m3 >= 0 ? "text-lime" : "text-pink"}>{fmt(volume.net_m3, 2)} m³</span>
      </div>
    </div>
  );
}
