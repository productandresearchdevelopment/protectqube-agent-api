from typing import List, Optional
from pydantic import BaseModel


class CellularReportItem(BaseModel):
    no: int
    id: str
    location: str
    type: str                  # "SmartBox Hitam" | "SmartBox Putih"
    modem: str                 # "Quectel EC200E" | "Quectel EC25-E" | "SIM7600"
    provider: str              # "Telkomsel" | "Indosat" | "XL Axiata" | "Smartfren"
    sim_number: str            # e.g. "6281212345678"
    
    # Komunikasi CPU - Modem
    cpu_modem_uptime: str      # e.g. "728h 15m"
    cpu_modem_offline: str     # e.g. "15h 45m"
    cpu_modem_success_rate: float # e.g. 98.5
    cpu_modem_avg_resp_ms: int # e.g. 220
    
    # Koneksi Jaringan
    network_uptime: str        # e.g. "720h 30m"
    network_offline: str       # e.g. "23h 30m"
    network_success_rate: Optional[float] = 98.2 # e.g. 98.2
    network_avg_rsrp: int      # e.g. -78
    network_avg_temp: int      # e.g. 45
    
    # Periode Gangguan
    trouble_events_count: int  # e.g. 3
    trouble_last_offline: str  # e.g. "26 Oct 2026 14:32"


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
    status: str       # "online" | "degraded" | "offline" | "no_data"
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

