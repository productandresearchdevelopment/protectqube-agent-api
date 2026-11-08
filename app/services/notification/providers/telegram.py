import logging
from typing import Dict, Any, Tuple
import httpx
from app.services.notification.providers.base import BaseNotificationProvider

logger = logging.getLogger(__name__)


class TelegramProvider(BaseNotificationProvider):
    provider_key = "telegram"
    display_name = "Telegram"
    description = "Send notifications via Telegram bot"
    icon = "Send"

    def get_config_schema(self) -> Dict[str, Any]:
        return {
            "fields": [
                {
                    "name": "bot_token",
                    "label": "Bot Token",
                    "type": "password",
                    "required": True,
                    "placeholder": "123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ",
                    "help": "Get this token from @BotFather on Telegram.",
                },
            ]
        }

    def test_connection(self, config: Dict[str, Any]) -> Tuple[bool, str]:
        bot_token = config.get("bot_token", "").strip()

        if not bot_token:
            return False, "Telegram Bot Token is required."

        url = f"https://api.telegram.org/bot{bot_token}/getMe"

        try:
            with httpx.Client(timeout=10.0) as client:
                res = client.get(url)
                try:
                    data = res.json()
                except Exception:
                    data = {}

                if res.status_code == 200 and data.get("ok"):
                    bot_name = data.get("result", {}).get("first_name", "Bot")
                    bot_user = data.get("result", {}).get("username", "")
                    return True, f"Connected to Telegram Bot @{bot_user} ({bot_name}) successfully!"
                elif res.status_code == 401 or data.get("error_code") == 401:
                    return False, "Invalid Telegram Bot Token (HTTP 401 Unauthorized). Please verify the token copied from @BotFather."
                elif res.status_code == 404:
                    return False, "Telegram API endpoint not found. Please verify the Bot Token format from @BotFather."

                desc = data.get("description", "")
                if desc:
                    return False, f"Telegram Bot verification failed: {desc}."
                return False, f"Telegram API responded with HTTP status {res.status_code}."
        except httpx.ConnectTimeout:
            return False, "Connection to Telegram timed out. Check your server's network connection."
        except httpx.ConnectError:
            return False, "Unable to connect to Telegram servers (api.telegram.org). Check your network connection."
        except Exception as e:
            logger.error(f"[TelegramProvider] Test error: {e}")
            return False, f"Failed to verify Telegram Bot: {str(e)}"

    def send(self, recipient: str, title: str, body: str, data: Dict[str, Any], config: Dict[str, Any]) -> Tuple[bool, str, Any]:
        bot_token = config.get("bot_token", "").strip()
        target_chat = recipient.strip() if recipient else ""

        if not bot_token or not target_chat:
            return False, "Missing bot_token or target chat_id", None

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

        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        payload = {
            "chat_id": target_chat,
            "text": msg,
        }

        try:
            with httpx.Client(timeout=10.0) as client:
                res = client.post(url, json=payload)
                res_data = res.json()
                if res.status_code == 200 and res_data.get("ok"):
                    return True, "", res_data
                return False, res_data.get("description", f"Telegram error {res.status_code}"), res_data
        except Exception as e:
            return False, str(e), None
