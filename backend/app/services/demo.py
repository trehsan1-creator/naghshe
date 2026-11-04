"""Seed demo projects from the bundled sample data.

This exists so a reviewer can open the workspace and immediately work with a realistic
dataset instead of an empty screen.  It uses exactly the same import path as a user
upload -- no shortcuts, no fabricated numbers.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..models import PointStatus, Project, ProjectStatus
from . import ingest
from .projects import create_project

__all__ = ["sample_data_dir", "seed_demo_project", "seed_demo_project_gsf"]


def sample_data_dir() -> Path:
    candidates = [
        Path(settings.sample_data_dir),
        Path(__file__).resolve().parents[3] / "sample_data",
        Path(__file__).resolve().parents[2] / "sample_data",
        Path("/sample_data"),
    ]
    for candidate in candidates:
        if (candidate / "sidewalk_survey_rd.txt").exists():
            return candidate
    raise FileNotFoundError(
        "Sample data not found. Expected sample_data/sidewalk_survey_rd.txt next to the "
        "backend directory."
    )


async def seed_demo_project(
    session: AsyncSession, name: str = "Sidewalk reconstruction -- Leimuiden (demo)"
) -> Dict[str, Any]:
    directory = sample_data_dir()

    existing_project = (
        await session.execute(select(Project).where(Project.name == name))
    ).scalars().first()
    if existing_project is not None:
        return {"project": existing_project.as_dict(), "created": False, "files": []}

    project = await create_project(
        session,
        name=name,
        code="DEMO-001",
        description=(
            "60 m urban street reconstruction: existing ground survey plus the proposed "
            "design, coded for field-to-finish linework (KBL/KBR curbs, SWL/SWR sidewalk, "
            "TR trees, MH manholes, CL centreline)."
        ),
        client="Municipality of Kaag en Braassem",
        location="Leimuiden, NL",
        surveyor="SurveyPro demo dataset",
        status=ProjectStatus.QAQC.value,
    )
    await session.flush()

    existing_path = directory / "sidewalk_survey_rd.txt"
    upload = await ingest.store_upload(
        session, project, existing_path.name, existing_path.read_bytes()
    )
    committed = await ingest.commit_file(
        session,
        project,
        upload.file,
        status=PointStatus.VALIDATED.value,
    )

    files = [upload.file.as_dict()]
    result: Dict[str, Any] = {
        "project": project.as_dict(),
        "created": True,
        "files": files,
        "points_created": committed["points_created"],
        "qa": committed["qa"]["summary"],
    }

    proposed_path = directory / "proposed_design_rd.txt"
    if proposed_path.exists():
        upload2 = await ingest.store_upload(
            session, project, proposed_path.name, proposed_path.read_bytes()
        )
        committed2 = await ingest.commit_file(
            session,
            project,
            upload2.file,
            status=PointStatus.VALIDATED.value,
        )
        result["files"].append(upload2.file.as_dict())
        result["proposed_points_created"] = committed2["points_created"]
        result["proposed_file_id"] = upload2.file.id
    result["existing_file_id"] = upload.file.id
    result["project"] = project.as_dict()
    return result


async def seed_demo_project_gsf(
    session: AsyncSession, name: str = "Leica TS02plus field book (demo)"
) -> Dict[str, Any]:
    """Second demo project: raw GSI-8 observations reduced to coordinates."""
    directory = sample_data_dir()
    gsi_path = directory / "leica_ts02_survey.gsi"
    if not gsi_path.exists():
        return {"created": False, "detail": "GSI sample not present."}

    existing = (
        await session.execute(select(Project).where(Project.name == name))
    ).scalars().first()
    if existing is not None:
        return {"project": existing.as_dict(), "created": False, "files": []}

    project = await create_project(
        session,
        name=name,
        code="DEMO-002",
        description=(
            "Raw Leica GSI-8 field book on a local engineering grid: station setup, "
            "backsight and polar observations reduced to ENZ with instrument and "
            "reflector heights."
        ),
        location="Local site grid",
        surveyor="Leica TS02plus",
        status=ProjectStatus.PROCESSING.value,
    )
    await session.flush()
    upload = await ingest.store_upload(session, project, gsi_path.name, gsi_path.read_bytes())
    committed = await ingest.commit_file(
        session, project, upload.file, status=PointStatus.VALIDATED.value
    )
    return {
        "project": project.as_dict(),
        "created": True,
        "files": [upload.file.as_dict()],
        "points_created": committed["points_created"],
        "stations_created": committed["stations_created"],
        "observations_created": committed["observations_created"],
    }
