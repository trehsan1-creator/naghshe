import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  ArrowRight,
  Boxes,
  Database,
  FileStack,
  FolderPlus,
  MapPin,
  Mountain,
  Plus,
  Ruler,
  Satellite,
  Trash2,
  UploadCloud,
} from "lucide-react";
import { api } from "../lib/api";
import { useWorkspace } from "../store/workspace";
import { Modal, Panel, StatusBadge, fmtInt, Spinner } from "../components/ui";
import type { Project } from "../lib/types";

const CRS_CHOICES = [
  { epsg: 28992, label: "EPSG:28992 — RD New / NAP (Netherlands)" },
  { epsg: 25831, label: "EPSG:25831 — ETRS89 / UTM 31N" },
  { epsg: 32631, label: "EPSG:32631 — WGS 84 / UTM 31N" },
  { epsg: 27700, label: "EPSG:27700 — OSGB36 / British National Grid" },
  { epsg: 2056, label: "EPSG:2056 — CH1903+ / LV95 (Switzerland)" },
  { epsg: 3857, label: "EPSG:3857 — Web Mercator" },
  { epsg: 4326, label: "EPSG:4326 — WGS 84 geographic" },
];

const PIPELINE = [
  { label: "RAW", note: "immutable uploads", tone: "text-muted" },
  { label: "VALIDATED", note: "QA/QC passed", tone: "text-cyan" },
  { label: "APPROVED", note: "signed off", tone: "text-lime" },
  { label: "TIN · CONTOURS", note: "CDT + breaklines", tone: "text-pink" },
  { label: "VOLUMES · PROFILE", note: "cut & fill", tone: "text-amber" },
  { label: "DXF", note: "CAD deliverable", tone: "text-ink" },
];

