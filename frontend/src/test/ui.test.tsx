import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
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
    expect(screen.getAllByText("مدیریت پروژه‌ها").length).toBeGreaterThan(0);
    expect(screen.getByText(/مدیریت وابستگی داده/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /پروژهٔ جدید/i })).toBeInTheDocument();
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

    expect(await screen.findByText("ورود داده‌های برداشت")).toBeInTheDocument();
    expect(screen.getByText("نگاشت ستون‌ها")).toBeInTheDocument();
    expect(screen.getByText("هشدارهای کنترل کیفیت")).toBeInTheDocument();
    expect(screen.getByText(/ثبت \d+ نقطه/)).toBeInTheDocument();
    expect(screen.getAllByText(/مختصات شرقی|مختصات شمالی/i).length).toBeGreaterThan(0);
  });

  it("shows the workspace toolbar and lets each imported survey get its own named surface", async () => {
    const user = userEvent.setup();
    useWorkspace.setState({
      project: {
        ...demoProject,
        files: [
          {
            id: "file-old",
            project_id: "proj-1",
            original_filename: "survey-old.csv",
            file_format: "csv",
            status: "COMMITTED",
            row_count: 3,
            imported_points: 3,
            size_bytes: 120,
            sha256: "old-hash",
          },
          {
            id: "file-new",
            project_id: "proj-1",
            original_filename: "survey-new.csv",
            file_format: "csv",
            status: "COMMITTED",
            row_count: 3,
            imported_points: 3,
            size_bytes: 120,
            sha256: "new-hash",
          },
        ],
      } as never,
      points: [point] as never,
      pointsTotal: 1,
      view: "workspace",
    });

    render(
      <MemoryRouter initialEntries={["/projects/proj-1"]}>
        <App />
      </MemoryRouter>,
    );

    expect(await screen.findByText("جدول نقاط برداشت")).toBeInTheDocument();
    expect(screen.getByText("لایه‌ها")).toBeInTheDocument();
    expect(screen.getByText("Surface")).toBeInTheDocument();
    expect(screen.getByText("فایل برداشتِ این سطح")).toBeInTheDocument();
    expect(screen.getByRole("option", { name: /survey-old.csv/ })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: /survey-new.csv/ })).toBeInTheDocument();
    const filePicker = screen.getByRole("combobox", { name: "فایل برداشتِ این سطح" });
    await user.selectOptions(filePicker, "file-old");
    expect(screen.getByRole("textbox", { name: "نام سطح" })).toHaveValue("survey-old · سطح");
    expect(screen.getByRole("button", { name: "ساخت سطح از فایل انتخاب‌شده" })).toBeEnabled();
    expect(screen.getAllByText("CL1_ST").length).toBeGreaterThan(0);
    expect(await screen.findByTestId("plan-canvas")).toBeInTheDocument();
  });
});
