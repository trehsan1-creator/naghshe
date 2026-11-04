"""Project CRUD, CRS metadata and workspace bootstrap."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import delete, select

from ...engines import coordinate_engine as coord
from ...models import DerivedOutput, Project, SurveyPoint
from ...schemas import ProjectCreate, ProjectUpdate
from ...services import projects as project_service
from ..deps import ProjectDep, SessionDep

router = APIRouter(tags=["projects"])


@router.get("/crs/{epsg}")
async def crs_metadata(epsg: int) -> Dict[str, Any]:
    """Describe an EPSG code (name, axes, units, area of use)."""
    try:
        return coord.describe_crs(epsg)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/crs")
async def crs_suggestions(
    eastings: List[float] = Query(default=[]),
    northings: List[float] = Query(default=[]),
) -> Dict[str, Any]:
    """Suggest CRSs from the numeric signature of a coordinate set."""
    return {"suggestions": coord.suggest_epsg(eastings, northings)}


@router.post("/projects", status_code=status.HTTP_201_CREATED)
async def create_project(payload: ProjectCreate, session: SessionDep) -> Dict[str, Any]:
    project = await project_service.create_project(
        session,
        name=payload.name,
        code=payload.code,
        description=payload.description,
        client=payload.client,
        location=payload.location,
        surveyor=payload.surveyor,
        crs_epsg=payload.crs_epsg,
        vertical_datum=payload.vertical_datum,
        angle_unit=payload.angle_unit,
        breakline_codes=payload.breakline_codes,
    )
    await session.commit()
    counters = await project_service.project_counters(session, project.id)
    return {**project.as_dict(), "counters": counters, "crs": _safe_crs(project.crs_epsg)}


@router.get("/projects")
async def list_projects(session: SessionDep) -> Dict[str, Any]:
    result = await session.execute(select(Project).order_by(Project.updated_at.desc()))
    projects = result.scalars().all()
    out = []
    for project in projects:
        counters = await project_service.project_counters(session, project.id)
        out.append({**project.as_dict(), "counters": counters})
    return {"projects": out, "total": len(out)}


@router.get("/projects/{project_id}")
async def get_project_detail(project: ProjectDep, session: SessionDep) -> Dict[str, Any]:
    counters = await project_service.project_counters(session, project.id)
    derived = (
        await session.execute(
            select(DerivedOutput)
            .where(DerivedOutput.project_id == project.id)
            .order_by(DerivedOutput.updated_at.desc())
        )
    ).scalars().all()
    return {
        **project.as_dict(),
        "counters": counters,
        "crs": _safe_crs(project.crs_epsg),
        "files": [f.as_dict() for f in project.files],
        "code_mappings": [c.as_dict() for c in project.code_mappings],
        "layers": [layer.as_dict() for layer in project.layers],
        "derived": [d.as_dict() for d in derived],
    }


@router.patch("/projects/{project_id}")
async def update_project(
    payload: ProjectUpdate, project: ProjectDep, session: SessionDep
) -> Dict[str, Any]:
    data = payload.model_dump(exclude_none=True)
    for key, value in data.items():
        setattr(project, key, value)
    if "crs_epsg" in data:
        try:
            coord.describe_crs(int(data["crs_epsg"]))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    await session.commit()
    return project.as_dict()


@router.delete("/projects/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(project: ProjectDep, session: SessionDep) -> None:
    await session.execute(delete(SurveyPoint).where(SurveyPoint.project_id == project.id))
    await session.execute(delete(DerivedOutput).where(DerivedOutput.project_id == project.id))
    await session.delete(project)
    await session.commit()


@router.get("/projects/{project_id}/overview")
async def project_overview(project: ProjectDep, session: SessionDep) -> Dict[str, Any]:
    """Everything the workspace needs on load: extent, code usage, derived state."""
    rows = (
        await session.execute(
            select(SurveyPoint).where(SurveyPoint.project_id == project.id)
            .order_by(SurveyPoint.source_order)
        )
    ).scalars().all()
    points = [p.to_engine_dict() for p in rows]
    extent = None
    codes: Dict[str, int] = {}
    if points:
        extent = {
            "min_x": min(p["easting"] for p in points),
            "max_x": max(p["easting"] for p in points),
            "min_y": min(p["northing"] for p in points),
            "max_y": max(p["northing"] for p in points),
            "min_z": min((p["elevation"] for p in points if p["elevation"] is not None), default=None),
            "max_z": max((p["elevation"] for p in points if p["elevation"] is not None), default=None),
        }
    for p in points:
        codes[p["code"] or "(none)"] = codes.get(p["code"] or "(none)", 0) + 1
    return {
        "project": project.as_dict(),
        "counters": await project_service.project_counters(session, project.id),
        "extent": extent,
        "code_usage": dict(sorted(codes.items(), key=lambda kv: kv[1], reverse=True)),
        "crs": _safe_crs(project.crs_epsg),
    }


def _safe_crs(epsg: int) -> Optional[Dict[str, Any]]:
    try:
        return coord.describe_crs(epsg)
    except Exception:
        return None
