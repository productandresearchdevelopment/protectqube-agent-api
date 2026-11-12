from typing import List, Optional
from pydantic import BaseModel


class CellularReportItem(BaseModel):
    no: int
    id: str
    location: str
    customer: Optional[str] = "-"
    type: str
    modem: str
    modem_name: Optional[str] = None
    modem_temp: Optional[int] = None
    provider: str
    sim_number: str
    quota_remaining_gb: Optional[float] = None
    
    cpu_modem_uptime: str
    cpu_modem_offline: str
    cpu_modem_success_rate: float
    cpu_modem_avg_resp_ms: Optional[float] = None
    
    network_uptime: str
    network_offline: str
    network_success_rate: Optional[float] = 98.2
    network_avg_rsrp: Optional[float] = None
    network_avg_temp: Optional[float] = None

    sla: Optional[float] = None
    
    trouble_events_count: int
    trouble_last_offline: str
    last_seen: Optional[str] = None


class ReportPaginationInfo(BaseModel):
    total_items: int
    total_pages: int
    current_page: int
    page_size: int
    showing_start: int
    showing_end: int


class CellularReportData(BaseModel):
    gateways: List[CellularReportItem]
    pagination: ReportPaginationInfo


class CellularReportResponse(BaseModel):
    status: bool
    data: CellularReportData


class TroubleEventItem(BaseModel):
    no: int
    start_time: str
    end_time: str
    duration: str
    cause: Optional[str] = None
    category: Optional[str] = None
    metric: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    reason: Optional[str] = None
    status: Optional[str] = "Resolved"
    duration_minutes: Optional[float] = None
    date_str: Optional[str] = None
    telemetry_history_id: Optional[str] = None


class TimelineSegment(BaseModel):
    status: str
    start_pct: float
    width_pct: float
    label: str
    period: str


class DailySlaRecord(BaseModel):
    day: int
    date: str
    day_name: str
    target_sla: float = 98.0
    observation_min: Optional[float] = None
    uptime_min: float
    downtime_min: float
    success_rate: float
    sla_diff: float
    sla_status: str
    cpu_modem_uptime_min: float
    cpu_modem_downtime_min: float
    cpu_modem_success_rate: float
    cpu_modem_sla_diff: float
    cpu_modem_status_sla: str
    cellular_uptime_min: float
    cellular_downtime_min: float
    cellular_success_rate: float
    cellular_sla_diff: float
    cellular_status_sla: str
    cpu_dvr_uptime_min: Optional[float] = None
    cpu_dvr_downtime_min: Optional[float] = None
    cpu_dvr_success_rate: Optional[float] = None
    cpu_dvr_sla_diff: Optional[float] = None
    cpu_dvr_status_sla: Optional[str] = None
    rec_uptime_min: Optional[float] = None
    rec_downtime_min: Optional[float] = None
    rec_success_rate: Optional[float] = None
    rec_sla_diff: Optional[float] = None
    rec_status_sla: Optional[str] = None
    rec_channels: Optional[str] = None
    rec_condition: Optional[str] = None


class DailySlaSummary(BaseModel):
    total_days: int
    target_sla_pct: float
    total_obs_min: float
    total_cpu_modem_uptime_min: float
    total_cpu_modem_downtime_min: float
    avg_cpu_modem_success_rate: float
    cpu_modem_sla_status: str
    total_cellular_uptime_min: float
    total_cellular_downtime_min: float
    avg_cellular_success_rate: float
    cellular_sla_status: str
    total_cpu_dvr_uptime_min: Optional[float] = None
    total_cpu_dvr_downtime_min: Optional[float] = None
    avg_cpu_dvr_success_rate: Optional[float] = None
    cpu_dvr_sla_status: Optional[str] = None
    total_rec_uptime_min: Optional[float] = None
    total_rec_downtime_min: Optional[float] = None
    avg_rec_success_rate: Optional[float] = None
    rec_sla_status: Optional[str] = None


class CellularReportGatewayDetail(BaseModel):
    id: str
    status: str
    location: str
    type: str
    modem: str
    provider: str
    sim_number: str
    sim_status: str
    quota_main_gb: Optional[float] = None
    quota_info: Optional[str] = None
    ip_address: str
    period: str
    period_hours: str
    cpu_modem_uptime: str
    cpu_modem_uptime_pct: str
    cpu_modem_offline: str
    cpu_modem_offline_pct: str
    success_rate: str
    success_rate_checks: str
    avg_response_time: str
    network_uptime: str
    network_uptime_pct: str
    network_offline: str
    network_offline_pct: str
    avg_rsrp: str
    avg_modem_temp: str
    temp_range: str
    total_gangguan: str
    timeline_segments: List[TimelineSegment]
    trouble_events: List[TroubleEventItem]
    daily_breakdown: Optional[List[DailySlaRecord]] = None
    daily_summary: Optional[DailySlaSummary] = None


class CellularReportGatewayDetailResponse(BaseModel):
    status: bool
    data: CellularReportGatewayDetail

