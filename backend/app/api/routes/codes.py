"""Code library, layer standard and derived-artefact (lineage) endpoints."""

from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from ...models import CodeMapping, DerivedOutput, LayerStandard
from ...schemas import CodeMappingIn, LayerIn
from ..deps import ProjectDep, SessionDep

router = APIRouter(prefix="/projects/{project_id}", tags=["codes"])


@router.get("/code-mappings")
async def list_code_mappings(project: ProjectDep) -> Dict[str, Any]:
    return {"code_mappings": [c.as_dict() for c in project.code_mappings]}


@router.put("/code-mappings")
async def upsert_code_mapping(
    payload: CodeMappingIn, project: ProjectDep, session: SessionDep
) -> Dict[str, Any]:
    existing = next(
        (c for c in project.code_mappings if c.code.upper() == payload.code.upper()), None
    )
    if existing is None:
        existing = CodeMapping(project_id=project.id, code=payload.code.upper())
        session.add(existing)
    for key, value in payload.model_dump().items():
        setattr(existing, key, value.upper() if key == "code" else value)
    await session.commit()
    return existing.as_dict()


@router.delete("/code-mappings/{mapping_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_code_mapping(mapping_id: str, project: ProjectDep, session: SessionDep) -> None:
    row = await session.get(CodeMapping, mapping_id)
    if row is None or row.project_id != project.id:
        raise HTTPException(status_code=404, detail="Code mapping not found.")
    await session.delete(row)
    await session.commit()


@router.get("/layers")
async def list_layers(project: ProjectDep) -> Dict[str, Any]:
    return {"layers": [layer.as_dict() for layer in project.layers]}


@router.put("/layers")
async def upsert_layer(payload: LayerIn, project: ProjectDep, session: SessionDep) -> Dict[str, Any]:
    existing = next((l for l in project.layers if l.name == payload.name), None)
    if existing is None:
        existing = LayerStandard(project_id=project.id, name=payload.name)
        session.add(existing)
    for key, value in payload.model_dump().items():
        setattr(existing, key, value)
    await session.commit()
    return existing.as_dict()


@router.patch("/layers/{layer_id}")
async def patch_layer(
    layer_id: str, payload: Dict[str, Any], project: ProjectDep, session: SessionDep
) -> Dict[str, Any]:
    row = await session.get(LayerStandard, layer_id)
    if row is None or row.project_id != project.id:
        raise HTTPException(status_code=404, detail="Layer not found.")
    for key in ("visible", "color", "linetype", "description"):
        if key in payload:
            setattr(row, key, payload[key])
    await session.commit()
    return row.as_dict()


@router.get("/derived")
async def list_derived(project: ProjectDep, session: SessionDep) -> Dict[str, Any]:
    rows = (
        await session.execute(
            select(DerivedOutput)
            .where(DerivedOutput.project_id == project.id)
            .order_by(DerivedOutput.updated_at.desc())
        )
    ).scalars().all()
    return {"derived": [r.as_dict() for r in rows], "total": len(rows)}


@router.get("/derived/{output_id}")
async def get_derived(output_id: str, project: ProjectDep, session: SessionDep) -> Dict[str, Any]:
    row = await session.get(DerivedOutput, output_id)
    if row is None or row.project_id != project.id:
        raise HTTPException(status_code=404, detail="Derived output not found.")
    from ...services.computation import load_payload

    return {**row.as_dict(include_payload=True), "payload": load_payload(row)}
