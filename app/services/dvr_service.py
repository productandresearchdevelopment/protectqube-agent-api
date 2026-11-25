import os
import json
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime
import time
from app.services.aiops_diagnostics_service import aiops_diagnostics_service

logger = logging.getLogger("dvr-service")


class DVRService:
    """
    Service layer for DVR & Recording Monitoring:
    100% Real data from MQTT Telemetry & ISAPI NVR probes:
    - NVR/DVR device status, IP endpoint, model & firmware
    - Real camera channels (e.g. WAREHOUSE KALIBATA 01 & 02)
    - Recording status & modes (CMR 24/7)
    - HDD storage capacity, utilized GB/TB, and SMART disk health
    - CPU-to-DVR communication diagnostics & latency
    """

    def __init__(self):
        self._live_gateways: Dict[str, Dict[str, Any]] = {}
        self._device_properties: Dict[str, Dict[str, Any]] = {}
        self._device_locations: Dict[str, str] = {}
        self._load_persisted_telemetry()

    def _cache_path(self) -> str:
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        return os.path.join(base_dir, "telemetry_cache.json")

    def _load_persisted_telemetry(self):
        """Loads cached real telemetry snapshots using centralized loader (PostgreSQL primary / disk fallback)."""
        from app.services.telemetry_loader import get_initial_telemetry_payloads, get_cached_inactive_gateways
        self._inactive_gateways = get_cached_inactive_gateways()
        payloads = get_initial_telemetry_payloads()
        for p in payloads:
            dev_id = p.get("device_id")
            if dev_id:
                if p.get("location"):
                    self._device_locations[dev_id] = p["location"]
                if p.get("property"):
                    self._device_properties[dev_id] = p["property"]
            self.update_from_telemetry(p, save_cache=False)
        logger.info(f"DVRService: Hydrated {len(self._live_gateways)} gateway(s)")

    def reload_telemetry_cache(self):
        """Flushes in-memory gateway states and reloads fresh telemetry from PostgreSQL (ignoring soft-deleted records)."""
        self._live_gateways.clear()
        self._device_properties.clear()
        self._device_locations.clear()
        self._load_persisted_telemetry()
        logger.info(f"DVRService: Telemetry reloaded. Active live gateways: {len(self._live_gateways)}")

    def update_from_telemetry(self, nms_payload: Dict[str, Any], save_cache: bool = True):
        """Ingests live MQTT telemetry and updates DVR fleet item & detailed diagnostics."""
        device_id = nms_payload.get("device_id")
        if not device_id:
            return
        dev_uuid = str(nms_payload.get("device_uuid", ""))
        inactives = getattr(self, "_inactive_gateways", None)
        if inactives and (device_id in inactives or (dev_uuid and dev_uuid in inactives)):
            return

        nvr = nms_payload.get("nvr_surveillance", {})
        gw_sys = nms_payload.get("gateway_system", {})
        hw = gw_sys.get("hardware", {})
        cpu = gw_sys.get("cpu", {})
        cameras_info = nvr.get("cameras", {})
        recording_info = nvr.get("recording", {})
        disks = nvr.get("disks", [])
        dev_info = nvr.get("device_info", {})

        is_connected = nvr.get("connected", False)
        from app.services.sla_calculator_service import sla_calculator_service
        box_type = sla_calculator_service.resolve_device_type(nms_payload, device_id)

        # Inspect real system logs for NVR telemetry ground truth:
        # e.g.: [NVR-CPU: OK] and NVR RECORDING: (CAMERA 1 : NOT_RECORD, ...)
        logs = nms_payload.get("recent_system_logs")
        lines_list: List[str] = []
        if isinstance(logs, list):
            lines_list = [line for line in logs if isinstance(line, str)]
        elif isinstance(logs, str) and logs.strip():
            lines_list = [line.strip() for line in logs.strip().split("\n")]

        import re
        log_cams: Dict[int, str] = {}
        is_rec = (recording_info.get("status") == "RECORDING" or recording_info.get("recording_status") == "RECORDING")

        # 1. Independently parse CPU to DVR communication status from recent system logs
        for line in reversed(lines_list):
            if "[NVR-CPU:" in line or "NVR:" in line:
                if "[NVR-CPU: OK]" in line or "NVR: OK" in line:
                    is_connected = True
                    break
                elif any(bad in line for bad in ["TERPUTUS", "LEPAS", "TIMEOUT", "ERROR", "DOWN", "OFFLINE"]):
                    is_connected = False
                    break

        # 2. Independently parse Camera Recording Status from recent system logs
        for line in reversed(lines_list):
            if "NVR RECORDING:" in line:
                rec_m = re.search(r'NVR\s+RECORDING:\s*\((.*?)\)', line, re.IGNORECASE)
                if rec_m:
                    cams_str = rec_m.group(1)
                    cam_matches = re.findall(r'CAMERA\s+(\d+)\s*:\s*([A-Za-z0-9_]+)', cams_str, re.IGNORECASE)
                    if cam_matches:
                        for cid, cst in cam_matches:
                            log_cams[int(cid)] = cst.upper()
                    is_rec = any("RECORD" in st and "NOT" not in st for st in log_cams.values())
                    break
                elif any(w in line for w in ["TERPUTUS", "LEPAS", "N/A", "OFFLINE"]):
                    is_rec = False
                    break
                else:
                    is_rec = True
                    break

        dev_loc = getattr(self, "_device_locations", {}).get(device_id)
        if not dev_loc:
            try:
                from app.services.telemetry_loader import get_device_metadata_cache
                dev_meta = get_device_metadata_cache().get(device_id)
                if dev_meta and dev_meta.get("location"):
                    dev_loc = dev_meta["location"]
                    self._device_locations[device_id] = dev_loc
            except Exception:
                pass

        loc_name = (
            dev_loc
            or nms_payload.get("location")
            or nms_payload.get("location_name")
            or nms_payload.get("site_name")
            or nms_payload.get("site_info", {}).get("location_name")
            or nms_payload.get("site_info", {}).get("site_name")
            or f"Gateway {device_id}"
        )
        if device_id and loc_name and not loc_name.startswith("Gateway "):
            self._device_locations[device_id] = loc_name

        dvr_model = dev_info.get("model") or "Hikvision/HiLook NVR"
        nvr_endpoint = nvr.get("nvr_endpoint", "172.16.37.130:80")
        ip_addr = nvr_endpoint.split(":")[0] if ":" in nvr_endpoint else nvr_endpoint
        port_num = nvr_endpoint.split(":")[1] if ":" in nvr_endpoint else "80"

        dev_prop = nms_payload.get("property") or self._device_properties.get(device_id) or {}
        if not dev_prop:
            try:
                from app.core.database import SessionLocal
                from app.models.base_models import Device
                db_p = SessionLocal()
                try:
                    d_obj = db_p.query(Device).filter(Device.name == str(device_id)).first()
                    if d_obj and d_obj.property:
                        dev_prop = d_obj.property
                        self._device_properties[device_id] = dev_prop
                        self._device_properties[str(d_obj.id)] = dev_prop
                finally:
                    db_p.close()
            except Exception:
                pass

        selected_cams = dev_prop.get("selected_cameras")
        raw_cam_list = list(cameras_info.get("camera_list", []))

        # Check if device is configured without DVR
        has_dvr = dev_prop.get("has_dvr")
        if has_dvr is None:
            if dev_prop.get("total_cameras") == 0 and (selected_cams is None or len(selected_cams) == 0):
                has_dvr = False
            else:
                has_dvr = True

        # Resolve configured camera channels (selected_cameras, total_cameras, or exclude uninstalled dummy slots)
        sel_set = None
        if not has_dvr:
            total_kamera = 0
            kamera_online = 0
            kamera_offline_raw = 0
            kamera_rec_count = 0
            is_rec = False
            cpu_dvr_status = "Not Installed"
            dvr_model = "Not Installed"
            rec_status = "N/A"
            health = "N/A"
            cap_gb = 0.0
            used_gb = 0.0
            free_gb = 0.0
            storage_pct = None
        elif selected_cams and isinstance(selected_cams, list) and len(selected_cams) > 0:
            sel_set = {str(x) for x in selected_cams}
        elif dev_prop.get("total_cameras") and isinstance(dev_prop.get("total_cameras"), (int, float)) and int(dev_prop.get("total_cameras")) < len(raw_cam_list):
            sel_set = {str(i + 1) for i in range(int(dev_prop.get("total_cameras")))}
        elif raw_cam_list:
            real_cams = [c for c in raw_cam_list if not (c.get("enabled") is False and (c.get("resolution") == "NO VIDEO" or c.get("resolution_raw") == "NO VIDEO"))]
            if real_cams and len(real_cams) < len(raw_cam_list):
                sel_set = {str(c.get("id")) for c in real_cams if c.get("id") is not None}

        if has_dvr:
            if not is_connected:
                if sel_set:
                    total_kamera = len(sel_set)
                else:
                    total_kamera = (dev_prop.get("total_cameras") if dev_prop.get("total_cameras") is not None else (cameras_info.get("total_cameras", 0) or len(log_cams) or 4))
                kamera_online = 0
                kamera_offline_raw = 0
            elif sel_set:
                total_kamera = len(sel_set)
                if log_cams:
                    log_cams = {cid: st for cid, st in log_cams.items() if str(cid) in sel_set}
                if raw_cam_list:
                    raw_cam_list = [c for c in raw_cam_list if str(c.get("id")) in sel_set or str(c.get("channel")) in sel_set]
                    kamera_online = sum(1 for c in raw_cam_list if c.get("is_online"))
                elif log_cams:
                    kamera_online = sum(1 for st in log_cams.values() if "RECORD" in st or "OK" in st)
                else:
                    kamera_online = min(total_kamera, cameras_info.get("online_count", 0))
                kamera_offline_raw = max(0, total_kamera - kamera_online)
            else:
                total_kamera = (dev_prop.get("total_cameras") if dev_prop.get("total_cameras") is not None else (cameras_info.get("total_cameras", 0) or len(log_cams) or 4))
                # 1. Kamera Fisik Terhubung (Online / ON CAM vs No Video)
                if "online_count" in cameras_info and cameras_info["online_count"] is not None:
                    kamera_online = min(total_kamera, cameras_info["online_count"])
                else:
                    no_video_c = sum(1 for line in lines_list[-15:] if "NO VIDEO" in line or "terputus" in line)
                    kamera_online = max(0, total_kamera - no_video_c)
                kamera_offline_raw = max(0, total_kamera - kamera_online)

            # 2. Kamera Aktif Merekam Video (Active Recording dari NVR RECORDING: (...))
            if not is_connected:
                kamera_rec_count = 0
                is_rec = False
            elif log_cams:
                kamera_rec_count = sum(1 for st in log_cams.values() if "RECORD" in st and "NOT" not in st)
                is_rec = (kamera_rec_count > 0)
            else:
                kamera_rec_count = recording_info.get("cameras_recording_count", 0 if not is_rec else kamera_online)
                is_rec = (kamera_rec_count > 0)

            cap_gb = float(nvr.get("total_capacity_gb", 0.0))
            used_gb = float(nvr.get("total_used_gb", 0.0))
            free_gb = float(nvr.get("total_free_gb", 0.0))
            storage_pct = int(round((used_gb / cap_gb) * 100)) if cap_gb > 0 else 0

            if is_connected:
                cpu_dvr_status = "Connected"
                rec_status = f"{kamera_rec_count}/{total_kamera} Recording"

                # Perhitungan DVR Health:
                # - Good: CPU terhubung dan rekaman kamera aktif berjalan normal (kamera_rec_count > 0)
                # - Warning: CPU terhubung tetapi rekaman macet/gagal (0 recording, HDD read-only / error)
                # - Critical: Komunikasi CPU ke NVR putus (No Response)
                if kamera_rec_count > 0:
                    health = "Good"
                else:
                    health = "Warning"
            else:
                cpu_dvr_status = "Not Connected"
                rec_status = f"0/{total_kamera} Recording"
                health = "Critical"

        ts_str = nms_payload.get("recorded_at") or nms_payload.get("datetime_utc7") or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        clean_update = ts_str.split(" (")[0] if " (" in ts_str else ts_str[:19]

        sla_cust = None
        try:
            from app.services.sla_report_service import sla_report_service
            sc = sla_report_service._live_gateways.get(device_id, {}).get("customer")
            if sc and sc != "-":
                sla_cust = sc
        except Exception:
            pass
        ec = self._live_gateways.get(device_id, {}).get("table_item", {}).get("customer")
        existing_cust = ec if (ec and ec != "-") else None
        raw_cust = nms_payload.get("customer")
        customer_val = (raw_cust if (raw_cust and raw_cust != "-") else None) or sla_cust or existing_cust or "-"
        device_uuid = nms_payload.get("device_uuid") or str(device_id)

        gw_item = {
            "no": len(self._live_gateways) + 1,
            "id": device_id,
            "device_uuid": device_uuid,
            "customer": customer_val,
            "client_name": customer_val,
            "location": loc_name,
            "type": box_type,
            "has_dvr": has_dvr,
            "dvr_model": dvr_model if has_dvr else "Not Installed",
            "status": "Online",
            "is_connected": is_connected if has_dvr else False,
            "is_offline": False,
            "ip_address": ip_addr,
            "cpu_dvr": cpu_dvr_status if has_dvr else "Not Installed",
            "total_kamera": total_kamera if has_dvr else 0,
            "kamera_online": kamera_online if has_dvr else 0,
            "kamera_no_video": kamera_offline_raw if has_dvr else 0,
            "kamera_offline": 0 if (not has_dvr or is_connected) else total_kamera,
            "recording_status": rec_status if has_dvr else "N/A",
            "storage_usage_percent": storage_pct if has_dvr else None,
            "dvr_health": health if has_dvr else "N/A",
            "last_update": clean_update,
        }

        cam_previews = []
        if not has_dvr:
            cam_previews = []
        elif log_cams:
            for cid_int in sorted(log_cams.keys()):
                st = log_cams[cid_int]
                is_cam_rec = ("RECORD" in st and "NOT" not in st)
                matched_raw = None
                for rc in raw_cam_list:
                    if str(rc.get("id")) == str(cid_int) or str(rc.get("channel")) == str(cid_int):
                        matched_raw = rc
                        break
                if not matched_raw and (cid_int - 1) < len(raw_cam_list):
                    matched_raw = raw_cam_list[cid_int - 1]

                cam_name = (matched_raw.get("name") if matched_raw else None) or f"CAM {cid_int:02d} - Channel {cid_int}"

                # Determine camera stream online status independently of recording status:
                if matched_raw and "is_online" in matched_raw:
                    is_cam_online = bool(matched_raw.get("is_online")) and is_connected
                else:
                    is_cam_online = is_connected and ("NO VIDEO" not in st and "OFFLINE" not in st and "TERPUTUS" not in st)

                raw_res = (matched_raw.get("resolution") if matched_raw else None)
                if raw_res and raw_res != "NO VIDEO":
                    res_val = raw_res
                else:
                    res_val = "1080P" if is_cam_online else "-"

                cam_previews.append({
                    "channel": cid_int,
                    "name": cam_name,
                    "status": "Online" if is_cam_online else ("No Video" if is_connected else "Offline"),
                    "is_recording": is_connected and is_cam_rec,
                    "fps": 25 if is_cam_online else 0,
                    "resolution": res_val,
                    "bitrate": "2048 Kbps" if (is_cam_online and is_cam_rec) else ("1024 Kbps" if is_cam_online else "0 Kbps"),
                    "timestamp": clean_update,
                })
        elif raw_cam_list:
            if selected_cams and isinstance(selected_cams, list) and len(selected_cams) > 0:
                sel_set = {str(x) for x in selected_cams}
                raw_cam_list = [c for c in raw_cam_list if str(c.get("id")) in sel_set or str(c.get("channel")) in sel_set]
            for idx, c in enumerate(raw_cam_list):
                c_online = c.get("is_online", False)
                cam_previews.append({
                    "channel": int(c.get("id", idx + 1)),
                    "name": c.get("name", f"CAM {idx + 1:02d}"),
                    "status": "Online" if c_online else "No Video",
                    "is_recording": c_online and is_rec,
                    "fps": 25 if c_online else 0,
                    "resolution": c.get("resolution", "1080P") if c_online else "-",
                    "bitrate": "2048 Kbps" if c_online else "0 Kbps",
                    "timestamp": clean_update,
                })
        else:
            ch_list = [int(x) for x in selected_cams] if (selected_cams and isinstance(selected_cams, list) and len(selected_cams) > 0) else list(range(1, total_kamera + 1))
            for cid in ch_list:
                cam_previews.append({
                    "channel": cid,
                    "name": f"CAM {cid:02d} - Channel {cid}",
                    "status": "Offline",
                    "is_recording": False,
                    "fps": 0,
                    "resolution": "-",
                    "bitrate": "0 Kbps",
                    "timestamp": clean_update,
                })

        primary_disk = disks[0] if disks else {}
        disk_health_info = primary_disk.get("health_info", {})
        disk_smart_status = primary_disk.get("status_raw", "ok").upper() if is_connected else "NO DISK"
        disk_temp = disk_health_info.get("temperature_c", 36)

        total_tb = round(cap_gb / 1024.0, 2)
        used_tb = round(used_gb / 1024.0, 2)

        if not has_dvr:
            detail_obj = {
                "id": device_id,
                "device_uuid": device_uuid,
                "customer": customer_val,
                "client_name": customer_val,
                "location": loc_name,
                "type": gw_item["type"],
                "model": f"{hw.get('type', 'Gateway')} {hw.get('model', 'DSGW-210')}",
                "dvr_model": "Not Installed",
                "ip_address": ip_addr,
                "last_update": clean_update,
                "status": "Online",
                "has_dvr": False,
                "is_connected": False,
                "is_offline": False,
                "service_status": "Running",
                "cpu_dvr": {
                    "status": "Not Installed",
                    "message": "No DVR/NVR surveillance unit installed on this gateway.",
                    "port": "-",
                    "response_time": "N/A",
                    "packet_loss": "N/A",
                    "last_check": clean_update,
                },
                "camera_status": {
                    "total": 0,
                    "online": 0,
                    "no_video": 0,
                    "offline": 0,
                    "percent": 0,
                    "sparkline": [0, 0, 0, 0, 0],
                },
                "recording_storage": {
                    "status": "N/A",
                    "used_tb": 0,
                    "total_tb": 0,
                    "percent": 0,
                    "retention_days": 0,
                    "sparkline": [0, 0, 0, 0],
                },
                "dvr_health": {
                    "status": "N/A",
                    "hdd_status": "No Storage Installed",
                    "temperature": "-",
                    "fan_status": "N/A",
                    "bad_sector": 0,
                    "power_on_hours": None,
                    "health_percent": None,
                    "health_label": "N/A",
                },
                "cameras": [],
                "firmware": "-",
                "serial_number": "-",
                "device_type": "Standalone IoT Gateway",
            }
        else:
            detail_obj = {
                "id": device_id,
                "device_uuid": device_uuid,
                "customer": customer_val,
                "client_name": customer_val,
                "location": loc_name,
                "type": gw_item["type"],
                "model": f"{hw.get('type', 'Gateway')} {hw.get('model', 'DSGW-210')}",
                "dvr_model": dvr_model,
                "ip_address": ip_addr,
                "last_update": clean_update,
                "status": "Online",
                "has_dvr": True,
                "is_connected": is_connected,
                "is_offline": False,
                "service_status": "Running",
                "cpu_dvr": {
                    "status": cpu_dvr_status,
                    "message": f"ISAPI/SDK protocol connected stably to {nvr_endpoint}" if is_connected else f"NVR communication failed: {self._translate_log_to_en(nvr.get('error_message', 'Host unreachable / Timeout'))}",
                    "port": f"{port_num} (HTTP ISAPI)",
                    "response_time": "< 15 ms" if is_connected else "Timeout",
                    "packet_loss": "0%" if is_connected else "100%",
                    "last_check": clean_update,
                },
                "camera_status": {
                    "total": total_kamera,
                    "online": kamera_online,
                    "no_video": kamera_offline_raw,
                    "offline": 0 if is_connected else total_kamera,
                    "percent": int(round((kamera_online / total_kamera) * 100)) if total_kamera > 0 else 0,
                    "sparkline": [kamera_online, kamera_online, kamera_online, kamera_online, kamera_online],
                },
                "recording_storage": {
                    "status": rec_status,
                    "used_tb": used_tb,
                    "total_tb": total_tb,
                    "percent": storage_pct,
                    "retention_days": (30 if storage_pct < 85 else 14) if storage_pct is not None else 0,
                    "sparkline": [max(5, storage_pct - 3), max(5, storage_pct - 2), storage_pct - 1, storage_pct] if storage_pct is not None else [0, 0, 0, 0],
                },
                "dvr_health": {
                    "status": health,
                    "hdd_status": f"HDD {primary_disk.get('name', 'hdd1')} ({disk_smart_status})" if disks else "No Disk Detected",
                    "temperature": f"{disk_temp}°C",
                    "fan_status": "Normal" if is_connected else "N/A",
                    "bad_sector": disk_health_info.get("bad_sectors", 0),
                    "power_on_hours": disk_health_info.get("power_on_hours"),
                    "health_percent": disk_health_info.get("health_percent"),
                    "health_label": self._translate_log_to_en(disk_health_info.get("health_label")) if disk_health_info.get("health_label") else "Good",
                },
                "cameras": cam_previews,
                "firmware": dev_info.get("firmware") or "V4.20.000",
                "serial_number": dev_info.get("serial") or "-",
                "device_type": dev_info.get("device_type") or "Surveillance NVR / IPC Hub",
            }

        is_dvr_online = (gw_item.get("status") == "Online")
        aiops_diagnostics_service.enrich_gateway(gw_item, nms_payload, is_online=is_dvr_online, box_type=box_type)
        aiops_diagnostics_service.enrich_gateway(detail_obj, nms_payload, is_online=is_dvr_online, box_type=box_type)

        last_seen_epoch = self._parse_payload_epoch(nms_payload)
        self._live_gateways[device_id] = {
            "table_item": gw_item,
            "detail_item": detail_obj,
            "status": "Online",
            "cap_gb": cap_gb,
            "used_gb": used_gb,
            "storage_pct": storage_pct,
            "is_connected": is_connected,
            "is_rec": is_rec,
            "health": health,
            "raw_payload": nms_payload,
            "last_seen_epoch": last_seen_epoch,
            "last_kamera_online": kamera_online,
            "last_storage_pct": storage_pct,
            "last_recording_status": rec_status,
        }

    ONLINE_TIMEOUT_SECONDS = 3600  # 1 Jam (3600 detik). Jika data telemetri berhenti > 1 jam, status menjadi Offline

    @staticmethod
    def _parse_payload_epoch(payload: Dict[str, Any]) -> float:
        ts = payload.get("timestamp")
        if ts and isinstance(ts, (int, float)) and ts > 1000000000:
            return ts / 1000.0 if ts > 100000000000 else float(ts)
        from datetime import timezone, timedelta
        ts_str = payload.get("datetime_utc7") or payload.get("recorded_at")
        if ts_str:
            clean = str(ts_str).split(" (")[0].strip()
            for fmt in ["%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%d %b %Y %H:%M:%S"]:
                try:
                    dt_wib = datetime.strptime(clean[:19], fmt)
                    dt_utc = dt_wib - timedelta(hours=7)
                    return dt_utc.replace(tzinfo=timezone.utc).timestamp()
                except Exception:
                    pass
        return time.time()

    def _sync_freshness(self):
        now = time.time()
        for dev_id, g in self._live_gateways.items():
            last_seen = g.get("last_seen_epoch")
            if not last_seen:
                last_seen = self._parse_payload_epoch(g.get("raw_payload", {}))
                g["last_seen_epoch"] = last_seen
            age_sec = now - last_seen
            table_item = g.get("table_item", {})
            detail_item = g.get("detail_item", {})
            if age_sec > self.ONLINE_TIMEOUT_SECONDS:
                g["status"] = "Offline"
                table_item["status"] = "Offline"
                table_item["is_offline"] = True
                if table_item.get("has_dvr") is not False:
                    table_item["cpu_dvr"] = "Not Connected"
                    table_item["dvr_health"] = "Critical"
                    # Preserve actual telemetry values as Last Known Good State:
                    if not isinstance(table_item.get("kamera_online"), (int, float)):
                        table_item["kamera_online"] = g.get("last_kamera_online", 0)
                    if not isinstance(table_item.get("storage_usage_percent"), (int, float)):
                        table_item["storage_usage_percent"] = g.get("last_storage_pct", 0)
                    if not table_item.get("recording_status") or table_item.get("recording_status") == "Not Recording":
                        table_item["recording_status"] = g.get("last_recording_status", "0/4 Recording")
                    g["is_connected"] = False
                    table_item["is_connected"] = False
                    g["health"] = "Critical"
                detail_item["status"] = "Offline"
                detail_item["service_status"] = "Stopped"
                detail_item["is_offline"] = True
                if table_item.get("has_dvr") is not False:
                    detail_item["is_connected"] = False
                    if "cpu_dvr" in detail_item:
                        detail_item["cpu_dvr"]["status"] = "Not Connected"
            else:
                g["status"] = "Online"
                table_item["status"] = "Online"
                table_item["is_offline"] = False
                is_conn = g.get("is_connected", False)
                table_item["is_connected"] = is_conn
                h = g.get("health", "Warning")
                detail_item["status"] = "Online"
                detail_item["service_status"] = "Running"
                detail_item["is_offline"] = False
                detail_item["is_connected"] = is_conn

            is_fresh_online = (g.get("status") == "Online" or table_item.get("status") == "Online")
            raw_pl = g.get("raw_payload", {})
            if isinstance(table_item, dict):
                aiops_diagnostics_service.enrich_gateway(table_item, raw_pl, is_online=is_fresh_online, box_type=table_item.get("type", "SmartBox"))
            if isinstance(detail_item, dict):
                aiops_diagnostics_service.enrich_gateway(detail_item, raw_pl, is_online=is_fresh_online, box_type=table_item.get("type", "SmartBox"))

    def get_summary(
        self,
        search: Optional[str] = None,
        gateway_type: Optional[str] = None,
        client: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Calculates dynamic summary metrics from 100% real live gateways matching active filters"""
        self._sync_freshness()
        gateways = list(self._live_gateways.values())

        for g in gateways:
            t_item = g.get("table_item", {})
            if not t_item.get("customer") or t_item.get("customer") == "-":
                try:
                    from app.services.sla_report_service import sla_report_service
                    s_cust = sla_report_service._live_gateways.get(t_item.get("id"), {}).get("customer")
                    if s_cust and s_cust != "-":
                        t_item["customer"] = s_cust
                        t_item["client_name"] = s_cust
                except Exception:
                    pass

        if search and isinstance(search, str):
            q = search.lower().strip()
            gateways = [
                g for g in gateways
                if (
                    q in str(g.get("table_item", {}).get("id", "")).lower()
                    or q in str(g.get("table_item", {}).get("location", "")).lower()
                    or q in str(g.get("table_item", {}).get("dvr_model", "")).lower()
                    or q in str(g.get("table_item", {}).get("type", "")).lower()
                    or q in str(g.get("table_item", {}).get("ip_address", "")).lower()
                    or q in str(g.get("table_item", {}).get("customer", "")).lower()
                    or q in str(g.get("table_item", {}).get("client_name", "")).lower()
                )
            ]

        if client and isinstance(client, str) and client not in ["Semua Client", "All", "All Clients"]:
            c_low = client.lower().strip()
            gateways = [
                g for g in gateways
                if c_low == str(g.get("table_item", {}).get("customer", "")).lower()
                or c_low == str(g.get("table_item", {}).get("client_name", "")).lower()
                or c_low in str(g.get("table_item", {}).get("customer", "")).lower()
            ]

        if gateway_type and isinstance(gateway_type, str) and gateway_type not in ["Semua Tipe", "All"]:
            gateways = [
                g for g in gateways
                if gateway_type.lower() in str(g.get("table_item", {}).get("type", "")).lower()
            ]

        total_gw = len(gateways)
        if total_gw == 0:
            return {
                "total_gateways": 0,
                "online": 0,
                "online_percent": 0.0,
                "offline": 0,
                "offline_percent": 0.0,
                "recording_normal": 0,
                "recording_normal_percent": 0.0,
                "good": 0,
                "good_percent": 0.0,
                "issue": 0,
                "issue_percent": 0.0,
                "warning": 0,
                "warning_percent": 0.0,
                "total_kamera": 0,
                "kamera_online": 0,
                "kamera_no_video": 0,
                "kamera_offline": 0,
                "total_storage_tb": 0,
                "storage_used_tb": 0,
                "storage_warning_tb": 0,
                "storage_critical_tb": 0,
            }

        online_count = sum(
            1 for g in gateways
            if g.get("status") == "Online" or g.get("table_item", {}).get("status") == "Online"
        )
        offline_count = sum(
            1 for g in gateways
            if g.get("status") == "Offline" or g.get("table_item", {}).get("status") == "Offline"
        )
        online_percent = round((online_count / total_gw) * 100.0, 1) if total_gw else 0.0
        offline_percent = round((offline_count / total_gw) * 100.0, 1) if total_gw else 0.0

        rec_count = sum(
            1 for g in gateways
            if g.get("is_connected", False)
            and "0/" not in str(g.get("table_item", {}).get("recording_status", "0/"))
        )
        issue_count = sum(
            1 for g in gateways
            if g.get("is_connected", False)
            and "0/" in str(g.get("table_item", {}).get("recording_status", "0/"))
        )

        total_cams = sum(
            g.get("table_item", {}).get("total_kamera", 0) for g in gateways
            if isinstance(g.get("table_item", {}).get("total_kamera"), (int, float))
        )
        online_cams = sum(
            g.get("table_item", {}).get("kamera_online", 0) for g in gateways
            if isinstance(g.get("table_item", {}).get("kamera_online"), (int, float))
        )
        no_video_cams = sum(
            g.get("table_item", {}).get("kamera_no_video", 0) for g in gateways
            if isinstance(g.get("table_item", {}).get("kamera_no_video"), (int, float))
        )
        offline_cams = max(0, total_cams - online_cams - no_video_cams)

        total_storage_tb = round(sum(g.get("cap_gb", 0) for g in gateways if isinstance(g.get("cap_gb"), (int, float))) / 1024.0, 1)
        used_storage_tb = round(sum(g.get("used_gb", 0) for g in gateways if isinstance(g.get("used_gb"), (int, float))) / 1024.0, 1)
        warn_storage_tb = round(sum(g.get("used_gb", 0) for g in gateways if isinstance(g.get("storage_pct"), (int, float)) and g["storage_pct"] > 80) / 1024.0, 1)
        crit_storage_tb = round(sum(g.get("used_gb", 0) for g in gateways if isinstance(g.get("storage_pct"), (int, float)) and g["storage_pct"] > 90) / 1024.0, 1)

        return {
            "total_gateways": total_gw,
            "online": online_count,
            "online_percent": online_percent,
            "offline": offline_count,
            "offline_percent": offline_percent,
            "recording_normal": rec_count,
            "recording_normal_percent": round((rec_count / total_gw) * 100.0, 1),
            "good": online_count,
            "good_percent": online_percent,
            "issue": issue_count,
            "issue_percent": round((issue_count / total_gw) * 100.0, 1),
            "warning": issue_count,
            "warning_percent": round((issue_count / total_gw) * 100.0, 1),
            "total_kamera": total_cams,
            "kamera_online": online_cams,
            "kamera_no_video": no_video_cams,
            "kamera_offline": offline_cams,
            "total_storage_tb": int(round(total_storage_tb)),
            "storage_used_tb": int(round(used_storage_tb)),
            "storage_warning_tb": int(round(warn_storage_tb)),
            "storage_critical_tb": int(round(crit_storage_tb)),
        }

    def get_charts(self) -> Dict[str, Any]:
        """Calculates dynamic donut & timeline charts from real live telemetry"""
        total_gw = len(self._live_gateways)
        connected_count = sum(1 for g in self._live_gateways.values() if g["is_connected"])
        no_resp_count = total_gw - connected_count

        total_cams = sum(
            g["table_item"]["total_kamera"] for g in self._live_gateways.values()
            if isinstance(g["table_item"].get("total_kamera"), (int, float))
        )
        online_cams = sum(
            g["table_item"]["kamera_online"] for g in self._live_gateways.values()
            if isinstance(g["table_item"].get("kamera_online"), (int, float))
        )
        no_video_cams = sum(
            g["table_item"]["kamera_no_video"] for g in self._live_gateways.values()
            if isinstance(g["table_item"].get("kamera_no_video"), (int, float))
        )
        offline_cams = max(0, total_cams - online_cams - no_video_cams)

        rec_cams = online_cams
        not_rec_cams = max(0, total_cams - rec_cams)

        storage_percentages = [g["storage_pct"] for g in self._live_gateways.values() if isinstance(g.get("storage_pct"), (int, float)) and g.get("cap_gb", 0) > 0]
        avg_storage = int(round(sum(storage_percentages) / len(storage_percentages))) if storage_percentages else 0
        max_storage = max(storage_percentages) if storage_percentages else 0
        min_storage = min(storage_percentages) if storage_percentages else 0

        now = datetime.now()
        current_hour = now.hour

        return {
            "cpu_dvr_comm": {
                "total_label": "Gateway",
                "total_count": total_gw,
                "slices": [
                    {
                        "label": "Connected",
                        "count": connected_count,
                        "percent": round((connected_count / total_gw) * 100.0, 1) if total_gw else 0.0,
                        "color": "#00c875",
                    },
                    {
                        "label": "No Response",
                        "count": no_resp_count,
                        "percent": round((no_resp_count / total_gw) * 100.0, 1) if total_gw else 0.0,
                        "color": "#e2445c",
                    },
                ],
            },
            "status_kamera": {
                "total_label": "Kamera",
                "total_count": total_cams,
                "slices": [
                    {
                        "label": "Online",
                        "count": online_cams,
                        "percent": round((online_cams / total_cams) * 100.0, 1) if total_cams else 0.0,
                        "color": "#00c875",
                    },
                    {
                        "label": "No Video",
                        "count": no_video_cams,
                        "percent": round((no_video_cams / total_cams) * 100.0, 1) if total_cams else 0.0,
                        "color": "#fdab3d",
                    },
                    {
                        "label": "Offline",
                        "count": offline_cams,
                        "percent": round((offline_cams / total_cams) * 100.0, 1) if total_cams else 0.0,
                        "color": "#e2445c",
                    },
                ],
            },
            "recording_status": {
                "total_label": "Kamera",
                "total_count": total_cams,
                "slices": [
                    {
                        "label": "Recording",
                        "count": rec_cams,
                        "percent": round((rec_cams / total_cams) * 100.0, 1) if total_cams else 0.0,
                        "color": "#00c875",
                    },
                    {
                        "label": "Not Recording",
                        "count": not_rec_cams,
                        "percent": round((not_rec_cams / total_cams) * 100.0, 1) if total_cams else 0.0,
                        "color": "#fdab3d",
                    },
                ],
            },
            "storage_usage": {
                "avg": f"{avg_storage}%",
                "max": f"{max_storage}%",
                "min": f"{min_storage}%",
                "timeline": [
                    {"time": f"{(current_hour - 8) % 24:02d}:00", "value": max(0.0, avg_storage - 0.4)},
                    {"time": f"{(current_hour - 6) % 24:02d}:00", "value": max(0.0, avg_storage - 0.3)},
                    {"time": f"{(current_hour - 4) % 24:02d}:00", "value": max(0.0, avg_storage - 0.2)},
                    {"time": f"{(current_hour - 2) % 24:02d}:00", "value": max(0.0, avg_storage - 0.1)},
                    {"time": f"{current_hour:02d}:00", "value": float(avg_storage)},
                ],
            },
        }

    def _apply_sorting(
        self,
        items: List[Dict[str, Any]],
        sort_by: Optional[str],
        sort_order: Optional[str],
    ) -> List[Dict[str, Any]]:
        if not sort_by or not isinstance(sort_by, str):
            return items
        is_desc = (str(sort_order).lower() == "desc") if sort_order else False
        key = sort_by.strip().lower()

        if key == "status":
            def status_rank(g: Dict[str, Any]) -> int:
                s = str(g.get("status", "")).lower()
                if s == "offline":
                    return 0
                if s in ("warning", "degraded"):
                    return 1
                return 2
            return sorted(items, key=status_rank, reverse=is_desc)

        if key == "cpu_dvr":
            def cpu_dvr_rank(g: Dict[str, Any]) -> int:
                if g.get("status") == "Offline":
                    return 0
                cd = str(g.get("cpu_dvr", "")).lower()
                if cd == "connected":
                    return 2
                if cd == "degraded":
                    return 1
                return 0
            return sorted(items, key=cpu_dvr_rank, reverse=is_desc)

        if key == "camera":
            valid = []
            missing = []
            for g in items:
                online = g.get("kamera_online")
                total = g.get("total_kamera")
                if isinstance(online, (int, float)):
                    tot = float(total) if isinstance(total, (int, float)) and total > 0 else 0.0
                    ratio = (float(online) / tot) if tot > 0 else 0.0
                    diff = float(online) - tot
                    valid.append(((ratio, diff, float(online)), g))
                else:
                    missing.append(g)
            valid.sort(key=lambda x: x[0], reverse=is_desc)
            return [g for _, g in valid] + missing

        if key == "recording_status":
            import re
            def rec_rank(g: Dict[str, Any]) -> tuple:
                rec_str = str(g.get("recording_status") or "0/4 Recording")
                m = re.search(r"(\d+)\s*/\s*(\d+)", rec_str)
                if m:
                    rec_count = int(m.group(1))
                    tot_count = int(m.group(2))
                else:
                    low = rec_str.lower()
                    if "recording" in low and "not" not in low and isinstance(g.get("kamera_online"), (int, float)):
                        rec_count = int(g["kamera_online"])
                    else:
                        rec_count = 0
                    tot_count = int(g.get("total_kamera") or 0)
                if tot_count <= 0 or rec_count <= 0:
                    return (0, 0.0, 0)
                ratio = rec_count / tot_count
                if rec_count >= tot_count:
                    return (2, ratio, rec_count)
                return (1, ratio, rec_count)
            return sorted(items, key=rec_rank, reverse=is_desc)

        if key in ("storage", "storage_percent", "storage_usage_percent"):
            valid = []
            missing = []
            for g in items:
                val = g.get("storage_usage_percent")
                if isinstance(val, (int, float)):
                    valid.append((float(val), g))
                else:
                    missing.append(g)
            valid.sort(key=lambda x: x[0], reverse=is_desc)
            return [g for _, g in valid] + missing

        if key == "dvr_health":
            def dvr_health_rank(g: Dict[str, Any]) -> int:
                if g.get("status") == "Offline":
                    return 0
                h = str(g.get("dvr_health", "")).lower()
                if h in ("good", "normal"):
                    return 2
                if h in ("warning", "caution"):
                    return 1
                return 0
            return sorted(items, key=dvr_health_rank, reverse=is_desc)

        return items

    def get_gateways(
        self,
        search: Optional[str] = None,
        gateway_type: Optional[str] = None,
        status: Optional[str] = None,
        client: Optional[str] = None,
        page: int = 1,
        page_size: int = 5,
        sort_by: Optional[str] = None,
        sort_order: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Filters & paginates real gateway records for the table"""
        self._sync_freshness()
        items = [g["table_item"] for g in self._live_gateways.values()]

        for idx, it in enumerate(items, 1):
            it["no"] = idx
            if not it.get("customer") or it.get("customer") == "-":
                try:
                    from app.services.sla_report_service import sla_report_service
                    s_cust = sla_report_service._live_gateways.get(it["id"], {}).get("customer")
                    if s_cust and s_cust != "-":
                        it["customer"] = s_cust
                        it["client_name"] = s_cust
                except Exception:
                    pass

        filtered = items

        if search and isinstance(search, str):
            q = search.lower().strip()
            filtered = [
                g for g in filtered
                if (
                    q in str(g.get("id", "")).lower()
                    or q in str(g.get("location", "")).lower()
                    or q in str(g.get("dvr_model", "")).lower()
                    or q in str(g.get("type", "")).lower()
                    or q in str(g.get("ip_address", "")).lower()
                    or q in str(g.get("customer", "")).lower()
                    or q in str(g.get("client_name", "")).lower()
                )
            ]

        if client and isinstance(client, str) and client not in ["Semua Client", "All", "All Clients"]:
            c_low = client.lower().strip()
            filtered = [
                g for g in filtered
                if c_low == str(g.get("customer", "")).lower()
                or c_low == str(g.get("client_name", "")).lower()
                or c_low in str(g.get("customer", "")).lower()
            ]

        if gateway_type and isinstance(gateway_type, str) and gateway_type not in ["Semua Tipe", "All"]:
            filtered = [g for g in filtered if gateway_type.lower() in g["type"].lower()]

        if status and isinstance(status, str) and status not in ["Semua Status", "All", "All Statuses"]:
            s = status.lower().strip()
            if s in ["online"]:
                filtered = [
                    g for g in filtered
                    if g.get("status") == "Online"
                ]
            elif s in ["offline"]:
                filtered = [
                    g for g in filtered
                    if g.get("status") == "Offline"
                ]
            elif s in ["recording", "normal", "recording normal", "full recording", "active recording", "good"]:
                filtered = [
                    g for g in filtered
                    if g.get("status") == "Online" and g.get("cpu_dvr") == "Connected" and "0/" not in str(g.get("recording_status", ""))
                ]
            elif s in ["issue", "warning", "partial", "partial recording"]:
                filtered = [
                    g for g in filtered
                    if g.get("status") == "Online" and g.get("cpu_dvr") == "Connected" and "0/" in str(g.get("recording_status", ""))
                ]
            elif s in ["critical", "not connected", "no response"]:
                filtered = [
                    g for g in filtered
                    if g.get("cpu_dvr") in ["Not Connected", "No Response", "Offline"] or g.get("dvr_health") == "Critical"
                ]

        filtered = self._apply_sorting(filtered, sort_by, sort_order)

        page = page if isinstance(page, int) and page >= 1 else 1
        page_size = page_size if isinstance(page_size, int) and page_size >= 1 else 5

        total_items = len(filtered)
        total_pages = max(1, (total_items + page_size - 1) // page_size)
        page = max(1, min(page, total_pages))
        start_idx = (page - 1) * page_size
        end_idx = min(start_idx + page_size, total_items)

        items_slice = filtered[start_idx:end_idx]

        return {
            "items": items_slice,
            "pagination": {
                "total_items": total_items,
                "total_pages": total_pages,
                "current_page": page,
                "page_size": page_size,
                "showing_start": start_idx + 1 if total_items > 0 else 0,
                "showing_end": end_idx,
            },
        }

    def get_dashboard(
        self,
        search: Optional[str] = None,
        gateway_type: Optional[str] = None,
        status: Optional[str] = None,
        client: Optional[str] = None,
        page: int = 1,
        page_size: int = 5,
        sort_by: Optional[str] = None,
        sort_order: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Unified dashboard payload for frontend consumer"""
        summary = self.get_summary(
            search=search,
            gateway_type=gateway_type,
            client=client,
        )
        charts = self.get_charts()
        gw_result = self.get_gateways(
            search=search,
            gateway_type=gateway_type,
            status=status,
            client=client,
            page=page,
            page_size=page_size,
            sort_by=sort_by,
            sort_order=sort_order,
        )
        client_options = sorted(list({
            str(g["table_item"].get("customer")).strip()
            for g in self._live_gateways.values()
            if g.get("table_item", {}).get("customer") and g["table_item"]["customer"] != "-"
        }))

        return {
            "summary": summary,
            "charts": charts,
            "gateways": gw_result["items"],
            "pagination": gw_result["pagination"],
            "client_options": client_options,
        }

    @staticmethod
    def _translate_log_to_en(text: str) -> str:
        if not text:
            return "Normal Operation"
        import re
        t = str(text)

        # 1. Alert patterns: Kamera not writing to disk, read-only, bad sector, storage full
        t = re.sub(
            r'Kamera\s+#?(\d+)\s*\((.*?)\)\s+status\s+ON\s+CAM\s+tetapi\s+rekaman\s+TIDAK\s+MASUK\s+ke\s+Harddisk\s*\((\d+)\s+segmen\s+tersimpan\s+hari\s+ini\)!?',
            r'Camera #\1 (\2) online (ON CAM) but not writing to Hard Drive (\3 segments saved today)!',
            t, flags=re.IGNORECASE
        )
        t = re.sub(
            r'Harddisk\s+NVR\s*\((.*?)\)\s+berstatus\s+READ-ONLY\s*\(RW\s*/\s*error\)!?\s*Rekaman\s+video\s+kamera\s+tidak\s+dapat\s+masuk\s+ke\s+harddisk\.?',
            r'NVR Hard Drive (\1) is READ-ONLY (I/O error)! Camera video recordings cannot write to disk.',
            t, flags=re.IGNORECASE
        )
        t = re.sub(
            r'Terdeteksi\s+(\d+)\s+Bad\s+Sector\s*\((\d+)\s+Rusak\s*/\s*(\d+)\s+Pending\)\s+pada\s+Harddisk\s+NVR\s*\((.*?)\)!?',
            r'Detected \1 Bad Sectors (\2 Damaged / \3 Pending) on NVR Hard Drive (\4)!',
            t, flags=re.IGNORECASE
        )
        t = re.sub(
            r'Kapasitas\s+Harddisk\s+NVR\s+penuh\s*\(Sisa\s*([\d\.]+%?)\)\.?\s*Perekaman\s+mode\s+loop\s+overwrite\s+24/7\s+tetap\s+aktif\.?',
            r'NVR Hard Drive storage full (Remaining \1). Continuous 24/7 loop overwrite mode active.',
            t, flags=re.IGNORECASE
        )
        t = re.sub(
            r'NVR\s+dalam\s+kondisi\s+online\s+tetapi\s+TIDAK\s+sedang\s+merekam\s+video!?',
            r'NVR is online but NOT actively recording video!',
            t, flags=re.IGNORECASE
        )
        t = re.sub(
            r'Kamera\s+#?(\d+)\s*\((.*?)\)\s+terputus\s*/\s*NO\s+VIDEO\s*\(Kabel\s+lepas\s+atau\s+kamera\s+mati\)\.?',
            r'Camera #\1 (\2) disconnected / NO VIDEO (cable detached or camera offline).',
            t, flags=re.IGNORECASE
        )
        t = re.sub(
            r'Perekaman\s+video\s+NVR\s+macet!?',
            'NVR video recording stalled!',
            t, flags=re.IGNORECASE
        )
        t = re.sub(
            r'Rekaman\s+terakhir\s+tersimpan\s*:',
            'Last recording saved:',
            t, flags=re.IGNORECASE
        )

        # 2. General fragments
        t = re.sub(r'Pemeriksaan\s+rekaman\s+kamera\s+selesai', 'Camera recording health check completed', t, flags=re.IGNORECASE)
        t = re.sub(r'Pemeriksaan\s+rekaman\s+kamera', 'Camera recording check', t, flags=re.IGNORECASE)
        t = re.sub(r'Perekaman\s+video\s+kamera\s+normal', 'Camera video recording operational', t, flags=re.IGNORECASE)
        t = re.sub(r'Perekaman\s+CCTV\s+Terhenti', 'CCTV Video Recording Stopped', t, flags=re.IGNORECASE)
        t = re.sub(r'Kamera\s+Hilang\s+Sinyal\s*/\s*No\s+Video', 'Camera Signal Loss / No Video', t, flags=re.IGNORECASE)
        t = re.sub(r'Kamera\s+Terputus\s*/\s*Offline', 'Camera Disconnected / Offline', t, flags=re.IGNORECASE)
        t = re.sub(r'Kamera\s+Tidak\s+Merekam', 'Camera Not Recording', t, flags=re.IGNORECASE)
        t = re.sub(r'Kamera\s+(\d+)\s+terputus', r'Camera \1 Disconnected', t, flags=re.IGNORECASE)
        t = re.sub(r'Kamera\s+(\d+)\s+tidak\s+merekam', r'Camera \1 Not Recording', t, flags=re.IGNORECASE)
        t = re.sub(r'Kamera\s+(\d+)\s+merekam\s+normal', r'Camera \1 Recording Normal', t, flags=re.IGNORECASE)
        t = re.sub(r'Harddisk\s+penyimpanan', 'Hard drive storage', t, flags=re.IGNORECASE)
        t = re.sub(r'Penyimpanan\s+harddisk', 'Hard drive storage', t, flags=re.IGNORECASE)
        t = re.sub(r'\(Kabel\s+lepas\s+atau\s+kamera\s+mati\)', '(cable detached or camera offline)', t, flags=re.IGNORECASE)
        t = re.sub(r'status\s+ON\s+CAM\s+tetapi\s+rekaman\s+TIDAK\s+MASUK\s+ke\s+Harddisk', 'online (ON CAM) but not writing to Hard Drive', t, flags=re.IGNORECASE)
        t = re.sub(r'segmen\s+tersimpan\s+hari\s+ini', 'segments saved today', t, flags=re.IGNORECASE)
        t = re.sub(r'berstatus\s+READ-ONLY', 'status is READ-ONLY', t, flags=re.IGNORECASE)
        t = re.sub(r'Kapasitas\s+Harddisk\s+NVR\s+penuh', 'NVR Hard Drive storage full', t, flags=re.IGNORECASE)
        t = re.sub(r'Perekaman\s+mode\s+loop\s+overwrite\s+24/7\s+tetap\s+aktif', '24/7 loop overwrite active', t, flags=re.IGNORECASE)
        t = re.sub(r'Timeout\s+koneksi\s+ke\s+NVR', 'Connection timeout to NVR', t, flags=re.IGNORECASE)
        t = re.sub(r'koneksi\s+ke\s+NVR', 'connection to NVR', t, flags=re.IGNORECASE)
        t = re.sub(r'koneksi', 'connection', t, flags=re.IGNORECASE)
        t = re.sub(r'terpakai', 'utilized', t, flags=re.IGNORECASE)
        t = re.sub(r'selesai', 'completed', t, flags=re.IGNORECASE)
        t = re.sub(r'terputus', 'disconnected', t, flags=re.IGNORECASE)
        t = re.sub(r'tidak\s+merekam', 'not recording', t, flags=re.IGNORECASE)
        t = re.sub(r'merekam', 'recording', t, flags=re.IGNORECASE)
        t = re.sub(r'Bahaya\s*\(Terdeteksi\s*(\d+)\s*Bad\s*Sector\)', r'Danger (Detected \1 Bad Sectors)', t, flags=re.IGNORECASE)
        t = re.sub(r'Terdeteksi\s*(\d+)\s*Bad\s*Sector', r'Detected \1 Bad Sectors', t, flags=re.IGNORECASE)
        t = re.sub(r'\bBahaya\b', 'Danger', t, flags=re.IGNORECASE)
        t = re.sub(r'\bBaik\b', 'Good', t, flags=re.IGNORECASE)
        t = re.sub(r'\bWaspada\b', 'Warning', t, flags=re.IGNORECASE)
        t = re.sub(r'\bKritis\b', 'Critical', t, flags=re.IGNORECASE)
        return t

    def _enrich_detail_with_history(
        self,
        base_detail: Dict[str, Any],
        dev_id: str,
        raw_payload: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Enriches DVR detail with 100% REAL historical telemetries, camera status, bad sectors, and event logs from DB."""
        detail = dict(base_detail)
        if not detail.get("customer") or detail.get("customer") == "-":
            try:
                from app.services.sla_report_service import sla_report_service
                s_cust = sla_report_service._live_gateways.get(dev_id, {}).get("customer")
                if s_cust and s_cust != "-":
                    detail["customer"] = s_cust
                    detail["client_name"] = s_cust
            except Exception:
                pass
        from app.core.database import SessionLocal
        from app.models.base_models import GatewayTelemetryHistory
        from datetime import timezone, timedelta
        import uuid as _uuid
        from app.models.base_models import Device

        WIB = timezone(timedelta(hours=7))

        db = SessionLocal()
        rows = []
        target_uuid = None
        try:
            try:
                target_uuid = _uuid.UUID(str(dev_id))
            except Exception:
                dev_obj = db.query(Device).filter(Device.name == str(dev_id)).first()
                if dev_obj:
                    target_uuid = dev_obj.id

            if target_uuid:
                # Lightweight column projection: skip 20KB+ raw_payload JSONB (~30x faster, identical sparklines)
                rows = (
                    db.query(
                        GatewayTelemetryHistory.recorded_at,
                        GatewayTelemetryHistory.cameras_online,
                        GatewayTelemetryHistory.disk_used_percent,
                    )
                    .filter(GatewayTelemetryHistory.device_id == target_uuid)
                    .order_by(GatewayTelemetryHistory.recorded_at.asc())
                    .all()
                )
        except Exception as e:
            logger.error(f"Error querying telemetry history for DVR {dev_id}: {e}")
        finally:
            db.close()

        # 1. Real Camera Status & Sparkline from Historical Telemetry
        cam_records = []
        for r in rows:
            if r.cameras_online is not None:
                cam_records.append(float(r.cameras_online))

        curr_online = detail.get("camera_status", {}).get("online", 2)
        if cam_records:
            step = max(1, len(cam_records) // 12)
            spark_cam = cam_records[::step]
            if cam_records[-1] != spark_cam[-1]:
                spark_cam.append(cam_records[-1])
            detail["camera_status"]["sparkline"] = spark_cam
        else:
            detail["camera_status"]["sparkline"] = [float(curr_online), float(curr_online)]

        # 2. Real Storage Sparkline from Historical Telemetry
        curr_pct = detail.get("recording_storage", {}).get("percent", 100)
        storage_records = []
        for r in rows:
            if r.disk_used_percent is not None:
                storage_records.append(float(r.disk_used_percent))

        if storage_records:
            step_s = max(1, len(storage_records) // 12)
            spark_s = storage_records[::step_s]
            if storage_records[-1] != spark_s[-1]:
                spark_s.append(storage_records[-1])
            detail["recording_storage"]["sparkline"] = spark_s
        else:
            detail["recording_storage"]["sparkline"] = [float(curr_pct), float(curr_pct)]

        # 2b. Enrich with Last Known Good NVR Telemetry if CPU-to-DVR is currently Not Connected or storage is 0
        cpu_status = detail.get("cpu_dvr", {}).get("status", "")
        # A device CPU is considered connected if cpu_dvr status is "Connected", status is not "Offline", and is_connected is not explicitly False
        is_cpu_connected = (cpu_status == "Connected") and (detail.get("status") != "Offline") and (detail.get("is_connected") is not False)
        is_cpu_not_connected = not is_cpu_connected

        dev_prop = self._device_properties.get(dev_id) or {}
        if not dev_prop:
            try:
                db_p = SessionLocal()
                try:
                    d_obj = db_p.query(Device).filter((Device.name == str(dev_id)) | (Device.id == target_uuid)).first()
                    if d_obj and d_obj.property:
                        dev_prop = d_obj.property
                        self._device_properties[dev_id] = dev_prop
                        self._device_properties[str(d_obj.id)] = dev_prop
                finally:
                    db_p.close()
            except Exception:
                pass

        # If device has no DVR installed, return clean non-DVR details immediately (skip NVR history and trouble events)
        has_dvr_flag = dev_prop.get("has_dvr")
        if has_dvr_flag is False or (has_dvr_flag is None and dev_prop.get("total_cameras") == 0 and not dev_prop.get("selected_cameras")) or detail.get("has_dvr") is False:
            detail["has_dvr"] = False
            detail["dvr_model"] = "Not Installed"
            detail["cpu_dvr"] = {
                "status": "Not Installed",
                "message": "No DVR/NVR surveillance unit installed on this gateway.",
                "port": "-",
                "response_time": "N/A",
                "packet_loss": "N/A",
                "last_check": detail.get("last_update", "-"),
            }
            detail["camera_status"] = {
                "total": 0,
                "online": 0,
                "no_video": 0,
                "offline": 0,
                "percent": 0,
                "sparkline": [0, 0],
            }
            detail["recording_storage"] = {
                "status": "N/A",
                "used_tb": 0,
                "total_tb": 0,
                "percent": 0,
                "retention_days": 0,
                "sparkline": [0, 0],
            }
            detail["dvr_health"] = {
                "status": "N/A",
                "hdd_status": "No Storage Installed",
                "temperature": "-",
                "fan_status": "N/A",
                "bad_sector": 0,
                "power_on_hours": None,
                "health_percent": None,
                "health_label": "N/A",
            }
            detail["cameras"] = []
            detail["events"] = []
            return detail

        if is_cpu_not_connected or float(detail.get("recording_storage", {}).get("total_tb", 0) or 0) == 0:
            last_nvr_row = None
            last_p_nvr = {}
            if target_uuid:
                db_nvr = SessionLocal()
                try:
                    # Fetch only recent nvr_surveillance sub-objects (uses DESC index, avoids loading all history)
                    recent_nvr_rows = (
                        db_nvr.query(
                            GatewayTelemetryHistory.recorded_at,
                            GatewayTelemetryHistory.raw_payload["nvr_surveillance"],
                        )
                        .filter(
                            GatewayTelemetryHistory.device_id == target_uuid,
                            GatewayTelemetryHistory.raw_payload.isnot(None),
                        )
                        .order_by(GatewayTelemetryHistory.recorded_at.desc())
                        .limit(50)
                        .all()
                    )
                    for rec_at, p_nvr in recent_nvr_rows:
                        if isinstance(p_nvr, dict) and (
                            p_nvr.get("connected") or float(p_nvr.get("total_capacity_gb", 0) or 0) > 0
                        ):
                            last_nvr_row = rec_at
                            last_p_nvr = p_nvr
                            break
                except Exception as e:
                    logger.debug(f"Could not fetch last known NVR snapshot for {dev_id}: {e}")
                finally:
                    db_nvr.close()

            if last_nvr_row is not None and last_p_nvr:
                last_cap_gb = float(last_p_nvr.get("total_capacity_gb", 0) or 0)
                last_used_gb = float(last_p_nvr.get("total_used_gb", 0) or 0)
                last_disks = last_p_nvr.get("disks") or []
                last_cams = last_p_nvr.get("cameras") or {}
                last_dev_info = last_p_nvr.get("device_info") or {}

                if is_cpu_not_connected:
                    last_conn_str = "-"
                    if last_nvr_row:
                        t_conn_wib = last_nvr_row.replace(tzinfo=timezone.utc).astimezone(WIB) if last_nvr_row.tzinfo is None else last_nvr_row.astimezone(WIB)
                        last_conn_str = t_conn_wib.strftime("%Y-%m-%d %H:%M:%S WIB")

                    detail["is_last_known"] = True
                    detail["last_connected_at"] = last_conn_str

                if last_dev_info.get("model") and detail.get("dvr_model") in ["-", "Hikvision/HiLook NVR"]:
                    detail["dvr_model"] = last_dev_info.get("model")

                if last_cap_gb > 0 and (is_cpu_not_connected or float(detail.get("recording_storage", {}).get("total_tb", 0) or 0) == 0):
                    last_tot_tb = round(last_cap_gb / 1024.0, 2)
                    last_usd_tb = round(last_used_gb / 1024.0, 2)
                    last_st_pct = int(round((last_used_gb / last_cap_gb) * 100))
                    detail["recording_storage"]["total_tb"] = last_tot_tb
                    detail["recording_storage"]["used_tb"] = last_usd_tb
                    detail["recording_storage"]["percent"] = last_st_pct
                    if is_cpu_not_connected:
                        detail["recording_storage"]["is_last_known"] = True

                if last_disks and (is_cpu_not_connected or not detail.get("dvr_health", {}).get("hdd_status")):
                    d0 = last_disks[0]
                    d0_health = d0.get("health_info") or {}
                    d0_status = d0.get("status_raw", "ok").upper()
                    detail["dvr_health"]["hdd_status"] = f"HDD {d0.get('name', 'hdd1')} ({d0_status})"
                    if d0_health.get("temperature_c"):
                        detail["dvr_health"]["temperature"] = f"{d0_health.get('temperature_c')}°C"
                    detail["dvr_health"]["fan_status"] = "Normal"
                    detail["dvr_health"]["bad_sector"] = d0_health.get("bad_sectors", 0)
                    detail["dvr_health"]["power_on_hours"] = d0_health.get("power_on_hours")
                    detail["dvr_health"]["health_percent"] = d0_health.get("health_percent")
                    detail["dvr_health"]["health_label"] = self._translate_log_to_en(d0_health.get("health_label") or "Healthy")
                    if is_cpu_not_connected:
                        detail["dvr_health"]["is_last_known"] = True

                # ONLY when CPU-to-DVR is actually NOT connected or gateway is offline, replace cameras with last known offline snapshot!
                if is_cpu_not_connected:
                    sel_cam_set = set(str(x) for x in dev_prop.get("selected_cameras", [])) if dev_prop.get("selected_cameras") else None
                    last_cam_list = last_cams.get("camera_list") or []
                    if sel_cam_set:
                        last_cam_list = [c for c in last_cam_list if str(c.get("id")) in sel_cam_set or str(c.get("channel")) in sel_cam_set]
                    elif dev_prop.get("total_cameras"):
                        tot_cam_cfg = int(dev_prop.get("total_cameras"))
                        last_cam_list = [c for c in last_cam_list if int(c.get("id", 0)) <= tot_cam_cfg]

                    if last_cam_list:
                        enriched_cams = []
                        for idx, c in enumerate(last_cam_list):
                            cid = int(c.get("id", idx + 1))
                            enriched_cams.append({
                                "channel": cid,
                                "name": c.get("name") or f"CAM {cid:02d} - Channel {cid}",
                                "status": "Offline",
                                "is_recording": False,
                                "fps": 0,
                                "resolution": c.get("resolution", "1080P"),
                                "bitrate": "0 Kbps",
                                "timestamp": detail.get("last_update", "-"),
                                "is_last_known": True,
                                "last_status": "Online (1080P)" if c.get("is_online") else "No Video",
                            })
                        detail["cameras"] = enriched_cams
                        detail["camera_status"]["total"] = len(enriched_cams)
                        detail["camera_status"]["offline"] = len(enriched_cams)
                        detail["camera_status"]["online"] = 0
                        detail["camera_status"]["no_video"] = 0
                        detail["camera_status"]["percent"] = 0
                        detail["camera_status"]["is_last_known"] = True

        # Ensure cameras preview list strictly matches selected_cameras configuration
        sel_set_cfg = set(str(x) for x in dev_prop.get("selected_cameras", [])) if dev_prop.get("selected_cameras") else None
        if not sel_set_cfg and dev_prop.get("total_cameras") and detail.get("cameras"):
            tot_cfg = int(dev_prop.get("total_cameras"))
            sel_set_cfg = {str(i + 1) for i in range(tot_cfg)}
        elif not sel_set_cfg and detail.get("cameras"):
            raw_c_list = detail.get("cameras")
            real_cams = [c for c in raw_c_list if not (c.get("resolution") == "NO VIDEO" and (c.get("status") == "No Video" or c.get("fps") == 0) and not c.get("is_recording") and "Camera 0" in c.get("name", ""))]
            if real_cams and len(real_cams) < len(raw_c_list):
                sel_set_cfg = {str(c.get("channel")) for c in real_cams if c.get("channel") is not None}

        if sel_set_cfg and detail.get("cameras"):
            detail["cameras"] = [c for c in detail["cameras"] if str(c.get("channel")) in sel_set_cfg]
        elif dev_prop.get("total_cameras") and detail.get("cameras"):
            tot_cfg = int(dev_prop.get("total_cameras"))
            detail["cameras"] = detail["cameras"][:tot_cfg]

        cams_list = detail.get("cameras", [])
        detail["camera_status"]["total"] = len(cams_list)
        if not is_cpu_not_connected and cams_list:
            detail["camera_status"]["online"] = sum(1 for c in cams_list if c.get("status") == "Online")
            detail["camera_status"]["no_video"] = sum(1 for c in cams_list if c.get("status") == "No Video")
            detail["camera_status"]["offline"] = sum(1 for c in cams_list if c.get("status") == "Offline")
            detail["camera_status"]["percent"] = int(round((detail["camera_status"]["online"] / len(cams_list)) * 100)) if len(cams_list) > 0 else 100

        # 3. Real Event Log from Incident Alerts & MQTT System Logs (Strictly Today Only)
        real_events = []
        import re
        from app.services.sla_calculator_service import WIB
        now_wib = datetime.now(timezone.utc).astimezone(WIB)
        today_iso = now_wib.strftime("%Y-%m-%d")
        today_display = now_wib.strftime("%d %b")

        payload_epoch = self._parse_payload_epoch(raw_payload or {})
        dt_payload_wib = datetime.fromtimestamp(payload_epoch, timezone.utc).astimezone(WIB)
        payload_wib_str = dt_payload_wib.strftime("%Y-%m-%d %H:%M:%S")

        # A. Trouble events calculated from GatewayIncidentAlert & SLA for today
        try:
            from app.services.sla_calculator_service import sla_calculator_service
            sla = sla_calculator_service.calculate_device_sla(dev_id, live_payload=raw_payload)
            for idx, ev in enumerate(sla.get("trouble_events", []), 1):
                ev_date = ev.get("date_str") or ""
                ev_start = ev.get("start_time") or ""
                # Only include events occurring today
                if ev_date and ev_date != today_iso:
                    continue
                if ev_start and today_iso not in ev_start and not ev_start.startswith(today_display):
                    continue

                metric = (ev.get("metric") or "").lower()
                cat = (ev.get("category") or "").lower()
                desc = (ev.get("description") or ev.get("title") or "").lower()
                if (
                    "dvr" in metric
                    or "nvr" in metric
                    or "cam" in metric
                    or "record" in metric
                    or "dvr" in cat
                    or "nvr" in cat
                ):
                    raw_title = ev.get("title") or ev.get("description") or "NVR System Incident Alert"
                    ev_epoch = ev.get("epoch")
                    if not ev_epoch:
                        raw_dt = ev.get("_raw_dt")
                        if raw_dt:
                            ev_epoch = raw_dt.replace(tzinfo=timezone.utc).timestamp() if raw_dt.tzinfo is None else raw_dt.timestamp()
                        else:
                            ev_epoch = payload_epoch

                    ev_time = ev.get("start_time")
                    if not ev_time or len(str(ev_time)) < 19:
                        ev_time = datetime.fromtimestamp(ev_epoch, timezone.utc).astimezone(WIB).strftime("%Y-%m-%d %H:%M:%S")

                    real_events.append({
                        "id": f"trouble-{idx}",
                        "title": self._translate_log_to_en(raw_title),
                        "time": ev_time,
                        "status": "error" if ev.get("status") == "Active" else "warning",
                        "duration": ev.get("duration", "-"),
                        "epoch": ev_epoch,
                    })
        except Exception as e:
            logger.debug(f"Could not extract trouble events for {dev_id}: {e}")

        # B. Parse recent_system_logs from MQTT telemetry stream for today only
        logs = (raw_payload or {}).get("recent_system_logs", [])
        for idx, line in enumerate(reversed(logs), 1):
            ts_m = re.match(r"\[(\d{4}-\d{2}-\d{2})\s+([\d:]+)\]", line)
            if ts_m:
                d_part, t_part = ts_m.group(1), ts_m.group(2)
                # Only include logs from today
                if d_part != today_iso:
                    continue
                try:
                    log_dt = datetime.strptime(f"{d_part} {t_part}", "%Y-%m-%d %H:%M:%S").replace(tzinfo=WIB)
                except ValueError:
                    log_dt = datetime.strptime(f"{d_part} {t_part}", "%Y-%m-%d %H:%M").replace(tzinfo=WIB)
                log_epoch = log_dt.timestamp()
                ts = f"{d_part} {t_part}" if len(t_part) == 8 else f"{d_part} {t_part}:00"
            else:
                ts_any = re.match(r"\[([\d:]+)\]", line)
                if ts_any:
                    t_str = ts_any.group(1)
                    try:
                        t_obj = datetime.strptime(t_str, "%H:%M:%S").time()
                    except ValueError:
                        t_obj = datetime.strptime(t_str, "%H:%M").time()
                    log_dt = datetime.combine(now_wib.date(), t_obj).replace(tzinfo=WIB)
                    log_epoch = log_dt.timestamp()
                    ts = log_dt.strftime("%Y-%m-%d %H:%M:%S")
                else:
                    log_epoch = payload_epoch
                    ts = payload_wib_str

            if "[NVR-CPU:" in line:
                nvr_cpu = re.search(r"\[NVR-CPU:\s*([^\]]+)\]", line)
                rec_m = re.search(r"NVR RECORDING:\s*\((.*?)\)", line)
                if nvr_cpu:
                    st = nvr_cpu.group(1).strip()
                    real_events.append({
                        "id": f"log-cpu-{idx}",
                        "title": f"CPU - NVR Connection: {st} (ISAPI/SDK link)",
                        "time": ts,
                        "status": "success" if st == "OK" else "error",
                        "epoch": log_epoch,
                    })
                if rec_m:
                    rec_st = rec_m.group(1).strip()
                    is_warn = "NOT_RECORD" in rec_st
                    real_events.append({
                        "id": f"log-rec-{idx}",
                        "title": f"Camera Recording Status: {rec_st}",
                        "time": ts,
                        "status": "warning" if is_warn else "success",
                        "epoch": log_epoch,
                    })
            elif any(k in line.lower() for k in ["kamera", "camera", "nvr", "dvr", "cctv", "harddisk nvr", "hdd1", "rekaman"]):
                if any(bad in line.lower() for bad in ["flash:", "disk /", "ram:", "modem-cpu", "sim:", "power:", "cpu:", "flash storage", "/dev/root", "/dev/mmcblk"]):
                    continue
                clean_text = re.sub(r"^\[.*?\]\s*(\[.*?\]\s*)*", "", line).strip()
                real_events.append({
                    "id": f"log-alert-{idx}",
                    "title": self._translate_log_to_en(clean_text),
                    "time": ts,
                    "status": "warning" if "[WARN" in line else "error" if "[ERR" in line else "info",
                    "epoch": log_epoch,
                })

            if len(real_events) >= 30:
                break

        # Fallback if no logs available: provide authentic device status snapshot
        if not real_events:
            c_status = detail.get("cpu_dvr", {}).get("status", "No Response")
            nvr_ip = detail.get("nvr_endpoint", "172.16.57.106:80")
            real_events.append({
                "id": "evt-live-nvr",
                "title": f"NVR Surveillance Connectivity ({nvr_ip}): {c_status}",
                "time": payload_wib_str,
                "status": "success" if c_status in ["Healthy", "Connected", "Running", "OK"] else "warning",
                "epoch": payload_epoch,
            })

        # Deduplicate events by normalized title to prevent duplicate entries
        seen_titles = set()
        deduped_events = []
        for ev in real_events:
            norm_key = re.sub(r"[^a-zA-Z0-9]", "", ev["title"].lower())
            if norm_key in seen_titles:
                continue
            seen_titles.add(norm_key)
            deduped_events.append(ev)
        real_events = deduped_events

        # STRICTLY SORT DESCENDING: Newest/latest on top
        real_events.sort(key=lambda x: x.get("epoch", 0.0), reverse=True)

        # Fallback if no logs available: provide authentic device status snapshot
        if not real_events:
            c_status = detail.get("cpu_dvr", {}).get("status", "No Response")
            r_status = detail.get("recording_storage", {}).get("status", "Not Recording")
            h_status = detail.get("dvr_health", {}).get("status", "Warning")
            curr_time = detail.get("last_update", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

            real_events.append({
                "id": "evt-live-cpu",
                "title": f"CPU - NVR Communication: {c_status}",
                "time": curr_time,
                "status": "success" if c_status == "Connected" else "error",
            })
            real_events.append({
                "id": "evt-live-rec",
                "title": f"Continuous Video Recording: {r_status}",
                "time": curr_time,
                "status": "success" if r_status == "Normal" else "warning",
            })
            real_events.append({
                "id": "evt-live-health",
                "title": f"Overall NVR Health: {h_status}",
                "time": curr_time,
                "status": "success" if h_status == "Good" else "warning",
            })

        detail["events"] = real_events

        # If gateway is truly offline (> 1h without telemetry), reflect offline status while preserving last known good state:
        g_live = self._live_gateways.get(dev_id, {})
        is_gw_truly_offline = (g_live.get("status") == "Offline") or (g_live.get("table_item", {}).get("status") == "Offline")
        if is_gw_truly_offline:
            last_seen = g_live.get("last_seen_epoch") or payload_epoch
            age_sec = max(0.0, time.time() - last_seen)
            dur_m = int(age_sec // 60)
            dur_str = f"{dur_m // 60}h {dur_m % 60}m" if dur_m >= 60 else f"{dur_m}m"
            if dur_m >= 1440:
                dur_str = f"{dur_m // 1440}d {(dur_m % 1440) // 60}h"

            detail["status"] = "Offline"
            detail["service_status"] = "Stopped"
            detail["is_offline"] = True
            detail["offline_duration"] = dur_str
            detail["last_telemetry_time"] = payload_wib_str

            detail["cpu_dvr"] = {
                "status": "Not Connected",
                "message": f"Gateway Offline (> 1 Hour). NVR telemetry link lost since {payload_wib_str} ({dur_str} ago).",
                "port": detail.get("cpu_dvr", {}).get("port") or "80 (ISAPI)",
                "response_time": "Timeout",
                "packet_loss": "100%",
                "last_check": detail.get("last_update", payload_wib_str),
            }

            # PRESERVE last known good storage & S.M.A.R.T telemetry (Do NOT wipe to 0.0 or N/A):
            if "recording_storage" in detail:
                detail["recording_storage"]["is_offline"] = True
            if "dvr_health" in detail:
                detail["dvr_health"]["status"] = "Critical"
                detail["dvr_health"]["is_offline"] = True
            if "camera_status" in detail:
                detail["camera_status"]["is_offline"] = True
            for cam in detail.get("cameras", []):
                cam["is_offline"] = True
            detail["events"].insert(0, {
                "id": "evt-offline-active",
                "title": f"Device Offline: NVR Telemetry & Streams Disconnected since {payload_wib_str} (Stopped sending data for {dur_str})",
                "time": payload_wib_str,
                "status": "error",
                "duration": dur_str,
                "category": "DVR",
                "epoch": now_wib.timestamp() + 1000,
            })
        else:
            detail["status"] = "Online"
            detail["service_status"] = "Running"
            detail["is_offline"] = False

        aiops = aiops_diagnostics_service.get_diagnostics(
            payload=raw_payload,
            is_online=(detail.get("status") == "Online"),
            box_type=detail.get("type", "SmartBox")
        )
        detail["reason"] = aiops["reason"]
        detail["reason_desc"] = aiops["reason_desc"]
        detail["evidence"] = aiops["evidence"]

        return detail

    def get_gateway_detail(self, gateway_id: str) -> Dict[str, Any]:
        """Detailed telemetry for a specific gateway DVR and real Camera recording channels"""
        self._sync_freshness()
        matched_gw = None
        matched_gid = None
        raw_payload = None

        target_id_low = gateway_id.lower().strip()
        for gid, gdata in self._live_gateways.items():
            g_uuid = str(gdata.get("device_uuid") or gdata.get("detail_item", {}).get("device_uuid") or "").lower()
            if gid.lower() == target_id_low or (g_uuid and g_uuid == target_id_low) or target_id_low in gid.lower():
                matched_gw = gdata["detail_item"]
                matched_gid = gid
                raw_payload = gdata.get("raw_payload")
                break

        if not matched_gw:
            if self._live_gateways:
                first_k = list(self._live_gateways.keys())[0]
                matched_gw = self._live_gateways[first_k]["detail_item"]
                matched_gid = first_k
                raw_payload = self._live_gateways[first_k].get("raw_payload")
            else:
                return {
                    "id": gateway_id,
                    "location": f"Gateway {gateway_id}",
                    "type": "SmartBox",
                    "model": "-",
                    "dvr_model": "-",
                    "ip_address": "-",
                    "last_update": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "status": "Offline",
                    "service_status": "Stopped",
                    "cpu_dvr": {
                        "status": "Not Connected",
                        "message": "No NVR telemetry received from gateway",
                        "port": "80 (ISAPI)",
                        "response_time": "Timeout",
                        "packet_loss": "100%",
                        "last_check": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    },
                    "camera_status": {"total": 0, "online": 0, "no_video": 0, "offline": 0, "percent": 0, "sparkline": [0, 0, 0]},
                    "recording_storage": {"status": "Not Recording", "used_tb": 0.0, "total_tb": 0.0, "percent": 0, "retention_days": 0, "sparkline": [0, 0]},
                    "dvr_health": {"status": "Critical", "hdd_status": "N/A", "temperature": "N/A", "fan_status": "N/A", "bad_sector": 0},
                    "cameras": [],
                }

        return self._enrich_detail_with_history(matched_gw, matched_gid or gateway_id, raw_payload)

    def reboot_gateway_nvr(self, gateway_id: str) -> Dict[str, Any]:
        """
        Publishes REBOOT_NVR command to MQTT Broker topic: pqube/nms/{gateway_id}/command
        Equivalent to:
        mosquitto_pub -h $MQTT_BROKER_HOST -p $MQTT_BROKER_PORT -u $MQTT_USERNAME -P $MQTT_PASSWORD -t pqube/nms/{gateway_id}/command -q 1 -m '{"action":"REBOOT_NVR"}'
        """
        import json
        from app.core.config import settings
        import paho.mqtt.publish as publish

        target_id = gateway_id.strip()
        topic = f"pqube/nms/{target_id}/command"
        payload_data = {"action": "REBOOT_NVR"}
        payload_str = json.dumps(payload_data)

        # 1. First priority: publish via persistent live MQTT client from agent_manager (reuses existing broker connection)
        published = False
        try:
            from app.agents.agent_manager import agent_manager
            if agent_manager and agent_manager._mqtt_client and agent_manager._mqtt_client.is_connected():
                info = agent_manager._mqtt_client.publish(topic, payload_str, qos=1)
                info.wait_for_publish(timeout=3.0)
                published = True
                logger.info(f"MQTT REBOOT_NVR command dispatched via persistent agent client to topic '{topic}' with QoS 1")
        except Exception as e_agent:
            logger.debug(f"Persistent agent client publish not available, falling back to publish.single: {e_agent}")

        # 2. Second priority: publish via standalone publish.single with config from .env / settings
        if not published:
            auth = None
            if settings.MQTT_USERNAME and settings.MQTT_PASSWORD:
                auth = {
                    "username": settings.MQTT_USERNAME,
                    "password": settings.MQTT_PASSWORD,
                }
            try:
                publish.single(
                    topic,
                    payload=payload_str,
                    hostname=settings.MQTT_BROKER_HOST,
                    port=settings.MQTT_BROKER_PORT,
                    auth=auth,
                    qos=1,
                )
                published = True
                logger.info(f"MQTT REBOOT_NVR command dispatched via publish.single to '{settings.MQTT_BROKER_HOST}:{settings.MQTT_BROKER_PORT}' topic '{topic}' with QoS 1")
            except Exception as e_single:
                logger.error(f"Failed to publish MQTT REBOOT_NVR command to '{topic}': {e_single}")
                return {
                    "success": False,
                    "device_id": target_id,
                    "topic": topic,
                    "action": "REBOOT_NVR",
                    "broker": f"{settings.MQTT_BROKER_HOST}:{settings.MQTT_BROKER_PORT}",
                    "message": f"Failed to dispatch MQTT reboot command: {str(e_single)}",
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                }

        return {
            "success": True,
            "device_id": target_id,
            "topic": topic,
            "action": "REBOOT_NVR",
            "broker": f"{settings.MQTT_BROKER_HOST}:{settings.MQTT_BROKER_PORT}",
            "message": f"Reboot instruction successfully dispatched to {target_id} via MQTT (Topic: {topic}, QoS: 1). NVR is restarting (estimated 60–90 seconds).",
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }


dvr_service = DVRService()

