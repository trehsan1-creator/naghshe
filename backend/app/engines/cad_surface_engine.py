"""
SurveyPro -- CAD & Surface Engine
=================================

Implements the computational core of the terrain workflow:

1. **Constrained Delaunay Triangulation (CDT)** for TIN surfaces.

   Breaklines (curb top/bottom, ridge lines, retaining walls) and the surface
   boundary are inserted as *constraints*.  Primary engine is Jonathan Shewchuk's
   ``triangle`` library (used by Triangle, QGIS and most commercial TIN engines) with
   the ``p`` (PSLG) switch, so every constraint is guaranteed to appear as an edge.
   When ``triangle`` is unavailable we fall back to a **conforming Delaunay**
   implementation: segments that are not yet edges are split at their midpoints and the
   triangulation is rebuilt until all constraints are present (a documented, terminating
   algorithm -- not an approximation).

2. **Contours** -- minor/index intervals, from either
   * ``tin``: exact marching-triangles on the CDT (each contour vertex is a linear
     interpolation on a real triangle edge), or
   * ``grid``: resample the TIN to a regular grid and hand it to ``contourpy``
     (marching squares), which is what most CAD deliverables expect.

3. **Volumes** -- three independent, textbook methods:
   * ``grid``: prismoidal summation over a regular cell grid clipped to the overlap of
     both surfaces,
   * ``prism_to_datum``: exact triangle prism integration against a design plane,
   * ``average_end_area``: classic Average End Area between cross sections.

4. **Profiles and cross sections** along an alignment, sampled from the TIN.

5. **DXF export** through ``ezdxf``: layered, blocked, 3DFACE mesh, LWPolylines with
   elevation, ready for AutoCAD/BricsCAD/QGIS.

All geometry is computed with ``numpy``/``scipy``/``shapely``; no placeholder returns.
"""

from __future__ import annotations

import io
import math
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np

try:  # constrained Delaunay (preferred)
    import triangle as _triangle
except Exception:  # pragma: no cover
    _triangle = None

from scipy.spatial import Delaunay, cKDTree

from shapely.geometry import LineString, MultiPoint, Point, Polygon, MultiPolygon
from shapely.ops import unary_union

from .linework_engine import (
    DEFAULT_CODE_LIBRARY,
    DEFAULT_LAYERS,
    CodeDefinition,
    LineworkFeature,
    lookup_definition,
)
from .txt_gsi_parser import Issue

__all__ = [
    "TinMesh",
    "build_tin",
    "interpolate_mesh",
    "sample_mesh",
    "generate_contours",
    "prism_volume_to_datum",
    "cut_fill_grid",
    "average_end_area",
    "build_alignment",
    "profile_along_alignment",
    "cross_section",
    "cut_fill_from_sections",
    "export_dxf",
    "mesh_stats",
]

COLOR_CUT = 1     # red
COLOR_FILL = 3    # green


# --------------------------------------------------------------------------------------
# TIN
# --------------------------------------------------------------------------------------
@dataclass
class TinMesh:
    """A triangulated surface: vertices (N x 3), faces (M x 3 indices), boundary."""

    vertices: np.ndarray
    faces: np.ndarray
    boundary: Optional[Polygon] = None
    boundary_source: str = "convex_hull"
    segments: np.ndarray = field(default_factory=lambda: np.zeros((0, 2), dtype=np.int32))
    constrained: bool = False          # True when 3D breaklines constrained the mesh
    breakline_edges: int = 0
    engine: str = "triangle"

    # lazily built point locator
    _centroids: Optional[np.ndarray] = None
    _tree: Optional[cKDTree] = None

    # -- basic geometry --------------------------------------------------------------
    @property
    def xy(self) -> np.ndarray:
        return self.vertices[:, :2]

    @property
    def z(self) -> np.ndarray:
        return self.vertices[:, 2]

    def triangle_coords(self) -> np.ndarray:
        return self.vertices[self.faces]  # (M, 3, 3)

    def areas(self) -> np.ndarray:
        tri = self.triangle_coords()
        a = tri[:, 1, :2] - tri[:, 0, :2]
        b = tri[:, 2, :2] - tri[:, 0, :2]
        return np.abs(a[:, 0] * b[:, 1] - a[:, 1] * b[:, 0]) * 0.5

    def locator(self) -> Tuple[np.ndarray, cKDTree]:
        if self._centroids is None or self._tree is None:
            self._centroids = self.triangle_coords()[:, :, :2].mean(axis=1)
            self._tree = cKDTree(self._centroids)
        return self._centroids, self._tree

    def as_payload(self, max_faces: Optional[int] = None) -> Dict[str, Any]:
        """Compact JSON payload for the 3D viewer."""
        faces = self.faces if max_faces is None or len(self.faces) <= max_faces else self.faces[:max_faces]
        return {
            "vertices": np.round(self.vertices, 4).tolist(),
            "faces": faces.astype(int).tolist(),
            "boundary": (
                [[round(x, 4), round(y, 4)] for x, y in self.boundary.exterior.coords]
                if self.boundary is not None and self.boundary.geom_type == "Polygon"
                else None
            ),
            "boundary_source": self.boundary_source,
            "constrained": bool(self.constrained),
            "engine": self.engine,
            "stats": self.stats(),
        }

    def stats(self) -> Dict[str, Any]:
        areas = self.areas()
        z = self.z
        return {
            "vertices": int(len(self.vertices)),
            "triangles": int(len(self.faces)),
            "area_m2": round(float(areas.sum()), 3),
            "min_z": round(float(z.min()), 4) if len(z) else None,
            "max_z": round(float(z.max()), 4) if len(z) else None,
            "mean_z": round(float(z.mean()), 4) if len(z) else None,
            "boundary_area_m2": round(float(self.boundary.area), 3) if self.boundary is not None else None,
            "boundary_source": self.boundary_source,
            "constrained": bool(self.constrained),
            "constraint_edges": int(len(self.segments)),
            "breakline_edges": self.breakline_edges,
            "engine": self.engine,
        }


def _extract_xyz(points: Sequence[Dict[str, Any]]) -> Tuple[np.ndarray, List[str], List[str]]:
    if not points:
        return np.zeros((0, 3)), [], []
    xyz = np.array(
        [
            [float(p["easting"]), float(p["northing"]), float(p.get("elevation") or 0.0)]
            for p in points
        ],
        dtype=float,
    )
    numbers = [str(p.get("point_number", "")) for p in points]
    codes = [str(p.get("code") or "") for p in points]
    return xyz, numbers, codes


