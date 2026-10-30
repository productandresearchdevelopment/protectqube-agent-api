import time
import signal
import sys
import logging
from app.core.config import settings
from app.core.init_db import init_db
from app.agents.agent_manager import agent_manager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [MQTT-Worker] %(name)s: %(message)s",
)
logger = logging.getLogger("worker")

_is_running = True


def handle_shutdown(signum, frame):
    global _is_running
    logger.info(f"Shutdown signal ({signum}) received. Stopping MQTT worker...")
    _is_running = False
    agent_manager.stop()
    logger.info("MQTT worker stopped cleanly.")
    sys.exit(0)


def main():
    logger.info("==================================================")
    logger.info("Starting Agent PQube Standalone MQTT Ingestion Worker")
    logger.info(f"Broker: {settings.MQTT_BROKER_HOST}:{settings.MQTT_BROKER_PORT}")
    logger.info(f"Topic:  {settings.MQTT_TOPIC_TELEMETRY}")
    logger.info("==================================================")

    signal.signal(signal.SIGINT, handle_shutdown)
    signal.signal(signal.SIGTERM, handle_shutdown)

    init_db()

    agent_manager.start()
    logger.info("Worker is actively listening and ingesting telemetry...")

    while _is_running:
        try:
            time.sleep(1)
        except KeyboardInterrupt:
            break

    handle_shutdown(signal.SIGINT, None)


if __name__ == "__main__":
    main()
