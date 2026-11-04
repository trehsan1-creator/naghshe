"""Computation orchestration: linework, TIN surfaces, contours, volumes, profiles.

Every function here loads *real* point coordinates from the database, feeds the
deterministic engines and records a ``DerivedOutput`` with a source fingerprint so the
dependency graph can mark results OUTDATED when the input changes.
"""

from __future__ import annotations

import json
import math
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..engines import cad_surface_engine as surf
from ..engines import coordinate_engine as coord
from ..engines import linework_engine as lw
from ..engines.txt_gsi_parser import Issue
from ..models import (
    DerivedOutput,
    OutputKind,
    OutputStatus,
    PointStatus,
    Project,
    ProjectFile,
    SurveyPoint,
    fingerprint_points,
)
from .projects import mark_derived_outdated

__all__ = [
    "load_project_points",
    "code_library",
    "linework_for_points",
    "breaklines_from_linework",
    "build_surface",
    "load_surface_mesh",
    "compute_volumes",
    "compute_profile",
    "compute_cross_sections",
    "alignment_from_request",
    "save_payload",
    "load_payload",
    "DERIVED_DIR",
]

DERIVED_DIR = Path(settings.upload_dir).parent / "derived"
DEFAULT_STATUSES = (PointStatus.VALIDATED.value, PointStatus.APPROVED.value)


# --------------------------------------------------------------------------------------
# Loading
# --------------------------------------------------------------------------------------
async def load_project_points(
    session: AsyncSession,
    project_id: str,
    statuses: Optional[Sequence[str]] = None,
    *,
    file_id: Optional[str] = None,
) -> List[SurveyPoint]:
    stmt = select(SurveyPoint).where(SurveyPoint.project_id == project_id)
    if statuses:
        stmt = stmt.where(SurveyPoint.status.in_(list(statuses)))
    if file_id:
        stmt = stmt.where(SurveyPoint.file_id == file_id)
    stmt = stmt.order_by(SurveyPoint.source_order, SurveyPoint.point_number)
    return list((await session.execute(stmt)).scalars().all())


def code_library(project: Project) -> List[lw.CodeDefinition]:
    """The project's code library as engine definitions."""
    mappings = [m for m in (project.code_mappings or []) if m.enabled]
    if not mappings:
        return list(lw.DEFAULT_CODE_LIBRARY)
    return [
        lw.CodeDefinition(
            code=m.code.upper(),
            kind=m.kind,
            layer=m.layer,
            block_name=m.block_name,
            color=m.color or 7,
            description=m.description or "",
        )
        for m in mappings
    ]


def linework_for_points(project: Project, points: Sequence[Dict[str, Any]]) -> lw.LineworkResult:
    return lw.build_linework(points, code_library(project))


def breaklines_from_linework(
    project: Project,
    result: lw.LineworkResult,
    codes: Optional[Sequence[str]] = None,
) -> List[Dict[str, Any]]:
    """Select 3D breaklines from the linework (curb tops, ridge lines, ...)."""
    wanted = {c.upper() for c in (codes if codes is not None else (project.breakline_codes or []))}
    if not wanted:
        return []
    out: List[Dict[str, Any]] = []
    for feature in result.features:
        if feature.base_code.upper() in wanted or feature.name.upper() in wanted:
            out.append(
                {
                    "name": feature.name,
                    "layer": feature.layer,
                    "vertices": [list(v) for v in feature.vertices],
                }
            )
    return out


# --------------------------------------------------------------------------------------
# Payload persistence
# --------------------------------------------------------------------------------------
def save_payload(output: DerivedOutput, payload: Dict[str, Any]) -> None:
    """Write a large derived payload to disk (kept out of the database)."""
    DERIVED_DIR.mkdir(parents=True, exist_ok=True)
    path = DERIVED_DIR / f"{output.id}.json"
    path.write_text(json.dumps(payload, default=str), encoding="utf-8")
    output.payload_path = str(path)
    output.payload_inline = {
        "stats": payload.get("stats"),
        "summary": payload.get("summary"),
        "boundary": payload.get("boundary"),
        "center": payload.get("center"),
        "extent": payload.get("extent"),
    }


