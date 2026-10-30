import uuid
import enum
from datetime import datetime
from sqlalchemy import (
    Column,
    String,
    Integer,
    Float,
    Boolean,
    DateTime,
    ForeignKey,
    Enum,
    Text,
    JSON,
)
from sqlalchemy.orm import relationship
from app.core.database import Base


def generate_uuid() -> str:
    return str(uuid.uuid4())


class EmailVerificationStatus(str, enum.Enum):
    PENDING = "PENDING"
    VERIFIED = "VERIFIED"
    EXPIRED = "EXPIRED"


class OtpType(str, enum.Enum):
    EMAIL_VERIFICATION = "EMAIL_VERIFICATION"
    PASSWORD_RESET = "PASSWORD_RESET"


class Role(Base):
    __tablename__ = "roles"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    name = Column(String(100), nullable=False, index=True)
    alias = Column(String(100), nullable=False)
    color = Column(String(20), nullable=False, default="#3b82f6")
    description = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    deleted_at = Column(DateTime, nullable=True)

    users = relationship("User", back_populates="role")
    role_modules = relationship("RoleModule", back_populates="role", cascade="all, delete-orphan")


class ModuleType(Base):
    __tablename__ = "module_types"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    name = Column(String(100), nullable=False)
    icon = Column(String(50), nullable=True)
    description = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    deleted_at = Column(DateTime, nullable=True)

    modules = relationship("Module", back_populates="module_type")


class Module(Base):
    __tablename__ = "modules"

    id = Column(Integer, primary_key=True, autoincrement=True)
    module_type_id = Column(String(36), ForeignKey("module_types.id", onupdate="CASCADE", ondelete="RESTRICT"), nullable=False, index=True)
    parent_id = Column(Integer, ForeignKey("modules.id", onupdate="CASCADE", ondelete="SET NULL"), nullable=True, index=True)
    path = Column(String(255), nullable=True)
    name = Column(String(100), nullable=False)
    icon = Column(String(50), nullable=True)
    route = Column(String(255), nullable=True)
    description = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    deleted_at = Column(DateTime, nullable=True)

    module_type = relationship("ModuleType", back_populates="modules")
    parent = relationship("Module", remote_side=[id], back_populates="children")
    children = relationship("Module", back_populates="parent")
    role_modules = relationship("RoleModule", back_populates="module", cascade="all, delete-orphan")


class RoleModule(Base):
    __tablename__ = "role_modules"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    role_id = Column(String(36), ForeignKey("roles.id", onupdate="CASCADE", ondelete="CASCADE"), nullable=False, index=True)
    module_id = Column(Integer, ForeignKey("modules.id", onupdate="CASCADE", ondelete="CASCADE"), nullable=False, index=True)
    checked = Column(Boolean, default=False, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    deleted_at = Column(DateTime, nullable=True)

    role = relationship("Role", back_populates="role_modules")
    module = relationship("Module", back_populates="role_modules")


class Upload(Base):
    __tablename__ = "uploads"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    filename = Column(String(255), nullable=False)
    category = Column(String(100), nullable=False)
    path = Column(String(500), nullable=False)
    type = Column(String(50), nullable=False)
    mime = Column(String(100), nullable=False)
    extension = Column(String(20), nullable=False)
    size = Column(Integer, nullable=False)
    filename_origin = Column(String(255), nullable=False)
    bucket = Column(String(100), nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    deleted_at = Column(DateTime, nullable=True)

    users = relationship("User", back_populates="avatar")


class User(Base):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    name = Column(String(100), nullable=False)
    username = Column(String(100), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password = Column(String(255), nullable=True)
    phone = Column(String(30), nullable=True)
    address = Column(Text, nullable=True)
    avatar_id = Column(String(36), ForeignKey("uploads.id", onupdate="CASCADE", ondelete="SET NULL"), unique=True, nullable=True)
    role_id = Column(String(36), ForeignKey("roles.id", onupdate="CASCADE", ondelete="RESTRICT"), nullable=False, index=True)
    last_login = Column(DateTime, nullable=True)

    email_verified = Column(Boolean, default=False, nullable=False)
    email_verified_at = Column(DateTime, nullable=True)
    email_verification_status = Column(Enum(EmailVerificationStatus), default=EmailVerificationStatus.PENDING, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    deleted_at = Column(DateTime, nullable=True)

    avatar = relationship("Upload", back_populates="users")
    role = relationship("Role", back_populates="users")
    sessions = relationship("UserSession", back_populates="user", cascade="all, delete-orphan")
    otps = relationship("UserOtp", back_populates="user", cascade="all, delete-orphan")


class UserSession(Base):
    __tablename__ = "user_sessions"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    user_id = Column(String(36), ForeignKey("users.id", onupdate="CASCADE", ondelete="CASCADE"), nullable=False, index=True)
    refresh_token_hash = Column(String(255), nullable=False)
    ip_address = Column(String(50), nullable=True)
    user_agent = Column(Text, nullable=True)
    device_name = Column(String(100), nullable=True)
    last_module_id = Column(Integer, nullable=True)
    last_activity_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    is_revoked = Column(Boolean, default=False, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    user = relationship("User", back_populates="sessions")


class UserOtp(Base):
    __tablename__ = "user_otps"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    user_id = Column(String(36), ForeignKey("users.id", onupdate="CASCADE", ondelete="CASCADE"), nullable=False, index=True)
    type = Column(Enum(OtpType), nullable=False)
    otp_hash = Column(String(255), nullable=False)
    expires_at = Column(DateTime, nullable=False)
    used = Column(Boolean, default=False, nullable=False)
    attempts = Column(Integer, default=0, nullable=False)
    last_sent_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    request_count = Column(Integer, default=1, nullable=False)
    cooldown_until = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    deleted_at = Column(DateTime, nullable=True)

    user = relationship("User", back_populates="otps")


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