def _dedupe_vertices(
    xyz: np.ndarray, tol: float = 1e-6
) -> Tuple[np.ndarray, np.ndarray]:
    """Merge vertices that coincide in planimetry.

    Returns the unique vertex array and an index map (original -> unique).
    A TIN cannot hold two vertices at the same XY; the *highest* Z wins, which is the
    standard convention (the surface is the upper envelope of stacked observations).
    """
    if len(xyz) == 0:
        return xyz, np.zeros(0, dtype=np.int64)
    quant = np.round(xyz[:, :2] / max(tol, 1e-9)).astype(np.int64)
    mapping: Dict[Tuple[int, int], int] = {}
    index_map = np.zeros(len(xyz), dtype=np.int64)
    unique: List[List[float]] = []
    for i, key in enumerate(map(tuple, quant)):
        if key in mapping:
            j = mapping[key]
            index_map[i] = j
            if xyz[i, 2] > unique[j][2]:
                unique[j][2] = float(xyz[i, 2])
        else:
            mapping[key] = len(unique)
            index_map[i] = len(unique)
            unique.append([float(xyz[i, 0]), float(xyz[i, 1]), float(xyz[i, 2])])
    return np.array(unique, dtype=float), index_map


def _ensure_constraint_vertices(
    vertices: np.ndarray,
    ring: Sequence[Sequence[float]],
    tol: float,
    snap_tolerance: float = 0.02,
) -> Tuple[np.ndarray, List[int]]:
    """Add ring / breakline vertices to the vertex array, returning their indices.

    Constraint vertices that already exist on the surface are re-used, never duplicated:
    a TIN cannot hold two vertices at the same location.  ``snap_tolerance`` controls how
    far (metres, planimetry) a breakline vertex may be from an existing surface vertex and
    still be merged onto it.

    This matters when the *same* planimetric breaklines are applied to two surfaces (e.g.
    existing ground vs proposed ground): the breakline vertex carries the elevation of the
    surface it was digitised on, and merging must keep *this* surface's elevation rather
    than importing a foreign one.
    """
    out_vertices = vertices
    indices: List[int] = []
    for coord in ring:
        x, y = float(coord[0]), float(coord[1])
        z = float(coord[2]) if len(coord) > 2 else None
        if len(out_vertices):
            d = np.hypot(out_vertices[:, 0] - x, out_vertices[:, 1] - y)
            nearest = int(np.argmin(d))
            if d[nearest] <= max(tol, 1e-6):
                indices.append(nearest)
                continue
            if snap_tolerance > 0 and d[nearest] <= snap_tolerance:
                indices.append(nearest)
                continue
        z_value = z if z is not None else _nearest_z(out_vertices, x, y)
        out_vertices = np.vstack([out_vertices, [x, y, z_value]])
        indices.append(len(out_vertices) - 1)
    return out_vertices, indices


def _nearest_z(vertices: np.ndarray, x: float, y: float) -> float:
    if len(vertices) == 0:
        return 0.0
    d = np.hypot(vertices[:, 0] - x, vertices[:, 1] - y)
    return float(vertices[int(np.argmin(d)), 2])


def _boundary_polygon(
    xy: np.ndarray, mode: str, ratio: float, user_boundary: Optional[Sequence[Sequence[float]]]
) -> Tuple[Optional[Polygon], str]:
    """Determine the TIN boundary (user polygon, concave hull or convex hull)."""
    if mode == "polygon" and user_boundary:
        coords = [(float(c[0]), float(c[1])) for c in user_boundary]
        if len(coords) > 1 and coords[0] == coords[-1]:
            coords = coords[:-1]
        poly = Polygon(coords)
        if not poly.is_valid:
            poly = poly.buffer(0)
        if poly.geom_type == "MultiPolygon":
            poly = max(poly.geoms, key=lambda g: g.area)
        # Clip to the data extent: a surface cannot be invented where nothing was measured.
        data_hull = MultiPoint([tuple(p) for p in xy]).convex_hull
        clipped = poly.intersection(data_hull)
        if clipped.is_empty or clipped.area <= 0:
            raise ValueError("The requested boundary does not overlap the survey points.")
        if clipped.geom_type == "MultiPolygon":
            clipped = max(clipped.geoms, key=lambda g: g.area)
        return clipped, "user_polygon"

    if len(xy) < 3:
        return None, "none"

    multipoint = MultiPoint([tuple(p) for p in xy])
    if mode == "concave_hull":
        try:
            import shapely

            hull = shapely.concave_hull(multipoint, ratio=ratio)
            if hull.geom_type == "Polygon" and hull.area > 0:
                return hull, f"concave_hull(ratio={ratio})"
        except Exception:  # pragma: no cover - very old shapely
            pass
    return multipoint.convex_hull, "convex_hull"


