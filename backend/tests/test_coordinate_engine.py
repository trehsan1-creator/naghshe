"""CRS handling, similarity transforms and the QA/QC battery."""

from __future__ import annotations

import math

import numpy as np
import pytest

from app.engines import coordinate_engine as coord


def test_describe_crs_rd():
    info = coord.describe_crs(28992)
    assert info["epsg"] == 28992
    assert info["is_projected"] is True
    assert "Amersfoort" in info["name"] or "RD" in info["name"]
    units = {axis["unit"] for axis in info["axis"]}
    assert any("metre" in unit for unit in units)


def test_describe_crs_rejects_unknown():
    with pytest.raises(ValueError):
        coord.describe_crs(999999)


def test_transform_rd_to_wgs84():
    points = [{"point_number": "1", "easting": 155_000.0, "northing": 463_000.0, "elevation": 0.0}]
    out, issues = coord.transform_points(points, 28992, 4326)
    lon, lat = out[0]["easting"], out[0]["northing"]
    # Amersfoort / central Netherlands
    assert 5.0 < lon < 6.0
    assert 51.9 < lat < 52.4
    assert points[0]["easting"] == 155_000.0  # input untouched


def test_transform_identity_returns_copy():
    points = [{"point_number": "1", "easting": 1.0, "northing": 2.0, "elevation": 3.0}]
    out, _ = coord.transform_points(points, 28992, 28992)
    assert out is not points and out == points


def test_similarity_transform_recovers_parameters():
    rng = np.random.default_rng(11)
    source = rng.uniform(0, 100, size=(12, 2))
    angle = math.radians(7.5)
    scale = 1.0003
    tx, ty = 250.0, -80.0
    c, s = math.cos(angle), math.sin(angle)
    target = np.array(
        [[tx + scale * (c * x - s * y), ty + scale * (s * x + c * y)] for x, y in source]
    )
    model = coord.fit_similarity([tuple(p) for p in source], [tuple(p) for p in target])
    assert model.tx == pytest.approx(tx, abs=1e-8)
    assert model.ty == pytest.approx(ty, abs=1e-8)
    assert model.rotation_rad == pytest.approx(angle, abs=1e-10)
    assert model.scale == pytest.approx(scale, abs=1e-10)
    assert model.rms == pytest.approx(0.0, abs=1e-8)
    assert model.rotation_gon == pytest.approx(math.degrees(angle) / 0.9, abs=1e-8)


def test_similarity_requires_two_points():
    with pytest.raises(ValueError):
        coord.fit_similarity([(0, 0)], [(1, 1)])


def test_qa_detects_duplicates_and_swap():
    points = [
        {"point_number": "1", "easting": 105420.0, "northing": 471880.0, "elevation": 0.85, "code": "CL1"},
        {"point_number": "2", "easting": 105420.0, "northing": 471880.0, "elevation": 0.85, "code": "CL1"},
        {"point_number": "3", "easting": 105421.0, "northing": 471881.0, "elevation": 0.86, "code": "CL1"},
        {"point_number": "3", "easting": 105422.0, "northing": 471882.0, "elevation": 0.87, "code": "CL1"},
    ]
    report = coord.validate_points(points, coord.QaTolerances())
    codes = {flag.code for flag in report.flags}
    assert "duplicate_coordinates" in codes
    assert "duplicate_point_number" in codes
    assert report.summary["points"] == 4


def test_qa_detects_elevation_spike(survey_points):
    points = [dict(p) for p in survey_points[:60]]
    points[10]["elevation"] = (points[10]["elevation"] or 0.0) + 4.0
    report = coord.validate_points(points, coord.QaTolerances())
    flags = {flag.code: flag for flag in report.flags}
    assert "elevation_anomaly" in flags
    assert "11" in flags["elevation_anomaly"].point_numbers or points[10]["point_number"] in flags[
        "elevation_anomaly"
    ].point_numbers


def test_qa_flags_missing_code_and_unknown_code():
    points = [
        {"point_number": str(i), "easting": 100 + i, "northing": 200 + i, "elevation": 1.0,
         "code": "" if i < 3 else "ZZZ"}
        for i in range(10)
    ]
    report = coord.validate_points(
        points, coord.QaTolerances(known_codes=["CL1", "MH"])
    )
    codes = {flag.code for flag in report.flags}
    assert "missing_code" in codes
    assert "unknown_code" in codes


def test_robust_z_is_median_based():
    values = np.array([1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 100.0])
    z = coord._robust_z(values)
    assert abs(z[-1]) > 3.5
    assert max(abs(z[:-1])) < 1e-9


def test_hull_area_square():
    area = coord.convex_hull_area([0, 10, 10, 0], [0, 0, 10, 10])
    assert area == pytest.approx(100.0)


def test_epsg_suggestion_for_rd():
    suggestions = coord.suggest_epsg([105420, 105460], [471880, 471920])
    assert suggestions[0]["epsg"] == 28992
    assert suggestions[0]["recommended"] is True
