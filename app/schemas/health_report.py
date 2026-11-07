from typing import List, Optional
from pydantic import BaseModel
from app.schemas.cellular_report import DailySlaRecord, DailySlaSummary


class HealthReportItem(BaseModel):
    no: int
    id: str
    location: str
    type: str
    
    cpu_avg: int
    cpu_max: int
    cpu_gt_80_duration: str
    
    ram_avg: int
    ram_max: int
    ram_gt_80_duration: str
    
    sd_avg: int
    sd_max: int
    sd_gt_90_duration: str
    
    sd_health_status: str
    sd_life_pct: int
    
    temp_avg: int
    temp_max: int
    
    uptime_duration: str
    uptime_pct: float
    
    jumlah_event: int


class ReportPaginationInfo(BaseModel):
    total_items: int
    total_pages: int
    current_page: int
    page_size: int
    showing_start: int
    showing_end: int


class HealthReportData(BaseModel):
    gateways: List[HealthReportItem]
    pagination: ReportPaginationInfo


class HealthReportResponse(BaseModel):
    status: bool
    data: HealthReportData


class HealthTrendPoint(BaseModel):
    date: str
    value: float
    time: Optional[str] = None
    day: Optional[int] = None
    date_key: Optional[str] = None


class HealthReportEvent(BaseModel):
    no: int
    start_time: str
    end_time: str
    duration: str
    category: Optional[str] = "-"
    value: Optional[str] = "-"
    description: Optional[str] = "-"
    title: Optional[str] = None
    cause: Optional[str] = None
    reason: Optional[str] = None
    status: Optional[str] = "Resolved"
    duration_minutes: Optional[float] = None
    metric: Optional[str] = None
    date_str: Optional[str] = None
    telemetry_history_id: Optional[str] = None


class HealthTimelineSegment(BaseModel):
    status: str
    start_pct: float
    width_pct: float
    label: Optional[str] = "-"
    period: Optional[str] = "-"


class HealthTimelineTrack(BaseModel):
    track_name: str
    segments: Optional[List[HealthTimelineSegment]] = []


class HealthReportGatewayDetail(BaseModel):
    id: str
    status: Optional[str] = "Online"
    location: Optional[str] = "-"
    type: Optional[str] = "SmartBox Hitam"
    cpu_spec: Optional[str] = "-"
    ram_spec: Optional[str] = "-"
    sd_spec: Optional[str] = "-"
    modem_spec: Optional[str] = "-"
    provider_spec: Optional[str] = "-"
    period: Optional[str] = "-"
    period_hours: Optional[str] = "-"
    uptime_duration: Optional[str] = "-"
    uptime_pct: Optional[str] = "0%"
    downtime_duration: Optional[str] = "0m"
    downtime_pct: Optional[str] = "0%"
    sla_target: Optional[str] = "99.5%"
    sla_target_hours: Optional[str] = "-"
    sla_status: Optional[str] = "Met"
    sla_downtime_allowed: Optional[str] = "-"
    cpu_avg: Optional[int] = 0
    cpu_max: Optional[int] = 0
    ram_avg: Optional[int] = 0
    ram_max: Optional[int] = 0
    sd_avg: Optional[int] = 0
    sd_max: Optional[int] = 0
    sd_health_status: Optional[str] = "Good"
    sd_life_pct: Optional[int] = 100
    temp_avg: Optional[int] = 45
    temp_max: Optional[int] = 60
    cpu_trend: Optional[List[HealthTrendPoint]] = []
    ram_trend: Optional[List[HealthTrendPoint]] = []
    sd_trend: Optional[List[HealthTrendPoint]] = []
    timeline_tracks: Optional[List[HealthTimelineTrack]] = []
    events: Optional[List[HealthReportEvent]] = []
    daily_breakdown: Optional[List[DailySlaRecord]] = None
    daily_summary: Optional[DailySlaSummary] = None


class HealthReportGatewayDetailResponse(BaseModel):
    status: bool
    data: HealthReportGatewayDetail

