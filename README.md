# SurveyPro

**Production-grade surveying · GIS · CAD · civil engineering platform — Deliverable 1.**

SurveyPro ingests raw total-station data (Leica GSI-8/16 or plain TXT/CSV), validates it with
surveying QA/QC, builds a **constrained Delaunay TIN** that honours 3D breaklines, derives contours,
profiles, cross sections and cut & fill volumes, and exports a **layered AutoCAD DXF** — all from a
dark engineering web UI backed by a FastAPI + PostGIS service.

Everything in this repository is a working vertical slice: real parsers, real pyproj transformations,
real Shewchuk `triangle` triangulation, real `contourpy` contours, real `ezdxf` output. There are no
mock calculations and no placeholder screens.

---

## 1. Screens & workflow

| Route | Screen | What it does |
| --- | --- | --- |
| `/` | **Project hub** | Project cards with point/derived counters, CRS and dependency state; create projects, seed the bundled demo datasets, delete projects. |
| `/projects/:id/import` | **Import wizard** | Drag & drop upload → format/encoding/delimiter detection → column mapper with confidence bars → QA/QC warning table → commit into the point database (RAW / VALIDATED / APPROVED). |
| `/projects/:id` | **Workspace** | Left layer manager + code legend + derived-output stack, centre canvas with **Plan (deck.gl orthographic)** / **GIS (MapLibre)** / **3D (three.js)** modes, bottom dock with the editable point table (TanStack), profile, cut & fill and cross-section tabs, right dock with the point inspector and surface builder. |
| `/projects/:id/codes` | **Code library** | Field code → CAD layer / geometry kind / block / ACI colour / breakline flag; layer standards. |
| `/projects/:id/qa` | **QA/QC report** | Findings with severity, affected points (clickable), dataset statistics, axis-swap verdict, editable tolerances. |

The workspace toolbar carries the three-tier status counters, one-click **Run QA/QC**, **Build
constrained TIN**, vertical exaggeration (3D), and the **DXF** / **CSV** download buttons.

---

## 2. Quick start

### Docker (PostGIS + API + web UI)

```bash
docker compose up --build
# web UI          http://localhost:5173
# API / Swagger   http://localhost:8000/docs
# PostGIS         localhost:5432  (surveypro / surveypro)
```

The backend container runs `alembic upgrade head` before starting uvicorn, so the PostGIS schema
(geometry columns `geometry(PointZ, <srid>)` + GiST index) is created by the migration, not by
`create_all`. Uploads and derived artefacts live in named volumes; `sample_data/` is mounted read-only
so the demo seeder works inside the container.

### Local development (SQLite fallback, no services required)

```bash
# API ---------------------------------------------------------------
cd backend
python -m venv ../.venv && ../.venv/bin/pip install -r requirements.txt
SURVEYPRO_DATABASE_URL="sqlite+aiosqlite:///./data/surveypro.db" \
  ../.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000

# Web UI ------------------------------------------------------------
cd frontend
npm install
npm run dev          # http://localhost:5173, /api proxied to :8000
```

With SQLite the geometry column stores ISO WKT and the bbox filter falls back to Python; with
PostgreSQL/PostGIS the same code path uses `ST_Within` + `ST_MakeEnvelope` inside the database.

---

## 3. Sample data (`/sample_data`)

| File | Contents |
| --- | --- |
| `sidewalk_survey_rd.txt` | 229 coded points of a 60 m urban street reconstruction, Dutch headers (`Puntnummer,X,Y,Z,Code,Omschrijving`), codes `CL1`, `KBL1`, `KBR1`, `KBBL1`, `KBBR1`, `SWL1`, `SWR1`, `MH`, `TREE`. |
| `sidewalk_survey_messy.txt` | The same survey as whitespace/tab mixed, **northing before easting**, no header, with duplicated and Z-inconsistent shots — exercises detection and QA/QC. |
| `proposed_design_rd.txt` | Proposed design surface for cut & fill comparison. |
| `leica_ts02_survey.gsi` | GSI-8/16 field book (station setup, Hz/V/slope-distance observations, level words, a zero-target block that must be skipped). |
| `ground_truth.json`, `gsi_ground_truth.json` | Expected values used by the parser tests. |
| `generate_sample_data.py` | Deterministic generator for the above. |

Seeding: **Project hub → “Field survey demo”** (creates the project, imports both TXT files and builds
the source surfaces) or **“Leica GSI demo”**.

---

## 4. Architecture

