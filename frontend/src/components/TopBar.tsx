import { useState } from "react";
import { NavLink, useNavigate } from "react-router-dom";
import {
  Activity,
  Code2,
  Download,
  FileSpreadsheet,
  FolderKanban,
  Layers,
  ShieldCheck,
  Upload,
} from "lucide-react";
import { api } from "../lib/api";
import { useWorkspace } from "../store/workspace";
import { Spinner, StatusBadge } from "./ui";

export default function TopBar() {
  const navigate = useNavigate();
  const project = useWorkspace((s) => s.project);
  const toast = useWorkspace((s) => s.toast);
  const [exportingDxf, setExportingDxf] = useState(false);
  const projectId = project?.id;

  const downloadDxf = async () => {
    if (!project) return;
    setExportingDxf(true);
    try {
      const { blob, filename } = await api.downloadDxf(project.id);
      const objectUrl = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = objectUrl;
      anchor.download = filename;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      window.setTimeout(() => URL.revokeObjectURL(objectUrl), 30_000);
      toast("success", "فایل DXF با موفقیت آمادهٔ دانلود شد.");
    } catch (error) {
      toast("error", `ساخت فایل DXF ناموفق بود: ${(error as Error).message}`);
    } finally {
      setExportingDxf(false);
    }
  };

  const nav = [
    { key: "workspace", label: "فضای کار", to: `/projects/${projectId}`, icon: Activity },
    { key: "import", label: "ورود داده", to: `/projects/${projectId}/import`, icon: Upload },
    { key: "codes", label: "کتابخانه کدها", to: `/projects/${projectId}/codes`, icon: Code2 },
    { key: "qa", label: "کنترل کیفیت", to: `/projects/${projectId}/qa`, icon: ShieldCheck },
  ];

  return (
    <header className="h-12 shrink-0 border-b border-edge bg-panel flex items-stretch">
      <button
        onClick={() => navigate("/")}
        className="px-4 flex items-center gap-2.5 border-e border-edge hover:bg-panel2 transition-colors"
        title="فهرست پروژه‌ها"
      >
        <svg viewBox="0 0 32 32" className="w-5 h-5">
          <path
            d="M5 24h22M16 5v19M8 12l8-6 8 6"
            stroke="#38BDF8"
            strokeWidth="2.4"
            fill="none"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
          <circle cx="16" cy="24" r="2.6" fill="#F472B6" />
        </svg>
        <span className="text-sm font-semibold tracking-tight">
          سروی<span className="text-cyan">پرو</span>
        </span>
        <span className="text-[9px] font-mono tracking-[0.12em] text-muted border border-edge rounded px-1 py-0.5">
          v1.0
        </span>
      </button>

      {project ? (
        <div className="flex-1 min-w-0 flex items-center">
          <div className="px-4 min-w-0 hidden lg:block">
            <div className="flex items-center gap-2 min-w-0">
              <span className="text-xs font-medium truncate max-w-[320px]">{project.name}</span>
              <StatusBadge status={project.dependency_state} />
            </div>
            <div className="flex items-center gap-2 text-[10px] text-muted font-mono mt-0.5">
              <span dir="ltr">EPSG:{project.crs_epsg}</span>
              <span className="text-edge">|</span>
              <span>{project.vertical_datum}</span>
              <span className="text-edge">|</span>
              <span>{project.linear_unit === "m" ? "متر" : project.linear_unit}</span>
              <span className="text-edge">|</span>
              <span>{project.angle_unit === "gon" ? "گرادیان" : "درجه"}</span>
            </div>
          </div>

          <nav className="flex items-stretch h-full">
            {nav.map(({ key, label, to, icon: Icon }) => (
              <NavLink
                key={key}
                to={to}
                end={key === "workspace"}
                className={({ isActive }) =>
                  `px-3 flex items-center gap-1.5 text-[11px] border-e border-edge transition-colors ${
                    isActive
                      ? "text-cyan bg-cyan/5 shadow-[inset_0_-2px_0_0_#38BDF8]"
                      : "text-muted hover:text-ink"
                  }`
                }
              >
                <Icon size={13} />
                <span className="hidden xl:inline">{label}</span>
              </NavLink>
            ))}
          </nav>

          <div className="topbar-actions ms-auto flex items-center gap-1.5 pe-3">
            <a
              className="btn-ghost"
              href={api.exportCsvUrl(project.id)}
              download
              title="خروجی CSV نقاط اعتبارسنجی‌شده و تأییدشده"
            >
              <FileSpreadsheet size={13} />
              <span className="hidden xl:inline">CSV</span>
            </a>
            <button
              className="btn-primary"
              onClick={() => void downloadDxf()}
              disabled={exportingDxf}
              title="ساخت و دانلود فایل DXF لایه‌بندی‌شده برای اتوکد"
            >
              {exportingDxf ? <Spinner /> : <Download size={13} />}
              <span className="hidden md:inline">{exportingDxf ? "در حال ساخت فایل…" : "خروجی DXF"}</span>
            </button>
          </div>
        </div>
      ) : (
        <div className="flex-1 flex items-center px-4 gap-2 text-[11px] text-muted">
          <FolderKanban size={13} />
          مرکز پروژه‌ها
          <span className="ms-auto flex items-center gap-1.5 text-[10px]">
            <Layers size={12} /> از برداشت تا نقشه · سطح مقید · احجام · DXF
          </span>
        </div>
      )}
    </header>
  );
}
