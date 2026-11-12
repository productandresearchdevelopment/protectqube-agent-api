import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime
from app.core.database import Base


def generate_uuid() -> str:
    return str(uuid.uuid4())


class BaseModel(Base):
    __abstract__ = True

    id = Column(String(36), primary_key=True, default=generate_uuid)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=True)
    deleted_at = Column(DateTime, nullable=True)
    created_by = Column(String(36), nullable=True)
    updated_by = Column(String(36), nullable=True)
    deleted_by = Column(String(36), nullable=True)


from app.models.auth_models import (
    EmailVerificationStatus,
    OtpType,
    Role,
    ModuleType,
    Module,
    RoleModule,
    Upload,
    User,
    UserSession,
    UserOtp,
)
from app.models.gateway_models import (
    Client,
    Device,
    GatewayTelemetryHistory,
    GatewayIncidentAlert,
)
from app.models.notification_models import (
    NotificationEvent,
    NotificationDestination,
    NotificationTarget,
    Notification,
    NotificationDelivery,
)
