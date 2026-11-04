"""API router aggregation."""

from __future__ import annotations

from fastapi import APIRouter

from .routes import codes, demo, export, files, geojson, points, projects, surfaces

api_router = APIRouter()
api_router.include_router(projects.router)
api_router.include_router(files.router)
api_router.include_router(points.router)
api_router.include_router(codes.router)
api_router.include_router(surfaces.router)
api_router.include_router(export.router)
api_router.include_router(geojson.router)
api_router.include_router(demo.router)

__all__ = ["api_router"]
