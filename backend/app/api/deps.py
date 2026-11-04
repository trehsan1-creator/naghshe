"""Shared FastAPI dependencies."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, Path, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.session import get_session
from ..models import Project

SessionDep = Annotated[AsyncSession, Depends(get_session)]


async def get_project(
    project_id: Annotated[str, Path(description="Project UUID")],
    session: SessionDep,
) -> Project:
    project = await session.get(Project, project_id)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Project '{project_id}' not found."
        )
    return project


ProjectDep = Annotated[Project, Depends(get_project)]
