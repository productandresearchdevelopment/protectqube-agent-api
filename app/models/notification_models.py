from datetime import datetime
from sqlalchemy import (
    Column,
    String,
    Boolean,
    DateTime,
    Text,
    JSON,
    ForeignKey,
)
from app.models.base_models import BaseModel


class NotificationEvent(BaseModel):
    __tablename__ = "notification_events"

    event_code = Column(String(50), unique=True, nullable=False, index=True)
    name = Column(String(100), nullable=False)
    category = Column(String(50), nullable=False, index=True)
    description = Column(Text, nullable=True)
    channels = Column(JSON, nullable=False, default=list)


class NotificationDestination(BaseModel):
    __tablename__ = "notification_destinations"

    provider_key = Column(String(50), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    config = Column(JSON, nullable=False, default=dict)
    status = Column(String(20), default="CONNECTED", nullable=False)
    last_tested_at = Column(DateTime, nullable=True)


class NotificationTarget(BaseModel):
    __tablename__ = "notification_targets"

    provider_key = Column(String(50), nullable=False, index=True)
    external_id = Column(String(255), nullable=False, index=True)
    display_name = Column(String(255), nullable=False)
    type = Column(String(50), nullable=False, default="chat")
    source = Column(String(50), nullable=False, default="manual")
    config = Column(JSON, nullable=False, default=dict)
    is_active = Column(Boolean, default=True, nullable=False)
    last_synced_at = Column(DateTime, nullable=True)


class Notification(BaseModel):
    __tablename__ = "notifications"

    event_code = Column(String(50), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    body = Column(Text, nullable=False)
    severity = Column(String(20), default="WARNING", nullable=False)
    data = Column(JSON, nullable=True)
    is_read = Column(Boolean, default=False, nullable=False, index=True)
    read_at = Column(DateTime, nullable=True)


class NotificationDelivery(BaseModel):
    __tablename__ = "notification_deliveries"

    notification_id = Column(String(36), ForeignKey("notifications.id", ondelete="SET NULL"), nullable=True, index=True)
    destination_id = Column(String(36), ForeignKey("notification_destinations.id", ondelete="SET NULL"), nullable=True, index=True)
    channel_type = Column(String(50), nullable=False, index=True)
    recipient = Column(String(255), nullable=True)
    status = Column(String(20), default="SUCCESS", nullable=False)
    error_message = Column(Text, nullable=True)
    response_payload = Column(JSON, nullable=True)
    sent_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
