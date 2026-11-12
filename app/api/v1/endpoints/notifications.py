from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models.auth_models import Role, User
from app.models.notification_models import (
    Notification,
    NotificationEvent,
    NotificationTarget,
)
from app.services.notification.notification_service import notification_service
from app.services.notification.destination_sync import (
    sync_telegram_destinations,
    sync_whatsapp_destinations,
)
from app.core.rbac import require_permission

router = APIRouter(prefix="/notifications", tags=["Notifications"])


def to_iso_utc(dt: Optional[datetime]) -> Optional[str]:
    if not dt:
        return None
    iso = dt.isoformat()
    if not iso.endswith("Z") and "+" not in iso:
        return f"{iso}Z"
    return iso


class NotificationEventCreate(BaseModel):
    event_code: str
    name: str
    category: str = "custom"
    description: Optional[str] = None
    channels: List[Dict[str, Any]] = []


class NotificationEventUpdate(BaseModel):
    name: Optional[str] = None
    category: Optional[str] = None
    description: Optional[str] = None
    channels: Optional[List[Dict[str, Any]]] = None


@router.get("")
def list_notifications(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    unread_only: bool = Query(False),
    read_status: Optional[str] = Query(None),
    severity: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    res = notification_service.get_notifications(
        db=db,
        page=page,
        limit=limit,
        unread_only=unread_only,
        read_status=read_status,
        severity=severity,
        search=search,
    )

    return {
        "status": True,
        "total": res["total"],
        "unread_count": res["unread_count"],
        "page": page,
        "limit": limit,
        "data": [
            {
                "id": n.id,
                "event_code": n.event_code,
                "title": n.title,
                "body": n.body,
                "severity": n.severity,
                "is_read": n.is_read,
                "read_at": to_iso_utc(n.read_at),
                "data": n.data,
                "created_at": to_iso_utc(n.created_at),
            }
            for n in res["items"]
        ]
    }


@router.put("/{notification_id}/read")
def mark_notification_read(notification_id: str, db: Session = Depends(get_db)):
    notif = notification_service.mark_as_read(db, notification_id)
    if not notif:
        raise HTTPException(status_code=404, detail="Notification not found")
    return {"status": True, "message": "Notification marked as read"}


@router.put("/read-all")
def mark_all_read(db: Session = Depends(get_db)):
    notification_service.mark_all_as_read(db)
    return {"status": True, "message": "All notifications marked as read"}


@router.get("/recipients-options", dependencies=[Depends(require_permission("/configuration"))])
def get_recipients_options(db: Session = Depends(get_db)):
    roles = db.query(Role).filter(Role.deleted_at.is_(None)).all()
    roles_data = []
    for r in roles:
        count = db.query(User).filter(User.role_id == r.id, User.deleted_at.is_(None)).count()
        roles_data.append({
            "id": r.id,
            "name": r.name,
            "alias": r.alias,
            "user_count": count,
        })

    users = db.query(User).filter(User.deleted_at.is_(None)).all()
    users_data = []
    for u in users:
        users_data.append({
            "id": u.id,
            "name": u.name,
            "username": u.username,
            "email": u.email,
            "role_name": u.role.name if u.role else "",
        })

    return {
        "status": True,
        "data": {
            "roles": roles_data,
            "users": users_data,
        }
    }


@router.get("/events", dependencies=[Depends(require_permission("/configuration"))])
def list_notification_events(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    search: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    configured_only: Optional[bool] = Query(None),
    db: Session = Depends(get_db)
):
    query = db.query(NotificationEvent)
    if configured_only:
        from sqlalchemy.dialects.postgresql import JSONB
        from sqlalchemy import func
        query = query.filter(
            NotificationEvent.channels.isnot(None),
            func.jsonb_array_length(NotificationEvent.channels.cast(JSONB)) > 0
        )
    if category and category.upper() != "ALL":
        query = query.filter(NotificationEvent.category.ilike(category.strip()))
    if search and search.strip():
        s = f"%{search.strip()}%"
        query = query.filter(NotificationEvent.name.ilike(s))
    total = query.count()
    events = (
        query.order_by(NotificationEvent.category, NotificationEvent.name)
        .offset((page - 1) * limit)
        .limit(limit)
        .all()
    )
    return {
        "status": True,
        "total": total,
        "page": page,
        "limit": limit,
        "data": [
            {
                "id": e.id,
                "event_code": e.event_code,
                "name": e.name,
                "category": e.category,
                "description": e.description,
                "channels": e.channels or [],
                "created_at": to_iso_utc(e.created_at),
                "updated_at": to_iso_utc(e.updated_at),
            }
            for e in events
        ]
    }


@router.post("/events", dependencies=[Depends(require_permission("/configuration"))])
def create_notification_event(payload: NotificationEventCreate, db: Session = Depends(get_db)):
    existing = db.query(NotificationEvent).filter(NotificationEvent.event_code == payload.event_code.strip()).first()
    if existing:
        raise HTTPException(status_code=400, detail="Event code already exists")
    event = NotificationEvent(
        event_code=payload.event_code.strip(),
        name=payload.name.strip(),
        category=payload.category.strip(),
        description=payload.description,
        channels=payload.channels or [],
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return {
        "status": True,
        "message": "Notification rule created successfully",
        "data": {
            "id": event.id,
            "event_code": event.event_code,
            "name": event.name,
            "category": event.category,
            "description": event.description,
            "channels": event.channels or [],
            "created_at": to_iso_utc(event.created_at),
            "updated_at": to_iso_utc(event.updated_at),
        }
    }


@router.put("/events/{event_id}", dependencies=[Depends(require_permission("/configuration"))])
def update_notification_event(event_id: str, payload: NotificationEventUpdate, db: Session = Depends(get_db)):
    event = db.query(NotificationEvent).filter(NotificationEvent.id == event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Notification event not found")
    if payload.name is not None:
        event.name = payload.name.strip()
    if payload.category is not None:
        event.category = payload.category.strip()
    if payload.description is not None:
        event.description = payload.description
    if payload.channels is not None:
        event.channels = payload.channels
    db.commit()
    db.refresh(event)
    return {
        "status": True,
        "message": "Notification rule updated successfully",
        "data": {
            "id": event.id,
            "event_code": event.event_code,
            "name": event.name,
            "category": event.category,
            "description": event.description,
            "channels": event.channels or [],
            "created_at": to_iso_utc(event.created_at),
            "updated_at": to_iso_utc(event.updated_at),
        }
    }


@router.delete("/events/{event_id}", dependencies=[Depends(require_permission("/configuration"))])
def delete_notification_event(event_id: str, db: Session = Depends(get_db)):
    event = db.query(NotificationEvent).filter(NotificationEvent.id == event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Notification event not found")
    event.channels = []
    db.commit()
    return {"status": True, "message": "Notification rule deleted successfully"}


@router.get("/deliveries")
def list_notification_deliveries(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    status: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    res = notification_service.get_deliveries(
        db=db,
        page=page,
        limit=limit,
        status=status
    )
    return {
        "status": True,
        "total": res["total"],
        "page": page,
        "limit": limit,
        "data": [
            {
                "id": d.id,
                "notification_id": d.notification_id,
                "destination_id": d.destination_id,
                "channel_type": d.channel_type,
                "recipient": d.recipient,
                "status": d.status,
                "error_message": d.error_message,
                "response_payload": d.response_payload,
                "sent_at": to_iso_utc(d.sent_at),
            }
            for d in res["items"]
        ]
    }


class NotificationTargetCreate(BaseModel):
    provider_key: str
    external_id: str
    display_name: str
    type: Optional[str] = "chat"
    config: Optional[Dict[str, Any]] = None


class DestinationSyncPayload(BaseModel):
    provider_key: str


@router.get("/destinations")
def list_destinations(
    provider_key: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    query = db.query(NotificationTarget).filter(NotificationTarget.is_active == True)
    if provider_key:
        query = query.filter(NotificationTarget.provider_key == provider_key)
    targets = query.order_by(NotificationTarget.display_name).all()
    return {
        "status": True,
        "data": [
            {
                "id": t.id,
                "provider_key": t.provider_key,
                "external_id": t.external_id,
                "display_name": t.display_name,
                "type": t.type,
                "source": t.source,
                "config": t.config or {},
                "is_active": t.is_active,
                "last_synced_at": to_iso_utc(t.last_synced_at),
                "created_at": to_iso_utc(t.created_at),
            }
            for t in targets
        ]
    }


@router.post("/destinations")
def create_destination(
    payload: NotificationTargetCreate,
    db: Session = Depends(get_db)
):
    existing = db.query(NotificationTarget).filter(
        NotificationTarget.provider_key == payload.provider_key,
        NotificationTarget.external_id == payload.external_id.strip()
    ).first()

    if existing:
        existing.display_name = payload.display_name.strip()
        existing.type = payload.type or existing.type
        existing.is_active = True
        if payload.config:
            existing.config = payload.config
        db.commit()
        db.refresh(existing)
        return {
            "status": True,
            "message": "Destination updated successfully",
            "data": {
                "id": existing.id,
                "provider_key": existing.provider_key,
                "external_id": existing.external_id,
                "display_name": existing.display_name,
                "type": existing.type,
                "source": existing.source,
                "is_active": existing.is_active,
            }
        }

    target = NotificationTarget(
        provider_key=payload.provider_key,
        external_id=payload.external_id.strip(),
        display_name=payload.display_name.strip(),
        type=payload.type or "chat",
        source="manual",
        config=payload.config or {},
        is_active=True,
    )
    db.add(target)
    db.commit()
    db.refresh(target)
    return {
        "status": True,
        "message": "Destination added successfully",
        "data": {
            "id": target.id,
            "provider_key": target.provider_key,
            "external_id": target.external_id,
            "display_name": target.display_name,
            "type": target.type,
            "source": target.source,
            "is_active": target.is_active,
        }
    }


@router.delete("/destinations/{destination_id}")
def delete_destination(
    destination_id: str,
    db: Session = Depends(get_db)
):
    target = db.query(NotificationTarget).filter(NotificationTarget.id == destination_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="Destination target not found")
    db.delete(target)
    db.commit()
    return {"status": True, "message": "Destination deleted successfully"}


@router.post("/destinations/sync")
def sync_destinations(
    payload: DestinationSyncPayload,
    db: Session = Depends(get_db)
):
    if payload.provider_key == "telegram":
        success, msg, count = sync_telegram_destinations(db)
    elif payload.provider_key == "whatsapp":
        success, msg, count = sync_whatsapp_destinations(db)
    else:
        raise HTTPException(status_code=400, detail=f"Provider '{payload.provider_key}' does not support sync")

    if not success:
        raise HTTPException(status_code=400, detail=msg)

    return {
        "status": True,
        "message": msg,
        "count": count
    }
