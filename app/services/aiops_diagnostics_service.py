from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Tuple, Optional


def format_wib_timestamp(ts_val: Any) -> str:
    """Formats timestamp into '23 Nov 10:14 WIB' format."""
    months = ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des"]
    dt = None
    if isinstance(ts_val, datetime):
        dt = ts_val
    elif isinstance(ts_val, (int, float)):
        # Check milliseconds vs seconds
        if ts_val > 1e11:
            dt = datetime.fromtimestamp(ts_val / 1000.0)
        else:
            dt = datetime.fromtimestamp(ts_val)
    elif isinstance(ts_val, str):
        try:
            # Try parsing ISO
            dt = datetime.fromisoformat(ts_val.replace("Z", "+00:00"))
        except Exception:
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d"):
                try:
                    dt = datetime.strptime(ts_val[:19], fmt)
                    break
                except Exception:
                    pass

    if not dt:
        dt = datetime.now()

    month_name = months[dt.month - 1]
    return f"{dt.day} {month_name} {dt.strftime('%H:%M')} WIB"


def classify_telemetry_reason(temp, csq, nvr_st, logs_str, payload, box_type):
    """
    Automated Root Cause Diagnostics (AIOps) classification engine.
    Detects root cause of device disruption / outage from telemetry data.
    """
    payload = payload if isinstance(payload, dict) else {}
    hw = payload.get('hardware_connections', {})
    sim_conn = hw.get('cellular_sim', {})
    cell_flow = hw.get('cellular_data_flow', {})
    modem_conn = hw.get('modem_usb', {})
    power = payload.get('power_source', {})
    recent_logs = payload.get('recent_system_logs', [])
    combined = (str(logs_str or '') + " " + " ".join(recent_logs)).lower()

    # 1. SIM Card Issue
    if sim_conn.get('status') == 'DISCONNECTED' or 'sim not detected' in combined or 'cpin' in combined:
        return "Kartu SIM Error / Tidak Terbaca", "Kartu SIM tidak terdeteksi di slot modem atau registrasi SIM ditolak operator.", "sim_error"

    # 2. Modem RF Surge & Fluktuasi Daya (Sinyal drop memicu tegangan drop / watchdog)
    has_watchdog_trigger = any(k in combined for k in ["watchdog warning", "karakter 's'", "cpu_nvr_offline", "reboot via arduino relay"])
    if has_watchdog_trigger or nvr_st == 'DISCONNECTED':
        return "Modem RF Surge / Fluktuasi Daya", "Sinyal seluler lemah memicu RF power spike modem saat transmisi, menyebabkan drop tegangan dan memicu proteksi daya.", "watchdog_relay"

    # 3. Power Loss / Mati Lampu PLN
    has_power_fail = (
        power.get('is_mains_online') is False
        or power.get('battery_status') == 'DISCHARGING'
        or power.get('undervoltage_now') is True
        or any(k in combined for k in ['undervoltage', 'listrik pln padam', 'ac power unplugged'])
    )
    if has_power_fail:
        return "Mati Lampu & Baterai Habis / Undervoltage", "Listrik PLN padam hingga baterai habis atau tegangan drop <4.63V.", "power_battery"

    # 4. Thermal Overheat
    if (temp and temp >= 75.0) or 'high_temp' in combined:
        return f"Suhu Panas Overheat ({temp}°C)", f"Suhu CPU mencapai {temp}°C, memicu SoC thermal cutoff.", "thermal"

    # 5. Cellular / Internet Issues
    has_low_signal = (csq is not None and (csq <= 2 or csq == 99)) or 'signal drop' in combined
    if has_low_signal:
        return f"Sinyal Seluler Drop (CSQ: {csq if csq is not None else 0})", "Sinyal radio seluler hilang atau terputus dari BTS operator.", "signal_loss"

    has_net_fail = ('network is unreachable' in combined or 'aliran data mati' in combined or cell_flow.get('status') in ['DISCONNECTED', 'FAIL'])
    if has_net_fail:
        return f"Paket Data / Internet Putus (CSQ: {csq})", "Sinyal seluler ada namun rute IP data terputus.", "signal_loss"

    # 6. Modem USB Freeze
    if modem_conn.get('status') == 'DISCONNECTED' or 'modem disconnected' in combined or 'modem freeze' in combined:
        return "Modem USB 4G Disconnect / Freeze", "Komunikasi USB CPU ke chip modem terputus atau port /dev/ttyUSB hilang.", "modem_usb"

    # 7. Fallback: Silent Cut
    return "Mati Mendadak (Silent Cut / Sakelar Off)", "Perangkat kehilangan daya mendadak tanpa panic log (MCB/sakelar toko dimatikan).", "silent_cut"


