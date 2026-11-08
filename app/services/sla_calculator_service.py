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


def _to_wib_str(dt: Optional[datetime], fmt: str = "%Y-%m-%d %H:%M:%S WIB") -> str:
    """Mengonversi UTC/naive datetime dari database ke jam lokal WIB (UTC+7)."""
    if not dt:
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(WIB).strftime(fmt)


def get_default_period_str(reference_dt: Optional[datetime] = None) -> str:
    """
    Menghasilkan string rentang tanggal bulan aktif berjalan dari tanggal 01 sampai hari ini (WIB) secara dinamis.
    Misal hari ini 05 Nov 2026 -> '01 Nov 2026 - 05 Nov 2026'.
    """
    if not reference_dt:
        reference_dt = datetime.now(timezone.utc).astimezone(WIB)
    year = reference_dt.year
    mon_name = reference_dt.strftime("%b")
    today_day = reference_dt.day
    return f"01 {mon_name} {year} - {today_day:02d} {mon_name} {year}"


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
    def _to_english_incident_desc(desc: Optional[str], metric: Optional[str] = None) -> str:
        """Converts Indonesian alert/incident descriptions into clean professional English."""
        if not desc:
            if metric == "cpu_modem":
                return "Modem USB Port Communication Lost ([MODEM-CPU: TERPUTUS])"
            elif metric == "cellular":
                return "Cellular Network Connection Disconnected (No Internet Data / CSQ 99)"
            elif metric in ["dvr", "cpu_dvr"]:
                return "Gateway CPU to NVR Communication Lost (NVR: OFFLINE)"
            elif metric == "recording":
                return "CCTV Cameras Not Recording"
            return "Normal Operation (No incidents detected)"

        t = str(desc)
        t = re.sub(r'Komunikasi\s+Port\s+USB\s+Modem\s+dengan\s+CPU\s+Terputus', 'Modem USB Port Communication Lost', t, flags=re.IGNORECASE)
        t = re.sub(r'Koneksi\s+Jaringan\s+Seluler\s+Terputus', 'Cellular Network Connection Disconnected', t, flags=re.IGNORECASE)
        t = re.sub(r'Aliran\s+Data\s+Internet\s+Mati', 'No Internet Data', t, flags=re.IGNORECASE)
        t = re.sub(r'Komunikasi\s+Gateway\s+CPU\s+ke\s+NVR\s+Surveillance\s+Terputus', 'Gateway CPU to NVR Communication Lost', t, flags=re.IGNORECASE)
        t = re.sub(r'Kamera\s+Hilang\s+Sinyal\s*/\s*No\s+Video', 'Camera Signal Loss / No Video', t, flags=re.IGNORECASE)
        t = re.sub(r'Kamera\s+Terputus\s*/\s*Offline', 'Camera Disconnected / Offline', t, flags=re.IGNORECASE)
        t = re.sub(r'Gangguan\s+Jaringan', 'Network Disruption', t, flags=re.IGNORECASE)
        t = re.sub(r'Gangguan', 'Incident', t, flags=re.IGNORECASE)
        t = re.sub(r'selama\s+(\d+)\s*Menit', r'for \1m', t, flags=re.IGNORECASE)
        t = re.sub(r'selama\s+(\d+)\s*Jam\s*(\d+)\s*Menit', r'for \1h \2m', t, flags=re.IGNORECASE)
        t = re.sub(r'selama\s+(\d+)\s*Jam', r'for \1h', t, flags=re.IGNORECASE)
        t = re.sub(r'(\d+)\s*Menit', r'\1m', t, flags=re.IGNORECASE)
        t = re.sub(r'(\d+)\s*Jam', r'\1h', t, flags=re.IGNORECASE)
        t = re.sub(r'Normal\s+Operation\s*\(No incidents detected\)', 'Normal Operation (No incidents detected)', t, flags=re.IGNORECASE)
        t = re.sub(r'Operasi\s+Normal', 'Normal Operation', t, flags=re.IGNORECASE)
        return t

    @staticmethod
    def parse_system_log_line(line_str: str) -> Tuple[Optional[str], Optional[bool], Optional[bool], Optional[bool], Optional[bool], float, Dict[int, str]]:
        """
        Parses a single log line from recent_system_logs:
        Returns:
            (ts_str, cpu_down, net_down, dvr_down, is_rec, rec_loss_ratio, cam_statuses)
        """
        m = re.search(r'\[(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})\]', line_str)
        if not m:
            return None, None, None, None, None, 0.0, {}
        ts_str = m.group(1)

        # 1. CPU - Modem & Gateway Heartbeat
        cpu_down = None
        if "[MODEM-CPU: TERPUTUS]" in line_str:
            cpu_down = True
        elif "[MODEM-CPU: OK]" in line_str or "[MQTT OK]" in line_str:
            cpu_down = False
        elif "[MQTT FAIL]" in line_str or "[MQTT ERROR]" in line_str:
            cpu_down = True

        # 2. Network Connection
        net_down = None
        if "[SIM: N/A (Modem Terputus)]" in line_str or re.search(r'\[SIM:\s*N/A\s*\(Modem Terputus\)', line_str, re.IGNORECASE):
            net_down = False  # Opsi E: Excluded from network downtime
        elif re.search(r'\[SIM:\s*[^\\\]]*\(4G\s*LTE,\s*CSQ\s*([1-9]|[1-2][0-9]|3[0-1])\)', line_str, re.IGNORECASE):
            net_down = False  # Opsi A
        elif "[SIM:" in line_str:
            net_down = True   # Opsi B, C, D, F

        # 3. CPU – DVR Communication & CCTV Recording
        # Parameter CPU-DVR: [NVR-CPU: OK] -> Uptime (dvr_down=False). Selain itu -> Downtime (dvr_down=True).
        dvr_down = None
        is_rec = None
        rec_loss_ratio = 0.0
        cam_statuses: Dict[int, str] = {}

        if "[NVR-CPU: OK]" in line_str:
            dvr_down = False
        elif "[NVR-CPU:" in line_str:
            dvr_down = True
        elif "NVR:" in line_str:
            nvr_m = re.search(r'NVR:\s*([^\|]+)', line_str)
            if nvr_m:
                nvr_val = nvr_m.group(1).strip().upper()
                dvr_down = ("OFFLINE" in nvr_val)

        # Parameter NVR RECORDING:
        # Format: NVR RECORDING: (CAMERA 1 : NOT_RECORD, CAMERA 2 : NOT_RECORD, CAMERA 3 : NOT_RECORD, CAMERA 4 : NOT_RECORD)
        rec_m = re.search(r'NVR\s+RECORDING:\s*\((.*?)\)', line_str, re.IGNORECASE)
        if rec_m:
            cams_str = rec_m.group(1)
            cam_matches = re.findall(r'CAMERA\s+(\d+)\s*:\s*([A-Za-z0-9_]+)', cams_str, re.IGNORECASE)
            if cam_matches:
                total_cams = len(cam_matches)
                rec_cams = 0
                for cid, cst in cam_matches:
                    cid_int = int(cid)
                    st_upper = cst.upper()
                    cam_statuses[cid_int] = st_upper
                    if "RECORD" in st_upper and "NOT" not in st_upper:
                        rec_cams += 1
                rec_loss_ratio = round((total_cams - rec_cams) / total_cams, 4) if total_cams > 0 else 0.0
                is_rec = (rec_cams > 0)
        elif "NVR RECORDING:" in line_str:
            if any(w in line_str for w in ["TERPUTUS", "LEPAS", "N/A", "OFFLINE"]):
                is_rec = False
                rec_loss_ratio = 1.0
            else:
                is_rec = True
                rec_loss_ratio = 0.0
        elif "NVR:" in line_str:
            nvr_m = re.search(r'NVR:\s*([^\|]+)', line_str)
            if nvr_m:
                nvr_val = nvr_m.group(1).strip().upper()
                if "OFFLINE" in nvr_val:
                    is_rec = False
                    rec_loss_ratio = 1.0
                else:
                    is_rec = ("SEDANG MEREKAM" in nvr_val or "MEREKAM" in nvr_val)
                    rec_loss_ratio = 0.0 if is_rec else 1.0

        return ts_str, cpu_down, net_down, dvr_down, is_rec, rec_loss_ratio, cam_statuses

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
        - Uptime: [NVR-CPU: OK]
        - Downtime: [NVR-CPU: TERPUTUS] / any NVR-CPU not OK / NVR: OFFLINE
        3. CCTV Recording:
        - Parsed from NVR RECORDING: (CAMERA 1 : RECORD/NOT_RECORD, ...)
        4. Network Connection (SIM):
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
                if isinstance(line, str) and ("[MODEM-CPU:" in line or "[NVR-CPU:" in line or "NVR:" in line or "[SIM:" in line):
                    latest_log = line
                    break
        elif isinstance(logs, str) and logs.strip():
            for line in reversed(logs.strip().split("\n")):
                if "[MODEM-CPU:" in line or "[NVR-CPU:" in line or "NVR:" in line or "[SIM:" in line:
                    latest_log = line.strip()
                    break

        cpu_modem_up: Optional[bool] = None
        network_up: Optional[bool] = None
        cpu_dvr_up: Optional[bool] = None
        is_recording: Optional[bool] = None

        if latest_log:
            # 1. CPU - Modem & Gateway Heartbeat
            if "[MODEM-CPU: OK]" in latest_log or "[MQTT OK]" in latest_log:
                cpu_modem_up = True
            elif "[MODEM-CPU: TERPUTUS]" in latest_log or "[MQTT FAIL]" in latest_log or "[MQTT ERROR]" in latest_log:
                cpu_modem_up = False

            # 2. CPU – DVR Communication
            if "[NVR-CPU: OK]" in latest_log:
                cpu_dvr_up = True
            elif "[NVR-CPU:" in latest_log:
                cpu_dvr_up = False
            else:
                nvr_match = re.search(r'NVR:\s*([^\|]+)', latest_log)
                if nvr_match:
                    nvr_val = nvr_match.group(1).strip().upper()
                    cpu_dvr_up = ("OFFLINE" not in nvr_val)

            # CCTV Recording
            rec_m = re.search(r'NVR\s+RECORDING:\s*\((.*?)\)', latest_log, re.IGNORECASE)
            if rec_m:
                cams_str = rec_m.group(1)
                cam_matches = re.findall(r'CAMERA\s+(\d+)\s*:\s*([A-Za-z0-9_]+)', cams_str, re.IGNORECASE)
                if cam_matches:
                    rec_cams = sum(1 for cid, cst in cam_matches if "RECORD" in cst.upper() and "NOT" not in cst.upper())
                    is_recording = (rec_cams > 0)
            elif "NVR RECORDING:" in latest_log:
                is_recording = not any(w in latest_log for w in ["TERPUTUS", "LEPAS", "N/A", "OFFLINE"])
            elif "NVR:" in latest_log:
                nvr_match = re.search(r'NVR:\s*([^\|]+)', latest_log)
                if nvr_match:
                    nvr_val = nvr_match.group(1).strip().upper()
                    if "OFFLINE" in nvr_val:
                        is_recording = False
                    else:
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

    def _extract_minute_health_trends(
        self,
        rows: Optional[List[Any]] = None,
        live_payload: Optional[Dict[str, Any]] = None
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, Any]]:
        """Extracts real per-minute CPU, RAM, and Disk telemetry trends from recent_system_logs and database history."""
        minute_health_map: Dict[str, Dict[str, Any]] = {}

        all_logs_sources = []
        if live_payload and live_payload.get("recent_system_logs"):
            all_logs_sources.append(live_payload.get("recent_system_logs"))
        if rows:
            for r in rows:
                logs = r.raw_payload.get("recent_system_logs") if (r and r.raw_payload) else None
                if logs:
                    all_logs_sources.append(logs)

        for logs in all_logs_sources:
            if isinstance(logs, str):
                logs = logs.strip().split("\n")
            for line in logs:
                line_str = str(line)
                ts_m = re.search(r'\[(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2}):\d{2}\]', line_str)
                if not ts_m:
                    continue
                date_part = ts_m.group(1)  # YYYY-MM-DD
                time_part = ts_m.group(2)  # HH:MM
                min_k = f"{date_part} {time_part}"
                if min_k in minute_health_map:
                    continue

                cpu_m = re.search(r'CPU:\s*([0-9\.]+)\%', line_str)
                ram_m = re.search(r'RAM:\s*([0-9\.]+)\%', line_str)
                disk_m = re.search(r'Disk\s*/?\s*:\s*([0-9\.]+)\%', line_str)

                c_val = float(cpu_m.group(1)) if cpu_m else None
                r_val = float(ram_m.group(1)) if ram_m else None
                d_val = float(disk_m.group(1)) if disk_m else None

                if c_val is not None or r_val is not None or d_val is not None:
                    try:
                        dt_obj = datetime.strptime(date_part, "%Y-%m-%d")
                        day_num = dt_obj.day
                        date_key = dt_obj.strftime("%d %b")
                    except Exception:
                        day_num = 1
                        date_key = date_part

                    minute_health_map[min_k] = {
                        "date": f"{date_key} {time_part}",
                        "time": time_part,
                        "day": day_num,
                        "date_key": date_key,
                        "cpu": round(c_val, 1) if c_val is not None else 0,
                        "ram": round(r_val, 1) if r_val is not None else 0,
                        "disk": round(d_val, 1) if d_val is not None else 0,
                    }

        cpu_trend = []
        ram_trend = []
        sd_trend = []

        if minute_health_map:
            for k in sorted(minute_health_map.keys()):
                item = minute_health_map[k]
                cpu_trend.append({"date": item["date"], "time": item["time"], "day": item["day"], "date_key": item["date_key"], "value": item["cpu"]})
                ram_trend.append({"date": item["date"], "time": item["time"], "day": item["day"], "date_key": item["date_key"], "value": item["ram"]})
                sd_trend.append({"date": item["date"], "time": item["time"], "day": item["day"], "date_key": item["date_key"], "value": item["disk"]})
        elif rows:
            step = max(1, len(rows) // 30)
            sampled = rows[::step]
            if rows[-1] not in sampled:
                sampled.append(rows[-1])

            for r in sampled:
                r_wib = r.recorded_at.replace(tzinfo=timezone.utc).astimezone(WIB) if r.recorded_at.tzinfo is None else r.recorded_at.astimezone(WIB)
                time_str = r_wib.strftime("%H:%M")
                day_num = r_wib.day
                date_key = r_wib.strftime("%d %b")
                dt_label = f"{date_key} {time_str}"

                c_val = int(round(r.cpu_percent or 0))
                ram_pct = int(round((r.ram_used_mb / r.ram_total_mb * 100))) if r.ram_total_mb else 25
                d_val = int(round(r.disk_used_percent or 50))

                cpu_trend.append({"date": dt_label, "time": time_str, "day": day_num, "date_key": date_key, "value": c_val})
                ram_trend.append({"date": dt_label, "time": time_str, "day": day_num, "date_key": date_key, "value": ram_pct})
                sd_trend.append({"date": dt_label, "time": time_str, "day": day_num, "date_key": date_key, "value": d_val})
        elif live_payload:
            now_dt = datetime.now(WIB)
            time_str = now_dt.strftime("%H:%M")
            day_num = now_dt.day
            date_key = now_dt.strftime("%d %b")
            dt_label = f"{date_key} {time_str}"
            c_val = round(float(live_payload.get("gateway_system", {}).get("cpu", {}).get("usage_percent", 0)), 1)
            r_val = round(float(live_payload.get("gateway_system", {}).get("memory", {}).get("usage_percent", 0)), 1)
            d_val = round(float(live_payload.get("flash_storage", {}).get("disk_usage", {}).get("root_used_percent", 0)), 1)
            cpu_trend.append({"date": dt_label, "time": time_str, "day": day_num, "date_key": date_key, "value": c_val})
            ram_trend.append({"date": dt_label, "time": time_str, "day": day_num, "date_key": date_key, "value": r_val})
            sd_trend.append({"date": dt_label, "time": time_str, "day": day_num, "date_key": date_key, "value": d_val})

        # Collect all points for real historical resource stats (CPU, RAM, Storage)
        all_cpus: List[float] = []
        all_rams: List[float] = []
        all_disks: List[float] = []

        if minute_health_map:
            for item in minute_health_map.values():
                if item.get("cpu") is not None:
                    all_cpus.append(float(item["cpu"]))
                if item.get("ram") is not None:
                    all_rams.append(float(item["ram"]))
                if item.get("disk") is not None:
                    all_disks.append(float(item["disk"]))
        elif rows:
            for r in rows:
                if r.cpu_percent is not None:
                    all_cpus.append(float(r.cpu_percent))
                if r.ram_used_mb is not None and r.ram_total_mb:
                    all_rams.append(float(round(r.ram_used_mb / r.ram_total_mb * 100.0, 1)))
                if r.disk_used_percent is not None:
                    all_disks.append(float(r.disk_used_percent))

        live_cpu = float(live_payload.get("gateway_system", {}).get("cpu", {}).get("usage_percent", 25.0)) if live_payload else 25.0
        live_ram = float(live_payload.get("gateway_system", {}).get("memory", {}).get("usage_percent", 35.0)) if live_payload else 35.0
        live_disk = float(live_payload.get("flash_storage", {}).get("partitions", [{}])[0].get("used_percent", 50.0)) if live_payload else 50.0

        if not all_cpus and live_cpu is not None:
            all_cpus.append(live_cpu)
        if not all_rams and live_ram is not None:
            all_rams.append(live_ram)
        if not all_disks and live_disk is not None:
            all_disks.append(live_disk)

        avg_cpu = round(sum(all_cpus) / len(all_cpus), 1) if all_cpus else round(live_cpu, 1)
        max_cpu = round(max(all_cpus), 1) if all_cpus else avg_cpu
        gt_80_cpu_mins = len([v for v in all_cpus if v > 80.0])
        cpu_gt_80_str = f"{gt_80_cpu_mins // 60}h {gt_80_cpu_mins % 60}m" if gt_80_cpu_mins > 0 else "-"

        avg_ram = round(sum(all_rams) / len(all_rams), 1) if all_rams else round(live_ram, 1)
        max_ram = round(max(all_rams), 1) if all_rams else avg_ram
        gt_80_ram_mins = len([v for v in all_rams if v > 80.0])
        ram_gt_80_str = f"{gt_80_ram_mins // 60}h {gt_80_ram_mins % 60}m" if gt_80_ram_mins > 0 else "-"

        avg_sd = round(sum(all_disks) / len(all_disks), 1) if all_disks else round(live_disk, 1)
        max_sd = round(max(all_disks), 1) if all_disks else avg_sd
        gt_90_sd_mins = len([v for v in all_disks if v > 90.0])
        sd_gt_90_str = f"{gt_90_sd_mins // 60}h {gt_90_sd_mins % 60}m" if gt_90_sd_mins > 0 else "-"

        health_stats = {
            "cpu_avg": int(round(avg_cpu)),
            "cpu_max": int(round(max_cpu)),
            "cpu_gt_80_duration": cpu_gt_80_str,
            "ram_avg": int(round(avg_ram)),
            "ram_max": int(round(max_ram)),
            "ram_gt_80_duration": ram_gt_80_str,
            "sd_avg": int(round(avg_sd)),
            "sd_max": int(round(max_sd)),
            "sd_gt_90_duration": sd_gt_90_str,
        }

        return cpu_trend, ram_trend, sd_trend, health_stats

    def calculate_device_sla(
        self,
        device_id: str,
        live_payload: Optional[Dict[str, Any]] = None,
        date_range_str: Optional[str] = None,
        date_range: Optional[str] = None,
    ) -> Dict[str, Any]:
        if not date_range_str and date_range:
            date_range_str = date_range

        # 1. Fast in-memory cache check (45s TTL)
        import time as _time
        now_ts = _time.time()
        cache_key = f"{device_id}_{date_range_str or ''}"
        if hasattr(self, "_sla_mem_cache") and cache_key in self._sla_mem_cache:
            entry_ts, cached_val = self._sla_mem_cache[cache_key]
            if (now_ts - entry_ts) < 45.0:
                return cached_val

        # 2. Database connection circuit breaker to prevent blocking socket timeouts
        db_available = getattr(self, "_db_available", True)
        last_db_err = getattr(self, "_last_db_err_time", 0.0)
        db = None
        if db_available or (now_ts - last_db_err) >= 30.0:
            try:
                db = SessionLocal()
            except Exception:
                self._db_available = False
                self._last_db_err_time = now_ts
                db = None

        rows: List[GatewayTelemetryHistory] = []
        alerts: List[GatewayIncidentAlert] = []
        start_dt, end_dt = self._parse_date_range(date_range_str)
        if db:
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
                        (GatewayIncidentAlert.start_time >= s_utc) & (GatewayIncidentAlert.start_time <= e_utc)
                    )
                else:
                    rows = query.order_by(GatewayTelemetryHistory.recorded_at.asc()).all()
                alerts = alert_q.order_by(GatewayIncidentAlert.start_time.desc()).all()
                self._db_available = True
            except Exception as e:
                self._db_available = False
                self._last_db_err_time = _time.time()
                logger.debug(f"Error querying telemetry/alert history for {device_id}: {e}")
            finally:
                try:
                    db.close()
                except Exception:
                    pass

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

        for idx, al in enumerate(alerts, 1):
            st_str = _to_wib_str(al.start_time, fmt="%Y-%m-%d %H:%M:%S WIB")
            et_str = _to_wib_str(al.end_time, fmt="%Y-%m-%d %H:%M:%S WIB") if al.end_time else "Active"
            
            dur_m = round(al.duration_minutes or 0)
            if al.duration_minutes and al.duration_minutes > 0:
                if dur_m >= 60:
                    dur_str = f"{dur_m // 60}h {dur_m % 60}m" if dur_m % 60 else f"{dur_m // 60}h"
                else:
                    dur_str = f"{dur_m}m"
            elif al.duration_str:
                dur_str = al.duration_str.replace("Menit", "m").replace("menit", "m").replace("Jam", "h").replace("jam", "h").replace("Detik", "s").replace("detik", "s").strip()
            else:
                dur_str = "1m"

            cat_label = "CPU - Modem" if al.metric == "cpu_modem" else ("Cellular Network" if al.metric == "cellular" else ("CCTV Recording" if al.metric == "recording" else "CPU - DVR"))
            date_key = (al.start_time + timedelta(hours=7)).strftime("%Y-%m-%d") if al.start_time else None
            desc_en = self._to_english_incident_desc(al.description, al.metric)

            ev_epoch = 0.0
            if al.start_time:
                ev_epoch = al.start_time.replace(tzinfo=timezone.utc).timestamp() if al.start_time.tzinfo is None else al.start_time.timestamp()

            trouble_events.append({
                "no": idx,
                "start_time": st_str,
                "end_time": et_str,
                "duration": dur_str,
                "duration_minutes": al.duration_minutes or 0.0,
                "category": cat_label,
                "metric": al.metric,
                "date_str": date_key,
                "day_downtime_minutes": al.duration_minutes or 0.0,
                "title": desc_en,
                "description": desc_en,
                "cause": desc_en,
                "reason": desc_en,
                "status": "Resolved" if al.status == "RESOLVED" else "Active",
                "telemetry_history_id": al.telemetry_history_id,
                "_raw_dt": al.start_time,
                "epoch": ev_epoch,
            })


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
                target_sla_pct=98.0,
                live_payload=live_payload,
                kernel_uptime_sec=kernel_uptime_sec,
            )

            if daily_summary and daily_summary.get("total_obs_min"):
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

            cpu_trend, ram_trend, sd_trend, health_stats = self._extract_minute_health_trends(rows=rows, live_payload=live_payload)

            res = {
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
                    {"track_name": "Gateway", "segments": [{"status": "online" if m_ok else "offline", "start_pct": 0, "width_pct": 100, "label": "Online" if m_ok else "Disconnected", "period": "Live"}]},
                    {"track_name": "Cellular", "segments": [{"status": "online" if net_ok else "offline", "start_pct": 0, "width_pct": 100, "label": "Online" if net_ok else "No Signal/SIM", "period": "Live"}]},
                    {"track_name": "DVR", "segments": [{"status": "online" if dvr_ok else "offline", "start_pct": 0, "width_pct": 100, "label": "Connected" if dvr_ok else "Offline", "period": "Live"}]},
                ],
                "avg_temp": 42,
                "avg_rsrp": -85,
                "avg_ping": round(float(live_payload.get("cellular_sim", {}).get("data_traffic", {}).get("ping_ms")), 1) if (live_payload and live_payload.get("cellular_sim", {}).get("data_traffic", {}).get("ping_ms") is not None) else None,
                "cpu_trend": cpu_trend,
                "ram_trend": ram_trend,
                "sd_trend": sd_trend,
                "daily_breakdown": daily_breakdown,
                "daily_summary": daily_summary,
            }
            res.update(health_stats)
            return res

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
                raw_gw_segments.append({"status": "offline", "duration": gap_sec, "label": "Modem-CPU Disconnected", "period": f"{curr_time_str} - {next_time_str}"})
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

        # Collect trend points from real minute system logs or telemetry rows
        cpu_trend, ram_trend, sd_trend, health_stats = self._extract_minute_health_trends(rows=rows, live_payload=live_payload)

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
            target_sla_pct=98.0,
            live_payload=live_payload,
            kernel_uptime_sec=kernel_uptime_sec,
        )

        if daily_summary and daily_summary.get("total_obs_min"):
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

        result = {
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
        result.update(health_stats)

        if not hasattr(self, "_sla_mem_cache"):
            self._sla_mem_cache = {}
        self._sla_mem_cache[cache_key] = (now_ts, result)
        return result

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
        target_sla_pct: float = 98.0,
        live_payload: Optional[Dict[str, Any]] = None,
        kernel_uptime_sec: int = 0
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """
        Menghasilkan rincian SLA harian (Day 1..Day N) dengan algoritma Daily Time-Slicing:
        - Hari kalender dihitung dari kemunculan data pertama / waktu boot perangkat (bukan tanggal 1 jika perangkat belum ada).
        - Hari berjalan (hari ini) dihitung kuota berjalannya (misal 72.8m), bukan 1.440 menit.
        - Kuota observasi per hari: day_obs_sec = d_end - d_start.
        - Persamaan mutlak: Uptime + Downtime = Observasi.
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
            s_date = datetime(ref_dt.year, ref_dt.month, 1).date()
            if ref_dt.year == now_wib.year and ref_dt.month == now_wib.month:
                e_date = now_wib.date()
            else:
                _, last_day = calendar.monthrange(ref_dt.year, ref_dt.month)
                e_date = datetime(ref_dt.year, ref_dt.month, last_day).date()

        # 1. Collect all candidate timestamps to determine the device's true first active datetime
        candidate_dts: List[datetime] = []
        if kernel_uptime_sec and kernel_uptime_sec > 0:
            candidate_dts.append(now_wib - timedelta(seconds=kernel_uptime_sec))

        if rows:
            for r in rows:
                if r.recorded_at:
                    r_dt = r.recorded_at.replace(tzinfo=timezone.utc).astimezone(WIB) if r.recorded_at.tzinfo is None else r.recorded_at.astimezone(WIB)
                    candidate_dts.append(r_dt)

        if alerts:
            for a in alerts:
                if a.start_time:
                    a_dt = a.start_time.replace(tzinfo=timezone.utc).astimezone(WIB) if a.start_time.tzinfo is None else a.start_time.astimezone(WIB)
                    candidate_dts.append(a_dt)

        if live_payload:
            rec_str = live_payload.get("recorded_at") or live_payload.get("datetime_utc7")
            if rec_str:
                try:
                    clean_rec = str(rec_str).split(" (")[0].strip()
                    candidate_dts.append(datetime.strptime(clean_rec[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=WIB))
                except Exception:
                    pass

        # 2. Pre-parse all unique minute system logs across rows AND live_payload for exact outage accounting
        unique_day_logs: Dict[str, Dict[str, Any]] = {}
        all_log_sources: List[Any] = []
        if rows:
            for r in rows:
                logs = r.raw_payload.get("recent_system_logs") if (r and r.raw_payload) else None
                if logs:
                    all_log_sources.append(logs)
        if live_payload and live_payload.get("recent_system_logs"):
            all_log_sources.append(live_payload.get("recent_system_logs"))

        for logs in all_log_sources:
            if isinstance(logs, str):
                logs = logs.strip().split("\n")
            for line in logs:
                parsed = self.parse_system_log_line(str(line))
                ts_str, c_down, n_down, d_down, rec = parsed[:5]
                rec_loss = parsed[5] if len(parsed) > 5 else (0.0 if rec else 1.0)
                cam_statuses = parsed[6] if len(parsed) > 6 else {}

                if ts_str:
                    try:
                        candidate_dts.append(datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=WIB))
                    except Exception:
                        pass

                if ts_str and (c_down is not None or n_down is not None or d_down is not None or rec is not None):
                    d_key = ts_str[:10]  # YYYY-MM-DD
                    min_k = ts_str[:16]  # YYYY-MM-DD HH:MM
                    if d_key not in unique_day_logs:
                        unique_day_logs[d_key] = {}
                    if min_k not in unique_day_logs[d_key]:
                        unique_day_logs[d_key][min_k] = [
                            bool(c_down),
                            bool(n_down),
                            bool(d_down),
                            float(rec_loss),
                            cam_statuses,
                        ]
                    else:
                        if c_down is not None and c_down:
                            unique_day_logs[d_key][min_k][0] = True
                        if n_down is not None and n_down:
                            unique_day_logs[d_key][min_k][1] = True
                        if d_down is not None and d_down:
                            unique_day_logs[d_key][min_k][2] = True
                        if rec_loss > unique_day_logs[d_key][min_k][3]:
                            unique_day_logs[d_key][min_k][3] = float(rec_loss)
                            if cam_statuses:
                                unique_day_logs[d_key][min_k][4] = cam_statuses

        # 3. Determine device's first active datetime: never calculate fake observation days before device existed
        device_first_dt: Optional[datetime] = min(candidate_dts) if candidate_dts else None
        if device_first_dt:
            s_date = max(s_date, device_first_dt.date())
        if s_date > e_date:
            s_date = e_date

        daily_records: List[Dict[str, Any]] = []
        cur_date = s_date
        total_cpu_down_sec = 0.0
        total_cell_down_sec = 0.0
        total_dvr_down_sec = 0.0
        total_rec_down_sec = 0.0
        total_obs_sec = 0.0

        # Pre-process alerts for fallback intervals
        cpu_raw: List[Tuple[datetime, datetime]] = []
        cell_raw: List[Tuple[datetime, datetime]] = []
        dvr_raw: List[Tuple[datetime, datetime]] = []
        if alerts:
            for a in alerts:
                if a.start_time and a.end_time and a.end_time > a.start_time:
                    s = a.start_time.astimezone(WIB) if a.start_time.tzinfo else a.start_time.replace(tzinfo=timezone.utc).astimezone(WIB)
                    e = a.end_time.astimezone(WIB) if a.end_time.tzinfo else a.end_time.replace(tzinfo=timezone.utc).astimezone(WIB)
                    if a.metric == "cpu_modem":
                        cpu_raw.append((s, e))
                    elif a.metric == "cellular":
                        cell_raw.append((s, e))
                    elif a.metric == "cpu_dvr":
                        dvr_raw.append((s, e))
        cpu_merged = self._merge_intervals(cpu_raw)
        cell_merged = self._merge_intervals(cell_raw)
        dvr_merged = self._merge_intervals(dvr_raw)

        while cur_date <= e_date:
            d_start = datetime(cur_date.year, cur_date.month, cur_date.day, 0, 0, 0, tzinfo=WIB)
            d_end = datetime(cur_date.year, cur_date.month, cur_date.day, 23, 59, 59, tzinfo=WIB)
            d_str = cur_date.strftime("%Y-%m-%d")

            # On first active day: observation starts at first active boot/registration time
            if device_first_dt and cur_date == device_first_dt.date():
                d_start = max(d_start, device_first_dt)

            # On current ongoing day (today): observation ends at current time
            if cur_date == now_wib.date():
                d_end = min(d_end, now_wib)

            day_obs_sec = min(86400.0, max(60.0, (d_end - d_start).total_seconds()))
            day_quota_min = round(day_obs_sec / 60.0, 1)

            day_cpu_down_sec = 0.0
            day_cell_down_sec = 0.0
            day_dvr_down_sec = 0.0
            day_rec_down_sec = 0.0
            rec_channels_info = "4 / 4 Cams"

            if cur_date > now_wib.date():
                pass
            elif d_str in unique_day_logs and unique_day_logs[d_str]:
                # Primary Path: 100% exact minute logs captured by gateway daemon buffer
                day_mins = unique_day_logs[d_str]
                day_cpu_down_sec = sum(60.0 for v in day_mins.values() if v[0])
                day_cell_down_sec = sum(60.0 for v in day_mins.values() if v[1])
                day_dvr_down_sec = sum(60.0 for v in day_mins.values() if v[2])
                day_rec_down_sec = sum(60.0 * float(v[3]) for v in day_mins.values())

                day_cams = [v[4] for v in day_mins.values() if len(v) > 4 and v[4]]
                if day_cams:
                    last_cams = day_cams[-1]
                    tot_c = len(last_cams)
                    rec_c = sum(1 for st in last_cams.values() if "RECORD" in str(st).upper() and "NOT" not in str(st).upper())
                    rec_channels_info = f"{rec_c} / {tot_c} Cams"
                elif day_rec_down_sec >= day_obs_sec:
                    rec_channels_info = "0 / 4 Cams"
            elif rows and len(rows) >= 2:
                for i in range(len(rows) - 1):
                    curr_r = rows[i]
                    next_r = rows[i + 1]
                    t1 = curr_r.recorded_at.replace(tzinfo=timezone.utc).astimezone(WIB) if curr_r.recorded_at.tzinfo is None else curr_r.recorded_at.astimezone(WIB)
                    t2 = next_r.recorded_at.replace(tzinfo=timezone.utc).astimezone(WIB) if next_r.recorded_at.tzinfo is None else next_r.recorded_at.astimezone(WIB)
                    overlap_s = max(t1, d_start)
                    overlap_e = min(t2, d_end)
                    if overlap_e > overlap_s:
                        dur = (overlap_e - overlap_s).total_seconds()
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
            elif alerts:
                for s, e in cpu_merged:
                    overlap_s = max(s, d_start)
                    overlap_e = min(e, d_end)
                    if overlap_e > overlap_s:
                        day_cpu_down_sec += (overlap_e - overlap_s).total_seconds()
                for s, e in cell_merged:
                    overlap_s = max(s, d_start)
                    overlap_e = min(e, d_end)
                    if overlap_e > overlap_s:
                        day_cell_down_sec += (overlap_e - overlap_s).total_seconds()
                for s, e in dvr_merged:
                    overlap_s = max(s, d_start)
                    overlap_e = min(e, d_end)
                    if overlap_e > overlap_s:
                        day_dvr_down_sec += (overlap_e - overlap_s).total_seconds()
                day_rec_down_sec = day_dvr_down_sec

            # Clamp downtimes strictly within actual day observation seconds
            day_cpu_down_sec = min(day_obs_sec, max(0.0, day_cpu_down_sec))
            day_cell_down_sec = min(day_obs_sec, max(0.0, day_cell_down_sec))
            day_dvr_down_sec = min(day_obs_sec, max(0.0, day_dvr_down_sec))
            day_rec_down_sec = min(day_obs_sec, max(0.0, day_rec_down_sec))

            cpu_down_min = round(day_cpu_down_sec / 60.0, 1)
            cpu_up_min = round(max(0.0, day_quota_min - cpu_down_min), 1)
            cpu_sr = round(max(0.0, min(100.0, (cpu_up_min / day_quota_min * 100.0))), 1) if day_quota_min > 0 else 100.0
            cpu_sla_diff = round(cpu_sr - target_sla_pct, 1)
            cpu_status = "Achieved" if cpu_sr >= target_sla_pct else "Not Achieved"

            cell_down_min = round(day_cell_down_sec / 60.0, 1)
            cell_up_min = round(max(0.0, day_quota_min - cell_down_min), 1)
            cell_sr = round(max(0.0, min(100.0, (cell_up_min / day_quota_min * 100.0))), 1) if day_quota_min > 0 else 100.0
            cell_sla_diff = round(cell_sr - target_sla_pct, 1)
            cell_status = "Achieved" if cell_sr >= target_sla_pct else "Not Achieved"

            dvr_down_min = round(day_dvr_down_sec / 60.0, 1)
            dvr_up_min = round(max(0.0, day_quota_min - dvr_down_min), 1)
            dvr_sr = round(max(0.0, min(100.0, (dvr_up_min / day_quota_min * 100.0))), 1) if day_quota_min > 0 else 100.0
            dvr_sla_diff = round(dvr_sr - target_sla_pct, 1)
            dvr_status = "Achieved" if dvr_sr >= target_sla_pct else "Not Achieved"

            rec_down_min = round(day_rec_down_sec / 60.0, 1)
            rec_up_min = round(max(0.0, day_quota_min - rec_down_min), 1)
            rec_sr = round(max(0.0, min(100.0, (rec_up_min / day_quota_min * 100.0))), 1) if day_quota_min > 0 else 100.0
            rec_sla_diff = round(rec_sr - target_sla_pct, 1)
            rec_status = "Achieved" if rec_sr >= target_sla_pct else "Not Achieved"

            daily_records.append({
                "day": cur_date.day,
                "date": cur_date.strftime("%d %b %Y"),
                "day_name": cur_date.strftime("%a"),
                "target_sla": target_sla_pct,
                "observation_min": day_quota_min,

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
                "rec_channels": rec_channels_info,
                "rec_condition": "Full Recording" if rec_sr >= target_sla_pct else ("Partial Recording" if rec_sr > 0 else "Not Recording"),
            })

            total_cpu_down_sec += day_cpu_down_sec
            total_cell_down_sec += day_cell_down_sec
            total_dvr_down_sec += day_dvr_down_sec
            total_rec_down_sec += day_rec_down_sec
            total_obs_sec += day_obs_sec

            cur_date += timedelta(days=1)

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
            "cpu_modem_sla_status": "Achieved" if avg_cpu_sr >= target_sla_pct else "Not Achieved",
            "total_cellular_uptime_min": total_cell_up_min,
            "total_cellular_downtime_min": total_cell_down_min,
            "avg_cellular_success_rate": avg_cell_sr,
            "cellular_sla_status": "Achieved" if avg_cell_sr >= target_sla_pct else "Not Achieved",
            "total_cpu_dvr_uptime_min": total_dvr_up_min,
            "total_cpu_dvr_downtime_min": total_dvr_down_min,
            "avg_cpu_dvr_success_rate": avg_dvr_sr,
            "cpu_dvr_sla_status": "Achieved" if avg_dvr_sr >= target_sla_pct else "Not Achieved",
            "total_rec_uptime_min": total_rec_up_min,
            "total_rec_downtime_min": total_rec_down_min,
            "avg_rec_success_rate": avg_rec_sr,
            "rec_sla_status": "Achieved" if avg_rec_sr >= target_sla_pct else "Not Achieved",
        }

        return daily_records, daily_summary


sla_calculator_service = SLACalculatorService()