def load_payload(output: DerivedOutput) -> Dict[str, Any]:
    if output.payload_path and Path(output.payload_path).exists():
        return json.loads(Path(output.payload_path).read_text(encoding="utf-8"))
    return output.payload_inline or {}


# --------------------------------------------------------------------------------------
# Surface
# --------------------------------------------------------------------------------------
async def build_surface(
    session: AsyncSession,
    project: Project,
    *,
    name: Optional[str] = None,
    statuses: Optional[Sequence[str]] = None,
    file_id: Optional[str] = None,
    boundary_mode: Optional[str] = None,
    boundary: Optional[Sequence[Sequence[float]]] = None,
    concave_ratio: float = 0.15,
    breakline_codes: Optional[Sequence[str]] = None,
    use_breaklines: bool = True,
    contour_interval: Optional[float] = None,
    major_every: int = 5,
    contour_method: str = "grid",
    contour_resolution: Optional[float] = None,
    persist: bool = True,
) -> Dict[str, Any]:
    """Build a constrained TIN (+ contours) from the project's points."""
    rows = await load_project_points(session, project.id, statuses or DEFAULT_STATUSES, file_id=file_id)
    if len(rows) < 3:
        raise ValueError(
            f"Only {len(rows)} usable point(s) found. A surface needs at least 3 points with an "
            "elevation. Approve/validate more points or check the elevation column."
        )
    with_z = [r for r in rows if r.elevation is not None]
    if len(with_z) < 3:
        raise ValueError("Fewer than 3 points carry an elevation; a TIN cannot be built.")

    points = [r.to_engine_dict() for r in with_z]
    linework = linework_for_points(project, points)
    breaklines = (
        breaklines_from_linework(project, linework, breakline_codes) if use_breaklines else []
    )

    mesh, issues = surf.build_tin(
        points,
        breaklines=breaklines,
        boundary_mode=boundary_mode or project.tin_boundary_mode or "concave_hull",
        boundary=boundary,
        concave_ratio=concave_ratio,
    )

    interval = float(contour_interval or project.contour_interval or 0.1)
    contours: List[Dict[str, Any]] = []
    contour_issues: List[Issue] = []
    try:
        contours = surf.generate_contours(
            mesh,
            interval,
            major_every=major_every,
            method=contour_method,
            resolution=contour_resolution,
        )
    except Exception as exc:  # pragma: no cover - defensive
        contour_issues.append(Issue("warning", "contour_failed", f"Contour generation failed: {exc}"))

    stats = mesh.stats()
    stats["source"] = {
        "statuses": list(statuses or DEFAULT_STATUSES),
        "file_id": file_id,
        "points_used": len(points),
        "points_available": len(rows),
    }

    payload: Dict[str, Any] = {
        "kind": "surface",
        "stats": stats,
        "mesh": mesh.as_payload(),
        "contours": contours,
        "contour_interval": interval,
        "contour_method": contour_method,
        "breaklines": breaklines,
        "linework": linework.as_dict(),
        "issues": [i.as_dict() for i in issues + contour_issues],
        "center": [
            (stats["min_z"] + stats["max_z"]) / 2.0,
            None,
        ],
        "extent": _extent(points),
    }
    if mesh.boundary is not None:
        payload["boundary"] = [[float(x), float(y)] for x, y in mesh.boundary.exterior.coords]
    payload["center"] = _centre(points)

    source_hash = fingerprint_points(
        points,
        extra=json.dumps(
            {
                "boundary_mode": boundary_mode,
                "breaklines": [b["name"] for b in breaklines],
                "interval": interval,
            },
            sort_keys=True,
        ),
    )

    if not persist:
        return payload

    output = DerivedOutput(
        project_id=project.id,
        kind=OutputKind.SURFACE.value,
        name=name or f"TIN surface ({len(points)} pts)",
        status=OutputStatus.CURRENT.value,
        params={
            "boundary_mode": boundary_mode or project.tin_boundary_mode,
            "concave_ratio": concave_ratio,
            "breakline_codes": list(breakline_codes or project.breakline_codes or []),
            "contour_interval": interval,
            "major_every": major_every,
            "contour_method": contour_method,
            "statuses": list(statuses or DEFAULT_STATUSES),
            "file_id": file_id,
        },
        summary={
            "triangles": stats["triangles"],
            "vertices": stats["vertices"],
            "area_m2": stats["area_m2"],
            "min_z": stats["min_z"],
            "max_z": stats["max_z"],
            "constraints": stats["constraint_edges"],
            "contours": len(contours),
            "engine": stats["engine"],
        },
        source_hash=source_hash,
        source_point_count=len(points),
        depends_on=[file_id] if file_id else [],
    )
    session.add(output)
    await session.flush()
    save_payload(output, payload)
    await session.flush()

    payload["output"] = output.as_dict()
    return payload


