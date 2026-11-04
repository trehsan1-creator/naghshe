#!/usr/bin/env python3
"""
Generate the SurveyPro sample datasets.

The data is *derived from a real geometric model* (a 60 m curved urban street with
curbs, sidewalk, cross-fall, manholes and trees), so every downstream computation --
TIN, contours, cut/fill, GSI polar reduction -- can be validated against a known
ground truth.  Run ``python sample_data/generate_sample_data.py`` to regenerate.

Outputs
-------
sidewalk_survey_rd.txt       comma separated, Dutch header, RD New (EPSG:28992)
sidewalk_survey_messy.txt    whitespace+tab mixture, no header, P N E Z code
proposed_design_rd.txt       proposed ground (new sidewalk + lowered roadway)
leica_ts02_survey.gsi        Leica GSI-8 field book on a local engineering grid
ground_truth.json            the model parameters used by the pytest suite
"""

from __future__ import annotations

import json
import math
import os
from typing import Dict, List, Tuple

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))

# ----------------------------------------------------------------------------------
# Survey design
# ----------------------------------------------------------------------------------
X0, Y0 = 105_420.000, 471_880.000      # RD New origin of the street (Leimuiden, NL)
Z0 = 0.845                             # NAP elevation at station 0
STATION_COUNT = 31                     # 0..60 m at 2 m spacing
STATION_STEP = 2.0
LONGITUDINAL_SLOPE = -0.006            # -0.6 % (draining to the west)
ROAD_CROSSFALL = -0.015                # 1.5 % cross fall from the crown
CURB_HEIGHT = 0.12                     # 12 cm curb
CURB_FACE = 3.20                       # road edge (bottom of curb)
CURB_TOP = 3.50                        # top of curb
SIDEWALK_BACK = 6.00                   # rear edge of the sidewalk
BEND_RADIUS = 400.0                    # street bends to the left with R = 400 m

# vertical angle / distance observation settings for the GSI file
GSI_STATION = (512.420, 918.880, 8.845)   # local engineering grid (metres)
GSI_INSTRUMENT_HEIGHT = 1.520
GSI_REFLECTOR_HEIGHT = 1.700
GON = 200.0 / math.pi                     # radians -> gon


def rng(seed: int = 20241104) -> np.random.Generator:
    return np.random.default_rng(seed)


def centreline(station: float) -> Tuple[float, float, float]:
    """Point on the curved centreline + tangent angle (radians, clockwise from north)."""
    theta = station / BEND_RADIUS
    # circular arc starting heading north, curving east
    x = X0 + BEND_RADIUS * (1.0 - math.cos(theta))
    y = Y0 + BEND_RADIUS * math.sin(theta)
    return x, y, theta


def frame(station: float) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    cx, cy, theta = centreline(station)
    # heading vector (direction of travel)
    heading = np.array([math.sin(theta), math.cos(theta)])
    normal = np.array([heading[1], -heading[0]])  # right-hand normal
    return np.array([cx, cy]), heading, normal


def surface_z(station: float, offset: float, *, proposed: bool = False) -> float:
    """Ground elevation model: longitudinal grade + road crown + curb + sidewalk."""
    base = Z0 + LONGITUDINAL_SLOPE * station
    a = abs(offset)
    if a <= CURB_FACE:
        z = base + ROAD_CROSSFALL * a           # road, falls to the gutter
    elif a <= CURB_TOP:
        z = base + ROAD_CROSSFALL * CURB_FACE + CURB_HEIGHT
    else:
        z = base + ROAD_CROSSFALL * CURB_FACE + CURB_HEIGHT - 0.008 * (a - CURB_TOP)
    if not proposed:
        return z
    # ---- proposed design -----------------------------------------------------------
    #  Roadway milled and reconstructed 5 cm lower; curb and sidewalk raised 15 cm with a
    #  1:50 crossfall towards the road.  Continuous across the curb top so the TIN can
    #  represent it exactly with the surveyed rows.
    if a > CURB_FACE:
        return z + 0.150 + 0.020 * max(0.0, a - CURB_TOP)
    return z - 0.050


def station_offsets() -> List[float]:
    return [i * STATION_STEP for i in range(STATION_COUNT)]


