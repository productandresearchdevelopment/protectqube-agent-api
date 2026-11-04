import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import desc, func
from app.models.base_models import GatewayIncidentAlert, GatewayTelemetryHistory

logger = logging.getLogger(__name__)

# Kamus Penerjemah Bahasa Manusia yang Mudah Dipahami
ALERT_DEFINITIONS = {
    "GATEWAY_REBOOT": {
        "title": "Gateway Habis Mati & Reboot (Uptime Reset)",
        "category": "POWER",
        "severity": "CRITICAL",
        "component": "Sistem Daya / CPU Gateway",
        "message": "Gateway terdeteksi sempat mati total / restart (counter uptime sistem ter-reset ke awal). Perangkat kini telah aktif dan pulih kembali.",
        "recommendation": "Periksa kestabilan sumber listrik PLN/UPS dan pastikan kabel daya/adaptor gateway tidak longgar."
    },
    "UNDERVOLTAGE_BROWNOUT": {
        "title": "Tegangan Listrik Adaptor Drop (<4.63V)",
        "category": "POWER",
        "severity": "CRITICAL",
        "component": "Adaptor Daya / PMIC CPU",
        "message": "Tegangan input dari adaptor listrik mengalami penurunan arus (brownout) di bawah batas toleransi minimum 4.63V sehingga CPU gateway mati/restart.",
        "recommendation": "Ganti adaptor daya gateway dengan spesifikasi 5V/3A murni, dan periksa terminal colokan listrik agar tidak kendor."
    },
    "SUDDEN_POWER_OUTAGE": {
        "title": "Mati Listrik Mendadak / Kabel Power Tercabut",
        "category": "POWER",
        "severity": "HIGH",
        "component": "Sumber Listrik AC/DC",
        "message": "Gateway mati tiba-tiba tanpa proses shutdown sistem (unclean power loss), kemungkinan akibat pemadaman listrik lokasi atau kabel power tercabut.",
        "recommendation": "Periksa kestabilan jalur listrik PLN/UPS di lokasi, dan pastikan kabel daya gateway terikat rapi (cable tie)."
    },
    "CPU_OVERHEAT_REBOOT": {
        "title": "Suhu CPU Panas Ekstrem (Thermal Protection)",
        "category": "SYSTEM",
        "severity": "HIGH",
        "component": "CPU Heatsink & Pendingin",
        "message": "Gateway sempat offline akibat penghentian sistem otomatis untuk proteksi keselamatan prosesor karena suhu melampaui batas toleransi.",
        "recommendation": "Periksa sirkulasi udara box enclosure gateway dan bersihkan kipas/ventilasi dari debu."
    },
    "SIM_CARD_REMOVED": {
        "title": "Kartu SIM Sempat Dicabut / Tidak Terdeteksi",
        "category": "CELLULAR",
        "severity": "CRITICAL",
        "component": "Slot SIM Tray Modem Quectel",
        "message": "Modem melaporkan kartu SIM tidak terdeteksi (+CPIN: NOT INSERTED). Aliran data internet terhenti seketika.",
        "recommendation": "Periksa fisik kartu SIM pada modem USB gateway, bersihkan lempeng kuningan kartu SIM, dan pastikan tray terkunci rapat."
    },
    "FAIL_SIM_CARD_REMOVED": {
        "title": "Kartu SIM Sempat Dicabut / Tidak Terdeteksi",
        "category": "CELLULAR",
        "severity": "CRITICAL",
        "component": "Slot SIM Card",
        "message": "Kartu SIM tidak terdeteksi atau dicabut dari slot modem seluler.",
        "recommendation": "Pasang kembali kartu SIM ke slot modem dan restart gateway jika diperlukan."
    },
    "MODEM_USB_DISCONNECTED": {
        "title": "Modem USB Quectel 4G Terputus",
        "category": "CELLULAR",
        "severity": "HIGH",
        "component": "Port USB Modem Quectel",
        "message": "Komunikasi port USB serial antara CPU gateway dan modem Quectel terputus sehingga koneksi seluler hilang.",
        "recommendation": "Pastikan kabel USB modem terpasang kencang ke port USB Raspberry Pi dan tidak longgar."
    },
    "CELLULAR_DISCONNECTED": {
        "title": "Koneksi Seluler Terputus (Blank Spot / Jaringan Hilang)",
        "category": "CELLULAR",
        "severity": "HIGH",
        "component": "Jaringan Data Seluler",
        "message": "Gateway kehilangan koneksi jaringan data internet dari operator seluler (sinyal hilang sesaat / blank spot).",
        "recommendation": "Periksa posisi antena 4G modem dan pastikan berada di area dengan jangkauan sinyal operator yang baik."
    },
    "TELEMETRY_GAP_WITH_REBOOT": {
        "title": "Koneksi Telemetri Terputus & Gateway Reboot",
        "category": "NETWORK",
        "severity": "HIGH",
        "component": "Jaringan Telemetri / CPU Gateway",
        "message": "Transmisi telemetri sempat terputus dan gateway terdeteksi mengalami reboot selama periode offline. Kini sistem dan transmisi data telah pulih normal kembali.",
        "recommendation": "Periksa kestabilan jaringan seluler di lokasi serta pastikan sumber daya adaptor gateway stabil."
    },
    "TELEMETRY_GAP_ONLINE": {
        "title": "Koneksi Telemetri Terputus (Gateway Tetap Aktif)",
        "category": "NETWORK",
        "severity": "HIGH",
        "component": "Jaringan Komunikasi Telemetri",
        "message": "Transmisi telemetri gateway sempat terputus, namun CPU gateway tetap beroperasi aktif tanpa reboot. Transmisi telemetri kini telah normal kembali.",
        "recommendation": "Periksa kekuatan sinyal seluler dan kestabilan komunikasi paket data internet di lokasi."
    },
    "LAN_CABLE_DISCONNECTED": {
        "title": "Kabel LAN Fisik eth0 Terputus (NO-CARRIER)",
        "category": "NETWORK",
        "severity": "HIGH",
        "component": "Kabel LAN RJ45 eth0",
        "message": "Port LAN eth0 CPU Gateway kehilangan sinyal link fisik ke NVR/Switch (kabel lepas atau putus di tengah).",
        "recommendation": "Periksa konektor RJ45 pada port eth0 gateway dan switch NVR, lakukan crimping ulang jika klip konektor patah."
    },
    "FAIL_NVR_DISCONNECTED": {
        "title": "Perangkat NVR / DVR Tidak Terhubung",
        "category": "CCTV_NVR",
        "severity": "HIGH",
        "component": "NVR Surveillance ISAPI",
        "message": "CPU Gateway gagal berkomunikasi dengan NVR (Port 80/ISAPI Timeout). Perekaman dan status kamera tidak terpantau.",
        "recommendation": "Periksa daya adaptor NVR dan pastikan switch jaringan lokal (LAN) aktif."
    },
    "WARN_CAMERA_OFFLINE": {
        "title": "Kamera CCTV Terputus (NO VIDEO)",
        "category": "CCTV_NVR",
        "severity": "WARNING",
        "component": "Kamera CCTV",
        "message": "Kamera CCTV terputus atau tidak mengirimkan sinyal video ke NVR.",
        "recommendation": "Periksa sambungan kabel coaxial/LAN dan adaptor daya kamera yang bersangkutan."
    },
    "WARN_NVR_HDD_FULL": {
        "title": "Kapasitas Harddisk NVR Penuh (100%)",
        "category": "CCTV_NVR",
        "severity": "WARNING",
        "component": "Harddisk NVR (SATA)",
        "message": "Kapasitas Harddisk NVR telah mencapai 100%. Perekaman tetap berjalan menggunakan mode loop overwrite otomatis.",
        "recommendation": "Pastikan mode auto-overwrite NVR tetap aktif, atau tambahkan kapasitas HDD jika durasi arsip video kurang."
    },
    "WARN_STORAGE_PARTITION_HIGH": {
        "title": "Kapasitas Partisi Root Storage Hampir Penuh",
        "category": "STORAGE",
        "severity": "WARNING",
        "component": "Partisi Storage (Root /)",
        "message": "Penggunaan memori flash pada partisi root sistem gateway telah melampaui batas waspada (>85%).",
        "recommendation": "Jalankan pembersihan log sementara atau hapus cache sistem untuk mencegah gateway read-only."
    },
    "WARN_STORAGE_HEALTH_DEGRADED": {
        "title": "Kondisi Flash Storage Gateway Menurun",
        "category": "STORAGE",
        "severity": "WARNING",
        "component": "MicroSD / eMMC Flash Card",
        "message": "Kesehatan fisik media penyimpanan flash menurun di bawah standar prima.",
        "recommendation": "Jadwalkan penggantian MicroSD/eMMC card saat jadwal maintenance berikutnya untuk mencegah korupsi data."
    },
    "WARN_CPU_HIGH_TEMP": {
        "title": "Suhu CPU Gateway Panas Berlebih (>80°C)",
        "category": "SYSTEM",
        "severity": "HIGH",
        "component": "CPU Heatsink & Pendingin",
        "message": "Suhu prosesor gateway mencapai batas bahaya. Berisiko menyebabkan throttling atau mati mendadak.",
        "recommendation": "Periksa sirkulasi udara di dalam box enclosure gateway dan bersihkan kipas/ventilasi dari debu."
    }
}


