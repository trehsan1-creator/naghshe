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
import { StatusBadge } from "./ui";

const NAV_ICONS = {
  workspace: Activity,
  import: Upload,
  codes: Code2,
  qa: ShieldCheck,
};

export default function TopBar() {
  const navigate = useNavigate();
  const project = useWorkspace((s) => s.project);
  const projectId = project?.id;

  const nav = [
    { key: "workspace", label: "Workspace", to: `/projects/${projectId}`, icon: NAV_ICONS.workspace },
    { key: "import", label: "Import", to: `/projects/${projectId}/import`, icon: NAV_ICONS.import },
    { key: "codes", label: "Code library", to: `/projects/${projectId}/codes`, icon: NAV_ICONS.codes },
    { key: "qa", label: "QA/QC", to: `/projects/${projectId}/qa`, icon: NAV_ICONS.qa },
  ];

  return (
    <header className="h-12 shrink-0 border-b border-edge bg-panel flex items-stretch">
      <button
        onClick={() => navigate("/")}
        className="px-4 flex items-center gap-2.5 border-r border-edge hover:bg-panel2 transition-colors"
        title="All projects"
      >
        <svg viewBox="0 0 32 32" className="w-5 h-5">
          <path d="M5 24h22M16 5v19M8 12l8-6 8 6" stroke="#38BDF8" strokeWidth="2.4" fill="none" strokeLinecap="round" strokeLinejoin="round" />
          <circle cx="16" cy="24" r="2.6" fill="#F472B6" />
        </svg>
        <span className="text-sm font-semibold tracking-tight">
          Survey<span className="text-cyan">Pro</span>
        </span>
        <span className="text-[9px] font-mono uppercase tracking-[0.18em] text-muted border border-edge rounded px-1 py-0.5">
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
              <span>EPSG:{project.crs_epsg}</span>
              <span className="text-edge">|</span>
              <span>{project.vertical_datum}</span>
              <span className="text-edge">|</span>
              <span>{project.linear_unit}</span>
              <span className="text-edge">|</span>
              <span>{project.angle_unit}</span>
            </div>
          </div>

          <nav className="flex items-stretch h-full">
            {nav.map(({ key, label, to, icon: Icon }) => (
              <NavLink
                key={key}
                to={to}
                end={key === "workspace"}
                className={({ isActive }) =>
                  `px-3 flex items-center gap-1.5 text-[11px] uppercase tracking-[0.1em] border-r border-edge transition-colors ${
                    isActive ? "text-cyan bg-cyan/5 shadow-[inset_0_-2px_0_0_#38BDF8]" : "text-muted hover:text-ink"
                  }`
                }
              >
                <Icon size={13} />
                <span className="hidden xl:inline">{label}</span>
              </NavLink>
            ))}
          </nav>

          <div className="ml-auto flex items-center gap-1.5 pr-3">
            <a
              className="btn-ghost"
              href={api.exportCsvUrl(project.id)}
              download
              title="Export validated/approved points as CSV"
            >
              <FileSpreadsheet size={13} />
              <span className="hidden xl:inline">CSV</span>
            </a>
            <button
              className="btn-primary"
              onClick={() => window.open(api.exportDxfUrl(project.id), "_blank")}
              title="One-click layered DXF deliverable"
            >
              <Download size={13} />
              <span className="hidden md:inline">DXF</span>
            </button>
          </div>
        </div>
      ) : (
        <div className="flex-1 flex items-center px-4 gap-2 text-[11px] uppercase tracking-[0.14em] text-muted">
          <FolderKanban size={13} />
          Project hub
          <span className="ml-auto flex items-center gap-1.5 text-[10px] normal-case tracking-normal">
            <Layers size={12} /> field-to-finish · TIN · volumes · DXF
          </span>
        </div>
      )}
    </header>
  );
}