def _extent(points: Sequence[Dict[str, Any]]) -> Dict[str, float]:
    xs = [p["easting"] for p in points]
    ys = [p["northing"] for p in points]
    zs = [p["elevation"] for p in points if p.get("elevation") is not None]
    return {
        "min_x": min(xs), "max_x": max(xs),
        "min_y": min(ys), "max_y": max(ys),
        "min_z": min(zs) if zs else 0.0, "max_z": max(zs) if zs else 0.0,
    }


def _centre(points: Sequence[Dict[str, Any]]) -> List[float]:
    xs = [p["easting"] for p in points]
    ys = [p["northing"] for p in points]
    zs = [p["elevation"] for p in points if p.get("elevation") is not None]
    return [sum(xs) / len(xs), sum(ys) / len(ys), (sum(zs) / len(zs)) if zs else 0.0]


async def load_surface_mesh(session: AsyncSession, output: DerivedOutput) -> Tuple[surf.TinMesh, Dict[str, Any]]:
    """Rehydrate a :class:`TinMesh` from a persisted surface payload."""
    import numpy as np

    payload = load_payload(output)
    mesh_payload = payload.get("mesh")
    if not mesh_payload:
        raise ValueError("Surface payload is missing its mesh; rebuild the surface.")
    vertices = np.array(mesh_payload["vertices"], dtype=float)
    faces = np.array(mesh_payload["faces"], dtype=np.int64)
    boundary = None
    if payload.get("boundary"):
        from shapely.geometry import Polygon

        ring = [(float(x), float(y)) for x, y in payload["boundary"]]
        if len(ring) >= 4:
            boundary = Polygon(ring)
            if not boundary.is_valid:
                boundary = boundary.buffer(0)
    mesh = surf.TinMesh(
        vertices=vertices,
        faces=faces,
        boundary=boundary,
        boundary_source=mesh_payload.get("boundary_source", "payload"),
        constrained=bool(mesh_payload.get("constrained")),
        engine=mesh_payload.get("engine", "payload"),
    )
    return mesh, payload


