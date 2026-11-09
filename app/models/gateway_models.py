from datetime import datetime
import uuid
from sqlalchemy import (
    Column,
    String,
    Integer,
    Float,
    Boolean,
    DateTime,
    ForeignKey,
    Text,
    JSON,
)
from sqlalchemy.orm import relationship
from app.core.database import Base


def generate_uuid() -> str:
    return str(uuid.uuid4())


class GatewayTelemetryHistory(Base):
    __tablename__ = "gateway_telemetry_history"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    device_id = Column(String(50), nullable=False, index=True)
    recorded_at = Column(DateTime, default=datetime.utcnow, index=True)

    overall_status = Column(String(20), nullable=True)
    location = Column(String(100), nullable=True)
    hardware_model = Column(String(100), nullable=True)

    cpu_percent = Column(Float, nullable=True)
    temperature_c = Column(Float, nullable=True)
    ram_used_mb = Column(Float, nullable=True)
    ram_total_mb = Column(Float, nullable=True)
    disk_used_percent = Column(Float, nullable=True)

    operator = Column(String(50), nullable=True)
    sim_status = Column(String(50), nullable=True)
    signal_csq = Column(Integer, nullable=True)
    signal_rsrp = Column(Integer, nullable=True)
    phone_number = Column(String(50), nullable=True)
    cellular_ip = Column(String(50), nullable=True)

    nvr_status = Column(String(50), nullable=True)
    nvr_recording = Column(Boolean, nullable=True)
    cameras_online = Column(Integer, nullable=True)
    cameras_total = Column(Integer, nullable=True)

    raw_payload = Column(JSON, nullable=True)


class GatewayIncidentAlert(Base):
    __tablename__ = "gateway_incident_alerts"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    device_id = Column(String(50), nullable=False, index=True)
    telemetry_history_id = Column(String(36), ForeignKey("gateway_telemetry_history.id", ondelete="SET NULL"), nullable=True, index=True)
    metric = Column(String(30), nullable=False, index=True)
    description = Column(Text, nullable=False)
    start_time = Column(DateTime, nullable=False, index=True)
    end_time = Column(DateTime, nullable=True)
    duration_minutes = Column(Float, default=0.0)
    duration_str = Column(String(50), nullable=True)
    status = Column(String(20), default="RESOLVED", index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    telemetry_history = relationship("GatewayTelemetryHistory", backref="incident_alerts")
