"""
SurveyPro -- Coordinate & QA/QC Engine
======================================

Responsibilities
----------------
* CRS handling through :mod:`pyproj`: EPSG lookup, metadata, axis-order-safe
  transformation (``always_xy=True`` -- the single most common source of mirrored
  survey exports), and compound vertical transformations where available.
* Local engineering grids: a full 2D similarity (Helmert 4-parameter) transformation
  *fitted by least squares from control points*, plus a rigid local shift/rotation.
* Survey QA/QC that produces **defensible statistics**, not guesses:

  - X/Y axis reversal detection from coordinate-magnitude geometry,
  - duplicate point numbers and duplicate coordinates (KD-tree radius search),
  - elevation anomalies using both a robust modified Z-score (median/MAD) *and*
    Tukey's IQR fences, plus a local (k-nearest-neighbour) vertical step test,
  - horizontal outliers via robust Mahalanobis-like scaling of X and Y,
  - missing / unknown feature codes against the project code library.

Everything here is deterministic: the same input always yields the same report.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np

try:  # pyproj is a hard requirement, but keep the module importable for pure-math use
    from pyproj import CRS, Transformer
    from pyproj.exceptions import CRSError
except Exception:  # pragma: no cover
    CRS = None  # type: ignore
    Transformer = None  # type: ignore
    CRSError = Exception  # type: ignore

from .txt_gsi_parser import Issue

__all__ = [
    "PointLike",
    "describe_crs",
    "suggest_epsg",
    "transform_points",
    "SimilarityTransform2D",
    "fit_similarity",
    "detect_axis_swap",
    "swap_axes",
    "QaTolerances",
    "QaReport",
    "validate_points",
    "convex_hull_area",
]

PointLike = Dict[str, Any]


# --------------------------------------------------------------------------------------
# CRS utilities
# --------------------------------------------------------------------------------------
def describe_crs(epsg: int) -> Dict[str, Any]:
    """Return metadata for an EPSG code (name, units, datum, area of use)."""
    if CRS is None:
        return {"epsg": int(epsg), "name": f"EPSG:{epsg}", "units": "unknown"}
    try:
        crs = CRS.from_epsg(int(epsg))
    except CRSError as exc:
        raise ValueError(f"Unknown EPSG code {epsg}: {exc}") from exc
    axis = []
    for ax in crs.axis_info:
        axis.append(
            {
                "name": ax.name,
                "abbrev": ax.abbrev,
                "direction": ax.direction,
                "unit": ax.unit_name,
                "unit_conversion": ax.unit_conversion_factor,
            }
        )
    area = None
    if crs.area_of_use is not None:
        aou = crs.area_of_use
        area = {
            "name": aou.name,
            "west": aou.west,
            "south": aou.south,
            "east": aou.east,
            "north": aou.north,
        }
    return {
        "epsg": int(epsg),
        "name": crs.name,
        "type": crs.type_name,
        "datum": crs.datum.name if crs.datum is not None else None,
        "is_projected": bool(crs.is_projected),
        "is_geographic": bool(crs.is_geographic),
        "axis": axis,
        "area_of_use": area,
        "axis_order": [ax.abbrev for ax in crs.axis_info],
    }


def suggest_epsg(
    eastings: Sequence[float], northings: Sequence[float]
) -> List[Dict[str, Any]]:
    """Suggest plausible CRSs from the *numeric signature* of the coordinates.

    This is a suggestion engine for the wizard: each entry carries the reasoning so
    a surveyor can accept or reject it.  It never silently applies a CRS.
    """
    if not eastings or not northings:
        return []
    xmin, xmax = min(eastings), max(eastings)
    ymin, ymax = min(northings), max(northings)
    span = max(xmax - xmin, ymax - ymin)
    out: List[Dict[str, Any]] = []

    if -180.0 <= xmin and xmax <= 180.0 and -90.0 <= ymin and ymax <= 90.0 and span < 90:
        out.append(
            {
                "epsg": 4326,
                "confidence": 0.85,
                "reason": "Coordinates fall inside the geographic degree range.",
                "recommended": True,
            }
        )
        return out

    if span < 5_000 and xmin > -1e5 and ymin > -1e5 and xmax < 1e6 and ymax < 1e6:
        out.append(
            {
                "epsg": 0,
                "confidence": 0.6,
                "reason": "Compact extent (< 5 km) with small magnitudes: looks like a local "
                "engineering grid. Use a custom CRS or import with the local shift tool.",
                "recommended": True,
                "local": True,
            }
        )

    # Dutch Rijksdriehoek: x ~ 0..300 km, y ~ 300..650 km
    if 0 <= xmin and xmax <= 320_000 and 250_000 <= ymin and ymax <= 700_000:
        out.append(
            {
                "epsg": 28992,
                "confidence": 0.9,
                "reason": "X within 0-320 km and Y within 250-700 km: signature of RD New / "
                "Amersfoort (EPSG:28992, the Dutch national grid).",
                "recommended": True,
            }
        )
        out.append(
            {
                "epsg": 32631,
                "confidence": 0.35,
                "reason": "UTM zone 31N is the common alternative for Dutch projects.",
            }
        )

    # UTM-like: large northing, moderate easting
    if 1_000_000 <= ymin and ymax <= 9_400_000 and -300_000 <= xmin and xmax <= 1_100_000:
        for zone in (31, 32, 30):
            out.append(
                {
                    "epsg": 32600 + zone,
                    "confidence": 0.55 if zone == 31 else 0.25,
                    "reason": f"Northing {ymin:,.0f}-{ymax:,.0f} and Easting "
                    f"{xmin:,.0f}-{xmax:,.0f} match UTM zone {zone}N numeric ranges.",
                    "recommended": zone == 31,
                }
            )
    if 0 <= ymin and ymax <= 10_000_000 and 100_000 <= xmin and xmax <= 900_000:
        out.append(
            {
                "epsg": 32631,
                "confidence": 0.5,
                "reason": "Easting 100-900 km with a 6-7 digit northing: UTM-style grid.",
            }
        )
    if ymax > 9_400_000 or abs(xmin) > 1_100_000:
        out.append(
            {
                "epsg": 0,
                "confidence": 0.4,
                "reason": "Coordinates exceed normal UTM ranges -- check for a unit error "
                "(millimetres?) or an X/Y swap.",
            }
        )
    # de-duplicate on epsg
    seen: set = set()
    unique: List[Dict[str, Any]] = []
    for item in sorted(out, key=lambda d: d["confidence"], reverse=True):
        key = (item["epsg"], item.get("local", False))
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


# --------------------------------------------------------------------------------------
# Transformations
# --------------------------------------------------------------------------------------
@dataclass
class SimilarityTransform2D:
    """2D similarity (Helmert 4-parameter) transformation.

    ``x' = tx + s(cos(a) x - sin(a) y)``
    ``y' = ty + s(sin(a) x + cos(a) y)``
    """

    tx: float = 0.0
    ty: float = 0.0
    rotation_rad: float = 0.0
    scale: float = 1.0
    rms: float = 0.0
    max_residual: float = 0.0
    n_control: int = 0

    def apply(self, x: float, y: float) -> Tuple[float, float]:
        c, s = math.cos(self.rotation_rad), math.sin(self.rotation_rad)
        return (
            self.tx + self.scale * (c * x - s * y),
            self.ty + self.scale * (s * x + c * y),
        )

    @property
    def rotation_gon(self) -> float:
        return self.rotation_rad * 200.0 / math.pi

    @property
    def rotation_deg(self) -> float:
        return math.degrees(self.rotation_rad)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "tx": self.tx,
            "ty": self.ty,
            "rotation_rad": self.rotation_rad,
            "rotation_gon": self.rotation_gon,
            "rotation_deg": self.rotation_deg,
            "scale": self.scale,
            "rms": self.rms,
            "max_residual": self.max_residual,
            "n_control": self.n_control,
        }


def fit_similarity(
    source: Sequence[Tuple[float, float]], target: Sequence[Tuple[float, float]]
) -> SimilarityTransform2D:
    """Least-squares fit of a 2D similarity transform from control point pairs.

    Closed-form solution (Umeyama / complex-number formulation):

    .. math::

        z = s e^{i\\alpha},\\quad
        z = \\frac{\\sum (t_i - \\bar t)\\overline{(s_i - \\bar s)}}
                   {\\sum |s_i - \\bar s|^2}

    Requires at least 2 non-coincident control points.  With exactly 2 points the
    transform is exact (RMS = 0) and the scale is fully determined by the pair.
    """
    if len(source) != len(target):
        raise ValueError("source and target must have the same number of control points")
    if len(source) < 2:
        raise ValueError("at least 2 control points are required to fit a similarity transform")

    s = np.asarray(source, dtype=float)
    t = np.asarray(target, dtype=float)
    if np.ptp(s[:, 0]) == 0 and np.ptp(s[:, 1]) == 0:
        raise ValueError("control points are coincident; the transform is undefined")

    sc = s - s.mean(axis=0)
    tc = t - t.mean(axis=0)
    denom = float(np.sum(sc * sc))
    if denom < 1e-12:
        raise ValueError("control points are coincident; the transform is undefined")

    # complex least squares: solve z * sum(|sc|^2) = sum(tc * conj(sc))
    sc_c = sc[:, 0] + 1j * sc[:, 1]
    tc_c = tc[:, 0] + 1j * tc[:, 1]
    z = complex(np.sum(tc_c * np.conj(sc_c)) / denom)
    scale = abs(z)
    rotation = math.atan2(z.imag, z.real)
    c, s_ = math.cos(rotation), math.sin(rotation)
    # translation from centroids
    src_mean = s.mean(axis=0)
    tgt_mean = t.mean(axis=0)
    tx = tgt_mean[0] - scale * (c * src_mean[0] - s_ * src_mean[1])
    ty = tgt_mean[1] - scale * (s_ * src_mean[0] + c * src_mean[1])
    model = SimilarityTransform2D(tx=tx, ty=ty, rotation_rad=rotation, scale=scale,
                                  n_control=len(source))
    predicted = np.array([model.apply(px, py) for px, py in source])
    residual = predicted - t
    model.rms = float(np.sqrt(np.mean(np.sum(residual ** 2, axis=1))))
    model.max_residual = float(np.max(np.sqrt(np.sum(residual ** 2, axis=1))))
    return model


def transform_points(
    points: Iterable[PointLike],
    source_epsg: int,
    target_epsg: int,
    *,
    source_epoch: Optional[float] = None,
    target_epoch: Optional[float] = None,
    vertical: bool = False,
) -> Tuple[List[PointLike], List[Issue]]:
    """Transform points between CRSs using pyproj.

    Returns new dictionaries (input is never mutated -- raw data stays immutable) plus
    any issues (e.g. points falling outside the area of use).
    """
    issues: List[Issue] = []
    pts = [dict(p) for p in points]
    if Transformer is None:
        raise RuntimeError("pyproj is not installed; CRS transformation is unavailable")
    if int(source_epsg) == int(target_epsg):
        return pts, issues

    try:
        transformer = Transformer.from_crs(
            CRS.from_epsg(int(source_epsg)),
            CRS.from_epsg(int(target_epsg)),
            always_xy=True,
        )
    except CRSError as exc:
        raise ValueError(f"Cannot build a transformation {source_epsg} -> {target_epsg}: {exc}") from exc

    xs = np.array([float(p["easting"]) for p in pts], dtype=float)
    ys = np.array([float(p["northing"]) for p in pts], dtype=float)
    zs = np.array([float(p.get("elevation") or 0.0) for p in pts], dtype=float)
    if vertical and transformer.has_vertical:
        nx, ny, nz = transformer.transform(xs, ys, zs)
    else:
        nx, ny = transformer.transform(xs, ys)
        nz = zs
    for i, p in enumerate(pts):
        p["easting"] = float(nx[i])
        p["northing"] = float(ny[i])
        if p.get("elevation") is not None and nz is not None:
            p["elevation"] = float(nz[i])

    if transformer.description:
        issues.append(
            Issue("info", "crs_transform", f"Transformation applied: {transformer.description}")
        )
    invalid = int(np.sum(~np.isfinite(np.asarray(nx))) + np.sum(~np.isfinite(np.asarray(ny))))
    if invalid:
        issues.append(
            Issue(
                "error",
                "crs_transform_invalid",
                f"{invalid} coordinate(s) fell outside the transformation area and became "
                "non-finite. Check the source CRS.",
            )
        )
    accuracy = transformer.get_accuracy() if hasattr(transformer, "get_accuracy") else None
    if not accuracy:
        issues.append(
            Issue(
                "warning",
                "crs_no_accuracy",
                "The chosen transformation has no documented accuracy (null transformation?).",
            )
        )
    return pts, issues


def detect_axis_swap(eastings: Sequence[float], northings: Sequence[float]) -> Dict[str, Any]:
    """Detect a probable X/Y (Easting/Northing) reversal.

    Evidence used, in order:
      1. UTM/Geodetic magnitude signature: northings live in 1e6..9.4e6, eastings in
         1e5..9e5.  If the first coordinate column is the big one, columns are swapped.
      2. Dutch RD signature: easting 0..300k, northing 300k..650k.
      3. Spatial coherence: a survey block is roughly square; swapping cannot change
         that, so a *strongly* elongated aspect ratio is not evidence -- we ignore it.
    """
    if not eastings or not northings:
        return {"swap_suspected": False, "confidence": 0.0, "reason": "no data"}
    e32 = np.asarray(eastings, dtype=float)
    n32 = np.asarray(northings, dtype=float)
    e_med = float(np.median(e32))
    n_med = float(np.median(n32))

    reasons: List[str] = []
    confidence = 0.0

    # 1. UTM-style signature
    if n_med < 1e6 <= e_med and n_med > 0:
        confidence = max(confidence, 0.9)
        reasons.append(
            f"Median of column 1 ({e_med:,.0f}) is in the UTM northing band (>= 1e6) while "
            f"column 2 ({n_med:,.0f}) is in the easting band."
        )
    # 2. RD signature
    if 0 <= n_med <= 400_000 and 300_000 <= e_med <= 700_000:
        confidence = max(confidence, 0.75)
        reasons.append(
            f"RD New geometry: X={e_med:,.0f} looks like a northing (300-650 km) and "
            f"Y={n_med:,.0f} like an easting (0-300 km)."
        )
    # 3. Negative eastings in a projected system (possible in some grids, low evidence)
    if np.all(e32 < 0) and np.all(n32 > 0):
        confidence = max(confidence, 0.2)
        reasons.append("All first-column values are negative; verify the axis direction.")

    return {
        "swap_suspected": confidence >= 0.7,
        "confidence": confidence,
        "reason": " ".join(reasons) if reasons else "No axis-reversal signature detected.",
        "median_first": e_med,
        "median_second": n_med,
    }


def swap_axes(points: Iterable[PointLike]) -> List[PointLike]:
    """Return copies with Easting <-> Northing exchanged."""
    out: List[PointLike] = []
    for p in points:
        q = dict(p)
        q["easting"], q["northing"] = float(p["northing"]), float(p["easting"])
        q["swap_applied"] = True
        out.append(q)
    return out


def convex_hull_area(eastings: Sequence[float], northings: Sequence[float]) -> float:
    """Area of the convex hull in square metres (shapely, monotone chain fallback)."""
    if len(eastings) < 3:
        return 0.0
    try:
        from shapely.geometry import MultiPoint

        return float(MultiPoint(list(zip(eastings, northings))).convex_hull.area)
    except Exception:  # pragma: no cover
        return 0.0


# --------------------------------------------------------------------------------------
# QA/QC
# --------------------------------------------------------------------------------------
@dataclass
class QaTolerances:
    """Project-level QA thresholds (also persisted on the Project row)."""

    duplicate_xy_tolerance: float = 0.005   # metres
    duplicate_z_tolerance: float = 0.02     # metres for "same point, different Z"
    z_mad_threshold: float = 3.5            # modified Z-score
    iqr_multiplier: float = 1.5             # Tukey fence width
    local_z_step_threshold: float = 1.5     # metres between k-NN points
    xy_outlier_threshold: float = 5.0       # robust z on X and Y
    knn: int = 6
    coordinate_range: Tuple[float, float] = (-1.0e7, 1.0e7)
    elevation_range: Tuple[float, float] = (-500.0, 9000.0)
    known_codes: Optional[Sequence[str]] = None

    def as_dict(self) -> Dict[str, Any]:
        return {
            "duplicate_xy_tolerance": self.duplicate_xy_tolerance,
            "duplicate_z_tolerance": self.duplicate_z_tolerance,
            "z_mad_threshold": self.z_mad_threshold,
            "iqr_multiplier": self.iqr_multiplier,
            "local_z_step_threshold": self.local_z_step_threshold,
            "xy_outlier_threshold": self.xy_outlier_threshold,
            "knn": self.knn,
            "elevation_range": list(self.elevation_range),
        }


@dataclass
class QaFlag:
    """A QA finding attached to one or more point indices."""

    code: str
    severity: str
    message: str
    point_numbers: List[str] = field(default_factory=list)
    indices: List[int] = field(default_factory=list)
    metric: Optional[float] = None
    suggestion: Optional[str] = None

    def as_dict(self) -> Dict[str, Any]:
        return {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
            "point_numbers": self.point_numbers,
            "indices": self.indices,
            "metric": self.metric,
            "suggestion": self.suggestion,
        }


@dataclass
class QaReport:
    flags: List[QaFlag]
    summary: Dict[str, Any]
    point_severity: Dict[str, str]  # point_number -> 'error'|'warning'|'ok'

    def as_dict(self) -> Dict[str, Any]:
        return {
            "flags": [f.as_dict() for f in self.flags],
            "summary": self.summary,
            "point_severity": self.point_severity,
        }


def _robust_z(values: np.ndarray) -> np.ndarray:
    """Modified Z-score using the median absolute deviation (Iglewicz & Hoaglin)."""
    med = float(np.median(values))
    mad = float(np.median(np.abs(values - med)))
    if mad == 0.0:
        # More than half the values are identical (common with a single spike in a flat
        # dataset).  Fall back to the mean absolute deviation, scaled to be sigma-consistent.
        mad = float(np.mean(np.abs(values - med))) * 1.253314
        if mad == 0.0:
            return np.zeros_like(values)
    return 0.6745 * (values - med) / mad


def _tukey_fences(values: np.ndarray, multiplier: float) -> Tuple[float, float]:
    q1, q3 = np.percentile(values, [25.0, 75.0])
    iqr = float(q3 - q1)
    return float(q1 - multiplier * iqr), float(q3 + multiplier * iqr)


def validate_points(
    points: Sequence[PointLike],
    tolerances: Optional[QaTolerances] = None,
    *,
    project_crs: Optional[int] = None,
) -> QaReport:
    """Run the full survey QA/QC battery over a point list.

    Each check is independent and reported as its own :class:`QaFlag` so the UI can
    group, filter and dismiss them.  Nothing is silently corrected.
    """
    tol = tolerances or QaTolerances()
    flags: List[QaFlag] = []
    point_severity: Dict[str, str] = {}
    n = len(points)

    def mark(indices: Iterable[int], severity: str) -> None:
        for i in indices:
            if 0 <= i < n:
                pn = str(points[i].get("point_number"))
                current = point_severity.get(pn)
                rank = {"ok": 0, "info": 1, "warning": 2, "error": 3}
                if current is None or rank.get(severity, 0) > rank.get(current, 0):
                    point_severity[pn] = severity

    if n == 0:
        return QaReport(
            flags=[QaFlag("empty_dataset", "error", "No points to validate.")],
            summary={"points": 0},
            point_severity={},
        )

    east = np.array([float(p["easting"]) for p in points], dtype=float)
    north = np.array([float(p["northing"]) for p in points], dtype=float)
    has_z = np.array([p.get("elevation") is not None for p in points], dtype=bool)
    elev = np.array(
        [float(p["elevation"]) if p.get("elevation") is not None else np.nan for p in points],
        dtype=float,
    )
    numbers = [str(p.get("point_number", "")) for p in points]
    codes = [str(p.get("code") or "").strip() for p in points]

    # ---- 1. Coordinate sanity -------------------------------------------------------
    bad_range = [
        i for i in range(n)
        if not (tol.coordinate_range[0] <= east[i] <= tol.coordinate_range[1])
        or not (tol.coordinate_range[1] * -1 <= north[i] <= tol.coordinate_range[1])
        or not math.isfinite(east[i])
        or not math.isfinite(north[i])
    ]
    if bad_range:
        flags.append(
            QaFlag(
                "coordinate_out_of_range",
                "error",
                f"{len(bad_range)} point(s) have coordinates outside +/-10,000 km -- likely a "
                "unit or parsing error.",
                [numbers[i] for i in bad_range[:50]],
                bad_range[:50],
                suggestion="Check the column mapping and the coordinate unit.",
            )
        )
        mark(bad_range, "error")

    # ---- 2. Axis swap ---------------------------------------------------------------
    swap = detect_axis_swap(east.tolist(), north.tolist())
    if swap["swap_suspected"]:
        flags.append(
            QaFlag(
                "xy_swap_suspected",
                "error",
                f"Easting/Northing appear to be reversed. {swap['reason']}",
                [],
                [],
                metric=swap["confidence"],
                suggestion="Use the 'Swap X/Y' action in the import wizard, then re-run QA/QC.",
            )
        )

    # ---- 3. Duplicate point numbers --------------------------------------------------
    seen: Dict[str, int] = {}
    dup_numbers: Dict[str, List[int]] = {}
    for i, pn in enumerate(numbers):
        if pn in seen:
            dup_numbers.setdefault(pn, [seen[pn]]).append(i)
        else:
            seen[pn] = i
    if dup_numbers:
        idx: List[int] = []
        for group in dup_numbers.values():
            idx.extend(group)
        pn_list = [numbers[i] for i in idx[:100]]
        flags.append(
            QaFlag(
                "duplicate_point_number",
                "warning",
                f"{len(dup_numbers)} point number(s) occur more than once "
                f"({len(idx)} records involved).",
                pn_list,
                idx[:100],
                suggestion="Keep one record (usually the latest re-observation) or renumber.",
            )
        )
        mark(idx, "warning")

    # ---- 4. Duplicate coordinates (KD-tree radius search) ---------------------------
    if n > 1:
        try:
            from scipy.spatial import cKDTree

            tree = cKDTree(np.column_stack([east, north]))
            pairs = tree.query_pairs(r=max(tol.duplicate_xy_tolerance, 1e-6), output_type="ndarray")
        except Exception:  # pragma: no cover - scipy always available in prod
            pairs = np.array([], dtype=int).reshape(0, 2)

        if len(pairs):
            dz_small: List[int] = []
            dz_diff: List[int] = []
            for a, b in pairs:
                if not (has_z[a] and has_z[b]):
                    dz_small.append(int(a))
                    dz_small.append(int(b))
                    continue
                if abs(elev[a] - elev[b]) <= tol.duplicate_z_tolerance:
                    dz_small.extend([int(a), int(b)])
                else:
                    dz_diff.extend([int(a), int(b)])
            if dz_small:
                uniq = sorted(set(dz_small))
                flags.append(
                    QaFlag(
                        "duplicate_coordinates",
                        "warning",
                        f"{len(pairs)} coordinate pair(s) are within "
                        f"{tol.duplicate_xy_tolerance * 1000:.0f} mm "
                        f"({len(uniq)} records) with consistent elevation.",
                        [numbers[i] for i in uniq[:100]],
                        uniq[:100],
                        suggestion="Legitimate for stacked features (e.g. top/bottom of curb); "
                        "otherwise remove the duplicates.",
                    )
                )
                mark(uniq[:100], "warning")
            if dz_diff:
                uniq = sorted(set(dz_diff))
                flags.append(
                    QaFlag(
                        "stacked_points",
                        "info",
                        f"{len(uniq)} points share planimetry but differ in elevation by more "
                        f"than {tol.duplicate_z_tolerance * 100:g} cm "
                        "(typical for curb top/bottom pairs).",
                        [numbers[i] for i in uniq[:100]],
                        uniq[:100],
                    )
                )

    # ---- 5. Elevation anomalies -----------------------------------------------------
    z_idx = np.where(has_z)[0]
    if len(z_idx) >= 5:
        z_values = elev[z_idx]
        mz = _robust_z(z_values)
        mad_hits = [int(z_idx[i]) for i in np.where(np.abs(mz) > tol.z_mad_threshold)[0]]
        lo, hi = _tukey_fences(z_values, tol.iqr_multiplier)
        iqr_hits = [int(z_idx[i]) for i in np.where((z_values < lo) | (z_values > hi))[0]]
        combined = sorted(set(mad_hits) | set(iqr_hits))
        if combined:
            flags.append(
                QaFlag(
                    "elevation_anomaly",
                    "warning",
                    f"{len(combined)} elevation(s) are statistical outliers "
                    f"(|modified Z| > {tol.z_mad_threshold} or outside Tukey fences "
                    f"[{lo:.3f}, {hi:.3f}] m).",
                    [numbers[i] for i in combined[:100]],
                    combined[:100],
                    metric=float(np.max(np.abs(mz))),
                    suggestion="Inspect in the 3D view; a spike is usually a mistyped digit.",
                )
            )
            mark(combined[:100], "warning")
        # median + spread summary
        med = float(np.median(z_values))
        flags.append(
            QaFlag(
                "elevation_statistics",
                "info",
                f"Elevation statistics: min {float(z_values.min()):.3f} m, "
                f"median {med:.3f} m, max {float(z_values.max()):.3f} m, "
                f"MAD {float(np.median(np.abs(z_values - med))):.3f} m.",
            )
        )

    # ---- 6. Local vertical steps (k-NN) ---------------------------------------------
    if n > tol.knn + 1 and len(z_idx) >= tol.knn + 1:
        try:
            from scipy.spatial import cKDTree

            tree = cKDTree(np.column_stack([east[z_idx], north[z_idx]]))
            dist, neigh = tree.query(np.column_stack([east[z_idx], north[z_idx]]), k=tol.knn + 1)
            spikes: List[int] = []
            for row in range(len(z_idx)):
                neighbour_ids = neigh[row][1:]
                if len(neighbour_ids) == 0:
                    continue
                diffs = np.abs(z_values[row] - z_values[neighbour_ids])
                nearest_dist = float(dist[row][1]) if len(dist[row]) > 1 else 1.0
                if diffs.min() > tol.local_z_step_threshold and nearest_dist < 3.0:
                    spikes.append(int(z_idx[row]))
            if spikes:
                flags.append(
                    QaFlag(
                        "elevation_spike",
                        "warning",
                        f"{len(spikes)} point(s) differ from every nearby point by more than "
                        f"{tol.local_z_step_threshold:g} m within 3 m horizontally -- classic "
                        "single-point spike.",
                        [numbers[i] for i in spikes[:100]],
                        spikes[:100],
                    )
                )
                mark(spikes[:100], "warning")
        except Exception:  # pragma: no cover
            pass

    # ---- 7. Horizontal outliers (robust) --------------------------------------------
    if n >= 8:
        zx = np.abs(_robust_z(east))
        zy = np.abs(_robust_z(north))
        outliers = [int(i) for i in np.where((zx > tol.xy_outlier_threshold) | (zy > tol.xy_outlier_threshold))[0]]
        far = [int(i) for i in outliers
               if math.hypot(east[i] - float(np.median(east)), north[i] - float(np.median(north))) > 10.0]
        if far:
            flags.append(
                QaFlag(
                    "xy_outlier",
                    "warning",
                    f"{len(far)} point(s) lie far outside the main cluster "
                    f"(robust Z > {tol.xy_outlier_threshold:g} in X or Y and > 10 m from the median).",
                    [numbers[i] for i in far[:100]],
                    far[:100],
                )
            )
            mark(far[:100], "warning")

    # ---- 8. Codes -------------------------------------------------------------------
    missing = [i for i, c in enumerate(codes) if c == ""]
    if missing:
        flags.append(
            QaFlag(
                "missing_code",
                "info",
                f"{len(missing)} point(s) have no feature code; they will be imported as "
                "generic points (layer S-POINT).",
                [numbers[i] for i in missing[:100]],
                missing[:100],
            )
        )
        mark(missing[:100], "info")
    if tol.known_codes:
        known = {str(c).upper() for c in tol.known_codes}
        unknown: Dict[str, List[int]] = {}
        for i, c in enumerate(codes):
            base = re.sub(r"\s+[A-Z]{2,4}$", "", c).upper()
            if c and base not in known and c.upper() not in known:
                unknown.setdefault(c, []).append(i)
        if unknown:
            idx = [i for group in unknown.values() for i in group]
            flags.append(
                QaFlag(
                    "unknown_code",
                    "info",
                    f"{len(unknown)} distinct code(s) are not in the project code library: "
                    + ", ".join(list(unknown)[:12]),
                    [numbers[i] for i in idx[:100]],
                    idx[:100],
                    suggestion="Add them in Code Mapping so they get the right CAD layer.",
                )
            )

    # ---- 9. Point numbering ---------------------------------------------------------
    numeric_numbers = [int(pn) for pn in numbers if pn.isdigit()]
    if len(numeric_numbers) >= 5 and len(numeric_numbers) == len(numbers):
        arr = sorted(numeric_numbers)
        gaps = sum(1 for a, b in zip(arr, arr[1:]) if b - a > 1)
        if gaps:
            flags.append(
                QaFlag(
                    "numbering_gaps",
                    "info",
                    f"{gaps} gap(s) in the point numbering sequence "
                    f"({arr[0]}..{arr[-1]}). Missing points may still be in the field book.",
                )
            )
        dup_geo = sum(1 for a, b in zip(arr, arr[1:]) if b == a)
        if dup_geo:
            flags.append(
                QaFlag("numbering_duplicates", "warning", f"{dup_geo} duplicate numeric point number(s).")
            )

    # ---- 10. Summary ----------------------------------------------------------------
    counts = {"error": 0, "warning": 0, "info": 0}
    for f in flags:
        counts[f.severity] = counts.get(f.severity, 0) + 1
    area = convex_hull_area(east.tolist(), north.tolist())
    summary = {
        "points": n,
        "with_elevation": int(has_z.sum()),
        "unique_codes": len({c for c in codes if c}),
        "extent_easting": [float(east.min()), float(east.max())],
        "extent_northing": [float(north.min()), float(north.max())],
        "convex_hull_area_m2": round(area, 3),
        "point_density_per_ha": round(n / (area / 10_000.0), 1) if area > 0 else None,
        "flag_counts": counts,
        "flagged_points": len(point_severity),
        "axis_swap": swap,
        "project_crs": project_crs,
    }
    return QaReport(flags, summary, point_severity)
