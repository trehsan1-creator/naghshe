"""
SurveyPro -- Universal Surveying File Importer
==============================================

This module implements *real* parsers (no mocks, no hardcoded point tables) for the
two survey data families that account for the overwhelming majority of field data in
urban reconstruction workflows:

1. ``.txt`` / ``.csv`` / ``.asc`` / ``.dat`` plain ASCII exports from total stations,
   GNSS rovers, levelling software and hand-edited spreadsheets.  These files are
   notoriously messy: variable whitespace, semicolons, decimal commas, headers in
   Dutch / Arabic / English, thousands separators, mixed delimiters inside one file.

2. Leica ``.gsi`` files (GSI-8 and GSI-16) written by TS02plus / FlexLine instruments,
   including the raw polar observations (Hz, V, slope distance) which must be reduced
   to cartesian coordinates using station coordinates, instrument and reflector height.

Design notes
------------
* Every detection step returns its *evidence* (scores, statistics, notes) so the
  front-end wizard can explain to the surveyor **why** a mapping was suggested.
* Parsing never raises on a bad record: it records an :class:`Issue` and keeps going,
  exactly like a field book would.
* The Leica decoder follows the published *GSI ONLINE* word structure:

  =========  ==================================================================
  positions  meaning
  =========  ==================================================================
  1-2        word index (WI): 11 point id, 21 Hz, 22 V, 31 slope dist, ...
  3-6        information characters (unit code at pos. 4, flags at pos. 5-6)
  7          sign ``+`` / ``-``
  8-15       data, 8 characters  (GSI-8 word, 16 chars incl. trailing blank)
  8-23       data, 16 characters (GSI-16 word, 24 chars incl. trailing blank)
  =========  ==================================================================

  GSI-16 measurement blocks are prefixed with ``*``.

References: Leica *GSI ONLINE for TPS and DNA* (2003/2008 editions), word index
table WI 11/21/22/31/32/33/81/82/83/84/85/86/87/88/41/42-49/71.
"""

from __future__ import annotations

import csv
import io
import math
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

__all__ = [
    "Issue",
    "ColumnProfile",
    "ColumnMapping",
    "TextAnalysis",
    "ParsedPoint",
    "TextParseResult",
    "GsiWord",
    "GsiBlock",
    "GsiStation",
    "GsiObservation",
    "GsiParseResult",
    "GsiOptions",
    "decode_bytes",
    "detect_delimiter",
    "analyze_text_file",
    "parse_text_points",
    "parse_gsi",
    "reduce_observation",
    "gon_to_rad",
    "GON_TO_RAD",
]

GON_TO_RAD = math.pi / 200.0
DEG_TO_RAD = math.pi / 180.0

_FIELD_ORDER: Tuple[str, ...] = (
    "point_number",
    "easting",
    "northing",
    "elevation",
    "code",
    "description",
)

# Header synonyms -- Dutch, English, German, French, Arabic transliterations and
# the abbreviations surveyors actually type.  Matching is case/accents insensitive.
_HEADER_SYNONYMS: Dict[str, Tuple[str, ...]] = {
    "point_number": (
        "pt", "pnt", "point", "pointno", "point_no", "pointnumber", "ptno", "ptnr",
        "nr", "no", "num", "number", "id", "punt", "puntnr", "puntnummer", "station",
        "pn", "pointid", "name", "pname", "kode", "ptid", "stn",
    ),
    "easting": (
        "easting", "east", "e", "x", "xc", "xcoord", "x_coord", "coordx", "oost",
        "oosterlengte", "rw", "rechts", "rechtswaarde", "ost", "est", "gkx", "utm_e",
        "eastings", "x_m", "lng", "lon",
    ),
    "northing": (
        "northing", "north", "n", "y", "yc", "ycoord", "y_coord", "coordy", "noord",
        "noorderbreedte", "hw", "hoogtewaarde", "nord", "nord", "utm_n", "northings",
        "y_m", "lat",
    ),
    "elevation": (
        "elevation", "elev", "height", "h", "z", "zcoord", "z_coord", "hoogte",
        "elevatie", "niveau", "rz", "z_m", "alt", "altitude", "level", "maaiveld",
        "hohe", "hauteur", "z_wert",
    ),
    "code": (
        "code", "cod", "cd", "feature", "featurecode", "fc", "sym", "symbol",
        "beschrijving_code", "ptcode", "fieldcode", "kode", "type",
    ),
    "description": (
        "description", "desc", "remark", "remarks", "note", "notes", "omschrijving",
        "opmerking", "comment", "comments", "text", "label", "bemerkung",
    ),
}

_NUMERIC_RE = re.compile(r"^[+-]?(\d+(?:[.,]\d*)?|[.,]\d+)(?:[eE][+-]?\d+)?$")
_INT_RE = re.compile(r"^[+-]?\d{1,9}$")
_WHITESPACE_DELIMS = ("ws",)
_DELIM_CANDIDATES: Tuple[str, ...] = (",", ";", "\t", "|", "ws")
_DELIM_LABEL = {
    ",": "comma",
    ";": "semicolon",
    "\t": "tab",
    "|": "pipe",
    "ws": "whitespace",
}

_MAX_ISSUES_PER_KIND = 40


# --------------------------------------------------------------------------------------
# Result containers
# --------------------------------------------------------------------------------------
@dataclass
class Issue:
    """A single QA/QC or parsing finding."""

    severity: str  # 'info' | 'warning' | 'error'
    code: str
    message: str
    line_no: Optional[int] = None
    column: Optional[str] = None
    value: Optional[str] = None

    def as_dict(self) -> Dict[str, Any]:
        return {
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
            "line_no": self.line_no,
            "column": self.column,
            "value": self.value,
        }


@dataclass
class ParsedPoint:
    point_number: str
    easting: float
    northing: float
    elevation: Optional[float]
    code: str = ""
    description: str = ""
    line_no: int = 0
    order: int = 0

    def as_dict(self) -> Dict[str, Any]:
        return {
            "point_number": self.point_number,
            "easting": self.easting,
            "northing": self.northing,
            "elevation": self.elevation,
            "code": self.code,
            "description": self.description,
            "line_no": self.line_no,
        }


@dataclass
class ColumnProfile:
    """Statistical fingerprint of one column, used to suggest a mapping."""

    index: int
    header: Optional[str]
    sample: List[str]
    numeric_ratio: float
    integer_ratio: float
    distinct_ratio: float
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    mean_value: Optional[float] = None
    mean_decimals: float = 0.0
    mean_length: float = 0.0
    alpha_ratio: float = 0.0
    uppercase_ratio: float = 0.0
    max_token_length: int = 0
    sequential_ratio: float = 0.0

    @property
    def span(self) -> float:
        if self.min_value is None or self.max_value is None:
            return 0.0
        return self.max_value - self.min_value

    def as_dict(self) -> Dict[str, Any]:
        return {
            "index": self.index,
            "header": self.header,
            "sample": self.sample[:8],
            "numeric_ratio": round(self.numeric_ratio, 3),
            "integer_ratio": round(self.integer_ratio, 3),
            "distinct_ratio": round(self.distinct_ratio, 3),
            "min": self.min_value,
            "max": self.max_value,
            "mean": None if self.mean_value is None else round(self.mean_value, 3),
            "mean_decimals": round(self.mean_decimals, 2),
            "alpha_ratio": round(self.alpha_ratio, 3),
            "max_token_length": self.max_token_length,
            "sequential_ratio": round(self.sequential_ratio, 3),
        }


