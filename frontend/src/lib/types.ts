/** Domain types mirroring the FastAPI schemas. */

export type PointStatus = "RAW" | "VALIDATED" | "APPROVED" | "REJECTED";

export interface CrsAxis {
  name: string;
  abbrev: string;
  direction: string;
  unit: string;
}

export interface CrsInfo {
  epsg: number;
  name: string;
  datum?: string | null;
  is_projected?: boolean;
  is_geographic?: boolean;
  axis?: CrsAxis[];
  area_of_use?: { name: string } | null;
}

export interface Counters {
  points: Record<string, number>;
  points_total: number;
  derived: Record<string, number>;
}

export interface Project {
  id: string;
  name: string;
  code?: string | null;
  description?: string | null;
  client?: string | null;
  location?: string | null;
  surveyor?: string | null;
  crs_epsg: number;
  vertical_datum: string;
  linear_unit: string;
  angle_unit: string;
  duplicate_xy_tolerance: number;
  duplicate_z_tolerance: number;
  z_mad_threshold: number;
  local_z_step_threshold: number;
  tin_boundary_mode: string;
  contour_interval: number;
  breakline_codes: string[];
  status: string;
  dependency_state: string;
  created_at?: string;
  updated_at?: string;
  counters?: Counters;
  crs?: CrsInfo | null;
  files?: ProjectFile[];
  code_mappings?: CodeMapping[];
  layers?: LayerStandard[];
  derived?: DerivedOutput[];
}

export interface ProjectFile {
  id: string;
  project_id: string;
  original_filename: string;
  file_format: string;
  encoding?: string | null;
  delimiter?: string | null;
  status: string;
  row_count: number;
  imported_points: number;
  size_bytes: number;
  sha256: string;
  notes?: string | null;
  import_log?: Record<string, unknown> | null;
  created_at?: string;
}

export interface ColumnProfile {
  index: number;
  header?: string | null;
  sample: string[];
  numeric_ratio: number;
  integer_ratio: number;
  distinct_ratio: number;
  min?: number | null;
  max?: number | null;
  mean?: number | null;
  mean_decimals: number;
  alpha_ratio: number;
  max_token_length: number;
  sequential_ratio: number;
}

export interface ColumnMapping {
  point_number: number | null;
  easting: number | null;
  northing: number | null;
  elevation: number | null;
  code: number | null;
  description: number | null;
  has_header: boolean;
  delimiter: string;
}

export interface Issue {
  severity: "info" | "warning" | "error";
  code: string;
  message: string;
  line_no?: number | null;
  column?: string | null;
  value?: string | null;
}

export interface QaFlag {
  code: string;
  severity: string;
  message: string;
  point_numbers: string[];
  indices: number[];
  metric?: number | null;
  suggestion?: string | null;
}

export interface QaReport {
  flags: QaFlag[];
  summary: {
    points?: number;
    with_elevation?: number;
    unique_codes?: number;
    extent_easting?: [number, number];
    extent_northing?: [number, number];
    convex_hull_area_m2?: number;
    point_density_per_ha?: number | null;
    flag_counts?: Record<string, number>;
    flagged_points?: number;
    axis_swap?: { swap_suspected: boolean; confidence: number; reason: string };
  };
  point_severity?: Record<string, string>;
}

export interface SurveyPoint {
  id: string;
  project_id: string;
  file_id?: string | null;
  point_number: string;
  easting: number;
  northing: number;
  elevation: number | null;
  code: string;
  description: string;
  layer: string;
  status: PointStatus;
  version: number;
  source_order: number;
  line_no?: number | null;
  qa_severity?: string | null;
  qa_flags?: string | null;
}

export interface PreviewPoint {
  point_number: string;
  easting: number;
  northing: number;
  elevation: number | null;
  code: string;
  description?: string;
  line_no?: number | null;
}

