"""Declarative base, naming conventions and the cross-dialect geometry type."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import DateTime, MetaData, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

try:  # PostGIS geometry support
    from geoalchemy2 import Geometry
    from geoalchemy2.elements import WKTElement
except Exception:  # pragma: no cover - geoalchemy2 is a hard requirement in prod
    Geometry = None  # type: ignore
    WKTElement = None  # type: ignore

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

#: On PostgreSQL this is a real PostGIS ``POINTZ`` column (GIST indexed);
#: on SQLite it degrades to ISO-8601 WKT text so the same models run anywhere.
PointZType: Any = Text().with_variant(
    Geometry(geometry_type="POINTZ", srid=0, spatial_index=True), "postgresql"
) if Geometry is not None else Text()


def new_uuid() -> str:
    return uuid.uuid4().hex


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, server_default=func.now(),
        nullable=False,
    )


class UUIDPrimaryKeyMixin:
    """String UUID primary keys (portable between PostgreSQL and SQLite)."""

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_uuid)


def wkt_point(x: float, y: float, z: Optional[float]) -> Any:
    """Build a geometry literal for the active dialect.

    PostGIS gets an EWKT ``POINT Z`` element (so the column stays queryable with
    ``ST_Intersects``/``ST_DWithin``); SQLite stores the same text verbatim.
    """
    if z is None:
        text = f"POINT Z ({x:.4f} {y:.4f} 0.0000)"
    else:
        text = f"POINT Z ({x:.4f} {y:.4f} {float(z):.4f})"
    if WKTElement is not None and _is_postgres():
        return WKTElement(text, srid=0)
    return text


def _is_postgres() -> bool:
    from ..config import settings

    return settings.is_postgres


def wkt_to_xy(text: Any) -> tuple[float, float, float] | None:
    """Parse a stored WKT/EWKT POINT back into ``(x, y, z)``."""
    if text is None:
        return None
    if not isinstance(text, str):
        text = str(text)
    try:
        body = text[text.index("(") + 1 : text.rindex(")")]
        parts = [p for p in body.replace(",", " ").split() if p]
        x, y = float(parts[0]), float(parts[1])
        z = float(parts[2]) if len(parts) > 2 else 0.0
        return x, y, z
    except Exception:
        return None