@dataclass
class ColumnMapping:
    """Which token index feeds which survey attribute (``None`` = not present)."""

    point_number: Optional[int] = None
    easting: Optional[int] = None
    northing: Optional[int] = None
    elevation: Optional[int] = None
    code: Optional[int] = None
    description: Optional[int] = None
    has_header: bool = False
    delimiter: str = "ws"

    def as_dict(self) -> Dict[str, Any]:
        return {
            "point_number": self.point_number,
            "easting": self.easting,
            "northing": self.northing,
            "elevation": self.elevation,
            "code": self.code,
            "description": self.description,
            "has_header": self.has_header,
            "delimiter": self.delimiter,
        }

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> Optional["ColumnMapping"]:
        if not data:
            return None

        def _idx(key: str) -> Optional[int]:
            value = data.get(key)
            if value is None or value == "" or value == -1:
                return None
            return int(value)

        return cls(
            point_number=_idx("point_number"),
            easting=_idx("easting"),
            northing=_idx("northing"),
            elevation=_idx("elevation"),
            code=_idx("code"),
            description=_idx("description"),
            has_header=bool(data.get("has_header", False)),
            delimiter=str(data.get("delimiter") or "ws"),
        )

    def validate(self) -> List[Issue]:
        issues: List[Issue] = []
        if self.easting is None or self.northing is None:
            issues.append(
                Issue(
                    "error",
                    "mapping_missing_planar",
                    "A column mapping needs both an Easting (X) and a Northing (Y) column.",
                )
            )
        if self.easting is not None and self.easting == self.northing:
            issues.append(
                Issue("error", "mapping_duplicate_column", "Easting and Northing map to the same column.")
            )
        return issues


@dataclass
class TextAnalysis:
    encoding: str
    encoding_notes: List[str]
    delimiter: str
    delimiter_scores: Dict[str, float]
    header_detected: bool
    header_tokens: List[str]
    row_count: int
    token_count_mode: int
    columns: List[ColumnProfile]
    mapping: ColumnMapping
    confidence: Dict[str, float]
    rows_preview: List[List[str]]
    issues: List[Issue] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "encoding": self.encoding,
            "encoding_notes": self.encoding_notes,
            "delimiter": self.delimiter,
            "delimiter_label": _DELIM_LABEL.get(self.delimiter, self.delimiter),
            "delimiter_scores": {k: round(v, 3) for k, v in self.delimiter_scores.items()},
            "header_detected": self.header_detected,
            "header_tokens": self.header_tokens,
            "row_count": self.row_count,
            "token_count_mode": self.token_count_mode,
            "columns": [c.as_dict() for c in self.columns],
            "mapping": self.mapping.as_dict(),
            "confidence": {k: round(v, 3) for k, v in self.confidence.items()},
            "rows_preview": self.rows_preview,
            "issues": [i.as_dict() for i in self.issues],
        }


@dataclass
class TextParseResult:
    points: List[ParsedPoint]
    issues: List[Issue]
    stats: Dict[str, Any]
    mapping: ColumnMapping

    def as_dict(self, limit: Optional[int] = None) -> Dict[str, Any]:
        pts = self.points if limit is None else self.points[:limit]
        return {
            "points": [p.as_dict() for p in pts],
            "issues": [i.as_dict() for i in self.issues],
            "stats": self.stats,
            "mapping": self.mapping.as_dict(),
        }


# --------------------------------------------------------------------------------------
# Encoding / delimiter / tokenising
# --------------------------------------------------------------------------------------
def decode_bytes(raw: bytes) -> Tuple[str, str, List[str]]:
    """Decode survey bytes with a deterministic, evidence-based strategy.

    Survey instruments emit UTF-8 (modern), UTF-16LE/BE (some Leica exports),
    Windows-1252 (Dutch fields) and Windows-1256 (Arabic speaking regions).
    We try in order of strictness and keep the first loss-less decode that does not
    contain replacement characters.
    """
    notes: List[str] = []
    if raw.startswith(b"\xff\xfe"):
        return _strip_bom(raw.decode("utf-16", errors="replace")), "utf-16-le", ["UTF-16 little endian BOM detected"]
    if raw.startswith(b"\xfe\xff"):
        return _strip_bom(raw.decode("utf-16", errors="replace")), "utf-16-be", ["UTF-16 big endian BOM detected"]
    if raw.startswith(b"\xef\xbb\xbf"):
        return raw.decode("utf-8-sig", errors="replace"), "utf-8-sig", ["UTF-8 BOM detected"]

    # Heuristic: UTF-16 without BOM -- ASCII text encoded as UTF-16 has ~50 % NUL bytes.
    if len(raw) >= 4:
        nul_ratio = raw[:4096].count(0) / max(1, len(raw[:4096]))
        if nul_ratio > 0.3:
            sample = raw[:4096]
            even_nuls = sum(1 for i in range(0, len(sample) - 1, 2) if sample[i] == 0)
            odd_nuls = sum(1 for i in range(1, len(sample), 2) if sample[i] == 0)
            enc = "utf-16-le" if even_nuls > odd_nuls else "utf-16-be"
            notes.append(f"UTF-16 without BOM assumed ({enc}); NUL byte ratio {nul_ratio:.2f}")
            return _strip_bom(raw.decode(enc, errors="replace")), enc, notes

    # Single-byte encodings all "succeed" on arbitrary bytes, so the winner is chosen by
    # a plausibility score rather than by the first codec that does not raise.
    best: Tuple[float, str, str] | None = None
    for enc in ("utf-8", "cp1252", "cp1256", "latin-1"):
        try:
            text = raw.decode(enc)
        except UnicodeDecodeError:
            continue
        score = _text_plausibility(text, preferred=(enc == "utf-8"))
        if best is None or score > best[0]:
            best = (score, enc, text)
    if best is not None:
        _, enc, text = best
        if enc != "utf-8":
            notes.append(f"File is not valid UTF-8; decoded as {enc} (best character-set fit).")
        return _strip_bom(text), enc, notes

    notes.append("Fell back to UTF-8 with replacement characters; some labels may be unreadable.")
    return _strip_bom(raw.decode("utf-8", errors="replace")), "utf-8", notes


# Characters that only appear when a single-byte encoding is misinterpreted (they are the
# cp1252 renderings of Arabic/Hebrew/Greek bytes, or of UTF-8 multi-byte sequences).
_RARE_LATIN = set(
    "ÞþÑñÃãÕõÐðÝý¸¹º¼½¾«»¦§¨©ª¬­®¯´µ·¿¡²³¤¥¢£¦"
)
_ARABIC_RANGE = (0x0600, 0x06FF)


def _text_plausibility(text: str, preferred: bool = False) -> float:
    """Heuristic score of how plausible a decoding looks (higher is better)."""
    if not text:
        return 0.0
    sample = text[:20_000]
    total = len(sample)
    rare = sum(1 for ch in sample if ch in _RARE_LATIN)
    arabic = sum(1 for ch in sample if _ARABIC_RANGE[0] <= ord(ch) <= _ARABIC_RANGE[1])
    control = sum(1 for ch in sample if ord(ch) < 0x20 and ch not in "\n\r\t")
    replacement = sample.count("\ufffd")
    score = 1.0
    score -= 3.0 * (rare / total)
    score -= 5.0 * (control / total)
    score -= 10.0 * (replacement / total)
    score += 0.35 * (arabic / total)
    if preferred:
        score += 0.25
    return score


def _strip_bom(text: str) -> str:
    return text[1:] if text[:1] == "\ufeff" else text


def _looks_mojibake(text: str) -> bool:
    """Detect classic UTF-8-read-as-cp1252 garbage such as ``Ã«``."""
    markers = ("Ã©", "Ã¨", "Ã«", "Ã¯", "Ã¶", "Ã¼", "Ã¡", "â€™", "Â°")
    return any(m in text for m in markers)


def _split_line(line: str, delimiter: str) -> List[str]:
    """Split one physical line into tokens.

    Handles quoted CSV fields, a stray opposite delimiter, and the common
    "comma file with a few semicolon lines" pathology.
    """
    stripped = line.rstrip("\r\n")
    if not stripped.strip():
        return []
    if delimiter in _WHITESPACE_DELIMS:
        return stripped.split()

    try:
        row = next(csv.reader([stripped], delimiter=delimiter, skipinitialspace=True))
    except csv.Error:
        row = stripped.split(delimiter)

    if len(row) <= 1 and delimiter not in stripped:
        # Mixed delimiter file: fall back to a generic split on any run of separators.
        alt = [t for t in re.split(r"\s*[,;|\t]\s*|\s{1,}(?=[^\s])", stripped) if t != ""]
        if len(alt) > 1:
            return alt
    return [c.strip().strip('"').strip("'") for c in row]


