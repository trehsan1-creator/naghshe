"""End-to-end API tests: upload -> QA/QC -> TIN -> volumes -> DXF."""

from __future__ import annotations

import io
import json

import pytest


async def _upload(client, project_id, path, filename):
    content = path.read_bytes()
    response = await client.post(
        f"/api/v1/projects/{project_id}/files",
        files={"file": (filename, io.BytesIO(content), "text/plain")},
    )
    assert response.status_code == 201, response.text
    return response.json()


async def test_health(client):
    response = await client.get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["engines"]["cdt"] in ("triangle", "conforming-delaunay fallback")


async def test_crs_endpoint(client):
    response = await client.get("/api/v1/crs/28992")
    assert response.status_code == 200
    assert response.json()["epsg"] == 28992
    bad = await client.get("/api/v1/crs/999999")
    assert bad.status_code == 400


async def test_project_lifecycle(client):
    created = await client.post("/api/v1/projects", json={"name": "Lifecycle", "crs_epsg": 32631})
    assert created.status_code == 201
    project = created.json()
    assert project["crs_epsg"] == 32631
    assert len(project["crs"]["axis"]) >= 2

    listed = await client.get("/api/v1/projects")
    assert any(p["id"] == project["id"] for p in listed.json()["projects"])

    patched = await client.patch(
        f"/api/v1/projects/{project['id']}", json={"name": "Lifecycle 2", "contour_interval": 0.2}
    )
    assert patched.status_code == 200
    assert patched.json()["name"] == "Lifecycle 2"

    detail = await client.get(f"/api/v1/projects/{project['id']}")
    assert detail.status_code == 200
    assert len(detail.json()["code_mappings"]) > 10
    assert len(detail.json()["layers"]) > 10

    deleted = await client.delete(f"/api/v1/projects/{project['id']}")
    assert deleted.status_code == 204
    assert (await client.get(f"/api/v1/projects/{project['id']}")).status_code == 404


async def test_unknown_project_returns_404(client):
    assert (await client.get("/api/v1/projects/does-not-exist")).status_code == 404


async def test_full_import_and_surface_workflow(client, project, sample_dir):
    project_id = project["id"]
    upload = await _upload(client, project_id, sample_dir / "sidewalk_survey_rd.txt", "survey.txt")
    file_id = upload["file"]["id"]
    analysis = upload["analysis"]
    assert analysis["mapping"]["easting"] == 1
    assert analysis["mapping"]["northing"] == 2
    assert analysis["header_detected"] is True
    assert analysis["qa"]["summary"]["points"] > 200

    # explicit re-analysis with the wizard mapping
    reanalyzed = await client.post(
        f"/api/v1/projects/{project_id}/files/{file_id}/analyze",
        json={"mapping": {**analysis["mapping"], "easting": 1, "northing": 2}, "swap_xy": False},
    )
    assert reanalyzed.status_code == 200

    committed = await client.post(
        f"/api/v1/projects/{project_id}/files/{file_id}/commit",
        json={"mapping": analysis["mapping"], "status": "VALIDATED"},
    )
    assert committed.status_code == 201, committed.text
    body = committed.json()
    assert body["points_created"] == 229
    assert body["qa"]["summary"]["flag_counts"]["error"] == 0

    points = await client.get(f"/api/v1/projects/{project_id}/points?limit=50")
    assert points.status_code == 200
    assert points.json()["total"] == 229
    assert len(points.json()["points"]) == 50

    filtered = await client.get(f"/api/v1/projects/{project_id}/points?code=TR&limit=100")
    assert filtered.json()["total"] == 6

    qaqc = await client.post(f"/api/v1/projects/{project_id}/qaqc", json={"persist": True})
    assert qaqc.status_code == 200
    assert qaqc.json()["summary"]["points"] == 229

    approved = await client.post(
        f"/api/v1/projects/{project_id}/points/bulk-status",
        json={"from_status": ["VALIDATED"], "status": "APPROVED"},
    )
    assert approved.status_code == 200
    assert approved.json()["updated"] == 229

    linework = await client.get(f"/api/v1/projects/{project_id}/linework")
    assert linework.status_code == 200
    assert linework.json()["stats"]["features"] >= 5

    surface = await client.post(
        f"/api/v1/projects/{project_id}/surfaces",
        json={"contour_interval": 0.1, "boundary_mode": "concave_hull", "contour_method": "tin"},
    )
    assert surface.status_code == 201, surface.text
    payload = surface.json()
    assert payload["stats"]["triangles"] > 100
    assert payload["stats"]["constrained"] is True
    assert payload["mesh"]["vertices"]
    assert payload["contours"]
    surface_id = payload["output"]["id"]

    reloaded = await client.get(f"/api/v1/projects/{project_id}/surfaces/{surface_id}")
    assert reloaded.status_code == 200
    assert len(reloaded.json()["mesh"]["faces"]) == len(payload["mesh"]["faces"])

    # proposed ground -> cut & fill
    upload2 = await _upload(
        client, project_id, sample_dir / "proposed_design_rd.txt", "proposed.txt"
    )
    committed2 = await client.post(
        f"/api/v1/projects/{project_id}/files/{upload2['file']['id']}/commit",
        json={"mapping": upload2["analysis"]["mapping"], "status": "VALIDATED"},
    )
    assert committed2.json()["points_created"] == 229

    volume = await client.post(
        f"/api/v1/projects/{project_id}/volumes",
        json={
            "existing_surface_id": surface_id,
            "proposed_file_id": upload2["file"]["id"],
            "method": "grid",
            "cell_size": 0.5,
        },
    )
    assert volume.status_code == 201, volume.text
    volumes = volume.json()
    assert volumes["cut_m3"] > 0 and volumes["fill_m3"] > 0
    assert volumes["net_m3"] == pytest.approx(volumes["cut_m3"] - volumes["fill_m3"], abs=2e-3)

    profile = await client.post(
        f"/api/v1/projects/{project_id}/profiles",
        json={"surface_id": surface_id, "feature_name": "CL1", "station_interval": 5.0},
    )
    assert profile.status_code == 201, profile.text
    assert profile.json()["samples"]

    sections = await client.post(
        f"/api/v1/projects/{project_id}/cross-sections",
        json={
            "surface_id": surface_id,
            "feature_name": "CL1",
            "stations": [0, 20, 40],
            "left": 8,
            "right": 8,
            "samples": 33,
        },
    )
    assert sections.status_code == 200
    assert len(sections.json()["sections"]) == 3

    # Persian project names must not break the RFC 6266 attachment response header.
    renamed = await client.patch(
        f"/api/v1/projects/{project_id}", json={"name": "برداشت آزمایشی"}
    )
    assert renamed.status_code == 200

    dxf = await client.get(f"/api/v1/projects/{project_id}/export/dxf")
    assert dxf.status_code == 200
    assert dxf.headers["content-type"] == "application/dxf"
    assert "filename*=UTF-8''" in dxf.headers["content-disposition"]
    assert b"SECTION" in dxf.content[:200]
    assert b"3DFACE" in dxf.content

    csv = await client.get(f"/api/v1/projects/{project_id}/export/points.csv")
    assert csv.status_code == 200
    assert csv.content.decode().splitlines()[0].startswith("point_number,northing,easting")

    # lineage: re-importing marks earlier surfaces OUTDATED
    derived = await client.get(f"/api/v1/projects/{project_id}/derived")
    kinds = {d["kind"]: d for d in derived.json()["derived"]}
    assert "surface" in kinds and "volume" in kinds


