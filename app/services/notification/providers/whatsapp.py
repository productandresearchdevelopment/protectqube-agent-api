import logging
from typing import Dict, Any, Tuple
from app.services.notification.providers.base import BaseNotificationProvider
from app.services.notification.whatsapp_session import whatsapp_session_manager

logger = logging.getLogger(__name__)


class WhatsAppProvider(BaseNotificationProvider):
    provider_key = "whatsapp"
    display_name = "WhatsApp"
    description = "Connect via Linked Device (QR Code or Pairing Code)"
    icon = "MessageSquare"

    def get_config_schema(self) -> Dict[str, Any]:
        return {
            "fields": []
        }

    def test_connection(self, config: Dict[str, Any]) -> Tuple[bool, str]:
        status = whatsapp_session_manager.get_status()
        if status.get("is_logged_in"):
            return True, "WhatsApp is connected and authenticated via Linked Device."
        return False, "WhatsApp is not connected. Please scan the QR code or enter pairing code in Integrations."

    def send(self, recipient: str, title: str, body: str, data: Dict[str, Any], config: Dict[str, Any]) -> Tuple[bool, str, Any]:
        target = recipient.strip() if recipient else ""
        if not target:
            return False, "Recipient phone number is required.", None

        dev_id = data.get("device_id", "Unknown Device")
        location = data.get("location", "-")
        time_str = data.get("timestamp", "")
        message_str = body or data.get("description", "")

        msg = (
            f"ID: {dev_id}\n"
            f"Location: {location}\n"
            f"Time: {time_str}\n"
            f"Message: {message_str}"
        )

        return whatsapp_session_manager.send_message(target, msg)