def build_tin(
    points: Sequence[Dict[str, Any]],
    *,
    breaklines: Optional[Sequence[Dict[str, Any]]] = None,
    boundary_mode: str = "convex_hull",
    boundary: Optional[Sequence[Sequence[float]]] = None,
    concave_ratio: float = 0.15,
    tol: float = 1e-6,
    snap_tolerance: float = 0.02,
    use_cdt: bool = True,
) -> Tuple[TinMesh, List[Issue]]:
    """Build a constrained TIN from survey points + 3D breaklines + optional boundary.

    Parameters
    ----------
    points
        Dictionaries with ``easting``, ``northing``, ``elevation``.
    breaklines
        ``[{"name": str, "vertices": [[e, n, z], ...]}, ...]`` -- each polyline becomes a
        chain of constraint edges; the triangulation is forced to honour it, so a curb
        never gets crossed by a triangle.
    boundary_mode
        ``'convex_hull' | 'concave_hull' | 'polygon'``.
    """
    issues: List[Issue] = []
    xyz, numbers, codes = _extract_xyz(points)
    if len(xyz) < 3:
        raise ValueError("A TIN needs at least 3 points with planimetry.")

    finite = np.isfinite(xyz).all(axis=1)
    if not finite.all():
        dropped = int((~finite).sum())
        xyz = xyz[finite]
        issues.append(
            Issue("warning", "tin_invalid_points", f"{dropped} point(s) with non-finite coordinates excluded.")
        )
    if len(xyz) < 3:
        raise ValueError("Fewer than 3 valid points remain; cannot triangulate.")

    vertices, index_map = _dedupe_vertices(xyz, tol=tol)
    if len(vertices) < len(xyz):
        issues.append(
            Issue(
                "info",
                "tin_duplicate_vertices",
                f"{len(xyz) - len(vertices)} coincident point(s) merged before triangulation "
                "(highest elevation kept).",
            )
        )

    # ---- constraints (breaklines + boundary ring) --------------------------------
    segment_list: List[Tuple[int, int]] = []
    breakline_payload: List[Dict[str, Any]] = []

    for bl in breaklines or []:
        verts = bl.get("vertices") or []
        if len(verts) < 2:
            continue
        vertices, idx = _ensure_constraint_vertices(vertices, verts, tol, snap_tolerance)
        for a, b in zip(idx, idx[1:]):
            if a != b:
                segment_list.append((a, b))
        breakline_payload.append(
            {"name": bl.get("name", "BREAKLINE"), "vertices": [list(map(float, v)) for v in verts]}
        )

    # count only the breakline constraints (boundary-ring edges are added below)
    breakline_edge_count = len(segment_list)

    boundary_poly, boundary_source = _boundary_polygon(
        vertices[:, :2], boundary_mode, concave_ratio, boundary
    )
    # A PSLG needs a closed ring: without it Triangle has no domain to fill (an open
    # polyline encloses zero area).  The ring is therefore always part of the PSLG, which
    # also guarantees the surface never extends beyond the surveyed data.
    if boundary_poly is not None:
        ring = list(boundary_poly.exterior.coords)[:-1]
        vertices, idx = _ensure_constraint_vertices(vertices, ring, tol, snap_tolerance)
        for a, b in zip(idx, idx[1:] + idx[:1]):
            if a != b:
                segment_list.append((a, b))

    segments = np.array(sorted({(min(a, b), max(a, b)) for a, b in segment_list}), dtype=np.int32)
    if len(segments) == 0:
        segments = np.zeros((0, 2), dtype=np.int32)

    # ---- triangulate ---------------------------------------------------------------
    faces: np.ndarray
    engine = "triangle"
    if use_cdt and _triangle is not None:
        try:
            data: Dict[str, Any] = {"vertices": vertices[:, :2].astype(np.float64)}
            if len(segments):
                data["segments"] = segments
            options = "p" if len(segments) else ""
            out = _triangle.triangulate(data, options)
            out_vertices = np.asarray(out["vertices"], dtype=float)
            out_faces = np.asarray(out["triangles"], dtype=np.int64)
            if len(out_vertices) != len(vertices):
                # Steiner points would appear only if a quality switch is used; map Z back.
                extra = out_vertices[len(vertices):]
                z_extra = np.array([_nearest_z(vertices, p[0], p[1]) for p in extra])
                vertices = np.vstack([vertices, np.column_stack([extra, z_extra])])
            faces = out_faces
        except Exception as exc:  # pragma: no cover - defensive
            issues.append(
                Issue(
                    "warning",
                    "cdt_fallback",
                    f"Constrained triangulation failed ({exc}); using the conforming Delaunay fallback.",
                )
            )
            faces, vertices, engine = _conforming_delaunay(vertices, segments, tol)
    else:
        faces, vertices, engine = _conforming_delaunay(vertices, segments, tol)

    # ---- clean-up ------------------------------------------------------------------
    faces = _drop_degenerate_faces(vertices, faces)
    if boundary_poly is not None:
        faces = _clip_faces_to_boundary(vertices, faces, boundary_poly)
    if len(faces) == 0:
        raise ValueError("Triangulation produced no valid triangles (degenerate input?).")

    mesh = TinMesh(
        vertices=vertices,
        faces=faces,
        boundary=boundary_poly,
        boundary_source=boundary_source,
        segments=segments,
        constrained=breakline_edge_count > 0,
        breakline_edges=breakline_edge_count,
        engine=engine,
    )
    if len(mesh.faces) < 2:
        issues.append(Issue("warning", "tin_small", "TIN has fewer than 2 triangles."))
    return mesh, issues


def _drop_degenerate_faces(vertices: np.ndarray, faces: np.ndarray, area_tol: float = 1e-9) -> np.ndarray:
    if len(faces) == 0:
        return faces
    tri = vertices[faces][:, :, :2]
    a = tri[:, 1] - tri[:, 0]
    b = tri[:, 2] - tri[:, 0]
    area = np.abs(a[:, 0] * b[:, 1] - a[:, 1] * b[:, 0]) * 0.5
    keep = area > area_tol
    return faces[keep]


def _clip_faces_to_boundary(vertices: np.ndarray, faces: np.ndarray, boundary: Polygon) -> np.ndarray:
    """Keep triangles whose centroid lies inside the surface boundary."""
    if len(faces) == 0 or boundary is None:
        return faces
    centroids = vertices[faces][:, :, :2].mean(axis=1)
    try:
        from shapely import contains_xy

        inside = contains_xy(boundary, centroids[:, 0], centroids[:, 1])
        return faces[np.asarray(inside, dtype=bool)]
    except Exception:  # pragma: no cover
        return np.array(
            [f for f, c in zip(faces, centroids) if boundary.contains(Point(float(c[0]), float(c[1])))],
            dtype=np.int64,
        )


def _conforming_delaunay(
    vertices: np.ndarray, segments: np.ndarray, tol: float = 1e-6, max_iterations: int = 40
) -> Tuple[np.ndarray, np.ndarray, str]:
    """Conforming Delaunay triangulation by recursive midpoint insertion.

    For a constraint segment that is not present as a triangulation edge, split it at its
    midpoint, insert the point and retriangulate.  Every iteration halves at least one
    segment, so the process terminates with all constraints present as edge chains.
    This is the classic Conforming-Delaunay construction (Ruppert/Edelsbrunner), and it
    never leaves a breakline crossed by a triangle edge.
    """
    verts = np.array(vertices, dtype=float)
    segs = [tuple(map(int, s)) for s in np.asarray(segments).reshape(-1, 2)]
    if not segs:
        if len(verts) < 3:
            return np.zeros((0, 3), dtype=np.int64), verts, "conforming_delaunay"
        tri = Delaunay(verts[:, :2])
        return tri.simplices.astype(np.int64), verts, "scipy_delaunay"

    working = list(segs)
    for _ in range(max_iterations):
        if len(verts) < 3:
            break
        try:
            tri = Delaunay(verts[:, :2])
        except Exception:
            break
        simp = tri.simplices
        edges = set()
        for s in simp:
            for a, b in ((s[0], s[1]), (s[1], s[2]), (s[2], s[0])):
                edges.add((min(a, b), max(a, b)))
        missing = [s for s in working if s not in edges]
        if not missing:
            return simp.astype(np.int64), verts, "conforming_delaunay"
        new_points: List[List[float]] = []
        next_segments: List[Tuple[int, int]] = []
        for a, b in missing:
            pa, pb = verts[a, :2], verts[b, :2]
            length = float(np.hypot(*(pb - pa)))
            if length <= max(tol * 4.0, 1e-7):
                next_segments.append((a, b))  # cannot split further; accept
                continue
            mid_xy = (pa + pb) / 2.0
            z = (verts[a, 2] + verts[b, 2]) / 2.0
            new_points.append([mid_xy[0], mid_xy[1], z])
            next_segments.append((a, b))  # replaced below once indices are known
        if not new_points:
            break
        base = len(verts)
        verts = np.vstack([verts, np.array(new_points, dtype=float)])
        # rebuild segments: each missing segment is split at its new midpoint
        mid_index = {i: base + i for i in range(len(new_points))}
        rebuilt: List[Tuple[int, int]] = []
        split_index = 0
        for seg in working:
            if seg in missing:
                m = mid_index[split_index]
                split_index += 1
                rebuilt.append((seg[0], m))
                rebuilt.append((m, seg[1]))
            else:
                rebuilt.append(seg)
        working = rebuilt

    tri = Delaunay(verts[:, :2])
    return tri.simplices.astype(np.int64), verts, "conforming_delaunay"


