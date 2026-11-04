"""Project lifecycle: creation, layer/code seeding and dependency-state bookkeeping."""

from __future__ import annotations

from typing import Any, Optional, Sequence

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..engines.linework_engine import DEFAULT_CODE_LIBRARY, DEFAULT_LAYERS
from ..models import (
    CodeMapping,
    DerivedOutput,
    LayerStandard,
    OutputStatus,
    Project,
    ProjectStatus,
    SurveyPoint,
)

__all__ = [
    "create_project",
    "seed_layers_and_codes",
    "get_project",
    "mark_derived_outdated",
    "project_counters",
]


async def create_project(
    session: AsyncSession,
    *,
    name: str,
    crs_epsg: Optional[int] = None,
    code: Optional[str] = None,
    description: Optional[str] = None,
    client: Optional[str] = None,
    location: Optional[str] = None,
    surveyor: Optional[str] = None,
    vertical_datum: Optional[str] = None,
    angle_unit: Optional[str] = None,
    breakline_codes: Optional[Sequence[str]] = None,
    status: str = ProjectStatus.DRAFT.value,
) -> Project:
    project = Project(
        name=name,
        code=code,
        description=description,
        client=client,
        location=location,
        surveyor=surveyor,
        crs_epsg=int(crs_epsg or settings.default_crs_epsg),
        vertical_datum=vertical_datum or settings.default_vertical_datum,
        angle_unit=angle_unit or settings.default_angle_unit,
        duplicate_xy_tolerance=settings.default_duplicate_xy_tolerance,
        duplicate_z_tolerance=settings.default_duplicate_z_tolerance,
        z_mad_threshold=settings.default_z_mad_threshold,
        tin_boundary_mode=settings.default_tin_boundary_mode,
        contour_interval=settings.default_contour_interval,
        breakline_codes=list(breakline_codes or settings.default_breakline_codes),
        status=status,
        dependency_state="CURRENT",
    )
    session.add(project)
    await session.flush()
    await seed_layers_and_codes(session, project)
    # Collections are populated so the caller never triggers a lazy load outside the
    # async greenlet context (SQLAlchemy would raise MissingGreenlet).
    await session.refresh(project, attribute_names=["code_mappings", "layers", "files"])
    return project


async def seed_layers_and_codes(session: AsyncSession, project: Project) -> None:
    """Install the survey layer standard and the default code library on a project."""
    for layer in DEFAULT_LAYERS:
        session.add(
            LayerStandard(
                project_id=project.id,
                name=layer["name"],
                color=int(layer.get("color", 7)),
                linetype=layer.get("linetype", "CONTINUOUS"),
                description=layer.get("description", ""),
                visible=True,
            )
        )
    breakline_codes = {c.upper() for c in (project.breakline_codes or [])}
    for definition in DEFAULT_CODE_LIBRARY:
        session.add(
            CodeMapping(
                project_id=project.id,
                code=definition.code,
                kind=definition.kind,
                layer=definition.layer,
                block_name=definition.block_name,
                color=definition.color,
                description=definition.description,
                is_breakline=definition.code.upper() in breakline_codes,
                enabled=True,
            )
        )
    await session.flush()


async def get_project(session: AsyncSession, project_id: str) -> Optional[Project]:
    return await session.get(Project, project_id)


async def project_counters(session: AsyncSession, project_id: str) -> dict[str, Any]:
    """Count points per status plus the number of derived artefacts."""
    rows = await session.execute(
        select(SurveyPoint.status, func.count(SurveyPoint.id))
        .where(SurveyPoint.project_id == project_id)
        .group_by(SurveyPoint.status)
    )
    counts = {status: int(count) for status, count in rows.all()}
    derived = await session.execute(
        select(DerivedOutput.kind, func.count(DerivedOutput.id))
        .where(DerivedOutput.project_id == project_id)
        .group_by(DerivedOutput.kind)
    )
    return {
        "points": counts,
        "points_total": sum(counts.values()),
        "derived": {kind: int(count) for kind, count in derived.all()},
    }


async def mark_derived_outdated(
    session: AsyncSession, project_id: str, reason: str = "source data changed"
) -> int:
    """Flag every derived artefact of a project OUTDATED (dependency graph propagation)."""
    result = await session.execute(
        update(DerivedOutput)
        .where(DerivedOutput.project_id == project_id, DerivedOutput.status == OutputStatus.CURRENT.value)
        .values(status=OutputStatus.OUTDATED.value)
    )
    await session.execute(
        update(Project).where(Project.id == project_id).values(dependency_state="OUTDATED")
    )
    return int(result.rowcount or 0)