# ----------------------------------------------------------------------------------
# Feature construction
# ----------------------------------------------------------------------------------
def build_points(proposed: bool = False) -> List[Dict[str, object]]:
    noise = rng(7 if proposed else 3)
    points: List[Dict[str, object]] = []
    stations = station_offsets()
    last = len(stations) - 1

    def add(code: str, station: float, offset: float, suffix: str = "") -> None:
        origin, heading, normal = frame(station)
        xy = origin + normal * offset
        z = surface_z(station, offset, proposed=proposed) + float(noise.normal(0.0, 0.003))
        points.append(
            {
                "easting": round(float(xy[0]) + float(noise.normal(0, 0.002)), 3),
                "northing": round(float(xy[1]) + float(noise.normal(0, 0.002)), 3),
                "elevation": round(z, 3),
                "code": code,
                "description": suffix,
            }
        )

    # --- centreline (alignment) ---------------------------------------------------
    for i, st in enumerate(stations):
        code = "CL1 ST" if i == 0 else ("CL1 END" if i == last else "CL1")
        add(code, st, 0.0, "road centre")

    # --- left curb: bottom then top (two breaklines, one per side) ----------------
    for i, st in enumerate(stations):
        code = "KBL1 ST" if i == 0 else ("KBL1 END" if i == last else "KBL1")
        add(code, st, -CURB_TOP, "curb top left")
    for i, st in enumerate(stations):
        code = "KBBL1 ST" if i == 0 else ("KBBL1 END" if i == last else "KBBL1")
        add(code, st, -CURB_FACE, "curb bottom left")

    # --- right curb ---------------------------------------------------------------
    for i, st in enumerate(stations):
        code = "KBR1 ST" if i == 0 else ("KBR1 END" if i == last else "KBR1")
        add(code, st, CURB_TOP, "curb top right")
    for i, st in enumerate(stations):
        code = "KBBR1 ST" if i == 0 else ("KBBR1 END" if i == last else "KBBR1")
        add(code, st, CURB_FACE, "curb bottom right")

    # --- sidewalk rear edges ------------------------------------------------------
    for i, st in enumerate(stations):
        code = "SWL1 ST" if i == 0 else ("SWL1 END" if i == last else "SWL1")
        add(code, st, -SIDEWALK_BACK, "sidewalk rear left")
    for i, st in enumerate(stations):
        code = "SWR1 ST" if i == 0 else ("SWR1 END" if i == last else "SWR1")
        add(code, st, SIDEWALK_BACK, "sidewalk rear right")

    # --- trees on the left sidewalk ------------------------------------------------
    for st in (5.0, 15.0, 25.0, 35.0, 45.0, 55.0):
        add("TR20", st, -5.00, "tree 20 cm")
    # --- manholes / drains ---------------------------------------------------------
    for st, off in ((8.0, -1.60), (24.0, 1.40), (42.0, -1.20)):
        add("MH", st, off, "rioolput")
    # --- lamp posts ------------------------------------------------------------------
    for st in (10.0, 30.0, 50.0):
        add("LAMP", st, 5.20, "lighting")

    # numbering: 1..n in survey order
    for i, p in enumerate(points, start=1):
        p["point_number"] = str(i)
    return points


def point_number_map(points: List[Dict[str, object]]) -> Dict[str, List[int]]:
    out: Dict[str, List[int]] = {}
    for p in points:
        base = str(p["code"]).split()[0]
        base = "".join(ch for ch in base if not ch.isdigit()).upper() or base
        out.setdefault(base, []).append(int(p["point_number"]))
    return out


# ----------------------------------------------------------------------------------
# Writers
# ----------------------------------------------------------------------------------
def write_rd_csv(points: List[Dict[str, object]], path: str) -> None:
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("Puntnummer,X,Y,Z,Code,Omschrijving\n")
        for p in points:
            fh.write(
                f"{p['point_number']},{p['easting']:.3f},{p['northing']:.3f},"
                f"{p['elevation']:.3f},{p['code']},{p['description']}\n"
            )


def write_messy_txt(points: List[Dict[str, object]], path: str) -> None:
    """A deliberately messy, header-less, mixed-delimiter field export."""
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        for i, p in enumerate(points):
            sep = "\t" if i % 3 == 0 else ("  " if i % 3 == 1 else " ")
            code = str(p["code"]).replace(" ", "_")
            fh.write(
                f"{p['point_number']}{sep}{p['northing']:.3f}{sep}{p['easting']:.3f}"
                f"{sep}{p['elevation']:.3f}{sep}{code}\n"
            )


