"""Universal text importer: encoding, delimiter, column inference and parsing."""

from __future__ import annotations

import pytest

from app.engines import coordinate_engine as coord
from app.engines import txt_gsi_parser as parser


def test_sniff_text_encodings():
    text = "Puntnummer,X,Y,Z,Code\n1,105420.000,471880.000,0.851,CL1\n"
    for encoding in ("utf-8", "utf-16", "cp1252"):
        decoded, detected, notes = parser.decode_bytes(text.encode(encoding))
        assert "Puntnummer" in decoded or "Puntnummer" in decoded.rstrip("\x00")
        assert detected in ("utf-8", "utf-16-le", "utf-16-be", "utf-16", "cp1252")
    assert decoded.startswith("Puntnummer")


def test_decode_arabic_cp1256():
    text = "رقم النقطة,الشرق,الشمال,الارتفاع\n1,105420.1,471880.2,0.85\n"
    decoded, encoding, _ = parser.decode_bytes(text.encode("cp1256"))
    assert "النقطة" in decoded
    assert encoding in ("cp1256", "utf-8")


def test_delimiter_detection_prefers_actual_separator():
    comma = "1,105420.000,471880.000,0.851,CL1\n2,105421.000,471882.000,0.831,CL1\n"
    semicolon = comma.replace(",", ";")
    tabs = "1\t105420.000\t471880.000\t0.851\tCL1\n2\t105421.000\t471882.000\t0.831\tCL1\n"
    assert parser.detect_delimiter(comma.splitlines())[0] == ","
    assert parser.detect_delimiter(semicolon.splitlines())[0] == ";"
    assert parser.detect_delimiter(tabs.splitlines())[0] == "\t"


def test_messy_whitespace_file_is_parsed(sample_dir):
    text = (sample_dir / "sidewalk_survey_messy.txt").read_text(encoding="utf-8")
    analysis = parser.analyze_text_file(text)
    assert analysis.delimiter == "ws"
    assert analysis.mapping.point_number == 0
    assert analysis.mapping.northing == 1     # P,N,E order in the export
    assert analysis.mapping.easting == 2
    assert analysis.mapping.elevation == 3
    parsed = parser.parse_text_points(
        text, analysis.mapping, analysis.delimiter, analysis.header_detected
    )
    assert parsed.stats["parsed"] == 229
    assert parsed.stats["skipped"] == 0
    assert 105_000 < parsed.points[0].easting < 106_000
    assert 471_000 < parsed.points[0].northing < 473_000


def test_dutch_header_mapping(sample_dir):
    text = (sample_dir / "sidewalk_survey_rd.txt").read_text(encoding="utf-8")
    analysis = parser.analyze_text_file(text)
    assert analysis.header_detected
    assert analysis.mapping.easting == 1
    assert analysis.mapping.northing == 2
    assert analysis.mapping.elevation == 3
    assert analysis.mapping.code == 4
    assert analysis.mapping.description == 5
    assert analysis.confidence["easting"] > 0.9


@pytest.mark.parametrize(
    "header,expected_easting",
    [
        ("P,N,E,Z,Code", 2),          # PNEZD (classic)
        ("Pt,Easting,Northing,Elevation,Desc", 1),
        ("id;x;y;hoogte;code", 1),    # Dutch semicolon + 'hoogte'
        ("Point,X,Y,H,Code", 1),
    ],
)
def test_header_variants(header, expected_easting):
    delimiter = ";" if ";" in header else ","
    columns = header.split(delimiter)
    rows = [header]
    for i in range(1, 6):
        values = []
        for name in columns:
            key = name.strip().lower()
            if key in ("p", "pt", "id", "point"):
                values.append(str(i))
            elif key in ("x", "easting", "e", "east"):
                values.append(f"{105420 + i * 2:.3f}")
            elif key in ("y", "northing", "n", "north"):
                values.append(f"{471880 + i * 2:.3f}")
            elif key in ("z", "h", "elevation", "hoogte", "elev"):
                values.append(f"{0.85 + i * 0.01:.3f}")
            else:
                values.append("CL1" if key == "code" else "centreline")
        rows.append(delimiter.join(values))
    text = "\n".join(rows) + "\n"
    analysis = parser.analyze_text_file(text)
    assert analysis.mapping.easting == expected_easting
    parsed = parser.parse_text_points(
        text, analysis.mapping, analysis.delimiter, analysis.header_detected
    )
    assert parsed.stats["parsed"] == 5
    assert parsed.points[0].easting > 100_000


def test_decimal_comma_and_thousands_separator():
    text = "1;105.420,500;471.880,250;0,851;CL1\n2;105.421,000;471.882,000;0,831;CL1\n3;105.422,000;471.884,000;0,811;CL1\n"
    analysis = parser.analyze_text_file(text)
    parsed = parser.parse_text_points(
        text, analysis.mapping, analysis.delimiter, analysis.header_detected
    )
    assert parsed.stats["parsed"] == 3
    assert parsed.points[0].easting == pytest.approx(105420.5)
    assert parsed.points[0].northing == pytest.approx(471880.25)
    assert parsed.points[0].elevation == pytest.approx(0.851)


def test_ragged_rows_report_but_continue():
    text = "1,105420.0,471880.0,0.85,CL1\n2,105421.0,471882.0\n3,105422.0,471884.0,0.81,CL1\n"
    parsed = parser.parse_text_points(text)
    assert parsed.stats["parsed"] == 3
    # elevation column missing on row 2 -> None, but the point is still imported
    assert parsed.points[1].elevation is None


def test_duplicate_point_numbers_reported():
    text = "1,105420.0,471880.0,0.85\n1,105421.0,471882.0,0.83\n2,105422.0,471884.0,0.81\n"
    parsed = parser.parse_text_points(text)
    codes = [issue.code for issue in parsed.issues]
    assert "duplicate_point_number" in codes
    assert parsed.stats["duplicate_point_numbers"] == 1


def test_xy_swap_detection_utm():
    eastings = [500_000 + i for i in range(10)]
    northings = [5_700_000 + i for i in range(10)]
    assert coord.detect_axis_swap(northings, eastings)["swap_suspected"] is True
    assert coord.detect_axis_swap(eastings, northings)["swap_suspected"] is False


def test_swap_axes_is_pure():
    points = [{"point_number": "1", "easting": 1.0, "northing": 2.0, "elevation": 3.0}]
    swapped = coord.swap_axes(points)
    assert swapped[0]["easting"] == 2.0 and swapped[0]["northing"] == 1.0
    assert points[0]["easting"] == 1.0  # original untouched


def test_preview_and_column_profiles(sample_dir):
    text = (sample_dir / "sidewalk_survey_rd.txt").read_text(encoding="utf-8")
    analysis = parser.analyze_text_file(text)
    payload = analysis.as_dict()
    assert len(payload["columns"]) == 6
    assert payload["rows_preview"]
    assert payload["columns"][0]["sequential_ratio"] > 0.9
    assert payload["mapping"]["easting"] == 1
