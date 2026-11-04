"""Deliverable endpoints: DXF for AutoCAD, CSV for spreadsheets."""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response

from ...models import PointStatus
from ...schemas import ExportRequest
from ...services import computation as comp
from ...services import export as export_service
from ..deps import ProjectDep, SessionDep

router = APIRouter(prefix="/projects/{project_id}/export", tags=["export"])


@router.post("/dxf")
async def export_dxf(
    payload: ExportRequest, project: ProjectDep, session: SessionDep
) -> Response:
    """One-click AutoCAD deliverable: layered, blocked, 3DFACE mesh, contours."""
    try:
        result = await export_service.build_dxf(
            session,
            project,
            statuses=payload.statuses,
            surface_id=payload.surface_id,
            include_points=payload.include_points,
            include_linework=payload.include_linework,
            include_tin=payload.include_tin,
            include_contours=payload.include_contours,
            include_labels=payload.include_labels,
            contour_interval=payload.contour_interval,
            major_every=payload.major_every,
        )
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await session.commit()
    return Response(
        content=result["content"],
        media_type="application/dxf",
        headers={
            "Content-Disposition": f'attachment; filename="{result["filename"]}"',
            "X-SurveyPro-Output-Id": (result["output"] or {}).get("id", ""),
        },
    )


@router.get("/dxf")
async def export_dxf_get(
    project: ProjectDep,
    session: SessionDep,
    surface_id: Optional[str] = None,
    include_tin: bool = Query(True),
    include_contours: bool = Query(True),
) -> Response:
    """GET variant so the browser can download with a plain link."""
    try:
        result = await export_service.build_dxf(
            session,
            project,
            surface_id=surface_id,
            include_tin=include_tin,
            include_contours=include_contours,
        )
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await session.commit()
    return Response(
        content=result["content"],
        media_type="application/dxf",
        headers={"Content-Disposition": f'attachment; filename="{result["filename"]}"'},
    )


@router.get("/points.csv")
async def export_points_csv(
    project: ProjectDep,
    session: SessionDep,
    statuses: Optional[str] = Query("VALIDATED,APPROVED"),
) -> Response:
    status_list = [s.strip().upper() for s in (statuses or "").split(",") if s.strip()]
    rows = await comp.load_project_points(session, project.id, status_list or None)
    if not rows:
        raise HTTPException(status_code=400, detail="No points match the requested statuses.")
    data = export_service.points_csv(rows)
    filename = f"surveypro_points_{project.id[:8]}.csv"
    return Response(
        content=data,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