def detect_delimiter(lines: Sequence[str]) -> Tuple[str, Dict[str, float]]:
    """Score candidate delimiters by *consistency of token count*, not frequency.

    A comma inside a decimal number therefore loses against semicolons that split
    every row into the same number of fields.
    """
    sample = [ln for ln in lines if ln.strip()][:200]
    scores: Dict[str, float] = {}
    if not sample:
        return "ws", {d: 0.0 for d in _DELIM_CANDIDATES}

    for delim in _DELIM_CANDIDATES:
        # A delimiter that is absent from the sample cannot be the delimiter, even if the
        # generic fallback in _split_line would happily split the line for us.
        if delim not in _WHITESPACE_DELIMS:
            appears = sum(1 for ln in sample if delim in ln) / len(sample)
            if appears < 0.6:
                scores[delim] = 0.0
                continue
        counts: List[int] = []
        for ln in sample:
            if delim in _WHITESPACE_DELIMS:
                counts.append(len(ln.split()))
            else:
                counts.append(len(_split_line(ln, delim)))
        mode, mode_freq = _mode(counts)
        if mode <= 1:
            scores[delim] = 0.0
            continue
        consistency = mode_freq / len(counts)
        # Reward field counts that look like a survey record (3..8 columns).
        shape_bonus = 1.0 if 3 <= mode <= 8 else 0.82
        scores[delim] = consistency * shape_bonus * min(mode, 6) / 6.0

    # A file such as "1;105.420,500;471.880,250" is delimiter-consistent for BOTH ';' and
    # ','.  Decimal commas are the giveaway: if commas are almost always followed by 1-3
    # digits they are decimal separators, so the semicolon must be the field separator.
    if scores.get(",") and scores.get(";") and abs(scores[","] - scores[";"]) < 0.35:
        decimal_commas = sum(len(re.findall(r"\d,\d{1,3}(?!\d)", ln)) for ln in sample)
        if decimal_commas >= len(sample):
            scores[";"] = max(scores[";"], scores[","]) + 0.05

    best = max(scores, key=lambda d: (scores[d], _delim_priority(d)))
    return best, scores


def _delim_priority(delim: str) -> int:
    return {",": 4, ";": 3, "\t": 2, "|": 1, "ws": 0}.get(delim, 0)


def _mode(values: Sequence[int]) -> Tuple[int, int]:
    if not values:
        return 0, 0
    counts: Dict[int, int] = {}
    for v in values:
        counts[v] = counts.get(v, 0) + 1
    best = max(counts.items(), key=lambda kv: (kv[1], kv[0]))
    return best[0], best[1]


_FLOAT_RE = re.compile(r"[+-]?(\d+(\.\d*)?|\.\d+)([eE][+-]?\d+)?$")


def _to_float(token: str) -> Optional[float]:
    """Parse a numeric token the way survey exports actually write numbers.

    Handles: ``-1.234``, ``1,5`` (decimal comma), ``105.420,500`` (European thousands +
    decimal comma), ``105,420.500`` (Anglo), thin/non-breaking spaces and the usual
    ``N/A`` / ``-`` placeholders.  A single comma with three trailing digits is read as a
    decimal separator (survey coordinates rarely use a thousands separator), which is the
    safe choice for elevation and coordinate columns.
    """
    if token is None:
        return None
    t = str(token).strip().replace("\u00a0", "").replace("\u202f", "").replace(" ", "")
    if not t:
        return None
    if t.upper() in {"-", ".", ",", "N/A", "NA", "NAN", "NULL", "NONE", "?", "--"}:
        return None
    t = t.replace("'", "")

    # thousands / decimal separators
    if "," in t and "." in t:
        if t.rfind(",") > t.rfind("."):
            t = t.replace(".", "").replace(",", ".")   # 105.420,500 -> 105420.500
        else:
            t = t.replace(",", "")                     # 105,420.500 -> 105420.500
    elif "," in t:
        if t.count(",") > 1:
            t = t.replace(",", "") if all(len(part) == 3 for part in t.split(",")[1:]) else t.replace(",", ".")
        else:
            t = t.replace(",", ".")
    if not _FLOAT_RE.match(t):
        return None
    try:
        value = float(t)
    except ValueError:
        return None
    if math.isnan(value) or math.isinf(value):
        return None
    return value


# --------------------------------------------------------------------------------------
# Column profiling and mapping inference
# --------------------------------------------------------------------------------------
def _normalise_header(token: str) -> str:
    token = unicodedata.normalize("NFKD", token or "")
    token = "".join(c for c in token if not unicodedata.combining(c))
    token = token.strip().strip("""'"()[]""").lower()
    token = re.sub(r"[^a-z0-9]+", "_", token).strip("_")
    return token


def _header_field(token: str) -> Optional[str]:
    key = _normalise_header(token)
    if not key:
        return None
    for field_name, synonyms in _HEADER_SYNONYMS.items():
        if key in synonyms:
            return field_name
    # substring fallback ('pt_code', 'elev_m', 'y_coord[m]')
    for field_name, synonyms in _HEADER_SYNONYMS.items():
        for syn in synonyms:
            if len(syn) >= 2 and (key.startswith(syn + "_") or key.endswith("_" + syn) or key == syn):
                return field_name
    return None


def _profile_column(index: int, header: Optional[str], values: Sequence[str]) -> ColumnProfile:
    numeric = [v for v in values if _to_float(v) is not None]
    numbers = [n for n in (_to_float(v) for v in values) if n is not None]
    non_empty = [v for v in values if str(v).strip() != ""]
    decimals: List[int] = []
    for v in numeric:
        t = str(v).strip().replace(",", ".")
        if "." in t:
            decimals.append(len(t.split(".")[-1]))
    # A point-number column is very often 1,2,3,...: measure how arithmetic it is.
    diffs = [b - a for a, b in zip(numbers, numbers[1:])]
    sequential = (sum(1 for d in diffs if d == 1.0) / len(diffs)) if diffs else 0.0
    alpha_tokens = [v for v in non_empty if any(ch.isalpha() for ch in v)]
    upper = [v for v in alpha_tokens if v.isupper()]
    return ColumnProfile(
        index=index,
        header=header,
        sample=list(non_empty[:8]),
        numeric_ratio=len(numeric) / max(1, len(values)),
        integer_ratio=len([v for v in values if _INT_RE.match(str(v).strip())]) / max(1, len(values)),
        distinct_ratio=len(set(non_empty)) / max(1, len(non_empty)),
        min_value=min(numbers) if numbers else None,
        max_value=max(numbers) if numbers else None,
        mean_value=(sum(numbers) / len(numbers)) if numbers else None,
        mean_decimals=(sum(decimals) / len(decimals)) if decimals else 0.0,
        mean_length=(sum(len(v) for v in non_empty) / len(non_empty)) if non_empty else 0.0,
        alpha_ratio=len(alpha_tokens) / max(1, len(values)),
        uppercase_ratio=len(upper) / max(1, len(alpha_tokens)) if alpha_tokens else 0.0,
        max_token_length=max((len(v) for v in non_empty), default=0),
        sequential_ratio=sequential,
    )


