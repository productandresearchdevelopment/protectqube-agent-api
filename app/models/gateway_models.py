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
    Time,
    text,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from app.core.database import Base


def generate_uuid() -> str:
    return str(uuid.uuid4())


class Client(Base):
    __tablename__ = "clients"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()"))
    name = Column(String(255), nullable=False)
    code = Column(String(100), unique=True, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False, index=True)

    created_at = Column(DateTime, default=datetime.utcnow, server_default=text("CURRENT_TIMESTAMP"), nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, server_default=text("CURRENT_TIMESTAMP"), nullable=True)
    deleted_at = Column(DateTime, nullable=True)
    created_by = Column(UUID(as_uuid=True), nullable=True)
    updated_by = Column(UUID(as_uuid=True), nullable=True)
    deleted_by = Column(UUID(as_uuid=True), nullable=True)

    devices = relationship("Device", back_populates="client")


class Device(Base):
    __tablename__ = "devices"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()"))
    client_id = Column(UUID(as_uuid=True), ForeignKey("clients.id", ondelete="SET NULL"), nullable=True, index=True)
    name = Column(String(255), nullable=False, index=True)
    location = Column(String(255), nullable=True)
    lat = Column(Float, nullable=True)
    long = Column(Float, nullable=True)
    hardware_model = Column(String(100), nullable=True)
    operational_start = Column(Time, nullable=True)
    operational_end = Column(Time, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False, index=True)
    property = Column(JSONB, default=dict, server_default=text("'{}'::jsonb"), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, server_default=text("CURRENT_TIMESTAMP"), nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, server_default=text("CURRENT_TIMESTAMP"), nullable=True)
    deleted_at = Column(DateTime, nullable=True)
    created_by = Column(UUID(as_uuid=True), nullable=True)
    updated_by = Column(UUID(as_uuid=True), nullable=True)
    deleted_by = Column(UUID(as_uuid=True), nullable=True)

    client = relationship("Client", back_populates="devices")
    telemetry_history = relationship("GatewayTelemetryHistory", back_populates="device", cascade="all, delete-orphan")
    incident_alerts = relationship("GatewayIncidentAlert", back_populates="device", cascade="all, delete-orphan")


class GatewayTelemetryHistory(Base):
    __tablename__ = "gateway_telemetry_history"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    device_id = Column(UUID(as_uuid=True), ForeignKey("devices.id", ondelete="CASCADE"), nullable=False, index=True)
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
    created_at = Column(DateTime, default=datetime.utcnow, server_default=text("CURRENT_TIMESTAMP"), nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, server_default=text("CURRENT_TIMESTAMP"), nullable=True)
    deleted_at = Column(DateTime, nullable=True)
    created_by = Column(String(36), nullable=True)
    updated_by = Column(String(36), nullable=True)
    deleted_by = Column(String(36), nullable=True)

    device = relationship("Device", back_populates="telemetry_history")


class GatewayIncidentAlert(Base):
    __tablename__ = "gateway_incident_alerts"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    device_id = Column(UUID(as_uuid=True), ForeignKey("devices.id", ondelete="CASCADE"), nullable=False, index=True)
    telemetry_history_id = Column(String(36), ForeignKey("gateway_telemetry_history.id", ondelete="SET NULL"), nullable=True, index=True)
    metric = Column(String(30), nullable=False, index=True)
    description = Column(Text, nullable=False)
    start_time = Column(DateTime, nullable=False, index=True)
    end_time = Column(DateTime, nullable=True)
    duration_minutes = Column(Float, default=0.0)
    duration_str = Column(String(50), nullable=True)
    status = Column(String(20), default="RESOLVED", index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    deleted_at = Column(DateTime, nullable=True)
    created_by = Column(String(36), nullable=True)
    updated_by = Column(String(36), nullable=True)
    deleted_by = Column(String(36), nullable=True)

    device = relationship("Device", back_populates="incident_alerts")
    telemetry_history = relationship("GatewayTelemetryHistory", backref="incident_alerts")
