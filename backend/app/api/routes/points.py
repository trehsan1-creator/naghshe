"""Point database, QA/QC and linework endpoints."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func, or_, select, update

from ...config import settings
from ...engines import coordinate_engine as coord
from ...models import PointStatus, SurveyPoint
from ...schemas import BulkStatusRequest, PointPatch, QaRequest
from ...services import computation as comp
from ...services.projects import mark_derived_outdated
from ..deps import ProjectDep, SessionDep

router = APIRouter(prefix="/projects/{project_id}", tags=["points"])


@router.get("/points")
async def list_points(
    project: ProjectDep,
    session: SessionDep,
    status_filter: Optional[List[str]] = Query(None, alias="status"),
    code: Optional[str] = None,
    search: Optional[str] = None,
    bbox: Optional[str] = Query(None, description="minx,miny,maxx,maxy"),
    limit: int = Query(2000, ge=1, le=200_000),
    offset: int = Query(0, ge=0),
    sort: str = Query("source_order", pattern="^(source_order|point_number|easting|northing|elevation|code|status)$"),
    order: str = Query("asc", pattern="^(asc|desc)$"),
) -> Dict[str, Any]:
    """Virtualised point database query (paged, filterable, bbox-aware)."""
    stmt = select(SurveyPoint).where(SurveyPoint.project_id == project.id)
    count_stmt = select(func.count(SurveyPoint.id)).where(SurveyPoint.project_id == project.id)

    if status_filter:
        stmt = stmt.where(SurveyPoint.status.in_(status_filter))
        count_stmt = count_stmt.where(SurveyPoint.status.in_(status_filter))
    if code:
        stmt = stmt.where(SurveyPoint.code.ilike(f"{code}%"))
        count_stmt = count_stmt.where(SurveyPoint.code.ilike(f"{code}%"))
    if search:
        pattern = f"%{search}%"
        condition = or_(
            SurveyPoint.point_number.ilike(pattern),
            SurveyPoint.code.ilike(pattern),
            SurveyPoint.description.ilike(pattern),
        )
        stmt = stmt.where(condition)
        count_stmt = count_stmt.where(condition)

    box = _parse_bbox(bbox)
    if box and settings.is_postgres:
        from geoalchemy2.functions import ST_MakeEnvelope, ST_Within

        envelope = ST_MakeEnvelope(box[0], box[1], box[2], box[3], 0)
        condition = ST_Within(SurveyPoint.geom, envelope)
        stmt = stmt.where(condition)
        count_stmt = count_stmt.where(condition)

    column = getattr(SurveyPoint, sort)
    stmt = stmt.order_by(column.desc() if order == "desc" else column.asc()).offset(offset).limit(limit)

    rows = list((await session.execute(stmt)).scalars().all())
    if box and not settings.is_postgres:
        rows = [
            r for r in rows
            if box[0] <= r.easting <= box[2] and box[1] <= r.northing <= box[3]
        ]
    total = int((await session.execute(count_stmt)).scalar_one())
    return {
        "points": [r.as_dict() for r in rows],
        "total": total,
        "returned": len(rows),
        "offset": offset,
        "limit": limit,
    }


@router.get("/points/{point_id}")
async def get_point(point_id: str, project: ProjectDep, session: SessionDep) -> Dict[str, Any]:
    row = await session.get(SurveyPoint, point_id)
    if row is None or row.project_id != project.id:
        raise HTTPException(status_code=404, detail="Point not found in this project.")
    data = row.as_dict(include_geometry=True)
    data["qa_flag_list"] = json.loads(row.qa_flags) if row.qa_flags else []
    return data


@router.patch("/points/{point_id}")
async def patch_point(
    point_id: str, payload: PointPatch, project: ProjectDep, session: SessionDep
) -> Dict[str, Any]:
    row = await session.get(SurveyPoint, point_id)
    if row is None or row.project_id != project.id:
        raise HTTPException(status_code=404, detail="Point not found in this project.")
    data = payload.model_dump(exclude_none=True)
    for key, value in data.items():
        setattr(row, key, value)
    if any(key in data for key in ("easting", "northing", "elevation")):
        row.version = (row.version or 1) + 1
        row.set_geometry()
    await mark_derived_outdated(session, project.id, "point edited")
    await session.commit()
    return row.as_dict()


@router.post("/points/bulk-status")
async def bulk_status(
    payload: BulkStatusRequest, project: ProjectDep, session: SessionDep
) -> Dict[str, Any]:
    """Approve / validate / reject points in bulk (drives the 3-tier workflow)."""
    stmt = update(SurveyPoint).where(SurveyPoint.project_id == project.id)
    if payload.ids:
        stmt = stmt.where(SurveyPoint.id.in_(payload.ids))
    if payload.point_numbers:
        stmt = stmt.where(SurveyPoint.point_number.in_(payload.point_numbers))
    if payload.from_status:
        stmt = stmt.where(SurveyPoint.status.in_(payload.from_status))
    if payload.code:
        stmt = stmt.where(SurveyPoint.code.ilike(f"{payload.code}%"))
    if not any((payload.ids, payload.point_numbers, payload.from_status, payload.code)):
        raise HTTPException(
            status_code=400,
            detail="Refusing a blanket update: specify ids, point_numbers, from_status or code.",
        )
    stmt = stmt.values(status=payload.status)
    result = await session.execute(stmt)
    await mark_derived_outdated(session, project.id, "point status changed")
    await session.commit()
    return {"updated": int(result.rowcount or 0), "status": payload.status}


@router.post("/qaqc")
async def run_qaqc(
    payload: QaRequest, project: ProjectDep, session: SessionDep
) -> Dict[str, Any]:
    """Run the full QA/QC battery and persist per-point severity flags."""
    rows = await comp.load_project_points(session, project.id, payload.statuses or None)
    if not rows:
        raise HTTPException(status_code=400, detail="No points to validate.")
    points = [r.to_engine_dict() for r in rows]
    tolerances = coord.QaTolerances(
        duplicate_xy_tolerance=project.duplicate_xy_tolerance,
        duplicate_z_tolerance=project.duplicate_z_tolerance,
        z_mad_threshold=project.z_mad_threshold,
        local_z_step_threshold=project.local_z_step_threshold,
        known_codes=[c.code for c in (project.code_mappings or []) if c.enabled],
    )
    report = coord.validate_points(points, tolerances, project_crs=project.crs_epsg)

    if payload.persist:
        by_number: Dict[str, List[str]] = {}
        severity: Dict[str, str] = {}
        for flag in report.flags:
            if flag.severity in ("warning", "error"):
                for pn in flag.point_numbers:
                    by_number.setdefault(pn, []).append(flag.code)
                    if flag.severity == "error":
                        severity[pn] = "error"
                    elif pn not in severity:
                        severity[pn] = "warning"
        for row in rows:
            flags = by_number.get(row.point_number)
            row.qa_flags = json.dumps(flags) if flags else None
            row.qa_severity = severity.get(row.point_number, "ok")
        await session.commit()

    payload_out = report.as_dict()
    payload_out["points_checked"] = len(points)
    payload_out["tolerances"] = tolerances.as_dict()
    return payload_out


@router.get("/qaqc")
async def latest_qaqc(project: ProjectDep, session: SessionDep) -> Dict[str, Any]:
    rows = await comp.load_project_points(session, project.id, None)
    flagged = [r.as_dict() for r in rows if r.qa_severity in ("warning", "error")]
    return {"flagged_points": flagged[:2000], "flagged_total": len(flagged)}


@router.get("/linework")
async def linework(project: ProjectDep, session: SessionDep) -> Dict[str, Any]:
    rows = await comp.load_project_points(
        session, project.id, [PointStatus.VALIDATED.value, PointStatus.APPROVED.value]
    )
    points = [r.to_engine_dict() for r in rows]
    result = comp.linework_for_points(project, points)
    return result.as_dict()


@router.get("/breaklines")
async def breaklines(project: ProjectDep, session: SessionDep) -> Dict[str, Any]:
    rows = await comp.load_project_points(
        session, project.id, [PointStatus.VALIDATED.value, PointStatus.APPROVED.value]
    )
    points = [r.to_engine_dict() for r in rows]
    result = comp.linework_for_points(project, points)
    return {"breaklines": comp.breaklines_from_linework(project, result)}


def _parse_bbox(value: Optional[str]):
    if not value:
        return None
    parts = [p for p in value.replace(" ", "").split(",") if p]
    if len(parts) != 4:
        raise HTTPException(status_code=400, detail="bbox must be 'minx,miny,maxx,maxy'.")
    try:
        return tuple(float(p) for p in parts)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="bbox values must be numeric.") from exc
