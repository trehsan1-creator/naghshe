"""Survey point -- the tier-2/3 record that flows into surfaces, volumes and CAD."""

from __future__ import annotations

import enum
from typing import Any, Optional

from sqlalchemy import Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..db.base import Base, PointZType, TimestampMixin, UUIDPrimaryKeyMixin, wkt_point


class PointStatus(str, enum.Enum):
    """Three-tier data governance.

    ``RAW``       imported, not yet checked
    ``VALIDATED`` passed QA/QC (or consciously accepted)
    ``APPROVED``  signed off -- only these feed approved surfaces/deliverables
    ``REJECTED``  excluded from every computation
    """

    RAW = "RAW"
    VALIDATED = "VALIDATED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class SurveyPoint(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "survey_points"

    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    file_id: Mapped[Optional[str]] = mapped_column(ForeignKey("project_files.id", ondelete="SET NULL"))

    point_number: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    easting: Mapped[float] = mapped_column(Float, nullable=False, index=True)
    northing: Mapped[float] = mapped_column(Float, nullable=False, index=True)
    elevation: Mapped[Optional[float]] = mapped_column(Float, index=True)
    code: Mapped[str] = mapped_column(String(64), default="", index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    layer: Mapped[str] = mapped_column(String(64), default="S-POINT", index=True)

    status: Mapped[str] = mapped_column(String(16), default=PointStatus.RAW.value, index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    source_order: Mapped[int] = mapped_column(Integer, default=0)  # field-book order
    line_no: Mapped[Optional[int]] = mapped_column(Integer)

    qa_severity: Mapped[Optional[str]] = mapped_column(String(16), index=True)
    qa_flags: Mapped[Optional[str]] = mapped_column(Text)  # JSON list of flag codes

    geom: Mapped[Optional[str]] = mapped_column(PointZType)

    def set_geometry(self) -> None:
        """(Re)build the PostGIS/WKT geometry from the numeric coordinates."""
        self.geom = wkt_point(self.easting, self.northing, self.elevation)

    def as_dict(self, include_geometry: bool = False) -> dict[str, Any]:
        data = {
            "id": self.id,
            "project_id": self.project_id,
            "file_id": self.file_id,
            "point_number": self.point_number,
            "easting": self.easting,
            "northing": self.northing,
            "elevation": self.elevation,
            "code": self.code,
            "description": self.description,
            "layer": self.layer,
            "status": self.status,
            "version": self.version,
            "source_order": self.source_order,
            "line_no": self.line_no,
            "qa_severity": self.qa_severity,
            "qa_flags": self.qa_flags,
        }
        if include_geometry:
            data["geom"] = self.geom if isinstance(self.geom, str) else None
        return data

    def to_engine_dict(self) -> dict[str, Any]:
        """The plain dictionary the computational engines consume."""
        return {
            "id": self.id,
            "point_number": self.point_number,
            "easting": float(self.easting),
            "northing": float(self.northing),
            "elevation": None if self.elevation is None else float(self.elevation),
            "code": self.code or "",
            "description": self.description or "",
            "layer": self.layer,
            "status": self.status,
            "source_order": self.source_order,
        }
