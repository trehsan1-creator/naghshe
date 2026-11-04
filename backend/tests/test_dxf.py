"""DXF deliverable: layers, blocks, 3DFACE mesh and polylines."""

from __future__ import annotations

import io
from collections import Counter

import ezdxf
import pytest

from app.engines import cad_surface_engine as surf
from app.engines import linework_engine as linework


@pytest.fixture(scope="module")
def dxf_bytes(survey_points, existing_tin):
    result = linework.build_linework(survey_points)
    contours = surf.generate_contours(existing_tin, 0.1, major_every=5, method="grid", resolution=0.4)
    breaklines = [
        {"name": f.name, "vertices": f.vertices}
        for f in result.features
        if f.base_code in ("KBL", "KBR")
    ]
    return surf.export_dxf(
        points=survey_points,
        features=result.features,
        mesh=existing_tin,
        contours=contours,
        breaklines=breaklines,
        boundary=list(existing_tin.boundary.exterior.coords),
        title="SurveyPro pytest export",
    ), contours


def test_dxf_is_valid_r2013(dxf_bytes):
    data, _ = dxf_bytes
    assert data.startswith(b"  0") and b"SECTION" in data[:200]
    doc = ezdxf.read(io.StringIO(data.decode("utf-8")))
    assert doc.dxfversion == "AC1027"
    assert doc.header["$INSUNITS"] == 6


def test_dxf_layers_present(dxf_bytes):
    data, _ = dxf_bytes
    doc = ezdxf.read(io.StringIO(data.decode("utf-8")))
    for name in ("S-POINT", "S-ELEV", "S-PN", "S-CURB", "S-SIDEWALK", "S-TREE", "S-MANHOLE",
                 "S-CONTOUR-MAJOR", "S-CONTOUR-MINOR", "S-TIN", "S-BREAKLINE", "S-BOUNDARY"):
        assert name in doc.layers, f"missing layer {name}"


def test_dxf_blocks_defined(dxf_bytes):
    data, _ = dxf_bytes
    doc = ezdxf.read(io.StringIO(data.decode("utf-8")))
    for name in ("TR", "MH", "POLE", "LAMP", "BM"):
        assert name in doc.blocks
        block = doc.blocks.get(name)
        assert len(list(block)) > 0
        assert {"POINT", "ELEV", "CODE"} <= {attdef.dxf.tag for attdef in block.attdefs()}


def test_dxf_entities(dxf_bytes, existing_tin, survey_points):
    data, contours = dxf_bytes
    doc = ezdxf.read(io.StringIO(data.decode("utf-8")))
    msp = doc.modelspace()
    counts = Counter(entity.dxftype() for entity in msp)
    assert counts["POINT"] == len(survey_points)
    assert counts["3DFACE"] == len(existing_tin.faces)
    assert counts["INSERT"] >= 12          # trees, manholes, lamps
    assert counts["LWPOLYLINE"] >= len(contours)
    assert counts["POLYLINE"] >= 1         # 3D breaklines

    faces = msp.query("3DFACE")
    first = faces[0]
    assert len(first.dxf.vtx0) == 3        # true 3D vertices

    contours_entities = [e for e in msp.query("LWPOLYLINE") if e.dxf.layer.startswith("S-CONTOUR")]
    assert contours_entities
    for entity in contours_entities[:5]:
        assert entity.dxf.elevation != 0


def test_dxf_blocks_carry_attributes(dxf_bytes):
    data, _ = dxf_bytes
    doc = ezdxf.read(io.StringIO(data.decode("utf-8")))
    inserts = [e for e in doc.modelspace().query("INSERT") if e.dxf.name == "TR"]
    assert inserts
    tags = {attrib.dxf.tag for attrib in inserts[0].attribs}
    assert {"POINT", "ELEV", "CODE"} <= tags
    assert inserts[0].get_attrib_text("CODE").startswith("TR")


def test_dxf_without_surface():
    points = [
        {"point_number": "1", "easting": 0.0, "northing": 0.0, "elevation": 1.0, "code": "MH"},
        {"point_number": "2", "easting": 5.0, "northing": 0.0, "elevation": 1.1, "code": "MH"},
    ]
    data = surf.export_dxf(points=points, title="no surface")
    doc = ezdxf.read(io.StringIO(data.decode("utf-8")))
    assert len(doc.modelspace().query("POINT")) == 2
    assert len(doc.modelspace().query("3DFACE")) == 0
