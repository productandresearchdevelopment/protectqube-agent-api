import logging
from typing import Dict, Any, Tuple
import httpx
from app.services.notification.providers.base import BaseNotificationProvider

logger = logging.getLogger(__name__)


class WebhookProvider(BaseNotificationProvider):
    provider_key = "webhook"
    display_name = "Generic Webhook (ERP / HTTP API)"
    description = "Send JSON incident events directly to Qualita ERP, external APIs, or custom servers."
    icon = "Link2"

    def get_config_schema(self) -> Dict[str, Any]:
        return {
            "fields": [
                {
                    "name": "webhook_url",
                    "label": "Webhook URL",
                    "type": "text",
                    "required": True,
                    "placeholder": "https://erp.qualita.co.id/api/v1/integrations/...",
                    "help": "Target HTTP endpoint that will receive POST event payloads.",
                },
                {
                    "name": "auth_header_name",
                    "label": "Auth Header Name (Optional)",
                    "type": "text",
                    "required": False,
                    "placeholder": "Authorization or X-API-Key",
                    "help": "Optional HTTP header name for authentication.",
                },
                {
                    "name": "auth_header_value",
                    "label": "Auth Header Value (Optional)",
                    "type": "password",
                    "required": False,
                    "placeholder": "Bearer your-secret-token",
                    "help": "Optional secret token or Bearer key.",
                },
            ]
        }

    def test_connection(self, config: Dict[str, Any]) -> Tuple[bool, str]:
        url = config.get("webhook_url", "").strip()
        if not url:
            return False, "Webhook URL is required"

        test_payload = {
            "event": "test_ping",
            "device_id": "test-device",
            "title": "Protectqube Webhook Test",
            "body": "This is a test event from Protectqube Agent webhook provider.",
            "data": {"status": "ok", "source": "protectqube_agent"},
        }

        success, err, resp = self.send(recipient=url, title="Test", body="Test", data=test_payload, config=config)
        if success:
            return True, f"Webhook ping returned successfully from {url}!"
        return False, f"Webhook ping failed: {err}"

    def send(self, recipient: str, title: str, body: str, data: Dict[str, Any], config: Dict[str, Any]) -> Tuple[bool, str, Any]:
        url = (recipient or config.get("webhook_url", "")).strip()
        if not url:
            return False, "Missing webhook URL", None

        headers = {
            "Content-Type": "application/json",
            "User-Agent": "ProtectqubeAgent-Webhook/1.0",
        }
        auth_name = config.get("auth_header_name", "").strip()
        auth_val = config.get("auth_header_value", "").strip()
        if auth_name and auth_val:
            headers[auth_name] = auth_val

        payload = {
            "title": title,
            "body": body,
            "data": data,
        }

        try:
            with httpx.Client(timeout=10.0) as client:
                res = client.post(url, json=payload, headers=headers)
                if res.status_code in [200, 201, 202, 204]:
                    try:
                        res_json = res.json()
                    except Exception:
                        res_json = {"status_code": res.status_code, "text": res.text}
                    return True, "", res_json
                return False, f"HTTP {res.status_code}: {res.text}", None
        except Exception as e:
            return False, str(e), None