def _suggest_mapping(
    columns: Sequence[ColumnProfile], headers: Sequence[str], has_header: bool
) -> Tuple[ColumnMapping, Dict[str, float], List[Issue]]:
    """Infer which column holds which survey attribute, with confidence scores."""
    issues: List[Issue] = []
    confidence: Dict[str, float] = {k: 0.0 for k in _FIELD_ORDER}
    mapping = ColumnMapping(has_header=has_header)
    taken: Dict[str, int] = {}

    # --- 1. Headers win when present -------------------------------------------------
    if has_header:
        for col in columns:
            field_name = _header_field(col.header or "")
            if field_name and field_name not in taken:
                taken[field_name] = col.index
                confidence[field_name] = 0.95

    # --- 2. Point number first: it is the column that identifies every row ----------
    #  (coordinates are then chosen from what is left, which removes the classic failure
    #   mode where an incrementing point column is mistaken for an easting.)
    if "point_number" not in taken:
        candidates = [
            c
            for c in columns
            if (c.integer_ratio >= 0.7 or c.numeric_ratio >= 0.7) and c.max_token_length <= 12
        ]

        def pt_score(c: ColumnProfile) -> float:
            score = 0.0
            score += 2.0 * c.sequential_ratio
            score += 1.2 * c.distinct_ratio
            score += 0.5 * c.integer_ratio
            if c.index == 0:
                score += 0.6
            if c.mean_decimals >= 1.0:
                score -= 1.0           # coordinates / elevations almost always carry decimals
            if c.mean_value is not None and abs(c.mean_value) > 1e5:
                score -= 2.0           # a 6-7 digit magnitude is a coordinate, not a point id
            return score

        if candidates:
            best = max(candidates, key=pt_score)
            score = pt_score(best)
            plausible = score >= 1.6 and (
                best.sequential_ratio > 0.5
                or best.mean_value is None
                or abs(best.mean_value) < 1e5
            )
            if plausible:
                mapping.point_number = best.index
                confidence["point_number"] = round(min(0.92, max(0.4, score / 4.0)), 3)
                taken["point_number"] = best.index
    else:
        mapping.point_number = taken["point_number"]

    # --- 3. Planar coordinates: the two remaining columns with the largest span -------
    numeric_cols = [c for c in columns if c.numeric_ratio >= 0.85 and c.span > 0]
    assigned = set(taken.values())
    planar_pool = [c for c in numeric_cols if c.index not in assigned]
    planar_pool.sort(key=lambda c: c.span, reverse=True)

    east = taken.get("easting")
    north = taken.get("northing")

    if east is None and north is None and len(planar_pool) >= 2:
        a, b = planar_pool[0], planar_pool[1]
        east, north = _decide_xy(a, b, issues)
        confidence["easting"] = 0.8
        confidence["northing"] = 0.8
    elif east is not None and north is None:
        cand = _best_remaining(planar_pool, {east})
        north = cand.index if cand else None
        confidence["northing"] = 0.7
    elif north is not None and east is None:
        cand = _best_remaining(planar_pool, {north})
        east = cand.index if cand else None
        confidence["easting"] = 0.7

    if east is not None:
        mapping.easting = east
        confidence["easting"] = max(confidence.get("easting", 0.0), 0.8)
    if north is not None:
        mapping.northing = north
        confidence["northing"] = max(confidence.get("northing", 0.0), 0.8)

    # --- 4. Elevation: smallest-span numeric column inside a plausible range ----------
    if "elevation" not in taken:
        pool = [
            c
            for c in numeric_cols
            if c.index not in {mapping.easting, mapping.northing, mapping.point_number}
        ]
        def z_score(c: ColumnProfile) -> float:
            if c.min_value is None or c.max_value is None:
                return -1e9
            score = 0.0
            if -500.0 <= c.min_value and c.max_value <= 9000.0:
                score += 1.0
            score += 1.0 / (1.0 + abs(c.mean_decimals - 3.0))  # Z usually has 2-3 decimals
            score -= 2.5 * (c.span / 1e6)  # planar coordinates span tens of km
            if c.integer_ratio > 0.98 and c.span < 1e5:
                score -= 0.4  # pure integers are usually point numbers
            return score

        if pool:
            best = max(pool, key=z_score)
            if z_score(best) > 0.2:
                mapping.elevation = best.index
                confidence["elevation"] = round(min(0.9, 0.45 + 0.35 * z_score(best)), 3)
    else:
        mapping.elevation = taken["elevation"]
        confidence["elevation"] = max(confidence["elevation"], 0.9)

    # --- 5. Code / description: the textual columns ----------------------------------
    text_cols = [
        c
        for c in columns
        if c.alpha_ratio >= 0.25 and c.index not in {mapping.easting, mapping.northing, mapping.elevation}
    ]
    used = {mapping.easting, mapping.northing, mapping.elevation, mapping.point_number}

    if "code" in taken:
        mapping.code = taken["code"]
    else:
        code_pool = [c for c in text_cols if c.max_token_length <= 12 and c.index not in used]
        if code_pool:
            best = min(code_pool, key=lambda c: (c.mean_length, c.index))
            mapping.code = best.index
            confidence["code"] = 0.7 if best.uppercase_ratio > 0.5 else 0.55

    if "description" in taken:
        mapping.description = taken["description"]
    else:
        desc_pool = [
            c for c in text_cols
            if c.index not in used and c.index != mapping.code and c.mean_length > 4
        ]
        if desc_pool:
            best = max(desc_pool, key=lambda c: c.mean_length)
            mapping.description = best.index
            confidence["description"] = 0.6

    if mapping.easting is not None and mapping.northing is not None:
        for name, idx in (("easting", mapping.easting), ("northing", mapping.northing)):
            col = columns[idx] if idx < len(columns) else None
            if col and col.numeric_ratio < 0.85:
                issues.append(
                    Issue(
                        "warning",
                        "low_numeric_ratio",
                        f"Column {idx + 1} suggested for {name} is only "
                        f"{col.numeric_ratio:.0%} numeric; check the mapping.",
                        column=name,
                    )
                )
    else:
        issues.append(
            Issue(
                "error",
                "planar_columns_not_found",
                "Could not identify Easting/Northing columns automatically. Choose them manually.",
            )
        )
    return mapping, confidence, issues


def _decide_xy(a: ColumnProfile, b: ColumnProfile, issues: List[Issue]) -> Tuple[int, int]:
    """Decide which of two numeric columns is Easting (X) and which is Northing (Y).

    Strategy (urban Netherlands / UTM reality):
      * RD / UTM northings are 400k-6.5M, eastings 0-800k.
      * If one column clearly stays under 1e6 and the other exceeds it, the larger
        one is the Northing.
      * Otherwise fall back to column order: the classic convention in survey exports
        is P,N,E,Z (northing before easting).  We flag the ambiguity so the wizard can
        ask the surveyor.
    """
    if a.max_value is None or b.max_value is None:
        return a.index, b.index

    a_big = abs(a.max_value) > 1e6 or abs(a.min_value or 0) > 1e6
    b_big = abs(b.max_value) > 1e6 or abs(b.min_value or 0) > 1e6

    if a_big and not b_big:
        return b.index, a.index  # (easting, northing)
    if b_big and not a_big:
        return a.index, b.index

    # Both in the same magnitude class.  In every projected grid in practical use the
    # northing carries the larger offset (UTM false-northing, RD's 300-650 km band,
    # Dutch/German local grids), so the *larger* median is the northing.
    a_mid = a.mean_value if a.mean_value is not None else 0.0
    b_mid = b.mean_value if b.mean_value is not None else 0.0
    scale = max(abs(a_mid), abs(b_mid), 1.0)
    if abs(abs(a_mid) - abs(b_mid)) / scale > 0.05 and max(abs(a_mid), abs(b_mid)) > 10_000:
        if abs(a_mid) > abs(b_mid):
            issues.append(
                Issue(
                    "info",
                    "xy_order_from_magnitude",
                    f"Easting/Northing inferred from magnitude: column {a.index + 1} is larger "
                    f"(mean {a_mid:,.0f} vs {b_mid:,.0f}) and is treated as Northing.",
                )
            )
            return b.index, a.index
        issues.append(
            Issue(
                "info",
                "xy_order_from_magnitude",
                f"Easting/Northing inferred from magnitude: column {b.index + 1} is larger "
                f"(mean {b_mid:,.0f} vs {a_mid:,.0f}) and is treated as Northing.",
            )
        )
        return a.index, b.index

    # Truly ambiguous. Prefer P,N,E ordering (northing first).
    issues.append(
        Issue(
            "warning",
            "xy_order_ambiguous",
            "Easting and Northing have the same magnitude range; assumed P,N,E ordering "
            f"(column {a.index + 1} = Northing, column {b.index + 1} = Easting). "
            "Verify the frame preview.",
        )
    )
    return b.index, a.index