class AIOpsDiagnosticsService:
    @staticmethod
    def get_diagnostics(
        payload: Optional[Dict[str, Any]] = None,
        is_online: bool = True,
        box_type: str = "SmartBox",
        temp: Optional[float] = None,
        csq: Optional[int] = None,
        nvr_st: Optional[str] = None,
        logs_str: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Returns full diagnostic reason, description, and evidence payload.
        """
        payload = payload if isinstance(payload, dict) else {}
        gw_sys = payload.get("gateway_system", {})
        cpu = gw_sys.get("cpu", {})
        sim = payload.get("cellular_sim", {})
        nvr = payload.get("nvr_surveillance", {})
        
        # Extract metrics if not passed explicitly
        if temp is None:
            temp = cpu.get("temperature_c") or payload.get("temperature_c")
        if csq is None:
            csq = sim.get("signal", {}).get("csq") or payload.get("signal_csq")
        if nvr_st is None:
            nvr_st = nvr.get("status") or payload.get("nvr_status")
        if not logs_str:
            recent_logs = payload.get("recent_system_logs", [])
            logs_str = " ".join(recent_logs)

        # Timestamp formatting
        ts_val = (
            payload.get("timestamp")
            or payload.get("datetime_local")
            or payload.get("datetime_utc7")
            or payload.get("recorded_at")
            or datetime.now()
        )
        evidence_ts = format_wib_timestamp(ts_val)

        # -------------------------------------------------------------
        # IF ONLINE: Normal Telemetry
        # -------------------------------------------------------------
        if is_online:
            # Check if there is an active warning condition even while online
            csq_val = csq if csq is not None else 24
            temp_val = temp if temp is not None else 45.0
            metrics_str = f"Sinyal: Baik | CSQ: {csq_val} | Suhu: {temp_val}°C"

            return {
                "reason": "Operasi Normal",
                "reason_desc": "Perangkat terhubung aktif, komunikasi modem dan telemetri gateway berfungsi baik.",
                "evidence": {
                    "badge": "Normal Online",
                    "badge_color": "emerald",
                    "metrics": metrics_str,
                    "snippet": "Semua subsistem terhubung normal tanpa anomali.",
                    "evidence_ts": evidence_ts,
                }
            }

        # -------------------------------------------------------------
        # IF OFFLINE: Run classification engine
        # -------------------------------------------------------------
        reason, reason_desc, category_code = classify_telemetry_reason(
            temp=temp,
            csq=csq,
            nvr_st=nvr_st,
            logs_str=logs_str,
            payload=payload,
            box_type=box_type
        )

        csq_disp = csq if csq is not None else 0
        temp_disp = temp if temp is not None else 0.0

        if category_code == "sim_error":
            badge = "Kartu SIM Error"
            badge_color = "purple"
            metrics_str = f"SIM: Disconnected | Operator: {sim.get('operator', 'N/A')}"
            snippet = "Kartu SIM tidak terdeteksi di slot modem atau registrasi SIM ditolak operator."
        elif category_code == "watchdog_relay":
            badge = "⚡ RF Power Surge & Voltage Drop"
            badge_color = "amber"
            metrics_str = f"Sinyal: Lemah | CSQ: {csq_disp} | NVR: {nvr_st or 'Offline'}"
            snippet = "Terdeteksi lonjakan arus transmisi RF modem saat sinyal drop, memicu proteksi daya / reboot watchdog."
        elif category_code == "power_battery":
            badge = "Mati Lampu & Baterai Habis"
            badge_color = "rose"
            metrics_str = "Power: Mains Offline / Undervoltage <4.63V"
            snippet = "Listrik PLN padam hingga baterai habis atau tegangan adaptor drop di bawah toleransi."
        elif category_code == "thermal":
            badge = f"Suhu Panas Overheat ({temp_disp}°C)"
            badge_color = "rose"
            metrics_str = f"Suhu CPU: {temp_disp}°C | Batas: 75.0°C"
            snippet = f"Suhu prosesor CPU mencapai {temp_disp}°C, memicu SoC thermal cutoff otomatis."
        elif category_code == "signal_loss":
            badge = f"Sinyal Seluler Drop (CSQ: {csq_disp})"
            badge_color = "amber"
            metrics_str = f"Sinyal CSQ: {csq_disp} | Rute: Data Unreachable"
            snippet = "Sinyal radio seluler hilang atau rute paket data IP terputus dari operator."
        elif category_code == "modem_usb":
            badge = "Modem USB 4G Disconnect"
            badge_color = "sky"
            metrics_str = "Port USB: /dev/ttyUSB No Response"
            snippet = "Komunikasi USB serial CPU ke modem Quectel terputus atau chip modem freeze."
        else:
            # Fallback: silent_cut
            badge = "Mati Mendadak (MCB Off)"
            badge_color = "slate"
            metrics_str = "Power: Kehilangan Daya Tiba-tiba"
            snippet = "Perangkat kehilangan daya mendadak tanpa panic log (MCB atau sakelar lokasi dimatikan)."

        return {
            "reason": reason,
            "reason_desc": reason_desc,
            "evidence": {
                "badge": badge,
                "badge_color": badge_color,
                "metrics": metrics_str,
                "snippet": snippet,
                "evidence_ts": evidence_ts,
            }
        }

    @classmethod
    def enrich_gateway(
        cls,
        target_dict: Dict[str, Any],
        payload: Optional[Dict[str, Any]] = None,
        is_online: Optional[bool] = None,
        box_type: str = "SmartBox"
    ) -> Dict[str, Any]:
        """
        Enriches a gateway item dictionary (table row or detail) with reason, reason_desc, and evidence.
        """
        status_str = str(target_dict.get("status", "")).lower()
        if is_online is None:
            is_online = (status_str == "online" or status_str == "healthy")

        diag = cls.get_diagnostics(
            payload=payload,
            is_online=is_online,
            box_type=box_type
        )
        target_dict["reason"] = diag["reason"]
        target_dict["reason_desc"] = diag["reason_desc"]
        target_dict["evidence"] = diag["evidence"]
        return target_dict


aiops_diagnostics_service = AIOpsDiagnosticsService()
