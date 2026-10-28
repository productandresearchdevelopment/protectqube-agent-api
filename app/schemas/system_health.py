from typing import List, Optional
from pydantic import BaseModel


class DeviceSummary(BaseModel):
    name: str
    model: str
    total: int
    healthy: int
    warning: int
    critical: int


class SystemHealthSummary(BaseModel):
    total_gateways: int
    healthy: int
    healthy_percent: float
    warning: int
    warning_percent: float
    critical: int
    critical_percent: float
    smartbox_hitam: DeviceSummary
    smartbox_putih: DeviceSummary


class TimelinePoint(BaseModel):
    time: str
    value: float


class MetricChart(BaseModel):
    avg: float
    max: Optional[float] = None
    min: Optional[float] = None
    timeline: List[TimelinePoint]


class SystemHealthCharts(BaseModel):
    cpu: MetricChart
    ram: MetricChart
    sd_card: MetricChart
    uptime: MetricChart


class GatewayItem(BaseModel):
    no: int
    id: str
    location: str
    type: str
    model: str
    cpu: int
    ram: int
    sd_used_gb: int
    sd_total_gb: int
    sd_percent: int
    sd_health: str
    uptime: str
    status: str
    last_update: str


class PaginationInfo(BaseModel):
    total_items: int
    total_pages: int
    current_page: int
    page_size: int
    showing_start: int
    showing_end: int


class SystemHealthDashboardData(BaseModel):
    summary: SystemHealthSummary
    charts: SystemHealthCharts
    gateways: List[GatewayItem]
    pagination: PaginationInfo


class SystemHealthDashboardResponse(BaseModel):
    status: bool
    data: SystemHealthDashboardData


class SDHealthDetails(BaseModel):
    status: str
    bad_sector: int
    wear_level: str
    temperature: str
    io_error: int


class DowntimeEvent(BaseModel):
    no: int
    start_time: str
    end_time: str
    duration: str
    accumulated_hours: str
    category: str
    reason: str
    sla_impact_pct: float
    status: str


class GatewayDetailData(BaseModel):
    id: str
    location: str
    type: str
    model: str
    ip_address: str
    uptime: str
    last_update: str
    service_status: str
    cpu_percent: int
    cpu_min: str
    cpu_max: str
    cpu_sparkline: List[float]
    ram_percent: int
    ram_min: str
    ram_max: str
    ram_sparkline: List[float]
    sd_percent: int
    sd_used_gb: int
    sd_total_gb: int
    sd_sparkline: List[float]
    sd_health: SDHealthDetails
    uptime_days: int
    uptime_hours: int
    uptime_status: str
    uptime_subtext: str
    month_period: Optional[str] = "01 Oct 2026 - 31 Oct 2026"
    month_total_hours: Optional[int] = 744
    uptime_duration: Optional[str] = "720h 15m"
    uptime_pct: Optional[str] = "96.8%"
    downtime_duration: Optional[str] = "23h 45m"
    downtime_pct: Optional[str] = "3.2%"
    sla_target: Optional[float] = 99.5
    sla_target_hours: Optional[str] = "740h 17m"
    sla_status: Optional[str] = "Breach"
    sla_downtime_allowed: Optional[str] = "3h 43m"
    downtime_events: Optional[List[DowntimeEvent]] = None


class GatewayDetailResponse(BaseModel):
    status: bool
    data: GatewayDetailData

