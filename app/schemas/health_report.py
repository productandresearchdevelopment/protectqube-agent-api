from typing import List, Optional
from pydantic import BaseModel


class HealthReportItem(BaseModel):
    no: int
    id: str
    location: str
    type: str                  # "SmartBox Hitam" | "SmartBox Putih"
    
    # CPU
    cpu_avg: int               # e.g. 32
    cpu_max: int               # e.g. 78
    cpu_gt_80_duration: str    # e.g. "5h 20m"
    
    # RAM
    ram_avg: int               # e.g. 43
    ram_max: int               # e.g. 81
    ram_gt_80_duration: str    # e.g. "2h 10m"
    
    # SD Card Usage
    sd_avg: int                # e.g. 68
    sd_max: int                # e.g. 82
    sd_gt_90_duration: str     # e.g. "-" | "18h 45m"
    
    # SD Card Health
    sd_health_status: str      # "Good" | "Caution" | "Poor"
    sd_life_pct: int           # e.g. 92
    
    # Suhu Sistem
    temp_avg: int              # e.g. 45
    temp_max: int              # e.g. 62 (highlight red if >= 80)
    
    # Uptime
    uptime_duration: str       # e.g. "720h 15m"
    uptime_pct: float          # e.g. 96.8
    
    jumlah_event: int          # e.g. 12, 28, 6


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
    status: str       # "normal" | "cpu_high" | "ram_high" | "sd_high" | "suhu_high" | "no_data"
    start_pct: float
    width_pct: float
    label: str
    period: str


class HealthTimelineTrack(BaseModel):
    track_name: str   # "CPU" | "RAM" | "SD Card" | "Suhu"
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

