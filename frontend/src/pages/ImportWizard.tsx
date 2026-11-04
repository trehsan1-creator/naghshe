import { useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  FileText,
  Info,
  RefreshCw,
  ShieldCheck,
  UploadCloud,
  Wand2,
} from "lucide-react";
import { useWorkspace } from "../store/workspace";
import { Panel, SeverityDot, Spinner, StatusBadge, fmt, fmtInt } from "../components/ui";
import type { ColumnMapping, Issue, PointStatus, QaFlag } from "../lib/types";

type Role = "point_number" | "easting" | "northing" | "elevation" | "code" | "description";

const ROLES: { key: Role; label: string; required?: boolean }[] = [
  { key: "point_number", label: "شماره نقطه", required: true },
  { key: "easting", label: "مختصات شرقی (X)", required: true },
  { key: "northing", label: "مختصات شمالی (Y)", required: true },
  { key: "elevation", label: "ارتفاع (Z)" },
  { key: "code", label: "کد برداشت" },
  { key: "description", label: "شرح" },
];

export default function ImportWizard() {
  const navigate = useNavigate();
  const project = useWorkspace((s) => s.project);
  const upload = useWorkspace((s) => s.upload);
  const analysis = useWorkspace((s) => s.analysis);
  const mapping = useWorkspace((s) => s.mapping);
  const startUpload = useWorkspace((s) => s.startUpload);
  const remap = useWorkspace((s) => s.remap);
  const commitImport = useWorkspace((s) => s.commitImport);
  const resetImport = useWorkspace((s) => s.resetImport);
  const busy = useWorkspace((s) => s.busy);
  const fileInput = useRef<HTMLInputElement | null>(null);
  const [dragging, setDragging] = useState(false);
  const [commitStatus, setCommitStatus] = useState<PointStatus>("VALIDATED");
  const [swapXy, setSwapXy] = useState(false);
  const [duplicatePolicy, setDuplicatePolicy] = useState<"skip" | "replace">("skip");

  const roleOf = (index: number): Role | "ignore" => {
    if (!mapping) return "ignore";
    for (const role of ROLES) {
      if (mapping[role.key] === index) return role.key;
    }
    return "ignore";
  };

  const assign = (index: number, role: Role | "ignore") => {
    const next: Record<string, number | null | boolean | string> = { ...(mapping ?? {}) };
    if (role === "ignore") {
      for (const key of Object.keys(next)) {
        if (next[key] === index) next[key] = null;
      }
    } else {
      for (const key of Object.keys(next)) {
        if (next[key] === index && key !== role) next[key] = null;
      }
      next[role] = index;
    }
    void remap(next);
  };

  const mappingReady = Boolean(
    mapping && mapping.easting !== null && mapping.northing !== null && mapping.point_number !== null,
  );

  const issueList: Issue[] = useMemo(
    () => [...(analysis?.parse_issues ?? []), ...(analysis?.issues ?? [])],
    [analysis],
  );

  const flags: QaFlag[] = analysis?.qa?.flags ?? [];
  const severityCounts = flags.reduce<Record<string, number>>((acc, flag) => {
    acc[flag.severity] = (acc[flag.severity] ?? 0) + 1;
    return acc;
  }, {});

  const handleFiles = async (files: FileList | null) => {
    const file = files?.[0];
    if (!file) return;
    await startUpload(file);
  };

  return (
    <div className="h-full overflow-auto">
      <div className="max-w-[1500px] mx-auto p-4 space-y-3">
        <div className="flex items-end gap-3">
          <div>
            <div className="text-[10px] uppercase tracking-[0.2em] text-cyan/80">گام ۱ · ورود داده</div>
            <h1 className="text-lg font-semibold tracking-tight mt-0.5">ورود داده‌های برداشت</h1>
            <p className="text-[11px] text-muted mt-1">
              فایل‌های TXT/CSV توتال‌استیشن با تشخیص خودکار کدگذاری، جداکننده و ستون‌ها؛ همچنین خروجی Leica GSI-8/16 با تبدیل مختصات قطبی به قائم.
            </p>
          </div>
          <div className="ms-auto flex items-center gap-2">
            {upload && (
              <button
                className="btn"
                onClick={() => {
                  resetImport();
                  setSwapXy(false);
                }}
              >
                <RefreshCw size={12} /> شروع مجدد
              </button>
            )}
            <button className="btn" onClick={() => navigate(`/projects/${project?.id}`)}>
              فضای کار <ArrowRight size={12} />
            </button>
          </div>
        </div>

        {!upload && (
          <div
            className={`panel border-dashed p-10 flex flex-col items-center gap-3 transition-colors ${
              dragging ? "border-cyan bg-cyan/5" : ""
            }`}
            onDragOver={(event) => {
              event.preventDefault();
              setDragging(true);
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={(event) => {
              event.preventDefault();
              setDragging(false);
              void handleFiles(event.dataTransfer.files);
            }}
          >
            <UploadCloud size={30} className="text-cyan/80" />
            <div className="text-sm">فایل برداشت را اینجا رها کنید</div>
            <div className="text-[11px] text-muted">
              .txt · .csv · .dat · .gsi — up to 25 MB, raw bytes are stored unmodified
            </div>
            <input
              ref={fileInput}
              type="file"
              className="hidden"
              accept=".txt,.csv,.dat,.gsi,.xyz,.asc"
              onChange={(event) => void handleFiles(event.target.files)}
            />
            <button className="btn-primary mt-1" onClick={() => fileInput.current?.click()} disabled={Boolean(busy)}>
              {busy ? <Spinner /> : <FileText size={13} />} انتخاب فایل
            </button>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-2 mt-4 w-full max-w-3xl">
              {[
                ["TXT · CSV", "Whitespace, comma, semicolon, tab or pipe delimited; سرستون detection."],
                ["Leica GSI", "بلوک‌های GSI-8 و GSI-16، ایستگاه و هدف، زاویه برحسب گرادیان یا درجه."],
                ["کنترل کیفیت هنگام ورود", "جابه‌جایی محورها، نقاط تکراری، داده‌های پرت ارتفاع و کدهای ناشناخته پیش از ثبت مشخص می‌شوند."],
              ].map(([title, note]) => (
                <div key={title} className="panel bg-panel2/50 p-2.5">
                  <div className="text-[10px] uppercase tracking-[0.12em] text-cyan">{title}</div>
                  <div className="text-[10px] text-muted mt-1 leading-relaxed">{note}</div>
                </div>
              ))}
            </div>
            {busy && <div className="text-[10px] font-mono text-cyan mt-1 flex items-center gap-2"><Spinner /> {busy}</div>}
          </div>
        )}

        {upload && analysis && (
          <>
            <div className="grid grid-cols-1 xl:grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)] gap-3">
              <Panel title="قالب شناسایی‌شده" icon={<Wand2 size={12} />}>
                <div className="p-2.5 grid grid-cols-2 md:grid-cols-3 gap-1.5 text-[10px] font-mono">
                  {[
                    ["فایل", upload.file.original_filename],
                    ["قالب", analysis.format],
                    ["کدگذاری", analysis.encoding],
                    ["جداکننده", analysis.delimiter_label ?? analysis.delimiter ?? "—"],
                    ["سرستون", analysis.header_detected ? analysis.header_tokens.join(" ") || "yes" : "none"],
                    ["ردیف‌ها", fmtInt(analysis.row_count)],
                    ["فیلد در هر ردیف", String(analysis.token_count_mode ?? "—")],
                    ["حجم فایل", `${(upload.file.size_bytes / 1024).toFixed(1)} kB`],
                    ["هش SHA-256", `${upload.file.sha256.slice(0, 12)}…`],
                  ].map(([label, value]) => (
                    <div key={label} className="bg-panel2/60 border border-edge/70 rounded px-2 py-1">
                      <div className="text-[9px] uppercase tracking-[0.1em] text-muted">{label}</div>
                      <div className="text-ink/90 truncate" title={String(value)}>
                        {value}
                      </div>
                    </div>
                  ))}
                </div>
                {analysis.encoding_notes.length > 0 && (
                  <div className="px-2.5 pb-2 text-[10px] text-muted leading-relaxed">
                    {analysis.encoding_notes.map((note) => (
                      <div key={note} className="flex gap-1.5">
                        <Info size={10} className="mt-[2px] shrink-0 text-cyan/70" /> {note}
                      </div>
                    ))}
                  </div>
                )}
              </Panel>

              <Panel
                title="نگاشت ستون‌ها"
                icon={<ShieldCheck size={12} />}
                right={
                  <span className={`text-[9px] font-mono ${mappingReady ? "text-lime" : "text-amber"}`}>
                    {mappingReady ? "نگاشت کامل است" : "ستون‌های X، Y و شناسهٔ نقطه را تعیین کنید"}
                  </span>
                }
              >
                <div className="max-h-[240px] overflow-auto">
                  <table className="w-full text-[10px]">
                    <thead className="sticky top-0 bg-panel2">
                      <tr className="text-[9px] uppercase tracking-[0.1em] text-muted">
                        <th className="text-start font-normal px-2 py-1">#</th>
                        <th className="text-start font-normal px-2 py-1">نمونه</th>
                        <th className="text-start font-normal px-2 py-1">نوع داده</th>
                        <th className="text-start font-normal px-2 py-1 w-32">نقش</th>
                        <th className="text-start font-normal px-2 py-1 w-16">اطمینان</th>
                      </tr>
                    </thead>
                    <tbody>
                      {analysis.columns.map((column) => {
                        const role = roleOf(column.index);
                        const confidence = role !== "ignore" ? analysis.confidence[role] ?? 0 : 0;
                        return (
                          <tr key={column.index} className="border-t border-edge/40">
                            <td className="px-2 py-[3px] font-mono text-muted">{column.index}</td>
                            <td className="px-2 py-[3px] font-mono text-ink/90 truncate max-w-[110px]">
                              {column.header || column.sample.slice(0, 3).join(" ")}
                            </td>
                            <td className="px-2 py-[3px] text-muted whitespace-nowrap">
                              {column.numeric_ratio > 0.9
                                ? column.integer_ratio > 0.9
                                  ? "integer"
                                  : `numeric ·${column.mean_decimals.toFixed(0)}dp`
                                : "text"}
                              {column.min !== null && column.max !== null && column.numeric_ratio > 0.9 && (
                                <span className="text-muted/60">
                                  {" "}
                                  {Math.round(column.min ?? 0)}–{Math.round(column.max ?? 0)}
                                </span>
                              )}
                            </td>
                            <td className="px-2 py-[3px]">
                              <select
                                className="field !h-5 !text-[10px] !px-1"
                                value={role}
                                onChange={(event) => assign(column.index, event.target.value as Role | "ignore")}
                              >
                                <option value="ignore">— نادیده‌گرفتن —</option>
                                {ROLES.map((r) => (
                                  <option key={r.key} value={r.key}>
                                    {r.label}
                                  </option>
                                ))}
                              </select>
                            </td>
                            <td className="px-2 py-[3px]">
                              <div className="flex items-center gap-1">
                                <div className="w-8 h-1 rounded bg-edge overflow-hidden">
                                  <div
                                    className={`h-full ${confidence > 0.7 ? "bg-lime" : confidence > 0.4 ? "bg-amber" : "bg-danger"}`}
                                    style={{ width: `${Math.round(confidence * 100)}%` }}
                                  />
                                </div>
                                <span className="font-mono text-[9px] text-muted">
                                  {Math.round(confidence * 100)}
                                </span>
                              </div>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
                <div className="flex items-center gap-2 px-2.5 py-2 border-t border-edge">
                  <label className="flex items-center gap-1.5 text-[10px] text-muted">
                    <input
                      type="checkbox"
                      className="accent-cyan"
                      checked={swapXy}
                      onChange={(event) => {
                        setSwapXy(event.target.checked);
                        const next = {
                          ...(mapping ?? {}),
                          easting: mapping?.northing ?? null,
                          northing: mapping?.easting ?? null,
                        } as Record<string, number | null | boolean | string>;
                        void remap(next);
                      }}
                    />
                    swap X ⇄ Y
                  </label>
                  <span className="text-[9px] text-muted font-mono ms-auto">
                    {analysis.points.length} parsed
                    {analysis.preview_truncated ? " (پیش‌نمایش کوتاه شده)" : ""}
                  </span>
                </div>
              </Panel>
            </div>

            <div className="grid grid-cols-1 xl:grid-cols-[minmax(0,1.35fr)_minmax(0,1fr)] gap-3">
              <Panel
                title="پیش‌نمایش"
                icon={<FileText size={12} />}
                right={<span className="text-[9px] font-mono text-muted">{fmtInt(analysis.points.length)} ردیف‌ها</span>}
              >
                <div className="max-h-[300px] overflow-auto">
                  <table className="w-full text-[10px]">
                    <thead className="sticky top-0 bg-panel2 z-10">
                      <tr className="text-[9px] uppercase tracking-[0.1em] text-muted">
                        <th className="text-start font-normal px-2 py-1">نقطه</th>
                        <th className="text-start font-normal px-2 py-1">کد</th>
                        <th className="text-end font-normal px-2 py-1">X</th>
                        <th className="text-end font-normal px-2 py-1">Y</th>
                        <th className="text-end font-normal px-2 py-1">Z</th>
                        <th className="text-start font-normal px-2 py-1">کیفیت</th>
                      </tr>
                    </thead>
                    <tbody>
                      {analysis.points.slice(0, 200).map((point) => {
                        const severity = analysis.qa?.point_severity?.[point.point_number];
                        return (
                          <tr key={`${point.point_number}-${point.line_no}`} className="border-t border-edge/40 font-mono">
                            <td className="px-2 py-[2px] text-ink/90">{point.point_number}</td>
                            <td className="px-2 py-[2px] text-cyan/90">{point.code || "—"}</td>
                            <td className="px-2 py-[2px] text-end tabular">{fmt(point.easting)}</td>
                            <td className="px-2 py-[2px] text-end tabular">{fmt(point.northing)}</td>
                            <td className="px-2 py-[2px] text-end tabular">{fmt(point.elevation)}</td>
                            <td className="px-2 py-[2px]">
                              <SeverityDot severity={severity} />
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </Panel>

              <div className="space-y-3 min-w-0">
                <Panel
                  title="هشدارهای کنترل کیفیت"
                  icon={<AlertTriangle size={12} />}
                  right={
                    <span className="text-[9px] font-mono">
                      <span className="text-danger">{severityCounts.error ?? 0} خطا</span>
                      {" · "}
                      <span className="text-amber">{severityCounts.warning ?? 0} هشدار</span>
                      {" · "}
                      <span className="text-muted">{severityCounts.info ?? 0} info</span>
                    </span>
                  }
                >
                  <ul className="divide-y divide-edge/50 max-h-[190px] overflow-auto">
                    {flags.map((flag, index) => (
                      <li key={`${flag.code}-${index}`} className="px-2.5 py-1.5">
                        <div className="flex items-center gap-1.5">
                          <SeverityDot severity={flag.severity} />
                          <span className="text-[10px] font-mono uppercase text-ink/80">{flag.code}</span>
                          <span className={`ms-auto text-[9px] font-mono sev-${flag.severity}`}>{flag.severity}</span>
                        </div>
                        <div className="text-[10px] text-muted leading-relaxed mt-0.5">{flag.message}</div>
                        {flag.point_numbers.length > 0 && (
                          <div className="text-[9px] font-mono text-muted/70 truncate mt-0.5">
                            pts: {flag.point_numbers.slice(0, 24).join(" ")}
                            {flag.point_numbers.length > 24 ? ` +${flag.point_numbers.length - 24}` : ""}
                          </div>
                        )}
                        {flag.suggestion && (
                          <div className="text-[9px] text-cyan/80 mt-0.5">→ {flag.suggestion}</div>
                        )}
                      </li>
                    ))}
                    {flags.length === 0 && (
                      <li className="px-2.5 py-2 text-[10px] text-lime flex items-center gap-1.5">
                        <CheckCircle2 size={11} /> در این پیش‌نمایش موردی برای کنترل کیفیت یافت نشد.
                      </li>
                    )}
                  </ul>
                  {issueList.length > 0 && (
                    <div className="px-2.5 py-1.5 border-t border-edge text-[9px] text-muted">
                      {issueList.length} یادداشت تجزیه: {issueList.slice(0, 2).map((issue) => issue.code).join(", ")}
                    </div>
                  )}
                </Panel>

                <Panel title="ثبت داده‌ها" icon={<ShieldCheck size={12} />}>
                  <div className="p-2.5 space-y-2">
                    <div className="grid grid-cols-2 gap-2">
                      <div>
                        <label className="label">وضعیت اولیه</label>
                        <select
                          className="field !h-7 !text-[10px]"
                          value={commitStatus}
                          onChange={(event) => setCommitStatus(event.target.value as PointStatus)}
                        >
                          <option value="RAW">خام — دادهٔ ورودی بررسی‌نشده</option>
                          <option value="VALIDATED">اعتبارسنجی‌شده — کنترل کیفیت انجام شده</option>
                          <option value="APPROVED">تأییدشده — تأیید نهایی</option>
                        </select>
                      </div>
                      <div>
                        <label className="label">شماره‌های تکراری نقاط</label>
                        <select
                          className="field !h-7 !text-[10px]"
                          value={duplicatePolicy}
                          onChange={(event) => setDuplicatePolicy(event.target.value as "skip" | "replace")}
                        >
                          <option value="skip">ردکردن نقاط تکراری</option>
                          <option value="replace">جایگزینی موارد موجود</option>
                        </select>
                      </div>
                    </div>
                    <div className="grid grid-cols-3 gap-1.5 text-[9px] font-mono">
                      {[
                        ["parsed", String(analysis.stats.parsed ?? analysis.points.length)],
                        ["skipped", String(analysis.stats.skipped ?? 0)],
                        ["dupes", String(analysis.stats.duplicate_point_numbers ?? 0)],
                        ["همراه با Z", String(analysis.stats.with_elevation ?? "—")],
                        ["codes", String(analysis.qa?.summary?.unique_codes ?? "—")],
                        ["hull m²", fmt(analysis.qa?.summary?.convex_hull_area_m2 ?? null, 1)],
                      ].map(([label, value]) => (
                        <div key={label} className="bg-panel2/60 border border-edge/70 rounded px-1.5 py-1">
                          <div className="text-[8px] uppercase tracking-[0.1em] text-muted">{label}</div>
                          <div className="text-ink/90">{value}</div>
                        </div>
                      ))}
                    </div>
                    <button
                      className="btn-primary w-full"
                      disabled={!mappingReady || Boolean(busy)}
                      onClick={async () => {
                        const ok = await commitImport(commitStatus, swapXy, duplicatePolicy === "replace");
                        if (ok) navigate(`/projects/${project?.id}`);
                      }}
                    >
                      {busy ? <Spinner /> : <CheckCircle2 size={13} />} ثبت {fmtInt(analysis.points.length)} نقطه
                    </button>
                    <div className="text-[9px] text-muted leading-relaxed">
                      با ثبت writes the point database and re-runs QA/QC. The original upload stays
                      و بایت‌به‌بایت در <span className="font-mono text-muted/80">project_files</span> همراه با
                      هش SHA-256 آن نگهداری می‌شود.
                    </div>
                  </div>
                </Panel>
              </div>
            </div>

            <Panel title="فایل‌های واردشدهٔ پیشین" icon={<FileText size={12} />}>
              <ul className="divide-y divide-edge/50">
                {(project?.files ?? []).map((file) => (
                  <li key={file.id} className="px-2.5 py-1.5 flex items-center gap-2 text-[10px]">
                    <FileText size={11} className="text-muted" />
                    <span className="font-mono text-ink/90 truncate">{file.original_filename}</span>
                    <StatusBadge status={file.status} />
                    <span className="text-muted font-mono">{fmtInt(file.row_count)} ردیف‌ها</span>
                    <span className="text-muted font-mono ms-auto">{fmtInt(file.imported_points)} pts</span>
                  </li>
                ))}
                {(project?.files ?? []).length === 0 && (
                  <li className="px-2.5 py-2 text-[10px] text-muted">هنوز فایلی وارد نشده است.</li>
                )}
              </ul>
            </Panel>
          </>
        )}

        {upload && !analysis && (
          <div className="panel p-6 text-[11px] text-muted flex items-center gap-2">
            <Spinner /> در حال پردازش {upload.file.original_filename}…
          </div>
        )}
      </div>
    </div>
  );
}

export type { ColumnMapping };