```
frontend/ (React 18 · TS · Vite · Tailwind · Zustand · TanStack Table · deck.gl · MapLibre · three/R3F)
   src/lib/api.ts          typed REST client (single source of truth for payload shapes)
   src/store/workspace.ts  Zustand store: project, points, layers, selection, derived outputs
   src/components/         PlanCanvas (deck.gl) · GisCanvas (MapLibre) · Scene3D (R3F) ·
                           LayerManager · PointTable · PropertiesPanel · ComputationPanels · charts
   src/pages/              Dashboard · ProjectShell · Workspace · ImportWizard · CodeLibrary · QaPage
        │  /api/v1 (Vite proxy in dev, nginx reverse proxy in Docker)
        ▼
backend/ (FastAPI · Pydantic v2 · SQLAlchemy 2 async · GeoAlchemy2 · Alembic · pyproj · shapely ·
          scipy · triangle · contourpy · numpy · ezdxf · lxml)
   app/engines/            pure, dependency-light computational kernels (no DB, no HTTP)
     txt_gsi_parser.py     encoding/delimiter/column heuristics, GSI-8/16 → polar → cartesian
     coordinate_engine.py  pyproj transforms, similarity (shift+rotation) fit, QA/QC battery
     linework_engine.py    field code → point/block/line/polygon, string resolution, closure
     cad_surface_engine.py CDT TIN, contours, grid/end-area volumes, profiles, sections, DXF
   app/services/           orchestration: ingest, computation, export, demo, lineage
   app/api/routes/         projects · files · points · codes · surfaces · export · geojson · demo
   app/models/             Project · ProjectFile · SurveyStation · RawObservation · SurveyPoint ·
                           CodeMapping · LayerStandard · DerivedOutput
   alembic/                initial migration (PostGIS extension + spatial index)
   tests/                  76 pytest cases
```

### Engine highlights

* **Parsing** — scoring-based encoding detection (`utf-8` → `cp1252` → `cp1256` …), delimiter scoring
  (`, ; \t |` and whitespace) with a decimal-comma tie-break, token-count mode voting, per-column
  statistical profiling (numeric/integer ratio, decimals, sequential ratio), header detection and a
  confidence-scored column mapping. GSI words are decoded per the Leica GSI ONLINE layout (8/16 chars,
  unit and decimal flags from positions 4–6, gon/degree Hz), and polar observations are reduced to
  rectangular coordinates with station height / instrument height / reflector height applied. Blocks
  with zero target coordinates are skipped.
* **CRS & QA/QC** — `pyproj` transformations between any EPSG codes, a 2D similarity transform
  (Helmert shift + rotation + scale) fitted with `scipy`, and a validation battery: X/Y swap detection
  (magnitude + axis-range signatures), duplicate XY/Z within tolerance, robust MAD Z outliers,
  local Z steps between neighbouring shots, unknown field codes, hull area and point density per
  hectare. Every flag carries severity, metric and the affected point numbers.
* **Surface** — constrained Delaunay triangulation via `triangle` with a concave/convex hull boundary
  and 3D breaklines (curb tops/bottoms, ridges) inserted as constrained edges; coincident points are
  merged keeping the highest elevation; contours are generated with `contourpy` (grid or TIN method)
  with configurable interval and index-contour emphasis.
* **Civil quantities** — grid-prismoidal cut & fill clipped to the overlap of two surfaces (cell size
  configurable), average-end-area from sampled sections, longitudinal profiles at any station interval
  and offset set, perpendicular cross sections with 2..2001 samples.
* **CAD** — `ezdxf` exporter writing layer table, ACI colours, point blocks with attributes, 3D
  polylines for linework and breaklines, `3DFACE` triangles for the TIN, contour polylines on
  `S-CONTOUR-MAJOR` / `S-CONTOUR-MINOR`, elevation labels, and a boundary polyline.

### Data governance

```
RAW  ──►  VALIDATED  ──►  APPROVED  ──►  TIN  ──►  contours / volumes / profiles / DXF
(immutable uploads)      (signed off)     (derived artefacts carry a dependency graph)
```

* Original uploads are stored byte-identical with a SHA-256 checksum; re-imports never mutate them.
* Point edits bump `version` and re-run the lineage propagation: every downstream artefact
  (`DerivedOutput`) is flagged **OUTDATED** until it is rebuilt, and the UI shows that state on the
  project card, the toolbar and each output in the layer manager.
* Computations consume only `VALIDATED` + `APPROVED` points; `REJECTED` points never reach a surface.

---

## 5. API

Base path `/api/v1` (OpenAPI at `/api/docs`).

