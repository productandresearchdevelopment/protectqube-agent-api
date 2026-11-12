import time
import logging
from collections import Counter
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)
WIB = timezone(timedelta(hours=7))


def _format_duration_short(seconds: float) -> str:
    sec = max(0, int(seconds))
    if sec < 60:
        return f"{sec}s"
    mins = sec // 60
    if mins < 60:
        return f"{mins}m"
    hours = mins // 60
    rem_m = mins % 60
    if hours < 24:
        return f"{hours}h {rem_m}m" if rem_m else f"{hours}h"
    days = hours // 24
    rem_h = hours % 24
    return f"{days}d {rem_h}h" if rem_h else f"{days}d"


class OverviewService:
    """
    Aggregates 100% real-time fleet overview summary, domain KPIs,
    real active incidents (offline gateways, cellular/SIM/signal issues,
    DVR/camera faults, system hardware alerts), and historical incident alerts.
    """

    def get_overview(self, db=None) -> Dict[str, Any]:
        from app.services.system_health_service import system_health_service
        from app.services.cellular_service import cellular_service
        from app.services.dvr_service import dvr_service
        from app.services.sla_report_service import sla_report_service
        from app.services.incident_alert_service import incident_alert_service

        # Sync freshness across all 3 real-time services
        system_health_service._sync_freshness()
        cellular_service._sync_freshness()
        dvr_service._sync_freshness()

        sh_map = system_health_service._live_gateways
        cel_map = cellular_service._live_gateways
        dvr_map = dvr_service._live_gateways
        sla_map = sla_report_service._live_gateways

        all_ids = list(dict.fromkeys(list(sh_map.keys()) + list(cel_map.keys()) + list(dvr_map.keys())))
        total = len(all_ids)
        now_ts = time.time()

        online_count = 0
        offline_count = 0
        warning_count = 0

        hitam_total = 0
        hitam_online = 0
        hitam_offline = 0
        putih_total = 0
        putih_online = 0
        putih_offline = 0

        # System health accumulators
        cpus: List[float] = []
        rams: List[float] = []
        sds: List[float] = []
        sd_lives: List[float] = []
        temps: List[float] = []
        sd_good = 0
        sd_warning = 0
        sd_critical = 0

        # Cellular accumulators
        rsrps: List[float] = []
        sig_dist = {"excellent": 0, "good": 0, "fair": 0, "poor": 0, "no_signal": 0}
        modem_connected = 0
        modem_disconnected = 0
        sim_ready = 0
        sim_not_detected = 0
        provider_counter: Counter = Counter()

        # System health status accumulators
        sh_normal = 0
        sh_warning = 0
        sh_critical = 0

        # Location & Client accumulators
        unique_locations = set()
        client_stats: Dict[str, Dict[str, int]] = {}

        # DVR accumulators
        total_cams = 0
        cams_online = 0
        cams_no_video = 0
        cams_offline = 0
        dvr_connected = 0
        dvr_disconnected = 0
        rec_active = 0
        rec_not_recording = 0
        rec_issue = 0
        total_storage_gb = 0.0
        used_storage_gb = 0.0
        brand_counter: Counter = Counter()

        active_incidents: List[Dict[str, Any]] = []

        for dev_id in all_ids:
            sh_entry = sh_map.get(dev_id, {})
            sh_item = sh_entry.get("table_item", {})
            sh_detail = sh_entry.get("detail_item", {})
            cel_entry = cel_map.get(dev_id, {})
            cel_item = cel_entry.get("item", {})
            cel_detail = cel_entry.get("detail", {})
            dvr_entry = dvr_map.get(dev_id, {})
            dvr_item = dvr_entry.get("table_item", {})
            sla_entry = sla_map.get(dev_id, {})

            location = (
                sh_item.get("location")
                or cel_item.get("location")
                or dvr_item.get("location")
                or dev_id
            )
            client_name = (
                sla_entry.get("customer")
                or sh_item.get("customer")
                or cel_item.get("customer")
                or dvr_item.get("customer")
                or "-"
            )
            if not client_name or client_name == "-":
                client_name = "-"

            gw_type = (
                sh_item.get("type")
                or cel_item.get("type")
                or dvr_item.get("type")
                or "SmartBox Putih"
            )
            is_black = "hitam" in gw_type.lower() or "black" in gw_type.lower()
            model_label = "SmartBox Black" if is_black else "SmartBox White"

            # Determine unified device online/offline status
            raw_status = (
                sh_item.get("status")
                or cel_item.get("status")
                or dvr_item.get("status")
                or "Offline"
            )
            is_offline = raw_status.lower() == "offline"
            last_seen = (
                sh_entry.get("last_seen_epoch")
                or cel_entry.get("last_seen_epoch")
                or dvr_entry.get("last_seen_epoch")
                or now_ts
            )
            last_update = (
                sh_item.get("last_update")
                or cel_item.get("last_update")
                or dvr_item.get("last_update")
                or "-"
            )

            if location:
                unique_locations.add(location.strip())

            c_key = client_name if (client_name and client_name != "-") else "Unassigned"
            if c_key not in client_stats:
                client_stats[c_key] = {
                    "total": 0,
                    "online": 0,
                    "offline": 0,
                    "sim_ready": 0,
                    "recording_active": 0,
                }
            client_stats[c_key]["total"] += 1
            if is_offline:
                client_stats[c_key]["offline"] += 1
            else:
                client_stats[c_key]["online"] += 1

            if is_black:
                hitam_total += 1
                if is_offline:
                    hitam_offline += 1
                else:
                    hitam_online += 1
            else:
                putih_total += 1
                if is_offline:
                    putih_offline += 1
                else:
                    putih_online += 1

            # Track domain metrics
            # --- System Health ---
            if not is_offline:
                if isinstance(sh_item.get("cpu"), (int, float)):
                    cpus.append(float(sh_item["cpu"]))
                if isinstance(sh_item.get("ram"), (int, float)):
                    rams.append(float(sh_item["ram"]))
                if isinstance(sh_item.get("sd_percent"), (int, float)):
                    sds.append(float(sh_item["sd_percent"]))
                if isinstance(sh_item.get("sd_health_percent"), (int, float)):
                    sd_lives.append(float(sh_item["sd_health_percent"]))

                sd_h = str(sh_item.get("sd_health", "Good")).lower()
                if "crit" in sd_h:
                    sd_critical += 1
                elif "warn" in sd_h:
                    sd_warning += 1
                else:
                    sd_good += 1

                raw_temp = cel_detail.get("modem_temperature", {}).get("temperature")
                if isinstance(raw_temp, (int, float)) and raw_temp > 0:
                    temps.append(float(raw_temp))
                else:
                    mt_str = str(cel_item.get("modem_temp", "")).replace("°C", "").strip()
                    try:
                        mt_f = float(mt_str)
                        if mt_f > 0:
                            temps.append(mt_f)
                    except ValueError:
                        pass

            # --- Cellular ---
            cpu_modem_ok = (cel_item.get("cpu_modem") == "Connected") and not is_offline
            if cpu_modem_ok:
                modem_connected += 1
            else:
                modem_disconnected += 1

            sim_st = str(cel_item.get("sim_status", "")).lower()
            is_sim_ok = (not is_offline) and any(k in sim_st for k in ["ready", "aktif", "active"])
            if is_sim_ok:
                sim_ready += 1
                client_stats[c_key]["sim_ready"] += 1
            else:
                sim_not_detected += 1

            prov = cel_item.get("provider") or "-"
            if prov and prov not in ["No SIM", "N/A", "-"]:
                provider_counter[prov] += 1

            rsrp_val: Optional[float] = None
            if is_sim_ok:
                rsrp_raw = cel_item.get("signal_rsrp", "")
                if isinstance(rsrp_raw, str) and "dBm" in rsrp_raw:
                    try:
                        rsrp_val = float(rsrp_raw.replace("dBm", "").strip())
                    except ValueError:
                        rsrp_val = None
                if rsrp_val is None:
                    d_rsrp = cel_detail.get("signal_strength", {}).get("rsrp")
                    if isinstance(d_rsrp, (int, float)):
                        rsrp_val = float(d_rsrp)
                if rsrp_val is not None and -140 <= rsrp_val <= -40:
                    rsrps.append(rsrp_val)
                    if rsrp_val >= -85:
                        sig_dist["excellent"] += 1
                    elif rsrp_val >= -95:
                        sig_dist["good"] += 1
                    elif rsrp_val >= -105:
                        sig_dist["fair"] += 1
                    else:
                        sig_dist["poor"] += 1
                else:
                    sig_dist["no_signal"] += 1
            else:
                sig_dist["no_signal"] += 1

            # --- DVR ---
            t_cam = int(dvr_item.get("total_kamera") or 0)
            o_cam = int(dvr_item.get("kamera_online") or 0) if not is_offline else 0
            nv_cam = int(dvr_item.get("kamera_no_video") or 0) if not is_offline else 0
            of_cam = int(dvr_item.get("kamera_offline") or 0) if not is_offline else t_cam

            total_cams += t_cam
            cams_online += o_cam
            cams_no_video += nv_cam
            cams_offline += of_cam

            dvr_ok = (dvr_item.get("cpu_dvr") == "Connected") and not is_offline
            if dvr_ok:
                dvr_connected += 1
            else:
                dvr_disconnected += 1

            rec_str = str(dvr_item.get("recording_status", ""))
            if dvr_ok and "0/" not in rec_str and "Recording" in rec_str:
                rec_active += 1
                client_stats[c_key]["recording_active"] += 1
            else:
                rec_issue += 1
                if dvr_ok:
                    rec_not_recording += 1

            cap_gb = float(dvr_entry.get("cap_gb") or 0.0)
            used_gb = float(dvr_entry.get("used_gb") or 0.0)
            total_storage_gb += cap_gb
            used_storage_gb += used_gb

            dvr_brand = str(dvr_item.get("dvr_model") or "")
            if dvr_brand and dvr_brand not in ["-", "N/A", "NVR Offline"]:
                if "hik" in dvr_brand.lower() or dvr_brand.upper().startswith("DS-"):
                    brand_counter["Hikvision"] += 1
                elif "dahua" in dvr_brand.lower() or dvr_brand.upper().startswith("DH-"):
                    brand_counter["Dahua"] += 1
                elif "hilook" in dvr_brand.lower():
                    brand_counter["HiLook"] += 1
                else:
                    brand_counter[dvr_brand.split()[0]] += 1

            # --- Active Incidents Detection (Online/Offline & Connection State Only) ---
            if is_offline:
                offline_count += 1
                down_dur = _format_duration_short(max(60.0, now_ts - last_seen))
                active_incidents.append({
                    "id": f"inc-offline-{dev_id}",
                    "device_id": dev_id,
                    "location": location,
                    "client": client_name,
                    "model": model_label,
                    "category": "offline",
                    "severity": "offline",
                    "alert_title": "Gateway Offline / Unreachable",
                    "alert_detail": f"No telemetry heartbeat received since {last_update}. Device unreachable.",
                    "metric": "Status: Offline",
                    "duration": down_dur,
                    "last_update": last_update,
                    "detail_href": "/system-health",
                })
                continue

            # Online device -> check subsystem connection / recording / power status
            # 1. Cellular checks
            if cel_item.get("cpu_modem") == "Not Connected":
                active_incidents.append({
                    "id": f"inc-modem-{dev_id}",
                    "device_id": dev_id,
                    "location": location,
                    "client": client_name,
                    "model": model_label,
                    "category": "cellular",
                    "severity": "disconnected",
                    "alert_title": "Modem USB Disconnected",
                    "alert_detail": "Serial communication between Gateway CPU and Quectel 4G modem lost.",
                    "metric": "CPU-Modem: Disconnected",
                    "duration": "Active",
                    "last_update": last_update,
                    "detail_href": "/cellular",
                })
            elif not is_sim_ok:
                active_incidents.append({
                    "id": f"inc-sim-{dev_id}",
                    "device_id": dev_id,
                    "location": location,
                    "client": client_name,
                    "model": model_label,
                    "category": "cellular",
                    "severity": "offline",
                    "alert_title": "SIM Card Not Detected",
                    "alert_detail": "Modem SIM tray reports no valid SIM card or cellular network registration failed.",
                    "metric": "SIM: Not Detected",
                    "duration": "Active",
                    "last_update": last_update,
                    "detail_href": "/cellular",
                })

            # 2. DVR / Camera checks
            if dvr_item and dvr_item.get("cpu_dvr") == "Not Connected":
                active_incidents.append({
                    "id": f"inc-dvr-{dev_id}",
                    "device_id": dev_id,
                    "location": location,
                    "client": client_name,
                    "model": model_label,
                    "category": "dvr",
                    "severity": "disconnected",
                    "alert_title": "DVR / NVR Disconnected",
                    "alert_detail": f"Gateway unable to reach {dvr_item.get('dvr_model', 'NVR')} via LAN ({dvr_item.get('ip_address', '-')}).",
                    "metric": "DVR: Disconnected",
                    "duration": "Active",
                    "last_update": last_update,
                    "detail_href": "/dvr-recording",
                })
            elif dvr_item and ("0/" in rec_str or of_cam > 0):
                is_zero_rec = "0/" in rec_str
                active_incidents.append({
                    "id": f"inc-cam-{dev_id}",
                    "device_id": dev_id,
                    "location": location,
                    "client": client_name,
                    "model": model_label,
                    "category": "dvr",
                    "severity": "offline",
                    "alert_title": "NVR Not Recording" if is_zero_rec else "CCTV Camera Offline",
                    "alert_detail": f"{o_cam}/{t_cam} cameras online, recording status: {rec_str or '0/0'}.",
                    "metric": f"Cam: {o_cam}/{t_cam} Online",
                    "duration": "Active",
                    "last_update": last_update,
                    "detail_href": "/dvr-recording",
                })

            # 3. Power outage / discharging check
            if sh_item.get("power_status") == "Discharging":
                active_incidents.append({
                    "id": f"inc-pwr-{dev_id}",
                    "device_id": dev_id,
                    "location": location,
                    "client": client_name,
                    "model": model_label,
                    "category": "system",
                    "severity": "offline",
                    "alert_title": "AC Power Lost (Running on Battery)",
                    "alert_detail": f"Gateway is discharging on backup battery ({sh_item.get('battery_percent') or '-'}%).",
                    "metric": "Power: Battery",
                    "duration": "Active",
                    "last_update": last_update,
                    "detail_href": "/system-health",
                })

            sh_normal += 1
            online_count += 1

        # Sort incidents: gateway offline -> cellular -> dvr -> power/system
        cat_priority = {"offline": 0, "cellular": 1, "dvr": 2, "system": 3}
        active_incidents.sort(
            key=lambda x: (cat_priority.get(x["category"], 4), x["location"])
        )

        # Percentages
        online_total = online_count + warning_count
        online_pct = round((online_total / total) * 100.0, 1) if total else 0.0
        warning_pct = round((warning_count / total) * 100.0, 1) if total else 0.0
        offline_pct = round((offline_count / total) * 100.0, 1) if total else 0.0

        # Aggregated metrics
        cpu_avg = round(sum(cpus) / len(cpus), 1) if cpus else 0.0
        cpu_max = round(max(cpus), 1) if cpus else 0.0
        ram_avg = round(sum(rams) / len(rams), 1) if rams else 0.0
        ram_max = round(max(rams), 1) if rams else 0.0
        sd_avg = round(sum(sds) / len(sds), 1) if sds else 0.0
        avg_sd_life = int(round(sum(sd_lives) / len(sd_lives))) if sd_lives else 100
        temp_avg = int(round(sum(temps) / len(temps))) if temps else 0
        temp_max = int(round(max(temps))) if temps else 0

        avg_rsrp = int(round(sum(rsrps) / len(rsrps))) if rsrps else None
        if avg_rsrp is None:
            sig_quality = "No Signal"
        elif avg_rsrp >= -85:
            sig_quality = "Excellent"
        elif avg_rsrp >= -95:
            sig_quality = "Good"
        elif avg_rsrp >= -105:
            sig_quality = "Fair"
        else:
            sig_quality = "Poor"

        modem_conn_pct = round((modem_connected / total) * 100.0, 1) if total else 0.0
        top_prov = "N/A"
        top_prov_pct = 0.0
        if provider_counter:
            top_p, top_cnt = provider_counter.most_common(1)[0]
            total_prov = sum(provider_counter.values())
            top_prov = top_p
            top_prov_pct = round((top_cnt / total_prov) * 100.0, 1) if total_prov else 0.0

        cam_online_pct = round((cams_online / total_cams) * 100.0, 1) if total_cams else 0.0
        dvr_conn_pct = round((dvr_connected / total) * 100.0, 1) if total else 0.0
        rec_active_pct = round((rec_active / total) * 100.0, 1) if total else 0.0
        total_storage_tb = round(total_storage_gb / 1024.0, 2)
        used_storage_tb = round(used_storage_gb / 1024.0, 2)
        storage_used_pct = round((used_storage_gb / total_storage_gb) * 100.0, 1) if total_storage_gb > 0 else 0.0

        top_brand = "Hikvision"
        if brand_counter:
            top_brand = " / ".join(b for b, _ in brand_counter.most_common(2))

        # Historical Incident Alerts from DB (optional fallback if DB offline)
        recent_history_alerts: List[Dict[str, Any]] = []
        db_incident_stats = {
            "total_offline_incidents": 0,
            "active_outages": 0,
            "cpu_modem_issues": 0,
            "cellular_issues": 0,
            "cpu_dvr_issues": 0,
        }
        if db is not None:
            try:
                hist_res = incident_alert_service.get_incident_alerts(db=db, limit=15, offset=0)
                if hist_res and hist_res.get("status"):
                    recent_history_alerts = hist_res.get("data", [])
                    db_incident_stats = hist_res.get("statistics", db_incident_stats)
            except Exception as e:
                logger.debug(f"Could not fetch historical incident alerts from DB: {e}")

        # Real Charts from the 3 domain services
        sh_charts = system_health_service.get_chart_telemetry()
        cel_charts = cellular_service.get_charts()
        dvr_charts = dvr_service.get_charts()

        # Provider list sorted by count
        total_prov_sum = sum(provider_counter.values())
        providers_list = [
            {
                "name": p_name,
                "count": p_cnt,
                "percent": round((p_cnt / total_prov_sum) * 100.0, 1) if total_prov_sum else 0.0,
            }
            for p_name, p_cnt in provider_counter.most_common(5)
        ]

        # Clients summary list
        clients_list = [
            {
                "name": c_name,
                "total": c_val["total"],
                "online": c_val["online"],
                "offline": c_val["offline"],
                "sim_ready": c_val["sim_ready"],
                "recording_active": c_val["recording_active"],
                "uptime_pct": round((c_val["online"] / c_val["total"]) * 100.0, 1) if c_val["total"] else 0.0,
            }
            for c_name, c_val in sorted(client_stats.items(), key=lambda x: -x[1]["total"])
        ]

        # Subsystem comparison bar chart data
        subsystem_comparison = [
            {
                "name": "Gateway",
                "healthy": online_total,
                "issue": offline_count,
                "healthy_pct": online_pct,
            },
            {
                "name": "Modem USB",
                "healthy": modem_connected,
                "issue": modem_disconnected,
                "healthy_pct": modem_conn_pct,
            },
            {
                "name": "SIM Card",
                "healthy": sim_ready,
                "issue": sim_not_detected,
                "healthy_pct": round((sim_ready / total) * 100.0, 1) if total else 0.0,
            },
            {
                "name": "DVR / NVR",
                "healthy": dvr_connected,
                "issue": dvr_disconnected,
                "healthy_pct": dvr_conn_pct,
            },
            {
                "name": "Recording",
                "healthy": rec_active,
                "issue": rec_issue,
                "healthy_pct": rec_active_pct,
            },
            {
                "name": "Cameras",
                "healthy": cams_online,
                "issue": cams_no_video + cams_offline,
                "healthy_pct": cam_online_pct,
            },
        ]

        return {
            "fleet": {
                "total_locations": len(unique_locations),
                "total_clients": len([c for c in clients_list if c["name"] != "Unassigned"]),
                "total_gateways": total,
                "online": online_total,
                "healthy": online_count,
                "warning": warning_count,
                "offline": offline_count,
                "online_percent": online_pct,
                "warning_percent": warning_pct,
                "offline_percent": offline_pct,
                "smartbox_hitam": {
                    "total": hitam_total,
                    "online": hitam_online,
                    "offline": hitam_offline,
                },
                "smartbox_putih": {
                    "total": putih_total,
                    "online": putih_online,
                    "offline": putih_offline,
                },
            },
            "system_health": {
                "cpu_avg": cpu_avg,
                "cpu_max": cpu_max,
                "ram_avg": ram_avg,
                "ram_max": ram_max,
                "sd_avg": sd_avg,
                "avg_sd_life": avg_sd_life,
                "sd_good": sd_good,
                "sd_warning": sd_warning,
                "sd_critical": sd_critical,
                "temp_avg": temp_avg,
                "temp_max": temp_max,
                "sla_pct": online_pct,
                "health_distribution": {
                    "normal": sh_normal,
                    "warning": sh_warning,
                    "critical": sh_critical,
                    "offline": offline_count,
                },
            },
            "cellular": {
                "avg_rsrp": avg_rsrp,
                "signal_quality": sig_quality,
                "modem_connected": modem_connected,
                "modem_disconnected": modem_disconnected,
                "modem_connected_pct": modem_conn_pct,
                "sim_ready": sim_ready,
                "sim_not_detected": sim_not_detected,
                "top_provider": top_prov,
                "top_provider_pct": top_prov_pct,
                "providers": providers_list,
                "signal_distribution": sig_dist,
                "sla_pct": round((sim_ready / total) * 100.0, 1) if total else 0.0,
            },
            "dvr": {
                "total_cameras": total_cams,
                "cameras_online": cams_online,
                "cameras_no_video": cams_no_video,
                "cameras_offline": cams_offline,
                "camera_online_pct": cam_online_pct,
                "dvr_connected": dvr_connected,
                "dvr_disconnected": dvr_disconnected,
                "dvr_connected_pct": dvr_conn_pct,
                "recording_active": rec_active,
                "recording_not_recording": rec_not_recording,
                "recording_issue": rec_issue,
                "recording_active_pct": rec_active_pct,
                "recording_distribution": {
                    "recording": rec_active,
                    "not_recording": rec_not_recording,
                    "disconnected": max(0, dvr_disconnected - offline_count),
                    "offline": offline_count,
                },
                "total_storage_tb": total_storage_tb,
                "used_storage_tb": used_storage_tb,
                "storage_used_pct": storage_used_pct,
                "top_brand": top_brand,
                "sla_pct": dvr_conn_pct,
            },
            "clients_summary": clients_list,
            "subsystem_comparison": subsystem_comparison,
            "incidents_summary": {
                "total_active_alerts": len(active_incidents),
                "offline_count": sum(1 for i in active_incidents if i["category"] == "offline"),
                "critical_count": sum(1 for i in active_incidents if i["severity"] == "critical"),
                "warning_count": sum(1 for i in active_incidents if i["severity"] == "warning"),
                "cellular_count": sum(1 for i in active_incidents if i["category"] == "cellular"),
                "dvr_count": sum(1 for i in active_incidents if i["category"] == "dvr"),
                "system_count": sum(1 for i in active_incidents if i["category"] == "system"),
                "db_stats": db_incident_stats,
            },
            "active_incidents": active_incidents,
            "recent_history_alerts": recent_history_alerts,
            "charts": {
                "system": sh_charts,
                "cellular": cel_charts,
                "dvr": dvr_charts,
            },
            "updated_at": datetime.now(WIB).strftime("%Y-%m-%d %H:%M:%S WIB"),
        }


overview_service = OverviewService()
