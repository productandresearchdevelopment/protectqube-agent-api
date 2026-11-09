import re
import logging
from typing import Optional
from fastapi import APIRouter, Depends, Query, Response, HTTPException

logger = logging.getLogger(__name__)
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.agents.agent_manager import agent_manager
from app.api.deps import get_current_user
from app.models.base_models import User
from app.services.system_health_service import system_health_service
from app.services.cellular_service import cellular_service
from app.services.incident_alert_service import incident_alert_service
from app.services.dvr_service import dvr_service
from app.services.cellular_report_service import cellular_report_service
from app.services.dvr_report_service import dvr_report_service
from app.services.health_report_service import health_report_service
from app.schemas.system_health import SystemHealthDashboardResponse, GatewayDetailResponse
from app.schemas.cellular import CellularDashboardResponse, CellularGatewayDetailResponse

from app.schemas.dvr import DVRDashboardResponse, DVRGatewayDetailResponse
from app.schemas.cellular_report import CellularReportResponse, CellularReportGatewayDetailResponse
from app.schemas.dvr_report import DVRReportResponse, DVRReportGatewayDetailResponse
from app.schemas.health_report import HealthReportResponse, HealthReportGatewayDetailResponse

router = APIRouter(prefix="/monitoring", tags=["Monitoring & Diagnostics"])


@router.get("/health")
def get_gateway_health():
    """
    Returns latest full diagnostic snapshot for SmartBox Gateway:
    1. Connectivity Agent (Quectel Modem & SIM Card)
    2. DVR Health Agent (Storage, Recording & Channels)
    3. System Health Agent (CPU, RAM, SD Card)
    """
    snapshot = agent_manager.get_latest()
    return {
        "status": True,
        "data": snapshot,
    }


@router.post("/trigger")
def trigger_agent_inspection(current_user: User = Depends(get_current_user)):
    """
    Forces an immediate real-time inspection cycle across all 3 monitoring agents.
    """
    fresh_snapshot = agent_manager.collect_all()
    return {
        "status": True,
        "message": "Real-time diagnostic inspection completed",
        "data": fresh_snapshot,
    }


@router.get("/connectivity")
def get_connectivity_status():
    """
    Detailed Quectel Modem & SIM health.
    """
    return {
        "status": True,
        "data": agent_manager.connectivity_agent.inspect(),
    }


@router.get("/dvr")
def get_dvr_status():
    """
    Detailed DVR and CCTV status.
    """
    return {
        "status": True,
        "data": agent_manager.dvr_agent.inspect(),
    }


@router.get("/system")
def get_system_status():
    """
    Detailed SBC System Health (CPU, RAM, SD Card).
    """
    return {
        "status": True,
        "data": agent_manager.system_agent.inspect(),
    }


@router.get("/system-health-dashboard", response_model=SystemHealthDashboardResponse)
def get_system_health_dashboard(
    search: Optional[str] = Query(None, description="Cari Gateway ID atau Lokasi"),
    gateway_type: Optional[str] = Query(None, description="Filter tipe SmartBox"),
    status: Optional[str] = Query(None, description="Filter status gateway"),
    page: int = Query(1, ge=1, description="Nomor halaman"),
    page_size: int = Query(5, ge=1, le=100, description="Jumlah item per halaman"),
):
    """
    Fleet Dashboard Telemetry for System Health (2,000 SmartBoxes):
    - Summary metrics
    - Historical timeline charts
    - Filterable and paginated gateway list
    Delegates cleanly to SystemHealthService.
    """
    dashboard_data = system_health_service.get_full_dashboard(
        search=search,
        gateway_type=gateway_type,
        status=status,
        page=page,
        page_size=page_size,
    )
    return {
        "status": True,
        "data": dashboard_data,
    }


@router.get("/gateway/{gateway_id}/detail", response_model=GatewayDetailResponse)
def get_gateway_detail(gateway_id: str):
    """
    Detailed diagnostic snapshot for a specific gateway (for bottom detail panel).
    """
    detail = system_health_service.get_gateway_detail(gateway_id)
    return {
        "status": True,
        "data": detail,
    }


