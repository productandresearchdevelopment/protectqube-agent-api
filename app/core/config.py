from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "Agent PQube Gateway"
    API_V1_STR: str = "/api/v1"
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    DEBUG: bool = True

    SECRET_KEY: str = "super-secret-key-change-this-in-production-agent-pqube-2026"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    DATABASE_URL: str = "postgresql+psycopg2://postgres:Dysaputra1701@localhost:5433/agent_pqube"

    MQTT_BROKER_HOST: str = "72.60.78.162"
    MQTT_BROKER_PORT: int = 1883
    MQTT_USERNAME: Optional[str] = "protequbeai"
    MQTT_PASSWORD: Optional[str] = "@Qualita2025"
    MQTT_CLIENT_ID: str = "smartbox-backend-sub"
    MQTT_TOPIC_TELEMETRY: str = "pqube/nms/#"
    MQTT_PUBLISH_INTERVAL_SECONDS: int = 30

    GATEWAY_TYPE: int = 1
    GATEWAY_ID: str = "smartbox-gateway-01"
    MODEM_SERIAL_PORT: str = "/dev/ttyUSB2"
    MODEM_BAUDRATE: int = 115200
    DVR_HOST: str = "192.168.1.100"
    DVR_PORT: int = 80
    DVR_RTSP_PORT: int = 554

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
