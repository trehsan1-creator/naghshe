"""Pytest fixtures: isolated database, application client and sample data paths."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_DIR = BACKEND_DIR.parent
SAMPLE_DIR = REPO_DIR / "sample_data"

# The settings singleton is created at import time, so the environment must be ready
# before anything from `app` is imported.
_TMP = Path(tempfile.mkdtemp(prefix="surveypro-tests-"))
os.environ["SURVEYPRO_DATABASE_URL"] = f"sqlite+aiosqlite:///{_TMP / 'test.db'}"
os.environ["SURVEYPRO_UPLOAD_DIR"] = str(_TMP / "uploads")
os.environ["SURVEYPRO_ENVIRONMENT"] = "test"
os.environ["SURVEYPRO_DEBUG"] = "false"
os.environ["SURVEYPRO_SAMPLE_DATA_DIR"] = str(SAMPLE_DIR)

sys.path.insert(0, str(BACKEND_DIR))

import numpy as np  # noqa: E402
import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402

from app.engines import cad_surface_engine as surf  # noqa: E402
from app.engines import txt_gsi_parser as parser  # noqa: E402
from app.engines import linework_engine as linework  # noqa: E402
from app.main import app as fastapi_app  # noqa: E402


@pytest.fixture(scope="session")
def sample_dir() -> Path:
    return SAMPLE_DIR


def _load_points(filename: str) -> list[dict]:
    text = (SAMPLE_DIR / filename).read_text(encoding="utf-8")
    analysis = parser.analyze_text_file(text)
    parsed = parser.parse_text_points(
        text, analysis.mapping, analysis.delimiter, analysis.header_detected
    )
    return [p.as_dict() for p in parsed.points]


@pytest.fixture(scope="session")
def survey_points() -> list[dict]:
    return _load_points("sidewalk_survey_rd.txt")


@pytest.fixture(scope="session")
def proposed_points() -> list[dict]:
    return _load_points("proposed_design_rd.txt")


@pytest.fixture(scope="session")
def breaklines(survey_points) -> list[dict]:
    result = linework.build_linework(survey_points)
    return [
        {"name": f.name, "vertices": f.vertices}
        for f in result.features
        if f.base_code.upper() in {"KBL", "KBR", "KBBL", "KBBR", "SWL", "SWR"}
    ]


@pytest.fixture(scope="session")
def centreline(survey_points):
    """The surveyed road centreline (CL1 linework) as a Shapely LineString."""
    from shapely.geometry import LineString

    result = linework.build_linework(survey_points)
    feature = next(f for f in result.features if f.name.startswith("CL"))
    return LineString([(v[0], v[1]) for v in feature.vertices])


@pytest.fixture(scope="session")
def existing_tin(survey_points, breaklines):
    mesh, issues = surf.build_tin(
        survey_points, breaklines=breaklines, boundary_mode="concave_hull", concave_ratio=0.2
    )
    return mesh


@pytest.fixture(scope="session")
def proposed_tin(proposed_points, breaklines):
    mesh, _ = surf.build_tin(
        proposed_points, breaklines=breaklines, boundary_mode="concave_hull", concave_ratio=0.2
    )
    return mesh


@pytest_asyncio.fixture
async def client():
    from app.db.session import init_db

    await init_db()
    transport = ASGITransport(app=fastapi_app)
    async with AsyncClient(transport=transport, base_url="http://surveypro.test") as async_client:
        yield async_client


@pytest_asyncio.fixture
async def project(client):
    response = await client.post(
        "/api/v1/projects",
        json={"name": "Pytest project", "crs_epsg": 28992, "location": "Leimuiden"},
    )
    assert response.status_code == 201, response.text
    return response.json()