def _best_remaining(pool: Sequence[ColumnProfile], exclude: Iterable[int]) -> Optional[ColumnProfile]:
    excluded = set(exclude)
    for col in pool:
        if col.index not in excluded:
            return col
    return None


# --------------------------------------------------------------------------------------
# Text analysis (drives the import wizard)
# --------------------------------------------------------------------------------------
def analyze_text_file(
    text: str,
    encoding: str = "utf-8",
    encoding_notes: Optional[List[str]] = None,
    max_preview_rows: int = 60,
) -> TextAnalysis:
    """Profile a delimited survey file and propose a column mapping."""
    lines = text.splitlines()
    data_lines = [ln for ln in lines if ln.strip()]
    delimiter, scores = detect_delimiter(data_lines)
    split_rows = [_split_line(ln, delimiter) for ln in data_lines]
    split_rows = [r for r in split_rows if r]

    header_detected = False
    header_tokens: List[str] = []
    if split_rows:
        first = split_rows[0]
        numeric = sum(1 for t in first if _to_float(t) is not None)
        alpha = sum(1 for t in first if any(c.isalpha() for c in t))
        if alpha >= 2 and numeric / max(1, len(first)) < 0.5:
            header_detected = True
            header_tokens = first
            split_rows = split_rows[1:]

    mode_count, _ = _mode([len(r) for r in split_rows])
    width = max([len(r) for r in split_rows], default=0)
    if mode_count and width > mode_count:
        width = mode_count  # ignore trailing junk on a handful of rows

    columns: List[ColumnProfile] = []
    for idx in range(width):
        values = [r[idx] if idx < len(r) else "" for r in split_rows]
        header = header_tokens[idx] if idx < len(header_tokens) else None
        columns.append(_profile_column(idx, header, values))

    mapping, confidence, issues = _suggest_mapping(columns, header_tokens, header_detected)
    mapping.delimiter = delimiter

    # Ragged-row diagnostics
    ragged = sum(1 for r in split_rows if len(r) != mode_count)
    if ragged:
        issues.append(
            Issue(
                "warning",
                "ragged_rows",
                f"{ragged} row(s) do not have the modal {mode_count} fields; "
                "they will be reported individually during import.",
            )
        )
    return TextAnalysis(
        encoding=encoding,
        encoding_notes=encoding_notes or [],
        delimiter=delimiter,
        delimiter_scores=scores,
        header_detected=header_detected,
        header_tokens=header_tokens,
        row_count=len(split_rows),
        token_count_mode=mode_count,
        columns=columns,
        mapping=mapping,
        confidence=confidence,
        rows_preview=[r[:width] for r in split_rows[:max_preview_rows]],
        issues=issues,
    )


# --------------------------------------------------------------------------------------
# Point parsing
# --------------------------------------------------------------------------------------
def parse_text_points(
    text: str,
    mapping: Optional[ColumnMapping] = None,
    delimiter: Optional[str] = None,
    has_header: Optional[bool] = None,
    *,
    elevation_required: bool = False,
) -> TextParseResult:
    """Parse a delimited survey file into points using an explicit (or inferred) mapping."""
    if mapping is None:
        analysis = analyze_text_file(text)
        mapping = analysis.mapping
        delimiter = analysis.delimiter
        has_header = analysis.header_detected
    delim = delimiter or mapping.delimiter or "ws"
    header = mapping.has_header if has_header is None else has_header

    issues: List[Issue] = []
    for issue in mapping.validate():
        issues.append(issue)
    if mapping.easting is None or mapping.northing is None:
        return TextParseResult([], issues, {"rows": 0, "parsed": 0, "skipped": 0}, mapping)

    points: List[ParsedPoint] = []
    total = 0
    skipped = 0
    first_data_line = True
    seen_numbers: Dict[str, int] = {}
    duplicate_issues = 0

    for line_no, raw_line in enumerate(text.splitlines(), start=1):
        if not raw_line.strip() or raw_line.lstrip().startswith(("#", "//", ";")):
            continue
        tokens = _split_line(raw_line, delim)
        if not tokens:
            continue
        if header and first_data_line:
            numeric = sum(1 for t in tokens if _to_float(t) is not None)
            if numeric / max(1, len(tokens)) < 0.5:
                first_data_line = False
                continue
        first_data_line = False
        total += 1

        def token(idx: Optional[int]) -> str:
            if idx is None or idx >= len(tokens):
                return ""
            return tokens[idx]

        east = _to_float(token(mapping.easting))
        north = _to_float(token(mapping.northing))
        elev = _to_float(token(mapping.elevation)) if mapping.elevation is not None else None

        if east is None or north is None:
            skipped += 1
            if skipped <= _MAX_ISSUES_PER_KIND:
                issues.append(
                    Issue(
                        "warning",
                        "row_unparseable",
                        f"Row skipped: Easting/Northing not numeric ('{token(mapping.easting)}', "
                        f"'{token(mapping.northing)}').",
                        line_no=line_no,
                        value=raw_line.strip()[:160],
                    )
                )
            continue

        if elevation_required and elev is None:
            skipped += 1
            if skipped <= _MAX_ISSUES_PER_KIND:
                issues.append(
                    Issue(
                        "warning",
                        "row_missing_elevation",
                        "Row skipped: elevation is required but missing.",
                        line_no=line_no,
                        value=raw_line.strip()[:160],
                    )
                )
            continue

        pt_number = token(mapping.point_number).strip()
        if not pt_number:
            pt_number = f"L{line_no}"
            if len([i for i in issues if i.code == "point_number_generated"]) < 5:
                issues.append(
                    Issue(
                        "info",
                        "point_number_generated",
                        f"No point number on line {line_no}; generated '{pt_number}'.",
                        line_no=line_no,
                    )
                )

        point = ParsedPoint(
            point_number=pt_number,
            easting=east,
            northing=north,
            elevation=elev,
            code=token(mapping.code).strip(),
            description=token(mapping.description).strip(),
            line_no=line_no,
            order=len(points),
        )
        if pt_number in seen_numbers:
            duplicate_issues += 1
            if duplicate_issues <= _MAX_ISSUES_PER_KIND:
                issues.append(
                    Issue(
                        "warning",
                        "duplicate_point_number",
                        f"Point number '{pt_number}' repeated (first seen line "
                        f"{seen_numbers[pt_number]}).",
                        line_no=line_no,
                        column="point_number",
                        value=pt_number,
                    )
                )
        else:
            seen_numbers[pt_number] = line_no
        points.append(point)

    zs = [p.elevation for p in points if p.elevation is not None]
    stats: Dict[str, Any] = {
        "rows": total,
        "parsed": len(points),
        "skipped": skipped,
        "unique_point_numbers": len(seen_numbers),
        "duplicate_point_numbers": duplicate_issues,
        "with_elevation": len(zs),
        "easting_range": _range_of([p.easting for p in points]),
        "northing_range": _range_of([p.northing for p in points]),
        "elevation_range": _range_of(zs),
    }
    return TextParseResult(points, issues, stats, mapping)


def _range_of(values: Sequence[float]) -> Optional[List[float]]:
    if not values:
        return None
    return [min(values), max(values)]


# --------------------------------------------------------------------------------------
# Leica GSI (GSI-8 / GSI-16)
# --------------------------------------------------------------------------------------
_GSI_WI_NAMES = {
    "11": "point_number",
    "12": "instrument_serial",
    "13": "instrument_type",
    "18": "time_1",
    "19": "time_2",
    "21": "hz",
    "22": "v",
    "25": "hz_difference",
    "31": "slope_distance",
    "32": "horizontal_distance",
    "33": "height_difference",
    "41": "code",
    "42": "info1",
    "43": "info2",
    "44": "info3",
    "45": "info4",
    "46": "info5",
    "47": "info6",
    "48": "info7",
    "49": "info8",
    "71": "description",
    "81": "target_easting",
    "82": "target_northing",
    "83": "target_elevation",
    "84": "station_easting",
    "85": "station_northing",
    "86": "station_elevation",
    "87": "reflector_height",
    "88": "instrument_height",
    "89": "decimals_definition",
}

