import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import or_
from app.core.database import SessionLocal
from app.models.base_models import GatewayIncidentAlert
from app.models.notification_models import (
    NotificationEvent,
    NotificationDestination,
    NotificationTarget,
    Notification,
    NotificationDelivery,
)
from app.services.notification.registry import integration_registry

logger = logging.getLogger(__name__)

dispatch_pool = ThreadPoolExecutor(max_workers=5, thread_name_prefix="notif-dispatch")


class NotificationService:
    def __init__(self):
        self.registry = integration_registry
        self._active_outages: Dict[str, Dict[str, Any]] = {}

    def process_telemetry_for_notifications(
        self,
        db: Session,
        dev_id: str,
        loc_name: str,
        payload: Dict[str, Any],
        rec_dt: datetime,
    ):
        if not payload or not isinstance(payload, dict):
            return

        # 0. Recover gateway_offline outage if telemetry resumes
        self._handle_module_recovery(
            db=db,
            dev_id=dev_id,
            loc_name=loc_name,
            metric="gateway",
            rec_dt=rec_dt,
        )

        logs = payload.get("recent_system_logs") or []
        if isinstance(logs, str):
            logs = logs.strip().split("\n")
        logs_str = " ".join(str(l) for l in logs)
        latest_logs = logs[-3:] if len(logs) >= 3 else logs
        latest_str = " ".join(str(l) for l in latest_logs)

        sim = payload.get("cellular_sim", {})
        modem = payload.get("modem_usb", {})

        modem_down = (
            "[MODEM-CPU: TERPUTUS]" in logs_str
            or "[MODEM-CPU: FAIL]" in logs_str
            or "[MODEM-CPU: ERROR]" in logs_str
            or (isinstance(modem, dict) and modem.get("status") in ["FAIL", "DISCONNECTED"])
        )
        modem_up = (
            "[MODEM-CPU: OK]" in latest_str
            or (isinstance(modem, dict) and modem.get("status") in ["OK", "CONNECTED"])
        )

        if modem_down:
            self._handle_module_down(
                db=db,
                dev_id=dev_id,
                loc_name=loc_name,
                metric="cpu_modem",
                rec_dt=rec_dt,
                reason="Port serial USB modul modem terlepas atau komunikasi terputus",
            )
        elif modem_up:
            self._handle_module_recovery(
                db=db,
                dev_id=dev_id,
                loc_name=loc_name,
                metric="cpu_modem",
                rec_dt=rec_dt,
            )

        csq = 0
        if isinstance(sim, dict) and sim.get("signal_csq") is not None:
            try:
                csq = int(sim.get("signal_csq"))
            except (ValueError, TypeError):
                csq = 0
        elif payload.get("signal_csq") is not None:
            try:
                csq = int(payload.get("signal_csq"))
            except (ValueError, TypeError):
                csq = 0

        sim_unplugged = (
            "[SIM: DICABUT" in logs_str
            or "SIM DICABUT" in logs_str
            or "SIM TIDAK TERDETEKSI" in logs_str
            or "SIM: TIDAK TERDETEKSI" in logs_str
            or "[ALERT] Kartu SIM tidak terdeteksi atau dicabut" in logs_str
            or "+CPIN: NOT INSERTED" in logs_str
            or (isinstance(sim, dict) and sim.get("sim_inserted") is False)
            or payload.get("sim_status") in ["NOT_INSERTED", "NOT INSERTED", "REMOVED"]
        )
        data_disconnected = (
            "[SIM: ALIRAN DATA INTERNET TERPUTUS" in logs_str
            or "PPP/QMI DOWN" in logs_str
            or "[ALERT] Koneksi data seluler terputus" in logs_str
            or (isinstance(sim, dict) and isinstance(sim.get("data_traffic"), dict) and sim.get("data_traffic", {}).get("connected") is False)
        )
        signal_lost = (
            "[SIM: TIDAK ADA SINYAL" in logs_str
            or "REGISTRASI JARINGAN GAGAL" in logs_str
            or "TIDAK ADA SINYAL" in logs_str
        )
        signal_bad = (
            "[SIM: KUALITAS SINYAL SANGAT BURUK" in logs_str
            or (csq == 99)
            or (csq == 0 and not sim_unplugged)
        )

        cell_down_reason = None
        if sim_unplugged:
            cell_down_reason = "Kartu SIM tidak terdeteksi atau dicabut dari slot modem"
        elif data_disconnected:
            cell_down_reason = "Aliran data internet terputus (PPP/QMI Down)"
        elif signal_lost:
            cell_down_reason = "Tidak ada sinyal seluler / Registrasi jaringan BTS gagal"
        elif signal_bad:
            cell_down_reason = "Kualitas sinyal sangat buruk (CSQ 99 / drop ekstrem)"

        has_active_sim_flag = (
            (isinstance(sim, dict) and sim.get("sim_inserted") is True)
            or payload.get("sim_status") == "Active"
        )
        cell_up = (
            cell_down_reason is None
            and has_active_sim_flag
            and 1 <= csq <= 31
            and not any(
                "SIM: DICABUT" in str(l)
                or "SIM TIDAK TERDETEKSI" in str(l)
                or "TERPUTUS" in str(l)
                or "CSQ 99" in str(l)
                for l in latest_logs
            )
        )

        if cell_down_reason and not modem_down:
            self._handle_module_down(
                db=db,
                dev_id=dev_id,
                loc_name=loc_name,
                metric="cellular",
                rec_dt=rec_dt,
                reason=cell_down_reason,
            )
        elif cell_up:
            op = (isinstance(sim, dict) and sim.get("operator")) or payload.get("operator") or "Telkomsel"
            sim_info = f"{op} 4G LTE, CSQ {csq}"
            self._handle_module_recovery(
                db=db,
                dev_id=dev_id,
                loc_name=loc_name,
                metric="cellular",
                rec_dt=rec_dt,
                sim_info=sim_info,
            )

        nvr_st = str(payload.get("nvr_status") or "").lower()
        dvr_down = (
            "[NVR-CPU: TERPUTUS]" in logs_str
            or "[NVR: OFFLINE]" in logs_str
            or "NVR: OFFLINE" in logs_str
            or "[ALERT] Komunikasi Gateway CPU ke NVR Surveillance Terputus" in logs_str
            or nvr_st == "offline"
        )
        dvr_up = (
            "[NVR-CPU: OK]" in latest_str
            or "NVR: SEDANG MEREKAM" in latest_str
            or "NVR: STANDBY" in latest_str
            or nvr_st == "online"
        )

        if dvr_down:
            self._handle_module_down(
                db=db,
                dev_id=dev_id,
                loc_name=loc_name,
                metric="cpu_dvr",
                rec_dt=rec_dt,
                reason="Kabel LAN lepas atau NVR mati",
            )
        elif dvr_up:
            self._handle_module_recovery(
                db=db,
                dev_id=dev_id,
                loc_name=loc_name,
                metric="cpu_dvr",
                rec_dt=rec_dt,
            )

        # 4. Camera Loss & NVR Recording Stopped (only evaluate when NVR is connected)
        if not dvr_down:
            nvr_obj = payload.get("nvr_surveillance") or {}
            cams_obj = payload.get("cameras") or nvr_obj.get("cameras") or {}
            rec_obj = payload.get("recording") or nvr_obj.get("recording") or {}
            cam_online = cams_obj.get("online_count")
            cam_total = cams_obj.get("total_cameras")
            if isinstance(cam_online, (int, float)) and isinstance(cam_total, (int, float)) and cam_total > 0:
                if cam_online < cam_total:
                    self._handle_module_down(
                        db=db,
                        dev_id=dev_id,
                        loc_name=loc_name,
                        metric="camera",
                        rec_dt=rec_dt,
                        reason=f"{int(cam_total - cam_online)} dari {int(cam_total)} kamera CCTV terputus (NO VIDEO)",
                    )
                else:
                    self._handle_module_recovery(
                        db=db,
                        dev_id=dev_id,
                        loc_name=loc_name,
                        metric="camera",
                        rec_dt=rec_dt,
                    )

            rec_count = rec_obj.get("cameras_recording_count")
            is_recording = rec_obj.get("is_recording")
            if is_recording is False or (isinstance(rec_count, (int, float)) and rec_count == 0 and isinstance(cam_online, (int, float)) and cam_online > 0):
                self._handle_module_down(
                    db=db,
                    dev_id=dev_id,
                    loc_name=loc_name,
                    metric="recording",
                    rec_dt=rec_dt,
                    reason="NVR terhubung tetapi tidak ada kamera yang aktif merekam (Not Recording)",
                )
            elif is_recording is True or (isinstance(rec_count, (int, float)) and rec_count > 0):
                self._handle_module_recovery(
                    db=db,
                    dev_id=dev_id,
                    loc_name=loc_name,
                    metric="recording",
                    rec_dt=rec_dt,
                )

        # 5. Power / Battery Drop
        gw_sys = payload.get("gateway_system") or {}
        pwr = payload.get("power_status") or gw_sys.get("power") or {}
        pwr_source = str(pwr.get("source") or pwr.get("power_source") or "").upper()
        pwr_state = str(pwr.get("status") or "").lower()
        batt_pct = pwr.get("battery_percent")
        volt_val = pwr.get("voltage_v") or pwr.get("voltage")
        try:
            volt_num = float(str(volt_val).replace("V", "").strip()) if volt_val is not None else None
        except (ValueError, TypeError):
            volt_num = None
        power_bad = (
            pwr_source == "BATT"
            or "discharging" in pwr_state
            or (isinstance(batt_pct, (int, float)) and batt_pct < 20)
            or (volt_num is not None and 0 < volt_num < 4.63)
            or "VOLTAGE" in logs_str.upper() and "DROP" in logs_str.upper()
        )
        if power_bad:
            pwr_reason = (
                f"Listrik padam / mode baterai ({batt_pct}%)"
                if (pwr_source == "BATT" or "discharging" in pwr_state)
                else f"Tegangan adaptor drop ({volt_num:.2f}V < 4.63V)" if volt_num is not None
                else "Gangguan daya / tegangan listrik adaptor drop"
            )
            self._handle_module_down(
                db=db,
                dev_id=dev_id,
                loc_name=loc_name,
                metric="power",
                rec_dt=rec_dt,
                reason=pwr_reason,
            )
        else:
            self._handle_module_recovery(
                db=db,
                dev_id=dev_id,
                loc_name=loc_name,
                metric="power",
                rec_dt=rec_dt,
            )

        # 6. Storage Full (>=95%) or Critical Health
        sd_obj = gw_sys.get("storage") or {}
        parts = sd_obj.get("partitions") or []
        sd_used = parts[0].get("used_percent") if parts and isinstance(parts[0], dict) else None
        sd_health = str(sd_obj.get("health_status") or sd_obj.get("sd_health") or "").lower()
        nvr_stor = (payload.get("nvr_surveillance") or {}).get("storage") or {}
        nvr_used = nvr_stor.get("used_percent")
        stor_bad_reasons = []
        if isinstance(sd_used, (int, float)) and sd_used >= 95:
            stor_bad_reasons.append(f"SD Card gateway penuh ({sd_used:.0f}%)")
        if sd_health in ("bad", "critical"):
            stor_bad_reasons.append(f"Kondisi flash storage {sd_health.capitalize()}")
        if isinstance(nvr_used, (int, float)) and nvr_used >= 95:
            stor_bad_reasons.append(f"Harddisk NVR penuh ({nvr_used:.0f}%)")
        if stor_bad_reasons:
            self._handle_module_down(
                db=db,
                dev_id=dev_id,
                loc_name=loc_name,
                metric="storage",
                rec_dt=rec_dt,
                reason=", ".join(stor_bad_reasons),
            )
        elif (isinstance(sd_used, (int, float)) or isinstance(nvr_used, (int, float))) and sd_health not in ("bad", "critical"):
            self._handle_module_recovery(
                db=db,
                dev_id=dev_id,
                loc_name=loc_name,
                metric="storage",
                rec_dt=rec_dt,
            )

        # 7. Physical LAN Cable eth0 Disconnected (NO-CARRIER)
        net_obj = payload.get("network") or gw_sys.get("network") or {}
        eth0_up = net_obj.get("eth0_carrier")
        lan_down = "NO-CARRIER" in logs_str.upper() or eth0_up is False
        lan_up = eth0_up is True or ("ETH0" in latest_str.upper() and "UP" in latest_str.upper() and "NO-CARRIER" not in latest_str.upper())
        if lan_down:
            self._handle_module_down(
                db=db,
                dev_id=dev_id,
                loc_name=loc_name,
                metric="lan",
                rec_dt=rec_dt,
                reason="Kabel LAN fisik eth0 terputus (NO-CARRIER)",
            )
        elif lan_up:
            self._handle_module_recovery(
                db=db,
                dev_id=dev_id,
                loc_name=loc_name,
                metric="lan",
                rec_dt=rec_dt,
            )

        # 8. CPU High Temperature (>80°C with 75°C hysteresis)
        cpu_obj = gw_sys.get("cpu") or {}
        temp_c = cpu_obj.get("temperature_c")
        if isinstance(temp_c, (int, float)):
            if temp_c > 80.0:
                self._handle_module_down(
                    db=db,
                    dev_id=dev_id,
                    loc_name=loc_name,
                    metric="high_temp",
                    rec_dt=rec_dt,
                    reason=f"Suhu CPU gateway mencapai {temp_c:.1f}°C (> 80°C)",
                )
            elif temp_c <= 75.0:
                self._handle_module_recovery(
                    db=db,
                    dev_id=dev_id,
                    loc_name=loc_name,
                    metric="high_temp",
                    rec_dt=rec_dt,
                )

        # 9. Weak Cellular Signal (RSRP < -105 dBm with -95 dBm hysteresis)
        if cell_up and 1 <= csq <= 31:
            rsrp_val = -(113 - 2 * csq)
            if rsrp_val < -105:
                self._handle_module_down(
                    db=db,
                    dev_id=dev_id,
                    loc_name=loc_name,
                    metric="weak_signal",
                    rec_dt=rec_dt,
                    reason=f"Kualitas sinyal seluler lemah (RSRP {rsrp_val} dBm / Poor)",
                )
            elif rsrp_val >= -95:
                self._handle_module_recovery(
                    db=db,
                    dev_id=dev_id,
                    loc_name=loc_name,
                    metric="weak_signal",
                    rec_dt=rec_dt,
                )

    def _handle_module_down(
        self,
        db: Session,
        dev_id: str,
        loc_name: str,
        metric: str,
        rec_dt: datetime,
        reason: str,
    ):
        outage_key = f"{dev_id}:{metric}"
        if outage_key not in self._active_outages:
            self._active_outages[outage_key] = {
                "device_id": dev_id,
                "location": loc_name,
                "metric": metric,
                "start_time": rec_dt,
                "last_seen_down": rec_dt,
                "reason": reason,
                "notified": True,
            }
            self.dispatch_module_event(
                db=db,
                dev_id=dev_id,
                loc_name=loc_name,
                metric=metric,
                is_recovered=False,
                rec_dt=rec_dt,
                reason=reason,
            )
        else:
            self._active_outages[outage_key]["last_seen_down"] = rec_dt

    def _handle_module_recovery(
        self,
        db: Session,
        dev_id: str,
        loc_name: str,
        metric: str,
        rec_dt: datetime,
        sim_info: Optional[str] = None,
    ):
        outage_key = f"{dev_id}:{metric}"
        if outage_key in self._active_outages:
            outage = self._active_outages.pop(outage_key)
            st = outage.get("start_time") or rec_dt
            diff_sec = max(60.0, (rec_dt - st).total_seconds())
            dur_m = max(1, round(diff_sec / 60.0))
            if dur_m >= 60:
                dur_str = f"{dur_m // 60} Jam {dur_m % 60} Menit" if dur_m % 60 else f"{dur_m // 60} Jam"
            else:
                dur_str = f"{dur_m} Menit"

            self.dispatch_module_event(
                db=db,
                dev_id=dev_id,
                loc_name=loc_name or outage.get("location") or "",
                metric=metric,
                is_recovered=True,
                rec_dt=rec_dt,
                duration_str=dur_str,
                sim_info=sim_info,
            )

    def dispatch_module_event(
        self,
        db: Session,
        dev_id: str,
        loc_name: str,
        metric: str,
        is_recovered: bool,
        rec_dt: datetime,
        reason: Optional[str] = None,
        duration_str: Optional[str] = None,
        sim_info: Optional[str] = None,
    ):
        try:
            dur = duration_str or "1 Menit"
            wib = timezone(timedelta(hours=7))
            t_wib = rec_dt.replace(tzinfo=timezone.utc).astimezone(wib) if rec_dt.tzinfo is None else rec_dt.astimezone(wib)
            ts_wib = t_wib.strftime("%Y-%m-%d %H:%M:%S (WIB)")

            if metric == "cellular":
                if is_recovered:
                    event_code = "gateway_cellular_recovered"
                    title = f"Cellular Recovered - {dev_id}"
                    sim_txt = sim_info or "4G LTE"
                    body = f"Koneksi seluler pada gateway {dev_id} telah pulih kembali ({sim_txt}) setelah mengalami downtime selama {dur}."
                    severity = "INFO"
                else:
                    event_code = "gateway_cellular_down"
                    title = f"Cellular Down - {dev_id}"
                    rsn = reason or "Kartu SIM tidak terdeteksi atau dicabut dari slot modem"
                    body = f"Koneksi seluler pada gateway {dev_id} terputus (Penyebab: {rsn})."
                    severity = "CRITICAL"

            elif metric == "cpu_modem":
                if is_recovered:
                    event_code = "gateway_modem_reconnected"
                    title = f"Modem Reconnected - {dev_id}"
                    body = f"Komunikasi port serial USB modem pada gateway {dev_id} telah terhubung kembali (OK) setelah mengalami downtime selama {dur}."
                    severity = "INFO"
                else:
                    event_code = "gateway_modem_disconnected"
                    title = f"Modem Disconnected - {dev_id}"
                    rsn = reason or "Port serial USB modul modem terlepas atau komunikasi terputus"
                    body = f"Komunikasi port serial USB modem pada gateway {dev_id} terputus (Penyebab: {rsn})."
                    severity = "CRITICAL"

            elif metric == "cpu_dvr":
                if is_recovered:
                    event_code = "gateway_dvr_recovered"
                    title = f"NVR Recovered - {dev_id}"
                    body = f"Perangkat NVR surveillance pada gateway {dev_id} telah pulih kembali dan aktif merekam setelah mengalami downtime selama {dur}."
                    severity = "INFO"
                else:
                    event_code = "gateway_dvr_offline"
                    title = f"NVR Offline - {dev_id}"
                    rsn = reason or "Kabel LAN lepas atau NVR mati"
                    body = f"Komunikasi gateway ke perangkat NVR surveillance pada {dev_id} terputus (Penyebab: {rsn})."
                    severity = "WARNING"

            elif metric == "gateway":
                if is_recovered:
                    event_code = "gateway_online"
                    title = f"Gateway Online - {dev_id}"
                    body = f"Gateway {dev_id} ({loc_name or dev_id}) telah kembali online dan mengirim telemetri setelah offline selama {dur}."
                    severity = "INFO"
                else:
                    event_code = "gateway_offline"
                    title = f"Gateway Offline - {dev_id}"
                    rsn = reason or "Tidak mengirim data telemetri MQTT lebih dari 1 jam"
                    body = f"Gateway {dev_id} ({loc_name or dev_id}) terdeteksi OFFLINE ({rsn})."
                    severity = "CRITICAL"

            elif metric == "camera":
                if is_recovered:
                    event_code = "gateway_camera_recovered"
                    title = f"Camera Recovered - {dev_id}"
                    body = f"Seluruh kamera CCTV pada gateway {dev_id} telah kembali online setelah gangguan selama {dur}."
                    severity = "INFO"
                else:
                    event_code = "gateway_camera_loss"
                    title = f"Camera Loss - {dev_id}"
                    rsn = reason or "Kamera CCTV terputus (NO VIDEO)"
                    body = f"Kamera CCTV pada gateway {dev_id} bermasalah ({rsn})."
                    severity = "WARNING"

            elif metric == "recording":
                if is_recovered:
                    event_code = "gateway_recording_resumed"
                    title = f"Recording Resumed - {dev_id}"
                    body = f"Rekaman NVR pada gateway {dev_id} telah aktif kembali setelah berhenti selama {dur}."
                    severity = "INFO"
                else:
                    event_code = "gateway_recording_stopped"
                    title = f"Recording Stopped - {dev_id}"
                    rsn = reason or "NVR berhenti merekam video"
                    body = f"NVR pada gateway {dev_id} berhenti merekam ({rsn})."
                    severity = "CRITICAL"

            elif metric == "power":
                if is_recovered:
                    event_code = "gateway_power_recovered"
                    title = f"Power Recovered - {dev_id}"
                    body = f"Sumber listrik / tegangan adaptor pada gateway {dev_id} telah kembali normal setelah gangguan selama {dur}."
                    severity = "INFO"
                else:
                    event_code = "gateway_power_drop"
                    title = f"Power Drop - {dev_id}"
                    rsn = reason or "Gangguan daya listrik / tegangan drop"
                    body = f"Peringatan daya pada gateway {dev_id}: {rsn}."
                    severity = "CRITICAL"

            elif metric == "storage":
                if is_recovered:
                    event_code = "gateway_storage_recovered"
                    title = f"Storage Recovered - {dev_id}"
                    body = f"Kapasitas dan kondisi storage pada gateway {dev_id} telah kembali normal setelah {dur}."
                    severity = "INFO"
                else:
                    event_code = "gateway_storage_critical"
                    title = f"Storage Critical - {dev_id}"
                    rsn = reason or "Kapasitas storage penuh atau kesehatan storage menurun"
                    body = f"Peringatan storage pada gateway {dev_id}: {rsn}."
                    severity = "CRITICAL"

            elif metric == "lan":
                if is_recovered:
                    event_code = "gateway_lan_reconnected"
                    title = f"LAN Reconnected - {dev_id}"
                    body = f"Koneksi kabel LAN eth0 pada gateway {dev_id} telah terhubung kembali setelah {dur}."
                    severity = "INFO"
                else:
                    event_code = "gateway_lan_disconnected"
                    title = f"LAN Disconnected - {dev_id}"
                    rsn = reason or "Kabel LAN fisik eth0 terputus (NO-CARRIER)"
                    body = f"Kabel LAN eth0 pada gateway {dev_id} terputus ({rsn})."
                    severity = "WARNING"

            elif metric == "high_temp":
                if is_recovered:
                    event_code = "gateway_temp_normal"
                    title = f"CPU Temperature Normal - {dev_id}"
                    body = f"Suhu CPU gateway {dev_id} telah kembali normal (<= 75°C) setelah panas tinggi selama {dur}."
                    severity = "INFO"
                else:
                    event_code = "gateway_high_temp"
                    title = f"CPU High Temp - {dev_id}"
                    rsn = reason or "Suhu CPU melebihi batas 80°C"
                    body = f"Peringatan suhu tinggi pada gateway {dev_id}: {rsn}."
                    severity = "WARNING"

            elif metric == "weak_signal":
                if is_recovered:
                    event_code = "gateway_signal_normal"
                    title = f"Cellular Signal Normal - {dev_id}"
                    body = f"Sinyal seluler pada gateway {dev_id} telah membaik kembali setelah sinyal lemah selama {dur}."
                    severity = "INFO"
                else:
                    event_code = "gateway_weak_signal"
                    title = f"Weak Signal - {dev_id}"
                    rsn = reason or "Kualitas sinyal seluler Poor (RSRP < -105 dBm)"
                    body = f"Sinyal seluler pada gateway {dev_id} lemah ({rsn})."
                    severity = "WARNING"

            elif metric == "sla":
                if is_recovered:
                    event_code = "gateway_sla_recovered"
                    title = f"SLA Target Achieved - {dev_id}"
                    body = f"SLA gateway {dev_id} telah kembali mencapai target >= 98.0% setelah berada di bawah target selama {dur}."
                    severity = "INFO"
                else:
                    event_code = "gateway_sla_breach"
                    title = f"SLA Below Target - {dev_id}"
                    rsn = reason or "SLA di bawah target 98.0%"
                    body = f"SLA gateway {dev_id} turun di bawah target 98.0% ({rsn})."
                    severity = "WARNING"

            else:
                act = "recovered" if is_recovered else "down"
                event_code = f"gateway_{metric}_{act}"
                title = f"{metric.capitalize()} {act.capitalize()} - {dev_id}"
                body = f"{metric.capitalize()} on gateway {dev_id} is {act}."
                severity = "INFO" if is_recovered else "WARNING"

            event_record = db.query(NotificationEvent).filter(NotificationEvent.event_code == event_code).first()
            if not event_record:
                return

            configured_channels = event_record.channels or []
            if not configured_channels:
                return

            norm_channels = []
            for c in configured_channels:
                if isinstance(c, str):
                    norm_channels.append({"channel_type": c, "is_enabled": True})
                elif isinstance(c, dict):
                    norm_channels.append(c)

            active_configured = [c for c in norm_channels if c.get("is_enabled", True)]
            if not active_configured:
                return

            in_app_entry = next((c for c in active_configured if c.get("channel_type") == "in_app"), None)
            in_app_enabled = bool(in_app_entry)

            recipient_overrides = {}
            channel_dest_ids = {}
            for c in active_configured:
                c_type = c.get("channel_type")
                if c_type and c_type != "in_app":
                    recipient_overrides[c_type] = c.get("recipient")
                    channel_dest_ids[c_type] = c.get("destination_ids") or []

            notif_data = {
                "event_code": event_code,
                "device_id": dev_id,
                "location": loc_name or "-",
                "metric": metric,
                "status": "RESOLVED" if is_recovered else "ACTIVE",
                "timestamp": ts_wib,
                "duration_str": dur if is_recovered else None,
            }

            notif_record = None
            if in_app_enabled:
                in_app_provider = self.registry.get("in_app")
                if in_app_provider:
                    notif_record = in_app_provider.create_in_app_record(
                        db=db,
                        event_code=event_code,
                        title=title,
                        body=body,
                        severity=severity,
                        data=notif_data
                    )
                    db.commit()

            active_destinations = db.query(NotificationDestination).filter(
                NotificationDestination.status == "CONNECTED"
            ).all()

            filtered_destinations = []
            for dest in active_destinations:
                if dest.provider_key in recipient_overrides or dest.provider_key in channel_dest_ids:
                    filtered_destinations.append(dest)

            if filtered_destinations:
                notif_id = notif_record.id if notif_record else None
                dest_info_list = [
                    {
                        "id": d.id,
                        "provider_key": d.provider_key,
                        "recipient_override": recipient_overrides.get(d.provider_key),
                        "destination_ids": channel_dest_ids.get(d.provider_key, [])
                    }
                    for d in filtered_destinations
                ]
                dispatch_pool.submit(self._async_dispatch_destinations, dest_info_list, title, body, notif_data, notif_id)

        except Exception as e:
            logger.error(f"[NotificationService] Error dispatching module event: {e}", exc_info=True)

    def check_periodic_health_notifications(self, db: Session):
        """
        Periodic sweep (e.g. every 60s) to detect:
        1. Gateway Offline (> ONLINE_TIMEOUT_SECONDS / 3600s without MQTT telemetry)
        2. Gateway SLA below target (< 98.0%)
        """
        import time
        try:
            from app.services.system_health_service import system_health_service
            now_epoch = time.time()
            now_dt = datetime.now(timezone.utc)
            timeout_sec = getattr(system_health_service, "ONLINE_TIMEOUT_SECONDS", 3600)

            for dev_id, entry in list(system_health_service._live_gateways.items()):
                last_epoch = entry.get("last_seen_epoch")
                if not isinstance(last_epoch, (int, float)) or last_epoch <= 0:
                    continue
                age_sec = now_epoch - last_epoch
                table_item = entry.get("table_item") or {}
                loc_name = table_item.get("location") or dev_id
                if age_sec > timeout_sec:
                    mins = int(age_sec // 60)
                    dur_label = f"{mins // 60} jam {mins % 60} menit" if mins >= 60 else f"{mins} menit"
                    self._handle_module_down(
                        db=db,
                        dev_id=dev_id,
                        loc_name=loc_name,
                        metric="gateway",
                        rec_dt=now_dt,
                        reason=f"Tidak ada data telemetri MQTT selama {dur_label} (batas 1 jam)",
                    )
        except Exception as e:
            logger.debug(f"[NotificationService] Periodic offline sweep skipped: {e}")

        try:
            from app.services.sla_calculator_service import sla_calculator_service
            from app.services.system_health_service import system_health_service
            now_dt = datetime.now(timezone.utc)
            for cache_key, cached in list(getattr(sla_calculator_service, "_summary_cache", {}).items()):
                if not isinstance(cached, dict):
                    continue
                val = cached.get("data") or cached
                if not isinstance(val, dict):
                    continue
                dev_id = val.get("device_id") or (str(cache_key).split(":")[0] if ":" in str(cache_key) else None)
                if not dev_id:
                    continue
                gw_sla = val.get("gateway_sla_pct")
                cel_sla = val.get("cellular_sla_pct")
                dvr_sla = val.get("dvr_sla_pct")
                if all(isinstance(x, (int, float)) for x in (gw_sla, cel_sla, dvr_sla)):
                    overall_sla = round((gw_sla + cel_sla + dvr_sla) / 3.0, 1)
                    loc_name = (system_health_service._live_gateways.get(dev_id, {}).get("table_item") or {}).get("location") or dev_id
                    if overall_sla < 98.0:
                        self._handle_module_down(
                            db=db,
                            dev_id=dev_id,
                            loc_name=loc_name,
                            metric="sla",
                            rec_dt=now_dt,
                            reason=f"SLA saat ini {overall_sla}% (target >= 98.0%)",
                        )
                    else:
                        self._handle_module_recovery(
                            db=db,
                            dev_id=dev_id,
                            loc_name=loc_name,
                            metric="sla",
                            rec_dt=now_dt,
                        )
        except Exception as e:
            logger.debug(f"[NotificationService] Periodic SLA sweep skipped: {e}")

    def dispatch_incident_event(self, db: Session, incident: GatewayIncidentAlert, event_type: str = "STARTED"):
        is_recovered = event_type.upper() in ["RESOLVED", "RECOVERED"]
        dur = incident.duration_str or (f"{int(incident.duration_minutes)} Menit" if incident.duration_minutes else "1 Menit")
        target_dt = incident.end_time if is_recovered and incident.end_time else (incident.start_time or datetime.utcnow())
        self.dispatch_module_event(
            db=db,
            dev_id=incident.device_id,
            loc_name="",
            metric=incident.metric,
            is_recovered=is_recovered,
            rec_dt=target_dt,
            reason=incident.description,
            duration_str=dur,
        )

    def _async_dispatch_destinations(
        self,
        dest_info_list: List[Dict[str, Any]],
        title: str,
        body: str,
        data: Dict[str, Any],
        notification_id: Optional[str]
    ):
        db = SessionLocal()
        try:
            for item in dest_info_list:
                dest_id = item["id"]
                custom_recipient = item.get("recipient_override")
                target_ids = item.get("destination_ids") or []
                dest = db.query(NotificationDestination).filter(
                    NotificationDestination.id == dest_id
                ).first()

                if not dest:
                    continue

                provider = self.registry.get(dest.provider_key)
                if not provider:
                    logger.warning(f"[NotificationService] Provider '{dest.provider_key}' not found in registry")
                    continue

                targets = []
                if target_ids:
                    targets = db.query(NotificationTarget).filter(
                        NotificationTarget.id.in_(target_ids),
                        NotificationTarget.is_active == True
                    ).all()

                if targets:
                    for target in targets:
                        effective_recipient = target.external_id
                        success, err_msg, resp_payload = provider.send(
                            recipient=effective_recipient,
                            title=title,
                            body=body,
                            data=data,
                            config=dest.config or {}
                        )

                        delivery = NotificationDelivery(
                            notification_id=notification_id,
                            destination_id=dest.id,
                            channel_type=dest.provider_key,
                            recipient=f"{target.display_name} ({effective_recipient})",
                            status="SUCCESS" if success else "FAILED",
                            error_message=err_msg if not success else None,
                            response_payload=resp_payload if isinstance(resp_payload, dict) else {"raw": str(resp_payload)},
                            sent_at=datetime.utcnow()
                        )
                        db.add(delivery)
                        db.commit()
                        logger.info(f"[NotificationService] Dispatched '{dest.provider_key}' to '{target.display_name}': status={delivery.status}")
                else:
                    effective_recipient = custom_recipient or str(
                        dest.config.get("default_chat_id")
                        or dest.config.get("default_recipient")
                        or dest.config.get("webhook_url")
                        or dest.config.get("default_recipients")
                        or ""
                    )

                    success, err_msg, resp_payload = provider.send(
                        recipient=effective_recipient,
                        title=title,
                        body=body,
                        data=data,
                        config=dest.config or {}
                    )

                    delivery = NotificationDelivery(
                        notification_id=notification_id,
                        destination_id=dest.id,
                        channel_type=dest.provider_key,
                        recipient=effective_recipient,
                        status="SUCCESS" if success else "FAILED",
                        error_message=err_msg if not success else None,
                        response_payload=resp_payload if isinstance(resp_payload, dict) else {"raw": str(resp_payload)},
                        sent_at=datetime.utcnow()
                    )
                    db.add(delivery)
                    db.commit()
                    logger.info(f"[NotificationService] Dispatched '{dest.provider_key}' for '{data.get('device_id')}': status={delivery.status}")
        except Exception as e:
            logger.error(f"[NotificationService] Async dispatch worker error: {e}")
        finally:
            db.close()

    def get_notifications(
        self,
        db: Session,
        page: int = 1,
        limit: int = 20,
        unread_only: bool = False,
        read_status: Optional[str] = None,
        severity: Optional[str] = None,
        search: Optional[str] = None,
    ):
        query = db.query(Notification)
        if unread_only or read_status == "UNREAD":
            query = query.filter(Notification.is_read == False)
        elif read_status == "READ":
            query = query.filter(Notification.is_read == True)

        if severity and severity.upper() != "ALL":
            query = query.filter(Notification.severity == severity.upper())

        if search and search.strip():
            term = f"%{search.strip()}%"
            query = query.filter(
                or_(
                    Notification.title.ilike(term),
                    Notification.body.ilike(term),
                    Notification.event_code.ilike(term),
                )
            )

        total = query.count()
        items = query.order_by(Notification.created_at.desc()).offset((page - 1) * limit).limit(limit).all()
        unread_count = db.query(Notification).filter(Notification.is_read == False).count()
        return {
            "items": items,
            "total": total,
            "page": page,
            "limit": limit,
            "unread_count": unread_count,
        }

    def get_deliveries(self, db: Session, page: int = 1, limit: int = 20, status: Optional[str] = None):
        query = db.query(NotificationDelivery)
        if status:
            query = query.filter(NotificationDelivery.status == status.upper())
        total = query.count()
        items = query.order_by(NotificationDelivery.sent_at.desc()).offset((page - 1) * limit).limit(limit).all()
        return {
            "items": items,
            "total": total,
            "page": page,
            "limit": limit,
        }

    def mark_as_read(self, db: Session, notification_id: str):
        notif = db.query(Notification).filter(Notification.id == notification_id).first()
        if notif:
            notif.is_read = True
            notif.read_at = datetime.utcnow()
            db.commit()
            db.refresh(notif)
        return notif

    def mark_all_as_read(self, db: Session):
        db.query(Notification).filter(Notification.is_read == False).update(
            {"is_read": True, "read_at": datetime.utcnow()}
        )
        db.commit()
        return True


notification_service = NotificationService()