# --------------------------------------------------------------------------------------
# Interpolation / sampling
# --------------------------------------------------------------------------------------
def sample_mesh(mesh: TinMesh, xs: np.ndarray, ys: np.ndarray, k: int = 12) -> np.ndarray:
    """Bilinearly interpolate the TIN at arbitrary points (NaN outside the surface).

    Point location uses a KD-tree on triangle centroids followed by an exact barycentric
    containment test, so the sampled surface honours breaklines (a sample never
    interpolates across a curb).
    """
    xs = np.asarray(xs, dtype=float).ravel()
    ys = np.asarray(ys, dtype=float).ravel()
    out = np.full(xs.shape, np.nan)
    if len(mesh.faces) == 0 or len(xs) == 0:
        return out
    centroids, tree = mesh.locator()
    tri = mesh.triangle_coords()  # (M,3,3)
    kk = int(min(max(k, 3), len(centroids)))
    _, idx = tree.query(np.column_stack([xs, ys]), k=kk)
    idx = np.atleast_2d(idx)
    if idx.shape[0] == 1 and len(xs) > 1:  # pragma: no cover - shape guard
        idx = idx.T
    for i in range(len(xs)):
        x, y = xs[i], ys[i]
        for j in idx[i]:
            v = tri[int(j)]
            z = _barycentric_z(v, x, y)
            if z is not None:
                out[i] = z
                break
        else:
            # fall back to the nearest triangle extrapolated (edge case: on a hull edge)
            continue
    return out


def _barycentric_z(triangle: np.ndarray, x: float, y: float, eps: float = 1e-9) -> Optional[float]:
    x1, y1, z1 = triangle[0]
    x2, y2, z2 = triangle[1]
    x3, y3, z3 = triangle[2]
    det = (y2 - y3) * (x1 - x3) + (x3 - x2) * (y1 - y3)
    if abs(det) < 1e-12:
        return None
    l1 = ((y2 - y3) * (x - x3) + (x3 - x2) * (y - y3)) / det
    l2 = ((y3 - y1) * (x - x3) + (x1 - x3) * (y - y3)) / det
    l3 = 1.0 - l1 - l2
    tol = -1e-9
    if l1 < tol or l2 < tol or l3 < tol:
        return None
    return float(l1 * z1 + l2 * z2 + l3 * z3)


def interpolate_mesh(mesh: TinMesh, x: float, y: float) -> Optional[float]:
    z = sample_mesh(mesh, np.array([x]), np.array([y]))
    return None if math.isnan(z[0]) else float(z[0])


def sample_grid(
    mesh: TinMesh, resolution: float, bbox: Optional[Tuple[float, float, float, float]] = None
) -> Dict[str, Any]:
    """Resample a TIN onto a regular grid (masked outside the boundary)."""
    if resolution <= 0:
        raise ValueError("Grid resolution must be positive")
    if bbox is None:
        if mesh.boundary is not None:
            minx, miny, maxx, maxy = mesh.boundary.bounds
        else:
            minx, miny = mesh.vertices[:, 0].min(), mesh.vertices[:, 1].min()
            maxx, maxy = mesh.vertices[:, 0].max(), mesh.vertices[:, 1].max()
    else:
        minx, miny, maxx, maxy = bbox
    nx = max(2, int(math.ceil((maxx - minx) / resolution)) + 1)
    ny = max(2, int(math.ceil((maxy - miny) / resolution)) + 1)
    if nx * ny > 16_000_000:
        raise ValueError(
            f"Grid too large ({nx}x{ny}); increase the cell size or reduce the extent."
        )
    xs = minx + np.arange(nx) * resolution
    ys = miny + np.arange(ny) * resolution
    gx, gy = np.meshgrid(xs, ys)
    z = sample_mesh(mesh, gx.ravel(), gy.ravel()).reshape(gy.shape)
    mask = np.isnan(z)
    return {"x": xs, "y": ys, "z": z, "mask": mask, "resolution": resolution,
            "bbox": [minx, miny, maxx, maxy], "nx": nx, "ny": ny}


# --------------------------------------------------------------------------------------
# Contours
# --------------------------------------------------------------------------------------
def _chain_segments(segments: Sequence[Tuple[Tuple[float, float], Tuple[float, float]]],
                    tol: float = 1e-7) -> List[List[Tuple[float, float]]]:
    """Stitch unordered contour segments into polylines (handles open and closed)."""
    if not segments:
        return []

    def key(p: Tuple[float, float]) -> Tuple[int, int]:
        return (int(round(p[0] / tol)), int(round(p[1] / tol)))

    adjacency: Dict[Tuple[int, int], List[Tuple[Tuple[int, int], int]]] = {}
    coords: Dict[Tuple[int, int], Tuple[float, float]] = {}
    for i, (a, b) in enumerate(segments):
        ka, kb = key(a), key(b)
        coords[ka] = a
        coords[kb] = b
        adjacency.setdefault(ka, []).append((kb, i))
        adjacency.setdefault(kb, []).append((ka, i))

    used = [False] * len(segments)
    polylines: List[List[Tuple[float, float]]] = []

    def walk(start: Tuple[int, int]) -> List[Tuple[float, float]]:
        path = [coords[start]]
        current = start
        while True:
            step = None
            for nxt, edge in adjacency.get(current, []):
                if not used[edge]:
                    step = (nxt, edge)
                    break
            if step is None:
                break
            nxt, edge = step
            used[edge] = True
            current = nxt
            path.append(coords[current])
            if current == start:
                break
        return path

    # open ends first, then remaining closed loops
    for node, links in adjacency.items():
        if len(links) == 1:
            path = walk(node)
            if len(path) > 1:
                polylines.append(path)
    for i, (a, b) in enumerate(segments):
        if not used[i]:
            path = walk(key(a))
            if len(path) > 1:
                polylines.append(path)
    return polylines


