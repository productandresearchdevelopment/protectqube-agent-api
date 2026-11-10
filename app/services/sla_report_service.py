import os
import json
import time
import io
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)


class SLAReportService:
    """
    Fleet-wide Service Level Agreement (SLA) & Availability Report Service.
    Aggregates multi-dimensional uptime & performance metrics:
    - Overall SLA (%)
    - Gateway Hardware Uptime SLA (%)
    - Cellular Connectivity SLA (%)
    - DVR Video Surveillance Recording SLA (%)
    - Trouble Outage Events & Downtime Duration
    """

    def __init__(self):
        self._live_gateways: Dict[str, Dict[str, Any]] = {}
        self._load_persisted_telemetry()

    def _cache_path(self) -> str:
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        return os.path.join(base_dir, "telemetry_cache.json")

    def _load_persisted_telemetry(self):
        """Loads cached real telemetry snapshots from PostgreSQL database (primary) or disk cache (fallback)"""
        loaded_from_db = False
        try:
            from app.core.database import SessionLocal
            from app.models.base_models import GatewayTelemetryHistory
            db = SessionLocal()
            try:
                query = db.query(GatewayTelemetryHistory)
                if hasattr(GatewayTelemetryHistory, "deleted_at"):
                    query = query.filter(GatewayTelemetryHistory.deleted_at.is_(None))
                latest_records = (
                    query.distinct(GatewayTelemetryHistory.device_id)
                    .order_by(GatewayTelemetryHistory.device_id, GatewayTelemetryHistory.recorded_at.desc())
                    .all()
                )
                for latest in latest_records:
                    if latest and latest.raw_payload:
                        payload = dict(latest.raw_payload)
                        if latest.recorded_at:
                            WIB = timezone(timedelta(hours=7))
                            t_wib = latest.recorded_at.replace(tzinfo=timezone.utc).astimezone(WIB) if latest.recorded_at.tzinfo is None else latest.recorded_at.astimezone(WIB)
                            payload["recorded_at"] = t_wib.strftime("%Y-%m-%d %H:%M:%S")
                        if latest.location:
                            payload["location"] = latest.location
                            payload["location_name"] = latest.location
                        self.update_from_telemetry(payload, compute_sla=False)
                if self._live_gateways:
                    loaded_from_db = True
                    logger.info(f"SLAReportService: Hydrated {len(self._live_gateways)} gateway(s) from PostgreSQL database")
            finally:
                db.close()
        except Exception as dbe:
            logger.debug(f"Could not hydrate gateways from database: {dbe}")

        if not loaded_from_db:
            cache_file = self._cache_path()
            if os.path.exists(cache_file):
                try:
                    with open(cache_file, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    if isinstance(data, list):
                        for item in data:
                            if isinstance(item, dict):
                                self.update_from_telemetry(item, compute_sla=False)
                    elif isinstance(data, dict):
                        self.update_from_telemetry(data, compute_sla=False)
                    logger.info(f"SLAReportService: Loaded {len(self._live_gateways)} live gateway(s)")
                except Exception as e:
                    logger.warning(f"Could not load telemetry cache for SLA report: {e}")

    def reload_telemetry_cache(self):
        """Flushes in-memory gateway states and reloads fresh telemetry from PostgreSQL."""
        self._live_gateways.clear()
        self._load_persisted_telemetry()
        logger.info(f"SLAReportService: Telemetry reloaded. Active live gateways: {len(self._live_gateways)}")

    def update_from_telemetry(self, nms_payload: Dict[str, Any], compute_sla: bool = False):
        """Ingests live MQTT telemetry and caches device reference for SLA report."""
        device_id = nms_payload.get("device_id")
        if not device_id:
            return

        gw_sys = nms_payload.get("gateway_system", {})
        hw = gw_sys.get("hardware", {})

        box_type = "SmartBox Hitam"
        hw_type = (hw.get("type") or hw.get("model") or "").lower()
        if "210" in hw_type or "white" in hw_type or "dsgw-210" in hw_type:
            box_type = "SmartBox Putih"

        location_name = (
            nms_payload.get("location_name")
            or nms_payload.get("location")
            or nms_payload.get("site_name")
            or nms_payload.get("site_info", {}).get("location_name")
            or f"Gateway {device_id}"
        )

        last_update = nms_payload.get("datetime_utc7") or nms_payload.get("recorded_at") or "-"

        self._live_gateways[device_id] = {
            "device_id": device_id,
            "id": device_id,
            "location": location_name,
            "type": box_type,
            "hardware_model": hw.get("model") or hw.get("type") or "Raspberry Pi 3B+",
            "last_update": last_update,
            "raw": nms_payload,
        }

    def get_report(
        self,
        search: Optional[str] = None,
        gateway_type: Optional[str] = None,
        sla_status: Optional[str] = None,
        date_range: Optional[str] = None,
        page: int = 1,
        page_size: int = 50,
    ) -> Dict[str, Any]:
        """
        Calculates and paginates comprehensive SLA compliance report.
        """
        from app.services.sla_calculator_service import sla_calculator_service

        all_items = list(self._live_gateways.values())

        # Filtering
        filtered: List[Dict[str, Any]] = []
        for g in all_items:
            # Search filter
            if search:
                s_lower = search.lower().strip()
                if s_lower not in g["location"].lower() and s_lower not in g["device_id"].lower():
                    continue

            # Type filter
            if gateway_type and gateway_type.lower() not in ["all", "all types"]:
                if gateway_type.lower() not in g["type"].lower():
                    continue

            filtered.append(g)

        # Sort alphabetically by location
        filtered.sort(key=lambda x: x["location"].lower())

        total_items = len(filtered)
        total_pages = max(1, (total_items + page_size - 1) // page_size)
        cur_page = max(1, min(page, total_pages))

        start_idx = (cur_page - 1) * page_size
        end_idx = min(start_idx + page_size, total_items)
        page_items = filtered[start_idx:end_idx]

        # Calculate Batch SLA for current page
        page_dev_ids = [item["device_id"] for item in page_items]
        batch_sla = sla_calculator_service.get_fast_batch_sla_summary(page_dev_ids, date_range_str=date_range)

        report_gateways: List[Dict[str, Any]] = []
        for idx, item in enumerate(page_items):
            dev_id = item["device_id"]
            sla_data = batch_sla.get(dev_id, {})

            gw_sla = float(sla_data.get("gateway_sla_pct", 100.0))
            cel_sla = float(sla_data.get("cellular_sla_pct", 100.0))
            dvr_sla = float(sla_data.get("dvr_sla_pct", 100.0))

            # Composite overall SLA %
            overall_sla = round((gw_sla + cel_sla + dvr_sla) / 3.0, 2)

            # SLA Status filter check if applied
            if sla_status:
                s_stat = sla_status.lower().strip()
                if s_stat in ["meet", "meet sla", "good"] and overall_sla < 99.0:
                    continue
                if s_stat in ["breach", "breach sla", "warning", "critical"] and overall_sla >= 99.0:
                    continue

            report_gateways.append({
                "no": start_idx + idx + 1,
                "id": dev_id,
                "location": item["location"],
                "type": item["type"],
                "hardware_model": item.get("hardware_model", "-"),
                "status": "Online",
                "overall_sla_pct": overall_sla,
                "gateway_sla_pct": gw_sla,
                "gateway_uptime_str": sla_data.get("gateway_uptime_str", "0m"),
                "gateway_offline_str": sla_data.get("gateway_offline_str", "0m"),
                "cellular_sla_pct": cel_sla,
                "cellular_uptime_str": sla_data.get("cellular_uptime_str", "0m"),
                "cellular_offline_str": sla_data.get("cellular_offline_str", "0m"),
                "dvr_sla_pct": dvr_sla,
                "dvr_uptime_str": sla_data.get("dvr_uptime_str", "0m"),
                "dvr_offline_str": sla_data.get("dvr_offline_str", "0m"),
                "events_count": int(sla_data.get("events_count", 0)),
                "last_update": item.get("last_update", "-"),
            })

        # Summary KPIs
        meet_sla_cnt = sum(1 for g in report_gateways if g["overall_sla_pct"] >= 99.0)
        breach_sla_cnt = len(report_gateways) - meet_sla_cnt
        avg_overall = round(sum(g["overall_sla_pct"] for g in report_gateways) / max(1, len(report_gateways)), 2)
        avg_gw = round(sum(g["gateway_sla_pct"] for g in report_gateways) / max(1, len(report_gateways)), 2)
        avg_cel = round(sum(g["cellular_sla_pct"] for g in report_gateways) / max(1, len(report_gateways)), 2)
        avg_dvr = round(sum(g["dvr_sla_pct"] for g in report_gateways) / max(1, len(report_gateways)), 2)

        hitam_items = [g for g in report_gateways if "hitam" in g["type"].lower()]
        putih_items = [g for g in report_gateways if "putih" in g["type"].lower()]
        hitam_sla = round(sum(g["overall_sla_pct"] for g in hitam_items) / max(1, len(hitam_items)), 2) if hitam_items else 100.0
        putih_sla = round(sum(g["overall_sla_pct"] for g in putih_items) / max(1, len(putih_items)), 2) if putih_items else 100.0

        summary = {
            "total_gateways": total_items,
            "avg_overall_sla": avg_overall,
            "avg_gateway_sla": avg_gw,
            "avg_cellular_sla": avg_cel,
            "avg_dvr_sla": avg_dvr,
            "meet_sla_count": meet_sla_cnt,
            "breach_sla_count": breach_sla_cnt,
            "meet_sla_percent": round((meet_sla_cnt / max(1, len(report_gateways))) * 100.0, 1),
            "smartbox_hitam_sla": hitam_sla,
            "smartbox_putih_sla": putih_sla,
        }

        pagination = {
            "total_items": total_items,
            "total_pages": total_pages,
            "current_page": cur_page,
            "page_size": page_size,
            "showing_start": start_idx + 1 if total_items > 0 else 0,
            "showing_end": end_idx,
        }

        return {
            "gateways": report_gateways,
            "summary": summary,
            "pagination": pagination,
        }

    def export_excel(
        self,
        search: Optional[str] = None,
        gateway_type: Optional[str] = None,
        sla_status: Optional[str] = None,
        date_range: Optional[str] = None,
    ) -> io.BytesIO:
        """Exports SLA compliance report to professional Excel spreadsheet (.xlsx)"""
        import openpyxl
        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

        report = self.get_report(
            search=search,
            gateway_type=gateway_type,
            sla_status=sla_status,
            date_range=date_range,
            page=1,
            page_size=5000,
        )

        gateways = report.get("gateways", [])
        summary = report.get("summary", {})

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Report SLA"
        ws.views.sheetView[0].showGridLines = True

        # Styles
        title_font = Font(name="Segoe UI", size=15, bold=True, color="1E293B")
        sub_font = Font(name="Segoe UI", size=9, color="64748B")
        header_font = Font(name="Segoe UI", size=10, bold=True, color="FFFFFF")
        header_fill = PatternFill(start_color="0F172A", end_color="0F172A", fill_type="solid")
        row_font = Font(name="Segoe UI", size=9)
        kpi_label_font = Font(name="Segoe UI", size=8, color="64748B")
        kpi_val_font = Font(name="Segoe UI", size=13, bold=True, color="0F172A")
        kpi_fill = PatternFill(start_color="F8FAFC", end_color="F8FAFC", fill_type="solid")

        thin_border = Border(
            left=Side(style="thin", color="E2E8F0"),
            right=Side(style="thin", color="E2E8F0"),
            top=Side(style="thin", color="E2E8F0"),
            bottom=Side(style="thin", color="E2E8F0")
        )

        # Title
        ws["A1"] = "PROTECTQUBE AIOPS - FLEET SLA COMPLIANCE REPORT"
        ws["A1"].font = title_font
        ws["A2"] = f"Generated on: {datetime.now().strftime('%d %b %Y %H:%M:%S')} WIB | Period: {date_range or 'Current Month'}"
        ws["A2"].font = sub_font

        # Summary Cards row 4-5
        kpis = [
            ("TOTAL GATEWAYS", f"{summary.get('total_gateways', 0)} Units", "A", "B"),
            ("OVERALL FLEET SLA", f"{summary.get('avg_overall_sla', 100.0)}%", "C", "D"),
            ("GATEWAY HARDWARE SLA", f"{summary.get('avg_gateway_sla', 100.0)}%", "E", "F"),
            ("CELLULAR NETWORK SLA", f"{summary.get('avg_cellular_sla', 100.0)}%", "G", "H"),
            ("DVR RECORDING SLA", f"{summary.get('avg_dvr_sla', 100.0)}%", "I", "J"),
        ]

        for label, val, c1, c2 in kpis:
            ws.merge_cells(f"{c1}4:{c2}4")
            ws[f"{c1}4"] = label
            ws[f"{c1}4"].font = kpi_label_font
            ws[f"{c1}4"].fill = kpi_fill
            ws[f"{c1}4"].alignment = Alignment(horizontal="center")

            ws.merge_cells(f"{c1}5:{c2}5")
            ws[f"{c1}5"] = val
            ws[f"{c1}5"].font = kpi_val_font
            ws[f"{c1}5"].fill = kpi_fill
            ws[f"{c1}5"].alignment = Alignment(horizontal="center")

        # Table Headers row 7
        headers = [
            "No", "Device ID", "Location", "SmartBox Type", "Hardware Model",
            "Overall SLA (%)", "Gateway SLA (%)", "Gateway Uptime", "Gateway Outage",
            "Cellular SLA (%)", "Cellular Uptime", "Cellular Outage",
            "DVR SLA (%)", "DVR Uptime", "DVR Outage", "Trouble Events", "Last Update"
        ]

        for col_idx, h in enumerate(headers, 1):
            cell = ws.cell(row=7, column=col_idx, value=h)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = Alignment(horizontal="center", vertical="center")
            cell.border = thin_border

        # Table Rows
        for r_idx, g in enumerate(gateways, 8):
            row_vals = [
                g.get("no", r_idx - 7),
                g.get("id"),
                g.get("location"),
                g.get("type"),
                g.get("hardware_model"),
                f"{g.get('overall_sla_pct', 100.0)}%",
                f"{g.get('gateway_sla_pct', 100.0)}%",
                g.get("gateway_uptime_str"),
                g.get("gateway_offline_str"),
                f"{g.get('cellular_sla_pct', 100.0)}%",
                g.get("cellular_uptime_str"),
                g.get("cellular_offline_str"),
                f"{g.get('dvr_sla_pct', 100.0)}%",
                g.get("dvr_uptime_str"),
                g.get("dvr_offline_str"),
                g.get("events_count", 0),
                g.get("last_update", "-"),
            ]
            for c_idx, val in enumerate(row_vals, 1):
                c = ws.cell(row=r_idx, column=c_idx, value=val)
                c.font = row_font
                c.border = thin_border
                if c_idx in [1, 2, 4, 16]:
                    c.alignment = Alignment(horizontal="center")
                elif c_idx in [6, 7, 10, 13]:
                    c.alignment = Alignment(horizontal="right")
                else:
                    c.alignment = Alignment(horizontal="left")

        # Column widths
        for col in ws.columns:
            max_len = max(len(str(cell.value or "")) for cell in col)
            col_letter = openpyxl.utils.get_column_letter(col[0].column)
            ws.column_dimensions[col_letter].width = max(max_len + 3, 11)

        output = io.BytesIO()
        wb.save(output)
        output.seek(0)
        return output


sla_report_service = SLAReportService()