def parse_uptime_to_seconds(uptime_str: Optional[str]) -> Optional[int]:
    """Mengubah format uptime '3d 1h 25m' atau '10m 49s' ke total detik."""
    if not uptime_str or not isinstance(uptime_str, str):
        return None
    total_seconds = 0
    d = re.search(r'(\d+)\s*d', uptime_str)
    h = re.search(r'(\d+)\s*h', uptime_str)
    m = re.search(r'(\d+)\s*m', uptime_str)
    s = re.search(r'(\d+)\s*s', uptime_str)
    if not (d or h or m or s):
        return None
    if d:
        total_seconds += int(d.group(1)) * 86400
    if h:
        total_seconds += int(h.group(1)) * 3600
    if m:
        total_seconds += int(m.group(1)) * 60
    if s:
        total_seconds += int(s.group(1))
    return total_seconds


def format_downtime_duration(seconds: int) -> str:
    """Format durasi downtime ke durasi yang mudah dibaca."""
    if seconds < 60:
        return f"{seconds} Detik"
    minutes = round(seconds / 60)
    if minutes < 60:
        return f"{minutes} Menit"
    hours = minutes // 60
    rem_min = minutes % 60
    if rem_min == 0:
        return f"{hours} Jam"
    return f"{hours} Jam {rem_min} Menit"