def generate_contours(
    mesh: TinMesh,
    interval: float = 0.25,
    *,
    major_every: int = 4,
    method: str = "grid",
    resolution: Optional[float] = None,
    base: Optional[float] = None,
) -> List[Dict[str, Any]]:
    """Extract contour lines at ``interval`` metres, with an index (major) contour every
    ``major_every`` lines.  Returns polylines with their elevation and length."""
    if interval <= 0:
        raise ValueError("Contour interval must be positive")
    z = mesh.z
    if len(z) == 0:
        return []
    zmin, zmax = float(np.nanmin(z)), float(np.nanmax(z))
    start = math.floor(zmin / interval) * interval if base is None else base
    levels: List[float] = []
    level = start
    while level <= zmax + interval:
        if level >= zmin - 1e-9:
            levels.append(round(level, 6))
        level += interval

    contours: List[Dict[str, Any]] = []

    if method == "grid":
        grid = sample_grid(mesh, resolution or max(interval, 0.5))
        try:
            from contourpy import LineType, contour_generator

            masked = np.ma.masked_invalid(grid["z"])
            cg = contour_generator(
                x=grid["x"], y=grid["y"], z=masked, line_type=LineType.Separate
            )
            for lvl in levels:
                for line in cg.lines(lvl):
                    if len(line) < 2:
                        continue
                    pts = [(float(p[0]), float(p[1])) for p in line]
                    contours.append(_contour_record(pts, lvl, start, interval, major_every))
        except Exception as exc:  # pragma: no cover
            raise RuntimeError(f"contourpy failed: {exc}") from exc
    else:  # exact marching triangles on the CDT
        tri = mesh.triangle_coords()
        for lvl in levels:
            segments: List[Tuple[Tuple[float, float], Tuple[float, float]]] = []
            v0, v1, v2 = tri[:, 0, :], tri[:, 1, :], tri[:, 2, :]
            above = (v0[:, 2] >= lvl).astype(np.int8) + (v1[:, 2] >= lvl) + (v2[:, 2] >= lvl)
            candidate = (above > 0) & (above < 3)
            for tri_index in np.where(candidate)[0]:
                seg = _triangle_contour_segment(tri[tri_index], lvl)
                if seg is not None:
                    segments.append(seg)
            for pts in _chain_segments(segments):
                contours.append(_contour_record(pts, lvl, start, interval, major_every))
    return contours


def _contour_record(
    pts: List[Tuple[float, float]], level: float, start: float, interval: float, major_every: int
) -> Dict[str, Any]:
    # numpy scalars must never leak into the JSON payload
    pts = [(float(x), float(y)) for x, y in pts]
    index = int(round((float(level) - float(start)) / interval))
    closed = bool(
        len(pts) > 3
        and abs(pts[0][0] - pts[-1][0]) < 1e-6
        and abs(pts[0][1] - pts[-1][1]) < 1e-6
    )
    length = float(sum(math.dist(a, b) for a, b in zip(pts, pts[1:])))
    is_major = bool(major_every > 0 and index % major_every == 0)
    return {
        "elevation": round(float(level), 4),
        "is_major": is_major,
        "index": index,
        "closed": closed,
        "length": round(length, 3),
        "points": [[round(x, 4), round(y, 4), round(level, 4)] for x, y in pts],
        "layer": "S-CONTOUR-MAJOR" if is_major else "S-CONTOUR-MINOR",
    }


def _triangle_contour_segment(
    triangle: np.ndarray, level: float
) -> Optional[Tuple[Tuple[float, float], Tuple[float, float]]]:
    """Intersect one triangle with a horizontal plane (marching triangles)."""
    pts: List[Tuple[float, float]] = []
    for i, j in ((0, 1), (1, 2), (2, 0)):
        x1, y1, z1 = triangle[i]
        x2, y2, z2 = triangle[j]
        if abs(z1 - z2) < 1e-12:
            continue
        if (z1 - level) * (z2 - level) <= 0:
            t = (level - z1) / (z2 - z1)
            if -1e-9 <= t <= 1 + 1e-9:
                pts.append((x1 + t * (x2 - x1), y1 + t * (y2 - y1)))
    if len(pts) < 2:
        return None
    a, b = pts[0], pts[1]
    if math.dist(a, b) < 1e-9:
        return None
    return (a, b)


# --------------------------------------------------------------------------------------
# Volumes
# --------------------------------------------------------------------------------------
def prism_volume_to_datum(mesh: TinMesh, datum_z: float) -> Dict[str, Any]:
    """Exact prism integration of a TIN against a horizontal design plane.

    For a planar triangle the vertical prism volume is exactly
    ``area * (mean of nodal height differences)`` -- the classic TIN prism method.
    """
    tri = mesh.triangle_coords()
    areas = mesh.areas()
    dz = tri[:, :, 2] - datum_z
    mean_dz = dz.mean(axis=1)
    cell = areas * mean_dz
    cut = float(cell[cell > 0].sum())
    fill = float(-cell[cell < 0].sum())
    return {
        "method": "prism_to_datum",
        "datum_z": round(float(datum_z), 4),
        "cut_m3": round(cut, 3),
        "fill_m3": round(fill, 3),
        "net_m3": round(cut - fill, 3),
        "area_m2": round(float(areas.sum()), 3),
        "triangles": int(len(areas)),
    }


def cut_fill_grid(
    existing: TinMesh,
    proposed: TinMesh,
    cell_size: float = 0.5,
    *,
    boundary: Optional[Polygon] = None,
    max_cells: int = 4_000_000,
) -> Dict[str, Any]:
    """Prismoidal cut & fill between two surfaces on a regular cell grid.

    Each cell is evaluated at its four corners (prismoidal, not centre-sampled), clipped
    to the overlap of both surfaces.  Cut is where existing ground is above proposed,
    fill where it is below.
    """
    if cell_size <= 0:
        raise ValueError("Cell size must be positive")
    if existing.boundary is not None and proposed.boundary is not None:
        overlap = existing.boundary.intersection(proposed.boundary)
    elif existing.boundary is not None:
        overlap = existing.boundary
    elif proposed.boundary is not None:
        overlap = proposed.boundary
    else:
        overlap = MultiPoint(list(map(tuple, existing.vertices[:, :2]))).convex_hull
    if boundary is not None:
        overlap = overlap.intersection(boundary)
    if overlap.is_empty:
        raise ValueError("The two surfaces do not overlap; there is no volume to compute.")
    if overlap.geom_type == "MultiPolygon":
        overlap = max(overlap.geoms, key=lambda g: g.area)

    minx, miny, maxx, maxy = overlap.bounds
    nx = int(math.ceil((maxx - minx) / cell_size)) + 1
    ny = int(math.ceil((maxy - miny) / cell_size)) + 1
    if nx * ny > max_cells:
        raise ValueError(
            f"Grid of {nx}x{ny} cells exceeds the {max_cells:,} cell limit; "
            "increase the cell size."
        )
    xs = minx + np.arange(nx) * cell_size
    ys = miny + np.arange(ny) * cell_size
    gx, gy = np.meshgrid(xs, ys)
    z_eg = sample_mesh(existing, gx.ravel(), gy.ravel()).reshape(gx.shape)
    z_pg = sample_mesh(proposed, gx.ravel(), gy.ravel()).reshape(gx.shape)

    # cell validity: all four corners inside both surfaces and inside the overlap
    valid = np.isfinite(z_eg) & np.isfinite(z_pg)
    cell_valid = valid[:-1, :-1] & valid[1:, :-1] & valid[:-1, 1:] & valid[1:, 1:]
    if overlap is not None:
        try:
            from shapely import contains_xy

            cx = (gx[:-1, :-1] + gx[1:, 1:]) / 2.0
            cy = (gy[:-1, :-1] + gy[1:, 1:]) / 2.0
            inside = contains_xy(overlap, cx, cy)
            cell_valid &= np.asarray(inside, dtype=bool)
        except Exception:  # pragma: no cover
            pass

    dz = np.zeros_like(cell_valid, dtype=float)
    dz = (
        (z_eg[:-1, :-1] - z_pg[:-1, :-1])
        + (z_eg[1:, :-1] - z_pg[1:, :-1])
        + (z_eg[:-1, 1:] - z_pg[:-1, 1:])
        + (z_eg[1:, 1:] - z_pg[1:, 1:])
    ) / 4.0
    cell_area = cell_size * cell_size
    effective = np.where(cell_valid, dz, 0.0)
    cut = float(np.sum(effective[effective > 0]) * cell_area)
    fill = float(-np.sum(effective[effective < 0]) * cell_area)
    cut_area = float(np.sum((effective > 0) & cell_valid) * cell_area)
    fill_area = float(np.sum((effective < 0) & cell_valid) * cell_area)
    zero_area = float(np.sum((effective == 0) & cell_valid) * cell_area)

    # depth statistics
    positives = effective[cell_valid & (effective > 0)]
    negatives = effective[cell_valid & (effective < 0)]
    return {
        "method": "grid_prismoidal",
        "cell_size": cell_size,
        "cells_used": int(cell_valid.sum()),
        "cut_m3": round(cut, 3),
        "fill_m3": round(fill, 3),
        "net_m3": round(cut - fill, 3),
        "cut_area_m2": round(cut_area, 3),
        "fill_area_m2": round(fill_area, 3),
        "unchanged_area_m2": round(zero_area, 3),
        "total_area_m2": round(cut_area + fill_area + zero_area, 3),
        "max_cut_depth": round(float(positives.max()), 4) if positives.size else 0.0,
        "max_fill_depth": round(float(-negatives.min()), 4) if negatives.size else 0.0,
        "mean_cut_depth": round(float(positives.mean()), 4) if positives.size else 0.0,
        "mean_fill_depth": round(float(-negatives.mean()), 4) if negatives.size else 0.0,
        "overlap_area_m2": round(float(overlap.area), 3),
    }