export default function Dashboard() {
  const navigate = useNavigate();
  const projects = useWorkspace((s) => s.projects);
  const loadProjects = useWorkspace((s) => s.loadProjects);
  const toast = useWorkspace((s) => s.toast);
  const busy = useWorkspace((s) => s.busy);
  const [showNew, setShowNew] = useState(false);
  const [seeding, setSeeding] = useState<"survey" | "gsi" | null>(null);

  useEffect(() => {
    void loadProjects();
  }, [loadProjects]);

  const totalPoints = projects.reduce((sum, p) => sum + (p.counters?.points_total ?? 0), 0);
  const totalDerived = projects.reduce(
    (sum, p) => sum + Object.values(p.counters?.derived ?? {}).reduce((a, b) => a + b, 0),
    0,
  );

  const seed = async (kind: "survey" | "gsi") => {
    setSeeding(kind);
    try {
      const result = kind === "survey" ? await api.seedDemo() : await api.seedGsiDemo();
      toast("success", result.created ? `Demo project created — ${result.project.name}` : "Demo project already exists");
      await loadProjects();
      navigate(`/projects/${result.project.id}`);
    } catch (error) {
      toast("error", `Demo seed failed: ${(error as Error).message}`);
    } finally {
      setSeeding(null);
    }
  };

  const remove = async (project: Project) => {
    if (!window.confirm(`Delete "${project.name}" and all of its points and derived outputs?`)) return;
    try {
      await api.deleteProject(project.id);
      toast("success", "Project deleted");
      await loadProjects();
    } catch (error) {
      toast("error", `Delete failed: ${(error as Error).message}`);
    }
  };

  return (
    <div className="h-full overflow-auto">
      <div className="max-w-[1400px] mx-auto px-6 py-6">
        <div className="flex flex-wrap items-end gap-4">
          <div>
            <div className="text-[10px] uppercase tracking-[0.22em] text-cyan/80">Surveying · GIS · CAD · Civil</div>
            <h1 className="text-2xl font-semibold tracking-tight mt-1">Project hub</h1>
            <p className="text-xs text-muted mt-1.5 max-w-2xl leading-relaxed">
              Field-to-finish processing: import total-station TXT/GSI, validate with QA/QC, build a
              constrained TIN, derive contours, profiles and cut &amp; fill volumes, then export a layered DXF.
            </p>
          </div>
          <div className="ml-auto flex flex-wrap items-center gap-2">
            <button className="btn" onClick={() => void seed("gsi")} disabled={seeding !== null}>
              {seeding === "gsi" ? <Spinner /> : <Satellite size={13} />}
              Leica GSI demo
            </button>
            <button className="btn" onClick={() => void seed("survey")} disabled={seeding !== null}>
              {seeding === "survey" ? <Spinner /> : <FileStack size={13} />}
              Field survey demo
            </button>
            <button className="btn-primary" onClick={() => setShowNew(true)}>
              <FolderPlus size={13} /> New project
            </button>
          </div>
        </div>

        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mt-5">
          {[
            { icon: <Boxes size={14} />, label: "Projects", value: fmtInt(projects.length), tone: "text-ink" },
            { icon: <Database size={14} />, label: "Survey points", value: fmtInt(totalPoints), tone: "text-cyan" },
            { icon: <Mountain size={14} />, label: "Derived outputs", value: fmtInt(totalDerived), tone: "text-pink" },
            {
              icon: <Ruler size={14} />,
              label: "Point CRS coverage",
              value: `${new Set(projects.map((p) => p.crs_epsg)).size}`,
              tone: "text-lime",
            },
          ].map((stat) => (
            <div key={stat.label} className="panel px-3 py-2.5 flex items-center gap-3">
              <span className="w-7 h-7 rounded bg-panel2 border border-edge flex items-center justify-center text-muted">
                {stat.icon}
              </span>
              <div>
                <div className="text-[9px] uppercase tracking-[0.16em] text-muted">{stat.label}</div>
                <div className={`text-lg font-mono tabular leading-tight ${stat.tone}`}>{stat.value}</div>
              </div>
            </div>
          ))}
        </div>

        <div className="panel mt-4 px-4 py-3">
          <div className="text-[9px] uppercase tracking-[0.18em] text-muted mb-2">
            Data governance — every downstream artefact is invalidated when upstream data changes
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {PIPELINE.map((step, index) => (
              <div key={step.label} className="flex items-center gap-2">
                <div className="px-2 py-1 rounded border border-edge bg-panel2">
                  <div className={`text-[10px] font-mono tracking-wider ${step.tone}`}>{step.label}</div>
                  <div className="text-[9px] text-muted">{step.note}</div>
                </div>
                {index < PIPELINE.length - 1 && <ArrowRight size={12} className="text-edge" />}
              </div>
            ))}
          </div>
        </div>

        <div className="mt-5 grid grid-cols-1 xl:grid-cols-2 gap-3">
          {projects.map((project) => (
            <div
              key={project.id}
              className="panel p-4 hover:border-cyan/40 transition-colors group cursor-pointer"
              onClick={() => navigate(`/projects/${project.id}`)}
            >
              <div className="flex items-start gap-3">
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <h2 className="text-sm font-medium truncate group-hover:text-cyan transition-colors">
                      {project.name}
                    </h2>
                    <StatusBadge status={project.status} />
                    <StatusBadge status={project.dependency_state} />
                  </div>
                  <div className="flex flex-wrap items-center gap-x-3 gap-y-1 mt-1.5 text-[10px] text-muted font-mono">
                    {project.code && <span>{project.code}</span>}
                    {project.location && (
                      <span className="inline-flex items-center gap-1">
                        <MapPin size={10} /> {project.location}
                      </span>
                    )}
                    <span>EPSG:{project.crs_epsg}</span>
                    <span>{project.linear_unit}</span>
                    <span>{project.angle_unit}</span>
                  </div>
                  {project.description && (
                    <p className="text-[11px] text-muted/80 mt-2 line-clamp-2 leading-relaxed">{project.description}</p>
                  )}
                </div>
                <button
                  className="btn-ghost opacity-0 group-hover:opacity-100"
                  onClick={(event) => {
                    event.stopPropagation();
                    void remove(project);
                  }}
                  title="Delete project"
                >
                  <Trash2 size={13} />
                </button>
              </div>

              <div className="flex flex-wrap gap-1.5 mt-3">
                {Object.entries(project.counters?.points ?? {}).map(([status, count]) => (
                  <span key={status} className="chip !normal-case">
                    {status} <span className="text-ink/80">{count}</span>
                  </span>
                ))}
                <span className="chip !normal-case text-cyan">
                  points <span className="text-ink/80">{fmtInt(project.counters?.points_total)}</span>
                </span>
                {Object.entries(project.counters?.derived ?? {}).map(([kind, count]) => (
                  <span key={kind} className="chip !normal-case text-pink">
                    {kind} <span className="text-ink/80">{count}</span>
                  </span>
                ))}
              </div>
            </div>
          ))}

          {projects.length === 0 && (
            <Panel className="xl:col-span-2" bodyClassName="p-0">
              <div className="p-10 flex flex-col items-center text-center gap-3">
                <UploadCloud size={26} className="text-cyan/70" />
                <div className="text-sm">No projects yet</div>
                <p className="text-[11px] text-muted max-w-md leading-relaxed">
                  Create a project and import a total-station file, or load the bundled Leimuiden sidewalk
                  dataset — 229 coded points, curb breaklines, a proposed design surface and a Leica GSI
                  export.
                </p>
                <div className="flex gap-2 mt-1">
                  <button className="btn-primary" onClick={() => setShowNew(true)}>
                    <Plus size={13} /> New project
                  </button>
                  <button className="btn" onClick={() => void seed("survey")}>
                    <FileStack size={13} /> Load demo dataset
                  </button>
                </div>
              </div>
            </Panel>
          )}
        </div>

        {busy && projects.length === 0 && (
          <div className="mt-4 flex items-center gap-2 text-[11px] text-muted">
            <Spinner /> {busy}
          </div>
        )}
      </div>

      {showNew && <NewProjectModal onClose={() => setShowNew(false)} />}
    </div>
  );
}

