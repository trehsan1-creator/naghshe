"""Upload -> analyse -> map columns -> commit (the import wizard backend)."""

from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from sqlalchemy import select

from ...models import ProjectFile
from ...schemas import AnalyzeRequest, CommitRequest
from ...services import ingest
from ..deps import ProjectDep, SessionDep

router = APIRouter(prefix="/projects/{project_id}/files", tags=["import"])


@router.get("")
async def list_files(project: ProjectDep, session: SessionDep) -> Dict[str, Any]:
    rows = (
        await session.execute(
            select(ProjectFile)
            .where(ProjectFile.project_id == project.id)
            .order_by(ProjectFile.created_at.desc())
        )
    ).scalars().all()
    return {"files": [f.as_dict() for f in rows], "total": len(rows)}


@router.post("", status_code=status.HTTP_201_CREATED)
async def upload_file(
    project: ProjectDep, session: SessionDep, file: UploadFile = File(...)
) -> Dict[str, Any]:
    """Store the raw file immutably and return the analysis preview."""
    content = await file.read()
    try:
        result = await ingest.store_upload(session, project, file.filename or "upload.txt", content)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await session.commit()
    return {
        "file": result.file.as_dict(),
        "analysis": result.analysis,
    }


@router.post("/{file_id}/analyze")
async def analyse(
    file_id: str, payload: AnalyzeRequest, project: ProjectDep, session: SessionDep
) -> Dict[str, Any]:
    record = await _get_file(session, project.id, file_id)
    mapping = payload.mapping.model_dump() if payload.mapping else None
    try:
        return await ingest.analyse_stored_file(
            session,
            project,
            record,
            mapping=mapping,
            delimiter=payload.delimiter,
            has_header=payload.has_header,
            swap_xy=payload.swap_xy,
            preview_only=payload.preview_only,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{file_id}/commit", status_code=status.HTTP_201_CREATED)
async def commit(
    file_id: str, payload: CommitRequest, project: ProjectDep, session: SessionDep
) -> Dict[str, Any]:
    record = await _get_file(session, project.id, file_id)
    try:
        result = await ingest.commit_file(
            session,
            project,
            record,
            mapping=payload.mapping.model_dump() if payload.mapping else None,
            delimiter=payload.delimiter,
            has_header=payload.has_header,
            swap_xy=payload.swap_xy,
            status=payload.status,
            replace_existing=payload.replace_existing,
        )
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await session.commit()
    return result


@router.get("/{file_id}")
async def get_file(file_id: str, project: ProjectDep, session: SessionDep) -> Dict[str, Any]:
    record = await _get_file(session, project.id, file_id)
    return record.as_dict()


@router.get("/{file_id}/log")
async def file_log(file_id: str, project: ProjectDep, session: SessionDep) -> Dict[str, Any]:
    record = await _get_file(session, project.id, file_id)
    return {"file": record.as_dict(), "import_log": record.import_log or {}}


async def _get_file(session, project_id: str, file_id: str) -> ProjectFile:
    record = await session.get(ProjectFile, file_id)
    if record is None or record.project_id != project_id:
        raise HTTPException(status_code=404, detail=f"File '{file_id}' not found in this project.")
    return record
