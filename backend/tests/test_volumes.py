"""Cut & fill volumes, profiles and cross sections."""

from __future__ import annotations

import math

import pytest
from shapely.geometry import LineString

from app.engines import cad_surface_engine as surf


def _ramp(slope: float, z0: float = 0.0, size: float = 20.0, step: float = 2.0):
    points = []
    n = 0
    x = 0.0
    while x <= size + 1e-9:
        y = 0.0
        while y <= size + 1e-9:
            n += 1
            points.append(
                {"point_number": str(n), "easting": x, "northing": y,
                 "elevation": z0 + slope * x}
            )
            y += step
        x += step
    return points


def test_prism_to_datum_is_exact():
    """A plane (slope 0.05) above datum 0 over 20x20 m: V = 400 * 0.5 = 200 m3."""
    mesh, _ = surf.build_tin(_ramp(0.05), boundary_mode="convex_hull")
    result = surf.prism_volume_to_datum(mesh, 0.0)
    assert result["cut_m3"] == pytest.approx(200.0, rel=1e-3)
    assert result["fill_m3"] == pytest.approx(0.0, abs=1e-6)
    assert result["area_m2"] == pytest.approx(400.0, rel=1e-6)


def test_prism_to_datum_split_cut_fill():
    mesh, _ = surf.build_tin(_ramp(0.05), boundary_mode="convex_hull")
    # datum through the middle of the ramp (max z = 1.0)
    result = surf.prism_volume_to_datum(mesh, 0.5)
    assert result["cut_m3"] == pytest.approx(50.0, rel=2e-2)
    assert result["fill_m3"] == pytest.approx(50.0, rel=2e-2)
    assert result["net_m3"] == pytest.approx(result["cut_m3"] - result["fill_m3"], abs=1e-6)


def test_cut_fill_grid_against_analytic_flat_plate():
    """EG flat at 1.00, PG flat at 0.90 over 20x20 m -> 40 m3 of cut, no fill."""
    existing, _ = surf.build_tin(_ramp(0.0, z0=1.0), boundary_mode="convex_hull")
    proposed, _ = surf.build_tin(_ramp(0.0, z0=0.90), boundary_mode="convex_hull")
    result = surf.cut_fill_grid(existing, proposed, cell_size=0.25)
    assert result["cut_m3"] == pytest.approx(40.0, rel=1e-3)
    assert result["fill_m3"] == pytest.approx(0.0, abs=1e-6)
    assert result["max_cut_depth"] == pytest.approx(0.10, abs=1e-6)


def test_cut_fill_grid_mixed():
    # EG: 1.00 + 0.02x ; PG: 0.95 + 0.04x -> they cross at x = 2.5 m
    existing, _ = surf.build_tin(_ramp(0.02, z0=1.0), boundary_mode="convex_hull")
    proposed, _ = surf.build_tin(_ramp(0.04, z0=0.95), boundary_mode="convex_hull")
    result = surf.cut_fill_grid(existing, proposed, cell_size=0.25)
    assert result["cut_m3"] > 0 and result["fill_m3"] > 0
    assert result["net_m3"] == pytest.approx(result["cut_m3"] - result["fill_m3"], abs=1e-6)
    assert result["cut_area_m2"] + result["fill_area_m2"] > 0


def test_cut_fill_converges_with_cell_size(existing_tin, proposed_tin):
    coarse = surf.cut_fill_grid(existing_tin, proposed_tin, 0.5)
    fine = surf.cut_fill_grid(existing_tin, proposed_tin, 0.25)
    assert fine["cut_m3"] == pytest.approx(coarse["cut_m3"], rel=0.12)
    assert fine["fill_m3"] == pytest.approx(coarse["fill_m3"], rel=0.12)


def test_design_volumes_match_the_model(existing_tin, proposed_tin):
    """Roadway lowered 5 cm (384 m2), sidewalk/curb raised 15 cm (336 m2), 60 m long."""
    result = surf.cut_fill_grid(existing_tin, proposed_tin, 0.25)
    assert result["cut_m3"] == pytest.approx(19.2, rel=0.10)
    assert result["fill_m3"] == pytest.approx(57.9, rel=0.15)
    assert result["net_m3"] < 0  # more fill than cut -> material must be imported


def test_average_end_area_matches_grid(existing_tin, proposed_tin, centreline):
    alignment = centreline
    stations = [0, 10, 20, 30, 40, 50, 59.9]
    eg_sections = [surf.cross_section(existing_tin, alignment, s, left=7, right=7, samples=81) for s in stations]
    pg_sections = [surf.cross_section(proposed_tin, alignment, s, left=7, right=7, samples=81) for s in stations]
    aea = surf.cut_fill_from_sections(stations, eg_sections, pg_sections)
    grid = surf.cut_fill_grid(existing_tin, proposed_tin, 0.25)
    assert aea["cut_m3"] == pytest.approx(grid["cut_m3"], rel=0.35)
    assert aea["fill_m3"] == pytest.approx(grid["fill_m3"], rel=0.50)
    assert aea["net_m3"] == pytest.approx(aea["cut_m3"] - aea["fill_m3"], abs=1e-6)


def test_average_end_area_formula():
    # areas 2,4,6 m2 at stations 0,10,20 -> 0.5*(2+4)*10 + 0.5*(4+6)*10 = 80
    result = surf.average_end_area([0, 10, 20], [2, 4, 6])
    assert result["volume_m3"] == pytest.approx(80.0)
    assert result["length_m"] == pytest.approx(20.0)


def test_profile_along_alignment(existing_tin, centreline):
    alignment = centreline
    profile = surf.profile_along_alignment(existing_tin, alignment, station_interval=5.0)
    assert len(profile["samples"]) == math.ceil(profile["length_m"] / 5.0) + 1
    assert profile["samples"][0]["station"] == 0.0
    assert profile["samples"][-1]["station"] == pytest.approx(profile["length_m"], abs=1e-6)
    elevations = [s["offsets"]["0"]["elevation"] for s in profile["samples"]]
    assert all(e is not None for e in elevations)
    assert profile["min_elevation"] <= profile["max_elevation"]


def test_cross_section_geometry(existing_tin, centreline):
    section = surf.cross_section(existing_tin, centreline, 20.0, left=6, right=6, samples=13)
    assert section["offsets"][0] == pytest.approx(-6.0)
    assert section["offsets"][-1] == pytest.approx(6.0)
    valid = [z for z in section["elevations"] if z is not None]
    assert len(valid) > 5
    # 1.5 % cross fall: the crown (offset 0) is higher than the gutters (offset +-3 m)
    assert section["offsets"][6] == pytest.approx(0.0)
    centre = section["elevations"][6]
    left_gutter = section["elevations"][3]    # offset -3.0
    right_gutter = section["elevations"][9]   # offset +3.0
    assert centre > left_gutter
    assert centre > right_gutter
    assert centre - left_gutter == pytest.approx(0.045, abs=0.02)
