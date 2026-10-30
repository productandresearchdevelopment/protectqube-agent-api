import sys
import logging
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from app.core.config import settings
from app.core.init_db import init_db
from app.agents.agent_manager import agent_manager
from app.api.v1.api import api_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("agent-pqube")


def start_worker():
    logger.info("==================================================")
    logger.info("Starting Agent PQube MQTT Ingestion Worker")
    logger.info(f"Broker: {settings.MQTT_BROKER_HOST}:{settings.MQTT_BROKER_PORT}")
    logger.info(f"Topic:  {settings.MQTT_TOPIC_TELEMETRY}")
    logger.info("==================================================")
    agent_manager.start()
    logger.info("MQTT Worker is actively listening and ingesting telemetry...")


def stop_worker():
    logger.info("Stopping MQTT Worker & Gateway Monitoring Agents...")
    agent_manager.stop()
    logger.info("MQTT Worker stopped cleanly.")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing Agent PQube SmartBox Backend...")
    try:
        init_db()
    except Exception as e:
        logger.error(f"Database initialization error: {e}")
    try:
        start_worker()
    except Exception as e:
        logger.error(f"Worker start error: {e}")
    yield
    try:
        stop_worker()
    except Exception as e:
        logger.error(f"Worker stop error: {e}")


app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    docs_url=f"{settings.API_V1_STR}/docs",
    redoc_url=f"{settings.API_V1_STR}/redoc",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"https?://.*",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix=settings.API_V1_STR)


@app.get("/", tags=["Health"])
def root():
    return {
        "status": True,
        "name": settings.PROJECT_NAME,
        "gateway_id": settings.GATEWAY_ID,
        "gateway_type": "SmartBox Hitam (Raspberry Pi 3B+)" if settings.GATEWAY_TYPE == 1 else "SmartBox Putih (Rockchip)",
        "version": "1.0.0",
        "docs": f"{settings.API_V1_STR}/docs",
    }


@app.get("/health", tags=["Health"])
def health_check():
    return {
        "status": "healthy",
        "service": "agent-pqube-backend-python",
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host=settings.HOST, port=settings.PORT, reload=settings.DEBUG, app_dir=str(BASE_DIR))
