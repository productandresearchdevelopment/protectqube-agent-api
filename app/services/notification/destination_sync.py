from datetime import datetime
from typing import List, Dict, Any, Tuple
import httpx
from sqlalchemy.orm import Session
from app.models.notification_models import NotificationDestination, NotificationTarget
from app.services.notification.whatsapp_session import whatsapp_session_manager


def sync_telegram_destinations(db: Session) -> Tuple[bool, str, int]:
    dest = db.query(NotificationDestination).filter(
        NotificationDestination.provider_key == "telegram",
        NotificationDestination.status == "CONNECTED"
    ).first()

    if not dest or not dest.config:
        return False, "Telegram is not connected or configured.", 0

    bot_token = dest.config.get("bot_token", "").strip()
    if not bot_token:
        return False, "Telegram bot token is missing.", 0

    url = f"https://api.telegram.org/bot{bot_token}/getUpdates"
    try:
        with httpx.Client(timeout=10.0) as client:
            res = client.get(url)
            data = res.json()
    except Exception as e:
        return False, f"Failed to connect to Telegram getUpdates: {str(e)}", 0

    if not res.is_success or not data.get("ok"):
        desc = data.get("description", "Unknown Telegram error")
        return False, f"Telegram API error: {desc}", 0

    updates = data.get("result", [])
    chat_map: Dict[str, Dict[str, Any]] = {}

    for u in updates:
        chat = None
        if "message" in u and "chat" in u["message"]:
            chat = u["message"]["chat"]
        elif "edited_message" in u and "chat" in u["edited_message"]:
            chat = u["edited_message"]["chat"]
        elif "channel_post" in u and "chat" in u["channel_post"]:
            chat = u["channel_post"]["chat"]
        elif "edited_channel_post" in u and "chat" in u["edited_channel_post"]:
            chat = u["edited_channel_post"]["chat"]
        elif "my_chat_member" in u and "chat" in u["my_chat_member"]:
            chat = u["my_chat_member"]["chat"]

        if chat and "id" in chat:
            chat_map[str(chat["id"])] = chat

    synced_count = 0
    now = datetime.utcnow()

    for chat_id, chat in chat_map.items():
        chat_type = chat.get("type", "chat")
        dest_type = "chat"
        display_name = ""

        if chat_type == "private":
            dest_type = "chat"
            first_name = chat.get("first_name", "")
            last_name = chat.get("last_name", "")
            username = chat.get("username", "")
            full_name = f"{first_name} {last_name}".strip()
            if username:
                display_name = f"{full_name} (@{username})" if full_name else f"@{username}"
            else:
                display_name = full_name or f"Private Chat ({chat_id})"
        elif chat_type in ("group", "supergroup"):
            dest_type = "group"
            display_name = chat.get("title") or f"Group ({chat_id})"
        elif chat_type == "channel":
            dest_type = "channel"
            display_name = chat.get("title") or f"Channel ({chat_id})"
        else:
            dest_type = "chat"
            display_name = chat.get("title") or f"Chat ({chat_id})"

        target = db.query(NotificationTarget).filter(
            NotificationTarget.provider_key == "telegram",
            NotificationTarget.external_id == chat_id
        ).first()

        if not target:
            target = NotificationTarget(
                provider_key="telegram",
                external_id=chat_id,
                display_name=display_name,
                type=dest_type,
                source="sync",
                is_active=True,
                last_synced_at=now,
            )
            db.add(target)
            synced_count += 1
        else:
            target.display_name = display_name
            target.type = dest_type
            target.source = "sync"
            target.last_synced_at = now
            synced_count += 1

    db.commit()
    return True, f"Successfully synced {synced_count} destination(s) from Telegram", synced_count


def sync_whatsapp_destinations(db: Session) -> Tuple[bool, str, int]:
    is_logged_in = whatsapp_session_manager.ensure_connected(timeout_sec=5.0)
    if not is_logged_in:
        return False, "WhatsApp is not connected or logged in. Please scan QR or link device in Integrations.", 0

    client = getattr(whatsapp_session_manager, "_client", None)
    if not client or not client.is_logged_in:
        return False, "WhatsApp client session is not active.", 0

    synced_count = 0
    now = datetime.utcnow()

    existing_rows = db.query(NotificationTarget).filter(
        NotificationTarget.provider_key == "whatsapp"
    ).all()
    existing_map: Dict[str, NotificationTarget] = {t.external_id: t for t in existing_rows}

    def upsert_target(ext_id: str, disp_name: str, dest_type: str):
        nonlocal synced_count
        target = existing_map.get(ext_id)
        if not target:
            target = NotificationTarget(
                provider_key="whatsapp",
                external_id=ext_id,
                display_name=disp_name,
                type=dest_type,
                source="sync",
                is_active=True,
                last_synced_at=now,
            )
            db.add(target)
            existing_map[ext_id] = target
        else:
            target.display_name = disp_name
            target.type = dest_type
            target.source = "sync"
            target.is_active = True
            target.last_synced_at = now
        synced_count += 1

    try:
        if hasattr(client, "get_joined_groups"):
            groups = client.get_joined_groups()
            if groups:
                for g in groups:
                    jid_user = getattr(g.JID, "User", "")
                    jid_server = getattr(g.JID, "Server", "g.us")
                    jid_str = f"{jid_user}@{jid_server}" if jid_user else str(g.JID)
                    if not jid_str:
                        continue

                    existing_t = existing_map.get(jid_str)
                    name = (
                        getattr(getattr(g, "GroupName", None), "Name", None)
                        or getattr(g, "Name", None)
                        or (
                            existing_t.display_name
                            if existing_t and existing_t.display_name and not existing_t.display_name.startswith("WhatsApp Group (")
                            else None
                        )
                    )
                    if not name:
                        name = f"WhatsApp Group ({jid_user or jid_str})"

                    upsert_target(jid_str, name, "group")
    except Exception:
        pass

    try:
        import sqlite3
        import os
        db_path = getattr(whatsapp_session_manager, "db_path", "")
        if db_path and os.path.exists(db_path):
            conn = sqlite3.connect(db_path, timeout=5.0)
            cur = conn.cursor()
            cur.execute("""
                SELECT their_jid, first_name, full_name, push_name, business_name 
                FROM whatsmeow_contacts 
                WHERE their_jid LIKE '%@s.whatsapp.net' 
                  AND (COALESCE(full_name, '') != '' OR COALESCE(push_name, '') != '' OR COALESCE(business_name, '') != '')
                ORDER BY COALESCE(NULLIF(full_name, ''), NULLIF(push_name, ''), business_name) ASC
            """)
            contacts = cur.fetchall()
            conn.close()
            for r in contacts:
                jid_str = r[0]
                contact_name = r[2] or r[3] or r[4] or r[1] or jid_str.split("@")[0]
                if not jid_str or not contact_name:
                    continue
                upsert_target(jid_str, contact_name, "chat")
    except Exception:
        pass

    db.commit()
    return True, f"Successfully synced {synced_count} destination(s) from WhatsApp", synced_count

