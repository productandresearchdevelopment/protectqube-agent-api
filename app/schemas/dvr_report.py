from typing import List, Optional
from pydantic import BaseModel


class DVRReportItem(BaseModel):
    no: int
    id: str
    location: str
    type: str                  # "SmartBox Hitam" | "SmartBox Putih"
    dvr_model: str             # "Hikvision DS-7616NI", "Dahua NVRS216", etc.
    
    # Komunikasi CPU - DVR
    cpu_dvr_uptime: str        # e.g. "720h 15m"
    cpu_dvr_offline: str       # e.g. "23h 45m"
    cpu_dvr_success_rate: float # e.g. 98.8
    cpu_dvr_avg_resp_ms: int   # e.g. 180
    
    # Status Kamera
    kamera_total: int          # e.g. 4, 8, 6
    kamera_online: int         # e.g. 4, 7, 6
    kamera_no_video: int       # e.g. 0, 1
    kamera_offline: int        # e.g. 0, 1
    
    # Status Recording
    rec_uptime: str            # e.g. "708h 20m"
    rec_tidak_merekam: str     # e.g. "12h 30m"
    rec_error: str             # e.g. "3h 10m"
    
    # Storage DVR
    storage_kapasitas: str     # e.g. "4 TB", "2 TB"
    storage_terpakai_pct: int  # e.g. 68, 82, 54
    storage_rata_rata: str     # e.g. "2.7 TB", "3.3 TB"
    
    jumlah_event: int          # e.g. 12, 28, 6
    terakhir_offline: str      # e.g. "26 Oct 2026 14:32"


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
    status: str       # "online" | "degraded" | "offline" | "no_data"
    start_pct: float
    width_pct: float
    label: str
    period: str


class DVRTimelineTrack(BaseModel):
    track_name: str   # "CPU – DVR" | "Recording" | "Kamera"
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

