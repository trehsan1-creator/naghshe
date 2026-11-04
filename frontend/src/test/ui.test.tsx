import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import App from "../App";
import { useWorkspace } from "../store/workspace";
import fixture from "./fixtures/upload-analysis.json";

vi.mock("../components/PlanCanvas", () => ({ default: () => <div data-testid="plan-canvas" /> }));
vi.mock("../components/GisCanvas", () => ({ default: () => <div data-testid="gis-canvas" /> }));
vi.mock("../components/Scene3D", () => ({ default: () => <div data-testid="scene-3d" /> }));

const demoProject = {
  id: "proj-1",
  name: "Sidewalk reconstruction — Leimuiden",
  code: "DEMO-001",
  description: "60 m urban street reconstruction",
  client: "Municipality",
  location: "Leimuiden, NL",
  surveyor: "SurveyPro",
  crs_epsg: 28992,
  vertical_datum: "NAP",
  linear_unit: "m",
  angle_unit: "gon",
  duplicate_xy_tolerance: 0.005,
  duplicate_z_tolerance: 0.02,
  z_mad_threshold: 3.5,
  local_z_step_threshold: 1.5,
  tin_boundary_mode: "concave_hull",
  contour_interval: 0.1,
  breakline_codes: ["KBL"],
  status: "QAQC",
  dependency_state: "CURRENT",
  counters: { points: { VALIDATED: 229 }, points_total: 229, derived: { surface: 1 } },
  files: [],
  code_mappings: [],
  layers: [],
};

const point = {
  id: "pt-1",
  project_id: "proj-1",
  file_id: null,
  point_number: "1",
  easting: 105419.995,
  northing: 471880.001,
  elevation: 0.851,
  code: "CL1_ST",
  description: "centreline start",
  layer: "S-CENTRELINE",
  status: "VALIDATED",
  version: 1,
  source_order: 1,
  line_no: 1,
  qa_severity: "ok",
  qa_flags: null,
};

const jsonResponse = (body: unknown) =>
  Promise.resolve(new Response(JSON.stringify(body), { status: 200, headers: { "content-type": "application/json" } }));

beforeEach(() => {
  vi.restoreAllMocks();
  useWorkspace.setState({
    projects: [],
    project: null,
    points: [],
    surface: null,
    linework: null,
    surfaces: [],
    upload: null,
    analysis: null,
    mapping: null,
    qa: null,
    view: "dashboard",
    busy: null,
    toasts: [],
  });
  vi.stubGlobal(
    "fetch",
    vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/projects/proj-1/surfaces")) return jsonResponse({ surfaces: [], total: 0 });
      if (url.includes("/projects/proj-1/points")) return jsonResponse({ points: [point], total: 1, returned: 1 });
      if (url.includes("/projects/proj-1/linework")) return jsonResponse({ features: [], issues: [], stats: {} });
      if (/\/projects\/proj-1$/.test(url)) return jsonResponse(demoProject);
      if (url.includes("/projects")) return jsonResponse({ projects: [demoProject], total: 1 });
      return jsonResponse({});
    }),
  );
});

describe("SurveyPro shell", () => {
  it("renders the project hub with the demo project card", async () => {
    render(
      <MemoryRouter initialEntries={["/"]}>
        <App />
      </MemoryRouter>,
    );
    expect(await screen.findByText(/Sidewalk reconstruction/)).toBeInTheDocument();
    expect(screen.getAllByText("Project hub").length).toBeGreaterThan(0);
    expect(screen.getByText(/DATA GOVERNANCE|Data governance/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /New project/i })).toBeInTheDocument();
  });

  it("renders the import wizard mapper and QA findings for an analysed upload", async () => {
    useWorkspace.setState({
      project: demoProject as never,
      upload: fixture as never,
      analysis: (fixture as { analysis: unknown }).analysis as never,
      mapping: (fixture.analysis as { mapping: Record<string, number | null | boolean | string> }).mapping,
      view: "import",
    });

    render(
      <MemoryRouter initialEntries={["/projects/proj-1/import"]}>
        <App />
      </MemoryRouter>,
    );

    expect(await screen.findByText("Import field data")).toBeInTheDocument();
    expect(screen.getByText("Column mapper")).toBeInTheDocument();
    expect(screen.getByText("QA/QC warnings")).toBeInTheDocument();
    expect(screen.getByText(/Commit 8 points|Commit 229 points/)).toBeInTheDocument();
    expect(screen.getAllByText(/easting|Northing/i).length).toBeGreaterThan(0);
  });

  it("shows the workspace toolbar, layers and point table for a loaded project", async () => {
    useWorkspace.setState({
      project: demoProject as never,
      points: [point] as never,
      pointsTotal: 1,
      view: "workspace",
    });

    render(
      <MemoryRouter initialEntries={["/projects/proj-1"]}>
        <App />
      </MemoryRouter>,
    );

    expect(await screen.findByText("Point database")).toBeInTheDocument();
    expect(screen.getByText("Layers")).toBeInTheDocument();
    expect(screen.getByText("Surface")).toBeInTheDocument();
    expect(screen.getByText("Build constrained TIN")).toBeInTheDocument();
    expect(screen.getAllByText("CL1_ST").length).toBeGreaterThan(0);
    expect(await screen.findByTestId("plan-canvas")).toBeInTheDocument();
  });
});
