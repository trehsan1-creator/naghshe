"""Constrained Delaunay TIN, contours and interpolation."""

from __future__ import annotations

import math

import numpy as np
import pytest
from shapely.geometry import LineString

from app.engines import cad_surface_engine as surf


def test_tin_basic_topology(existing_tin, survey_points):
    mesh = existing_tin
    assert len(mesh.faces) > 0
    assert mesh.vertices.shape[1] == 3
    assert int(mesh.faces.max()) < len(mesh.vertices)
    # Euler characteristic for a triangulated disk: V - E + F = 1
    areas = mesh.areas()
    assert areas.min() > 0
    assert mesh.stats()["triangles"] == len(mesh.faces)


def test_tin_euler_characteristic(existing_tin):
    mesh = existing_tin
    edges = set()
    for a, b, c in mesh.faces:
        for u, v in ((a, b), (b, c), (c, a)):
            edges.add((min(int(u), int(v)), max(int(u), int(v))))
    v = len(mesh.vertices)
    e = len(edges)
    f = len(mesh.faces)
    # disk: V - E + F = 1  (boundary vertices lower the count; allow a small tolerance
    # for interior breakline vertices that are not part of any face when clipped)
    assert abs((v - e + f) - 1) <= max(2, v // 50)


def test_breaklines_are_honoured(existing_tin, breaklines):
    """No triangle edge may cross a breakline: this is the whole point of a CDT."""
    mesh = existing_tin
    assert mesh.constrained is True
    assert len(mesh.segments) > 0

    vertex_xy = mesh.vertices[:, :2]
    edges = set()
    for a, b, c in mesh.faces:
        edges.update({(min(a, b), max(a, b)), (min(b, c), max(b, c)), (min(c, a), max(c, a))})
    edge_lines = [LineString([vertex_xy[u], vertex_xy[v]]) for u, v in edges]

    from shapely.strtree import STRtree

    tree = STRtree(edge_lines)
    crossing = 0
    for u, v in mesh.segments:
        constraint = LineString([vertex_xy[int(u)], vertex_xy[int(v)]])
        for idx in tree.query(constraint):
            edge = edge_lines[int(idx)]
            if constraint.equals(edge):
                continue
            if constraint.crosses(edge):
                # a crossing at a shared endpoint is not a crossing in Shapely,
                # so anything returned here is a genuine violation
                crossing += 1
                break
    assert crossing == 0, f"{crossing} triangle edge(s) cross a breakline"


def test_breakline_changes_the_surface(existing_tin, survey_points):
    plain, _ = surf.build_tin(survey_points, boundary_mode="convex_hull")
    assert plain.constrained is False
    assert plain.breakline_edges == 0
    assert existing_tin.breakline_edges > 0


def test_conforming_delaunay_fallback(survey_points, breaklines, monkeypatch):
    monkeypatch.setattr(surf, "_triangle", None)
    mesh, issues = surf.build_tin(
        survey_points, breaklines=breaklines, boundary_mode="concave_hull", concave_ratio=0.2
    )
    assert mesh.engine == "conforming_delaunay"
    assert len(mesh.faces) > 100
    # the fallback must still honour every constraint as an edge
    edges = set()
    for a, b, c in mesh.faces:
        edges.update({(min(a, b), max(a, b)), (min(b, c), max(b, c)), (min(c, a), max(c, a))})
    for u, v in mesh.segments:
        key = (min(int(u), int(v)), max(int(u), int(v)))
        assert key in edges, "conforming Delaunay failed to realise a constraint"


def test_interpolation_is_exact_on_a_plane():
    points = [
        {"point_number": "1", "easting": 0.0, "northing": 0.0, "elevation": 10.0},
        {"point_number": "2", "easting": 10.0, "northing": 0.0, "elevation": 11.0},
        {"point_number": "3", "easting": 10.0, "northing": 10.0, "elevation": 13.0},
        {"point_number": "4", "easting": 0.0, "northing": 10.0, "elevation": 12.0},
        {"point_number": "5", "easting": 5.0, "northing": 5.0, "elevation": 11.5},
    ]
    mesh, _ = surf.build_tin(points, boundary_mode="convex_hull")
    # the five points define the plane z = 10 + 0.1 x + 0.2 y
    for x, y, z in [(1.0, 1.0, 10.3), (2.5, 7.5, 11.75), (9.0, 9.0, 12.7)]:
        sampled = surf.interpolate_mesh(mesh, x, y)
        assert sampled == pytest.approx(z, abs=1e-9)


def test_interpolation_outside_is_none(existing_tin):
    assert surf.interpolate_mesh(existing_tin, 0.0, 0.0) is None


def test_tin_requires_three_points():
    with pytest.raises(ValueError):
        surf.build_tin([{"easting": 0, "northing": 0, "elevation": 0}])


def test_user_boundary_clips_surface(survey_points):
    xs = [p["easting"] for p in survey_points]
    ys = [p["northing"] for p in survey_points]
    cx, cy = sum(xs) / len(xs), sum(ys) / len(ys)
    ring = [[cx - 8, cy - 8], [cx + 8, cy - 8], [cx + 8, cy + 8], [cx - 8, cy + 8]]
    mesh, _ = surf.build_tin(survey_points, boundary_mode="polygon", boundary=ring)
    assert mesh.boundary_source == "user_polygon"
    assert mesh.boundary.area <= mesh.boundary.envelope.area + 1e-6
    full, _ = surf.build_tin(survey_points, boundary_mode="convex_hull")
    assert mesh.areas().sum() < full.areas().sum()


def test_contours_are_generated_at_every_level(existing_tin):
    intervals = 0.1
    contours = surf.generate_contours(existing_tin, intervals, major_every=5, method="tin")
    assert len(contours) > 0
    levels = sorted({c["elevation"] for c in contours})
    zmin = float(existing_tin.z.min())
    zmax = float(existing_tin.z.max())
    for level in levels:
        assert zmin <= level <= zmax
        assert abs(level / intervals - round(level / intervals)) < 1e-6
    assert all(len(c["points"]) >= 2 for c in contours)
    assert any(c["is_major"] for c in contours)


def test_contour_methods_agree(existing_tin):
    tin = surf.generate_contours(existing_tin, 0.2, major_every=5, method="tin")
    grid = surf.generate_contours(existing_tin, 0.2, major_every=5, method="grid", resolution=0.4)
    tin_levels = {round(c["elevation"], 4) for c in tin}
    grid_levels = {round(c["elevation"], 4) for c in grid}
    assert tin_levels == grid_levels  # same discrete level set
    tin_length = sum(c["length"] for c in tin)
    grid_length = sum(c["length"] for c in grid)
    assert 0.6 < (grid_length / tin_length) < 1.6


def test_sample_grid_masks_outside(existing_tin):
    grid = surf.sample_grid(existing_tin, 1.0)
    assert grid["mask"].any()
    assert (~grid["mask"]).sum() > 100
    assert np.nanmax(grid["z"]) <= float(existing_tin.z.max()) + 1e-6
