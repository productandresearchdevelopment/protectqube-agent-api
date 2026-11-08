import logging
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from app.models.notification_models import NotificationDestination
from app.services.notification.providers.base import BaseNotificationProvider
from app.services.notification.providers.in_app import InAppProvider
from app.services.notification.providers.discord import DiscordProvider
from app.services.notification.providers.telegram import TelegramProvider
from app.services.notification.providers.whatsapp import WhatsAppProvider
from app.services.notification.providers.email import EmailProvider
from app.services.notification.providers.slack import SlackProvider

logger = logging.getLogger(__name__)


class IntegrationRegistry:
    def __init__(self):
        self._providers: Dict[str, BaseNotificationProvider] = {}
        self.register(InAppProvider())
        self.register(DiscordProvider())
        self.register(TelegramProvider())
        self.register(WhatsAppProvider())
        self.register(EmailProvider())
        self.register(SlackProvider())

    def register(self, provider: BaseNotificationProvider):
        self._providers[provider.provider_key] = provider

    def get(self, provider_key: str) -> Optional[BaseNotificationProvider]:
        return self._providers.get(provider_key)

    def list_providers(self, db: Session) -> List[Dict[str, Any]]:
        """
        Lists third-party integration providers matching the ERP integration configuration screen.
        Excludes native internal providers such as in_app.
        """
        destinations = {d.provider_key: d for d in db.query(NotificationDestination).all()}
        result = []

        preferred_order = ["discord", "telegram", "whatsapp", "email", "slack"]

        for key in preferred_order:
            p = self._providers.get(key)
            if not p:
                continue

            dest = destinations.get(key)
            status = "NOT_CONFIGURED"
            last_tested_at = None
            config_masked = {}
            dest_id = None

            if dest:
                status = dest.status
                last_tested_at = dest.last_tested_at.isoformat() if dest.last_tested_at else None
                dest_id = dest.id
                raw_cfg = dest.config or {}
                config_masked = {}
                for k, v in raw_cfg.items():
                    if any(s in k.lower() for s in ["token", "password", "secret", "key", "url"]) and v:
                        v_str = str(v)
                        config_masked[k] = (v_str[:6] + "••••" + v_str[-4:]) if len(v_str) > 12 else "••••••••"
                    else:
                        config_masked[k] = v

            result.append({
                "provider_key": p.provider_key,
                "display_name": p.display_name,
                "description": p.description,
                "icon": p.icon,
                "status": status,
                "destination_id": dest_id,
                "last_tested_at": last_tested_at,
                "schema": p.get_config_schema(),
                "config": config_masked,
            })

        return result


integration_registry = IntegrationRegistry()