def average_end_area(
    stations: Sequence[float], areas: Sequence[float], *, is_cut: bool = True
) -> Dict[str, Any]:
    """Classic Average End Area volume from a list of cross-section areas.

    .. math:: V = \\sum_{i=1}^{n-1} \\frac{A_i + A_{i+1}}{2} \\,(L_{i+1} - L_i)
    """
    if len(stations) != len(areas):
        raise ValueError("stations and areas must have the same length")
    if len(stations) < 2:
        raise ValueError("Average End Area needs at least two sections")
    order = np.argsort(np.asarray(stations, dtype=float))
    s = np.asarray(stations, dtype=float)[order]
    a = np.asarray(areas, dtype=float)[order]
    if np.any(np.diff(s) < 0):
        raise ValueError("stations must be increasing after sorting")
    increments = (a[:-1] + a[1:]) / 2.0 * np.diff(s)
    return {
        "method": "average_end_area",
        "kind": "cut" if is_cut else "fill",
        "volume_m3": round(float(increments.sum()), 3),
        "length_m": round(float(s[-1] - s[0]), 3),
        "sections": int(len(s)),
        "segments": [
            {"from": round(float(s[i]), 3), "to": round(float(s[i + 1]), 3),
             "volume_m3": round(float(increments[i]), 3)}
            for i in range(len(increments))
        ],
    }


# --------------------------------------------------------------------------------------
# Alignment, profiles and cross sections
# --------------------------------------------------------------------------------------
def build_alignment(vertices: Sequence[Sequence[float]]) -> LineString:
    """Create a 2D alignment LineString (raises on fewer than two vertices)."""
    coords = [(float(v[0]), float(v[1])) for v in vertices]
    if len(coords) < 2:
        raise ValueError("An alignment needs at least two vertices")
    return LineString(coords)


def profile_along_alignment(
    mesh: TinMesh,
    alignment: LineString,
    *,
    station_interval: float = 5.0,
    design_mesh: Optional[TinMesh] = None,
    offsets: Sequence[float] = (0.0,),
) -> Dict[str, Any]:
    """Sample a longitudinal profile (and optional design surface) along an alignment.

    Samples are placed at ``station_interval`` plus the exact end station.  Several
    offsets can be requested at once (e.g. left/centre/right of a road).
    """
    if station_interval <= 0:
        raise ValueError("station interval must be positive")
    length = float(alignment.length)
    if length <= 0:
        raise ValueError("alignment has zero length")
    stations = list(np.arange(0.0, length, station_interval)) + [length]
    samples: List[Dict[str, Any]] = []
    for s in stations:
        point = alignment.interpolate(float(s))
        tangent = _tangent_at(alignment, float(s))
        normal = (-tangent[1], tangent[0])
        row: Dict[str, Any] = {"station": round(float(s), 3), "offsets": {}}
        for off in offsets:
            x = point.x + normal[0] * off
            y = point.y + normal[1] * off
            z = interpolate_mesh(mesh, x, y)
            z_design = interpolate_mesh(design_mesh, x, y) if design_mesh is not None else None
            row["offsets"][f"{off:g}"] = {
                "easting": round(x, 4),
                "northing": round(y, 4),
                "elevation": None if z is None else round(z, 4),
                "design_elevation": None if z_design is None else round(z_design, 4),
                "depth": None
                if (z is None or z_design is None)
                else round(z - z_design, 4),
            }
        samples.append(row)
    values = [s["offsets"]["0"]["elevation"] for s in samples if "0" in s["offsets"]]
    finite = [v for v in values if v is not None]
    return {
        "length_m": round(length, 3),
        "station_interval": station_interval,
        "offsets": list(offsets),
        "samples": samples,
        "min_elevation": round(min(finite), 4) if finite else None,
        "max_elevation": round(max(finite), 4) if finite else None,
        "alignment": [[round(x, 4), round(y, 4)] for x, y in alignment.coords],
    }


def _tangent_at(line: LineString, station: float) -> Tuple[float, float]:
    """Unit tangent of the alignment at a station (handles segment interiors)."""
    length = line.length
    s = min(max(station, 0.0), length)
    eps = max(min(0.5, length / 1000.0), 1e-6)
    a = line.interpolate(max(0.0, s - eps))
    b = line.interpolate(min(length, s + eps))
    dx, dy = b.x - a.x, b.y - a.y
    norm = math.hypot(dx, dy)
    if norm < 1e-12:
        coords = list(line.coords)
        for (x1, y1), (x2, y2) in zip(coords, coords[1:]):
            dx, dy = x2 - x1, y2 - y1
            norm = math.hypot(dx, dy)
            if norm > 1e-12:
                break
    return (dx / norm, dy / norm) if norm > 0 else (1.0, 0.0)