# GSI unit code found at position 6 of the information field -> scale divisor.
# '.'/'0' = metres with last place 1 mm; '6' = 0.1 mm; '8' = 0.01 mm (per GSI ONLINE).
_GSI_DISTANCE_SCALE = {
    "0": 1e3,
    ".": 1e3,
    "1": 1e3,   # feet, 0.001 ft (handled via unit override)
    "2": 1e3,
    "3": 1e3,
    "4": 1e3,
    "5": 1e3,
    "6": 1e4,
    "7": 1e5,
    "8": 1e5,
    "9": 1e3,
}
_GSI_FEET_CODES = {"1", "7"}


@dataclass
class GsiOptions:
    """Decoding options for ambiguous parts of the GSI standard."""

    angle_unit: str = "gon"            # 'gon' | 'deg' | 'mil' | 'dms'
    distance_unit: str = "auto"        # 'auto' | 'm' | 'ft'
    vertical_angle_mode: str = "auto"  # 'auto' | 'zenith' | 'vertical'
    auto_orient: bool = True           # derive station orientation from the backsight
    default_orientation_gon: float = 0.0
    strict: bool = False               # raise on structural errors instead of collecting them


@dataclass
class GsiWord:
    wi: str
    info: str
    sign: str
    raw: str
    start: int
    position: int = 0

    @property
    def name(self) -> str:
        return _GSI_WI_NAMES.get(self.wi, f"wi_{self.wi}")

    @property
    def value(self) -> Optional[float]:
        digits = self.raw.strip()
        if not digits:
            return None
        body = digits.lstrip("+-")
        if body.isdigit():
            value = float(int(body))
        else:
            try:
                value = float(body)
            except ValueError:
                return None
        return -value if self.sign == "-" else value

    @property
    def text(self) -> str:
        return self.raw.strip()

    @property
    def unit_code(self) -> str:
        """The unit / decimal descriptor at position 6 of the word."""
        return self.info[3] if len(self.info) >= 4 else "."


@dataclass
class GsiBlock:
    line_no: int
    is_gsi16: bool
    words: List[GsiWord]

    def by_wi(self) -> Dict[str, GsiWord]:
        out: Dict[str, GsiWord] = {}
        for w in self.words:
            out.setdefault(w.wi, w)
        return out


@dataclass
class GsiStation:
    point_number: str
    easting: Optional[float] = None
    northing: Optional[float] = None
    elevation: Optional[float] = None
    instrument_height: float = 0.0
    orientation_rad: Optional[float] = None
    line_no: int = 0


@dataclass
class GsiObservation:
    point_number: str
    line_no: int
    hz_rad: Optional[float] = None
    v_rad: Optional[float] = None
    slope_distance: Optional[float] = None
    horizontal_distance: Optional[float] = None
    height_difference: Optional[float] = None
    reflector_height: Optional[float] = None
    code: str = ""
    description: str = ""
    station: Optional[str] = None
    # Computed by the reduction step
    computed_easting: Optional[float] = None
    computed_northing: Optional[float] = None
    computed_elevation: Optional[float] = None
    recorded_easting: Optional[float] = None
    recorded_northing: Optional[float] = None
    recorded_elevation: Optional[float] = None


@dataclass
class GsiParseResult:
    blocks: List[GsiBlock]
    stations: List[GsiStation]
    observations: List[GsiObservation]
    points: List[ParsedPoint]
    issues: List[Issue]
    stats: Dict[str, Any]

    def as_dict(self, limit: Optional[int] = None) -> Dict[str, Any]:
        pts = self.points if limit is None else self.points[:limit]
        return {
            "points": [p.as_dict() for p in pts],
            "stations": [
                {
                    "point_number": s.point_number,
                    "easting": s.easting,
                    "northing": s.northing,
                    "elevation": s.elevation,
                    "instrument_height": s.instrument_height,
                    "orientation_rad": s.orientation_rad,
                    "line_no": s.line_no,
                }
                for s in self.stations
            ],
            "observations": [
                {
                    "point_number": o.point_number,
                    "line_no": o.line_no,
                    "hz_rad": o.hz_rad,
                    "v_rad": o.v_rad,
                    "slope_distance": o.slope_distance,
                    "reflector_height": o.reflector_height,
                    "code": o.code,
                    "station": o.station,
                }
                for o in (self.observations if limit is None else self.observations[:limit])
            ],
            "issues": [i.as_dict() for i in self.issues],
            "stats": self.stats,
        }


def _gsi_point_id(raw: str) -> str:
    """Normalise a GSI point identifier: ``00000010`` -> ``10``, ``0000A113`` kept as is."""
    text = (raw or "").strip()
    if text.isdigit():
        return str(int(text))
    return text


def _parse_gsi_line(line: str, line_no: int) -> Tuple[GsiBlock, List[Issue]]:
    """Tokenise one GSI line into words, tolerating GSI-8 / GSI-16 / mixed files."""
    issues: List[Issue] = []
    body = line.rstrip("\r\n")
    is_gsi16 = body.startswith("*")
    if is_gsi16:
        body = body[1:]
    words: List[GsiWord] = []
    pos = 0
    n = len(body)
    while pos < n:
        while pos < n and body[pos] in " \t":
            pos += 1
        if pos >= n:
            break
        if body[pos] == "*":
            is_gsi16 = True
            pos += 1
            continue
        if pos + 7 > n or not body[pos : pos + 2].isdigit():
            issues.append(
                Issue(
                    "warning",
                    "gsi_unexpected_character",
                    f"Unexpected characters in GSI block at column {pos + 1}; block partially parsed.",
                    line_no=line_no,
                    value=body[pos : pos + 24],
                )
            )
            break
        wi = body[pos : pos + 2]
        info = body[pos + 2 : pos + 6]
        sign = body[pos + 6]
        data_start = pos + 7
        if sign not in "+-":
            issues.append(
                Issue(
                    "warning",
                    "gsi_missing_sign",
                    f"Missing +/- sign in word {wi} at column {pos + 7}; assuming '+'.",
                    line_no=line_no,
                    value=body[pos : pos + 16],
                )
            )
            info = body[pos + 2 : pos + 6]
            sign = "+"
            data_start = pos + 6

        end: Optional[int] = None
        for length in ((16, 8) if is_gsi16 else (8, 16)):
            cand = data_start + length
            if cand >= n or body[cand] in " \t":
                end = min(cand, n)
                break
        if end is None:
            # No blank separator: scan for the next plausible word start.
            end = n
            for j in range(data_start + 1, n - 7):
                if body[j : j + 2].isdigit() and body[j + 6] in "+-" and body[j - 1] not in "0123456789":
                    end = j
                    break
        raw = body[data_start:end]
        words.append(GsiWord(wi=wi, info=info, sign=sign, raw=raw, start=pos, position=len(words)))
        pos = end
    return GsiBlock(line_no=line_no, is_gsi16=is_gsi16, words=words), issues


def _decode_gsi_distance(word: GsiWord, opts: GsiOptions) -> Tuple[Optional[float], List[Issue]]:
    issues: List[Issue] = []
    value = word.value
    if value is None:
        return None, issues
    code = word.unit_code
    scale = _GSI_DISTANCE_SCALE.get(code, 1e3)
    result = value / scale
    if opts.distance_unit == "ft" or (opts.distance_unit == "auto" and code in _GSI_FEET_CODES):
        result *= 0.3048
        if opts.distance_unit == "auto":
            issues.append(
                Issue(
                    "info",
                    "gsi_feet",
                    f"Word {word.wi} uses a feet unit code ('{code}'); converted to metres.",
                )
            )
    return result, issues


