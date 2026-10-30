from typing import List, Optional
from pydantic import BaseModel


class DVRReportItem(BaseModel):
    no: int
    id: str
    location: str
    type: str
    dvr_model: str
    
    cpu_dvr_uptime: str
    cpu_dvr_offline: str
    cpu_dvr_success_rate: float
    cpu_dvr_avg_resp_ms: int
    
    kamera_total: int
    kamera_online: int
    kamera_no_video: int
    kamera_offline: int
    
    rec_uptime: str
    rec_tidak_merekam: str
    rec_error: str
    
    storage_kapasitas: str
    storage_terpakai_pct: int
    storage_rata_rata: str
    
    jumlah_event: int
    terakhir_offline: str


class ReportPaginationInfo(BaseModel):
    total_items: int
    total_pages: int
    current_page: int
    page_size: int
    showing_start: int
    showing_end: int


class DVRReportData(BaseModel):
    gateways: List[DVRReportItem]
    pagination: ReportPaginationInfo


class DVRReportResponse(BaseModel):
    status: bool
    data: DVRReportData


class DVRReportTroubleEvent(BaseModel):
    no: int
    start_time: str
    end_time: str
    duration: str
    category: str
    description: str


class DVRTimelineSegment(BaseModel):
    status: str
    start_pct: float
    width_pct: float
    label: str
    period: str


class DVRTimelineTrack(BaseModel):
    track_name: str
    segments: List[DVRTimelineSegment]


class DVRReportGatewayDetail(BaseModel):
    id: str
    status: str
    location: str
    type: str
    dvr_model: str
    kamera_channels: str
    storage_capacity: str
    period: str
    period_hours: str
    cpu_dvr_uptime: str
    cpu_dvr_uptime_pct: str
    cpu_dvr_offline: str
    cpu_dvr_offline_pct: str
    success_rate: str
    success_rate_checks: str
    avg_response_time: str
    rec_uptime: str
    rec_uptime_pct: str
    rec_tidak_merekam: str
    rec_tidak_merekam_pct: str
    rec_error: str
    rec_error_pct: str
    storage_used_pct: int
    kamera_total: int
    kamera_online: int
    kamera_no_video: int
    kamera_offline: int
    timeline_tracks: List[DVRTimelineTrack]
    trouble_events: List[DVRReportTroubleEvent]


class DVRReportGatewayDetailResponse(BaseModel):
    status: bool
    data: DVRReportGatewayDetail

