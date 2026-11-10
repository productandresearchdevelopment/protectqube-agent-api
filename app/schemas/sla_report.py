from typing import List, Optional, Union, Dict, Any
from pydantic import BaseModel
from app.schemas.health_report import ReportPaginationInfo


class SLAReportItem(BaseModel):
    no: int
    id: str
    location: str
    type: str
    customer: str = "-"
    hardware_model: Optional[str] = "-"

    # Smartbox column
    smartbox_status: str = "Online"
    smartbox_uptime_pct: float = 100.0
    smartbox_uptime_duration: Optional[str] = "0m"

    # DVR column
    dvr_status: str = "Online"
    dvr_uptime_pct: float = 100.0
    dvr_uptime_duration: Optional[str] = "0m"

    # Network column
    network_status: str = "Online"
    network_uptime_pct: float = 100.0
    network_uptime_duration: Optional[str] = "0m"

    # Combined SLA column
    sla_uptime_pct: float = 100.0
    sla_failure_rate_pct: float = 0.0

    # Historical & metadata references
    overall_sla_pct: float = 100.0
    gateway_sla_pct: float = 100.0
    cellular_sla_pct: float = 100.0
    dvr_sla_pct: float = 100.0
    gateway_uptime_str: Optional[str] = "0m"
    gateway_offline_str: Optional[str] = "0m"
    cellular_uptime_str: Optional[str] = "0m"
    cellular_offline_str: Optional[str] = "0m"
    dvr_uptime_str: Optional[str] = "0m"
    dvr_offline_str: Optional[str] = "0m"
    events_count: int = 0
    last_update: Optional[str] = None


class SLAReportSummary(BaseModel):
    total_gateways: int
    total_locations: int = 0
    device_online_count: int = 0
    device_offline_count: int = 0
    total_cameras: int = 0
    cameras_online: int = 0
    cameras_offline: int = 0
    total_storage_tb: float = 0.0
    storage_used_tb: float = 0.0
    avg_sla_uptime: float
    avg_sla_failure_rate: float
    avg_smartbox_uptime: float
    avg_dvr_uptime: float
    avg_network_uptime: float
    total_incidents: int = 0
    mttr_minutes: float = 0.0
    mttr_formatted: str = "0 menit"
    mtbf_hours: float = 0.0
    mtbf_formatted: str = "0 jam"
    meet_sla_count: int
    breach_sla_count: int
    meet_sla_percent: float
    smartbox_hitam_sla: float
    smartbox_putih_sla: float


class SLAReportData(BaseModel):
    gateways: List[SLAReportItem]
    summary: SLAReportSummary
    pagination: ReportPaginationInfo


class SLAReportResponse(BaseModel):
    status: bool
    data: SLAReportData


class SLAReportGatewayDetail(BaseModel):
    id: str
    location: str
    type: str
    customer: str = "-"
    hardware_model: Optional[str] = "-"
    status: str = "Online"
    period: str
    period_hours: str
    sla_target: float = 99.5
    sla_uptime_pct: float
    sla_failure_rate_pct: float
    meets_sla: bool
    smartbox_status: str
    smartbox_uptime_pct: float
    smartbox_uptime_duration: str
    smartbox_offline_duration: str
    dvr_status: str
    dvr_uptime_pct: float
    dvr_uptime_duration: str
    dvr_offline_duration: str
    network_status: str
    network_uptime_pct: float
    network_uptime_duration: str
    network_offline_duration: str
    trouble_events: List[Dict[str, Any]] = []
    daily_breakdown: List[Dict[str, Any]] = []
    daily_summary: Optional[Dict[str, Any]] = None
    timeline_tracks: Optional[List[Dict[str, Any]]] = None


class SLAReportGatewayDetailResponse(BaseModel):
    status: bool
    data: SLAReportGatewayDetail
