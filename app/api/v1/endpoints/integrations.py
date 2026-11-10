from datetime import datetime
from typing import Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models.notification_models import NotificationDestination
from app.services.notification.registry import integration_registry
from app.services.notification.whatsapp_session import whatsapp_session_manager
from app.core.rbac import require_permission

router = APIRouter(prefix="/integrations", tags=["Integrations & Connected Apps"], dependencies=[Depends(require_permission("/configuration"))])


class ConnectProviderPayload(BaseModel):
    name: Optional[str] = None
    config: Dict[str, Any]


class WhatsAppPairPhonePayload(BaseModel):
    phone: str


@router.get("")
def list_integrations(db: Session = Depends(get_db)):
    providers = integration_registry.list_providers(db)
    return {
        "status": True,
        "data": providers
    }


@router.get("/whatsapp/status")
def get_whatsapp_status():
    status = whatsapp_session_manager.get_status()
    return {
        "status": True,
        "data": status
    }


@router.post("/whatsapp/qr")
def generate_whatsapp_qr():
    result = whatsapp_session_manager.request_qr()
    return {
        "status": True,
        "data": result
    }


@router.post("/whatsapp/pair-phone")
def pair_whatsapp_phone(payload: WhatsAppPairPhonePayload):
    try:
        code = whatsapp_session_manager.request_pairing_code(payload.phone)
        return {
            "status": True,
            "data": {
                "code": code,
                "phone": payload.phone
            }
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{provider_key}/connect")
def connect_provider(provider_key: str, payload: ConnectProviderPayload, db: Session = Depends(get_db)):
    provider = integration_registry.get(provider_key)
    if not provider:
        raise HTTPException(status_code=404, detail=f"Provider '{provider_key}' not found")

    dest = db.query(NotificationDestination).filter(NotificationDestination.provider_key == provider_key).first()
    name = payload.name or provider.display_name
    config = payload.config

    old_cfg = dest.config if dest and dest.config else {}
    merged_cfg = dict(old_cfg)
    for k, v in config.items():
        if str(v).startswith("••••"):
            continue
        merged_cfg[k] = v

    success, test_msg = provider.test_connection(merged_cfg)
    if not success:
        raise HTTPException(status_code=400, detail=test_msg)

    if not dest:
        dest = NotificationDestination(
            provider_key=provider_key,
            name=name,
            config=merged_cfg,
            status="CONNECTED",
            last_tested_at=datetime.utcnow(),
        )
        db.add(dest)
    else:
        dest.name = name
        dest.config = merged_cfg
        dest.status = "CONNECTED"
        dest.last_tested_at = datetime.utcnow()
        dest.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(dest)

    return {
        "status": True,
        "message": f"{provider.display_name} verified and connected successfully",
        "data": {"id": dest.id, "status": dest.status}
    }


@router.post("/{provider_key}/disconnect")
def disconnect_provider(provider_key: str, db: Session = Depends(get_db)):
    if provider_key == "whatsapp":
        whatsapp_session_manager.disconnect()

    dest = db.query(NotificationDestination).filter(NotificationDestination.provider_key == provider_key).first()
    if dest:
        dest.config = {}
        dest.status = "NOT_CONFIGURED"
        dest.updated_at = datetime.utcnow()
        db.commit()

    return {
        "status": True,
        "message": f"Provider '{provider_key}' disconnected successfully"
    }