def cross_section(
    mesh: TinMesh,
    alignment: LineString,
    station: float,
    *,
    left: float = 10.0,
    right: float = 10.0,
    samples: int = 41,
) -> Dict[str, Any]:
    """Extract a cross section perpendicular to the alignment at a station.

    Offsets are signed: negative = left of the direction of travel.
    """
    if samples < 2:
        raise ValueError("samples must be >= 2")
    point = alignment.interpolate(min(max(station, 0.0), alignment.length))
    tangent = _tangent_at(alignment, station)
    normal = (-tangent[1], tangent[0])
    offsets = np.linspace(-abs(left), abs(right), samples)
    east = point.x + normal[0] * offsets
    north = point.y + normal[1] * offsets
    z = sample_mesh(mesh, east, north)
    return {
        "station": round(float(station), 3),
        "centre": [round(point.x, 4), round(point.y, 4)],
        "tangent": [round(tangent[0], 6), round(tangent[1], 6)],
        "offsets": [round(float(o), 3) for o in offsets],
        "eastings": [round(float(v), 4) for v in east],
        "northings": [round(float(v), 4) for v in north],
        "elevations": [None if math.isnan(v) else round(float(v), 4) for v in z],
    }


def cut_fill_from_sections(
    stations: Sequence[float],
    existing_sections: Sequence[Dict[str, Any]],
    proposed_sections: Sequence[Dict[str, Any]],
) -> Dict[str, Any]:
    """Average End Area cut & fill from paired cross sections.

    Each section is converted to a closed profile polygon; cut area is
    ``EG minus PG`` and fill area is ``PG minus EG`` (set difference of the areas
    below each profile), then integrated with the Average End Area formula.
    """
    if not (len(stations) == len(existing_sections) == len(proposed_sections)):
        raise ValueError("stations, existing and proposed sections must have equal length")
    cut_areas: List[float] = []
    fill_areas: List[float] = []
    rows: List[Dict[str, Any]] = []
    for st, eg_sec, pg_sec in zip(stations, existing_sections, proposed_sections):
        base = _common_base_level(eg_sec, pg_sec)
        eg_poly = _profile_polygon(eg_sec, base)
        pg_poly = _profile_polygon(pg_sec, base)
        if eg_poly is None or pg_poly is None:
            cut_areas.append(0.0)
            fill_areas.append(0.0)
            rows.append({"station": st, "cut_area_m2": 0.0, "fill_area_m2": 0.0})
            continue
        cut_poly = eg_poly.difference(pg_poly)
        fill_poly = pg_poly.difference(eg_poly)
        cut_areas.append(float(cut_poly.area))
        fill_areas.append(float(fill_poly.area))
        rows.append(
            {
                "station": round(float(st), 3),
                "cut_area_m2": round(float(cut_poly.area), 4),
                "fill_area_m2": round(float(fill_poly.area), 4),
            }
        )
    cut = average_end_area(stations, cut_areas, is_cut=True)
    fill = average_end_area(stations, fill_areas, is_cut=False)
    return {
        "method": "average_end_area",
        "cut_m3": cut["volume_m3"],
        "fill_m3": fill["volume_m3"],
        "net_m3": round(cut["volume_m3"] - fill["volume_m3"], 3),
        "length_m": cut["length_m"],
        "sections": rows,
        "cut_segments": cut["segments"],
        "fill_segments": fill["segments"],
    }


def _common_base_level(*sections: Dict[str, Any]) -> float:
    """Lowest valid elevation of a group of sections, minus one metre of headroom."""
    values: List[float] = []
    for section in sections:
        values.extend(float(z) for z in section.get("elevations", []) if z is not None)
    return (min(values) - 1.0) if values else 0.0


def _profile_polygon(section: Dict[str, Any], base: Optional[float] = None) -> Optional[Polygon]:
    """Close a cross-section profile into a polygon down to a common base level.

    Both profiles of a station must be closed at the *same* base, otherwise the set
    difference picks up the area below the deeper profile and inflates the volume.
    """
    pairs = [
        (float(o), float(z))
        for o, z in zip(section.get("offsets", []), section.get("elevations", []))
        if z is not None
    ]
    if len(pairs) < 2:
        return None
    if base is None:
        base = min(z for _, z in pairs) - 1.0
    ring = pairs + [(pairs[-1][0], base), (pairs[0][0], base)]
    poly = Polygon(ring)
    if not poly.is_valid:
        poly = poly.buffer(0)
        if poly.is_empty:
            return None
        if poly.geom_type == "MultiPolygon":
            poly = max(poly.geoms, key=lambda g: g.area)
    return poly


# --------------------------------------------------------------------------------------
# DXF export
# --------------------------------------------------------------------------------------
_BLOCK_SYMBOLS: Dict[str, Dict[str, Any]] = {
    "TR": {"shape": "tree", "size": 1.5, "label": "TREE"},
    "MH": {"shape": "manhole", "size": 0.35, "label": "MANHOLE"},
    "POLE": {"shape": "pole", "size": 0.15, "label": "POLE"},
    "LAMP": {"shape": "lamp", "size": 0.2, "label": "LAMP"},
    "BM": {"shape": "benchmark", "size": 0.4, "label": "BENCHMARK"},
}


def _define_blocks(doc) -> None:
    """Create the survey symbol blocks (real geometry, with attribute definitions)."""
    for name, spec in _BLOCK_SYMBOLS.items():
        block = doc.blocks.new(name=name, base_point=(0, 0, 0))
        size = spec["size"]
        shape = spec["shape"]
        if shape == "tree":
            block.add_circle((0, 0), size * 0.45)
            block.add_line((-size * 0.45, 0), (size * 0.45, 0))
            block.add_line((0, -size * 0.45), (0, size * 0.45))
        elif shape == "manhole":
            block.add_circle((0, 0), size)
            block.add_circle((0, 0), size * 0.65)
            block.add_line((-size, 0), (size, 0))
            block.add_line((0, -size), (0, size))
        elif shape == "pole":
            block.add_circle((0, 0), size)
            block.add_line((-size, 0), (size, 0))
            block.add_line((0, -size), (0, size))
        elif shape == "lamp":
            block.add_circle((0, 0), size)
            for k in range(6):
                ang = k * math.pi / 3.0
                block.add_line(
                    (math.cos(ang) * size, math.sin(ang) * size),
                    (math.cos(ang) * size * 2.0, math.sin(ang) * size * 2.0),
                )
        elif shape == "benchmark":
            block.add_line((-size, -size), (size, -size))
            block.add_line((-size, -size), (0, size))
            block.add_line((size, -size), (0, size))
        # attributes: point number, elevation, code
        for tag, prompt, index in (
            ("POINT", "Point number", 1),
            ("ELEV", "Elevation", 2),
            ("CODE", "Field code", 3),
        ):
            block.add_attdef(
                tag,
                (size * 1.2, size * (3 - index) * 0.6),
                dxfattribs={"height": max(size * 0.35, 0.12)},
            )


