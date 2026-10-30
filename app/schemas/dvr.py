from typing import List, Optional
from pydantic import BaseModel


class DVRSummary(BaseModel):
    total_gateways: int
    recording_normal: int
    recording_normal_percent: float
    issue: int
    issue_percent: float
    offline: int
    offline_percent: float
    total_kamera: int
    kamera_online: int
    kamera_no_video: int
    kamera_offline: int
    total_storage_tb: int
    storage_used_tb: int
    storage_warning_tb: int
    storage_critical_tb: int


class DonutSlice(BaseModel):
    label: str
    count: int
    percent: float
    color: str


class DonutChart(BaseModel):
    total_label: str
    total_count: int
    slices: List[DonutSlice]


class TimelinePoint(BaseModel):
    time: str
    value: float


class MetricChart(BaseModel):
    avg: str
    max: Optional[str] = None
    min: Optional[str] = None
    timeline: List[TimelinePoint]


class DVRCharts(BaseModel):
    cpu_dvr_comm: DonutChart
    status_kamera: DonutChart
    recording_status: DonutChart
    storage_usage: MetricChart


class DVRGatewayItem(BaseModel):
    no: int
    id: str
    location: str
    type: str
    dvr_model: str
    cpu_dvr: str
    total_kamera: int
    kamera_online: int
    kamera_no_video: int
    kamera_offline: int
    recording_status: str
    storage_usage_percent: int
    dvr_health: str
    last_update: str


class PaginationInfo(BaseModel):
    total_items: int
    total_pages: int
    current_page: int
    page_size: int
    showing_start: int
    showing_end: int


class DVRDashboardData(BaseModel):
    summary: DVRSummary
    charts: DVRCharts
    gateways: List[DVRGatewayItem]
    pagination: PaginationInfo


class DVRDashboardResponse(BaseModel):
    status: bool
    data: DVRDashboardData


class CPUDVRDetail(BaseModel):
    status: str
    message: str
    port: str
    response_time: str
    packet_loss: str
    last_check: str


class CameraStatusDetail(BaseModel):
    total: int
    online: int
    no_video: int
    offline: int
    percent: int
    sparkline: List[float]


class RecordingStorageDetail(BaseModel):
    status: str
    used_tb: float
    total_tb: float
    percent: int
    retention_days: int
    sparkline: List[float]


class DVRHealthDetail(BaseModel):
    status: str
    hdd_status: str
    temperature: str
    fan_status: str
    bad_sector: int


class CameraChannelPreview(BaseModel):
    channel: int
    name: str
    status: str
    is_recording: bool
    fps: int
    resolution: str
    bitrate: str
    timestamp: str


class DVRGatewayDetailData(BaseModel):
    id: str
    location: str
    type: str
    model: str
    dvr_model: str
    ip_address: str
    last_update: str
    service_status: str
    cpu_dvr: CPUDVRDetail
    camera_status: CameraStatusDetail
    recording_storage: RecordingStorageDetail
    dvr_health: DVRHealthDetail
    cameras: List[CameraChannelPreview]


class DVRGatewayDetailResponse(BaseModel):
    status: bool
    data: DVRGatewayDetailData

