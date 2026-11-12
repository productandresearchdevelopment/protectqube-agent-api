from typing import List, Optional, Union, Dict, Any
from pydantic import BaseModel


class DeviceSummary(BaseModel):
    name: str
    model: str
    total: int
    online: Optional[int] = 0
    offline: Optional[int] = 0
    healthy: Optional[int] = 0
    warning: Optional[int] = 0
    critical: Optional[int] = 0


class SystemHealthSummary(BaseModel):
    total_gateways: int
    online: Optional[int] = 0
    online_percent: Optional[float] = 0.0
    offline: Optional[int] = 0
    offline_percent: Optional[float] = 0.0
    healthy: Optional[int] = 0
    healthy_percent: Optional[float] = 0.0
    warning: Optional[int] = 0
    warning_percent: Optional[float] = 0.0
    critical: Optional[int] = 0
    critical_percent: Optional[float] = 0.0
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
    device_uuid: Optional[str] = None
    customer: Optional[str] = "-"
    client_name: Optional[str] = "-"
    location: str
    type: str
    model: str
    cpu: Union[int, float, str]
    ram: Union[int, float, str]
    sd_used_gb: Union[int, float, str]
    sd_total_gb: Union[int, float, str]
    sd_percent: Union[int, float, str]
    sd_health: str
    sd_health_percent: Optional[Union[int, float, str]] = 100
    uptime: str
    status: str
    last_update: str
    power_source: Optional[str] = "AC"
    power_status: Optional[str] = "Normal"
    power_badge: Optional[str] = "Normal"
    power_text: Optional[str] = "AC [OK]"
    battery_percent: Optional[Union[int, float, str]] = None
    is_power_drop: Optional[bool] = False
    voltage: Optional[str] = None


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
    health_percent: Optional[Union[int, float, str]] = 100
    bad_sector: Optional[Union[int, str]] = 0
    wear_level: Optional[str] = "0%"
    temperature: Optional[str] = "45°C"
    io_error: Optional[Union[int, str]] = 0


class DowntimeEvent(BaseModel):
    no: int
    start_time: str
    end_time: str
    duration: str
    accumulated_hours: Optional[str] = "-"
    category: str
    reason: str
    sla_impact_pct: Optional[float] = 0.0
    status: str


class SystemHealthEventItem(BaseModel):
    id: Optional[str] = None
    title: str
    time: str
    status: str = "success"
    duration: Optional[str] = None
    category: Optional[str] = None
    epoch: Optional[float] = None


class GatewayDetailData(BaseModel):
    id: str
    device_uuid: Optional[str] = None
    customer: Optional[str] = "-"
    client_name: Optional[str] = "-"
    location: str
    type: str
    model: str
    ip_address: str
    uptime: str
    last_update: str
    service_status: str
    cpu_percent: Union[int, float, str]
    cpu_min: str
    cpu_max: str
    cpu_sparkline: List[Union[float, int, str]]
    ram_percent: Union[int, float, str]
    ram_min: str
    ram_max: str
    ram_sparkline: List[Union[float, int, str]]
    ram_total_gb: Optional[Union[float, int, str]] = None
    ram_used_gb: Optional[Union[float, int, str]] = None
    ram_free_gb: Optional[Union[float, int, str]] = None
    sd_percent: Union[int, float, str]
    sd_used_gb: Union[int, float, str]
    sd_total_gb: Union[int, float, str]
    sd_sparkline: List[Union[float, int, str]]
    sd_health: SDHealthDetails
    uptime_days: Optional[Union[int, str]] = 1
    uptime_hours: Optional[Union[int, str]] = 0
    uptime_status: str
    uptime_subtext: str
    month_period: Optional[str] = None
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
    events: Optional[List[SystemHealthEventItem]] = None
    status: Optional[str] = "Healthy"
    daily_uptime: Optional[Dict[str, Any]] = None
    power_info: Optional[Dict[str, Any]] = None


class GatewayDetailResponse(BaseModel):
    status: bool
    data: GatewayDetailData

