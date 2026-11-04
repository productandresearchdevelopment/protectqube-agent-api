import re
import logging
import calendar
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timedelta, timezone
from app.core.database import SessionLocal
from app.models.base_models import GatewayTelemetryHistory, GatewayIncidentAlert

logger = logging.getLogger("sla-calculator-service")

GAP_THRESHOLD_SECONDS = 600  # 10 Menit: ambang batas offline valid (2 siklus simpan 5 menit)
WIB = timezone(timedelta(hours=7))


def _to_wib_str(dt: Optional[datetime], fmt: str = "%d %b %H:%M") -> str:
    """Mengonversi UTC/naive datetime dari database ke jam lokal WIB (UTC+7)."""
    if not dt:
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(WIB).strftime(fmt)


def get_default_period_str(reference_dt: Optional[datetime] = None) -> str:
    """
    Menghasilkan string rentang tanggal bulan aktif (misal '01 Nov 2026 - 30 Nov 2026')
    berdasarkan waktu sekarang (WIB) secara dinamis.
    """
    if not reference_dt:
        reference_dt = datetime.now(timezone.utc).astimezone(WIB)
    year = reference_dt.year
    month = reference_dt.month
    _, last_day = calendar.monthrange(year, month)
    mon_name = reference_dt.strftime("%b")
    return f"01 {mon_name} {year} - {last_day:02d} {mon_name} {year}"