async def test_outdated_propagation(client, project, sample_dir):
    project_id = project["id"]
    upload = await _upload(client, project_id, sample_dir / "sidewalk_survey_rd.txt", "s.txt")
    await client.post(
        f"/api/v1/projects/{project_id}/files/{upload['file']['id']}/commit",
        json={"mapping": upload["analysis"]["mapping"]},
    )
    surface = await client.post(
        f"/api/v1/projects/{project_id}/surfaces", json={"contour_method": "tin"}
    )
    surface_id = surface.json()["output"]["id"]
    first = await client.get(f"/api/v1/projects/{project_id}/derived/{surface_id}")
    assert first.json()["status"] == "CURRENT"

    points = (await client.get(f"/api/v1/projects/{project_id}/points?limit=1")).json()["points"]
    patched = await client.patch(
        f"/api/v1/projects/{project_id}/points/{points[0]['id']}",
        json={"elevation": 1.234},
    )
    assert patched.status_code == 200
    after = await client.get(f"/api/v1/projects/{project_id}/derived/{surface_id}")
    assert after.json()["status"] == "OUTDATED"


async def test_gsi_upload_and_reduction(client, project, sample_dir):
    project_id = project["id"]
    upload = await _upload(
        client, project_id, sample_dir / "leica_ts02_survey.gsi", "leica.gsi"
    )
    assert upload["file"]["file_format"] == "gsi"
    assert upload["analysis"]["stats"]["stations"] == 1
    committed = await client.post(
        f"/api/v1/projects/{project_id}/files/{upload['file']['id']}/commit", json={}
    )
    assert committed.status_code == 201, committed.text
    body = committed.json()
    assert body["observations_created"] > 200
    assert body["stations_created"] == 1
    points = (await client.get(f"/api/v1/projects/{project_id}/points?limit=5")).json()
    assert points["total"] > 200


async def test_rejects_unsupported_binary(client, project):
    response = await client.post(
        f"/api/v1/projects/{project['id']}/files",
        files={"file": ("scan.pdf", io.BytesIO(b"%PDF-1.4\x00\x01\x02"), "application/pdf")},
    )
    assert response.status_code in (201, 400)
    if response.status_code == 201:
        assert response.json()["file"]["file_format"] in ("txt", "csv")


async def test_demo_seed(client):
    response = await client.post("/api/v1/demo/seed", json={})
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["created"] in (True, False)
    if body["created"]:
        assert body["points_created"] == 229
        files = await client.get(f"/api/v1/projects/{body['project']['id']}/files")
        assert len(files.json()["files"]) == 2
