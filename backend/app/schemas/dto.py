"""Pydantic v2 request/response models for the SurveyPro API."""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional, Sequence

from pydantic import BaseModel, ConfigDict, Field, field_validator


# --------------------------------------------------------------------------------------
# Projects
# --------------------------------------------------------------------------------------
class ProjectCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    code: Optional[str] = None
    description: Optional[str] = None
    client: Optional[str] = None
    location: Optional[str] = None
    surveyor: Optional[str] = None
    crs_epsg: int = Field(28992, ge=1, le=999999)
    vertical_datum: str = "NAP"
    angle_unit: Literal["gon", "deg", "mil", "dms"] = "gon"
    breakline_codes: Optional[List[str]] = None


class ProjectUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = None
    client: Optional[str] = None
    location: Optional[str] = None
    surveyor: Optional[str] = None
    crs_epsg: Optional[int] = Field(None, ge=1, le=999999)
    vertical_datum: Optional[str] = None
    angle_unit: Optional[Literal["gon", "deg", "mil", "dms"]] = None
    duplicate_xy_tolerance: Optional[float] = Field(None, gt=0, le=10)
    duplicate_z_tolerance: Optional[float] = Field(None, gt=0, le=10)
    z_mad_threshold: Optional[float] = Field(None, gt=0, le=20)
    local_z_step_threshold: Optional[float] = Field(None, gt=0, le=50)
    tin_boundary_mode: Optional[Literal["convex_hull", "concave_hull", "polygon"]] = None
    contour_interval: Optional[float] = Field(None, gt=0, le=100)
    breakline_codes: Optional[List[str]] = None
    status: Optional[str] = None


# --------------------------------------------------------------------------------------
# Import
# --------------------------------------------------------------------------------------
class ColumnMappingIn(BaseModel):
    point_number: Optional[int] = Field(None, ge=0)
    easting: Optional[int] = Field(None, ge=0)
    northing: Optional[int] = Field(None, ge=0)
    elevation: Optional[int] = Field(None, ge=0)
    code: Optional[int] = Field(None, ge=0)
    description: Optional[int] = Field(None, ge=0)
    has_header: bool = False
    delimiter: str = "ws"


class AnalyzeRequest(BaseModel):
    mapping: Optional[ColumnMappingIn] = None
    delimiter: Optional[str] = None
    has_header: Optional[bool] = None
    swap_xy: bool = False
    preview_only: bool = True


class CommitRequest(BaseModel):
    mapping: Optional[ColumnMappingIn] = None
    delimiter: Optional[str] = None
    has_header: Optional[bool] = None
    swap_xy: bool = False
    status: Literal["RAW", "VALIDATED", "APPROVED", "REJECTED"] = "VALIDATED"
    replace_existing: bool = False


# --------------------------------------------------------------------------------------
# Points
# --------------------------------------------------------------------------------------
class PointPatch(BaseModel):
    elevation: Optional[float] = None
    code: Optional[str] = None
    description: Optional[str] = None
    layer: Optional[str] = None
    status: Optional[Literal["RAW", "VALIDATED", "APPROVED", "REJECTED"]] = None


class BulkStatusRequest(BaseModel):
    ids: Optional[List[str]] = None
    point_numbers: Optional[List[str]] = None
    status: Literal["RAW", "VALIDATED", "APPROVED", "REJECTED"]
    from_status: Optional[List[str]] = None
    code: Optional[str] = None

    @field_validator("ids", "point_numbers", "from_status")
    @classmethod
    def _no_empty(cls, value):
        return value or None


class QaRequest(BaseModel):
    statuses: Optional[List[str]] = None
    persist: bool = True


# --------------------------------------------------------------------------------------
# Codes / layers
# --------------------------------------------------------------------------------------
class CodeMappingIn(BaseModel):
    code: str = Field(..., min_length=1, max_length=32)
    kind: Literal["block", "line", "polygon", "point"] = "block"
    layer: str = "S-POINT"
    block_name: Optional[str] = None
    color: int = Field(7, ge=0, le=256)
    description: Optional[str] = None
    is_breakline: bool = False
    enabled: bool = True


class LayerIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=64)
    color: int = Field(7, ge=0, le=256)
    linetype: str = "CONTINUOUS"
    description: Optional[str] = None
    visible: bool = True


# --------------------------------------------------------------------------------------
# Surfaces / volumes / profiles
# --------------------------------------------------------------------------------------
class SurfaceBuildRequest(BaseModel):
    name: Optional[str] = None
    statuses: Optional[List[str]] = None
    file_id: Optional[str] = None
    boundary_mode: Literal["convex_hull", "concave_hull", "polygon"] = "concave_hull"
    boundary: Optional[List[List[float]]] = None
    concave_ratio: float = Field(0.15, ge=0.0, le=1.0)
    breakline_codes: Optional[List[str]] = None
    use_breaklines: bool = True
    contour_interval: Optional[float] = Field(None, gt=0, le=100)
    major_every: int = Field(5, ge=0, le=50)
    contour_method: Literal["grid", "tin"] = "grid"
    contour_resolution: Optional[float] = Field(None, gt=0, le=50)


class VolumeRequest(BaseModel):
    existing_surface_id: str
    proposed_surface_id: Optional[str] = None
    proposed_file_id: Optional[str] = None
    method: Literal["grid", "average_end_area"] = "grid"
    cell_size: float = Field(0.5, gt=0, le=50)


class ProfileRequest(BaseModel):
    surface_id: str
    design_surface_id: Optional[str] = None
    alignment: Optional[List[List[float]]] = None
    feature_name: Optional[str] = None
    station_interval: float = Field(5.0, gt=0, le=500)
    offsets: List[float] = Field(default_factory=lambda: [0.0])


class CrossSectionRequest(BaseModel):
    surface_id: str
    design_surface_id: Optional[str] = None
    alignment: Optional[List[List[float]]] = None
    feature_name: Optional[str] = None
    stations: Optional[List[float]] = None
    station_interval: float = Field(10.0, gt=0, le=500)
    left: float = Field(10.0, gt=0, le=200)
    right: float = Field(10.0, gt=0, le=200)
    samples: int = Field(61, ge=2, le=2001)


class ExportRequest(BaseModel):
    statuses: Optional[List[str]] = None
    surface_id: Optional[str] = None
    include_points: bool = True
    include_linework: bool = True
    include_tin: bool = True
    include_contours: bool = True
    include_labels: bool = True
    contour_interval: Optional[float] = None
    major_every: int = 5


# --------------------------------------------------------------------------------------
# Demo
# --------------------------------------------------------------------------------------
class DemoSeedRequest(BaseModel):
    name: str = "Sidewalk reconstruction -- Leimuiden (demo)"
    include_proposed: bool = True


class Message(BaseModel):
    model_config = ConfigDict(extra="allow")
    detail: str