def _decode_gsi_angle(
    word: GsiWord, opts: GsiOptions
) -> Tuple[Optional[float], List[Issue]]:
    """Decode an angular GSI word to radians.

    GSI stores angles as scaled integers.  For a TS02 in the factory setting
    (gon, 4 decimals) ``21.324+001234500`` means 123.4500 gon.  When a file uses a
    different resolution (GSI-16 allows 5-6 decimals) we resolve the scale by
    plausibility: the value must land inside one full circle.
    """
    issues: List[Issue] = []
    value = word.value
    if value is None:
        return None, issues
    if opts.angle_unit == "dms":
        rad = _dms_packed_to_rad(value)
        return rad, issues

    limit = {"gon": 400.0, "deg": 360.0, "mil": 6400.0}.get(opts.angle_unit, 400.0)
    chosen: Optional[float] = None
    for decimals in (4, 5, 6, 3, 2, 1, 0):
        cand = value / (10.0 ** decimals)
        if 0.0 <= cand < limit:
            chosen = cand
            break
    if chosen is None:
        issues.append(
            Issue(
                "warning",
                "gsi_angle_out_of_range",
                f"Angle value {value:g} in word {word.wi} does not fit a full circle; ignored.",
                value=word.raw,
            )
        )
        return None, issues
    if opts.angle_unit == "gon":
        return chosen * GON_TO_RAD, issues
    if opts.angle_unit == "deg":
        return chosen * DEG_TO_RAD, issues
    return chosen * (2.0 * math.pi / 6400.0), issues