@router.get("/cellular-dashboard", response_model=CellularDashboardResponse)
def get_cellular_dashboard(
    search: Optional[str] = Query(None, description="Cari Gateway ID atau Lokasi"),
    gateway_type: Optional[str] = Query(None, description="Filter tipe SmartBox"),
    status: Optional[str] = Query(None, description="Filter status gateway: Online, Degraded, Offline"),
    provider: Optional[str] = Query(None, description="Filter provider SIM card"),
    page: int = Query(1, ge=1, description="Nomor halaman"),
    page_size: int = Query(5, ge=1, le=100, description="Jumlah item per halaman"),
):
    """
    Fleet Dashboard Telemetry for Cellular Connectivity (2,000 SmartBoxes):
    - Modem, SIM Card, Signal (RSRP), and Network status
    - CPU-Modem communication health breakdown
    - Filterable and paginated gateway list
    """
    dashboard_data = cellular_service.get_full_dashboard(
        search=search,
        gateway_type=gateway_type,
        status=status,
        provider=provider,
        page=page,
        page_size=page_size,
    )
    return {
        "status": True,
        "data": dashboard_data,
    }


@router.get("/cellular/gateway/{gateway_id}/detail", response_model=CellularGatewayDetailResponse)
def get_cellular_gateway_detail(gateway_id: str):
    """
    Detailed cellular connectivity telemetry for a specific gateway
    (CPU-Modem communication, Signal RSRP, Network & SIM details, Modem temperature).
    """
    detail_data = cellular_service.get_gateway_detail(gateway_id)
    return {
        "status": True,
        "data": detail_data,
    }


@router.get("/dvr-dashboard", response_model=DVRDashboardResponse)
def get_dvr_dashboard(
    search: Optional[str] = Query(None, description="Cari Gateway ID atau Lokasi"),
    gateway_type: Optional[str] = Query(None, description="Filter tipe SmartBox"),
    status: Optional[str] = Query(None, description="Filter status gateway/recording"),
    page: int = Query(1, ge=1, description="Nomor halaman"),
    page_size: int = Query(5, ge=1, le=100, description="Jumlah item per halaman"),
):
    """
    Fleet Dashboard Telemetry for DVR & Recording (2,000 SmartBoxes):
    - DVR/NVR status, Camera channels (Online, No Video, Offline)
    - Recording status, Storage usage timeline, and CPU-DVR communication
    - Filterable and paginated gateway list
    """
    dashboard_data = dvr_service.get_dashboard(
        search=search,
        gateway_type=gateway_type,
        status=status,
        page=page,
        page_size=page_size,
    )
    return {
        "status": True,
        "data": dashboard_data,
    }


@router.get("/dvr/gateway/{gateway_id}/detail", response_model=DVRGatewayDetailResponse)
def get_dvr_gateway_detail(gateway_id: str):
    """
    Detailed telemetry for a specific gateway DVR and Camera recording preview.
    """
    detail_data = dvr_service.get_gateway_detail(gateway_id)
    return {
        "status": True,
        "data": detail_data,
    }


@router.post("/dvr/gateway/{gateway_id}/reboot")
def reboot_dvr_gateway(gateway_id: str):
    """
    Publishes MQTT command 'REBOOT_NVR' to topic pqube/nms/{gateway_id}/command
    """
    from fastapi import HTTPException
    res = dvr_service.reboot_gateway_nvr(gateway_id)
    if not res.get("success"):
        raise HTTPException(status_code=500, detail=res.get("message"))
    return {
        "status": True,
        "data": res,
    }


@router.get("/reports/cellular", response_model=CellularReportResponse)
def get_cellular_report(
    search: Optional[str] = Query(None, description="Cari Gateway ID atau Lokasi"),
    gateway_type: Optional[str] = Query(None, description="Filter tipe SmartBox"),
    provider: Optional[str] = Query(None, description="Filter provider SIM card"),
    location: Optional[str] = Query(None, description="Filter lokasi/kota"),
    date_range: Optional[str] = Query(None, description="Filter rentang tanggal"),
    page: int = Query(1, ge=1, description="Nomor halaman"),
    page_size: int = Query(10, ge=1, le=100, description="Jumlah item per halaman"),
):
    """
    Historical Telemetry Report for Cellular Fleet (2,000 SmartBoxes):
    - Multi-metric historical SLAs: CPU-Modem communication, Network connection,
      RSRP, Modem Temperature, Trouble incident events.
    """
    report_data = cellular_report_service.get_report(
        search=search,
        gateway_type=gateway_type,
        provider=provider,
        location=location,
        date_range=date_range,
        page=page,
        page_size=page_size,
    )
    return {
        "status": True,
        "data": report_data,
    }