def extract_downtime_from_logs(logs: list) -> Optional[Tuple[datetime, datetime, int]]:
    """
    Mendeteksi timestamp offline terakhir dan recovery dari baris recent_system_logs:
    [2026-11-02 15:41:51] [INFO ] [#25] [MQTT OK] ...
    [2026-11-02 16:09:45] [INFO ] === NMS BACKGROUND DAEMON STARTED ===
    """
    if not logs or not isinstance(logs, list):
        return None
    
    daemon_idx = -1
    for idx, l in enumerate(logs):
        line_str = str(l)
        if "=== NMS BACKGROUND DAEMON STARTED ===" in line_str or "DAEMON STARTED" in line_str:
            daemon_idx = idx
            break
            
    if daemon_idx > 0:
        prev_line = logs[daemon_idx - 1]
        start_line = logs[daemon_idx]
        
        m_prev = re.search(r'\[(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})\]', str(prev_line))
        m_start = re.search(r'\[(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})\]', str(start_line))
        
        if m_prev and m_start:
            try:
                # Log gateway adalah waktu lokal WIB (UTC+7)
                dt_offline_wib = datetime.strptime(m_prev.group(1), "%Y-%m-%d %H:%M:%S")
                dt_online_wib = datetime.strptime(m_start.group(1), "%Y-%m-%d %H:%M:%S")

                # Abaikan tahun tidak valid (misal 2019 jam RTC belum sinkron NTP)
                if dt_offline_wib.year < 2024 or dt_online_wib.year < 2024:
                    return None
                
                # Konversi ke UTC untuk disimpan ke database
                dt_offline_utc = dt_offline_wib - timedelta(hours=7)
                dt_online_utc = dt_online_wib - timedelta(hours=7)
                
                gap_sec = int((dt_online_wib - dt_offline_wib).total_seconds())
                if gap_sec >= 600:  # Minimal downtime 10 menit (600 detik)
                    return dt_offline_utc, dt_online_utc, gap_sec
            except Exception:
                pass
    return None


