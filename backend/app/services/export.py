"""Deliverable export: layered DXF (AutoCAD) and point CSV."""

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from ..engines import cad_surface_engine as surf
from ..models import DerivedOutput, OutputKind, OutputStatus, PointStatus, Project, SurveyPoint
from . import computation as comp
from .projects import mark_derived_outdated

__all__ = ["build_dxf", "points_csv", "save_deliverable"]


async def build_dxf(
    session: AsyncSession,
    project: Project,
    *,
    statuses: Optional[Sequence[str]] = None,
    surface_id: Optional[str] = None,
    include_points: bool = True,
    include_linework: bool = True,
    include_tin: bool = True,
    include_contours: bool = True,
    include_labels: bool = True,
    contour_interval: Optional[float] = None,
    major_every: int = 5,
    persist: bool = True,
) -> Dict[str, Any]:
    """Generate a complete multi-layer DXF and (optionally) store it as a deliverable."""
    statuses = list(statuses or (PointStatus.VALIDATED.value, PointStatus.APPROVED.value))
    rows = await comp.load_project_points(session, project.id, statuses)
    if not rows:
        raise ValueError("No points with the selected statuses; nothing to export.")

    points = [r.to_engine_dict() for r in rows]
    linework = comp.linework_for_points(project, points)
    breaklines = comp.breaklines_from_linework(project, linework)

    mesh = None
    contours: List[Dict[str, Any]] = []
    boundary = None
    payload: Dict[str, Any] = {}

    if surface_id:
        output = await session.get(DerivedOutput, surface_id)
        if output is None or output.project_id != project.id:
            raise ValueError("Surface not found in this project.")
        mesh, payload = await comp.load_surface_mesh(session, output)
        contours = payload.get("contours") or []
        boundary = payload.get("boundary")
    elif include_tin or include_contours:
        try:
            payload = await comp.build_surface(
                session,
                project,
                name="Surface for DXF export",
                statuses=statuses,
                contour_interval=contour_interval,
                major_every=major_every,
                persist=False,
            )
            mesh_payload = payload["mesh"]
            import numpy as np

            mesh = surf.TinMesh(
                vertices=np.array(mesh_payload["vertices"], dtype=float),
                faces=np.array(mesh_payload["faces"], dtype=np.int64),
                boundary=None,
                boundary_source=mesh_payload.get("boundary_source", "export"),
                constrained=bool(mesh_payload.get("constrained")),
                engine=mesh_payload.get("engine", "export"),
            )
            contours = payload.get("contours") or []
            boundary = payload.get("boundary")
        except ValueError:
            mesh = None  # not enough elevation data: export planimetry only

    alignment = None
    if linework.features:
        centre = next(
            (f for f in linework.features if f.base_code.upper() in ("CL", "CENTER", "AXIS")),
            None,
        )
        if centre is not None:
            alignment = [[v[0], v[1]] for v in centre.vertices]

    data = surf.export_dxf(
        points=points,
        features=linework.features if include_linework else [],
        mesh=mesh if include_tin else None,
        contours=contours if include_contours else [],
        breaklines=breaklines,
        boundary=boundary,
        alignment=alignment,
        title=f"{project.name} -- SurveyPro export",
        code_library=comp.code_library(project),
        include_points=include_points,
        include_tin=include_tin,
        include_contours=include_contours,
        label_points=include_labels,
    )

    filename = f"{_slug(project.name)}_surveypro.dxf"
    record = None
    if persist:
        record = await save_deliverable(
            session,
            project,
            data,
            filename=filename,
            kind=OutputKind.DXF.value,
            summary={
                "points": len(points) if include_points else 0,
                "features": len(linework.features),
                "triangles": 0 if mesh is None else int(len(mesh.faces)),
                "contours": len(contours),
                "bytes": len(data),
            },
            depends_on=[surface_id] if surface_id else [],
        )
    return {"content": data, "filename": filename, "output": record.as_dict() if record else None}


async def save_deliverable(
    session: AsyncSession,
    project: Project,
    data: bytes,
    *,
    filename: str,
    kind: str,
    summary: Dict[str, Any],
    depends_on: Optional[Sequence[str]] = None,
) -> DerivedOutput:
    export_dir = Path(comp.DERIVED_DIR) / "exports"
    export_dir.mkdir(parents=True, exist_ok=True)
    safe = "".join(ch for ch in filename if ch.isalnum() or ch in "._-") or "export.dxf"
    path = export_dir / f"{project.id}_{safe}"
    path.write_bytes(data)

    record = DerivedOutput(
        project_id=project.id,
        kind=kind,
        name=filename,
        status=OutputStatus.CURRENT.value,
        summary=summary,
        params={"filename": safe, "bytes": len(data)},
        payload_path=str(path),
        source_point_count=0,
        depends_on=list(depends_on or []),
    )
    session.add(record)
    await session.flush()
    return record


def points_csv(points: Sequence[SurveyPoint]) -> bytes:
    """CSV of points in the standard P,N,E,Z,Code,Layer,Status order."""
    buffer = io.StringIO()
    buffer.write("point_number,northing,easting,elevation,code,layer,status,description\n")
    for p in points:
        description = (p.description or "").replace('"', '""')
        elevation = "" if p.elevation is None else f"{p.elevation:.4f}"
        buffer.write(
            f'"{p.point_number}",{p.northing:.4f},{p.easting:.4f},{elevation},'
            f'"{(p.code or "").replace(chr(34), chr(34)*2)}",{p.layer},{p.status},"{description}"\n'
        )
    return buffer.getvalue().encode("utf-8")


def _slug(text: str) -> str:
    out = "".join(ch.lower() if ch.isalnum() else "-" for ch in (text or "project"))
    while "--" in out:
        out = out.replace("--", "-")
    return out.strip("-")[:60] or "project"
