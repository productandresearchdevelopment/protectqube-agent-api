import logging
from typing import Dict, Any, Tuple
import httpx
from app.services.notification.providers.base import BaseNotificationProvider

logger = logging.getLogger(__name__)


class SlackProvider(BaseNotificationProvider):
    provider_key = "slack"
    display_name = "Slack"
    description = "Send notifications to Slack channels"
    icon = "Slack"

    def get_config_schema(self) -> Dict[str, Any]:
        return {
            "fields": [
                {
                    "name": "webhook_url",
                    "label": "Slack Webhook URL",
                    "type": "password",
                    "required": True,
                    "placeholder": "https://hooks.slack.com/services/...",
                    "help": "Incoming Webhook URL from your Slack App configuration.",
                },
                {
                    "name": "channel",
                    "label": "Channel (Optional)",
                    "type": "text",
                    "required": False,
                    "placeholder": "#incidents or #alerts",
                    "help": "Override default channel if supported by your Slack webhook.",
                },
            ]
        }

    def test_connection(self, config: Dict[str, Any]) -> Tuple[bool, str]:
        webhook_url = config.get("webhook_url", "").strip()
        if not webhook_url:
            return False, "Slack Webhook URL is required."

        if not webhook_url.startswith("https://hooks.slack.com/"):
            return False, "Invalid Slack Webhook URL. It must begin with https://hooks.slack.com/services/..."

        payload = {
            "text": "*ProtectQube Test Alert*\nSlack integration connected successfully!",
        }
        channel = config.get("channel", "").strip()
        if channel:
            payload["channel"] = channel

        try:
            with httpx.Client(timeout=10.0) as client:
                res = client.post(webhook_url, json=payload)
                if res.status_code == 200 and res.text == "ok":
                    return True, "Connected to Slack channel successfully!"
                elif res.text == "channel_not_found":
                    return False, "Slack channel not found. Ensure the channel name is correct and the bot is invited to that channel."
                elif res.text == "invalid_token" or res.status_code in [401, 403]:
                    return False, "Slack Webhook URL is invalid or has been revoked. Create a new Incoming Webhook in your Slack App."
                elif res.text == "action_prohibited":
                    return False, "Action prohibited by your Slack workspace settings."
                elif res.status_code == 404:
                    return False, "Slack Webhook URL not found (HTTP 404). Ensure the full URL was copied correctly."
                return False, f"Slack responded with HTTP status {res.status_code}: {res.text}"
        except httpx.ConnectTimeout:
            return False, "Connection to Slack timed out. Check your server's network connection."
        except httpx.ConnectError:
            return False, "Unable to reach Slack servers. Check your server's network connection."
        except Exception as e:
            logger.error(f"[SlackProvider] Test error: {e}")
            return False, f"Failed to connect to Slack: {str(e)}"

    def send(self, recipient: str, title: str, body: str, data: Dict[str, Any], config: Dict[str, Any]) -> Tuple[bool, str, Any]:
        webhook_url = config.get("webhook_url", "").strip()
        if not webhook_url:
            return False, "Missing Slack Webhook URL", None

        dev_id = data.get("device_id", "Unknown Device")
        metric = data.get("metric", "")
        duration = data.get("duration_str", "")

        text = f"*{title}*\n{body}\n• *Device:* `{dev_id}`"
        if metric:
            text += f"\n• *Metric:* {metric}"
        if duration:
            text += f"\n• *Duration:* {duration}"

        payload = {"text": text}
        channel = config.get("channel", "").strip()
        if channel:
            payload["channel"] = channel

        try:
            with httpx.Client(timeout=10.0) as client:
                res = client.post(webhook_url, json=payload)
                if res.status_code == 200 and res.text == "ok":
                    return True, "", {"status": "DELIVERED"}
                return False, f"Slack error {res.status_code}: {res.text}", None
        except Exception as e:
            return False, str(e), None