class IncidentAlertService:
    """
    Mengelola pencatatan, pengolahan, dan penyajian data alert insiden/downtime gateway
    agar mudah dibaca dan dipahami oleh manajemen maupun teknisi.
    """

    def _extract_downtime(
        self,
        db: Session,
        dev_id: str,
        payload: Dict[str, Any],
        rec_dt: datetime,
        telemetry_history_id: Optional[str] = None
    ) -> Optional[Tuple[datetime, datetime, int]]:
        """
        Mendeteksi apakah paket telemetri ini merupakan momen pemulihan paska offline / downtime.
        Sumber 1: Parsing log sistem (recent_system_logs)
        Sumber 2: Selisih waktu dengan rekam telemetri sebelumnya di database (gap >= 600 detik / 10 menit)
        """
        # 1. Coba deteksi langsung dari log sistem gateway
        recent_logs = payload.get("recent_system_logs", [])
        from_logs = extract_downtime_from_logs(recent_logs)
        if from_logs:
            return from_logs

        # 2. Fallback: Di bawah Opsi A, selisih waktu transmisi tanpa error log bukan downtime
        return None

    def process_telemetry_for_alerts(
        self,
        db: Session,
        dev_id: str,
        loc_name: str,
        payload: Dict[str, Any],
        rec_dt: datetime,
        telemetry_history_id: Optional[str] = None
    ) -> List[GatewayIncidentAlert]:
        created_alerts = []
        if not payload or not isinstance(payload, dict):
            return created_alerts

        pt = payload.get("power_throttled", {})
        sim = payload.get("cellular_sim", {})
        hw_conn = payload.get("hardware_connections", {})
        lan = hw_conn.get("ethernet_lan") if isinstance(hw_conn, dict) else None
        modem_usb = hw_conn.get("modem_usb") if isinstance(hw_conn, dict) else None
        recent_logs = payload.get("recent_system_logs", [])
        if not isinstance(recent_logs, list):
            recent_logs = []
        has_log_cabut = any(("SIM: DICABUT" in str(l) or "SIM DICABUT" in str(l) or "SIM TIDAK TERDETEKSI" in str(l) or "SIM: TIDAK TERDETEKSI" in str(l) or "+CPIN: NOT INSERTED" in str(l)) for l in recent_logs)
        has_daemon_restart = any("=== NMS BACKGROUND DAEMON STARTED ===" in str(l) for l in recent_logs)

        uptime_str = payload.get("gateway_system", {}).get("uptime")
        uptime_sec = parse_uptime_to_seconds(uptime_str)

        # -------------------------------------------------------------
        # 1. DETEKSI DOWNTIME GAP & REBOOT RECOVERY DENGAN AKAR MASALAH JELAS
        # -------------------------------------------------------------
        downtime_info = self._extract_downtime(db, dev_id, payload, rec_dt, telemetry_history_id)
        if downtime_info:
            dt_offline_utc, dt_online_utc, gap_sec = downtime_info
            downtime_h = format_downtime_duration(gap_sec)
            start_wib_str = (dt_offline_utc + timedelta(hours=7)).strftime("%H:%M WIB")
            end_wib_str = (dt_online_utc + timedelta(hours=7)).strftime("%H:%M WIB")

            # -------------------------------------------------------------
            # Identifikasi Akar Masalah Berdasarkan Data Real MQTT
            # Tidak berasumsi tanpa bukti di payload
            # -------------------------------------------------------------
            offline_rec = payload.get("offline_recovery") or {}
            offline_cause = str(offline_rec.get("cause") or offline_rec.get("event") or "").upper() if isinstance(offline_rec, dict) else ""

            # 1. Bukti eksplisit dari MQTT bahwa SIM Card dicabut / tidak terbaca
            is_explicit_sim_issue = (
                "SIM" in offline_cause
                or has_log_cabut
                or (isinstance(sim, dict) and sim.get("sim_inserted") is False)
            )

            # 2. Apakah gateway hidup terus menerus sepanjang gap waktu?
            # Jika uptime saat data tiba >= (gap_sec - 120 detik), berarti CPU 100% TIDAK PERNAH MATI!
            is_gateway_alive_whole_time = (uptime_sec is not None and gap_sec > 0 and uptime_sec >= (gap_sec - 120))

            # 3. Reboot murni (POWER): HANYA jika counter uptime benar-benar baru menyala (< 300 detik)
            # dan durasi gap wajar untuk sebuah reboot (< 1800 detik / 30 menit)
            is_fresh_reboot = (uptime_sec is not None and uptime_sec <= 300 and has_daemon_restart and gap_sec < 1800)

            up_display = uptime_str or (f"{uptime_sec}s" if uptime_sec else "0s")

            if is_explicit_sim_issue:
                # KASUS A: Bukti Eksplisit Kartu SIM Tidak Terdeteksi
                rc_code = "SIM_CARD_REMOVED"
                def_info = ALERT_DEFINITIONS[rc_code]
                title = def_info["title"]
                message = (
                    f"Koneksi gateway terputus selama {downtime_h} ({start_wib_str} s/d {end_wib_str}) "
                    f"karena kartu SIM terdeteksi tidak terbaca di slot modem USB (+CPIN: NOT INSERTED). "
                    f"Koneksi kini telah pulih kembali (uptime sistem: {up_display})."
                )

            elif isinstance(modem_usb, dict) and (modem_usb.get("status") == "FAIL" or modem_usb.get("connected") is False):
                # KASUS B: Port USB Modem Terputus
                rc_code = "MODEM_USB_DISCONNECTED"
                def_info = ALERT_DEFINITIONS[rc_code]
                title = def_info["title"]
                message = (
                    f"Koneksi gateway offline selama {downtime_h} ({start_wib_str} s/d {end_wib_str}) "
                    f"karena komunikasi serial port USB modem Quectel sempat terputus."
                )

            elif isinstance(lan, dict) and lan.get("status") == "FAIL":
                # KASUS C: Port LAN Terputus
                rc_code = "LAN_CABLE_DISCONNECTED"
                def_info = ALERT_DEFINITIONS[rc_code]
                title = def_info["title"]
                message = f"Koneksi kabel LAN port eth0 terputus selama {downtime_h}."

            elif is_gateway_alive_whole_time:
                # KASUS D: Gateway Hidup Terus 100%, Hanya Telemetri/Jaringan yang Sempat Terputus
                rc_code = "TELEMETRY_GAP_ONLINE"
                def_info = ALERT_DEFINITIONS[rc_code]
                title = def_info["title"]
                message = (
                    f"Koneksi telemetri gateway sempat terputus selama {downtime_h} ({start_wib_str} s/d {end_wib_str}). "
                    f"CPU gateway tetap beroperasi aktif normal (uptime sistem: {up_display}). "
                    f"Transmisi data kini telah terhubung kembali normal."
                )

            elif is_fresh_reboot:
                # KASUS E: Reboot Murni Cepat (< 30 Menit, Uptime Baru < 5 Menit)
                rc_code = "GATEWAY_REBOOT"
                def_info = ALERT_DEFINITIONS[rc_code]
                title = def_info["title"]
                cause_note = ""
                if isinstance(pt, dict) and (pt.get("undervoltage_occurred") or pt.get("undervoltage_now")):
                    p_hex = pt.get("raw_hex", "0x50005")
                    cause_note = f" (Tercatat indikasi tegangan adaptor drop PMIC: {p_hex})"
                elif isinstance(pt, dict) and pt.get("thermal_throttled_occurred"):
                    cause_note = " (Tercatat proteksi shutdown suhu termal CPU)"
                
                message = (
                    f"Gateway terdeteksi sempat mati / reboot selama {downtime_h} ({start_wib_str} s/d {end_wib_str}) "
                    f"dengan counter uptime sistem ter-reset ke {up_display}{cause_note}. "
                    f"Gateway kini telah aktif dan beroperasi normal kembali."
                )

            elif isinstance(pt, dict) and pt.get("undervoltage_now"):
                # Hanya jika undervoltage AKTIF SEKARANG, bukan sekadar riwayat bit lama
                rc_code = "UNDERVOLTAGE_BROWNOUT"
                p_hex = pt.get("raw_hex", "0x50005")
                def_info = ALERT_DEFINITIONS[rc_code]
                title = def_info["title"]
                message = (
                    f"Gateway offline selama {downtime_h} ({start_wib_str} s/d {end_wib_str}) "
                    f"akibat tegangan listrik input adaptor drop di bawah batas toleransi minimum 4.63V (PMIC: {p_hex}). "
                    f"Gateway otomatis reboot dan pulih setelah tegangan listrik kembali stabil."
                )

            elif isinstance(pt, dict) and pt.get("thermal_throttled_occurred"):
                rc_code = "CPU_OVERHEAT_REBOOT"
                def_info = ALERT_DEFINITIONS[rc_code]
                title = def_info["title"]
                message = (
                    f"Gateway offline selama {downtime_h} ({start_wib_str} s/d {end_wib_str}) "
                    f"akibat proteksi shutdown otomatis prosesor karena suhu melampaui ambang batas aman."
                )

            else:
                # KASUS F: Telemetri Terputus dengan Indikasi Reboot di Tengah Masa Offline
                # (Sesuai Fakta Data MQTT: gap offline panjang dan uptime sistem ter-reset sebagian)
                rc_code = "TELEMETRY_GAP_WITH_REBOOT"
                def_info = ALERT_DEFINITIONS[rc_code]
                title = def_info["title"]
                message = (
                    f"Koneksi telemetri gateway terputus selama {downtime_h} ({start_wib_str} s/d {end_wib_str}). "
                    f"Saat koneksi pulih, counter uptime sistem tercatat {up_display} (menandakan gateway sempat reboot). "
                    f"Seluruh koneksi data dan telemetri kini telah aktif normal kembali."
                )

            alert = self._create_or_update_downtime_alert(
                db=db,
                dev_id=dev_id,
                location=loc_name,
                alert_code=rc_code,
                category=def_info["category"],
                severity=def_info["severity"],
                title=title,
                message=message,
                component=def_info["component"],
                recommendation=def_info["recommendation"],
                downtime_duration=downtime_h,
                downtime_seconds=gap_sec,
                occurred_at=dt_offline_utc,
                recovered_at=dt_online_utc,
                status="RESOLVED",
                extra_data={
                    "gap_seconds": gap_sec,
                    "downtime_duration": downtime_h,
                    "offline_wib": start_wib_str,
                    "online_wib": end_wib_str,
                    "power_throttled": pt,
                    "uptime": uptime_str
                },
                telemetry_history_id=telemetry_history_id
            )
            if alert:
                created_alerts.append(alert)

        # -------------------------------------------------------------
        # 2. STATUS AKTIF BERJALAN: Drop Tegangan Saat Ini (undervoltage_now)
        # -------------------------------------------------------------
        if isinstance(pt, dict) and pt.get("undervoltage_now"):
            p_hex = pt.get("raw_hex", "0x50005")
            def_p = ALERT_DEFINITIONS["UNDERVOLTAGE_BROWNOUT"]
            alert = self._create_alert_if_not_exists(
                db=db,
                dev_id=dev_id,
                location=loc_name,
                alert_code="UNDERVOLTAGE_BROWNOUT",
                category=def_p["category"],
                severity="CRITICAL",
                title="Tegangan Listrik Adaptor Sedang Drop (<4.63V)",
                message=f"Tegangan listrik saat ini berada di bawah batas toleransi minimum 4.63V (PMIC: {p_hex}). Gateway berisiko mati sewaktu-waktu.",
                component=def_p["component"],
                recommendation=def_p["recommendation"],
                downtime_duration=None,
                downtime_seconds=None,
                occurred_at=rec_dt,
                recovered_at=None,
                status="ACTIVE",
                extra_data={"power_throttled": pt},
                telemetry_history_id=telemetry_history_id
            )
            if alert:
                created_alerts.append(alert)
        elif isinstance(pt, dict) and not pt.get("undervoltage_now"):
            # Auto-resolve alert undervoltage yang sedang ACTIVE jika tegangan sudah normal
            active_uv = db.query(GatewayIncidentAlert).filter(
                GatewayIncidentAlert.device_id == dev_id,
                GatewayIncidentAlert.alert_code == "UNDERVOLTAGE_BROWNOUT",
                GatewayIncidentAlert.status == "ACTIVE"
            ).first()
            if active_uv:
                active_uv.recovered_at = rec_dt
                active_uv.status = "RESOLVED"
                gap = int((rec_dt - active_uv.occurred_at).total_seconds()) if active_uv.occurred_at else 0
                active_uv.downtime_seconds = max(gap, 0)
                active_uv.downtime_duration = format_downtime_duration(gap)
                active_uv.message = f"Tegangan listrik input adaptor sempat drop di bawah toleransi 4.63V selama {active_uv.downtime_duration}. Tegangan kini telah stabil kembali normal."
                try:
                    db.commit()
                except Exception:
                    db.rollback()

        # -------------------------------------------------------------
        # 3. KARTU SIM: Sedang Dicabut (ACTIVE) atau Sempat Dicabut (RESOLVED)
        # -------------------------------------------------------------
        if isinstance(sim, dict) and sim.get("sim_inserted") is False:
            def_s = ALERT_DEFINITIONS["SIM_CARD_REMOVED"]
            sig = sim.get("signal")
            csq = sig.get("csq") if isinstance(sig, dict) else sig
            alert = self._create_alert_if_not_exists(
                db=db,
                dev_id=dev_id,
                location=loc_name,
                alert_code="SIM_CARD_REMOVED",
                category=def_s["category"],
                severity=def_s["severity"],
                title="Kartu SIM Saat Ini Tidak Terdeteksi",
                message=def_s["message"],
                component=def_s["component"],
                recommendation=def_s["recommendation"],
                downtime_duration=None,
                downtime_seconds=None,
                occurred_at=rec_dt,
                recovered_at=None,
                status="ACTIVE",
                extra_data={"operator": sim.get("operator"), "csq": csq},
                telemetry_history_id=telemetry_history_id
            )
            if alert:
                created_alerts.append(alert)
        elif has_log_cabut and isinstance(sim, dict) and sim.get("sim_inserted") is True:
            # Riwayat pencabutan SIM terdeteksi di log sistem sebelum pemulihan
            def_s = ALERT_DEFINITIONS["SIM_CARD_REMOVED"]
            sim_cabut_utc = None
            sim_recovered_utc = None
            for log_line in recent_logs:
                l_str = str(log_line)
                if any(k in l_str for k in ["SIM: DICABUT", "SIM DICABUT", "SIM TIDAK TERDETEKSI", "SIM: TIDAK TERDETEKSI", "+CPIN: NOT INSERTED"]):
                    m_time = re.search(r'\[(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})\]', l_str)
                    if m_time and not sim_cabut_utc:
                        try:
                            t_wib = datetime.strptime(m_time.group(1), "%Y-%m-%d %H:%M:%S")
                            if t_wib.year >= 2024:
                                sim_cabut_utc = t_wib - timedelta(hours=7)
                        except Exception:
                            pass
                elif "MQTT OK" in l_str and any(k in l_str for k in ["Telkomsel", "Indosat", "XL", "Smartfren", "SIM:"]):
                    m_time = re.search(r'\[(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})\]', l_str)
                    if m_time and not sim_recovered_utc:
                        try:
                            t_wib = datetime.strptime(m_time.group(1), "%Y-%m-%d %H:%M:%S")
                            if t_wib.year >= 2024:
                                sim_recovered_utc = t_wib - timedelta(hours=7)
                        except Exception:
                            pass

            if sim_cabut_utc and sim_recovered_utc and sim_recovered_utc > sim_cabut_utc:
                sim_gap = int((sim_recovered_utc - sim_cabut_utc).total_seconds())
            else:
                sim_gap = 600
                sim_recovered_utc = rec_dt
                sim_cabut_utc = rec_dt - timedelta(seconds=sim_gap)

            if sim_gap >= 600:
                sim_h = format_downtime_duration(sim_gap)
                start_sim_wib = (sim_cabut_utc + timedelta(hours=7)).strftime("%H:%M WIB")
                end_sim_wib = (sim_recovered_utc + timedelta(hours=7)).strftime("%H:%M WIB")

                alert = self._create_or_update_downtime_alert(
                    db=db,
                    dev_id=dev_id,
                    location=loc_name,
                    alert_code="SIM_CARD_REMOVED",
                    category=def_s["category"],
                    severity=def_s["severity"],
                    title="Kartu SIM Sempat Dicabut / Tidak Terdeteksi",
                    message=(
                        f"Kartu SIM terdeteksi sempat dicabut dari slot modem selama {sim_h} "
                        f"({start_sim_wib} s/d {end_sim_wib}) sehingga transmisi data seluler terhenti. "
                        f"Kartu SIM kini telah dipasang kembali normal ({sim.get('operator', 'Seluler')})."
                    ),
                    component=def_s["component"],
                    recommendation=def_s["recommendation"],
                    downtime_duration=sim_h,
                    downtime_seconds=sim_gap,
                    occurred_at=sim_cabut_utc,
                    recovered_at=sim_recovered_utc,
                    status="RESOLVED",
                    extra_data={
                        "operator": sim.get("operator"),
                        "downtime_duration": sim_h,
                        "sim_removed_wib": start_sim_wib,
                        "sim_recovered_wib": end_sim_wib
                    },
                    telemetry_history_id=telemetry_history_id
                )
                if alert:
                    created_alerts.append(alert)

        # -------------------------------------------------------------
        # 4. STATUS AKTIF BERJALAN: Kabel LAN Fisik eth0 Terputus (NO-CARRIER)
        # -------------------------------------------------------------
        if isinstance(lan, dict) and lan.get("status") == "FAIL":
            def_lan = ALERT_DEFINITIONS["LAN_CABLE_DISCONNECTED"]
            alert = self._create_alert_if_not_exists(
                db=db,
                dev_id=dev_id,
                location=loc_name,
                alert_code="LAN_CABLE_DISCONNECTED",
                category=def_lan["category"],
                severity=def_lan["severity"],
                title=def_lan["title"],
                message=lan.get("message") or def_lan["message"],
                component=def_lan["component"],
                recommendation=def_lan["recommendation"],
                downtime_duration=None,
                downtime_seconds=None,
                occurred_at=rec_dt,
                recovered_at=None,
                status="ACTIVE",
                extra_data={"link_type": lan.get("link_type")},
                telemetry_history_id=telemetry_history_id
            )
            if alert:
                created_alerts.append(alert)
        elif isinstance(lan, dict) and (lan.get("status") == "CONNECTED" or lan.get("connected") is True):
            # Auto-resolve alert LAN fisik yang sedang ACTIVE jika kabel sudah dicolok kembali normal
            active_lan = db.query(GatewayIncidentAlert).filter(
                GatewayIncidentAlert.device_id == dev_id,
                GatewayIncidentAlert.alert_code == "LAN_CABLE_DISCONNECTED",
                GatewayIncidentAlert.status == "ACTIVE"
            ).first()
            if active_lan:
                active_lan.recovered_at = rec_dt
                active_lan.status = "RESOLVED"
                gap = int((rec_dt - active_lan.occurred_at).total_seconds()) if active_lan.occurred_at else 0
                active_lan.downtime_seconds = max(gap, 0)
                active_lan.downtime_duration = format_downtime_duration(gap)
                active_lan.message = f"Koneksi kabel LAN port eth0 sempat terputus selama {active_lan.downtime_duration}. Kabel LAN kini telah terhubung kembali normal ke switch/NVR."
                try:
                    db.commit()
                except Exception:
                    db.rollback()

        return created_alerts

    def _create_or_update_downtime_alert(
        self,
        db: Session,
        dev_id: str,
        location: str,
        alert_code: str,
        category: str,
        severity: str,
        title: str,
        message: str,
        component: Optional[str],
        recommendation: Optional[str],
        downtime_duration: Optional[str],
        downtime_seconds: Optional[int],
        occurred_at: datetime,
        recovered_at: Optional[datetime],
        status: str,
        extra_data: Optional[Dict[str, Any]],
        telemetry_history_id: Optional[str] = None
    ) -> Optional[GatewayIncidentAlert]:
        """Menyimpan atau mengupdate insiden downtime tanpa duplikasi dalam rentang 30 menit."""
        window_start = occurred_at - timedelta(minutes=30)
        window_end = (recovered_at or occurred_at) + timedelta(minutes=30)

        existing = db.query(GatewayIncidentAlert).filter(
            GatewayIncidentAlert.device_id == dev_id,
            GatewayIncidentAlert.category == category,
            GatewayIncidentAlert.occurred_at >= window_start,
            GatewayIncidentAlert.occurred_at <= window_end
        ).first()

        if existing:
            # Selalu perbarui informasi ke diagnosis terbaru yang paling presisi
            existing.alert_code = alert_code
            existing.category = category
            existing.severity = severity
            existing.title = title
            existing.message = message
            existing.component = component
            existing.recommendation = recommendation
            existing.downtime_duration = downtime_duration
            existing.downtime_seconds = downtime_seconds
            existing.occurred_at = occurred_at
            existing.recovered_at = recovered_at
            existing.status = status
            existing.extra_data = extra_data
            existing.telemetry_history_id = telemetry_history_id or existing.telemetry_history_id
            try:
                db.commit()
                db.refresh(existing)
                return existing
            except Exception as e:
                db.rollback()
                logger.warning(f"Failed to update downtime alert: {e}")
            return None

        dt_wib = occurred_at + timedelta(hours=7) if occurred_at else datetime.now(timezone.utc) + timedelta(hours=7)
        cal_date_str = dt_wib.strftime("%Y-%m-%d")
        day_down_min = round(downtime_seconds / 60.0, 1) if downtime_seconds else 0.0
        resolved_metric = "power" if "REBOOT" in alert_code or category == "POWER" else ("cpu_modem" if category == "CPU_MODEM" else ("cpu_dvr" if category in ["CPU_DVR", "DVR", "CCTV_NVR"] else "cellular"))

        # Buat entri baru jika belum pernah dicatat
        alert = GatewayIncidentAlert(
            device_id=dev_id,
            location=location,
            category=category,
            alert_code=alert_code,
            severity=severity,
            title=title,
            message=message,
            component=component,
            recommendation=recommendation,
            downtime_duration=downtime_duration,
            downtime_seconds=downtime_seconds,
            metric=resolved_metric,
            date_str=cal_date_str,
            day_downtime_minutes=day_down_min,
            occurred_at=occurred_at,
            recovered_at=recovered_at,
            status=status,
            extra_data=extra_data,
            telemetry_history_id=telemetry_history_id,
            created_at=datetime.utcnow()
        )
        db.add(alert)
        try:
            db.commit()
            db.refresh(alert)
            return alert
        except Exception as e:
            db.rollback()
            logger.warning(f"Failed to insert downtime alert: {e}")
            return None

    def _create_alert_if_not_exists(
        self,
        db: Session,
        dev_id: str,
        location: str,
        alert_code: str,
        category: str,
        severity: str,
        title: str,
        message: str,
        component: Optional[str],
        recommendation: Optional[str],
        downtime_duration: Optional[str],
        downtime_seconds: Optional[int],
        occurred_at: datetime,
        recovered_at: Optional[datetime],
        status: str,
        extra_data: Optional[Dict[str, Any]],
        telemetry_history_id: Optional[str] = None
    ) -> Optional[GatewayIncidentAlert]:
        """Menghindari duplikasi alert pada device yang sama dalam rentang waktu 15 menit."""
        # Jika status ACTIVE, jangan buat tiket baru jika tiket ACTIVE masih terbuka
        if status == "ACTIVE":
            active_existing = db.query(GatewayIncidentAlert.id).filter(
                GatewayIncidentAlert.device_id == dev_id,
                GatewayIncidentAlert.alert_code == alert_code,
                GatewayIncidentAlert.status == "ACTIVE"
            ).first()
            if active_existing:
                return None

        window_start = occurred_at - timedelta(minutes=15)
        window_end = occurred_at + timedelta(minutes=15)
        existing = db.query(GatewayIncidentAlert.id).filter(
            GatewayIncidentAlert.device_id == dev_id,
            GatewayIncidentAlert.alert_code == alert_code,
            GatewayIncidentAlert.occurred_at >= window_start,
            GatewayIncidentAlert.occurred_at <= window_end
        ).first()

        if existing:
            return None

        alert = GatewayIncidentAlert(
            device_id=dev_id,
            location=location,
            category=category,
            alert_code=alert_code,
            severity=severity,
            title=title,
            message=message,
            component=component,
            recommendation=recommendation,
            downtime_duration=downtime_duration,
            downtime_seconds=downtime_seconds,
            occurred_at=occurred_at,
            recovered_at=recovered_at,
            status=status,
            extra_data=extra_data,
            telemetry_history_id=telemetry_history_id,
            created_at=datetime.utcnow()
        )
        db.add(alert)
        try:
            db.commit()
            db.refresh(alert)
            return alert
        except Exception as e:
            db.rollback()
            logger.warning(f"Failed to insert incident alert: {e}")
            return None

    def get_incident_alerts(
        self,
        db: Session,
        device_id: Optional[str] = None,
        category: Optional[str] = None,
        severity: Optional[str] = None,
        status: Optional[str] = None,
        search: Optional[str] = None,
        limit: int = 50,
        offset: int = 0
    ) -> Dict[str, Any]:
        """Query alert dengan filter, pagination, dan ringkasan statistik."""
        query = db.query(GatewayIncidentAlert)

        if device_id:
            query = query.filter(GatewayIncidentAlert.device_id == device_id)
        if category:
            query = query.filter(GatewayIncidentAlert.category == category.upper())
        if severity:
            query = query.filter(GatewayIncidentAlert.severity == severity.upper())
        if status:
            query = query.filter(GatewayIncidentAlert.status == status.upper())
        if search:
            search_fmt = f"%{search}%"
            query = query.filter(
                (GatewayIncidentAlert.title.ilike(search_fmt)) |
                (GatewayIncidentAlert.location.ilike(search_fmt)) |
                (GatewayIncidentAlert.device_id.ilike(search_fmt)) |
                (GatewayIncidentAlert.component.ilike(search_fmt))
            )

        total_count = query.count()
        rows = query.order_by(desc(GatewayIncidentAlert.occurred_at)).offset(offset).limit(limit).all()

        # Statistik ringkasan insiden offline
        stats = {
            "total_offline_incidents": db.query(GatewayIncidentAlert).count(),
            "active_outages": db.query(GatewayIncidentAlert).filter(GatewayIncidentAlert.status == "ACTIVE").count(),
            "power_voltage_drop_issues": db.query(GatewayIncidentAlert).filter(GatewayIncidentAlert.category == "POWER").count(),
            "sim_card_issues": db.query(GatewayIncidentAlert).filter(GatewayIncidentAlert.category == "CELLULAR").count(),
            "lan_network_issues": db.query(GatewayIncidentAlert).filter(GatewayIncidentAlert.category == "NETWORK").count(),
        }

        items = []
        for r in rows:
            # Konversi ke WIB untuk tampilan
            occurred_wib = r.occurred_at + timedelta(hours=7) if r.occurred_at else None
            recovered_wib = r.recovered_at + timedelta(hours=7) if r.recovered_at else None

            items.append({
                "id": r.id,
                "device_id": r.device_id,
                "location": r.location,
                "category": r.category,
                "alert_code": r.alert_code,
                "severity": r.severity,
                "title": r.title,
                "message": r.message,
                "component": r.component,
                "recommendation": r.recommendation,
                "downtime_duration": r.downtime_duration,
                "downtime_seconds": r.downtime_seconds,
                "occurred_at_utc": r.occurred_at.strftime("%Y-%m-%d %H:%M:%S") if r.occurred_at else None,
                "occurred_at_wib": occurred_wib.strftime("%Y-%m-%d %H:%M:%S WIB") if occurred_wib else None,
                "recovered_at_wib": recovered_wib.strftime("%Y-%m-%d %H:%M:%S WIB") if recovered_wib else None,
                "status": r.status,
                "telemetry_history_id": r.telemetry_history_id,
                "extra_data": r.extra_data
            })

        return {
            "status": True,
            "total": total_count,
            "limit": limit,
            "offset": offset,
            "statistics": stats,
            "data": items
        }

    def get_summary_stats(self, db: Session, device_id: Optional[str] = None) -> Dict[str, Any]:
        query = db.query(GatewayIncidentAlert)
        if device_id:
            query = query.filter(GatewayIncidentAlert.device_id == device_id)

        return {
            "total_offline_incidents": query.count(),
            "active_outages": query.filter(GatewayIncidentAlert.status == "ACTIVE").count(),
            "power_voltage_drop_issues": query.filter(GatewayIncidentAlert.category == "POWER").count(),
            "sim_card_issues": query.filter(GatewayIncidentAlert.category == "CELLULAR").count(),
            "lan_network_issues": query.filter(GatewayIncidentAlert.category == "NETWORK").count(),
        }

    def backfill_from_telemetry_history(self, db: Session) -> int:
        """Memproses data historis yang sudah ada di gateway_telemetry_history ke tabel alert."""
        rows = db.query(GatewayTelemetryHistory).order_by(GatewayTelemetryHistory.recorded_at.asc()).all()
        total_created = 0
        logger.info(f"Starting backfill alerts from {len(rows)} telemetry history rows...")

        for r in rows:
            p = r.raw_payload or {}
            created = self.process_telemetry_for_alerts(
                db=db,
                dev_id=r.device_id,
                loc_name=r.location or f"Gateway {r.device_id}",
                payload=p,
                rec_dt=r.recorded_at,
                telemetry_history_id=r.id
            )
            total_created += len(created)

        logger.info(f"Backfill completed! Created/updated {total_created} incident alerts in database.")
        return total_created


incident_alert_service = IncidentAlertService()
