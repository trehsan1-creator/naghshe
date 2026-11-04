"""SurveyPro backend -- FastAPI application factory."""

from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager
from typing import Any, Dict

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .api.router import api_router
from .config import settings
from .db.session import dispose_engine, init_db

logger = logging.getLogger("surveypro")
logging.basicConfig(
    level=logging.INFO if not settings.debug else logging.DEBUG,
    format="%(asctime)s %(levelname)-8s %(name)s :: %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    logger.info("SurveyPro API ready (database=%s)", settings.database_url.split("@")[-1])
    yield
    await dispose_engine()


def create_app() -> FastAPI:
    app = FastAPI(
        title="SurveyPro API",
        version="1.0.0",
        description=(
            "Industrial surveying, GIS, CAD and civil engineering platform.\n\n"
            "Deliverable 1: universal .txt/.csv/.gsi ingestion, surveying QA/QC, "
            "constrained TIN surfaces, contours, cut & fill volumes and DXF export."
        ),
        lifespan=lifespan,
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["Content-Disposition", "X-SurveyPro-Output-Id"],
    )

    @app.middleware("http")
    async def add_timing_header(request: Request, call_next):
        started = time.perf_counter()
        response = await call_next(request)
        response.headers["X-Process-Time"] = f"{(time.perf_counter() - started) * 1000:.1f}ms"
        return response

    @app.exception_handler(ValueError)
    async def value_error_handler(request: Request, exc: ValueError):
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    @app.get(f"{settings.api_prefix}/health", tags=["system"])
    async def health() -> Dict[str, Any]:
        return {
            "status": "ok",
            "app": settings.app_name,
            "version": "1.0.0",
            "database": "postgresql/postgis" if settings.is_postgres else "sqlite (dev fallback)",
            "engines": {
                "cdt": "triangle" if _has_triangle() else "conforming-delaunay fallback",
                "contours": "contourpy",
                "crs": "pyproj",
                "cad": "ezdxf",
            },
        }

    app.include_router(api_router, prefix=settings.api_prefix)
    return app


def _has_triangle() -> bool:
    try:
        import triangle  # noqa: F401

        return True
    except Exception:
        return False


app = create_app()
