from typing import Optional, Dict, Any, List
from datetime import datetime
from pydantic import BaseModel, Field


class DeviceUpdate(BaseModel):
    client_id: Optional[str] = Field(None, description="Client UUID or null to unassign")
    location: Optional[str] = Field(None, max_length=255)
    lat: Optional[float] = None
    long: Optional[float] = None
    hardware_model: Optional[str] = Field(None, max_length=100)
    operational_start: Optional[str] = Field(None, description="HH:MM:SS format")
    operational_end: Optional[str] = Field(None, description="HH:MM:SS format")
    is_active: Optional[bool] = None
    property: Optional[Dict[str, Any]] = Field(None, description="Additional properties JSONB")
    total_cameras: Optional[int] = Field(None, description="Shortcut to set property.total_cameras")
    selected_cameras: Optional[List[str]] = Field(None, description="List of camera channel IDs selected for monitoring")


class DetectedCamera(BaseModel):
    id: str
    channel: int
    name: str
    is_online: bool
    resolution: Optional[str] = None
    recording_status: Optional[str] = None


class DeviceResponse(BaseModel):
    id: str
    name: str
    location: Optional[str] = None
    lat: Optional[float] = None
    long: Optional[float] = None
    hardware_model: Optional[str] = None
    operational_start: Optional[str] = None
    operational_end: Optional[str] = None
    is_active: bool = True
    client_id: Optional[str] = None
    client_name: Optional[str] = None
    property: Dict[str, Any] = {}
    total_cameras: Optional[int] = None
    selected_cameras: Optional[List[str]] = None
    detected_cameras: Optional[List[DetectedCamera]] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True
