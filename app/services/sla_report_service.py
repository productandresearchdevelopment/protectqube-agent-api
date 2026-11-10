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
    - Location, Type, Customer ("-")
    - Smartbox Device: Status (Online/Offline), Uptime %
    - DVR Surveillance: Status (Working/Not Working), Uptime %
    - Network (Cellular): Status (Working/Not Working), Uptime %
    - Overall SLA: Combined Uptime % (Avg of 3), Failure Rate % (100% - SLA)
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

        box_type = "Hitam"
        hw_type = (hw.get("type") or hw.get("model") or "").lower()
        if "210" in hw_type or "white" in hw_type or "dsgw-210" in hw_type:
            box_type = "Putih"

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
            "customer": "-",
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
        from app.services.sla_calculator_service import sla_calculator_service, get_default_period_str
        from app.services.system_health_service import system_health_service
        from app.services.dvr_service import dvr_service
        from app.services.cellular_service import cellular_service
        from app.services.health_report_service import health_report_service
        from app.services.dvr_report_service import dvr_report_service
        from app.services.cellular_report_service import cellular_report_service

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

        # 1. Sync real-time freshness across all 3 domain services right now
        try:
            system_health_service._sync_freshness()
            dvr_service._sync_freshness()
            cellular_service._sync_freshness()
        except Exception as sync_err:
            logger.debug(f"Freshness sync error: {sync_err}")

        # Preload incident alerts for all devices on this active page in one single SQL query
        page_dev_ids = [item["device_id"] for item in page_items]
        req_dr = date_range or get_default_period_str()
        preloaded_alerts = sla_calculator_service.preload_alerts_for_devices(page_dev_ids, date_range_str=req_dr)

        report_gateways: List[Dict[str, Any]] = []
        for idx, item in enumerate(page_items):
            dev_id = item["device_id"]
            live_pl = item.get("raw") or health_report_service._live_gateways.get(dev_id, {}).get("raw_payload")

            # Calculate authentic domain SLA using preloaded alerts (100% identical to Health, DVR, & Cellular reports)
            sla = sla_calculator_service.calculate_device_sla(
                device_id=dev_id,
                live_payload=live_pl,
                date_range_str=req_dr,
                skip_history_rows=True,
                preloaded_alerts=preloaded_alerts.get(dev_id, []),
            )

            # 1. Smartbox Uptime (Persis kolom UPTIME di Report Health)
            gw_sla = float(sla.get("gateway_sla_pct", 100.0))
            sb_dur = str(sla.get("gateway_uptime_str") or "0m")

            # 2. DVR Uptime (Persis kolom UPTIME di Report DVR: (CPU-DVR + Cam + Rec) / 3)
            cpu_dvr_sr = float(sla.get("cpu_dvr_success_rate", sla.get("gateway_sla_pct", 100.0)))
            rec_sr = float(sla.get("dvr_sla_pct", 100.0))
            d_entry = dvr_report_service._live_gateways.get(dev_id, {})
            d_item = d_entry.get("report_item") or {}
            cam_tot = d_item.get("kamera_total", 0)
            cam_on = d_item.get("kamera_online", 0)
            cam_sr = round((cam_on / max(1, cam_tot)) * 100.0, 1) if cam_tot > 0 else 100.0
            dvr_sla = round((cpu_dvr_sr + cam_sr + rec_sr) / 3.0, 1)
            dvr_dur = str(sla.get("dvr_uptime_str") or d_item.get("cpu_dvr_uptime") or "0m")

            # 3. Network / Cellular Uptime (Persis kolom UPTIME di Report Cellular: (CPU-Modem + Network) / 2)
            cpu_modem_sr = float(sla.get("gateway_sla_pct", 100.0))
            net_conn_sr = float(sla.get("cellular_sla_pct", 100.0))
            cel_sla = round((cpu_modem_sr + net_conn_sr) / 2.0, 1)
            cel_dur = str(sla.get("cellular_uptime_str") or "0m")

            # Composite overall SLA % = average of Smartbox, DVR, Cellular
            sla_uptime = round((gw_sla + cel_sla + dvr_sla) / 3.0, 2)
            sla_fail_rate = round(max(0.0, 100.0 - sla_uptime), 2)

            # REAL-TIME / CURRENT STATUS (Data status saat ini, bukan akumulasi per bulan)
            live_health = system_health_service._live_gateways.get(dev_id, {})
            live_dvr = dvr_service._live_gateways.get(dev_id, {})
            live_cel = cellular_service._live_gateways.get(dev_id, {})

            # 1. Real-time Smartbox Status
            sb_live_status = (
                live_health.get("table_item", {}).get("status")
                or live_health.get("status")
                or "Offline"
            )
            is_sb_online = (sb_live_status == "Online")

            # 2. Status Cascade Rule:
            # Jika Smartbox Offline -> DVR & Network otomatis Offline
            if not is_sb_online:
                smartbox_status = "Offline"
                dvr_status = "Offline"
                network_status = "Offline"
            else:
                smartbox_status = "Online"

                # Real-time DVR Status saat Smartbox Online
                dvr_live_stat = (
                    live_dvr.get("table_item", {}).get("status")
                    or live_dvr.get("status")
                    or "Offline"
                )
                rec_stat = (
                    live_dvr.get("table_item", {}).get("recording_status")
                    or live_dvr.get("health", {}).get("recording_status")
                    or ""
                ).lower()
                is_dvr_working = (dvr_live_stat == "Online")
                if "no video" in rec_stat and ("0/" in rec_stat or "offline" in rec_stat):
                    is_dvr_working = False
                dvr_status = "Online" if is_dvr_working else "Offline"

                # Real-time Network / Cellular Status saat Smartbox Online
                cel_live_stat = (
                    live_cel.get("item", {}).get("status")
                    or live_cel.get("status")
                    or "Offline"
                )
                sim_stat = (
                    live_cel.get("item", {}).get("sim_status")
                    or live_cel.get("detail", {}).get("modem_health", {}).get("sim_status")
                    or ""
                ).lower()
                is_net_working = (cel_live_stat == "Online")
                if "tidak terdeteksi" in sim_stat or "error" in sim_stat or "removed" in sim_stat:
                    is_net_working = False
                network_status = "Online" if is_net_working else "Offline"

            # SLA Status filter check if applied
            if sla_status:
                s_stat = sla_status.lower().strip()
                if s_stat in ["meet", "meet sla", "good"] and sla_uptime < 99.0:
                    continue
                if s_stat in ["breach", "breach sla", "warning", "critical"] and sla_uptime >= 99.0:
                    continue

            report_gateways.append({
                "no": start_idx + idx + 1,
                "id": dev_id,
                "location": item["location"],
                "type": item["type"],
                "customer": item.get("customer", "-"),
                "hardware_model": item.get("hardware_model", "-"),

                # Smartbox
                "smartbox_status": smartbox_status,
                "smartbox_uptime_pct": round(gw_sla, 1),
                "smartbox_uptime_duration": sb_dur,

                # DVR
                "dvr_status": dvr_status,
                "dvr_uptime_pct": round(dvr_sla, 1),
                "dvr_uptime_duration": dvr_dur,

                # Network
                "network_status": network_status,
                "network_uptime_pct": round(cel_sla, 1),
                "network_uptime_duration": cel_dur,

                # SLA
                "sla_uptime_pct": sla_uptime,
                "sla_failure_rate_pct": sla_fail_rate,

                # Legacy & detail metadata
                "overall_sla_pct": sla_uptime,
                "gateway_sla_pct": gw_sla,
                "cellular_sla_pct": cel_sla,
                "dvr_sla_pct": dvr_sla,
                "gateway_uptime_str": sb_dur,
                "gateway_offline_str": str(sla.get("gateway_offline_str", "0m")),
                "cellular_uptime_str": cel_dur,
                "cellular_offline_str": str(sla.get("cellular_offline_str", "0m")),
                "dvr_uptime_str": dvr_dur,
                "dvr_offline_str": str(sla.get("dvr_offline_str", "0m")),
                "events_count": len(sla.get("trouble_events", [])),
                "last_update": item.get("last_update", "-"),
            })

        # Summary KPIs across the active period
        meet_sla_cnt = sum(1 for g in report_gateways if g["sla_uptime_pct"] >= 99.0)
        breach_sla_cnt = len(report_gateways) - meet_sla_cnt
        avg_sla_up = round(sum(g["sla_uptime_pct"] for g in report_gateways) / max(1, len(report_gateways)), 2)
        avg_sla_fail = round(sum(g["sla_failure_rate_pct"] for g in report_gateways) / max(1, len(report_gateways)), 2)
        avg_sb = round(sum(g["smartbox_uptime_pct"] for g in report_gateways) / max(1, len(report_gateways)), 2)
        avg_dvr = round(sum(g["dvr_uptime_pct"] for g in report_gateways) / max(1, len(report_gateways)), 2)
        avg_net = round(sum(g["network_uptime_pct"] for g in report_gateways) / max(1, len(report_gateways)), 2)

        hitam_items = [g for g in report_gateways if "hitam" in g["type"].lower()]
        putih_items = [g for g in report_gateways if "putih" in g["type"].lower()]
        hitam_sla = round(sum(g["sla_uptime_pct"] for g in hitam_items) / max(1, len(hitam_items)), 2) if hitam_items else 100.0
        putih_sla = round(sum(g["sla_uptime_pct"] for g in putih_items) / max(1, len(putih_items)), 2) if putih_items else 100.0

        # 1. Total Locations
        tot_locations = len(set(g.get("location") for g in all_items if g.get("location")))

        # 2. Device Online & Offline counts
        dev_online = 0
        dev_offline = 0
        for g in all_items:
            did = g["device_id"]
            lh = system_health_service._live_gateways.get(did, {})
            st = lh.get("table_item", {}).get("status") or lh.get("status") or "Offline"
            if st == "Online":
                dev_online += 1
            else:
                dev_offline += 1

        # 3. Total Camera (Online & Offline)
        cam_tot = 0
        cam_on = 0
        for did, g in dvr_report_service._live_gateways.items():
            item_d = g.get("report_item", {})
            cam_tot += int(item_d.get("kamera_total", 0))
            cam_on += int(item_d.get("kamera_online", 0))
        cam_off = max(0, cam_tot - cam_on)

        # 4. Total Storage (Total Capacity & Used TB)
        stor_tot_tb = 0.0
        stor_used_tb = 0.0
        for did, g in dvr_report_service._live_gateways.items():
            item_d = g.get("report_item", {})
            st_str = str(item_d.get("storage_kapasitas", "0"))
            if "TB" in st_str:
                try:
                    cap = float(st_str.replace("TB", "").strip())
                    stor_tot_tb += cap
                    pct = float(item_d.get("storage_terpakai_pct", 85)) / 100.0
                    stor_used_tb += (cap * pct)
                except Exception:
                    pass

        # 7 & 8. Incidents, MTTR, and MTBF from Database
        tot_incidents = 0
        tot_downtime_minutes = 0.0
        obs_hours = 240.0
        try:
            from app.core.database import SessionLocal
            from app.models.base_models import GatewayIncidentAlert
            from sqlalchemy import func
            from datetime import datetime, timezone, timedelta
            start_dt, end_dt = sla_calculator_service._parse_date_range(req_dr)
            if not start_dt:
                WIB = timezone(timedelta(hours=7))
                now_wib = datetime.now(timezone.utc).astimezone(WIB)
                start_dt = datetime(now_wib.year, now_wib.month, 1, 0, 0, 0, tzinfo=WIB)
                end_dt = now_wib
            s_utc = start_dt.astimezone(timezone.utc) if start_dt.tzinfo else (start_dt - timedelta(hours=7))
            e_utc = end_dt.astimezone(timezone.utc) if end_dt.tzinfo else (end_dt - timedelta(hours=7))
            obs_hours = max(1.0, (end_dt - start_dt).total_seconds() / 3600.0)

            db = SessionLocal()
            tot_incidents = db.query(func.count(GatewayIncidentAlert.id)).filter(
                GatewayIncidentAlert.start_time >= s_utc,
                GatewayIncidentAlert.start_time <= e_utc
            ).scalar() or 0

            tot_downtime_minutes = db.query(func.sum(GatewayIncidentAlert.duration_minutes)).filter(
                GatewayIncidentAlert.start_time >= s_utc,
                GatewayIncidentAlert.start_time <= e_utc
            ).scalar() or 0.0
            db.close()
        except Exception as dbe:
            logger.debug(f"Could not load incident alerts summary: {dbe}")

        # MTTR (Mean Time To Repair) = Total Downtime / Total Incidents
        mttr_min = round(tot_downtime_minutes / max(1, tot_incidents), 1) if tot_incidents > 0 else 0.0
        if mttr_min >= 60.0:
            mttr_formatted = f"{round(mttr_min / 60.0, 1)} jam"
        else:
            mttr_formatted = f"{int(round(mttr_min))} menit"

        # MTBF (Mean Time Between Failures) = Total Uptime / Total Incidents
        total_fleet_uptime_hours = max(0.0, (obs_hours * max(1, total_items)) - (tot_downtime_minutes / 60.0))
        mtbf_hrs = round(total_fleet_uptime_hours / max(1, tot_incidents), 1) if tot_incidents > 0 else round(obs_hours, 1)
        if mtbf_hrs >= 1.0:
            mtbf_formatted = f"{int(round(mtbf_hrs))} jam"
        else:
            mtbf_formatted = f"{int(round(mtbf_hrs * 60))} menit"

        summary = {
            "total_gateways": total_items,
            "total_locations": tot_locations,
            "device_online_count": dev_online,
            "device_offline_count": dev_offline,
            "total_cameras": cam_tot,
            "cameras_online": cam_on,
            "cameras_offline": cam_off,
            "total_storage_tb": round(stor_tot_tb, 1),
            "storage_used_tb": round(stor_used_tb, 1),
            "avg_sla_uptime": avg_sla_up,
            "avg_sla_failure_rate": avg_sla_fail,
            "avg_smartbox_uptime": avg_sb,
            "avg_dvr_uptime": avg_dvr,
            "avg_network_uptime": avg_net,
            "total_incidents": tot_incidents,
            "mttr_minutes": mttr_min,
            "mttr_formatted": mttr_formatted,
            "mtbf_hours": mtbf_hrs,
            "mtbf_formatted": mtbf_formatted,
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

    def get_gateway_detail(self, gateway_id: str, date_range: Optional[str] = None) -> Dict[str, Any]:
        """
        Detailed SLA performance telemetry for a specific gateway:
        - Device profile & metadata
        - Individual and combined SLA metrics (Smartbox, DVR, Cellular)
        - SLA tolerance, target (99.5%), downtime analysis
        - Multi-day timeline / Daily SLA breakdown
        - Chronological trouble events list across all domains
        """
        from app.services.sla_calculator_service import sla_calculator_service, get_default_period_str
        from app.services.system_health_service import system_health_service
        from app.services.dvr_service import dvr_service
        from app.services.cellular_service import cellular_service
        from app.services.health_report_service import health_report_service
        from app.services.dvr_report_service import dvr_report_service
        from app.services.cellular_report_service import cellular_report_service

        target_g = None
        cleaned_id = gateway_id.strip().lower()

        for gid, data in self._live_gateways.items():
            g_low = gid.strip().lower()
            if g_low == cleaned_id or cleaned_id in g_low or g_low in cleaned_id:
                target_g = data
                break

        if not target_g and self._live_gateways:
            target_g = next(iter(self._live_gateways.values()))

        req_period = date_range or get_default_period_str()
        dev_id = target_g.get("device_id", gateway_id) if target_g else gateway_id
        location = target_g.get("location", f"Gateway {gateway_id}") if target_g else f"Gateway {gateway_id}"
        gw_type = target_g.get("type", "Hitam") if target_g else "Hitam"
        customer = target_g.get("customer", "-") if target_g else "-"
        hw_model = target_g.get("hardware_model", "Dusun DSGW-10") if target_g else "Dusun DSGW-10"

        # Calculate SLA details with alerts and daily breakdown
        sla = sla_calculator_service.calculate_device_sla(
            dev_id,
            date_range_str=req_period,
            skip_history_rows=False,
        )

        # 1. Fetch domain-specific uptime percentages from the domain report services
        h_pct = 100.0
        h_dur = "0m"
        h_status = "Online"
        h_live = system_health_service._live_gateways.get(dev_id, {})
        h_status = h_live.get("table_item", {}).get("status") or h_live.get("status") or "Online"
        h_item = health_report_service._live_gateways.get(dev_id)
        if h_item:
            try:
                h_sla = sla_calculator_service.calculate_device_sla(dev_id, date_range_str=req_period, skip_history_rows=True)
                h_pct = float(h_sla.get("gateway_sla_pct", 100.0))
                h_dur = h_sla.get("gateway_uptime_str", "0m")
            except Exception:
                pass

        d_pct = 100.0
        d_dur = "0m"
        d_status = "Online"
        d_live = dvr_report_service._live_gateways.get(dev_id, {})
        d_status = d_live.get("report_item", {}).get("dvr_status") or "Online"
        d_item = dvr_report_service._live_gateways.get(dev_id)
        if d_item:
            try:
                d_detail = dvr_report_service.get_gateway_detail(dev_id, date_range=req_period)
                rec_up_str = d_detail.get("rec_uptime_pct", "100.0%").replace("%", "").strip()
                d_pct = float(rec_up_str) if rec_up_str else 100.0
                d_dur = d_detail.get("rec_uptime", "0m")
            except Exception:
                pass

        c_pct = 100.0
        c_dur = "0m"
        c_status = "Online"
        c_live = cellular_report_service._live_gateways.get(dev_id, {})
        c_status = c_live.get("report_item", {}).get("network_status") or "Online"
        c_item = cellular_report_service._live_gateways.get(dev_id)
        if c_item:
            try:
                c_detail = cellular_report_service.get_gateway_detail(dev_id, date_range=req_period)
                c_pct = float(c_detail.get("uptime_pct", 100.0))
                c_dur = c_detail.get("uptime_duration", "0m")
            except Exception:
                pass

        # Combined SLA
        sla_uptime = round((h_pct + d_pct + c_pct) / 3.0, 2)
        sla_failure = round(max(0.0, 100.0 - sla_uptime), 2)
        meets_sla = sla_uptime >= 99.5

        # Format trouble events
        trouble_events = sla.get("trouble_events", [])
        daily_breakdown = sla.get("daily_breakdown", [])
        daily_summary = sla.get("daily_summary")

        return {
            "id": dev_id,
            "location": location,
            "type": gw_type,
            "customer": customer,
            "hardware_model": hw_model,
            "status": "Online" if h_status == "Online" else "Offline",
            "period": req_period,
            "period_hours": sla.get("period_hours_str", "0h 00m"),
            "sla_target": 99.5,
            "sla_uptime_pct": sla_uptime,
            "sla_failure_rate_pct": sla_failure,
            "meets_sla": meets_sla,
            "smartbox_status": h_status,
            "smartbox_uptime_pct": h_pct,
            "smartbox_uptime_duration": h_dur,
            "smartbox_offline_duration": sla.get("gateway_offline_str", "0m"),
            "dvr_status": d_status,
            "dvr_uptime_pct": d_pct,
            "dvr_uptime_duration": d_dur,
            "dvr_offline_duration": sla.get("dvr_offline_str", "0m"),
            "network_status": c_status,
            "network_uptime_pct": c_pct,
            "network_uptime_duration": c_dur,
            "network_offline_duration": sla.get("cellular_offline_str", "0m"),
            "trouble_events": trouble_events,
            "daily_breakdown": daily_breakdown,
            "daily_summary": daily_summary,
            "timeline_tracks": sla.get("timeline_tracks", []),
        }

    def export_excel(
        self,
        search: Optional[str] = None,
        gateway_type: Optional[str] = None,
        sla_status: Optional[str] = None,
        date_range: Optional[str] = None,
    ) -> io.BytesIO:
        """Exports SLA compliance report to professional Excel spreadsheet (.xlsx) matching client visual spec"""
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
        sub_hdr_font = Font(name="Segoe UI", size=9, bold=True, color="334155")
        row_font = Font(name="Segoe UI", size=9)
        red_font = Font(name="Segoe UI", size=9, bold=True, color="E11D48")
        green_font = Font(name="Segoe UI", size=9, bold=True, color="16A34A")

        # Color fills matching UI mockup
        sb_fill = PatternFill(start_color="DBEAFE", end_color="DBEAFE", fill_type="solid")  # Blue
        dvr_fill = PatternFill(start_color="DCFCE7", end_color="DCFCE7", fill_type="solid") # Green
        net_fill = PatternFill(start_color="F3E8FF", end_color="F3E8FF", fill_type="solid") # Purple
        sla_fill = PatternFill(start_color="FEF9C3", end_color="FEF9C3", fill_type="solid") # Yellow
        hdr_base_fill = PatternFill(start_color="F1F5F9", end_color="F1F5F9", fill_type="solid")

        thin_border = Border(
            left=Side(style="thin", color="CBD5E1"),
            right=Side(style="thin", color="CBD5E1"),
            top=Side(style="thin", color="CBD5E1"),
            bottom=Side(style="thin", color="CBD5E1")
        )

        # Title
        ws["A1"] = "PROTECTQUBE AIOPS - SERVICE LEVEL AGREEMENT (SLA) REPORT"
        ws["A1"].font = title_font
        ws["A2"] = f"Generated: {datetime.now().strftime('%d %b %Y %H:%M:%S')} WIB | Period: {date_range or 'Current Month'}"
        ws["A2"].font = sub_font

        # Summary KPIs row 4-5
        ws["A4"] = "TOTAL FLEET"
        ws["A5"] = f"{summary.get('total_gateways', 0)} Gateways"
        ws["C4"] = "AVERAGE SLA UPTIME"
        ws["C5"] = f"{summary.get('avg_sla_uptime', 100.0)}%"
        ws["E4"] = "FAILURE RATE"
        ws["E5"] = f"{summary.get('avg_sla_failure_rate', 0.0)}%"
        ws["G4"] = "SMARTBOX UPTIME"
        ws["G5"] = f"{summary.get('avg_smartbox_uptime', 100.0)}%"
        ws["I4"] = "DVR UPTIME"
        ws["I5"] = f"{summary.get('avg_dvr_uptime', 100.0)}%"
        ws["K4"] = "NETWORK UPTIME"
        ws["K5"] = f"{summary.get('avg_network_uptime', 100.0)}%"

        for col_l in ["A", "C", "E", "G", "I", "K"]:
            ws[f"{col_l}4"].font = Font(name="Segoe UI", size=8, bold=True, color="64748B")
            ws[f"{col_l}5"].font = Font(name="Segoe UI", size=12, bold=True, color="0F172A")

        # Level 1 Table Header Row 7
        ws["A7"] = "No"
        ws["B7"] = "Location"
        ws["C7"] = "Type"
        ws["D7"] = "Customer"
        ws.merge_cells("A7:A8")
        ws.merge_cells("B7:B8")
        ws.merge_cells("C7:C8")
        ws.merge_cells("D7:D8")

        for c_let in ["A", "B", "C", "D"]:
            c = ws[f"{c_let}7"]
            c.font = Font(name="Segoe UI", size=10, bold=True, color="0F172A")
            c.fill = hdr_base_fill
            c.alignment = Alignment(horizontal="center", vertical="center")

        # Smartbox Group E-F
        ws.merge_cells("E7:F7")
        ws["E7"] = "Smartbox"
        ws["E7"].font = Font(name="Segoe UI", size=10, bold=True, color="1E40AF")
        ws["E7"].fill = sb_fill
        ws["E7"].alignment = Alignment(horizontal="center")

        # DVR Group G-H
        ws.merge_cells("G7:H7")
        ws["G7"] = "DVR"
        ws["G7"].font = Font(name="Segoe UI", size=10, bold=True, color="166534")
        ws["G7"].fill = dvr_fill
        ws["G7"].alignment = Alignment(horizontal="center")

        # Network Group I-J
        ws.merge_cells("I7:J7")
        ws["I7"] = "Network"
        ws["I7"].font = Font(name="Segoe UI", size=10, bold=True, color="6B21A8")
        ws["I7"].fill = net_fill
        ws["I7"].alignment = Alignment(horizontal="center")

        # SLA Group K-L
        ws.merge_cells("K7:L7")
        ws["K7"] = "SLA"
        ws["K7"].font = Font(name="Segoe UI", size=10, bold=True, color="854D0E")
        ws["K7"].fill = sla_fill
        ws["K7"].alignment = Alignment(horizontal="center")

        # Level 2 Sub-Headers Row 8
        sub_headers = [
            (5, "Status", sb_fill), (6, "Uptime", sb_fill),
            (7, "Status", dvr_fill), (8, "Uptime", dvr_fill),
            (9, "Status", net_fill), (10, "Uptime", net_fill),
            (11, "Uptime", sla_fill), (12, "Failure Rate", sla_fill),
        ]
        for col_idx, text, fill_bg in sub_headers:
            cell = ws.cell(row=8, column=col_idx, value=text)
            cell.font = sub_hdr_font
            cell.fill = fill_bg
            cell.alignment = Alignment(horizontal="center", vertical="center")

        # Table Rows
        for r_idx, g in enumerate(gateways, 9):
            row_vals = [
                g.get("no", r_idx - 8),
                g.get("location"),
                g.get("type"),
                g.get("customer", "-"),
                g.get("smartbox_status", "Online"),
                f"{g.get('smartbox_uptime_pct', 100.0):.1f}%",
                g.get("dvr_status", "Working"),
                f"{g.get('dvr_uptime_pct', 100.0):.1f}%",
                g.get("network_status", "Working"),
                f"{g.get('network_uptime_pct', 100.0):.1f}%",
                f"{g.get('sla_uptime_pct', 100.0):.2f}%",
                f"{g.get('sla_failure_rate_pct', 0.0):.2f}%",
            ]
            for c_idx, val in enumerate(row_vals, 1):
                c = ws.cell(row=r_idx, column=c_idx, value=val)
                c.font = row_font
                c.border = thin_border
                if c_idx in [1, 3, 4, 5, 7, 9]:
                    c.alignment = Alignment(horizontal="center")
                elif c_idx in [6, 8, 10, 11, 12]:
                    c.alignment = Alignment(horizontal="right")
                    if c_idx == 12:
                        c.font = red_font
                    elif c_idx == 11:
                        c.font = green_font
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
