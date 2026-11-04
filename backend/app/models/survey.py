"""Total-station setups and raw (unreduced) observations."""

from __future__ import annotations

from typing import Any, List, Optional

from sqlalchemy import Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class SurveyStation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One instrument setup (occupied point) with its orientation.

    Raw observations are stored in radians as *read* from the instrument; the reduction
    to cartesian coordinates is a derived value, never a replacement of the raw record.
    """

    __tablename__ = "survey_stations"

    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    file_id: Mapped[Optional[str]] = mapped_column(ForeignKey("project_files.id", ondelete="SET NULL"))
    point_number: Mapped[str] = mapped_column(String(64), index=True)
    easting: Mapped[Optional[float]] = mapped_column(Float)
    northing: Mapped[Optional[float]] = mapped_column(Float)
    elevation: Mapped[Optional[float]] = mapped_column(Float)
    instrument_height: Mapped[float] = mapped_column(Float, default=0.0)
    reflector_height: Mapped[Optional[float]] = mapped_column(Float)
    orientation_rad: Mapped[Optional[float]] = mapped_column(Float)
    orientation_source: Mapped[Optional[str]] = mapped_column(String(32))
    line_no: Mapped[Optional[int]] = mapped_column(Integer)

    observations: Mapped[List["RawObservation"]] = relationship(
        back_populates="station", cascade="all, delete-orphan"
    )

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "point_number": self.point_number,
            "easting": self.easting,
            "northing": self.northing,
            "elevation": self.elevation,
            "instrument_height": self.instrument_height,
            "reflector_height": self.reflector_height,
            "orientation_rad": self.orientation_rad,
            "orientation_gon": None if self.orientation_rad is None else self.orientation_rad * 200.0 / 3.141592653589793,
            "orientation_source": self.orientation_source,
            "line_no": self.line_no,
        }


class RawObservation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A single polar observation exactly as recorded in the field book."""

    __tablename__ = "raw_observations"

    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    file_id: Mapped[Optional[str]] = mapped_column(ForeignKey("project_files.id", ondelete="SET NULL"))
    station_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("survey_stations.id", ondelete="CASCADE"), index=True
    )
    point_number: Mapped[str] = mapped_column(String(64), index=True)
    line_no: Mapped[Optional[int]] = mapped_column(Integer)

    hz_rad: Mapped[Optional[float]] = mapped_column(Float)
    v_rad: Mapped[Optional[float]] = mapped_column(Float)
    slope_distance: Mapped[Optional[float]] = mapped_column(Float)
    horizontal_distance: Mapped[Optional[float]] = mapped_column(Float)
    height_difference: Mapped[Optional[float]] = mapped_column(Float)
    reflector_height: Mapped[Optional[float]] = mapped_column(Float)
    code: Mapped[Optional[str]] = mapped_column(String(64))
    description: Mapped[Optional[str]] = mapped_column(String(255))
    face: Mapped[str] = mapped_column(String(4), default="1")

    # reduced values (derived, kept next to the raw record for audit)
    computed_easting: Mapped[Optional[float]] = mapped_column(Float)
    computed_northing: Mapped[Optional[float]] = mapped_column(Float)
    computed_elevation: Mapped[Optional[float]] = mapped_column(Float)
    recorded_easting: Mapped[Optional[float]] = mapped_column(Float)
    recorded_northing: Mapped[Optional[float]] = mapped_column(Float)
    recorded_elevation: Mapped[Optional[float]] = mapped_column(Float)

    station: Mapped[Optional[SurveyStation]] = relationship(back_populates="observations")

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "station_id": self.station_id,
            "point_number": self.point_number,
            "line_no": self.line_no,
            "hz_rad": self.hz_rad,
            "v_rad": self.v_rad,
            "slope_distance": self.slope_distance,
            "horizontal_distance": self.horizontal_distance,
            "height_difference": self.height_difference,
            "reflector_height": self.reflector_height,
            "code": self.code,
            "computed": {
                "easting": self.computed_easting,
                "northing": self.computed_northing,
                "elevation": self.computed_elevation,
            },
            "recorded": {
                "easting": self.recorded_easting,
                "northing": self.recorded_northing,
                "elevation": self.recorded_elevation,
            },
        }
