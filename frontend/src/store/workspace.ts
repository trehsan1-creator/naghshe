/** Zustand workspace store: project, data layers, selection and view state. */

import { create } from "zustand";
import { api } from "../lib/api";
import type {
  AnalysisPayload,
  CodeMapping,
  ContourLine,
  CrossSectionResult,
  DerivedOutput,
  LineworkResult,
  PointStatus,
  ProfileResult,
  Project,
  ProjectFile,
  QaReport,
  SurfacePayload,
  SurveyPoint,
  VolumeResult,
} from "../lib/types";

export type ViewMode = "plan" | "gis" | "3d";
export type AppView = "dashboard" | "import" | "workspace";

export interface Toast {
  id: number;
  kind: "info" | "success" | "error";
  message: string;
}

interface LayerVisibility {
  points: boolean;
  labels: boolean;
  linework: boolean;
  breaklines: boolean;
  contoursMinor: boolean;
  contoursMajor: boolean;
  tin: boolean;
  boundary: boolean;
}

interface WorkspaceState {
  view: AppView;
  viewMode: ViewMode;
  projects: Project[];
  project: Project | null;
  points: SurveyPoint[];
  pointsTotal: number;
  linework: LineworkResult | null;
  surface: SurfacePayload | null;
  surfaces: DerivedOutput[];
  selectedPoint: SurveyPoint | null;
  hoveredPoint: SurveyPoint | null;
  qa: QaReport | null;
  volume: VolumeResult | null;
  profile: ProfileResult | null;
  crossSections: CrossSectionResult | null;
  statusFilter: PointStatus[];
  search: string;
  layers: LayerVisibility;
  verticalExaggeration: number;
  busy: string | null;
  toasts: Toast[];

  // import wizard
  upload: { file: ProjectFile; analysis: AnalysisPayload | null } | null;
  mapping: Record<string, number | null | boolean | string> | null;
  analysis: AnalysisPayload | null;

  setView: (view: AppView) => void;
  setViewMode: (mode: ViewMode) => void;
  toggleLayer: (key: keyof LayerVisibility) => void;
  setVerticalExaggeration: (value: number) => void;
  setStatusFilter: (statuses: PointStatus[]) => void;
  setSearch: (value: string) => void;
  selectPoint: (point: SurveyPoint | null) => void;
  hoverPoint: (point: SurveyPoint | null) => void;
  toast: (kind: Toast["kind"], message: string) => void;
  dismissToast: (id: number) => void;

  loadProjects: () => Promise<void>;
  openProject: (id: string) => Promise<void>;
  refreshPoints: () => Promise<void>;
  refreshDerived: () => Promise<void>;
  runQa: () => Promise<void>;
  updateStatus: (status: PointStatus, ids?: string[]) => Promise<void>;
  buildSurface: (options?: Record<string, unknown>) => Promise<void>;
  loadSurface: (surfaceId: string) => Promise<void>;
  computeVolumes: (options: Record<string, unknown>) => Promise<void>;
  computeProfile: (options: Record<string, unknown>) => Promise<void>;
  computeCrossSections: (options: Record<string, unknown>) => Promise<void>;
  saveCodeMapping: (mapping: CodeMapping) => Promise<void>;

  startUpload: (file: File) => Promise<void>;
  remap: (mapping: Record<string, number | null | boolean | string>) => Promise<void>;
  commitImport: (status: PointStatus, swapXy: boolean, replaceExisting?: boolean) => Promise<boolean>;
  resetImport: () => void;
}

const defaultLayers: LayerVisibility = {
  points: true,
  labels: true,
  linework: true,
  breaklines: true,
  contoursMinor: false,
  contoursMajor: true,
  tin: true,
  boundary: true,
};

let toastSeq = 0;