# --------------------------------------------------------------------------------------
# Volumes
# --------------------------------------------------------------------------------------
async def compute_volumes(
    session: AsyncSession,
    project: Project,
    *,
    existing_surface_id: str,
    proposed_surface_id: Optional[str] = None,
    proposed_file_id: Optional[str] = None,
    method: str = "grid",
    cell_size: float = 0.5,
    persist: bool = True,
) -> Dict[str, Any]:
    """Cut & fill between existing ground and proposed ground."""
    existing = await session.get(DerivedOutput, existing_surface_id)
    if existing is None or existing.project_id != project.id:
        raise ValueError("Existing surface not found in this project.")
    if existing.kind != OutputKind.SURFACE.value:
        raise ValueError("The existing-ground artefact is not a surface.")

    if proposed_surface_id:
        proposed_output = await session.get(DerivedOutput, proposed_surface_id)
        if proposed_output is None or proposed_output.project_id != project.id:
            raise ValueError("Proposed surface not found in this project.")
    elif proposed_file_id:
        built = await build_surface(
            session,
            project,
            name="Proposed ground",
            file_id=proposed_file_id,
            persist=True,
        )
        proposed_output = await session.get(DerivedOutput, built["output"]["id"])
    else:
        raise ValueError("Provide either proposed_surface_id or proposed_file_id.")

    existing_mesh, existing_payload = await load_surface_mesh(session, existing)
    proposed_mesh, proposed_payload = await load_surface_mesh(session, proposed_output)

    if method not in ("grid", "average_end_area"):
        raise ValueError(f"Unknown volume method '{method}'.")

    alignment = None
    if method == "average_end_area":
        alignment = _alignment_from_surface_payload(existing_payload)
        if alignment is None:
            raise ValueError(
                "Average End Area needs an alignment (a CL/centreline feature). Add linework with "
                "a CL code or use the grid method."
            )

    if method == "grid":
        result = surf.cut_fill_grid(existing_mesh, proposed_mesh, cell_size)
    else:
        from shapely.geometry import LineString

        line = LineString(alignment)
        stations = _stations(line.length, max(cell_size * 4, 1.0))
        eg_sections = [surf.cross_section(existing_mesh, line, s, left=40, right=40, samples=161) for s in stations]
        pg_sections = [surf.cross_section(proposed_mesh, line, s, left=40, right=40, samples=161) for s in stations]
        aea = surf.cut_fill_from_sections(stations, eg_sections, pg_sections)
        result = {
            "method": "average_end_area",
            "cut_m3": aea["cut_m3"],
            "fill_m3": aea["fill_m3"],
            "net_m3": aea["net_m3"],
            "length_m": aea["length_m"],
            "sections": aea["sections"],
            "sign_convention": "cut = EG above PG (material removed); fill = PG above EG",
        }

    result.update(
        {
            "existing_surface": existing.as_dict(),
            "proposed_surface": proposed_output.as_dict(),
            "existing_summary": existing_payload.get("stats"),
            "proposed_summary": proposed_payload.get("stats"),
        }
    )

    if persist:
        output = DerivedOutput(
            project_id=project.id,
            kind=OutputKind.VOLUME.value,
            name=f"Cut & fill: {existing.name} vs {proposed_output.name}",
            status=OutputStatus.CURRENT.value,
            params={"method": method, "cell_size": cell_size},
            summary={
                "cut_m3": result["cut_m3"],
                "fill_m3": result["fill_m3"],
                "net_m3": result["net_m3"],
                "method": result["method"],
            },
            source_hash=f"{existing.source_hash}:{proposed_output.source_hash}",
            source_point_count=(existing.source_point_count or 0) + (proposed_output.source_point_count or 0),
            depends_on=[existing.id, proposed_output.id],
        )
        session.add(output)
        await session.flush()
        save_payload(output, result)
        await session.flush()
        result["output"] = output.as_dict()
    return result


def _stations(length: float, interval: float) -> List[float]:
    stations = []
    s = 0.0
    while s < length:
        stations.append(round(s, 3))
        s += interval
    stations.append(round(length, 3))
    return stations


def _alignment_from_surface_payload(payload: Dict[str, Any]) -> Optional[List[List[float]]]:
    linework = payload.get("linework") or {}
    for feature in linework.get("features", []):
        base = str(feature.get("base_code", "")).upper()
        name = str(feature.get("name", "")).upper()
        if base in ("CL", "KBL", "KBR") or name.startswith("CL"):
            return [[float(v[0]), float(v[1])] for v in feature.get("vertices", [])]
    breaklines = payload.get("breaklines") or []
    if breaklines:
        return [[float(v[0]), float(v[1])] for v in breaklines[0]["vertices"]]
    return None


# --------------------------------------------------------------------------------------
# Profiles and cross sections
# --------------------------------------------------------------------------------------
def alignment_from_request(
    request_vertices: Optional[Sequence[Sequence[float]]],
    linework: Optional[lw.LineworkResult] = None,
    feature_name: Optional[str] = None,
) -> Any:
    from shapely.geometry import LineString

    if request_vertices:
        coords = [(float(v[0]), float(v[1])) for v in request_vertices]
        if len(coords) < 2:
            raise ValueError("An alignment needs at least 2 vertices.")
        return LineString(coords)
    if linework is not None:
        for feature in linework.features:
            if feature_name and feature.name.upper() != feature_name.upper():
                continue
            if len(feature.vertices) >= 2:
                return LineString([(v[0], v[1]) for v in feature.vertices])
    raise ValueError(
        "No alignment available: pass alignment vertices or import points coded CL (centreline)."
    )


async def _resolve_alignment(
    session: AsyncSession,
    project: Project,
    alignment: Optional[Sequence[Sequence[float]]],
    feature_name: Optional[str],
):
    """Use the supplied vertices, or fall back to the surveyed centreline linework."""
    if alignment:
        return alignment_from_request(alignment, None, feature_name)
    rows = await load_project_points(session, project.id, DEFAULT_STATUSES)
    linework = linework_for_points(project, [r.to_engine_dict() for r in rows])
    return alignment_from_request(None, linework, feature_name)


