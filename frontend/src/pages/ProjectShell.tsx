import { useEffect } from "react";
import { NavLink, Outlet, useNavigate, useParams } from "react-router-dom";
import { Activity, ArrowLeft, Code2, ShieldCheck, Upload } from "lucide-react";
import { api } from "../lib/api";
import { useWorkspace } from "../store/workspace";
import { Spinner } from "../components/ui";

export default function ProjectShell() {
  const { projectId } = useParams<{ projectId: string }>();
  const navigate = useNavigate();
  const project = useWorkspace((s) => s.project);
  const openProject = useWorkspace((s) => s.openProject);
  const toast = useWorkspace((s) => s.toast);

  useEffect(() => {
    if (!projectId) return;
    if (project?.id === projectId) return;
    openProject(projectId).catch((error) => {
      toast("error", `Could not open project: ${(error as Error).message}`);
      navigate("/");
    });
  }, [projectId, project?.id, openProject, toast, navigate]);

  // Warm the CRS cache so the shell can show the datum immediately.
  useEffect(() => {
    if (projectId && project?.id !== projectId) {
      api.getProject(projectId).catch(() => undefined);
    }
  }, [projectId, project?.id]);

  if (!project || project.id !== projectId) {
    return (
      <div className="h-full flex items-center justify-center gap-2 text-xs text-muted">
        <Spinner /> Loading project workspace…
      </div>
    );
  }

  const rail = [
    { to: `/projects/${project.id}`, label: "Canvas", icon: Activity, end: true },
    { to: `/projects/${project.id}/import`, label: "Import", icon: Upload, end: false },
    { to: `/projects/${project.id}/codes`, label: "Codes", icon: Code2, end: false },
    { to: `/projects/${project.id}/qa`, label: "QA/QC", icon: ShieldCheck, end: false },
  ];

  return (
    <div className="h-full flex min-h-0">
      <aside className="w-12 shrink-0 border-r border-edge bg-panel flex flex-col items-center py-2 gap-1">
        <button
          className="w-9 h-9 rounded flex items-center justify-center text-muted hover:text-cyan hover:bg-panel2 transition-colors"
          onClick={() => navigate("/")}
          title="Back to project hub"
        >
          <ArrowLeft size={15} />
        </button>
        <div className="w-6 h-px bg-edge my-1" />
        {rail.map(({ to, label, icon: Icon, end }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            title={label}
            className={({ isActive }) =>
              `w-9 h-9 rounded flex items-center justify-center transition-colors ${
                isActive ? "bg-cyan/10 text-cyan" : "text-muted hover:text-ink hover:bg-panel2"
              }`
            }
          >
            <Icon size={16} />
          </NavLink>
        ))}
      </aside>
      <div className="flex-1 min-w-0 min-h-0">
        <Outlet />
      </div>
    </div>
  );
}
