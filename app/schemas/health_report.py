from typing import List, Optional
from pydantic import BaseModel


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


class HealthReportEvent(BaseModel):
    no: int
    start_time: str
    end_time: str
    duration: str
    category: str
    value: str
    description: str


class HealthTimelineSegment(BaseModel):
    status: str
    start_pct: float
    width_pct: float
    label: str
    period: str


class HealthTimelineTrack(BaseModel):
    track_name: str
    segments: List[HealthTimelineSegment]


class HealthReportGatewayDetail(BaseModel):
    id: str
    status: str
    location: str
    type: str
    cpu_spec: str
    ram_spec: str
    sd_spec: str
    modem_spec: str
    provider_spec: str
    period: str
    period_hours: str
    uptime_duration: str
    uptime_pct: str
    downtime_duration: Optional[str] = "23h 45m"
    downtime_pct: Optional[str] = "3.2%"
    sla_target: Optional[str] = "99.5%"
    sla_target_hours: Optional[str] = "740h 17m"
    sla_status: Optional[str] = "Breach"
    sla_downtime_allowed: Optional[str] = "3h 43m"
    cpu_avg: int
    cpu_max: int
    ram_avg: int
    ram_max: int
    sd_avg: int
    sd_max: int
    sd_health_status: str
    sd_life_pct: int
    temp_avg: int
    temp_max: int
    cpu_trend: List[HealthTrendPoint]
    ram_trend: List[HealthTrendPoint]
    sd_trend: List[HealthTrendPoint]
    timeline_tracks: List[HealthTimelineTrack]
    events: List[HealthReportEvent]


class HealthReportGatewayDetailResponse(BaseModel):
    status: bool
    data: HealthReportGatewayDetail

