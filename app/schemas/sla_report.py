from typing import List, Optional, Union, Dict, Any
from pydantic import BaseModel
from app.schemas.health_report import ReportPaginationInfo


class SLAReportItem(BaseModel):
    no: int
    id: str
    location: str
    type: str
    hardware_model: Optional[str] = "-"
    status: str = "Online"

    overall_sla_pct: float
    gateway_sla_pct: float
    gateway_uptime_str: str
    gateway_offline_str: str

    cellular_sla_pct: float
    cellular_uptime_str: str
    cellular_offline_str: str

    dvr_sla_pct: float
    dvr_uptime_str: str
    dvr_offline_str: str

    events_count: int
    last_update: Optional[str] = None


class SLAReportSummary(BaseModel):
    total_gateways: int
    avg_overall_sla: float
    avg_gateway_sla: float
    avg_cellular_sla: float
    avg_dvr_sla: float
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
