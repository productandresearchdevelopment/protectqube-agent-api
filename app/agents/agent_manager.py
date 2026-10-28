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

    def _setup_mqtt(self):
        if not mqtt:
            logger.warning("paho-mqtt library not installed. Telemetry will not be published to broker.")
            return

        try:
            self._mqtt_client = mqtt.Client(
                client_id=settings.MQTT_CLIENT_ID,
                protocol=mqtt.MQTTv5 if hasattr(mqtt, "MQTTv5") else 4,
            )
            if settings.MQTT_USERNAME and settings.MQTT_PASSWORD:
                self._mqtt_client.username_pw_set(settings.MQTT_USERNAME, settings.MQTT_PASSWORD)

            self._mqtt_client.connect_async(settings.MQTT_BROKER_HOST, settings.MQTT_BROKER_PORT, keepalive=60)
            self._mqtt_client.loop_start()
            logger.info(f"MQTT Client initialized to {settings.MQTT_BROKER_HOST}:{settings.MQTT_BROKER_PORT}")
        except Exception as e:
            logger.warning(f"Could not connect to MQTT broker: {e}")

    def collect_all(self) -> Dict[str, Any]:
        """
        Runs all 3 agents and bundles into a unified telemetry payload.
        """
        start_time = time.time()
        conn_data = self.connectivity_agent.inspect()
        dvr_data = self.dvr_agent.inspect()
        sys_data = self.system_agent.inspect()

        # Overall Gateway Health
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
            try:
                payload = self.collect_all()
                if self._mqtt_client and self._mqtt_client.is_connected():
                    self._mqtt_client.publish(
                        settings.MQTT_TOPIC_TELEMETRY,
                        json.dumps(payload),
                        qos=1,
                    )
            except Exception as e:
                logger.error(f"Error in agent collection loop: {e}")

            time.sleep(settings.MQTT_PUBLISH_INTERVAL_SECONDS)

    def start(self):
        if self._running:
            return
        self._running = True
        self._setup_mqtt()
        # Take immediate first snapshot
        try:
            self.collect_all()
        except Exception as e:
            logger.warning(f"Initial agent snapshot failed: {e}")

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
