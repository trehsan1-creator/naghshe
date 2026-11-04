"""
SurveyPro -- Field-to-Finish: Code-to-Block & Intelligent Linework
=================================================================

Converts flat survey point lists into CAD-ready features exactly the way a
field-to-finish package (F2F) does:

* **Point codes** become blocks on standard layers (``TR`` -> TREE on ``S-TREE``).
* **Sequential linework commands** embedded in the code string build polylines and
  polygons::

      CURB1 ST    start the feature named CURB1
      CURB1        continue it (implicit)
      CURB1 CL    close the polygon (adds the closing segment)
      CURB1 END   end the feature without closing

* A **default layer standard** (``S-POINT``, ``S-ELEV``, ``S-CURB``, ``S-SIDEWALK``,
  ``S-CONTOUR`` ...) is applied so the DXF opens correctly in AutoCAD/BricsCAD with the
  right colours, and so the web canvas can style features consistently.

Nothing here is decorative: the output is the same data structure that is written to
DXF, drawn on the canvas and measured (length/area/closure error).
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from .txt_gsi_parser import Issue

__all__ = [
    "CodeDefinition",
    "DEFAULT_CODE_LIBRARY",
    "DEFAULT_LAYERS",
    "LineworkFeature",
    "LineworkResult",
    "parse_code_string",
    "build_linework",
    "layer_for_code",
    "normalise_code",
]

# --------------------------------------------------------------------------------------
# Layer standard (AutoCAD ACI colours; S- prefix = Survey layer family)
# --------------------------------------------------------------------------------------
DEFAULT_LAYERS: List[Dict[str, Any]] = [
    {"name": "S-POINT", "color": 7, "linetype": "CONTINUOUS", "description": "Generic survey points"},
    {"name": "S-ELEV", "color": 8, "linetype": "CONTINUOUS", "description": "Elevation text"},
    {"name": "S-PN", "color": 9, "linetype": "CONTINUOUS", "description": "Point numbers"},
    {"name": "S-CURB", "color": 30, "linetype": "CONTINUOUS", "description": "Curb lines"},
    {"name": "S-SIDEWALK", "color": 40, "linetype": "CONTINUOUS", "description": "Sidewalk / pavement edges"},
    {"name": "S-ROAD", "color": 32, "linetype": "CONTINUOUS", "description": "Asphalt / roadway edges"},
    {"name": "S-GUTTER", "color": 33, "linetype": "CONTINUOUS", "description": "Gutter lines"},
    {"name": "S-TREE", "color": 94, "linetype": "CONTINUOUS", "description": "Trees (block TR)"},
    {"name": "S-MANHOLE", "color": 6, "linetype": "CONTINUOUS", "description": "Manholes / drains (block MH)"},
    {"name": "S-POLE", "color": 2, "linetype": "CONTINUOUS", "description": "Poles (block POLE)"},
    {"name": "S-LAMP", "color": 2, "linetype": "CONTINUOUS", "description": "Street lighting (block LAMP)"},
    {"name": "S-BUILDING", "color": 12, "linetype": "CONTINUOUS", "description": "Building footprints"},
    {"name": "S-FENCE", "color": 250, "linetype": "DASHED", "description": "Fences / walls"},
    {"name": "S-BREAKLINE", "color": 1, "linetype": "DASHED", "description": "TIN breaklines"},
    {"name": "S-CONTOUR-MINOR", "color": 251, "linetype": "CONTINUOUS", "description": "Minor contours"},
    {"name": "S-CONTOUR-MAJOR", "color": 250, "linetype": "CONTINUOUS", "description": "Index contours"},
    {"name": "S-TIN", "color": 253, "linetype": "CONTINUOUS", "description": "TIN 3DFACE mesh"},
    {"name": "S-BOUNDARY", "color": 5, "linetype": "CONTINUOUS", "description": "Surface boundary"},
    {"name": "S-SURFACE", "color": 4, "linetype": "CONTINUOUS", "description": "Surface text / spot heights"},
    {"name": "S-XSECT", "color": 5, "linetype": "CONTINUOUS", "description": "Cross sections"},
    {"name": "S-PROFILE", "color": 4, "linetype": "CONTINUOUS", "description": "Longitudinal profile"},
    {"name": "S-ALIGNMENT", "color": 6, "linetype": "CENTER", "description": "Alignment / centreline"},
    {"name": "S-VOLUME", "color": 3, "linetype": "CONTINUOUS", "description": "Cut/fill boundaries"},
]


@dataclass
class CodeDefinition:
    """Mapping from a field code to CAD output."""

    code: str
    kind: str                 # 'block' | 'line' | 'polygon' | 'point'
    layer: str
    block_name: Optional[str] = None
    color: int = 7
    description: str = ""
    # Optional attribute extraction: e.g. TR20 (diameter 20 cm)
    attribute_pattern: Optional[str] = None

    def as_dict(self) -> Dict[str, Any]:
        return {
            "code": self.code,
            "kind": self.kind,
            "layer": self.layer,
            "block_name": self.block_name,
            "color": self.color,
            "description": self.description,
        }


DEFAULT_CODE_LIBRARY: List[CodeDefinition] = [
    # --- point symbols (blocks) ------------------------------------------------------
    CodeDefinition("TR", "block", "S-TREE", "TR", 94, "Tree", r"^TR(?P<diameter>\d{1,3})?$"),
    CodeDefinition("TREE", "block", "S-TREE", "TR", 94, "Tree", r"^TREE(?P<diameter>\d{1,3})?$"),
    CodeDefinition("MH", "block", "S-MANHOLE", "MH", 6, "Manhole / rioolput"),
    CodeDefinition("MANHOLE", "block", "S-MANHOLE", "MH", 6, "Manhole"),
    CodeDefinition("DRAIN", "block", "S-MANHOLE", "MH", 6, "Drain"),
    CodeDefinition("POLE", "block", "S-POLE", "POLE", 2, "Utility pole"),
    CodeDefinition("PL", "block", "S-POLE", "POLE", 2, "Utility pole"),
    CodeDefinition("LAMP", "block", "S-LAMP", "LAMP", 2, "Street light"),
    CodeDefinition("BM", "block", "S-POINT", "BM", 1, "Benchmark"),
    # --- linework --------------------------------------------------------------------
    CodeDefinition("CURB", "line", "S-CURB", None, 30, "Curb line"),
    CodeDefinition("KB", "line", "S-CURB", None, 30, "Kantband (curb)"),
    CodeDefinition("SW", "line", "S-SIDEWALK", None, 40, "Sidewalk edge"),
    CodeDefinition("TP", "line", "S-SIDEWALK", None, 40, "Tegelpad (paved path)"),
    CodeDefinition("ROAD", "line", "S-ROAD", None, 32, "Road edge"),
    CodeDefinition("ASPH", "line", "S-ROAD", None, 32, "Asphalt edge"),
    CodeDefinition("GUT", "line", "S-GUTTER", None, 33, "Gutter"),
    CodeDefinition("EDGE", "line", "S-SIDEWALK", None, 40, "Surface edge"),
    CodeDefinition("CL", "line", "S-ROAD", None, 32, "Centreline"),
    CodeDefinition("FENCE", "line", "S-FENCE", None, 250, "Fence"),
    CodeDefinition("WALL", "line", "S-FENCE", None, 250, "Wall"),
    CodeDefinition("BLDG", "polygon", "S-BUILDING", None, 12, "Building footprint"),
    CodeDefinition("BLD", "polygon", "S-BUILDING", None, 12, "Building footprint"),
    CodeDefinition("PARCEL", "polygon", "S-BOUNDARY", None, 5, "Parcel boundary"),
    CodeDefinition("BRK", "line", "S-BREAKLINE", None, 1, "TIN breakline"),
    CodeDefinition("STN", "point", "S-POINT", None, 1, "Station / control point"),
]

COMMANDS = {
    "ST": "start",
    "START": "start",
    "B": "start",
    "BEGIN": "start",
    "END": "end",
    "E": "end",
    "CL": "close",
    "CLOSE": "close",
    "C": "close",
}

_LIBRARY_BY_CODE: Dict[str, CodeDefinition] = {d.code.upper(): d for d in DEFAULT_CODE_LIBRARY}


def normalise_code(raw: str) -> str:
    """Upper-case, strip attributes and control codes from a raw field code."""
    if raw is None:
        return ""
    return str(raw).strip().upper()


def parse_code_string(raw: str) -> Dict[str, Any]:
    """Split a field code into ``{feature, base, command, attributes}``.

    Handles the real forms found in Leica/Carlson/SurvCE exports::

        'CURB1 ST'   -> feature 'CURB1', base 'CURB', command 'start'
        'CURB1'      -> feature 'CURB1', base 'CURB', command None
        'SW2.CL'     -> feature 'SW2',  base 'SW',   command 'close'
        'TR20'       -> feature 'TR20', base 'TR',   command None, attributes {'diameter': 20}
        'MH-01'      -> feature 'MH1',  base 'MH',   command None
    """
    # underscores are commonly written instead of spaces when a device cannot emit them
    text = normalise_code(raw).replace("_", " ")
    result: Dict[str, Any] = {
        "raw": raw,
        "feature": "",
        "base": "",
        "command": None,
        "attributes": {},
        "suffix": "",
    }
    if not text:
        return result

    tokens = [t for t in re.split(r"[\s.]+", text) if t]
    command = None
    if len(tokens) > 1 and tokens[-1] in COMMANDS:
        command = COMMANDS[tokens[-1]]
        tokens = tokens[:-1]
    feature = tokens[0] if tokens else ""
    # attributes: remaining tokens like 'TR' '20' or 'SW' 'R' (right offset)
    if len(tokens) > 1:
        result["attributes"]["params"] = tokens[1:]

    # split base code from a numeric suffix (and optional side letter):
    #   CURB1 -> (CURB, 1)   TR20 -> (TR, 20)   CURB1R -> (CURB, 1, R)   MH -> (MH)
    feature_clean = feature.replace("-", "").replace("_", "")
    base = feature_clean
    m = re.match(r"^([A-Z]+?)(\d+)([A-Z])?$", feature_clean)
    plain = re.match(r"^([A-Z]+)$", feature_clean)
    if m:
        base = m.group(1)
        result["suffix"] = m.group(2)
        result["attributes"]["index"] = int(m.group(2))
        if m.group(3):
            result["suffix"] += m.group(3)
            result["attributes"]["side"] = m.group(3)
    elif plain:
        base = plain.group(1)
    result.update({"feature": feature, "base": base, "command": command})
    return result


def lookup_definition(base: str, library: Sequence[CodeDefinition] | None = None) -> Optional[CodeDefinition]:
    """Find the definition for a base code, longest-prefix first."""
    lib = library or DEFAULT_CODE_LIBRARY
    table = {d.code.upper(): d for d in lib}
    if base in table:
        return table[base]
    # longest prefix match ('SWHOEK' -> 'SW')
    for code in sorted(table, key=len, reverse=True):
        if base.startswith(code):
            return table[code]
    return None


def layer_for_code(code: str, library: Sequence[CodeDefinition] | None = None) -> str:
    parsed = parse_code_string(code)
    definition = lookup_definition(parsed["base"], library)
    return definition.layer if definition else "S-POINT"


@dataclass
class LineworkFeature:
    """A resolved linework feature (polyline or polygon)."""

    name: str
    base_code: str
    kind: str                 # 'line' | 'polygon'
    layer: str
    vertices: List[Tuple[float, float, float]] = field(default_factory=list)
    point_numbers: List[str] = field(default_factory=list)
    closed: bool = False
    length: float = 0.0
    area: float = 0.0
    closure_error: Optional[float] = None

    def as_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "base_code": self.base_code,
            "kind": self.kind,
            "layer": self.layer,
            "vertices": [list(v) for v in self.vertices],
            "point_numbers": self.point_numbers,
            "closed": self.closed,
            "length": round(self.length, 4),
            "area": round(self.area, 4),
            "closure_error": None if self.closure_error is None else round(self.closure_error, 4),
        }


@dataclass
class LineworkResult:
    features: List[LineworkFeature]
    issues: List[Issue]
    stats: Dict[str, Any]

    def as_dict(self) -> Dict[str, Any]:
        return {
            "features": [f.as_dict() for f in self.features],
            "issues": [i.as_dict() for i in self.issues],
            "stats": self.stats,
        }


def _polyline_length(vertices: Sequence[Tuple[float, float, float]], closed: bool) -> float:
    pts = list(vertices) + ([vertices[0]] if closed and vertices else [])
    return sum(
        math.dist((a[0], a[1]), (b[0], b[1])) for a, b in zip(pts, pts[1:])
    )


def _polygon_area(vertices: Sequence[Tuple[float, float, float]]) -> float:
    if len(vertices) < 3:
        return 0.0
    area = 0.0
    pts = list(vertices)
    for i in range(len(pts)):
        x1, y1 = pts[i][0], pts[i][1]
        x2, y2 = pts[(i + 1) % len(pts)][0], pts[(i + 1) % len(pts)][1]
        area += x1 * y2 - x2 * y1
    return abs(area) / 2.0


def build_linework(
    points: Sequence[Dict[str, Any]],
    library: Sequence[CodeDefinition] | None = None,
    *,
    connect_mode: str = "auto",
) -> LineworkResult:
    """Build linework features from coded points.

    ``connect_mode``:
      * ``'command'`` -- only explicit ST / CL / END commands create and finish features
        (strict field-to-finish behaviour).
      * ``'sequential'`` -- every run of consecutive points sharing a base code forms a
        line automatically (fast for point-only files).
      * ``'auto'`` -- command mode, but a point whose code appears twice in a row also
        starts/continues a feature implicitly (a pragmatic hybrid).
    """
    issues: List[Issue] = []
    features: List[LineworkFeature] = []
    open_features: Dict[str, LineworkFeature] = {}
    unmatched_codes: Dict[str, int] = {}
    started = 0
    explicit_features: set = set()

    for p in points:
        raw_code = str(p.get("code") or "").strip()
        if not raw_code:
            continue
        parsed = parse_code_string(raw_code)
        base = parsed["base"]
        definition = lookup_definition(base, library)
        if definition is None:
            unmatched_codes[base] = unmatched_codes.get(base, 0) + 1

        vertex = (
            float(p["easting"]),
            float(p["northing"]),
            float(p.get("elevation") or 0.0),
        )
        pn = str(p.get("point_number", ""))

        if definition is None or definition.kind in ("block", "point"):
            # symbol codes never participate in linework
            continue

        name = parsed["feature"] or base
        command = parsed["command"]

        if command == "start" or (
            command is None
            and connect_mode == "sequential"
            and (name not in open_features)
        ):
            feature = open_features.get(name)
            if feature is None:
                feature = LineworkFeature(
                    name=name, base_code=base, kind="line",
                    layer=definition.layer, closed=False,
                )
                open_features[name] = feature
                started += 1
            feature.vertices.append(vertex)
            feature.point_numbers.append(pn)
            continue

        feature = open_features.get(name)
        if feature is None:
            if connect_mode == "sequential":
                continue
            feature = LineworkFeature(
                name=name, base_code=base, kind="line",
                layer=definition.layer, closed=False,
            )
            open_features[name] = feature
            issues.append(
                Issue(
                    "info",
                    "linework_implicit_start",
                    f"Feature '{name}' has no start command; started at point {pn}.",
                    column="code",
                    value=raw_code,
                )
            )
        feature.vertices.append(vertex)
        feature.point_numbers.append(pn)

        if command in ("close", "end"):
            explicit_features.add(name)
            del open_features[name]
            feature.closed = command == "close" or definition.kind == "polygon"
            _finalise(feature, definition, issues)
            features.append(feature)

    # Anything still open at end of file is closed off with a warning.
    for name, feature in open_features.items():
        feature.closed = False
        issues.append(
            Issue(
                "warning",
                "linework_unterminated",
                f"Feature '{name}' was never ended (no END/CL command); "
                f"{len(feature.vertices)} vertices kept as an open polyline.",
            )
        )
        _finalise(feature, lookup_definition(feature.base_code, library), issues)
        features.append(feature)

    for code, count in unmatched_codes.items():
        issues.append(
            Issue(
                "info",
                "code_not_mapped",
                f"Code '{code}' ({count} point(s)) is not in the code library; "
                "mapped to the S-POINT layer.",
                value=code,
            )
        )

    total_length = sum(f.length for f in features)
    total_area = sum(f.area for f in features if f.closed)
    stats = {
        "points_considered": len(points),
        "features": len(features),
        "open_features": len(open_features),
        "started": started,
        "total_length": round(total_length, 3),
        "total_area": round(total_area, 3),
        "unmatched_codes": unmatched_codes,
        "connect_mode": connect_mode,
    }
    return LineworkResult(features, issues, stats)


def _finalise(
    feature: LineworkFeature,
    definition: Optional[CodeDefinition],
    issues: List[Issue],
) -> None:
    """Compute geometry metrics and apply the polygon rule from the code library."""
    if definition is not None and definition.kind == "polygon":
        feature.closed = True
    if len(feature.vertices) < 2:
        issues.append(
            Issue(
                "warning",
                "linework_too_short",
                f"Feature '{feature.name}' has only {len(feature.vertices)} vertex/vertices.",
            )
        )
        return
    feature.length = _polyline_length(feature.vertices, feature.closed)
    if feature.closed:
        if len(feature.vertices) >= 3:
            feature.area = _polygon_area(feature.vertices)
            first, last = feature.vertices[0], feature.vertices[-1]
            feature.closure_error = math.dist((first[0], first[1]), (last[0], last[1]))
            feature.kind = "polygon"
            if feature.closure_error > 0.05:
                issues.append(
                    Issue(
                        "warning",
                        "linework_closure_error",
                        f"Feature '{feature.name}' is closed but its first and last point are "
                        f"{feature.closure_error * 100:.1f} cm apart.",
                        value=feature.name,
                    )
                )
        else:
            issues.append(
                Issue(
                    "warning",
                    "linework_polygon_too_few_vertices",
                    f"Feature '{feature.name}' was closed with fewer than 3 vertices.",
                )
            )