def _dms_packed_to_rad(value: float) -> float:
    """Convert packed DDMMSSssss integers (e.g. 5212345678 = 52°12'34.5678") to radians."""
    v = abs(value)
    seconds_full = v / 10000.0
    deg = int(seconds_full // 10000)
    minutes = int((seconds_full - deg * 10000) // 100)
    seconds = seconds_full - deg * 10000 - minutes * 100
    rad = (deg + minutes / 60.0 + seconds / 3600.0) * DEG_TO_RAD
    return -rad if value < 0 else rad


def gon_to_rad(gon: float) -> float:
    return gon * GON_TO_RAD


def reduce_observation(
    station: GsiStation,
    obs: GsiObservation,
    *,
    vertical_angle_mode: str = "zenith",
    orientation_rad: float = 0.0,
) -> Tuple[Optional[Tuple[float, float, float]], List[Issue]]:
    """Reduce one polar observation to a cartesian coordinate (trigonometry, not a table).

    .. math::

        d_h = s \\sin z \\quad \\Delta h = s \\cos z

        E = E_0 + d_h \\sin(H_z + o) \\quad N = N_0 + d_h \\cos(H_z + o)

        Z = Z_0 + i_H + \\Delta h - t_H

    ``z`` is the zenith angle; when the instrument is configured to output a
    *vertical* angle (0° = horizon) it is converted with ``z = 90° - v``.
    """
    issues: List[Issue] = []
    if station.easting is None or station.northing is None:
        issues.append(
            Issue(
                "error",
                "gsi_station_unknown",
                f"Cannot reduce point {obs.point_number}: station "
                f"{station.point_number} has no coordinates.",
                line_no=obs.line_no,
            )
        )
        return None, issues
    if obs.hz_rad is None or obs.slope_distance is None:
        issues.append(
            Issue(
                "warning",
                "gsi_observation_incomplete",
                f"Point {obs.point_number} has no Hz/slope distance; coordinate not reduced.",
                line_no=obs.line_no,
            )
        )
        return None, issues

    zenith = _zenith_angle(obs.v_rad, vertical_angle_mode)
    s = obs.slope_distance
    d_h = s * math.sin(zenith)
    dz = s * math.cos(zenith)
    azimuth = obs.hz_rad + orientation_rad
    east = station.easting + d_h * math.sin(azimuth)
    north = station.northing + d_h * math.cos(azimuth)
    elev = 0.0
    if station.elevation is not None:
        elev = (
            station.elevation
            + station.instrument_height
            + dz
            - (obs.reflector_height or 0.0)
        )
    else:
        issues.append(
            Issue(
                "warning",
                "gsi_station_height_unknown",
                f"Station {station.point_number} has no elevation; point "
                f"{obs.point_number} reduced in planimetry only.",
                line_no=obs.line_no,
            )
        )
    return (east, north, elev), issues


def _zenith_angle(v_rad: Optional[float], mode: str) -> float:
    if v_rad is None:
        return math.pi / 2.0
    if mode == "zenith":
        return v_rad
    if mode == "vertical":
        return math.pi / 2.0 - v_rad
    # auto: Leica zenith angles cluster around 90 gon, vertical angles around 0.
    return v_rad if abs(v_rad) > math.pi / 4.0 else math.pi / 2.0 - v_rad


def parse_gsi(text: str, options: Optional[GsiOptions] = None) -> GsiParseResult:
    """Parse a Leica GSI-8 / GSI-16 file into stations, observations and coordinates."""
    opts = options or GsiOptions()
    issues: List[Issue] = []
    blocks: List[GsiBlock] = []
    stations: List[GsiStation] = []
    observations: List[GsiObservation] = []
    points: List[ParsedPoint] = []

    gsi16_blocks = 0
    gsi8_blocks = 0

    current_station: Optional[GsiStation] = None
    pending_station: Optional[GsiStation] = None
    pending_reflector: Optional[float] = None
    pending_code = ""
    pending_desc = ""
    last_point_number: Optional[str] = None
    v_values: List[float] = []

    for line_no, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        block, block_issues = _parse_gsi_line(line, line_no)
        issues.extend(block_issues)
        if not block.words:
            continue
        blocks.append(block)
        if block.is_gsi16:
            gsi16_blocks += 1
        else:
            gsi8_blocks += 1

        wi = block.by_wi()

        # ---- contextual words that apply to *following* measurement blocks --------
        if "87" in wi:
            rh, _ = _decode_gsi_distance(wi["87"], opts)
            pending_reflector = rh
        if "41" in wi:
            pending_code = wi["41"].text
        if "71" in wi:
            pending_desc = wi["71"].text

        # ---- station setup block (84/85/86) --------------------------------------
        if any(k in wi for k in ("84", "85", "86", "88")):
            station = GsiStation(
                point_number=_gsi_point_id(wi["11"].text) if "11" in wi else (last_point_number or "STN"),
                line_no=line_no,
            )
            if "84" in wi:
                station.easting = _decode_gsi_distance(wi["84"], opts)[0]
            if "85" in wi:
                station.northing = _decode_gsi_distance(wi["85"], opts)[0]
            if "86" in wi:
                station.elevation = _decode_gsi_distance(wi["86"], opts)[0]
            if "88" in wi:
                station.instrument_height = _decode_gsi_distance(wi["88"], opts)[0] or 0.0
            current_station = station
            stations.append(station)
            if "21" in wi and "31" in wi:
                # Backsight block: 11 + 21 + 31 with station coordinates present.
                hz_rad, angle_issues = _decode_gsi_angle(wi["21"], opts)
                issues.extend(angle_issues)
                slope = _decode_gsi_distance(wi["31"], opts)[0]
                if hz_rad is not None and slope is not None and "22" in wi:
                    v_rad, a_issues = _decode_gsi_angle(wi["22"], opts)
                    issues.extend(a_issues)
                    v_values.append(v_rad if v_rad is not None else math.pi / 2)
                    bs = GsiObservation(
                        point_number=station.point_number,
                        line_no=line_no,
                        hz_rad=hz_rad,
                        v_rad=v_rad,
                        slope_distance=slope,
                        reflector_height=pending_reflector,
                        code=pending_code or "BS",
                        station=station.point_number,
                    )
                    observations.append(bs)
                    pending_station = station
            continue

        # ---- measurement block ----------------------------------------------------
        if "11" in wi and any(k in wi for k in ("21", "22", "31", "32", "33", "81")):
            pt_number = _gsi_point_id(wi["11"].text)
            last_point_number = pt_number
            obs = GsiObservation(
                point_number=pt_number,
                line_no=line_no,
                code=pending_code,
                description=pending_desc,
                reflector_height=pending_reflector,
                station=current_station.point_number if current_station else None,
            )
            if "21" in wi:
                obs.hz_rad, a_issues = _decode_gsi_angle(wi["21"], opts)
                issues.extend(a_issues)
            if "22" in wi:
                obs.v_rad, a_issues = _decode_gsi_angle(wi["22"], opts)
                issues.extend(a_issues)
                if obs.v_rad is not None:
                    v_values.append(obs.v_rad)
            if "31" in wi:
                obs.slope_distance = _decode_gsi_distance(wi["31"], opts)[0]
            if "32" in wi:
                obs.horizontal_distance = _decode_gsi_distance(wi["32"], opts)[0]
            if "33" in wi:
                obs.height_difference = _decode_gsi_distance(wi["33"], opts)[0]
            if "81" in wi:
                obs.recorded_easting = _decode_gsi_distance(wi["81"], opts)[0]
            if "82" in wi:
                obs.recorded_northing = _decode_gsi_distance(wi["82"], opts)[0]
            if "83" in wi:
                obs.recorded_elevation = _decode_gsi_distance(wi["83"], opts)[0]
            observations.append(obs)
            pending_code = ""
            pending_desc = ""
            continue

        # ---- standalone coordinate block (11/81/82/83) ----------------------------
        if "11" in wi and "81" in wi and "82" in wi:
            east = _decode_gsi_distance(wi["81"], opts)[0]
            north = _decode_gsi_distance(wi["82"], opts)[0]
            elev = _decode_gsi_distance(wi["83"], opts)[0] if "83" in wi else None
            if east is not None and north is not None:
                points.append(
                    ParsedPoint(
                        point_number=_gsi_point_id(wi["11"].text),
                        easting=east,
                        northing=north,
                        elevation=elev,
                        code=pending_code,
                        description=pending_desc,
                        line_no=line_no,
                        order=len(points),
                    )
                )
            pending_code = ""
            pending_desc = ""

    # ---- resolve vertical-angle convention from the whole file ----------------
    v_mode = opts.vertical_angle_mode
    if v_mode == "auto":
        if v_values:
            median_v = sorted(v_values)[len(v_values) // 2]
            v_mode = "zenith" if abs(median_v) > math.pi / 4.0 else "vertical"
        else:
            v_mode = "zenith"
        if v_values:
            issues.append(
                Issue(
                    "info",
                    "gsi_vertical_mode",
                    f"Vertical angle convention detected as '{v_mode}' "
                    f"(median V = {sorted(v_values)[len(v_values) // 2] * 200.0 / math.pi:.3f} gon).",
                )
            )

    # ---- station orientation from the backsight (if resolvable) ----------------
    orientation_by_station: Dict[str, float] = {}
    if opts.auto_orient:
        for obs in observations:
            if obs.code != "BS" or obs.hz_rad is None or obs.slope_distance is None:
                continue
            station = next((s for s in stations if s.point_number == obs.station), None)
            if station is None or station.easting is None or station.northing is None:
                continue
            bs_point = next(
                (p for p in points if p.point_number == obs.point_number), None
            )
            if bs_point is None:
                # reduce the backsight itself, then use the true azimuth
                reduced, _ = reduce_observation(station, obs, vertical_angle_mode=v_mode)
                if reduced is None:
                    continue
                bx, by = reduced[0], reduced[1]
            else:
                bx, by = bs_point.easting, bs_point.northing
            true_az = math.atan2(bx - station.easting, by - station.northing) % (2 * math.pi)
            orientation = (true_az - obs.hz_rad) % (2 * math.pi)
            orientation_by_station[station.point_number] = orientation
            station.orientation_rad = orientation
            issues.append(
                Issue(
                    "info",
                    "gsi_orientation",
                    f"Station {station.point_number}: orientation solved from backsight "
                    f"= {orientation * 200.0 / math.pi:.4f} gon.",
                )
            )

    # ---- reduce every observation to coordinates ------------------------------
    computed = 0
    for obs in observations:
        if obs.code == "BS":
            continue
        station = next((s for s in reversed(stations) if s.point_number == obs.station), None)
        if station is None and stations:
            station = stations[-1]
        if station is None:
            issues.append(
                Issue(
                    "error",
                    "gsi_station_unknown",
                    f"Point {obs.point_number} is observed without an instrument setup "
                    "(no WI 84/85/86 block); the coordinate cannot be reduced.",
                    line_no=obs.line_no,
                )
            )
            continue
        orientation = orientation_by_station.get(
            station.point_number, gon_to_rad(opts.default_orientation_gon)
        )
        reduced, red_issues = reduce_observation(
            station, obs, vertical_angle_mode=v_mode, orientation_rad=orientation
        )
        issues.extend(red_issues)
        if reduced is None:
            continue
        east, north, elev = reduced
        obs.computed_easting, obs.computed_northing, obs.computed_elevation = east, north, elev
        if obs.recorded_easting is not None and obs.recorded_northing is not None:
            # Instrument already stored coordinates: prefer them (they include the
            # station orientation and any refraction/temperature correction).
            east = obs.recorded_easting
            north = obs.recorded_northing
            if obs.recorded_elevation is not None:
                elev = obs.recorded_elevation
            delta = math.hypot(east - obs.computed_easting, north - obs.computed_northing)
            if delta > 0.02:
                issues.append(
                    Issue(
                        "info",
                        "gsi_reduction_mismatch",
                        f"Point {obs.point_number}: recorded coordinate differs from our polar "
                        f"reduction by {delta * 1000:.0f} mm (orientation/scale differences).",
                        line_no=obs.line_no,
                    )
                )
        points.append(
            ParsedPoint(
                point_number=obs.point_number,
                easting=east,
                northing=north,
                elevation=elev,
                code=obs.code,
                description=obs.description,
                line_no=obs.line_no,
                order=len(points),
            )
        )
        computed += 1

    # ---- station coordinates themselves are points too --------------------------
    existing = {p.point_number for p in points}
    for st in stations:
        if st.easting is None or st.northing is None:
            continue
        if st.point_number in existing:
            continue
        points.append(
            ParsedPoint(
                point_number=st.point_number,
                easting=st.easting,
                northing=st.northing,
                elevation=st.elevation,
                code="STN",
                description=f"Station setup (iH={st.instrument_height:.3f} m)",
                line_no=st.line_no,
                order=len(points),
            )
        )
        existing.add(st.point_number)

    if not observations and not points:
        issues.append(
            Issue(
                "error",
                "gsi_no_records",
                "No GSI records recognised. The file may use a different word length or be "
                "an ASCII export rather than a GSI file.",
            )
        )
    if gsi16_blocks and gsi8_blocks:
        issues.append(
            Issue(
                "info",
                "gsi_mixed_formats",
                f"File mixes GSI-16 ({gsi16_blocks} blocks) and GSI-8 ({gsi8_blocks} blocks).",
            )
        )

    zs = [p.elevation for p in points if p.elevation is not None]
    stats: Dict[str, Any] = {
        "blocks": len(blocks),
        "gsi8_blocks": gsi8_blocks,
        "gsi16_blocks": gsi16_blocks,
        "stations": len(stations),
        "observations": len(observations),
        "reduced_points": computed,
        "parsed": len(points),
        "vertical_angle_mode": v_mode,
        "orientation_solved": len(orientation_by_station),
        "easting_range": _range_of([p.easting for p in points]),
        "northing_range": _range_of([p.northing for p in points]),
        "elevation_range": _range_of(zs),
    }
    return GsiParseResult(blocks, stations, observations, points, issues, stats)


# --------------------------------------------------------------------------------------
# Format sniffing
# --------------------------------------------------------------------------------------
def sniff_format(filename: str, text: str) -> str:
    """Return 'gsi' | 'dxf' | 'landxml' | 'csv' | 'txt' based on *content*, not just suffix."""
    lower = (filename or "").lower()
    head = text[:4000]
    if head.lstrip().startswith("0\nSECTION") or "\nAcDbEntity" in head or "SECTION" in head[:200] and "HEADER" in head[:400]:
        return "dxf"
    if "<LandXML" in head or "landxml" in head[:400].lower():
        return "landxml"
    gsi_like = sum(
        1 for ln in head.splitlines()[:200] if re.match(r"^\*?\d{2}[.\d]{4}[+\-]", ln.strip())
    )
    if gsi_like >= 1 or lower.endswith(".gsi"):
        return "gsi"
    if lower.endswith(".csv"):
        return "csv"
    return "txt"
