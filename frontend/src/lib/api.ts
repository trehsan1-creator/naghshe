/** Thin, typed client for the SurveyPro REST API. */

import type {
  AnalysisPayload,
  CodeMapping,
  CrossSectionResult,
  DerivedOutput,
  GeoJsonFeatureCollection,
  LineworkResult,
  PointStatus,
  ProfileResult,
  Project,
  ProjectFile,
  QaReport,
  SurfacePayload,
  SurveyPoint,
  VolumeResult,
} from "./types";

const BASE = import.meta.env.VITE_API_BASE ?? "/api/v1";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE}${path}`, {
    headers: init?.body instanceof FormData ? undefined : { "Content-Type": "application/json" },
    ...init,
  });
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const body = await response.json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* keep the status text */
    }
    throw new ApiError(response.status, detail);
  }
  if (response.status === 204) return undefined as T;
  const contentType = response.headers.get("content-type") ?? "";
  if (contentType.includes("application/json")) return (await response.json()) as T;
  return (await response.text()) as unknown as T;
}

export const api = {
  health: () => request<{ status: string; engines: Record<string, string> }>("/health"),

  listProjects: () => request<{ projects: Project[]; total: number }>("/projects"),

  getProject: (id: string) => request<Project>(`/projects/${id}`),

  createProject: (payload: {
    name: string;
    crs_epsg?: number;
    description?: string;
    location?: string;
    client?: string;
    code?: string;
    surveyor?: string;
    vertical_datum?: string;
    angle_unit?: "gon" | "deg" | "mil" | "dms";
    breakline_codes?: string[];
  }) => request<Project>("/projects", { method: "POST", body: JSON.stringify(payload) }),

  updateProject: (id: string, payload: Record<string, unknown>) =>
    request<Project>(`/projects/${id}`, { method: "PATCH", body: JSON.stringify(payload) }),

  deleteProject: (id: string) => request<void>(`/projects/${id}`, { method: "DELETE" }),

  overview: (id: string) =>
    request<{
      project: Project;
      counters: Project["counters"];
      extent: Record<string, number> | null;
      code_usage: Record<string, number>;
      crs: Project["crs"];
    }>(`/projects/${id}/overview`),

  uploadFile: async (projectId: string, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<{ file: ProjectFile; analysis: AnalysisPayload | null }>(
      `/projects/${projectId}/files`,
      { method: "POST", body: form },
    );
  },

  analyzeFile: (
    projectId: string,
    fileId: string,
    payload: {
      mapping?: Record<string, unknown>;
      delimiter?: string;
      swap_xy?: boolean;
      preview_only?: boolean;
    },
  ) =>
    request<AnalysisPayload>(`/projects/${projectId}/files/${fileId}/analyze`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  commitFile: (
    projectId: string,
    fileId: string,
    payload: {
      mapping?: Record<string, unknown>;
      swap_xy?: boolean;
      status?: PointStatus;
      replace_existing?: boolean;
    },
  ) =>
    request<{
      file: ProjectFile;
      points_created: number;
      stations_created: number;
      observations_created: number;
      qa: QaReport;
    }>(`/projects/${projectId}/files/${fileId}/commit`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  listPoints: (
    projectId: string,
    params: {
      statuses?: string[];
      code?: string;
      search?: string;
      limit?: number;
      offset?: number;
      sort?: string;
      order?: string;
    } = {},
  ) => {
    const query = new URLSearchParams();
    params.statuses?.forEach((s) => query.append("status", s));
    if (params.code) query.set("code", params.code);
    if (params.search) query.set("search", params.search);
    query.set("limit", String(params.limit ?? 5000));
    query.set("offset", String(params.offset ?? 0));
    query.set("sort", params.sort ?? "source_order");
    query.set("order", params.order ?? "asc");
    return request<{ points: SurveyPoint[]; total: number; returned: number }>(
      `/projects/${projectId}/points?${query.toString()}`,
    );
  },

  patchPoint: (projectId: string, pointId: string, payload: Record<string, unknown>) =>
    request<SurveyPoint>(`/projects/${projectId}/points/${pointId}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),

  bulkStatus: (
    projectId: string,
    payload: {
      status: PointStatus;
      ids?: string[];
      point_numbers?: string[];
      from_status?: string[];
      code?: string;
    },
  ) =>
    request<{ updated: number; status: string }>(`/projects/${projectId}/points/bulk-status`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  runQa: (projectId: string) =>
    request<QaReport & { points_checked: number; tolerances: Record<string, number> }>(
      `/projects/${projectId}/qaqc`,
      { method: "POST", body: JSON.stringify({ persist: true }) },
    ),

  linework: (projectId: string) =>
    request<LineworkResult>(`/projects/${projectId}/linework`),

  codeMappings: (projectId: string) =>
    request<{ code_mappings: CodeMapping[] }>(`/projects/${projectId}/code-mappings`),

  upsertCodeMapping: (projectId: string, payload: CodeMapping) =>
    request<CodeMapping>(`/projects/${projectId}/code-mappings`, {
      method: "PUT",
      body: JSON.stringify(payload),
    }),

  buildSurface: (projectId: string, payload: Record<string, unknown>) =>
    request<SurfacePayload>(`/projects/${projectId}/surfaces`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  getSurface: (projectId: string, surfaceId: string) =>
    request<SurfacePayload>(`/projects/${projectId}/surfaces/${surfaceId}`),

  listSurfaces: (projectId: string) =>
    request<{ surfaces: DerivedOutput[]; total: number }>(`/projects/${projectId}/surfaces`),

  listDerived: (projectId: string) =>
    request<{ derived: DerivedOutput[]; total: number }>(`/projects/${projectId}/derived`),

  computeVolumes: (projectId: string, payload: Record<string, unknown>) =>
    request<VolumeResult>(`/projects/${projectId}/volumes`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  computeProfile: (projectId: string, payload: Record<string, unknown>) =>
    request<ProfileResult>(`/projects/${projectId}/profiles`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  computeCrossSections: (projectId: string, payload: Record<string, unknown>) =>
    request<CrossSectionResult>(`/projects/${projectId}/cross-sections`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  geojson: (projectId: string, surfaceId?: string | null) => {
    const query = surfaceId ? `?surface_id=${surfaceId}` : "";
    return request<GeoJsonFeatureCollection>(`/projects/${projectId}/geojson${query}`);
  },

  exportDxfUrl: (projectId: string, opts: { surfaceId?: string | null; tin?: boolean; contours?: boolean } = {}) => {
    const query = new URLSearchParams();
    if (opts.surfaceId) query.set("surface_id", opts.surfaceId);
    if (opts.tin === false) query.set("include_tin", "false");
    if (opts.contours === false) query.set("include_contours", "false");
    const qs = query.toString();
    return `${BASE}/projects/${projectId}/export/dxf${qs ? `?${qs}` : ""}`;
  },

  exportCsvUrl: (projectId: string) => `${BASE}/projects/${projectId}/export/points.csv`,

  seedDemo: () =>
    request<{ project: Project; created: boolean; points_created?: number }>("/demo/seed", {
      method: "POST",
      body: JSON.stringify({}),
    }),

  seedGsiDemo: () =>
    request<{ project: Project; created: boolean; observations_created?: number }>("/demo/seed-gsi", {
      method: "POST",
      body: JSON.stringify({}),
    }),
};
