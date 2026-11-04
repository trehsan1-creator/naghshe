// @vitest-environment node
/**
 * Contract test: exercises the real FastAPI backend through the browser client.
 *
 * Skipped automatically when the API is not reachable (e.g. CI without services).
 * Start it with:  cd backend && uvicorn app.main:app --port 8000
 */
import { beforeAll, describe, expect, it, vi } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import type { SurveyPoint } from "./types";

const API_BASE = process.env.SURVEYPRO_API_BASE ?? "http://127.0.0.1:8000/api/v1";
let api: (typeof import("./api"))["api"];

const samplePath = (name: string) => resolve(process.cwd(), "..", "sample_data", name);
const fileOf = (name: string) => {
  const buffer = readFileSync(samplePath(name));
  return new File([new Uint8Array(buffer)], name, { type: "text/plain" });
};

let online = false;
beforeAll(async () => {
  // Point the typed client at the live API before the module resolves its base URL.
  vi.stubEnv("VITE_API_BASE", API_BASE);
  ({ api } = await import("./api"));
  try {
    const health = await api.health();
    online = health.status === "ok";
  } catch {
    online = false;
  }
});

describe("SurveyPro API contract", () => {
  it("runs the full field-to-finish pipeline on the sample sidewalk survey", async (ctx) => {
    if (!online) {
      ctx.skip();
      return;
    }
    const project = await api.createProject({
      name: `Contract test ${Date.now()}`,
      crs_epsg: 28992,
      angle_unit: "gon",
      code: "TEST-001",
    });
    expect(project.id).toBeTruthy();
    expect(project.crs_epsg).toBe(28992);

    const uploaded = await api.uploadFile(project.id, fileOf("sidewalk_survey_rd.txt"));
    expect(uploaded.file.file_format).toBe("txt");
    const analysis = uploaded.analysis!;
    expect(analysis.row_count).toBeGreaterThan(200);
    expect(analysis.mapping.easting).not.toBeNull();
    expect(analysis.mapping.northing).not.toBeNull();
    expect(analysis.qa.summary.points).toBe(analysis.points.length);
    expect(analysis.points[0]).toHaveProperty("easting");

    const committed = await api.commitFile(project.id, uploaded.file.id, {
      status: "VALIDATED",
      mapping: analysis.mapping as unknown as Record<string, unknown>,
    });
    expect(committed.points_created).toBe(229);

    const { points, total } = await api.listPoints(project.id, { limit: 2000 });
    expect(total).toBe(229);
    expect(points.every((p: SurveyPoint) => p.status === "VALIDATED")).toBe(true);

    const qa = await api.runQa(project.id);
    expect(qa.points_checked).toBe(229);
    expect(qa.tolerances.duplicate_xy_tolerance).toBeGreaterThan(0);

    const linework = await api.linework(project.id);
    expect(linework.features.length).toBeGreaterThanOrEqual(5);
    expect(linework.features[0].vertices[0]).toHaveLength(3);

    const surface = await api.buildSurface(project.id, {
      file_id: uploaded.file.id,
      contour_interval: 0.1,
    });
    expect(surface.mesh.faces.length).toBeGreaterThan(100);
    expect(surface.mesh.constrained).toBe(true);
    expect(surface.contours.length).toBeGreaterThan(0);
    expect(surface.stats.area_m2).toBeGreaterThan(100);

    // Proposed design surface from the second sample file.
    const designUpload = await api.uploadFile(project.id, fileOf("proposed_design_rd.txt"));
    const designCommit = await api.commitFile(project.id, designUpload.file.id, { status: "VALIDATED" });
    expect(designCommit.points_created).toBeGreaterThan(100);
    const design = await api.buildSurface(project.id, {
      file_id: designUpload.file.id,
      contour_interval: 0.1,
    });
    expect(design.output?.id).toBeTruthy();

    const volumes = await api.computeVolumes(project.id, {
      existing_surface_id: surface.output!.id,
      proposed_surface_id: design.output!.id,
      method: "grid",
      cell_size: 0.5,
    });
    expect(volumes.method).toBe("grid_prismoidal");
    expect(volumes.total_area_m2).toBeGreaterThan(0);
    expect(volumes.cut_m3 + volumes.fill_m3).toBeGreaterThan(0);

    const profile = await api.computeProfile(project.id, {
      surface_id: surface.output!.id,
      station_interval: 5,
      offsets: [0, 1],
    });
    expect(profile.samples.length).toBeGreaterThan(2);
    expect(profile.length_m).toBeGreaterThan(10);

    const sections = await api.computeCrossSections(project.id, {
      surface_id: surface.output!.id,
      station_interval: 10,
      left: 4,
      right: 4,
      samples: 41,
    });
    expect(sections.sections.length).toBeGreaterThan(1);
    expect(sections.sections[0].existing.elevations.length).toBe(41);

    const geojson = await api.geojson(project.id, surface.output!.id);
    expect(geojson.type).toBe("FeatureCollection");
    expect(geojson.features.some((f) => f.properties?.kind === "point")).toBe(true);
    expect(geojson.bbox?.[0]).toBeGreaterThan(-180);

    const derived = await api.listDerived(project.id);
    expect(derived.derived.some((d) => d.kind === "surface")).toBe(true);

    await api.deleteProject(project.id);
  }, 60_000);
});
