import logging
from datetime import datetime
from typing import Dict, Any, Tuple
from sqlalchemy.orm import Session
from app.models.notification_models import Notification
from app.services.notification.providers.base import BaseNotificationProvider

logger = logging.getLogger(__name__)


class InAppProvider(BaseNotificationProvider):
    provider_key = "in_app"
    display_name = "In-App Dashboard"
    description = "Displays real-time notifications in the top navbar bell and incident feed."
    icon = "Bell"

    def get_config_schema(self) -> Dict[str, Any]:
        return {
            "fields": []
        }

    def test_connection(self, config: Dict[str, Any]) -> Tuple[bool, str]:
        return True, "In-App provider is native and always active."

    def send(self, recipient: str, title: str, body: str, data: Dict[str, Any], config: Dict[str, Any]) -> Tuple[bool, str, Any]:
        return True, "", {}

    def create_in_app_record(
        self,
        db: Session,
        event_code: str,
        title: str,
        body: str,
        severity: str,
        data: Dict[str, Any] = None
    ) -> Notification:
        notif = Notification(
            event_code=event_code,
            title=title,
            body=body,
            severity=severity,
            data=data or {},
            is_read=False,
            created_at=datetime.utcnow()
        )
        db.add(notif)
        db.commit()
        db.refresh(notif)
        return notif