function NewProjectModal({ onClose }: { onClose: () => void }) {
  const navigate = useNavigate();
  const loadProjects = useWorkspace((s) => s.loadProjects);
  const toast = useWorkspace((s) => s.toast);
  const [form, setForm] = useState({
    name: "",
    code: "",
    client: "",
    location: "",
    description: "",
    crs_epsg: 28992,
    angle_unit: "gon" as "gon" | "deg",
  });
  const [saving, setSaving] = useState(false);

  const submit = async () => {
    if (!form.name.trim()) {
      toast("error", "A project name is required");
      return;
    }
    setSaving(true);
    try {
      const project = await api.createProject({
        name: form.name.trim(),
        code: form.code || undefined,
        client: form.client || undefined,
        location: form.location || undefined,
        description: form.description || undefined,
        crs_epsg: Number(form.crs_epsg),
        angle_unit: form.angle_unit,
      });
      await loadProjects();
      toast("success", `Project "${project.name}" created`);
      onClose();
      navigate(`/projects/${project.id}/import`);
    } catch (error) {
      toast("error", `Could not create project: ${(error as Error).message}`);
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal title="New survey project" onClose={onClose} width="max-w-xl">
      <div className="grid grid-cols-2 gap-3">
        <div className="col-span-2">
          <label className="label">Project name *</label>
          <input
            className="field"
            autoFocus
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
            placeholder="Kerkstraat sidewalk reconstruction"
          />
        </div>
        <div>
          <label className="label">Project code</label>
          <input
            className="field"
            value={form.code}
            onChange={(e) => setForm({ ...form, code: e.target.value })}
            placeholder="2026-014"
          />
        </div>
        <div>
          <label className="label">Client</label>
          <input
            className="field"
            value={form.client}
            onChange={(e) => setForm({ ...form, client: e.target.value })}
            placeholder="Municipality"
          />
        </div>
        <div>
          <label className="label">Location</label>
          <input
            className="field"
            value={form.location}
            onChange={(e) => setForm({ ...form, location: e.target.value })}
            placeholder="Leimuiden, NL"
          />
        </div>
        <div>
          <label className="label">Horizontal CRS</label>
          <select
            className="field"
            value={form.crs_epsg}
            onChange={(e) => setForm({ ...form, crs_epsg: Number(e.target.value) })}
          >
            {CRS_CHOICES.map((choice) => (
              <option key={choice.epsg} value={choice.epsg}>
                {choice.label}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="label">Angle unit (total station)</label>
          <select
            className="field"
            value={form.angle_unit}
            onChange={(e) => setForm({ ...form, angle_unit: e.target.value as "gon" | "deg" })}
          >
            <option value="gon">gon (centesimal)</option>
            <option value="deg">degree (sexagesimal)</option>
          </select>
        </div>
        <div>
          <label className="label">Notes</label>
          <input
            className="field"
            value={form.description}
            onChange={(e) => setForm({ ...form, description: e.target.value })}
            placeholder="Scope, control, deliverable"
          />
        </div>
      </div>
      <div className="flex justify-end gap-2 mt-4">
        <button className="btn" onClick={onClose}>
          Cancel
        </button>
        <button className="btn-primary" onClick={() => void submit()} disabled={saving}>
          {saving ? <Spinner /> : <Plus size={13} />} Create &amp; import
        </button>
      </div>
    </Modal>
  );
}