class SLACalculatorService:
    """
    Automated SLA & Incident Calculator:
    Computes 100% real Uptime, Downtime, SLA % and Incident Trouble Events
    from PostgreSQL table 'gateway_telemetry_history' combined with kernel uptime.
    """

    @staticmethod
    def _parse_date_range(date_range_str: Optional[str]) -> Tuple[Optional[datetime], Optional[datetime]]:
        """Parses '01 Oct 2026 - 31 Oct 2026' or '2026-10-01 - 2026-10-31' into start and end datetimes."""
        if not date_range_str:
            return None, None
        try:
            parts = [p.strip() for p in date_range_str.split(" - ")]
            if len(parts) != 2:
                return None, None
            start_str, end_str = parts[0], parts[1]
            start_dt = None
            end_dt = None
            for fmt in ["%d %b %Y", "%Y-%m-%d", "%d/%m/%Y", "%d %B %Y"]:
                try:
                    start_dt = datetime.strptime(start_str, fmt)
                    end_dt = datetime.strptime(end_str, fmt).replace(hour=23, minute=59, second=59)
                    break
                except ValueError:
                    continue
            return start_dt, end_dt
        except Exception:
            return None, None

    @staticmethod
    def _format_duration(seconds: float) -> str:
        s = int(max(0, seconds))
        h = s // 3600
        m = (s % 3600) // 60
        if h > 0:
            return f"{h}h {m:02d}m"
        return f"{m}m"

    @staticmethod
    def evaluate_record_status(
        payload: Optional[Dict[str, Any]],
        sim_status_db: Optional[str] = None,
        signal_csq_db: Optional[int] = None,
        nvr_status_db: Optional[str] = None,
        is_rec_db: Optional[bool] = None,
    ) -> Tuple[bool, bool, bool, bool]:
        """
        Evaluates real-time health from 'recent_system_logs' or structured payload:
        Returns:
            (cpu_modem_up: bool, network_up: bool, cpu_dvr_up: bool, is_recording: bool)

        Rules:
        1. CPU - Modem:
           - Uptime: [MODEM-CPU: OK]
           - Downtime: [MODEM-CPU: TERPUTUS]
        2. CPU – DVR Communication:
           - Downtime: NVR: OFFLINE
           - Uptime: Any status other than OFFLINE (e.g. SEDANG MEREKAM, JADWAL AKTIF)
        3. Network Connection (SIM):
           - Uptime: Strictly Opsi A (<Operator> (4G LTE, CSQ <1-31>))
           - Downtime: Opsi B (ALIRAN DATA MATI), C (DICABUT), D (NO SIGNAL), F (CSQ 99)
           - EXCEPTION (Opsi E): [SIM: N/A (Modem Terputus)] is EXCLUDED from Network downtime
             (allocated to CPU-Modem downtime).
        """
        payload = payload if isinstance(payload, dict) else {}
        logs = payload.get("recent_system_logs")

        latest_log = None
        if isinstance(logs, list) and logs:
            for line in reversed(logs):
                if isinstance(line, str) and ("[MODEM-CPU:" in line or "NVR:" in line or "[SIM:" in line):
                    latest_log = line
                    break
        elif isinstance(logs, str) and logs.strip():
            for line in reversed(logs.strip().split("\n")):
                if "[MODEM-CPU:" in line or "NVR:" in line or "[SIM:" in line:
                    latest_log = line.strip()
                    break

        cpu_modem_up: Optional[bool] = None
        network_up: Optional[bool] = None
        cpu_dvr_up: Optional[bool] = None
        is_recording: Optional[bool] = None

        if latest_log:
            # 1. CPU - Modem
            if "[MODEM-CPU: OK]" in latest_log:
                cpu_modem_up = True
            elif "[MODEM-CPU: TERPUTUS]" in latest_log:
                cpu_modem_up = False

            # 2. CPU – DVR Communication & Recording
            nvr_match = re.search(r'NVR:\s*([^\|]+)', latest_log)
            if nvr_match:
                nvr_val = nvr_match.group(1).strip().upper()
                if "OFFLINE" in nvr_val:
                    cpu_dvr_up = False
                    is_recording = False
                else:
                    cpu_dvr_up = True
                    is_recording = ("SEDANG MEREKAM" in nvr_val or "MEREKAM" in nvr_val)

            # 3. Network Connection (SIM)
            if "[SIM: N/A (Modem Terputus)]" in latest_log or re.search(r'\[SIM:\s*N/A\s*\(Modem Terputus\)', latest_log, re.IGNORECASE):
                network_up = True  # Opsi E: excluded from network downtime
            elif re.search(r'\[SIM:\s*[^\]]*\(4G\s*LTE,\s*CSQ\s*([1-9]|[1-2][0-9]|3[0-1])\)', latest_log, re.IGNORECASE):
                network_up = True  # Opsi A
            elif "[SIM:" in latest_log:
                network_up = False  # Opsi B, C, D, F

        # Fallbacks for records before recent_system_logs existed or if missing in log
        if cpu_modem_up is None:
            hw_conn = payload.get("hardware_connections", {}).get("modem_usb", {})
            if hw_conn.get("connected") is False or hw_conn.get("status") in ["FAIL", "DISCONNECTED"]:
                cpu_modem_up = False
            else:
                modem_obj = payload.get("modem_usb", {})
                cpu_modem_up = False if (modem_obj.get("connected") is False or modem_obj.get("connection_status") in ["DISCONNECTED", "FAIL"]) else True

        if cpu_dvr_up is None:
            nvr_obj = payload.get("nvr_surveillance", {})
            nvr_stat = str(nvr_obj.get("status") or nvr_status_db or "").upper()
            if nvr_stat == "OFFLINE" or nvr_obj.get("connected") is False:
                cpu_dvr_up = False
                is_recording = False
            else:
                cpu_dvr_up = True
                is_recording = is_rec_db if is_rec_db is not None else (nvr_obj.get("recording") is True or nvr_stat in ["RECORDING", "SEDANG MEREKAM"])

        if is_recording is None:
            is_recording = bool(is_rec_db)

        if network_up is None:
            if not cpu_modem_up:
                network_up = True  # Opsi E fallback
            else:
                sim_obj = payload.get("cellular_sim", {})
                csq = signal_csq_db if signal_csq_db is not None else sim_obj.get("signal", {}).get("csq", 0)
                sim_ins = sim_obj.get("sim_inserted") if "sim_inserted" in sim_obj else (sim_status_db == "Aktif")
                conn_state = str(sim_obj.get("connection_state") or "").upper()
                net_mode = str(sim_obj.get("network_mode") or "").upper()
                csq_val = int(csq or 0)
                if sim_ins and (1 <= csq_val <= 31) and ("ONLINE" in conn_state or "AKTIF" in conn_state or "4G" in net_mode) and "MATI" not in conn_state:
                    network_up = True
                else:
                    network_up = False

        return cpu_modem_up, network_up, cpu_dvr_up, is_recording

    @staticmethod
    def resolve_device_type(payload: Optional[Dict[str, Any]], device_id: str = "") -> str:
        """
        Mengambil tipe/variant SmartBox langsung dari data MQTT (variant, flag, pqube_variant, dll).
        """
        if not payload or not isinstance(payload, dict):
            return "SmartBox Hitam"

        gw_sys = payload.get("gateway_system", {}) if isinstance(payload, dict) else {}
        hw = gw_sys.get("hardware", {}) if isinstance(gw_sys, dict) else {}
        site_info = payload.get("site_info", {}) if isinstance(payload, dict) else {}

        raw_var = (
            payload.get("variant")
            or payload.get("flag")
            or payload.get("pqube_variant")
            or payload.get("pqube_flag")
            or payload.get("pqube_type")
            or site_info.get("variant")
            or site_info.get("flag")
            or gw_sys.get("variant")
            or hw.get("variant")
            or hw.get("flag")
        )

        if raw_var and isinstance(raw_var, str):
            v_low = raw_var.strip().lower()
            if "hitam" in v_low:
                return "SmartBox Hitam"
            if "putih" in v_low:
                return "SmartBox Putih"
            return f"SmartBox {raw_var.strip().capitalize()}"

        model_str = (str(hw.get("model", "")) + " " + str(hw.get("type", ""))).lower()
        if "rpi" in model_str or "raspberry" in model_str or "hitam" in device_id.lower():
            return "SmartBox Hitam"
        if "dusun" in model_str or "dsgw" in model_str or "putih" in device_id.lower():
            return "SmartBox Putih"

        return "SmartBox Hitam"

    def calculate_device_sla(
        self,
        device_id: str,
        live_payload: Optional[Dict[str, Any]] = None,
        date_range_str: Optional[str] = None,
        date_range: Optional[str] = None,
    ) -> Dict[str, Any]:
        if not date_range_str and date_range:
            date_range_str = date_range
        """
        Analyzes historical records in database for the given device_id.
        Returns:
            - gateway_uptime & offline duration + SLA %
            - cellular_uptime & offline duration + SLA %
            - dvr_uptime & offline duration + SLA %
            - real trouble events
            - real multi-track timeline segments
            - real historical trend lines (CPU, RAM, SD, RSRP)
        """
        db = SessionLocal()
        rows: List[GatewayTelemetryHistory] = []
        alerts: List[GatewayIncidentAlert] = []
        start_dt, end_dt = self._parse_date_range(date_range_str)
        try:
            query = db.query(GatewayTelemetryHistory).filter(GatewayTelemetryHistory.device_id == device_id)
            alert_q = db.query(GatewayIncidentAlert).filter(GatewayIncidentAlert.device_id == device_id)
            if start_dt and end_dt:
                s_utc = start_dt - timedelta(hours=7)
                e_utc = end_dt - timedelta(hours=7)
                s_date_str = start_dt.strftime("%Y-%m-%d")
                e_date_str = end_dt.strftime("%Y-%m-%d")
                # Prepend the single row immediately preceding s_utc so intervals spanning across start_dt are preserved
                prev_row = (
                    db.query(GatewayTelemetryHistory)
                    .filter(GatewayTelemetryHistory.device_id == device_id, GatewayTelemetryHistory.recorded_at < s_utc)
                    .order_by(GatewayTelemetryHistory.recorded_at.desc())
                    .first()
                )
                range_rows = (
                    db.query(GatewayTelemetryHistory)
                    .filter(
                        GatewayTelemetryHistory.device_id == device_id,
                        GatewayTelemetryHistory.recorded_at >= s_utc,
                        GatewayTelemetryHistory.recorded_at <= e_utc
                    )
                    .order_by(GatewayTelemetryHistory.recorded_at.asc())
                    .all()
                )
                rows = ([prev_row] if prev_row else []) + range_rows
                alert_q = alert_q.filter(
                    (GatewayIncidentAlert.date_str >= s_date_str) & (GatewayIncidentAlert.date_str <= e_date_str)
                    | ((GatewayIncidentAlert.occurred_at >= s_utc) & (GatewayIncidentAlert.occurred_at <= e_utc))
                )
            else:
                rows = query.order_by(GatewayTelemetryHistory.recorded_at.asc()).all()
            alerts = alert_q.order_by(GatewayIncidentAlert.occurred_at.desc()).all()
        except Exception as e:
            logger.error(f"Error querying telemetry/alert history for {device_id}: {e}")
        finally:
            db.close()

        kernel_uptime_sec = 0
        if live_payload:
            gw_sys = live_payload.get("gateway_system", {})
            kernel_uptime_sec = gw_sys.get("uptime_seconds", 0)
            if not kernel_uptime_sec:
                raw_up = gw_sys.get("uptime", "")
                try:
                    parts = raw_up.split()
                    h = 0
                    m = 0
                    for p in parts:
                        if p.endswith("h"):
                            h = int(p[:-1])
                        elif p.endswith("m"):
                            m = int(p[:-1])
                        elif p.endswith("d"):
                            h += int(p[:-1]) * 24
                    kernel_uptime_sec = h * 3600 + m * 60
                except Exception:
                    kernel_uptime_sec = 3600

        # Build authentic trouble events directly from GatewayIncidentAlert
        trouble_events: List[Dict[str, Any]] = []
        alert_windows: List[Tuple[datetime, datetime]] = []

        for al in alerts:
            # Abaikan alert resolusi lama yang durasinya di bawah 1 menit (60 detik)
            if al.status == "RESOLVED" and al.downtime_seconds and al.downtime_seconds < 60:
                continue

            st_str = _to_wib_str(al.occurred_at, fmt="%d %b %H:%M")
            if al.recovered_at:
                et_str = _to_wib_str(al.recovered_at, fmt="%d %b %H:%M")
            else:
                et_str = "Active"

            dur_str = al.downtime_duration or (
                self._format_duration(al.downtime_seconds)
                if al.downtime_seconds
                else ("Active" if al.status == "ACTIVE" else "1m")
            )

            cat_label = al.category
            if al.category == "POWER":
                cat_label = "Power / Reboot"
            elif al.category in ["CPU_MODEM"]:
                cat_label = "CPU - Modem"
            elif al.category in ["CCTV_NVR", "DVR", "CPU_DVR"]:
                cat_label = "CPU - DVR"
            elif al.category in ["CELLULAR", "NETWORK"]:
                cat_label = "Seluler / Network"
            elif al.category == "STORAGE":
                cat_label = "Storage / SD"
            elif al.category == "SYSTEM":
                cat_label = "System Health"

            val_label = al.component or al.alert_code

            resolved_metric = al.metric
            if not resolved_metric:
                if "REBOOT" in al.alert_code or al.category == "POWER":
                    resolved_metric = "power"
                elif al.category == "CPU_MODEM" or "MODEM" in al.alert_code:
                    resolved_metric = "cpu_modem"
                elif al.category in ["CPU_DVR", "DVR", "CCTV_NVR"] or "DVR" in al.alert_code or "NVR" in al.alert_code:
                    resolved_metric = "cpu_dvr"
                else:
                    resolved_metric = "cellular"

            trouble_events.append({
                "no": len(trouble_events) + 1,
                "start_time": st_str,
                "end_time": et_str,
                "duration": dur_str,
                "category": cat_label,
                "metric": resolved_metric,
                "date_str": al.date_str or (al.occurred_at.strftime("%Y-%m-%d") if al.occurred_at else None),
                "day_downtime_minutes": al.day_downtime_minutes or (round(al.downtime_seconds / 60.0, 1) if al.downtime_seconds else 0.0),
                "title": al.title,
                "description": al.title,
                "cause": al.message,
                "reason": al.message,
                "status": "Resolved" if al.status == "RESOLVED" else "Active",
                "recommendation": al.recommendation or "-",
                "severity": al.severity,
                "alert_code": al.alert_code,
                "value": val_label,
                "accumulated_hours": dur_str,
                "sla_impact_pct": round(min(5.0, ((al.downtime_seconds or 60) / 3600.0) * 100), 2),
                "_raw_dt": al.occurred_at,
            })

            if al.occurred_at:
                rec_dt = al.recovered_at or (al.occurred_at + timedelta(seconds=al.downtime_seconds or 300))
                alert_windows.append((al.occurred_at, rec_dt))


        if not rows:
            obs_sec = max(3600, kernel_uptime_sec)
            m_ok, net_ok, dvr_ok, rec_ok = self.evaluate_record_status(live_payload)

            gw_up_str = self._format_duration(obs_sec) if m_ok else "0m"
            gw_off_str = "0m" if m_ok else self._format_duration(obs_sec)
            gw_sr = 100.0 if m_ok else 0.0

            net_up_str = self._format_duration(obs_sec) if net_ok else "0m"
            net_off_str = "0m" if net_ok else self._format_duration(obs_sec)
            net_sr = 100.0 if net_ok else 0.0

            dvr_comm_up_str = self._format_duration(obs_sec) if dvr_ok else "0m"
            dvr_comm_off_str = "0m" if dvr_ok else self._format_duration(obs_sec)
            dvr_comm_sr = 100.0 if dvr_ok else 0.0

            rec_up_str = self._format_duration(obs_sec) if rec_ok else "0m"
            rec_off_str = "0m" if rec_ok else self._format_duration(obs_sec)
            rec_sr = 100.0 if rec_ok else 0.0

            daily_breakdown, daily_summary = self.calculate_daily_breakdown(
                start_dt=start_dt,
                end_dt=end_dt,
                alerts=alerts,
                rows=rows,
                target_sla_pct=98.0
            )

            if date_range_str and daily_summary and daily_summary.get("total_obs_min"):
                obs_sec = daily_summary["total_obs_min"] * 60.0
                gw_up_str = self._format_duration(daily_summary["total_cpu_modem_uptime_min"] * 60.0)
                gw_off_str = self._format_duration(daily_summary["total_cpu_modem_downtime_min"] * 60.0)
                gw_sr = daily_summary["avg_cpu_modem_success_rate"]
                net_up_str = self._format_duration(daily_summary["total_cellular_uptime_min"] * 60.0)
                net_off_str = self._format_duration(daily_summary["total_cellular_downtime_min"] * 60.0)
                net_sr = daily_summary["avg_cellular_success_rate"]
                dvr_comm_up_str = self._format_duration(daily_summary.get("total_cpu_dvr_uptime_min", 0) * 60.0)
                dvr_comm_off_str = self._format_duration(daily_summary.get("total_cpu_dvr_downtime_min", 0) * 60.0)
                dvr_comm_sr = daily_summary.get("avg_cpu_dvr_success_rate", 100.0)
                rec_up_str = self._format_duration(daily_summary.get("total_rec_uptime_min", 0) * 60.0)
                rec_off_str = self._format_duration(daily_summary.get("total_rec_downtime_min", 0) * 60.0)
                rec_sr = daily_summary.get("avg_rec_success_rate", 100.0)

            return {
                "period_hours_str": f"({round(obs_sec / 3600, 1)} hrs)",
                "observation_seconds": obs_sec,

                # Legacy & CPU - Modem metrics
                "gateway_uptime_str": gw_up_str,
                "gateway_offline_str": gw_off_str,
                "gateway_sla_pct": gw_sr,
                "cpu_modem_uptime_str": gw_up_str,
                "cpu_modem_offline_str": gw_off_str,
                "cpu_modem_success_rate": gw_sr,

                # Network Connection metrics
                "cellular_uptime_str": net_up_str,
                "cellular_offline_str": net_off_str,
                "cellular_sla_pct": net_sr,
                "network_uptime_str": net_up_str,
                "network_offline_str": net_off_str,
                "network_success_rate": net_sr,

                # CPU – DVR Communication metrics
                "cpu_dvr_uptime_str": dvr_comm_up_str,
                "cpu_dvr_offline_str": dvr_comm_off_str,
                "cpu_dvr_success_rate": dvr_comm_sr,

                # Recording Uptime (DVR Video Recording)
                "dvr_uptime_str": rec_up_str,
                "dvr_offline_str": rec_off_str,
                "dvr_sla_pct": rec_sr,

                "trouble_events": trouble_events,
                "timeline_tracks": [
                    {"track_name": "Gateway", "segments": [{"status": "online" if m_ok else "offline", "start_pct": 0, "width_pct": 100, "label": "Online" if m_ok else "Terputus", "period": "Live"}]},
                    {"track_name": "Cellular", "segments": [{"status": "online" if net_ok else "offline", "start_pct": 0, "width_pct": 100, "label": "Online" if net_ok else "No Signal/SIM", "period": "Live"}]},
                    {"track_name": "DVR", "segments": [{"status": "online" if dvr_ok else "offline", "start_pct": 0, "width_pct": 100, "label": "Connected" if dvr_ok else "Offline", "period": "Live"}]},
                ],
                "avg_temp": 42,
                "avg_rsrp": -85,
                "avg_ping": round(float(live_payload.get("cellular_sim", {}).get("data_traffic", {}).get("ping_ms")), 1) if (live_payload and live_payload.get("cellular_sim", {}).get("data_traffic", {}).get("ping_ms") is not None) else None,
                "cpu_trend": [],
                "ram_trend": [],
                "sd_trend": [],
                "daily_breakdown": daily_breakdown,
                "daily_summary": daily_summary,
            }

        first_time = rows[0].recorded_at
        last_time = rows[-1].recorded_at
        delta_span = max(60.0, (last_time - first_time).total_seconds())

        total_obs_sec = max(delta_span, float(kernel_uptime_sec), 3600.0)

        gw_downtime_sec = 0.0
        cellular_downtime_sec = 0.0
        dvr_downtime_sec = 0.0
        rec_downtime_sec = 0.0

        raw_gw_segments: List[Dict[str, Any]] = []

        for i in range(len(rows) - 1):
            curr_r = rows[i]
            next_r = rows[i + 1]
            gap_sec = (next_r.recorded_at - curr_r.recorded_at).total_seconds()

            curr_time_str = _to_wib_str(curr_r.recorded_at)
            next_time_str = _to_wib_str(next_r.recorded_at)

            m_up, n_up, d_up, r_rec = self.evaluate_record_status(
                curr_r.raw_payload,
                curr_r.sim_status,
                curr_r.signal_csq,
                curr_r.nvr_status,
                curr_r.nvr_recording
            )

            if not m_up:
                gw_downtime_sec += gap_sec
                raw_gw_segments.append({"status": "offline", "duration": gap_sec, "label": "Modem-CPU Terputus", "period": f"{curr_time_str} - {next_time_str}"})
            else:
                raw_gw_segments.append({"status": "online", "duration": gap_sec, "label": "Online Normal", "period": f"{curr_time_str} - {next_time_str}"})

            if not n_up:
                cellular_downtime_sec += gap_sec

            if not d_up:
                dvr_downtime_sec += gap_sec

            if not r_rec:
                rec_downtime_sec += gap_sec

        gw_uptime_sec = max(0.0, total_obs_sec - gw_downtime_sec)
        cellular_uptime_sec = max(0.0, total_obs_sec - cellular_downtime_sec)
        dvr_uptime_sec = max(0.0, total_obs_sec - dvr_downtime_sec)
        rec_uptime_sec = max(0.0, total_obs_sec - rec_downtime_sec)

        gw_sla = round(max(0.0, min(100.0, (gw_uptime_sec / total_obs_sec) * 100.0)), 1)
        cellular_sla = round(max(0.0, min(100.0, (cellular_uptime_sec / total_obs_sec) * 100.0)), 1)
        dvr_sla = round(max(0.0, min(100.0, (dvr_uptime_sec / total_obs_sec) * 100.0)), 1)
        rec_sla = round(max(0.0, min(100.0, (rec_uptime_sec / total_obs_sec) * 100.0)), 1)

        timeline_segments = []
        if raw_gw_segments:
            tot_seg_dur = sum(s["duration"] for s in raw_gw_segments)
            curr_pct = 0.0
            for s in raw_gw_segments[:12]:
                w = round((s["duration"] / tot_seg_dur) * 100.0, 1) if tot_seg_dur > 0 else 100.0
                timeline_segments.append({
                    "status": s["status"],
                    "start_pct": round(curr_pct, 1),
                    "width_pct": max(2.0, w),
                    "label": s["label"],
                    "period": s["period"],
                })
                curr_pct += w
        else:
            timeline_segments = [
                {"status": "online", "start_pct": 0, "width_pct": 100.0, "label": "Online Normal", "period": f"{_to_wib_str(first_time)} - Present"}
            ]

        timeline_tracks = [
            {"track_name": "Gateway", "segments": timeline_segments},
            {"track_name": "Cellular", "segments": [
                {"status": "online" if cellular_sla >= 90 else "offline", "start_pct": 0, "width_pct": 100.0, "label": f"Cellular ({cellular_sla}%)", "period": "Observation Period"}
            ]},
            {"track_name": "DVR", "segments": [
                {"status": "online" if dvr_sla >= 90 else "offline", "start_pct": 0, "width_pct": 100.0, "label": f"DVR/NVR ({dvr_sla}%)", "period": "Observation Period"}
            ]},
        ]

        step = max(1, len(rows) // 15)
        sampled = rows[::step]
        if rows[-1] not in sampled:
            sampled.append(rows[-1])

        cpu_trend = []
        ram_trend = []
        sd_trend = []
        for r in sampled:
            dt_label = _to_wib_str(r.recorded_at, fmt="%H:%M")
            cpu_trend.append({"date": dt_label, "value": int(round(r.cpu_percent or 0))})
            ram_pct = int(round((r.ram_used_mb / r.ram_total_mb * 100))) if r.ram_total_mb else 25
            ram_trend.append({"date": dt_label, "value": ram_pct})
            sd_trend.append({"date": dt_label, "value": int(round(r.disk_used_percent or 50))})

        # Urutkan trouble events secara kronologis menurun (kejadian terbaru nomor 1 di atas)
        trouble_events.sort(key=lambda x: x.get("_raw_dt") or datetime.min, reverse=True)
        for idx, ev in enumerate(trouble_events, 1):
            ev["no"] = idx
            ev.pop("_raw_dt", None)


        valid_temps = [r.temperature_c for r in rows if r.temperature_c is not None]
        avg_temp_val = int(round(sum(valid_temps) / len(valid_temps))) if valid_temps else 42
        min_temp_val = round(min(valid_temps), 1) if valid_temps else None
        max_temp_val = round(max(valid_temps), 1) if valid_temps else None

        valid_csqs = [r.signal_csq for r in rows if r.signal_csq is not None and r.signal_csq > 0]
        if valid_csqs:
            avg_csq_val = sum(valid_csqs) / len(valid_csqs)
            avg_rsrp_val = int(round(-(113 - 2 * avg_csq_val)))
        else:
            avg_rsrp_val = -85

        valid_pings = []
        for r in rows:
            if r.raw_payload and isinstance(r.raw_payload, dict):
                p = r.raw_payload.get("cellular_sim", {}).get("data_traffic", {}).get("ping_ms")
                if p is not None:
                    try:
                        valid_pings.append(float(p))
                    except (ValueError, TypeError):
                        pass
        if not valid_pings and live_payload:
            p = live_payload.get("cellular_sim", {}).get("data_traffic", {}).get("ping_ms")
            if p is not None:
                try:
                    valid_pings.append(float(p))
                except (ValueError, TypeError):
                    pass
        avg_ping_val = round(sum(valid_pings) / len(valid_pings), 1) if valid_pings else None

        daily_breakdown, daily_summary = self.calculate_daily_breakdown(
            start_dt=start_dt,
            end_dt=end_dt,
            alerts=alerts,
            rows=rows,
            target_sla_pct=98.0
        )

        if date_range_str and daily_summary and daily_summary.get("total_obs_min"):
            total_obs_sec = daily_summary["total_obs_min"] * 60.0
            gw_uptime_sec = daily_summary["total_cpu_modem_uptime_min"] * 60.0
            gw_downtime_sec = daily_summary["total_cpu_modem_downtime_min"] * 60.0
            gw_sla = daily_summary["avg_cpu_modem_success_rate"]

            cellular_uptime_sec = daily_summary["total_cellular_uptime_min"] * 60.0
            cellular_downtime_sec = daily_summary["total_cellular_downtime_min"] * 60.0
            cellular_sla = daily_summary["avg_cellular_success_rate"]

            dvr_uptime_sec = daily_summary.get("total_cpu_dvr_uptime_min", gw_uptime_sec / 60.0) * 60.0
            dvr_downtime_sec = daily_summary.get("total_cpu_dvr_downtime_min", gw_downtime_sec / 60.0) * 60.0
            dvr_sla = daily_summary.get("avg_cpu_dvr_success_rate", gw_sla)

            rec_uptime_sec = daily_summary.get("total_rec_uptime_min", dvr_uptime_sec / 60.0) * 60.0
            rec_downtime_sec = daily_summary.get("total_rec_downtime_min", dvr_downtime_sec / 60.0) * 60.0
            rec_sla = daily_summary.get("avg_rec_success_rate", dvr_sla)

        return {
            "period_hours_str": f"({round(total_obs_sec / 3600, 1)} hrs)",
            "observation_seconds": total_obs_sec,

            # Legacy & CPU - Modem metrics
            "gateway_uptime_str": self._format_duration(gw_uptime_sec),
            "gateway_offline_str": self._format_duration(gw_downtime_sec),
            "gateway_sla_pct": gw_sla,
            "cpu_modem_uptime_str": self._format_duration(gw_uptime_sec),
            "cpu_modem_offline_str": self._format_duration(gw_downtime_sec),
            "cpu_modem_success_rate": gw_sla,

            # Network Connection metrics
            "cellular_uptime_str": self._format_duration(cellular_uptime_sec),
            "cellular_offline_str": self._format_duration(cellular_downtime_sec),
            "cellular_sla_pct": cellular_sla,
            "network_uptime_str": self._format_duration(cellular_uptime_sec),
            "network_offline_str": self._format_duration(cellular_downtime_sec),
            "network_success_rate": cellular_sla,

            # CPU – DVR Communication metrics
            "cpu_dvr_uptime_str": self._format_duration(dvr_uptime_sec),
            "cpu_dvr_offline_str": self._format_duration(dvr_downtime_sec),
            "cpu_dvr_success_rate": dvr_sla,

            # Recording Uptime (DVR Video Recording)
            "dvr_uptime_str": self._format_duration(rec_uptime_sec),
            "dvr_offline_str": self._format_duration(rec_downtime_sec),
            "dvr_sla_pct": rec_sla,

            "avg_temp": avg_temp_val,
            "min_temp": min_temp_val,
            "max_temp": max_temp_val,
            "avg_rsrp": avg_rsrp_val,
            "avg_ping": avg_ping_val,
            "trouble_events": trouble_events,
            "timeline_tracks": timeline_tracks,
            "cpu_trend": cpu_trend,
            "ram_trend": ram_trend,
            "sd_trend": sd_trend,
            "daily_breakdown": daily_breakdown,
            "daily_summary": daily_summary,
        }

    @staticmethod
    def _merge_intervals(raw_intervals: List[Tuple[datetime, datetime]]) -> List[Tuple[datetime, datetime]]:
        if not raw_intervals:
            return []
        sorted_int = sorted(raw_intervals, key=lambda x: x[0])
        merged = [sorted_int[0]]
        for cur_s, cur_e in sorted_int[1:]:
            last_s, last_e = merged[-1]
            if cur_s <= last_e:
                merged[-1] = (last_s, max(last_e, cur_e))
            else:
                merged.append((cur_s, cur_e))
        return merged

    def calculate_daily_breakdown(
        self,
        start_dt: Optional[datetime],
        end_dt: Optional[datetime],
        alerts: List[GatewayIncidentAlert],
        rows: Optional[List[GatewayTelemetryHistory]] = None,
        target_sla_pct: float = 98.0
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """
        Menghasilkan rincian SLA harian (Day 1..Day N) dengan algoritma Daily Time-Slicing:
        Setiap hari kalender memiliki kuota waktu 1.440 menit (24 jam) dari 00:00:00 s/d 23:59:59 WIB.
        Insiden downtime yang menyeberang tengah malam (misal 26 jam) otomatis dipotong
        ke masing-masing hari kalender yang bersangkutan tanpa melebihi 1.440 menit per hari.
        Rumus Success Rate per hari: 100% - (downtime_menit / 1440.0 * 100%) = (uptime_menit / 1440.0 * 100%).
        """
        now_wib = datetime.now(timezone.utc).astimezone(WIB)
        if start_dt and end_dt:
            s_date = start_dt.astimezone(WIB).date() if start_dt.tzinfo else start_dt.date()
            e_date = end_dt.astimezone(WIB).date() if end_dt.tzinfo else end_dt.date()
        else:
            ref_dt = now_wib
            if rows and rows[-1].recorded_at:
                r_dt = rows[-1].recorded_at
                ref_dt = r_dt.replace(tzinfo=timezone.utc).astimezone(WIB) if r_dt.tzinfo is None else r_dt.astimezone(WIB)
            _, last_day = calendar.monthrange(ref_dt.year, ref_dt.month)
            s_date = datetime(ref_dt.year, ref_dt.month, 1).date()
            e_date = datetime(ref_dt.year, ref_dt.month, last_day).date()

        daily_records: List[Dict[str, Any]] = []
        cur_date = s_date
        day_idx = 1

        total_cpu_down_sec = 0.0
        total_cell_down_sec = 0.0
        total_dvr_down_sec = 0.0
        total_rec_down_sec = 0.0
        total_obs_sec = 0.0

        # Primary Calculation Path: when historical telemetry rows exist
        if rows and len(rows) >= 2:
            t_last_wib = rows[-1].recorded_at.replace(tzinfo=timezone.utc).astimezone(WIB) if rows[-1].recorded_at.tzinfo is None else rows[-1].recorded_at.astimezone(WIB)

            while cur_date <= e_date:
                d_start = datetime(cur_date.year, cur_date.month, cur_date.day, 0, 0, 0, tzinfo=WIB)
                d_end = datetime(cur_date.year, cur_date.month, cur_date.day, 23, 59, 59, tzinfo=WIB)

                day_cpu_down_sec = 0.0
                day_cell_down_sec = 0.0
                day_dvr_down_sec = 0.0
                day_rec_down_sec = 0.0

                if cur_date > now_wib.date():
                    # Hari mendatang belum diamati
                    pass
                else:
                    for i in range(len(rows) - 1):
                        curr_r = rows[i]
                        next_r = rows[i + 1]
                        t1 = curr_r.recorded_at.replace(tzinfo=timezone.utc).astimezone(WIB) if curr_r.recorded_at.tzinfo is None else curr_r.recorded_at.astimezone(WIB)
                        t2 = next_r.recorded_at.replace(tzinfo=timezone.utc).astimezone(WIB) if next_r.recorded_at.tzinfo is None else next_r.recorded_at.astimezone(WIB)

                        overlap_s = max(t1, d_start)
                        overlap_e = min(t2, d_end)

                        if overlap_e > overlap_s:
                            dur = (overlap_e - overlap_s).total_seconds()
                            gap_sec = (t2 - t1).total_seconds()

                            m_up, n_up, d_up, is_rec = self.evaluate_record_status(
                                curr_r.raw_payload,
                                curr_r.sim_status,
                                curr_r.signal_csq,
                                curr_r.nvr_status,
                                curr_r.nvr_recording
                            )
                            if not m_up:
                                day_cpu_down_sec += dur
                            if not n_up:
                                day_cell_down_sec += dur
                            if not d_up:
                                day_dvr_down_sec += dur
                            if not is_rec:
                                day_rec_down_sec += dur

                    # Jika data berhenti sebelum d_end dan tanggal ini sudah terjadi
                    if t_last_wib < d_end and (cur_date < now_wib.date() or (cur_date == now_wib.date() and t_last_wib < now_wib)):
                        tail_s = max(d_start, t_last_wib)
                        tail_e = min(d_end, now_wib) if cur_date == now_wib.date() else d_end
                        if tail_e > tail_s:
                            tail_dur = (tail_e - tail_s).total_seconds()
                            last_p = rows[-1].raw_payload if isinstance(rows[-1].raw_payload, dict) else {}
                            m_up_l, n_up_l, d_up_l, is_rec_l = self.evaluate_record_status(
                                last_p,
                                rows[-1].sim_status,
                                rows[-1].signal_csq,
                                rows[-1].nvr_status,
                                rows[-1].nvr_recording
                            )
                            if not m_up_l:
                                day_cpu_down_sec += tail_dur
                            if not n_up_l:
                                day_cell_down_sec += tail_dur
                            if not d_up_l:
                                day_dvr_down_sec += tail_dur
                            if not is_rec_l:
                                day_rec_down_sec += tail_dur

                day_cpu_down_sec = min(86400.0, max(0.0, day_cpu_down_sec))
                day_cell_down_sec = min(86400.0, max(0.0, day_cell_down_sec))
                day_dvr_down_sec = min(86400.0, max(0.0, day_dvr_down_sec))
                day_rec_down_sec = min(86400.0, max(0.0, day_rec_down_sec))

                cpu_down_min = round(day_cpu_down_sec / 60.0, 1)
                cpu_up_min = round(max(0.0, 1440.0 - cpu_down_min), 1)
                cpu_sr = round(max(0.0, min(100.0, 100.0 - (cpu_down_min / 1440.0 * 100.0))), 1)
                cpu_sla_diff = round(cpu_sr - target_sla_pct, 1)
                cpu_status = "Tercapai" if cpu_sr >= target_sla_pct else "Tidak Tercapai"

                cell_down_min = round(day_cell_down_sec / 60.0, 1)
                cell_up_min = round(max(0.0, 1440.0 - cell_down_min), 1)
                cell_sr = round(max(0.0, min(100.0, 100.0 - (cell_down_min / 1440.0 * 100.0))), 1)
                cell_sla_diff = round(cell_sr - target_sla_pct, 1)
                cell_status = "Tercapai" if cell_sr >= target_sla_pct else "Tidak Tercapai"

                dvr_down_min = round(day_dvr_down_sec / 60.0, 1)
                dvr_up_min = round(max(0.0, 1440.0 - dvr_down_min), 1)
                dvr_sr = round(max(0.0, min(100.0, 100.0 - (dvr_down_min / 1440.0 * 100.0))), 1)
                dvr_sla_diff = round(dvr_sr - target_sla_pct, 1)
                dvr_status = "Tercapai" if dvr_sr >= target_sla_pct else "Tidak Tercapai"

                rec_down_min = round(day_rec_down_sec / 60.0, 1)
                rec_up_min = round(max(0.0, 1440.0 - rec_down_min), 1)
                rec_sr = round(max(0.0, min(100.0, 100.0 - (rec_down_min / 1440.0 * 100.0))), 1)
                rec_sla_diff = round(rec_sr - target_sla_pct, 1)
                rec_status = "Tercapai" if rec_sr >= target_sla_pct else "Tidak Tercapai"

                daily_records.append({
                    "day": day_idx,
                    "date": cur_date.strftime("%d %b %Y"),
                    "day_name": cur_date.strftime("%a"),
                    "target_sla": target_sla_pct,

                    # Default / CPU - Modem table display
                    "uptime_min": cpu_up_min,
                    "downtime_min": cpu_down_min,
                    "success_rate": cpu_sr,
                    "sla_diff": cpu_sla_diff,
                    "sla_status": cpu_status,

                    "cpu_modem_uptime_min": cpu_up_min,
                    "cpu_modem_downtime_min": cpu_down_min,
                    "cpu_modem_success_rate": cpu_sr,
                    "cpu_modem_sla_diff": cpu_sla_diff,
                    "cpu_modem_status_sla": cpu_status,

                    # Cellular / Network metrics
                    "cellular_uptime_min": cell_up_min,
                    "cellular_downtime_min": cell_down_min,
                    "cellular_success_rate": cell_sr,
                    "cellular_sla_diff": cell_sla_diff,
                    "cellular_status_sla": cell_status,

                    # CPU – DVR Communication metrics
                    "cpu_dvr_uptime_min": dvr_up_min,
                    "cpu_dvr_downtime_min": dvr_down_min,
                    "cpu_dvr_success_rate": dvr_sr,
                    "cpu_dvr_sla_diff": dvr_sla_diff,
                    "cpu_dvr_status_sla": dvr_status,

                    # Recording metrics
                    "rec_uptime_min": rec_up_min,
                    "rec_downtime_min": rec_down_min,
                    "rec_success_rate": rec_sr,
                    "rec_sla_diff": rec_sla_diff,
                    "rec_status_sla": rec_status,
                })

                total_cpu_down_sec += day_cpu_down_sec
                total_cell_down_sec += day_cell_down_sec
                total_dvr_down_sec += day_dvr_down_sec
                total_rec_down_sec += day_rec_down_sec
                total_obs_sec += 86400.0

                cur_date += timedelta(days=1)
                day_idx += 1

        else:
            # Fallback when rows are not present: use GatewayIncidentAlerts
            cpu_raw: List[Tuple[datetime, datetime]] = []
            cell_raw: List[Tuple[datetime, datetime]] = []
            dvr_raw: List[Tuple[datetime, datetime]] = []

            for a in alerts:
                if a.occurred_at and a.recovered_at and a.recovered_at > a.occurred_at:
                    s = a.occurred_at.astimezone(WIB) if a.occurred_at.tzinfo else a.occurred_at.replace(tzinfo=timezone.utc).astimezone(WIB)
                    e = a.recovered_at.astimezone(WIB) if a.recovered_at.tzinfo else a.recovered_at.replace(tzinfo=timezone.utc).astimezone(WIB)

                    is_cpu_modem = (
                        a.category in ["POWER", "SYSTEM"]
                        or "REBOOT" in a.alert_code
                        or "MODEM" in a.alert_code
                        or "UNDERVOLTAGE" in a.alert_code
                        or a.alert_code == "TELEMETRY_GAP_WITH_REBOOT"
                    )
                    is_dvr = (
                        a.category in ["CCTV_NVR", "DVR"]
                        or "DVR" in a.alert_code
                        or "NVR" in a.alert_code
                    )

                    if is_cpu_modem:
                        cpu_raw.append((s, e))
                    if is_dvr:
                        dvr_raw.append((s, e))
                    cell_raw.append((s, e))

            cpu_merged = self._merge_intervals(cpu_raw)
            cell_merged = self._merge_intervals(cell_raw)
            dvr_merged = self._merge_intervals(dvr_raw)

            while cur_date <= e_date:
                d_start = datetime(cur_date.year, cur_date.month, cur_date.day, 0, 0, 0, tzinfo=WIB)
                d_end = datetime(cur_date.year, cur_date.month, cur_date.day, 23, 59, 59, tzinfo=WIB)

                day_cpu_down_sec = 0.0
                for s, e in cpu_merged:
                    overlap_s = max(s, d_start)
                    overlap_e = min(e, d_end)
                    if overlap_e > overlap_s:
                        day_cpu_down_sec += (overlap_e - overlap_s).total_seconds()

                day_cell_down_sec = 0.0
                for s, e in cell_merged:
                    overlap_s = max(s, d_start)
                    overlap_e = min(e, d_end)
                    if overlap_e > overlap_s:
                        day_cell_down_sec += (overlap_e - overlap_s).total_seconds()

                day_dvr_down_sec = 0.0
                for s, e in dvr_merged:
                    overlap_s = max(s, d_start)
                    overlap_e = min(e, d_end)
                    if overlap_e > overlap_s:
                        day_dvr_down_sec += (overlap_e - overlap_s).total_seconds()

                day_cpu_down_sec = min(86400.0, day_cpu_down_sec)
                day_cell_down_sec = min(86400.0, day_cell_down_sec)
                day_dvr_down_sec = min(86400.0, day_dvr_down_sec)

                cpu_down_min = round(day_cpu_down_sec / 60.0, 1)
                cpu_up_min = round(max(0.0, 1440.0 - cpu_down_min), 1)
                cpu_sr = round((cpu_up_min / 1440.0) * 100.0, 1)
                cpu_sla_diff = round(cpu_sr - target_sla_pct, 1)
                cpu_status = "Tercapai" if cpu_sr >= target_sla_pct else "Tidak Tercapai"

                cell_down_min = round(day_cell_down_sec / 60.0, 1)
                cell_up_min = round(max(0.0, 1440.0 - cell_down_min), 1)
                cell_sr = round((cell_up_min / 1440.0) * 100.0, 1)
                cell_sla_diff = round(cell_sr - target_sla_pct, 1)
                cell_status = "Tercapai" if cell_sr >= target_sla_pct else "Tidak Tercapai"

                dvr_down_min = round(day_dvr_down_sec / 60.0, 1)
                dvr_up_min = round(max(0.0, 1440.0 - dvr_down_min), 1)
                dvr_sr = round((dvr_up_min / 1440.0) * 100.0, 1)
                dvr_sla_diff = round(dvr_sr - target_sla_pct, 1)
                dvr_status = "Tercapai" if dvr_sr >= target_sla_pct else "Tidak Tercapai"

                daily_records.append({
                    "day": day_idx,
                    "date": cur_date.strftime("%d %b %Y"),
                    "day_name": cur_date.strftime("%a"),
                    "target_sla": target_sla_pct,

                    "uptime_min": cpu_up_min,
                    "downtime_min": cpu_down_min,
                    "success_rate": cpu_sr,
                    "sla_diff": cpu_sla_diff,
                    "sla_status": cpu_status,

                    "cpu_modem_uptime_min": cpu_up_min,
                    "cpu_modem_downtime_min": cpu_down_min,
                    "cpu_modem_success_rate": cpu_sr,
                    "cpu_modem_sla_diff": cpu_sla_diff,
                    "cpu_modem_status_sla": cpu_status,

                    "cellular_uptime_min": cell_up_min,
                    "cellular_downtime_min": cell_down_min,
                    "cellular_success_rate": cell_sr,
                    "cellular_sla_diff": cell_sla_diff,
                    "cellular_status_sla": cell_status,

                    "cpu_dvr_uptime_min": dvr_up_min,
                    "cpu_dvr_downtime_min": dvr_down_min,
                    "cpu_dvr_success_rate": dvr_sr,
                    "cpu_dvr_sla_diff": dvr_sla_diff,
                    "cpu_dvr_status_sla": dvr_status,
                })

                total_cpu_down_sec += day_cpu_down_sec
                total_cell_down_sec += day_cell_down_sec
                total_dvr_down_sec += day_dvr_down_sec
                total_obs_sec += 86400.0

                cur_date += timedelta(days=1)
                day_idx += 1

        total_cpu_up_min = round(max(0.0, (total_obs_sec - total_cpu_down_sec) / 60.0), 1)
        total_cpu_down_min = round(total_cpu_down_sec / 60.0, 1)
        avg_cpu_sr = round((total_cpu_up_min / (total_obs_sec / 60.0)) * 100.0, 1) if total_obs_sec > 0 else 100.0

        total_cell_up_min = round(max(0.0, (total_obs_sec - total_cell_down_sec) / 60.0), 1)
        total_cell_down_min = round(total_cell_down_sec / 60.0, 1)
        avg_cell_sr = round((total_cell_up_min / (total_obs_sec / 60.0)) * 100.0, 1) if total_obs_sec > 0 else 100.0

        total_dvr_up_min = round(max(0.0, (total_obs_sec - total_dvr_down_sec) / 60.0), 1)
        total_dvr_down_min = round(total_dvr_down_sec / 60.0, 1)
        avg_dvr_sr = round((total_dvr_up_min / (total_obs_sec / 60.0)) * 100.0, 1) if total_obs_sec > 0 else 100.0

        total_rec_up_min = round(max(0.0, (total_obs_sec - total_rec_down_sec) / 60.0), 1)
        total_rec_down_min = round(total_rec_down_sec / 60.0, 1)
        avg_rec_sr = round((total_rec_up_min / (total_obs_sec / 60.0)) * 100.0, 1) if total_obs_sec > 0 else 100.0

        daily_summary = {
            "total_days": len(daily_records),
            "target_sla_pct": target_sla_pct,
            "total_obs_min": round(total_obs_sec / 60.0, 1),
            "total_cpu_modem_uptime_min": total_cpu_up_min,
            "total_cpu_modem_downtime_min": total_cpu_down_min,
            "avg_cpu_modem_success_rate": avg_cpu_sr,
            "cpu_modem_sla_status": "Tercapai" if avg_cpu_sr >= target_sla_pct else "Tidak Tercapai",
            "total_cellular_uptime_min": total_cell_up_min,
            "total_cellular_downtime_min": total_cell_down_min,
            "avg_cellular_success_rate": avg_cell_sr,
            "cellular_sla_status": "Tercapai" if avg_cell_sr >= target_sla_pct else "Tidak Tercapai",
            "total_cpu_dvr_uptime_min": total_dvr_up_min,
            "total_cpu_dvr_downtime_min": total_dvr_down_min,
            "avg_cpu_dvr_success_rate": avg_dvr_sr,
            "cpu_dvr_sla_status": "Tercapai" if avg_dvr_sr >= target_sla_pct else "Tidak Tercapai",
            "total_rec_uptime_min": total_rec_up_min,
            "total_rec_downtime_min": total_rec_down_min,
            "avg_rec_success_rate": avg_rec_sr,
            "rec_sla_status": "Tercapai" if avg_rec_sr >= target_sla_pct else "Tidak Tercapai",
        }

        return daily_records, daily_summary

        return daily_records, daily_summary


sla_calculator_service = SLACalculatorService()