def export_dxf(
    *,
    points: Sequence[Dict[str, Any]],
    features: Optional[Sequence[LineworkFeature]] = None,
    mesh: Optional[TinMesh] = None,
    contours: Optional[Sequence[Dict[str, Any]]] = None,
    breaklines: Optional[Sequence[Dict[str, Any]]] = None,
    boundary: Optional[Sequence[Sequence[float]]] = None,
    alignment: Optional[Sequence[Sequence[float]]] = None,
    title: str = "SurveyPro export",
    code_library: Optional[Sequence[CodeDefinition]] = None,
    layers: Optional[Sequence[Dict[str, Any]]] = None,
    include_points: bool = True,
    include_tin: bool = True,
    include_contours: bool = True,
    label_points: bool = True,
) -> bytes:
    """Write a complete, layered DXF (DXF R2013) to bytes.

    Layers, blocks and entity types follow the survey layer standard so the file opens
    in AutoCAD/BricsCAD/QGIS with the expected colours and object structure.
    """
    import ezdxf
    from ezdxf.enums import TextEntityAlignment

    doc = ezdxf.new("R2013", setup=True)
    doc.units = ezdxf.units.M
    doc.header["$INSUNITS"] = 6  # metres
    doc.header["$MEASUREMENT"] = 1
    doc.header["$LTSCALE"] = 1.0

    wanted_layers: Dict[str, Dict[str, Any]] = {l["name"]: l for l in (layers or DEFAULT_LAYERS)}
    for layer_def in (layers or DEFAULT_LAYERS):
        name = layer_def["name"]
        if name not in doc.layers:
            layer = doc.layers.add(name, color=int(layer_def.get("color", 7)))
            linetype = layer_def.get("linetype", "CONTINUOUS")
            if linetype != "CONTINUOUS" and linetype in doc.linetypes:
                layer.dxf.linetype = linetype
    if "0" in doc.layers:
        doc.layers.get("0").dxf.color = 7

    _define_blocks(doc)
    msp = doc.modelspace()

    # ---- points -------------------------------------------------------------------
    lib = list(code_library) if code_library else DEFAULT_CODE_LIBRARY
    for p in points if include_points else []:
        x = float(p["easting"])
        y = float(p["northing"])
        z = float(p.get("elevation") or 0.0)
        code = str(p.get("code") or "").strip()
        definition = lookup_definition(_base_of(code), lib)
        layer = definition.layer if definition else "S-POINT"
        block_name = definition.block_name if definition and definition.kind == "block" else None

        msp.add_point((x, y, z), dxfattribs={"layer": layer})
        if block_name:
            insert = msp.add_blockref(block_name, (x, y), dxfattribs={"layer": layer})
            for tag, value in (
                ("POINT", str(p.get("point_number", ""))),
                ("ELEV", f"{z:.3f}"),
                ("CODE", code),
            ):
                insert.add_attrib(
                    tag, value, insert=(0.0, 0.0), dxfattribs={"layer": layer, "height": 0.25}
                )
        if label_points:
            if p.get("elevation") is not None:
                text = msp.add_text(
                    f"{z:.3f}", dxfattribs={"layer": "S-ELEV", "height": 0.35}
                )
                text.set_placement((x + 0.25, y + 0.25), align=TextEntityAlignment.LEFT)
            num = msp.add_text(
                str(p.get("point_number", "")),
                dxfattribs={"layer": "S-PN", "height": 0.28},
            )
            num.set_placement((x + 0.25, y - 0.55), align=TextEntityAlignment.LEFT)

    # ---- linework -----------------------------------------------------------------
    for feature in features or []:
        coords = [(float(v[0]), float(v[1])) for v in feature.vertices]
        if len(coords) < 2:
            continue
        elevation = float(feature.vertices[0][2]) if feature.vertices else 0.0
        msp.add_lwpolyline(
            coords,
            close=feature.closed,
            dxfattribs={"layer": feature.layer, "elevation": elevation},
        )

    # ---- breaklines ---------------------------------------------------------------
    for bl in breaklines or []:
        coords = [(float(v[0]), float(v[1]), float(v[2])) for v in bl.get("vertices", [])]
        if len(coords) >= 2:
            msp.add_polyline3d(coords, dxfattribs={"layer": "S-BREAKLINE"})

    # ---- boundary -----------------------------------------------------------------
    if boundary and len(boundary) >= 3:
        msp.add_lwpolyline(
            [(float(c[0]), float(c[1])) for c in boundary],
            close=True,
            dxfattribs={"layer": "S-BOUNDARY"},
        )

    # ---- TIN ----------------------------------------------------------------------
    if mesh is not None and include_tin:
        verts = mesh.vertices
        for face in mesh.faces:
            pts = [tuple(float(c) for c in verts[i]) for i in face]
            msp.add_3dface([pts[0], pts[1], pts[2], pts[2]], dxfattribs={"layer": "S-TIN"})

    # ---- contours -----------------------------------------------------------------
    if contours and include_contours:
        for contour in contours:
            pts = [(float(p[0]), float(p[1])) for p in contour["points"]]
            if len(pts) < 2:
                continue
            msp.add_lwpolyline(
                pts,
                close=bool(contour.get("closed")),
                dxfattribs={
                    "layer": contour.get("layer", "S-CONTOUR-MINOR"),
                    "elevation": float(contour["elevation"]),
                },
            )

    # ---- alignment ----------------------------------------------------------------
    if alignment and len(alignment) >= 2:
        msp.add_lwpolyline(
            [(float(c[0]), float(c[1])) for c in alignment], dxfattribs={"layer": "S-ALIGNMENT"}
        )

    # ---- title block text in model space -------------------------------------------
    if points:
        xs = [float(p["easting"]) for p in points]
        ys = [float(p["northing"]) for p in points]
        minx, miny, maxx, maxy = min(xs), min(ys), max(xs), max(ys)
        header = msp.add_text(
            title,
            dxfattribs={"layer": "S-SURFACE", "height": max((maxy - miny) * 0.02, 0.5)},
        )
        header.set_placement((minx, maxy + (maxy - miny) * 0.05), align=TextEntityAlignment.LEFT)
        doc.set_modelspace_vport(
            height=max(maxy - miny, 10.0) * 1.15,
            center=((minx + maxx) / 2.0, (miny + maxy) / 2.0),
        )

    stream = io.StringIO()
    doc.write(stream)
    return stream.getvalue().encode("utf-8")


def _base_of(code: str) -> str:
    from .linework_engine import parse_code_string

    return parse_code_string(code)["base"]


def mesh_stats(mesh: TinMesh) -> Dict[str, Any]:
    return mesh.stats()
