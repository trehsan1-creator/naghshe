"""Derived artefacts and the dependency graph that keeps them honest."""

from __future__ import annotations

import enum
import hashlib
import json
from typing import Any, Optional

from sqlalchemy import JSON, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class OutputKind(str, enum.Enum):
    LINEWORK = "linework"
    SURFACE = "surface"
    CONTOURS = "contours"
    VOLUME = "volume"
    PROFILE = "profile"
    CROSS_SECTIONS = "cross_sections"
    DXF = "dxf"
    REPORT = "report"


class OutputStatus(str, enum.Enum):
    CURRENT = "CURRENT"   # computed from the current source data
    OUTDATED = "OUTDATED"  # a source changed after this artefact was produced
    STALE_REF = "STALE_REF"


class DerivedOutput(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Everything SurveyPro computes from points (TIN, contours, volumes, DXF...).

    ``source_hash`` fingerprints the inputs (point ids + coordinates + breaklines).  When
    the points or breaklines change, every dependent artefact is flagged ``OUTDATED`` --
    a surveyor must never quote a volume computed from data that has since been edited.
    """

    __tablename__ = "derived_outputs"

    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default=OutputStatus.CURRENT.value, index=True)

    params: Mapped[Optional[dict]] = mapped_column(JSON)
    summary: Mapped[Optional[dict]] = mapped_column(JSON)
    payload_path: Mapped[Optional[str]] = mapped_column(Text)
    payload_inline: Mapped[Optional[dict]] = mapped_column(JSON)

    source_hash: Mapped[Optional[str]] = mapped_column(String(64), index=True)
    source_point_count: Mapped[int] = mapped_column(Integer, default=0)
    depends_on: Mapped[Optional[list]] = mapped_column(JSON)

    def as_dict(self, include_payload: bool = False) -> dict[str, Any]:
        data = {
            "id": self.id,
            "project_id": self.project_id,
            "kind": self.kind,
            "name": self.name,
            "status": self.status,
            "params": self.params or {},
            "summary": self.summary or {},
            "source_hash": self.source_hash,
            "source_point_count": self.source_point_count,
            "depends_on": self.depends_on or [],
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
        if include_payload:
            data["payload"] = self.payload_inline
        return data


def fingerprint_points(points: list[dict[str, Any]], extra: str = "") -> str:
    """Deterministic SHA-256 over the point set (id, xy, z, code) plus extra context."""
    digest = hashlib.sha256()
    for p in sorted(points, key=lambda q: (str(q.get("point_number")), str(q.get("id", "")))):
        digest.update(
            f"{p.get('point_number')}|{float(p['easting']):.4f}|{float(p['northing']):.4f}|"
            f"{'' if p.get('elevation') is None else format(float(p['elevation']), '.4f')}|"
            f"{p.get('code', '')}\n".encode("utf-8")
        )
    digest.update(extra.encode("utf-8"))
    return digest.hexdigest()


def json_dumps(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
