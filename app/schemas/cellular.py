from typing import List, Optional
from pydantic import BaseModel


class DeviceSummary(BaseModel):
    name: str
    model: str
    total: int
    online: int
    offline: int
    degraded: int


class CellularSummary(BaseModel):
    total_gateways: int
    online: int
    online_percent: float
    offline: int
    offline_percent: float
    degraded: int
    degraded_percent: float
    smartbox_hitam: DeviceSummary
    smartbox_putih: DeviceSummary


class DonutSlice(BaseModel):
    label: str
    count: int
    percent: float
    color: str


class DonutChart(BaseModel):
    total_label: str
    total_count: int
    total_percent: float
    slices: List[DonutSlice]


class TimelinePoint(BaseModel):
    time: str
    value: float


class MetricChart(BaseModel):
    avg: str
    max: Optional[str] = None
    min: Optional[str] = None
    timeline: List[TimelinePoint]


class CellularCharts(BaseModel):
    cpu_modem_comm: DonutChart
    modem_network_status: DonutChart
    signal_strength: MetricChart
    modem_temperature: MetricChart


class CellularGatewayItem(BaseModel):
    no: int
    id: str
    location: str
    type: str
    model: str
    modem: str
    provider: str
    sim_status: str
    cpu_modem: str
    network: str
    signal_rsrp: str
    signal_bars: int
    modem_temp: str
    status: str
    last_update: str


class PaginationInfo(BaseModel):
    total_items: int
    total_pages: int
    current_page: int
    page_size: int
    showing_start: int
    showing_end: int


class CellularDashboardData(BaseModel):
    summary: CellularSummary
    charts: CellularCharts
    gateways: List[CellularGatewayItem]
    pagination: PaginationInfo


class CellularDashboardResponse(BaseModel):
    status: bool
    data: CellularDashboardData


class CPUModemDetail(BaseModel):
    status: str
    message: str
    port: str
    baudrate: int
    driver: str
    last_check: str


class SignalStrengthDetail(BaseModel):
    rsrp: int
    unit: str
    max_rsrp: str
    min_rsrp: str
    avg_rsrp: str
    sparkline: List[float]


class NetworkSIMDetail(BaseModel):
    network_type: str
    network_sub: str
    operator: str
    sim_status: str
    imsi: str
    iccid: str
    data_upload: str
    data_download: str
    roaming: str


class ModemTempDetail(BaseModel):
    temperature: int
    unit: str
    max_temp: str
    min_temp: str
    avg_temp: str
    sparkline: List[float]


class CellularGatewayDetailData(BaseModel):
    id: str
    location: str
    type: str
    model: str
    modem: str
    provider: str
    sim_card: str
    ip_address: str
    last_update: str
    service_status: str
    cpu_modem: CPUModemDetail
    signal_strength: SignalStrengthDetail
    network_sim: NetworkSIMDetail
    modem_temperature: ModemTempDetail


class CellularGatewayDetailResponse(BaseModel):
    status: bool
    data: CellularGatewayDetailData

