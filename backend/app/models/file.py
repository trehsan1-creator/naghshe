"""Raw project file (the immutable tier-1 record of every import)."""

from __future__ import annotations

from typing import Any, Optional

from sqlalchemy import JSON, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class ProjectFile(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """An uploaded raw file.

    RAW DATA is never modified: the bytes are written once to content-addressed storage,
    their SHA-256 is recorded, and every derived artefact points back here.
    """

    __tablename__ = "project_files"

    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_path: Mapped[str] = mapped_column(Text, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    file_format: Mapped[str] = mapped_column(String(16), default="txt", index=True)
    encoding: Mapped[Optional[str]] = mapped_column(String(32))
    delimiter: Mapped[Optional[str]] = mapped_column(String(8))
    status: Mapped[str] = mapped_column(String(16), default="uploaded", index=True)
    row_count: Mapped[int] = mapped_column(Integer, default=0)
    imported_points: Mapped[int] = mapped_column(Integer, default=0)
    import_log: Mapped[Optional[dict]] = mapped_column(JSON)
    notes: Mapped[Optional[str]] = mapped_column(Text)

    project: Mapped["Project"] = relationship(back_populates="files")  # noqa: F821

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "project_id": self.project_id,
            "original_filename": self.original_filename,
            "stored_filename": self.stored_filename,
            "sha256": self.sha256,
            "size_bytes": self.size_bytes,
            "file_format": self.file_format,
            "encoding": self.encoding,
            "delimiter": self.delimiter,
            "status": self.status,
            "row_count": self.row_count,
            "imported_points": self.imported_points,
            "notes": self.notes,
            "import_log": self.import_log,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
