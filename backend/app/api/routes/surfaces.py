"""TIN surfaces, contours, volumes, profiles and cross sections."""

from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from ...models import DerivedOutput, OutputKind
from ...schemas import CrossSectionRequest, ProfileRequest, SurfaceBuildRequest, VolumeRequest
from ...services import computation as comp
from ..deps import ProjectDep, SessionDep

router = APIRouter(prefix="/projects/{project_id}", tags=["surfaces"])


@router.post("/surfaces", status_code=status.HTTP_201_CREATED)
async def build_surface(
    payload: SurfaceBuildRequest, project: ProjectDep, session: SessionDep
) -> Dict[str, Any]:
    """Build a constrained TIN + contours from the project's validated/approved points."""
    try:
        result = await comp.build_surface(
            session,
            project,
            name=payload.name,
            statuses=payload.statuses,
            file_id=payload.file_id,
            boundary_mode=payload.boundary_mode,
            boundary=payload.boundary,
            concave_ratio=payload.concave_ratio,
            breakline_codes=payload.breakline_codes,
            use_breaklines=payload.use_breaklines,
            contour_interval=payload.contour_interval,
            major_every=payload.major_every,
            contour_method=payload.contour_method,
            contour_resolution=payload.contour_resolution,
        )
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await session.commit()
    return result


@router.get("/surfaces")
async def list_surfaces(project: ProjectDep, session: SessionDep) -> Dict[str, Any]:
    rows = (
        await session.execute(
            select(DerivedOutput)
            .where(
                DerivedOutput.project_id == project.id,
                DerivedOutput.kind.in_(
                    [OutputKind.SURFACE.value, OutputKind.CONTOURS.value, OutputKind.VOLUME.value,
                     OutputKind.PROFILE.value, OutputKind.CROSS_SECTIONS.value, OutputKind.DXF.value]
                ),
            )
            .order_by(DerivedOutput.updated_at.desc())
        )
    ).scalars().all()
    return {"surfaces": [r.as_dict() for r in rows], "total": len(rows)}


@router.get("/surfaces/{surface_id}")
async def get_surface(surface_id: str, project: ProjectDep, session: SessionDep) -> Dict[str, Any]:
    row = await session.get(DerivedOutput, surface_id)
    if row is None or row.project_id != project.id:
        raise HTTPException(status_code=404, detail="Surface not found.")
    payload = comp.load_payload(row)
    payload["output"] = row.as_dict()
    return payload


@router.post("/volumes", status_code=status.HTTP_201_CREATED)
async def compute_volumes(
    payload: VolumeRequest, project: ProjectDep, session: SessionDep
) -> Dict[str, Any]:
    try:
        result = await comp.compute_volumes(
            session,
            project,
            existing_surface_id=payload.existing_surface_id,
            proposed_surface_id=payload.proposed_surface_id,
            proposed_file_id=payload.proposed_file_id,
            method=payload.method,
            cell_size=payload.cell_size,
        )
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await session.commit()
    return result


@router.post("/profiles", status_code=status.HTTP_201_CREATED)
async def compute_profile(
    payload: ProfileRequest, project: ProjectDep, session: SessionDep
) -> Dict[str, Any]:
    try:
        result = await comp.compute_profile(
            session,
            project,
            surface_id=payload.surface_id,
            design_surface_id=payload.design_surface_id,
            alignment=payload.alignment,
            feature_name=payload.feature_name,
            station_interval=payload.station_interval,
            offsets=payload.offsets,
        )
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await session.commit()
    return result


@router.post("/cross-sections")
async def compute_cross_sections(
    payload: CrossSectionRequest, project: ProjectDep, session: SessionDep
) -> Dict[str, Any]:
    try:
        result = await comp.compute_cross_sections(
            session,
            project,
            surface_id=payload.surface_id,
            design_surface_id=payload.design_surface_id,
            alignment=payload.alignment,
            feature_name=payload.feature_name,
            stations=payload.stations,
            station_interval=payload.station_interval,
            left=payload.left,
            right=payload.right,
            samples=payload.samples,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return result