export interface AnalysisPayload {
  format: string;
  encoding: string;
  encoding_notes: string[];
  delimiter?: string;
  delimiter_label?: string;
  delimiter_scores?: Record<string, number>;
  header_detected: boolean;
  header_tokens: string[];
  row_count: number;
  token_count_mode?: number;
  columns: ColumnProfile[];
  /** Mapper as returned by the parser heuristics (server field is `mapping`). */
  mapping: ColumnMapping;
  suggested_mapping?: ColumnMapping;
  confidence: Record<string, number>;
  rows_preview: string[][];
  points: PreviewPoint[];
  preview_truncated?: boolean;
  issues?: Issue[];
  parse_issues: Issue[];
  analysis_issues?: Issue[];
  stats: Record<string, unknown>;
  qa: QaReport;
}

export interface CodeMapping {
  id?: string;
  code: string;
  kind: "block" | "line" | "polygon" | "point";
  layer: string;
  block_name?: string | null;
  color: number;
  description?: string | null;
  is_breakline: boolean;
  enabled: boolean;
}

export interface LayerStandard {
  id?: string;
  name: string;
  color: number;
  linetype: string;
  description?: string | null;
  visible: boolean;
}

export interface LineworkFeature {
  name: string;
  base_code: string;
  kind: "line" | "polygon";
  layer: string;
  vertices: [number, number, number][];
  point_numbers: string[];
  closed: boolean;
  length: number;
  area: number;
  closure_error: number | null;
}

export interface LineworkResult {
  features: LineworkFeature[];
  issues: Issue[];
  stats: Record<string, unknown>;
}

export interface TinMeshPayload {
  vertices: [number, number, number][];
  faces: number[][];
  boundary: [number, number][] | null;
  boundary_source: string;
  constrained: boolean;
  engine: string;
  stats: Record<string, number | string | boolean | null>;
}

export interface ContourLine {
  elevation: number;
  is_major: boolean;
  index: number;
  closed: boolean;
  length: number;
  points: [number, number, number][];
  layer: string;
}

export interface SurfacePayload {
  kind?: string;
  stats: Record<string, any>;
  mesh: TinMeshPayload;
  contours: ContourLine[];
  contour_interval: number;
  contour_method: string;
  breaklines: { name: string; vertices: [number, number, number][] }[];
  linework?: LineworkResult;
  issues: Issue[];
  boundary?: [number, number][];
  extent: Record<string, number>;
  center: [number, number, number];
  output?: DerivedOutput;
}

export interface VolumeResult {
  method: string;
  cut_m3: number;
  fill_m3: number;
  net_m3: number;
  cell_size?: number;
  cut_area_m2?: number;
  fill_area_m2?: number;
  total_area_m2?: number;
  max_cut_depth?: number;
  max_fill_depth?: number;
  mean_cut_depth?: number;
  mean_fill_depth?: number;
  overlap_area_m2?: number;
  length_m?: number;
  sections?: { station: number; cut_area_m2: number; fill_area_m2: number }[];
  output?: DerivedOutput;
}

export interface ProfileSample {
  station: number;
  offsets: Record<
    string,
    {
      easting: number;
      northing: number;
      elevation: number | null;
      design_elevation: number | null;
      depth: number | null;
    }
  >;
}

export interface ProfileResult {
  length_m: number;
  station_interval: number;
  offsets: number[];
  samples: ProfileSample[];
  min_elevation: number | null;
  max_elevation: number | null;
  alignment: [number, number][];
  output?: DerivedOutput;
}

export interface CrossSection {
  station: number;
  centre: [number, number];
  offsets: number[];
  eastings: number[];
  northings: number[];
  elevations: (number | null)[];
}

export interface CrossSectionResult {
  sections: { station: number; existing: CrossSection; proposed: CrossSection | null }[];
  average_end_area?: { cut_m3: number; fill_m3: number; net_m3: number; length_m: number };
}

export interface DerivedOutput {
  id: string;
  kind: string;
  name: string;
  status: "CURRENT" | "OUTDATED" | string;
  params: Record<string, unknown>;
  summary: Record<string, any>;
  source_hash?: string | null;
  source_point_count: number;
  depends_on: string[];
  created_at?: string;
  updated_at?: string;
}

export interface GeoJsonFeatureCollection {
  type: "FeatureCollection";
  features: GeoJSON.Feature[];
  bbox?: number[];
}
