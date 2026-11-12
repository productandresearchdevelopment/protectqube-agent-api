import logging
import uuid
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import or_, func

from app.core.database import get_db
from app.models.base_models import Client, Device, User
from app.schemas.client import ClientCreate, ClientUpdate
from app.api.deps import get_current_user
from app.core.rbac import require_permission

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/clients", tags=["Clients"], dependencies=[Depends(require_permission("/configuration"))])


@router.get("")
def list_clients(
    search: Optional[str] = Query(None),
    is_active: Optional[bool] = Query(None),
    include_deleted: bool = Query(False),
    all: bool = Query(False, description="Return all without pagination for dropdowns"),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    search_str = search if isinstance(search, str) else None
    active_bool = is_active if isinstance(is_active, bool) else None
    all_bool = all if isinstance(all, bool) else False
    page_num = page if isinstance(page, int) else 1
    page_size_num = page_size if isinstance(page_size, int) else 25

    query = db.query(Client)
    if not include_deleted:
        query = query.filter(Client.deleted_at.is_(None))

    if active_bool is not None:
        query = query.filter(Client.is_active == active_bool)
    elif not include_deleted:
        # Default: only show active clients
        query = query.filter(Client.is_active.is_(True))

    if search_str and search_str.strip():
        term = f"%{search_str.strip()}%"
        query = query.filter(
            or_(
                Client.name.ilike(term),
                Client.code.ilike(term),
            )
        )

    total = query.count()

    if all_bool:
        clients = query.order_by(Client.name.asc()).all()
    else:
        offset = (page_num - 1) * page_size_num
        clients = query.order_by(Client.name.asc()).offset(offset).limit(page_size_num).all()

    # Pre-count devices per client
    device_counts = dict(
        db.query(Device.client_id, func.count(Device.id))
        .filter(Device.client_id.isnot(None))
        .group_by(Device.client_id)
        .all()
    )

    results = []
    for c in clients:
        results.append({
            "id": str(c.id),
            "name": c.name,
            "code": c.code,
            "is_active": c.is_active,
            "devices_count": device_counts.get(c.id, 0),
            "created_at": c.created_at,
            "updated_at": c.updated_at,
            "deleted_at": c.deleted_at,
        })

    return {
        "status": True,
        "data": results,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.post("", status_code=status.HTTP_201_CREATED)
def create_client(
    payload: ClientCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Check duplicate code if provided
    if payload.code and payload.code.strip():
        existing = db.query(Client).filter(
            Client.code.ilike(payload.code.strip()),
            Client.deleted_at.is_(None)
        ).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Client with code '{payload.code}' already exists."
            )

    client_id = uuid.uuid4()
    client = Client(
        id=client_id,
        name=payload.name.strip(),
        code=payload.code.strip().upper() if payload.code else None,
        is_active=payload.is_active,
        created_by=current_user.id if hasattr(current_user, "id") else None,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(client)
    db.commit()
    db.refresh(client)

    return {
        "status": True,
        "message": "Client created successfully",
        "data": {
            "id": str(client.id),
            "name": client.name,
            "code": client.code,
            "is_active": client.is_active,
            "devices_count": 0,
            "created_at": client.created_at,
        }
    }


@router.get("/{client_id}")
def get_client(
    client_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        c_uuid = uuid.UUID(client_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid client UUID format")

    client = db.query(Client).filter(Client.id == c_uuid, Client.deleted_at.is_(None)).first()
    if not client:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")

    dev_count = db.query(Device).filter(Device.client_id == c_uuid).count()

    return {
        "status": True,
        "data": {
            "id": str(client.id),
            "name": client.name,
            "code": client.code,
            "is_active": client.is_active,
            "devices_count": dev_count,
            "created_at": client.created_at,
            "updated_at": client.updated_at,
        }
    }


@router.put("/{client_id}")
def update_client(
    client_id: str,
    payload: ClientUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        c_uuid = uuid.UUID(client_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid client UUID format")

    client = db.query(Client).filter(Client.id == c_uuid, Client.deleted_at.is_(None)).first()
    if not client:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")

    if payload.code is not None and payload.code.strip():
        existing = db.query(Client).filter(
            Client.code.ilike(payload.code.strip()),
            Client.id != c_uuid,
            Client.deleted_at.is_(None)
        ).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Client with code '{payload.code}' already exists."
            )
        client.code = payload.code.strip().upper()
    elif payload.code == "":
        client.code = None

    if payload.name is not None:
        client.name = payload.name.strip()

    if payload.is_active is not None:
        client.is_active = payload.is_active

    client.updated_at = datetime.utcnow()
    client.updated_by = current_user.id if hasattr(current_user, "id") else None

    db.commit()
    db.refresh(client)

    return {
        "status": True,
        "message": "Client updated successfully",
        "data": {
            "id": str(client.id),
            "name": client.name,
            "code": client.code,
            "is_active": client.is_active,
            "updated_at": client.updated_at,
        }
    }


@router.delete("/{client_id}")
def delete_client(
    client_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        c_uuid = uuid.UUID(client_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid client UUID format")

    client = db.query(Client).filter(Client.id == c_uuid, Client.deleted_at.is_(None)).first()
    if not client:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")

    # Soft delete client and detach from devices
    db.query(Device).filter(Device.client_id == c_uuid).update({"client_id": None}, synchronize_session=False)

    client.deleted_at = datetime.utcnow()
    client.deleted_by = current_user.id if hasattr(current_user, "id") else None
    client.is_active = False

    db.commit()

    return {"status": True, "message": "Client deleted successfully"}
