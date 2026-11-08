import logging
from typing import Dict, Any, Tuple
import httpx
from app.services.notification.providers.base import BaseNotificationProvider

logger = logging.getLogger(__name__)


class DiscordProvider(BaseNotificationProvider):
    provider_key = "discord"
    display_name = "Discord"
    description = "Send notifications to Discord channels"
    icon = "MessageSquare"

    def get_config_schema(self) -> Dict[str, Any]:
        return {
            "fields": [
                {
                    "name": "webhook_url",
                    "label": "Discord Webhook URL",
                    "type": "password",
                    "required": True,
                    "placeholder": "https://discord.com/api/webhooks/...",
                    "help": "Create a webhook in your Discord channel settings.",
                },
                {
                    "name": "bot_username",
                    "label": "Bot Username (Optional)",
                    "type": "text",
                    "required": False,
                    "placeholder": "ProtectQube Alert Bot",
                    "help": "Custom username to display when sending messages.",
                },
            ]
        }

    def test_connection(self, config: Dict[str, Any]) -> Tuple[bool, str]:
        webhook_url = config.get("webhook_url", "").strip()
        if not webhook_url:
            return False, "Discord Webhook URL is required."

        if not webhook_url.startswith("https://discord.com/api/webhooks/") and not webhook_url.startswith("https://discordapp.com/api/webhooks/"):
            return False, "Invalid Discord Webhook URL. It must begin with https://discord.com/api/webhooks/..."

        payload = {
            "content": "**ProtectQube Test Alert**\nDiscord integration connected successfully!",
        }
        bot_username = config.get("bot_username", "").strip()
        if bot_username:
            payload["username"] = bot_username

        try:
            with httpx.Client(timeout=10.0) as client:
                res = client.post(webhook_url, json=payload)
                if res.status_code in [200, 204]:
                    return True, "Connected to Discord channel successfully!"
                elif res.status_code == 404:
                    return False, "Discord webhook not found (HTTP 404). The webhook may have been deleted from your Discord channel."
                elif res.status_code in [401, 403]:
                    return False, "Discord webhook access denied (HTTP 401/403). The webhook token is invalid."
                elif res.status_code == 429:
                    return False, "Rate limit exceeded on Discord. Please wait a moment before trying again."
                return False, f"Discord responded with HTTP status {res.status_code}."
        except httpx.ConnectTimeout:
            return False, "Connection to Discord timed out. Check your server's network connection."
        except httpx.ConnectError:
            return False, "Unable to reach Discord servers. Check your server's network connection."
        except Exception as e:
            logger.error(f"[DiscordProvider] Test error: {e}")
            return False, f"Failed to connect to Discord: {str(e)}"

    def send(self, recipient: str, title: str, body: str, data: Dict[str, Any], config: Dict[str, Any]) -> Tuple[bool, str, Any]:
        webhook_url = config.get("webhook_url", "").strip()
        if not webhook_url:
            return False, "Missing Discord Webhook URL", None

        dev_id = data.get("device_id", "Unknown Device")
        metric = data.get("metric", "")
        duration = data.get("duration_str", "")
        severity = data.get("severity", "WARNING")

        color = 0x00c875 if severity == "INFO" else 0xe2445c if severity == "CRITICAL" else 0xfdab3d

        embed = {
            "title": title,
            "description": body,
            "color": color,
            "fields": [
                {"name": "Device", "value": f"`{dev_id}`", "inline": True},
            ],
            "footer": {"text": f"ProtectQube • {data.get('timestamp', '')}"}
        }
        if metric:
            embed["fields"].append({"name": "Metric", "value": metric, "inline": True})
        if duration:
            embed["fields"].append({"name": "Duration", "value": duration, "inline": True})

        payload = {
            "embeds": [embed]
        }
        bot_username = config.get("bot_username", "").strip()
        if bot_username:
            payload["username"] = bot_username

        try:
            with httpx.Client(timeout=10.0) as client:
                res = client.post(webhook_url, json=payload)
                if res.status_code in [200, 204]:
                    return True, "", {"status": "DELIVERED"}
                return False, f"Discord error {res.status_code}: {res.text}", None
        except Exception as e:
            return False, str(e), None
