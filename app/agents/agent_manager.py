import json
import time
import logging
import threading
from typing import Dict, Any, Optional

try:
    import paho.mqtt.client as mqtt
except ImportError:
    mqtt = None

from app.core.config import settings
from app.agents.connectivity_agent import ConnectivityAgent
from app.agents.dvr_health_agent import DVRHealthAgent
from app.agents.system_health_agent import SystemHealthAgent

logger = logging.getLogger(__name__)


class GatewayAgentManager:
    """
    Orchestrates the 3 Monitoring Agents:
    1. Connectivity Agent (Modem & SIM)
    2. DVR Health Agent (DVR & CCTV)
    3. System Health Agent (CPU, RAM, SD Card)
    And pushes periodic telemetry payload via MQTT.
    """

    def __init__(self):
        self.connectivity_agent = ConnectivityAgent(
            port=settings.MODEM_SERIAL_PORT,
            baudrate=settings.MODEM_BAUDRATE,
        )
        self.dvr_agent = DVRHealthAgent(
            host=settings.DVR_HOST,
            http_port=settings.DVR_PORT,
            rtsp_port=settings.DVR_RTSP_PORT,
        )
        self.system_agent = SystemHealthAgent()

        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._mqtt_client: Optional[Any] = None
        self._latest_snapshot: Dict[str, Any] = {}
        self._last_saved_to_db: Dict[str, float] = {}
        self._db_save_interval: float = 300.0

    def _save_to_database(self, payload: Dict[str, Any]):
        """Persists a historical telemetry snapshot to PostgreSQL every 5 minutes per device."""
        try:
            dev_id = payload.get("device_id") or settings.GATEWAY_ID
            now_ts = time.time()
            last_ts = self._last_saved_to_db.get(dev_id, 0.0)

            if (now_ts - last_ts) < self._db_save_interval:
                return

            from app.core.database import SessionLocal
            from app.models.base_models import GatewayTelemetryHistory
            from datetime import datetime

            gw_sys = payload.get("gateway_system", {})
            cpu = gw_sys.get("cpu", {})
            mem = gw_sys.get("memory", {})
            hw = gw_sys.get("hardware", {})
            sim = payload.get("cellular_sim", {})
            modem = payload.get("modem_usb", {})
            nvr = payload.get("nvr_surveillance", {})
            flash = payload.get("flash_storage", {})
            parts = flash.get("partitions", [])
            p0 = parts[0] if parts else {}

            csq = sim.get("signal", {}).get("csq", 0)
            rsrp_val = -(113 - 2 * csq) if csq > 0 else None

            cameras = nvr.get("cameras", {})
            cam_online = cameras.get("online_count", 0) if isinstance(cameras, dict) else 0
            cam_total = cameras.get("total_cameras", 0) if isinstance(cameras, dict) else 0

            rec_obj = nvr.get("recording", {})
            is_rec = rec_obj.get("is_recording", False) if isinstance(rec_obj, dict) else False

            loc_name = (
                payload.get("location_name")
                or payload.get("site_name")
                or payload.get("site_info", {}).get("location_name")
                or payload.get("site_info", {}).get("site_name")
                or f"Gateway {dev_id}"
            )

            db = SessionLocal()
            try:
                hist_entry = GatewayTelemetryHistory(
                    device_id=dev_id,
                    recorded_at=datetime.utcnow(),
                    overall_status=payload.get("overall_status"),
                    location=loc_name,
                    hardware_model=hw.get("model") or hw.get("type") or "-",
                    cpu_percent=cpu.get("usage_percent"),
                    temperature_c=cpu.get("temperature_c"),
                    ram_used_mb=mem.get("used_mb"),
                    ram_total_mb=mem.get("total_mb"),
                    disk_used_percent=p0.get("used_percent"),
                    operator=sim.get("operator") if sim.get("operator") != "N/A" else None,
                    sim_status="Aktif" if sim.get("sim_inserted") else "Tidak Terdeteksi",
                    signal_csq=csq,
                    signal_rsrp=rsrp_val,
                    phone_number=sim.get("msisdn") if sim.get("msisdn") != "N/A" else None,
                    cellular_ip=sim.get("data_traffic", {}).get("cellular_ip"),
                    nvr_status=nvr.get("status"),
                    nvr_recording=is_rec,
                    cameras_online=cam_online,
                    cameras_total=cam_total,
                    raw_payload=payload,
                )
                db.add(hist_entry)
                db.commit()
                self._last_saved_to_db[dev_id] = now_ts
                logger.info(f"[DB] Successfully recorded 5-minute telemetry history for device '{dev_id}'")
            finally:
                db.close()
        except Exception as dbe:
            logger.warning(f"Could not persist telemetry to database: {dbe}")

    def _on_connect(self, client, userdata, flags, rc, properties=None):
        if rc == 0:
            logger.info(f"Connected to MQTT Broker {settings.MQTT_BROKER_HOST}:{settings.MQTT_BROKER_PORT}")
            client.subscribe(settings.MQTT_TOPIC_TELEMETRY)
            logger.info(f"Subscribed to MQTT Topic: '{settings.MQTT_TOPIC_TELEMETRY}'")
        else:
            logger.error(f"MQTT connect failed, return code={rc}")

    def _on_message(self, client, userdata, msg):
        try:
            payload_str = msg.payload.decode("utf-8", errors="replace")
            payload = json.loads(payload_str)
            logger.info(f"Received MQTT Telemetry from topic: '{msg.topic}' (Device: {payload.get('device_id')})")
            
            if "gateway_system" in payload or "cellular_sim" in payload:
                mapped = self._map_nms_payload(payload)
                self._latest_snapshot = mapped
                try:
                    from app.services.cellular_service import cellular_service
                    cellular_service.update_from_telemetry(payload)
                except Exception as ce:
                    logger.warning(f"Could not update cellular service: {ce}")

                try:
                    from app.services.dvr_service import dvr_service
                    dvr_service.update_from_telemetry(payload)
                except Exception as de:
                    logger.warning(f"Could not update dvr service: {de}")

                try:
                    from app.services.system_health_service import system_health_service
                    system_health_service.update_from_telemetry(payload)
                except Exception as she:
                    logger.warning(f"Could not update system health service: {she}")

                try:
                    from app.services.cellular_report_service import cellular_report_service
                    cellular_report_service.update_from_telemetry(payload)
                except Exception as cre:
                    logger.warning(f"Could not update cellular report service: {cre}")

                try:
                    from app.services.dvr_report_service import dvr_report_service
                    dvr_report_service.update_from_telemetry(payload)
                except Exception as dre:
                    logger.warning(f"Could not update dvr report service: {dre}")

                try:
                    from app.services.health_report_service import health_report_service
                    health_report_service.update_from_telemetry(payload)
                except Exception as hre:
                    logger.warning(f"Could not update health report service: {hre}")
                
                self._save_to_database(payload)
            else:
                self._latest_snapshot = payload
        except Exception as e:
            logger.error(f"Error processing MQTT message: {e}")

    def _map_nms_payload(self, nms: Dict[str, Any]) -> Dict[str, Any]:
        """
        Maps incoming NMS payload from gateway to standard IGatewayHealthTelemetry schema for dashboard.
        """
        gw_sys = nms.get("gateway_system", {})
        hw = gw_sys.get("hardware", {})
        cpu = gw_sys.get("cpu", {})
        mem = gw_sys.get("memory", {})
        
        flash = nms.get("flash_storage", {})
        parts = flash.get("partitions", [])
        p0 = parts[0] if parts else {}
        
        modem = nms.get("modem_usb", {})
        sim = nms.get("cellular_sim", {})
        sig = sim.get("signal", {})
        
        nvr = nms.get("nvr_surveillance", {})
        rec = nvr.get("recording", {})
        
        alerts = nms.get("active_alerts", [])
        issues = [a.get("message", a.get("code", "")) for a in alerts if isinstance(a, dict)]
        
        conn_data = {
            "status": "HEALTHY" if sim.get("sim_inserted") else "DISCONNECTED",
            "modem_connected": modem.get("connected", False),
            "port": modem.get("serial_ports", [{}])[0].get("port", "/dev/ttyUSB2") if modem.get("serial_ports") else "/dev/ttyUSB2",
            "operator": sim.get("operator") if sim.get("operator") != "N/A" else None,
            "iccid": sim.get("iccid") if sim.get("iccid") != "N/A" else None,
            "phone_number": sim.get("msisdn") if sim.get("msisdn") != "N/A" else None,
            "signal_csq": sig.get("csq", 0),
            "signal_percent": sig.get("quality_percent", 0.0),
            "signal_quality": sig.get("status", "Unknown"),
            "temperature_celsius": cpu.get("temperature_c"),
            "network_tech": sim.get("network_mode", "LTE"),
            "registration_status": sim.get("connection_state", "Unknown"),
            "error": None if sim.get("sim_inserted") else sim.get("connection_state"),
        }
        
        dvr_data = {
            "status": "HEALTHY" if nvr.get("connected") else "OFFLINE",
            "host": nvr.get("nvr_endpoint", "172.16.37.130"),
            "ping_ok": nvr.get("connected", False),
            "http_port_open": nvr.get("connected", False),
            "rtsp_port_open": nvr.get("connected", False),
            "hdd_status": "GOOD" if nvr.get("total_capacity_gb", 0) > 0 else "UNKNOWN",
            "hdd_total_gb": nvr.get("total_capacity_gb", 0.0),
            "hdd_used_gb": nvr.get("total_used_gb", 0.0),
            "hdd_free_gb": nvr.get("total_free_gb", 0.0),
            "hdd_usage_percent": round(100.0 - nvr.get("total_free_percent", 100.0), 1) if nvr.get("total_free_percent") is not None else 0.0,
            "recording_active": rec.get("is_recording", False),
            "channel_count": len(nvr.get("disks", [])),
            "channels": [],
            "issues": [nvr.get("error_message")] if nvr.get("error_message") else [],
        }
        
        sys_data = {
            "status": cpu.get("status", "HEALTHY"),
            "cpu": {
                "usage_percent": cpu.get("usage_percent", 0.0),
                "core_count": cpu.get("cores", 4),
                "load_average_1m": cpu.get("load_avg", [0, 0, 0])[0] if cpu.get("load_avg") else 0.0,
                "load_average_5m": cpu.get("load_avg", [0, 0, 0])[1] if len(cpu.get("load_avg", [])) > 1 else 0.0,
                "load_average_15m": cpu.get("load_avg", [0, 0, 0])[2] if len(cpu.get("load_avg", [])) > 2 else 0.0,
            },
            "ram": {
                "total_mb": mem.get("total_mb", 0.0),
                "used_mb": mem.get("used_mb", 0.0),
                "free_mb": mem.get("free_mb", 0.0),
                "usage_percent": mem.get("usage_percent", 0.0),
            },
            "sd_card": {
                "mount_point": p0.get("mount_point", "/userdata"),
                "total_gb": p0.get("total_gb", flash.get("hardware", {}).get("total_disk_gb", 0.0)),
                "used_gb": p0.get("used_gb", 0.0),
                "free_gb": p0.get("free_gb", 0.0),
                "usage_percent": p0.get("used_percent", 0.0),
                "is_readonly": flash.get("hw_write_lock", "").lower() != "normal (writable)",
                "health_status": flash.get("health_label", "Healthy"),
            },
            "issues": issues,
        }
        
        return {
            "gateway_id": nms.get("device_id", settings.GATEWAY_ID),
            "gateway_type": f"{hw.get('type', 'Gateway')} {hw.get('model', '')}".strip() or "-",
            "timestamp": nms.get("timestamp", time.time()),
            "overall_status": nms.get("overall_status", "HEALTHY"),
            "has_critical_issue": nms.get("overall_status") == "CRITICAL" or len(issues) > 0,
            "connectivity": conn_data,
            "dvr": dvr_data,
            "system": sys_data,
            "issues": issues,
            "collection_duration_ms": 0.0,
            "raw_nms": nms,
        }

    def _setup_mqtt(self):
        if not mqtt:
            logger.warning("paho-mqtt library not installed. Telemetry will not be subscribed/published.")
            return

        try:
            if hasattr(mqtt, "CallbackAPIVersion"):
                self._mqtt_client = mqtt.Client(
                    mqtt.CallbackAPIVersion.VERSION2,
                    client_id=settings.MQTT_CLIENT_ID,
                )
            else:
                self._mqtt_client = mqtt.Client(
                    client_id=settings.MQTT_CLIENT_ID,
                    protocol=mqtt.MQTTv5 if hasattr(mqtt, "MQTTv5") else 4,
                )

            if settings.MQTT_USERNAME and settings.MQTT_PASSWORD:
                self._mqtt_client.username_pw_set(settings.MQTT_USERNAME, settings.MQTT_PASSWORD)

            self._mqtt_client.on_connect = self._on_connect
            self._mqtt_client.on_message = self._on_message

            self._mqtt_client.connect_async(settings.MQTT_BROKER_HOST, settings.MQTT_BROKER_PORT, keepalive=60)
            self._mqtt_client.loop_start()
            logger.info(f"MQTT Client initialized to {settings.MQTT_BROKER_HOST}:{settings.MQTT_BROKER_PORT}")
        except Exception as e:
            logger.warning(f"Could not connect to MQTT broker: {e}")

    def collect_all(self) -> Dict[str, Any]:
        """
        Runs all 3 agents and bundles into a unified telemetry payload (fallback if no MQTT live data).
        """
        start_time = time.time()
        conn_data = self.connectivity_agent.inspect()
        dvr_data = self.dvr_agent.inspect()
        sys_data = self.system_agent.inspect()

        is_healthy = (
            conn_data.get("status") in ("HEALTHY", "SIMULATED")
            and dvr_data.get("status") in ("HEALTHY", "WARNING")
            and sys_data.get("status") in ("HEALTHY", "WARNING")
        )

        all_issues = []
        if conn_data.get("error"):
            all_issues.append(f"Connectivity: {conn_data['error']}")
        all_issues.extend(dvr_data.get("issues", []))
        all_issues.extend(sys_data.get("issues", []))

        payload = {
            "gateway_id": settings.GATEWAY_ID,
            "gateway_type": "SmartBox Hitam (RPi 3B+)" if settings.GATEWAY_TYPE == 1 else "SmartBox Putih (Rockchip)",
            "timestamp": time.time(),
            "overall_status": "HEALTHY" if is_healthy else "DEGRADED",
            "has_critical_issue": (sys_data.get("status") == "CRITICAL" or dvr_data.get("status") == "OFFLINE"),
            "connectivity": conn_data,
            "dvr": dvr_data,
            "system": sys_data,
            "issues": all_issues,
            "collection_duration_ms": round((time.time() - start_time) * 1000, 2),
        }

        self._latest_snapshot = payload
        return payload

    def _loop(self):
        logger.info("Gateway Monitoring Agent loop started.")
        while self._running:
            time.sleep(settings.MQTT_PUBLISH_INTERVAL_SECONDS)

    def start(self):
        if self._running:
            return
        self._running = True
        self._setup_mqtt()

        self._thread = threading.Thread(target=self._loop, daemon=True, name="GatewayAgentThread")
        self._thread.start()

    def stop(self):
        self._running = False
        if self._mqtt_client:
            try:
                self._mqtt_client.loop_stop()
                self._mqtt_client.disconnect()
            except Exception:
                pass

    def get_latest(self) -> Dict[str, Any]:
        if not self._latest_snapshot:
            return self.collect_all()
        return self._latest_snapshot


agent_manager = GatewayAgentManager()
