"""Leica GSI-8 / GSI-16 parsing and polar reduction against a known ground truth."""

from __future__ import annotations

import json
import math

import pytest

from app.engines import txt_gsi_parser as parser

GON = 200.0 / math.pi


def _word(wi: str, value: int, info: str = "..00") -> str:
    return f"{wi}{info}{'+' if value >= 0 else '-'}{abs(int(value)):08d}"


def test_word_structure_gsi8():
    line = "110001+0000A110 81..00+00005387 82..00-00000992"
    block, issues = parser._parse_gsi_line(line, 1)
    assert not issues
    assert len(block.words) == 3
    assert block.words[0].wi == "11" and block.words[0].text == "0000A110"
    assert block.words[1].wi == "81" and block.words[1].value == 5387
    assert block.words[2].sign == "-" and block.words[2].value == -992


def test_word_structure_gsi16():
    line = "*110005+000000000PNC0059 21.324+0000000009983610 22.002+0000000005171400"
    block, _ = parser._parse_gsi_line(line, 1)
    assert block.is_gsi16
    assert block.words[0].text == "000000000PNC0059"
    assert block.words[1].wi == "21"
    assert block.words[1].value == 9983610


def test_distance_scale_millimetres():
    word, _ = parser._parse_gsi_line("81..00+01999507", 1)
    value, _ = parser._decode_gsi_distance(word.words[0], parser.GsiOptions())
    assert value == pytest.approx(1999.507, abs=1e-6)


def test_angle_decode_gon():
    word, _ = parser._parse_gsi_line("21.324+001234500", 1)
    radians, issues = parser._decode_gsi_angle(word.words[0], parser.GsiOptions())
    assert not issues
    assert radians * GON == pytest.approx(123.45, abs=1e-6)


def test_angle_decode_degrees():
    # the GSI word carries 4 implied decimals, so 1234500 is 123.4500 in either unit
    word, _ = _parse_one("21.324+001234500")
    radians, _ = parser._decode_gsi_angle(word, parser.GsiOptions(angle_unit="deg"))
    assert math.degrees(radians) == pytest.approx(123.45, abs=1e-6)
    gon, _ = parser._decode_gsi_angle(word, parser.GsiOptions(angle_unit="gon"))
    assert gon * GON == pytest.approx(123.45, abs=1e-6)


def _parse_one(line: str):
    block, _ = parser._parse_gsi_line(line, 1)
    return block.words[0], block


def test_dms_decode():
    # 52°12'34.5600" packed as 5212345600
    rad = parser._dms_packed_to_rad(5212345600)
    assert math.degrees(rad) == pytest.approx(52 + 12 / 60 + 34.56 / 3600, abs=1e-9)


def test_polar_reduction_matches_ground_truth(sample_dir):
    truth = json.loads((sample_dir / "gsi_ground_truth.json").read_text())
    text = (sample_dir / "leica_ts02_survey.gsi").read_text()
    result = parser.parse_gsi(text)

    assert result.stats["stations"] == 1
    assert result.stats["reduced_points"] == len(truth["points"])
    assert result.stats["vertical_angle_mode"] == "zenith"

    by_number = {p.point_number: p for p in result.points}
    worst = 0.0
    for expected in truth["points"]:
        parsed = by_number[expected["point_number"]]
        dx = parsed.easting - expected["easting"]
        dy = parsed.northing - expected["northing"]
        dz = (parsed.elevation or 0.0) - expected["elevation"]
        worst = max(worst, abs(dx), abs(dy), abs(dz))
        assert abs(dx) < 0.002
        assert abs(dy) < 0.002
        assert abs(dz) < 0.002
    assert worst < 0.002, f"worst polar-reduction error {worst * 1000:.2f} mm"


def test_station_and_observation_records(sample_dir):
    text = (sample_dir / "leica_ts02_survey.gsi").read_text()
    result = parser.parse_gsi(text)
    station = result.stations[0]
    assert station.point_number == "1"
    assert station.easting == pytest.approx(512.42, abs=1e-3)
    assert station.instrument_height == pytest.approx(1.52, abs=1e-3)
    assert station.orientation_rad is not None
    assert all(o.slope_distance and o.slope_distance > 0 for o in result.observations)
    assert all(o.hz_rad is not None for o in result.observations)


def test_reduction_respects_instrument_and_reflector_height():
    station = parser.GsiStation("1", easting=0.0, northing=0.0, elevation=100.0, instrument_height=1.5)
    obs = parser.GsiObservation(
        point_number="2", line_no=1, hz_rad=0.0, v_rad=math.pi / 2, slope_distance=10.0,
        reflector_height=1.7,
    )
    (east, north, elev), issues = parser.reduce_observation(station, obs, vertical_angle_mode="zenith")
    assert east == pytest.approx(0.0, abs=1e-9)
    assert north == pytest.approx(10.0, abs=1e-9)
    assert elev == pytest.approx(100.0 + 1.5 - 1.7, abs=1e-9)


def test_vertical_angle_convention_auto_detected():
    station = parser.GsiStation("1", easting=0.0, northing=0.0, elevation=0.0, instrument_height=0.0)
    # vertical angle 5 gon above the horizon => zenith = 95 gon
    obs = parser.GsiObservation(
        point_number="2", line_no=1, hz_rad=0.0, v_rad=5.0 / GON, slope_distance=100.0
    )
    (_, north, elev), _ = parser.reduce_observation(station, obs, vertical_angle_mode="vertical")
    assert elev == pytest.approx(100.0 * math.sin(5.0 / GON), abs=1e-6)
    assert north == pytest.approx(100.0 * math.cos(5.0 / GON), abs=1e-6)


def test_format_sniffing():
    assert parser.sniff_format("x.txt", "110001+0000A110 81..00+00005387") == "gsi"
    assert parser.sniff_format("x.gsi", "") == "gsi"
    assert parser.sniff_format("x.csv", "1,2,3,4\n") == "csv"
    assert parser.sniff_format("x.dxf", "0\nSECTION\n2\nHEADER\n") == "dxf"
    assert parser.sniff_format("x.xml", '<?xml version="1.0"?><LandXML></LandXML>') == "landxml"


def test_stationless_gsi_reports_error():
    text = "110001+00000001 21.324+001234500 31..00+00010000\n"
    result = parser.parse_gsi(text)
    codes = [i.code for i in result.issues]
    assert "gsi_station_unknown" in codes
