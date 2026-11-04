"""Project, layer standard and code-mapping models."""

from __future__ import annotations

import enum
from typing import Any, List, Optional

from sqlalchemy import JSON, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class ProjectStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    FIELDWORK = "FIELDWORK"
    PROCESSING = "PROCESSING"
    QAQC = "QAQC"
    APPROVED = "APPROVED"
    ARCHIVED = "ARCHIVED"


class Project(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A surveying project: CRS, units, tolerances and workflow status."""

    __tablename__ = "projects"

    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    code: Mapped[Optional[str]] = mapped_column(String(64), index=True)
    description: Mapped[Optional[str]] = mapped_column(Text)
    client: Mapped[Optional[str]] = mapped_column(String(200))
    location: Mapped[Optional[str]] = mapped_column(String(200))
    surveyor: Mapped[Optional[str]] = mapped_column(String(200))

    crs_epsg: Mapped[int] = mapped_column(Integer, default=28992, nullable=False)
    vertical_datum: Mapped[str] = mapped_column(String(32), default="NAP", nullable=False)
    linear_unit: Mapped[str] = mapped_column(String(16), default="m", nullable=False)
    angle_unit: Mapped[str] = mapped_column(String(16), default="gon", nullable=False)

    # QA/QC tolerances (metres unless stated otherwise)
    duplicate_xy_tolerance: Mapped[float] = mapped_column(Float, default=0.005)
    duplicate_z_tolerance: Mapped[float] = mapped_column(Float, default=0.02)
    z_mad_threshold: Mapped[float] = mapped_column(Float, default=3.5)
    local_z_step_threshold: Mapped[float] = mapped_column(Float, default=1.5)

    # surface defaults
    tin_boundary_mode: Mapped[str] = mapped_column(String(24), default="concave_hull")
    contour_interval: Mapped[float] = mapped_column(Float, default=0.10)
    breakline_codes: Mapped[list] = mapped_column(JSON, default=list)

    status: Mapped[str] = mapped_column(String(16), default=ProjectStatus.DRAFT.value, index=True)
    dependency_state: Mapped[str] = mapped_column(String(16), default="CURRENT")

    files: Mapped[List["ProjectFile"]] = relationship(  # noqa: F821
        back_populates="project", cascade="all, delete-orphan", lazy="selectin"
    )
    code_mappings: Mapped[List["CodeMapping"]] = relationship(
        back_populates="project", cascade="all, delete-orphan", lazy="selectin"
    )
    layers: Mapped[List["LayerStandard"]] = relationship(
        back_populates="project", cascade="all, delete-orphan", lazy="selectin"
    )

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "code": self.code,
            "description": self.description,
            "client": self.client,
            "location": self.location,
            "surveyor": self.surveyor,
            "crs_epsg": self.crs_epsg,
            "vertical_datum": self.vertical_datum,
            "linear_unit": self.linear_unit,
            "angle_unit": self.angle_unit,
            "duplicate_xy_tolerance": self.duplicate_xy_tolerance,
            "duplicate_z_tolerance": self.duplicate_z_tolerance,
            "z_mad_threshold": self.z_mad_threshold,
            "local_z_step_threshold": self.local_z_step_threshold,
            "tin_boundary_mode": self.tin_boundary_mode,
            "contour_interval": self.contour_interval,
            "breakline_codes": self.breakline_codes or [],
            "status": self.status,
            "dependency_state": self.dependency_state,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class LayerStandard(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """CAD layer definition used by the DXF writer and the web canvas."""

    __tablename__ = "layer_standards"
    __table_args__ = (UniqueConstraint("project_id", "name", name="uq_layer_project_name"),)

    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    color: Mapped[int] = mapped_column(Integer, default=7)
    linetype: Mapped[str] = mapped_column(String(32), default="CONTINUOUS")
    description: Mapped[Optional[str]] = mapped_column(String(200))
    visible: Mapped[bool] = mapped_column(default=True)

    project: Mapped[Project] = relationship(back_populates="layers")

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "color": self.color,
            "linetype": self.linetype,
            "description": self.description,
            "visible": self.visible,
        }


class CodeMapping(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Field code -> CAD layer / block / geometry behaviour."""

    __tablename__ = "code_mappings"
    __table_args__ = (UniqueConstraint("project_id", "code", name="uq_code_project_code"),)

    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    code: Mapped[str] = mapped_column(String(32), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), default="block")  # block|line|polygon|point
    layer: Mapped[str] = mapped_column(String(64), default="S-POINT")
    block_name: Mapped[Optional[str]] = mapped_column(String(64))
    color: Mapped[int] = mapped_column(Integer, default=7)
    description: Mapped[Optional[str]] = mapped_column(String(200))
    is_breakline: Mapped[bool] = mapped_column(default=False)
    enabled: Mapped[bool] = mapped_column(default=True)

    project: Mapped[Project] = relationship(back_populates="code_mappings")

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "code": self.code,
            "kind": self.kind,
            "layer": self.layer,
            "block_name": self.block_name,
            "color": self.color,
            "description": self.description,
            "is_breakline": self.is_breakline,
            "enabled": self.enabled,
        }