```
GET    /health                                engine + database capabilities
GET    /crs  ·  /crs/{epsg}                    CRS metadata & suggestions (pyproj)

POST   /projects                               create project (CRS, units, tolerances)
GET    /projects                               list with counters
GET    /projects/{id}                          detail: files, codes, layers, derived outputs
PATCH  /projects/{id}                           tolerances, boundary mode, contour interval, status
DELETE /projects/{id}

POST   /projects/{id}/files                    upload (multipart) → analysis payload
POST   /projects/{id}/files/{fid}/analyze      re-parse with an explicit column mapping
POST   /projects/{id}/files/{fid}/commit       write points / stations / observations
GET    /projects/{id}/files/{fid}/log          import log

GET    /projects/{id}/points                   paged, filterable, sortable point database
PATCH  /projects/{id}/points/{pid}             edit level/code/description/status (version bump)
POST   /projects/{id}/points/bulk-status       RAW → VALIDATED → APPROVED / REJECTED
POST   /projects/{id}/qaqc                     run + persist the QA/QC battery
GET    /projects/{id}/qaqc                     currently flagged points
GET    /projects/{id}/linework · /breaklines   field-to-finish geometry

GET    /projects/{id}/code-mappings            code library
PUT    /projects/{id}/code-mappings            upsert a code
GET/PUT/PATCH /projects/{id}/layers            layer standards

POST   /projects/{id}/surfaces                 build constrained TIN + contours
GET    /projects/{id}/surfaces[/{sid}]         list / reload a stored surface payload
POST   /projects/{id}/volumes                  cut & fill (grid prismoidal or end area)
POST   /projects/{id}/profiles                 longitudinal profile
POST   /projects/{id}/cross-sections           perpendicular sections
GET    /projects/{id}/derived                  lineage graph of derived artefacts

GET    /projects/{id}/export/dxf               layered DXF (also POST for options)
GET    /projects/{id}/export/points.csv        point list CSV
GET    /projects/{id}/geojson                  points/linework/contours in EPSG:4326 (pyproj)
POST   /demo/seed · /demo/seed-gsi             bundled demo datasets
```

Uploads return the full analysis: detected format/encoding/delimiter, column profiles, suggested
mapping + per-role confidence, up to 500 preview points, parse issues and the QA/QC report computed
with the suggested mapping — which is what the import wizard renders.

---

## 6. Tests

```bash
# backend — 76 cases: parsers (TXT + GSI), coordinate engine & QA/QC, TIN, volumes, DXF, REST API
cd backend && ../.venv/bin/python -m pytest tests/ -q

# frontend — component/route smoke tests + a live API contract test
cd frontend && npm run typecheck && npm test
```

The frontend contract test (`src/lib/api.test.ts`) drives the real backend through the typed client:
upload → analyse → commit 229 points → QA/QC → linework → surface → design surface → volumes →
profile → cross sections → GeoJSON → lineage → delete. It skips automatically when the API is not
running on `127.0.0.1:8000` (override with `SURVEYPRO_API_BASE`).

Measured on the bundled sidewalk dataset: 229 points, 851 TIN triangles over 720.7 m², 128 contours
at 0.10 m, cut/fill versus the proposed design in the m³ range, DXF ≈ 310 kB containing `3DFACE`
triangles and layered polylines.

---

## 7. Configuration

All settings are environment driven with the `SURVEYPRO_` prefix (`app/config.py`):

| Variable | Default | Purpose |
| --- | --- | --- |
| `SURVEYPRO_DATABASE_URL` | `sqlite+aiosqlite:///./data/surveypro.db` | Async SQLAlchemy URL (`postgresql+asyncpg://…` for PostGIS) |
| `SURVEYPRO_UPLOAD_DIR` | `./data/uploads` | Raw upload storage |
| `SURVEYPRO_MAX_UPLOAD_BYTES` | `67108864` | Upload limit (64 MB) |
| `SURVEYPRO_CORS_ORIGINS` | `*` | Comma-separated origins |
| `SURVEYPRO_DEFAULT_CRS_EPSG` | `28992` | Default project CRS |
| `SURVEYPRO_SAMPLE_DATA_DIR` | `../sample_data` | Demo dataset location |
| `VITE_API_BASE` | `/api/v1` | Frontend API base (relative → proxied) |

---

## 8. Deliverable 1 scope & next slices

**In this repository (working end to end):** project/file/point/station/observation models with the
three-tier governance model, TXT + GSI ingestion with mapper and QA/QC, linework, constrained TIN,
contours, cut & fill, profiles, cross sections, layered DXF, CSV, GeoJSON, the dark engineering UI
with plan/GIS/3D canvases and the full API.

**Deliberately not scaffolded yet** (later slices, kept out to avoid empty placeholders): traverse
adjustment (least squares network), GNSS baseline processing, point-cloud registration, road design
(vertical alignment / superelevation), sewer & utility networks, quantity take-off reporting and
multi-user roles/permissions.