def write_gsi(points: List[Dict[str, object]], path: str) -> None:
    """Write a Leica GSI-8 field book: station setup, backsight, polar observations.

    The observations are *computed from the RD model*, projected into a local grid, so a
    correct polar reduction in the parser must reproduce those local coordinates.
    """
    ex, ey, ez = GSI_STATION
    ih = GSI_INSTRUMENT_HEIGHT
    rh = GSI_REFLECTOR_HEIGHT
    # local grid = RD shifted so that values fit the 8-digit GSI-8 data field
    ox, oy = X0 - 400.0, Y0 - 400.0

    def word(wi: str, value: int, info: str = "..00") -> str:
        return f"{wi}{info}{'+' if value >= 0 else '-'}{abs(int(value)):08d}"

    def code_word(code: str) -> str:
        return f"41..00+{code[:8]:<8}"

    lines: List[str] = []
    # station setup: point 1, station coordinates 84/85/86, heights 87/88
    lines.append(
        " ".join(
            [
                word("11", 1),
                word("84", round(ex * 1000)),
                word("85", round(ey * 1000)),
                word("86", round(ez * 1000)),
                word("88", round(ih * 1000)),
                word("87", round(rh * 1000)),
            ]
        )
    )
    # backsight to point 2 (known coordinate block, azimuth reference)
    bs_station, bs_heading, _ = frame(0.0)
    bs_target = np.array([X0 - ox, Y0 - oy])
    az_bs = math.atan2(bs_target[0] - ex, bs_target[1] - ey) % (2 * math.pi)
    bs_dist = float(np.hypot(*(bs_target - np.array([ex, ey]))))
    hz_bs = az_bs  # orientation reference: Hz read equals the azimuth to the backsight
    lines.append(
        " ".join(
            [
                word("11", 2),
                word("21", round(hz_bs * GON * 10_000)),
                word("22", round((math.pi / 2) * GON * 10_000)),
                word("31", round(bs_dist * 1000)),
                word("41", 0),  # placeholder replaced below
                word("81", round((X0 - ox) * 1000)),
                word("82", round((Y0 - oy) * 1000)),
                word("83", round(Z0 * 1000)),
            ]
        ).replace(word("41", 0), code_word("BS"))
    )

    truth: List[Dict[str, float]] = []
    for idx, p in enumerate(points, start=10):
        tx = float(p["easting"]) - ox
        ty = float(p["northing"]) - oy
        tz = float(p["elevation"])
        dx, dy = tx - ex, ty - ey
        hz = math.atan2(dx, dy) % (2 * math.pi)
        horiz = math.hypot(dx, dy)
        dz = (tz + rh) - (ez + ih)   # reflector centre is rh above the ground mark
        slope = math.hypot(horiz, dz)
        zenith = math.atan2(horiz, dz) if slope > 0 else math.pi / 2
        lines.append(
            " ".join(
                [
                    word("11", idx),
                    word("21", round(hz * GON * 10_000), ".324"),
                    word("31", round(slope * 1000)),
                    word("41", 0),
                    word("22", round(zenith * GON * 10_000), ".324"),
                    word("87", round(rh * 1000)),
                ]
            ).replace(word("41", 0), code_word(str(p["code"]).split()[0]))
        )
        truth.append(
            {
                "point_number": str(idx),
                "easting": round(tx, 3),
                "northing": round(ty, 3),
                "elevation": round(tz, 3),
                "slope_distance": round(slope, 3),
                "zenith_gon": round(zenith * GON, 4),
                "hz_gon": round(hz * GON, 4),
            }
        )

    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(lines) + "\n")

    with open(os.path.join(HERE, "gsi_ground_truth.json"), "w", encoding="utf-8") as fh:
        json.dump(
            {
                "station": {"easting": ex, "northing": ey, "elevation": ez,
                            "instrument_height": ih, "reflector_height": rh},
                "offset": {"easting": ox, "northing": oy},
                "points": truth,
            },
            fh,
            indent=2,
        )


def main() -> None:
    existing = build_points(proposed=False)
    proposed = build_points(proposed=True)

    write_rd_csv(existing, os.path.join(HERE, "sidewalk_survey_rd.txt"))
    write_messy_txt(existing, os.path.join(HERE, "sidewalk_survey_messy.txt"))
    write_rd_csv(proposed, os.path.join(HERE, "proposed_design_rd.txt"))
    write_gsi(existing, os.path.join(HERE, "leica_ts02_survey.gsi"))

    truth = {
        "existing_points": len(existing),
        "proposed_points": len(proposed),
        "crs": "EPSG:28992",
        "origin": {"x": X0, "y": Y0, "z": Z0},
        "street_length_m": station_offsets()[-1],
        "expected_curb": {"face": CURB_FACE, "top": CURB_TOP, "height": CURB_HEIGHT},
        "elevation_range": [
            min(float(p["elevation"]) for p in existing),
            max(float(p["elevation"]) for p in existing),
        ],
    }
    with open(os.path.join(HERE, "ground_truth.json"), "w", encoding="utf-8") as fh:
        json.dump(truth, fh, indent=2)
    print(
        f"wrote {len(existing)} existing points, {len(proposed)} proposed points, "
        f"1 GSI field book"
    )


if __name__ == "__main__":
    main()