export const useWorkspace = create<WorkspaceState>((set, get) => ({
  view: "dashboard",
  viewMode: "plan",
  projects: [],
  project: null,
  points: [],
  pointsTotal: 0,
  linework: null,
  surface: null,
  surfaces: [],
  selectedPoint: null,
  hoveredPoint: null,
  qa: null,
  volume: null,
  profile: null,
  crossSections: null,
  statusFilter: ["VALIDATED", "APPROVED"],
  search: "",
  layers: defaultLayers,
  verticalExaggeration: 3,
  busy: null,
  toasts: [],
  upload: null,
  mapping: null,
  analysis: null,

  setView: (view) => set({ view }),
  setViewMode: (viewMode) => set({ viewMode }),
  toggleLayer: (key) => set((state) => ({ layers: { ...state.layers, [key]: !state.layers[key] } })),
  setVerticalExaggeration: (value) => set({ verticalExaggeration: value }),
  setStatusFilter: (statusFilter) => {
    set({ statusFilter });
    void get().refreshPoints();
  },
  setSearch: (search) => set({ search }),
  selectPoint: (selectedPoint) => set({ selectedPoint }),
  hoverPoint: (hoveredPoint) => set({ hoveredPoint }),

  toast: (kind, message) => {
    const id = ++toastSeq;
    set((state) => ({ toasts: [...state.toasts, { id, kind, message }] }));
    window.setTimeout(() => get().dismissToast(id), kind === "error" ? 8000 : 4000);
  },
  dismissToast: (id) => set((state) => ({ toasts: state.toasts.filter((t) => t.id !== id) })),

  loadProjects: async () => {
    try {
      const { projects } = await api.listProjects();
      set({ projects });
    } catch (error) {
      get().toast("error", `Could not load projects: ${(error as Error).message}`);
    }
  },

  openProject: async (id) => {
    set({ busy: "Loading project…" });
    try {
      const project = await api.getProject(id);
      set({ project, view: "workspace", selectedPoint: null, volume: null, profile: null });
      await Promise.all([get().refreshPoints(), get().refreshDerived()]);
      try {
        const linework = await api.linework(id);
        set({ linework });
      } catch {
        set({ linework: null });
      }
      // Restore the most recent current surface so the canvas opens on the TIN
      // instead of an empty plan view.
      const latest =
        get().surfaces.find((s) => s.kind === "surface" && s.status === "CURRENT") ??
        get().surfaces.find((s) => s.kind === "surface");
      if (latest) {
        try {
          const payload = await api.getSurface(id, latest.id);
          set({
            surface: payload,
            layers: { ...get().layers, tin: true, boundary: true, contoursMinor: true, contoursMajor: true },
          });
        } catch {
          /* surface payload unavailable — keep the empty canvas */
        }
      } else {
        set({ surface: null });
      }
    } catch (error) {
      get().toast("error", `Could not open project: ${(error as Error).message}`);
    } finally {
      set({ busy: null });
    }
  },

  refreshPoints: async () => {
    const { project, statusFilter, search } = get();
    if (!project) return;
    try {
      const data = await api.listPoints(project.id, {
        statuses: statusFilter.length ? statusFilter : undefined,
        search: search || undefined,
        limit: 20000,
      });
      set({ points: data.points, pointsTotal: data.total });
    } catch (error) {
      get().toast("error", `Could not load points: ${(error as Error).message}`);
    }
  },

  refreshDerived: async () => {
    const { project } = get();
    if (!project) return;
    try {
      const { surfaces } = await api.listSurfaces(project.id);
      set({ surfaces });
    } catch {
      /* derived list is optional */
    }
  },

  runQa: async () => {
    const { project } = get();
    if (!project) return;
    set({ busy: "Running QA/QC…" });
    try {
      const qa = await api.runQa(project.id);
      set({ qa });
      await get().refreshPoints();
      get().toast("success", `QA/QC complete — ${qa.flags.length} finding(s)`);
    } catch (error) {
      get().toast("error", `QA/QC failed: ${(error as Error).message}`);
    } finally {
      set({ busy: null });
    }
  },

  updateStatus: async (status, ids) => {
    const { project, selectPoint, selectedPoint } = get();
    if (!project) return;
    try {
      if (ids && ids.length) {
        const result = await api.bulkStatus(project.id, { status, ids });
        get().toast("success", `${result.updated} point(s) → ${status}`);
      } else {
        const from = get().statusFilter.length
          ? get().statusFilter
          : (["RAW", "VALIDATED", "APPROVED"] as PointStatus[]);
        const result = await api.bulkStatus(project.id, { status, from_status: from });
        get().toast("success", `${result.updated} point(s) → ${status}`);
      }
      if (selectedPoint) selectPoint({ ...selectedPoint, status });
      await Promise.all([get().refreshPoints(), get().refreshDerived()]);
    } catch (error) {
      get().toast("error", `Status update failed: ${(error as Error).message}`);
    }
  },

  buildSurface: async (options = {}) => {
    const { project } = get();
    if (!project) return;
    set({ busy: "Building constrained TIN…" });
    try {
      const surface = await api.buildSurface(project.id, {
        statuses: get().statusFilter.length ? get().statusFilter : undefined,
        boundary_mode: project.tin_boundary_mode,
        contour_interval: project.contour_interval,
        contour_method: "grid",
        major_every: 5,
        use_breaklines: true,
        ...options,
      });
      set({
        surface,
        layers: {
          ...get().layers,
          contoursMinor: true,
          contoursMajor: true,
          tin: true,
          boundary: true,
        },
      });
      await get().refreshDerived();
      const stats = surface.stats ?? {};
      get().toast(
        "success",
        `TIN built: ${stats.triangles ?? 0} triangles, ${surface.contours.length} contours`,
      );
    } catch (error) {
      get().toast("error", `Surface build failed: ${(error as Error).message}`);
    } finally {
      set({ busy: null });
    }
  },

  loadSurface: async (surfaceId) => {
    const { project } = get();
    if (!project) return;
    set({ busy: "Loading surface…" });
    try {
      const surface = await api.getSurface(project.id, surfaceId);
      set({ surface, viewMode: get().viewMode === "plan" ? "3d" : get().viewMode });
    } catch (error) {
      get().toast("error", `Could not load surface: ${(error as Error).message}`);
    } finally {
      set({ busy: null });
    }
  },

  computeVolumes: async (options) => {
    const { project } = get();
    if (!project) return;
    set({ busy: "Computing cut & fill…" });
    try {
      const volume = await api.computeVolumes(project.id, options);
      set({ volume });
      await get().refreshDerived();
      get().toast("success", `Cut ${volume.cut_m3.toFixed(2)} m³ · Fill ${volume.fill_m3.toFixed(2)} m³`);
    } catch (error) {
      get().toast("error", `Volume computation failed: ${(error as Error).message}`);
    } finally {
      set({ busy: null });
    }
  },

  computeProfile: async (options) => {
    const { project } = get();
    if (!project) return;
    set({ busy: "Sampling profile…" });
    try {
      const profile = await api.computeProfile(project.id, options);
      set({ profile });
    } catch (error) {
      get().toast("error", `Profile failed: ${(error as Error).message}`);
    } finally {
      set({ busy: null });
    }
  },

  computeCrossSections: async (options) => {
    const { project } = get();
    if (!project) return;
    set({ busy: "Extracting cross sections…" });
    try {
      const crossSections = await api.computeCrossSections(project.id, options);
      set({ crossSections });
    } catch (error) {
      get().toast("error", `Cross sections failed: ${(error as Error).message}`);
    } finally {
      set({ busy: null });
    }
  },

  saveCodeMapping: async (mapping) => {
    const { project } = get();
    if (!project) return;
    try {
      await api.upsertCodeMapping(project.id, mapping);
      const refreshed = await api.getProject(project.id);
      set({ project: refreshed });
      get().toast("success", `Code ${mapping.code} saved`);
    } catch (error) {
      get().toast("error", `Could not save code: ${(error as Error).message}`);
    }
  },

  startUpload: async (file) => {
    const { project } = get();
    if (!project) return;
    set({ busy: "Uploading & analysing…", upload: null, analysis: null, mapping: null });
    try {
      const result = await api.uploadFile(project.id, file);
      set({
        upload: result,
        analysis: result.analysis,
        mapping: result.analysis
          ? ({ ...result.analysis.mapping } as unknown as Record<string, number | null | boolean | string>)
          : null,
      });
      get().toast("success", `${result.file.original_filename} analysed`);
    } catch (error) {
      get().toast("error", `Upload failed: ${(error as Error).message}`);
    } finally {
      set({ busy: null });
    }
  },

  remap: async (mapping) => {
    const { project, upload } = get();
    if (!project || !upload) return;
    set({ busy: "Re-parsing with the new mapping…", mapping });
    try {
      const analysis = await api.analyzeFile(project.id, upload.file.id, {
        mapping: mapping as Record<string, unknown>,
        preview_only: false,
      });
      set({ analysis });
    } catch (error) {
      get().toast("error", `Mapping failed: ${(error as Error).message}`);
    } finally {
      set({ busy: null });
    }
  },

  commitImport: async (status, swapXy, replaceExisting = false) => {
    const { project, upload, mapping } = get();
    if (!project || !upload) return false;
    set({ busy: "Committing points…" });
    try {
      const result = await api.commitFile(project.id, upload.file.id, {
        mapping: (mapping ?? {}) as Record<string, unknown>,
        status,
        swap_xy: swapXy,
        replace_existing: replaceExisting,
      });
      get().toast("success", `${result.points_created} point(s) imported as ${status}`);
      set({ upload: null, analysis: null, mapping: null, view: "workspace" });
      await get().openProject(project.id);
      return true;
    } catch (error) {
      get().toast("error", `Import failed: ${(error as Error).message}`);
      return false;
    } finally {
      set({ busy: null });
    }
  },

  resetImport: () => set({ upload: null, analysis: null, mapping: null }),
}));

export const useSelectedPoint = () => useWorkspace((s) => s.selectedPoint);
export const useLayers = () => useWorkspace((s) => s.layers);
export const useViewMode = () => useWorkspace((s) => s.viewMode);
export const usePoints = () => useWorkspace((s) => s.points);
export const useSurface = () => useWorkspace((s) => s.surface);

export function visibleContours(surface: SurfacePayload | null, layers: LayerVisibility): ContourLine[] {
  if (!surface) return [];
  return surface.contours.filter((c) => (c.is_major ? layers.contoursMajor : layers.contoursMinor));
}
