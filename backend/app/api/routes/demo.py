"""Demo seeding endpoints (sample sidewalk survey + Leica GSI field book)."""

from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, HTTPException, status

from ...schemas import DemoSeedRequest
from ...services import demo
from ..deps import SessionDep

router = APIRouter(prefix="/demo", tags=["demo"])


@router.post("/seed", status_code=status.HTTP_201_CREATED)
async def seed(payload: DemoSeedRequest, session: SessionDep) -> Dict[str, Any]:
    try:
        result = await demo.seed_demo_project(session, payload.name)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await session.commit()
    return result


@router.post("/seed-gsi", status_code=status.HTTP_201_CREATED)
async def seed_gsi(session: SessionDep) -> Dict[str, Any]:
    try:
        result = await demo.seed_demo_project_gsf(session)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await session.commit()
    return result