@router.get("/reports/cellular/export")
@router.get("/reports/cellular/export-excel")
def export_cellular_report_excel(
    search: Optional[str] = Query(None, description="Cari Gateway ID atau Lokasi"),
    gateway_type: Optional[str] = Query(None, description="Filter tipe SmartBox"),
    provider: Optional[str] = Query(None, description="Filter provider SIM card"),
    location: Optional[str] = Query(None, description="Filter lokasi/kota"),
    date_range: Optional[str] = Query(None, description="Filter rentang tanggal"),
):
    """
    Exports fleet cellular telemetry data to professional Excel (.xlsx) file.
    """
    try:
        excel_stream = cellular_report_service.export_excel(
            search=search,
            gateway_type=gateway_type,
            provider=provider,
            location=location,
            date_range=date_range,
        )
        safe_range = (date_range or "current").replace(" ", "_").replace("/", "-")
        filename = f"Cellular_SLA_Report_{safe_range}.xlsx"
        return Response(
            content=excel_stream.getvalue(),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except Exception as e:
        logger.error(f"Error exporting Cellular report Excel: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to generate Excel export: {str(e)}")


@router.get("/reports/cellular/gateway/{gateway_id}/export-pdf")
def export_cellular_detail_pdf(
    gateway_id: str,
    date_range: Optional[str] = Query(None, description="Filter rentang tanggal"),
):
    """
    Exports detailed Cellular performance report to PDF (.pdf) format.
    """
    try:
        detail = cellular_report_service.get_gateway_detail(gateway_id=gateway_id, date_range=date_range)
        loc_clean = re.sub(r"[^\w\s-]", "", detail.get("location") or gateway_id).strip().replace(" ", "_")
        safe_range = (date_range or "current").replace(" ", "_").replace("/", "-")
        filename = f"Cellular_Detail_{loc_clean}_{safe_range}.pdf"
        pdf_stream = cellular_report_service.export_detail_pdf(gateway_id=gateway_id, date_range=date_range)
        return Response(
            content=pdf_stream.getvalue(),
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except Exception as e:
        logger.error(f"Error exporting Cellular detail PDF: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to generate PDF export: {str(e)}")


@router.get("/reports/cellular/gateway/{gateway_id}/detail", response_model=CellularReportGatewayDetailResponse)
def get_cellular_report_gateway_detail(
    gateway_id: str,
    date_range: Optional[str] = Query(None, description="Filter rentang tanggal"),
):
    """
    Detailed performance telemetry for a specific gateway in Cellular Report.
    """
    detail_data = cellular_report_service.get_gateway_detail(gateway_id=gateway_id, date_range=date_range)
    return {
        "status": True,
        "data": detail_data,
    }


@router.get("/reports/dvr", response_model=DVRReportResponse)
def get_dvr_report(
    search: Optional[str] = Query(None, description="Cari Gateway ID atau Lokasi"),
    gateway_type: Optional[str] = Query(None, description="Filter tipe SmartBox"),
    dvr_brand: Optional[str] = Query(None, description="Filter merek DVR/NVR"),
    location: Optional[str] = Query(None, description="Filter lokasi/kota"),
    date_range: Optional[str] = Query(None, description="Filter rentang tanggal"),
    page: int = Query(1, ge=1, description="Nomor halaman"),
    page_size: int = Query(10, ge=1, le=100, description="Jumlah item per halaman"),
):
    """
    Historical Telemetry Report for DVR Fleet (2,000 SmartBoxes):
    - Multi-metric historical SLAs: CPU-DVR communication, Camera Channels,
      Recording status, Storage utilization, and trouble incident events.
    """
    report_data = dvr_report_service.get_report(
        search=search,
        gateway_type=gateway_type,
        dvr_brand=dvr_brand,
        location=location,
        date_range=date_range,
        page=page,
        page_size=page_size,
    )
    return {
        "status": True,
        "data": report_data,
    }


@router.get("/reports/dvr/export")
@router.get("/reports/dvr/export-excel")
def export_dvr_report_excel(
    search: Optional[str] = Query(None, description="Cari Gateway ID atau Lokasi"),
    gateway_type: Optional[str] = Query(None, description="Filter tipe SmartBox"),
    status: Optional[str] = Query(None, description="Filter status DVR/recording"),
    dvr_brand: Optional[str] = Query(None, description="Filter merek DVR/NVR"),
    location: Optional[str] = Query(None, description="Filter lokasi/kota"),
    date_range: Optional[str] = Query(None, description="Filter rentang tanggal"),
):
    """
    Exports fleet DVR telemetry data to professional Excel (.xlsx) file.
    """
    try:
        excel_stream = dvr_report_service.export_excel(
            search=search,
            gateway_type=gateway_type,
            status=status,
            dvr_brand=dvr_brand,
            location=location,
            date_range=date_range,
        )
        safe_range = (date_range or "current").replace(" ", "_").replace("/", "-")
        filename = f"DVR_Recording_Report_{safe_range}.xlsx"
        return Response(
            content=excel_stream.getvalue(),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except Exception as e:
        logger.error(f"Error exporting DVR report Excel: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to generate Excel export: {str(e)}")


@router.get("/reports/dvr/gateway/{gateway_id}/export-pdf")
def export_dvr_detail_pdf(
    gateway_id: str,
    date_range: Optional[str] = Query(None, description="Filter rentang tanggal"),
):
    """
    Exports detailed DVR performance report to PDF (.pdf) format.
    """
    try:
        detail = dvr_report_service.get_gateway_detail(gateway_id=gateway_id, date_range=date_range)
        loc_clean = re.sub(r"[^\w\s-]", "", detail.get("location") or gateway_id).strip().replace(" ", "_")
        safe_range = (date_range or "current").replace(" ", "_").replace("/", "-")
        filename = f"DVR_Detail_{loc_clean}_{safe_range}.pdf"
        pdf_stream = dvr_report_service.export_detail_pdf(gateway_id=gateway_id, date_range=date_range)
        return Response(
            content=pdf_stream.getvalue(),
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except Exception as e:
        logger.error(f"Error exporting DVR detail PDF: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to generate PDF export: {str(e)}")


@router.get("/reports/dvr/gateway/{gateway_id}/detail", response_model=DVRReportGatewayDetailResponse)
def get_dvr_report_gateway_detail(
    gateway_id: str,
    date_range: Optional[str] = Query(None, description="Filter rentang tanggal"),
):
    """
    Detailed performance telemetry for a specific gateway in DVR Report.
    """
    detail_data = dvr_report_service.get_gateway_detail(gateway_id=gateway_id, date_range=date_range)
    return {
        "status": True,
        "data": detail_data,
    }


@router.get("/reports/health", response_model=HealthReportResponse)
def get_health_report(
    search: Optional[str] = Query(None, description="Cari Gateway ID atau Lokasi"),
    gateway_type: Optional[str] = Query(None, description="Filter tipe SmartBox"),
    location: Optional[str] = Query(None, description="Filter lokasi/kota"),
    date_range: Optional[str] = Query(None, description="Filter rentang tanggal"),
    page: int = Query(1, ge=1, description="Nomor halaman"),
    page_size: int = Query(10, ge=1, le=100, description="Jumlah item per halaman"),
):
    """
    Historical Telemetry Report for System Health (2,000 SmartBoxes):
    - Multi-metric historical SLAs: CPU, RAM, SD Card usage, SD Card health/life,
      System Temperature spikes, Uptime duration & percentage, Trouble events.
    """
    try:
        report_data = health_report_service.get_report(
            search=search,
            gateway_type=gateway_type,
            location=location,
            date_range=date_range,
            page=page,
            page_size=page_size,
        )
        # Test validation explicitly
        validated = HealthReportResponse(status=True, data=report_data)
        return validated
    except Exception as e:
        import traceback
        err_msg = traceback.format_exc()
        try:
            with open("error_health_report.log", "w", encoding="utf-8") as f:
                f.write(err_msg)
        except Exception:
            pass
        logger.error(f"Error in get_health_report: {err_msg}")
        raise e


@router.get("/reports/health/export")
@router.get("/reports/health/export-excel")
def export_health_report_excel(
    search: Optional[str] = Query(None, description="Cari Gateway ID atau Lokasi"),
    gateway_type: Optional[str] = Query(None, description="Filter tipe SmartBox"),
    location: Optional[str] = Query(None, description="Filter lokasi/kota"),
    date_range: Optional[str] = Query(None, description="Filter rentang tanggal"),
):
    """
    Exports fleet System Health telemetry data to professional Excel (.xlsx) file.
    """
    try:
        excel_stream = health_report_service.export_excel(
            search=search,
            gateway_type=gateway_type,
            location=location,
            date_range=date_range,
        )
        safe_range = (date_range or "current").replace(" ", "_").replace("/", "-")
        filename = f"System_Health_Report_{safe_range}.xlsx"
        return Response(
            content=excel_stream.getvalue(),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except Exception as e:
        logger.error(f"Error exporting Health report Excel: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to generate Excel export: {str(e)}")


@router.get("/reports/health/gateway/{gateway_id}/export-pdf")
def export_health_detail_pdf(
    gateway_id: str,
    date_range: Optional[str] = Query(None, description="Filter rentang tanggal"),
):
    """
    Exports detailed System Health performance report to PDF (.pdf) format.
    """
    try:
        detail = health_report_service.get_gateway_detail(gateway_id=gateway_id, date_range=date_range)
        loc_clean = re.sub(r"[^\w\s-]", "", detail.get("location") or gateway_id).strip().replace(" ", "_")
        safe_range = (date_range or "current").replace(" ", "_").replace("/", "-")
        filename = f"Health_Detail_{loc_clean}_{safe_range}.pdf"
        pdf_stream = health_report_service.export_detail_pdf(gateway_id=gateway_id, date_range=date_range)
        return Response(
            content=pdf_stream.getvalue(),
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except Exception as e:
        logger.error(f"Error exporting Health detail PDF: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to generate PDF export: {str(e)}")


@router.get("/reports/health/gateway/{gateway_id}/detail", response_model=HealthReportGatewayDetailResponse)
def get_health_report_gateway_detail(
    gateway_id: str,
    date_range: Optional[str] = Query(None, description="Filter rentang tanggal"),
):
    """
    Detailed performance telemetry for a specific gateway in System Health Report.
    """
    detail_data = health_report_service.get_gateway_detail(gateway_id=gateway_id, date_range=date_range)
    return {
        "status": True,
        "data": detail_data,
    }


# =========================================================================
# GATEWAY INCIDENT & DOWNTIME ALERTS
# =========================================================================

@router.get("/incident-alerts")
def get_incident_alerts(
    device_id: Optional[str] = Query(None, description="Filter spesifik ID Gateway (e.g. gw-590c9399)"),
    category: Optional[str] = Query(None, description="Filter kategori: POWER, CELLULAR, CCTV_NVR, STORAGE, SYSTEM, NETWORK"),
    severity: Optional[str] = Query(None, description="Filter tingkat keparahan: CRITICAL, HIGH, WARNING, INFO"),
    status: Optional[str] = Query(None, description="Filter status: ACTIVE, RESOLVED"),
    search: Optional[str] = Query(None, description="Pencarian teks bebas (ID, Lokasi, Judul, Pesan)"),
    limit: int = Query(50, ge=1, le=200, description="Jumlah data per halaman"),
    offset: int = Query(0, ge=0, description="Offset data untuk pagination"),
    db: Session = Depends(get_db),
):
    """
    Mengambil riwayat kejadian/incident alert gateway (drop tegangan listrik, mati mendadak,
    kartu SIM dicabut, kabel LAN terputus, kamera offline, dsb.) dengan penjelasan dan rekomendasi yang mudah dipahami.
    """
    result = incident_alert_service.get_incident_alerts(
        db=db,
        device_id=device_id,
        category=category,
        severity=severity,
        status=status,
        search=search,
        limit=limit,
        offset=offset,
    )
    return result


@router.get("/incident-alerts/summary")
def get_incident_alerts_summary(
    device_id: Optional[str] = Query(None, description="Filter ringkasan untuk spesifik ID Gateway"),
    db: Session = Depends(get_db),
):
    """
    Mengambil ringkasan statistik alert dan kejadian insiden (total, active, critical, warning, power, cellular, cctv).
    """
    stats = incident_alert_service.get_summary_stats(db=db, device_id=device_id)
    return {
        "status": True,
        "data": stats,
    }


