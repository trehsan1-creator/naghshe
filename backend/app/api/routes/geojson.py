"""GeoJSON delivery endpoint.

The web GIS view (MapLibre) needs EPSG:4326.  Rather than faking an approximate
client-side conversion, this endpoint reprojects the project geometry with pyproj
- the exact same transformation stack the coordinate engine uses.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pyproj import CRS, Transformer
from sqlalchemy import select

from ...models import DerivedOutput, OutputKind, PointStatus, SurveyPoint
from ...services import computation as comp
from ..deps import ProjectDep, SessionDep

router = APIRouter(prefix="/projects/{project_id}", tags=["geojson"])


def _transformer(source_epsg: int, target_epsg: int = 4326) -> Transformer:
    if int(source_epsg) == int(target_epsg):
        return Transformer.from_crs(4326, 4326, always_xy=True)
    try:
        return Transformer.from_crs(
            CRS.from_epsg(int(source_epsg)), CRS.from_epsg(int(target_epsg)), always_xy=True
        )
    except Exception as exc:  # pragma: no cover - defensive
        raise HTTPException(status_code=400, detail=f"Cannot transform from EPSG:{source_epsg}: {exc}") from exc


def _ring(transformer: Transformer, coords: List[List[float]]) -> List[List[float]]:
    out: List[List[float]] = []
    for vertex in coords:
        lon, lat = transformer.transform(float(vertex[0]), float(vertex[1]))
        z = vertex[2] if len(vertex) > 2 else None
        out.append([round(lon, 9), round(lat, 9)] if z is None else [round(lon, 9), round(lat, 9), round(float(z), 4)])
    return out


@router.get("/geojson")
async def geojson(
    project: ProjectDep,
    session: SessionDep,
    statuses: Optional[str] = Query(None, description="comma separated statuses"),
    surface_id: Optional[str] = None,
    include_surface: bool = True,
) -> Dict[str, Any]:
    """Points, linework, contours and TIN boundary reprojected to WGS84."""
    wanted = [s.strip().upper() for s in (statuses or "").split(",") if s.strip()]
    stmt = select(SurveyPoint).where(SurveyPoint.project_id == project.id)
    if wanted:
        stmt = stmt.where(SurveyPoint.status.in_(wanted))
    stmt = stmt.order_by(SurveyPoint.source_order)
    rows = list((await session.execute(stmt)).scalars().all())

    transformer = _transformer(project.crs_epsg)
    features: List[Dict[str, Any]] = []
    xs: List[float] = []
    ys: List[float] = []

    for row in rows:
        lon, lat = transformer.transform(float(row.easting), float(row.northing))
        xs.append(lon)
        ys.append(lat)
        features.append(
            {
                "type": "Feature",
                "id": row.id,
                "geometry": {"type": "Point", "coordinates": [lon, lat]},
                "properties": {
                    "kind": "point",
                    "point_number": row.point_number,
                    "code": row.code,
                    "description": row.description,
                    "layer": row.layer,
                    "status": row.status,
                    "elevation": row.elevation,
                    "qa_severity": row.qa_severity,
                    "easting": row.easting,
                    "northing": row.northing,
                },
            }
        )

    # Field-to-finish linework from the validated/approved subset.
    validated = [
        r for r in rows if r.status in (PointStatus.VALIDATED.value, PointStatus.APPROVED.value)
    ]
    linework = comp.linework_for_points(project, [r.to_engine_dict() for r in validated])
    for feature in linework.features:
        coords = _ring(transformer, [list(v) for v in feature.vertices])
        if len(coords) < 2:
            continue
        geometry = (
            {"type": "Polygon", "coordinates": [coords]}
            if feature.kind == "polygon" and feature.closed
            else {"type": "LineString", "coordinates": coords}
        )
        features.append(
            {
                "type": "Feature",
                "geometry": geometry,
                "properties": {
                    "kind": "linework",
                    "name": feature.name,
                    "code": feature.base_code,
                    "layer": feature.layer,
                    "length": feature.length,
                    "area": feature.area,
                    "closed": feature.closed,
                },
            }
        )

    surface_feature = None
    if include_surface:
        if surface_id:
            surface_feature = await session.get(DerivedOutput, surface_id)
            if surface_feature is not None and surface_feature.project_id != project.id:
                surface_feature = None
        else:
            surface_feature = (
                await session.execute(
                    select(DerivedOutput)
                    .where(
                        DerivedOutput.project_id == project.id,
                        DerivedOutput.kind == OutputKind.SURFACE.value,
                    )
                    .order_by(DerivedOutput.updated_at.desc())
                    .limit(1)
                )
            ).scalars().first()

        if surface_feature is not None:
            payload = comp.load_payload(surface_feature)
            for contour in payload.get("contours", []):
                coords = _ring(transformer, [list(p) for p in contour["points"]])
                if len(coords) < 2:
                    continue
                features.append(
                    {
                        "type": "Feature",
                        "geometry": {"type": "LineString", "coordinates": coords},
                        "properties": {
                            "kind": "contour",
                            "elevation": contour["elevation"],
                            "is_major": contour["is_major"],
                            "layer": contour["layer"],
                        },
                    }
                )
            boundary = payload.get("boundary") or payload.get("mesh", {}).get("boundary")
            if boundary and len(boundary) >= 3:
                ring = _ring(transformer, [list(p) for p in boundary])
                ring.append(ring[0])
                features.append(
                    {
                        "type": "Feature",
                        "geometry": {"type": "Polygon", "coordinates": [ring]},
                        "properties": {"kind": "boundary", "layer": "S-BOUNDARY"},
                    }
                )

    bbox = [min(xs), min(ys), max(xs), max(ys)] if xs else None
    return {
        "type": "FeatureCollection",
        "crs": {"type": "name", "properties": {"name": f"urn:ogc:def:crs:OGC:1.3:CRS84"}},
        "source_crs": {"epsg": project.crs_epsg},
        "bbox": bbox,
        "features": features,
    }