async def compute_profile(
    session: AsyncSession,
    project: Project,
    *,
    surface_id: str,
    design_surface_id: Optional[str] = None,
    alignment: Optional[Sequence[Sequence[float]]] = None,
    feature_name: Optional[str] = None,
    station_interval: float = 5.0,
    offsets: Sequence[float] = (0.0,),
    persist: bool = True,
) -> Dict[str, Any]:
    output = await session.get(DerivedOutput, surface_id)
    if output is None or output.project_id != project.id:
        raise ValueError("Surface not found in this project.")
    mesh, payload = await load_surface_mesh(session, output)

    design_mesh = None
    design_output = None
    if design_surface_id:
        design_output = await session.get(DerivedOutput, design_surface_id)
        if design_output is None or design_output.project_id != project.id:
            raise ValueError("Design surface not found in this project.")
        design_mesh, _ = await load_surface_mesh(session, design_output)

    line = await _resolve_alignment(session, project, alignment, feature_name)
    profile = surf.profile_along_alignment(
        mesh,
        line,
        station_interval=station_interval,
        design_mesh=design_mesh,
        offsets=offsets,
    )
    profile["surface"] = output.as_dict()
    if design_output is not None:
        profile["design_surface"] = design_output.as_dict()

    if persist:
        derived = DerivedOutput(
            project_id=project.id,
            kind=OutputKind.PROFILE.value,
            name=f"Profile along {feature_name or 'alignment'}",
            status=OutputStatus.CURRENT.value,
            params={"station_interval": station_interval, "offsets": list(offsets)},
            summary={
                "length_m": profile["length_m"],
                "min_elevation": profile["min_elevation"],
                "max_elevation": profile["max_elevation"],
                "samples": len(profile["samples"]),
            },
            source_hash=f"{output.source_hash}:profile",
            source_point_count=output.source_point_count,
            depends_on=[output.id] + ([design_output.id] if design_output else []),
        )
        session.add(derived)
        await session.flush()
        save_payload(derived, profile)
        await session.flush()
        profile["output"] = derived.as_dict()
    return profile


async def compute_cross_sections(
    session: AsyncSession,
    project: Project,
    *,
    surface_id: str,
    design_surface_id: Optional[str] = None,
    alignment: Optional[Sequence[Sequence[float]]] = None,
    feature_name: Optional[str] = None,
    stations: Optional[Sequence[float]] = None,
    station_interval: float = 10.0,
    left: float = 10.0,
    right: float = 10.0,
    samples: int = 61,
) -> Dict[str, Any]:
    output = await session.get(DerivedOutput, surface_id)
    if output is None or output.project_id != project.id:
        raise ValueError("Surface not found in this project.")
    mesh, _ = await load_surface_mesh(session, output)
    design_mesh = None
    if design_surface_id:
        design_output = await session.get(DerivedOutput, design_surface_id)
        if design_output is None or design_output.project_id != project.id:
            raise ValueError("Design surface not found in this project.")
        design_mesh, _ = await load_surface_mesh(session, design_output)

    line = await _resolve_alignment(session, project, alignment, feature_name)
    station_list = [float(s) for s in stations] if stations else _stations(line.length, station_interval)
    sections = []
    for station in station_list:
        eg = surf.cross_section(mesh, line, station, left=left, right=right, samples=samples)
        pg = (
            surf.cross_section(design_mesh, line, station, left=left, right=right, samples=samples)
            if design_mesh is not None
            else None
        )
        sections.append({"station": station, "existing": eg, "proposed": pg})

    result = {
        "surface": output.as_dict(),
        "alignment": [[float(x), float(y)] for x, y in line.coords],
        "left": left,
        "right": right,
        "sections": sections,
    }
    if design_mesh is not None:
        aea = surf.cut_fill_from_sections(
            station_list,
            [s["existing"] for s in sections],
            [s["proposed"] for s in sections],
        )
        result["average_end_area"] = aea
    return result


async def project_extent(session: AsyncSession, project_id: str) -> Dict[str, Any]:
    rows = await load_project_points(session, project_id, None)
    if not rows:
        return {"empty": True}
    return _extent([r.to_engine_dict() for r in rows])
