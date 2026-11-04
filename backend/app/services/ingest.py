"""Import pipeline: raw file -> analysis -> preview -> committed points.

The three tiers of the data model are enforced here:

* ``RAW``   -- the uploaded bytes are written once, content addressed, never edited.
* ``PROCESSED`` -- parsed points land as ``SurveyPoint`` rows with status ``RAW`` or
  ``VALIDATED`` and are never overwritten by a later import (each import is a new
  version).
* ``FINAL`` -- status ``APPROVED``; only these feed approved surfaces and deliverables.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..engines import coordinate_engine as coord
from ..engines import txt_gsi_parser as parser
from ..engines.linework_engine import lookup_definition, parse_code_string
from ..models import PointStatus, ProjectFile, Project, RawObservation, SurveyPoint, SurveyStation
from .projects import mark_derived_outdated

__all__ = [
    "UploadResult",
    "analyse_stored_file",
    "commit_file",
    "store_upload",
    "parse_stored_file",
    "detect_format",
]

TEXT_FORMATS = {"txt", "csv", "asc", "dat", "xyz", "pnezd"}
SUPPORTED_EXTENSIONS = TEXT_FORMATS | {"gsi", "dxf", "xml", "landxml"}


@dataclass
class UploadResult:
    file: ProjectFile
    analysis: Optional[Dict[str, Any]]


# --------------------------------------------------------------------------------------
# Storage
# --------------------------------------------------------------------------------------
def detect_format(filename: str, text: str) -> str:
    fmt = parser.sniff_format(filename, text)
    if fmt == "landxml":
        return "xml"
    if fmt in ("gsi", "dxf"):
        return fmt
    return "csv" if filename.lower().endswith(".csv") else "txt"


def _safe_name(filename: str) -> str:
    base = Path(filename).name
    return re.sub(r"[^A-Za-z0-9._-]+", "_", base)[:120] or "upload.txt"


async def store_upload(
    session: AsyncSession,
    project: Project,
    filename: str,
    content: bytes,
) -> UploadResult:
    """Persist the raw bytes (immutable) and analyse them for the import wizard."""
    if len(content) == 0:
        raise ValueError("The uploaded file is empty.")
    if len(content) > settings.max_upload_bytes:
        raise ValueError(
            f"File is larger than the {settings.max_upload_bytes / 1_048_576:.0f} MB limit."
        )
    digest = hashlib.sha256(content).hexdigest()
    safe = _safe_name(filename)

    text, encoding, encoding_notes = parser.decode_bytes(content)
    file_format = detect_format(safe, text)
    if file_format not in ("txt", "csv", "gsi", "dxf", "xml"):
        raise ValueError(f"Unsupported file format detected for '{filename}'.")
    if file_format in ("dxf", "xml"):
        raise ValueError(
            f"'{filename}' looks like {file_format.upper()}; that importer ships in the next "
            "delivery. This build accepts .txt/.csv/.gsi surveying files."
        )

    project_dir = Path(settings.upload_dir) / project.id
    project_dir.mkdir(parents=True, exist_ok=True)
    stored_name = f"{digest[:16]}_{safe}"
    storage_path = project_dir / stored_name
    if not storage_path.exists():          # content addressed: never overwrite
        storage_path.write_bytes(content)

    existing = await session.execute(
        select(ProjectFile).where(ProjectFile.project_id == project.id, ProjectFile.sha256 == digest)
    )
    duplicate = existing.scalars().first()

    import_log: Dict[str, Any] = {
        "encoding_notes": encoding_notes,
        "detected_format": file_format,
        "size_bytes": len(content),
        "digest": digest,
    }
    analysis: Optional[Dict[str, Any]] = None

    if file_format in ("txt", "csv"):
        analysed = parser.analyze_text_file(text, encoding, encoding_notes)
        analysis = analysed.as_dict()
        analysis["format"] = file_format
        # The wizard's first screen already shows parsed points and the QA/QC verdict,
        # computed with the *suggested* mapping so the surveyor sees real numbers at once.
        initial = parser.parse_text_points(
            text, analysed.mapping, analysed.delimiter, analysed.header_detected
        )
        preview_points = [p.as_dict() for p in initial.points]
        analysis["points"] = preview_points[:500]
        analysis["preview_truncated"] = len(preview_points) > 500
        analysis["stats"] = initial.stats
        analysis["parse_issues"] = [i.as_dict() for i in initial.issues][:200]
        analysis["qa"] = _qa_payload(project, preview_points)
        import_log.update(
            {
                "encoding": analysed.encoding,
                "delimiter": analysed.delimiter,
                "rows": analysed.row_count,
                "columns": len(analysed.columns),
                "header_detected": analysed.header_detected,
                "suggested_mapping": analysed.mapping.as_dict(),
            }
        )
    else:  # GSI
        gsi = parser.parse_gsi(
            text, parser.GsiOptions(angle_unit=project.angle_unit or "gon")
        )
        analysis = gsi.as_dict(limit=200)
        analysis["format"] = "gsi"
        gsi_points = [p.as_dict() for p in gsi.points]
        analysis["qa"] = _qa_payload(project, gsi_points)
        import_log.update(
            {
                "encoding": encoding,
                "blocks": gsi.stats["blocks"],
                "stations": gsi.stats["stations"],
                "observations": gsi.stats["observations"],
                "reduced_points": gsi.stats["reduced_points"],
                "vertical_angle_mode": gsi.stats["vertical_angle_mode"],
            }
        )

    record = ProjectFile(
        project_id=project.id,
        original_filename=filename,
        stored_filename=stored_name,
        storage_path=str(storage_path),
        sha256=digest,
        size_bytes=len(content),
        file_format=file_format,
        encoding=encoding,
        delimiter=analysis.get("delimiter") if analysis else None,
        status="analysed",
        row_count=int((analysis or {}).get("row_count") or (analysis or {}).get("stats", {}).get("blocks", 0) or 0),
        imported_points=0,
        import_log=import_log,
        notes=("Duplicate upload: identical content already exists in this project."
               if duplicate else None),
    )
    session.add(record)
    await session.flush()
    return UploadResult(file=record, analysis=analysis)


def _read_file_text(record: ProjectFile) -> Tuple[str, str, List[str]]:
    raw = Path(record.storage_path).read_bytes()
    return parser.decode_bytes(raw)


# --------------------------------------------------------------------------------------
# Analysis / preview
# --------------------------------------------------------------------------------------
async def analyse_stored_file(
    session: AsyncSession,
    project: Project,
    record: ProjectFile,
    *,
    mapping: Optional[Dict[str, Any]] = None,
    delimiter: Optional[str] = None,
    has_header: Optional[bool] = None,
    swap_xy: bool = False,
    preview_only: bool = True,
) -> Dict[str, Any]:
    """Re-analyse a stored file with an explicit (wizard supplied) mapping."""
    text, encoding, notes = _read_file_text(record)

    if record.file_format == "gsi":
        gsi = parser.parse_gsi(
            text,
            parser.GsiOptions(angle_unit=project.angle_unit or "gon"),
        )
        payload = gsi.as_dict(limit=None)
        payload["format"] = "gsi"
        payload["encoding"] = encoding
        payload["encoding_notes"] = notes
        points = [p.as_dict() for p in gsi.points]
        if swap_xy:
            points = coord.swap_axes(points)
            payload["points"] = points
        payload["qa"] = _qa_payload(project, points)
        return payload

    analysed = parser.analyze_text_file(text, encoding, notes)
    column_mapping = parser.ColumnMapping.from_dict(mapping) if mapping else analysed.mapping
    if mapping is None:
        column_mapping.delimiter = analysed.delimiter
    parsed = parser.parse_text_points(
        text,
        column_mapping,
        delimiter or column_mapping.delimiter or analysed.delimiter,
        analysed.header_detected if has_header is None else has_header,
    )
    points = [p.as_dict() for p in parsed.points]
    if swap_xy:
        points = coord.swap_axes(points)

    payload = {
        "format": record.file_format,
        "encoding": encoding,
        "encoding_notes": notes,
        "delimiter": column_mapping.delimiter,
        "header_detected": analysed.header_detected,
        "header_tokens": analysed.header_tokens,
        "columns": [c.as_dict() for c in analysed.columns],
        "suggested_mapping": analysed.mapping.as_dict(),
        "confidence": analysed.confidence,
        "analysis_issues": [i.as_dict() for i in analysed.issues],
        "mapping": column_mapping.as_dict(),
        "rows_preview": analysed.rows_preview,
        "row_count": analysed.row_count,
        "points": points[:500] if preview_only else points,
        "preview_truncated": preview_only and len(points) > 500,
        "parse_issues": [i.as_dict() for i in parsed.issues][:200],
        "stats": parsed.stats,
        "qa": _qa_payload(project, points),
    }
    return payload


def _qa_payload(project: Project, points: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    tolerances = coord.QaTolerances(
        duplicate_xy_tolerance=project.duplicate_xy_tolerance,
        duplicate_z_tolerance=project.duplicate_z_tolerance,
        z_mad_threshold=project.z_mad_threshold,
        local_z_step_threshold=project.local_z_step_threshold,
        known_codes=[c.code for c in (project.code_mappings or []) if c.enabled],
    )
    report = coord.validate_points(list(points), tolerances, project_crs=project.crs_epsg)
    return report.as_dict()


# --------------------------------------------------------------------------------------
# Commit
# --------------------------------------------------------------------------------------
async def parse_stored_file(
    project: Project,
    record: ProjectFile,
    *,
    mapping: Optional[Dict[str, Any]] = None,
    delimiter: Optional[str] = None,
    has_header: Optional[bool] = None,
    swap_xy: bool = False,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], Optional[parser.GsiParseResult], List[parser.Issue]]:
    """Parse a stored raw file into plain point dictionaries (no DB writes)."""
    text, encoding, notes = _read_file_text(record)
    issues: List[parser.Issue] = []

    if record.file_format == "gsi":
        gsi = parser.parse_gsi(text, parser.GsiOptions(angle_unit=project.angle_unit or "gon"))
        points = [p.as_dict() for p in gsi.points]
        if swap_xy:
            points = coord.swap_axes(points)
        return points, [i.as_dict() for i in gsi.issues], gsi, gsi.issues

    analysed = parser.analyze_text_file(text, encoding, notes)
    column_mapping = parser.ColumnMapping.from_dict(mapping) if mapping else analysed.mapping
    if not column_mapping.delimiter:
        column_mapping.delimiter = analysed.delimiter
    parsed = parser.parse_text_points(
        text,
        column_mapping,
        delimiter or column_mapping.delimiter or analysed.delimiter,
        analysed.header_detected if has_header is None else has_header,
    )
    points = [p.as_dict() for p in parsed.points]
    if swap_xy:
        points = coord.swap_axes(points)
    return points, [i.as_dict() for i in parsed.issues], None, parsed.issues


async def commit_file(
    session: AsyncSession,
    project: Project,
    record: ProjectFile,
    *,
    mapping: Optional[Dict[str, Any]] = None,
    delimiter: Optional[str] = None,
    has_header: Optional[bool] = None,
    swap_xy: bool = False,
    status: str = PointStatus.VALIDATED.value,
    replace_existing: bool = False,
) -> Dict[str, Any]:
    """Create ``SurveyPoint`` rows (plus stations/observations for GSI) from a raw file."""
    points, issue_dicts, gsi, raw_issues = await parse_stored_file(
        project, record, mapping=mapping, delimiter=delimiter, has_header=has_header, swap_xy=swap_xy
    )
    if not points:
        raise ValueError("No valid points could be parsed from this file; check the column mapping.")
    if status not in {s.value for s in PointStatus}:
        raise ValueError(f"Unknown point status '{status}'.")

    if replace_existing:
        await session.execute(delete(SurveyPoint).where(SurveyPoint.file_id == record.id))

    code_lookup = {c.code.upper(): c for c in (project.code_mappings or [])}
    created: List[SurveyPoint] = []
    for order, point in enumerate(points):
        code = str(point.get("code") or "").strip()
        base = parse_code_string(code)["base"]
        mapping_row = code_lookup.get(base.upper())
        if mapping_row is None:
            definition = lookup_definition(base)
            layer = definition.layer if definition else "S-POINT"
        else:
            layer = mapping_row.layer
        row = SurveyPoint(
            project_id=project.id,
            file_id=record.id,
            point_number=str(point["point_number"])[:64],
            easting=float(point["easting"]),
            northing=float(point["northing"]),
            elevation=None if point.get("elevation") is None else float(point["elevation"]),
            code=code[:64],
            description=str(point.get("description") or "")[:500],
            layer=layer,
            status=status,
            source_order=order,
            line_no=point.get("line_no"),
        )
        row.set_geometry()
        session.add(row)
        created.append(row)
    await session.flush()

    observations_created = 0
    stations_created = 0
    if gsi is not None:
        station_ids: Dict[str, str] = {}
        for station in gsi.stations:
            row = SurveyStation(
                project_id=project.id,
                file_id=record.id,
                point_number=station.point_number,
                easting=station.easting,
                northing=station.northing,
                elevation=station.elevation,
                instrument_height=station.instrument_height or 0.0,
                reflector_height=None,
                orientation_rad=station.orientation_rad,
                orientation_source="backsight" if station.orientation_rad is not None else None,
                line_no=station.line_no,
            )
            session.add(row)
            await session.flush()
            station_ids.setdefault(station.point_number, row.id)
            stations_created += 1
        for obs in gsi.observations:
            session.add(
                RawObservation(
                    project_id=project.id,
                    file_id=record.id,
                    station_id=station_ids.get(obs.station or ""),
                    point_number=obs.point_number,
                    line_no=obs.line_no,
                    hz_rad=obs.hz_rad,
                    v_rad=obs.v_rad,
                    slope_distance=obs.slope_distance,
                    horizontal_distance=obs.horizontal_distance,
                    height_difference=obs.height_difference,
                    reflector_height=obs.reflector_height,
                    code=obs.code,
                    description=obs.description,
                    computed_easting=obs.computed_easting,
                    computed_northing=obs.computed_northing,
                    computed_elevation=obs.computed_elevation,
                    recorded_easting=obs.recorded_easting,
                    recorded_northing=obs.recorded_northing,
                    recorded_elevation=obs.recorded_elevation,
                )
            )
            observations_created += 1

    # QA/QC over the *whole* project after the import, so cross-file duplicates show up.
    all_points = (
        await session.execute(select(SurveyPoint).where(SurveyPoint.project_id == project.id))
    ).scalars().all()
    engine_points = [
        {
            "point_number": p.point_number,
            "easting": p.easting,
            "northing": p.northing,
            "elevation": p.elevation,
            "code": p.code,
        }
        for p in all_points
    ]
    tolerances = coord.QaTolerances(
        duplicate_xy_tolerance=project.duplicate_xy_tolerance,
        duplicate_z_tolerance=project.duplicate_z_tolerance,
        z_mad_threshold=project.z_mad_threshold,
        local_z_step_threshold=project.local_z_step_threshold,
        known_codes=[c.code for c in (project.code_mappings or []) if c.enabled],
    )
    report = coord.validate_points(engine_points, tolerances, project_crs=project.crs_epsg)

    by_number: Dict[str, List[str]] = {}
    for flag in report.flags:
        if flag.severity in ("warning", "error"):
            for pn in flag.point_numbers:
                by_number.setdefault(pn, []).append(flag.code)
    for row in all_points:
        flags = by_number.get(row.point_number)
        row.qa_flags = json.dumps(flags) if flags else None
        row.qa_severity = ("error" if any(f in ("coordinate_out_of_range", "xy_swap_suspected") for f in (flags or []))
                           else ("warning" if flags else "ok"))

    record.status = "committed"
    record.imported_points = len(created)
    record.import_log = {
        **(record.import_log or {}),
        "committed_points": len(created),
        "stations": stations_created,
        "observations": observations_created,
        "swap_xy": swap_xy,
        "status": status,
        "issues": issue_dicts[:100],
        "qa_summary": report.summary,
    }
    await mark_derived_outdated(session, project.id, "new import committed")
    await session.flush()

    return {
        "file": record.as_dict(),
        "points_created": len(created),
        "stations_created": stations_created,
        "observations_created": observations_created,
        "qa": report.as_dict(),
        "points": [p.as_dict() for p in created[:500]],
    }
