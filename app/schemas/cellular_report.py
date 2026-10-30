from typing import List, Optional
from pydantic import BaseModel


class CellularReportItem(BaseModel):
    no: int
    id: str
    location: str
    type: str
    modem: str
    provider: str
    sim_number: str
    
    cpu_modem_uptime: str
    cpu_modem_offline: str
    cpu_modem_success_rate: float
    cpu_modem_avg_resp_ms: int
    
    network_uptime: str
    network_offline: str
    network_success_rate: Optional[float] = 98.2
    network_avg_rsrp: int
    network_avg_temp: int
    
    trouble_events_count: int
    trouble_last_offline: str


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
    cause: str


class TimelineSegment(BaseModel):
    status: str
    start_pct: float
    width_pct: float
    label: str
    period: str


class CellularReportGatewayDetail(BaseModel):
    id: str
    status: str
    location: str
    type: str
    modem: str
    provider: str
    sim_number: str
    sim_status: str
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


class CellularReportGatewayDetailResponse(BaseModel):
    status: bool
    data: CellularReportGatewayDetail

