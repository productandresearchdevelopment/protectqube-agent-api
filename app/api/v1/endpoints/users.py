import logging
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import or_
from app.core.database import get_db
from app.core.security import get_password_hash
from app.models.base_models import User, Role
from app.schemas.user import UserCreate, UserUpdate
from app.api.deps import get_current_user
from app.core.rbac import require_permission

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/users", tags=["Users"], dependencies=[Depends(require_permission("/configuration"))])


@router.get("")
def list_users(
    search: Optional[str] = Query(None),
    role_id: Optional[str] = Query(None),
    include_deleted: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(User)
    if not include_deleted:
        query = query.filter(User.deleted_at.is_(None))

    if role_id and role_id.strip() and role_id.lower() != "all":
        query = query.filter(User.role_id == role_id.strip())

    if search and search.strip():
        term = f"%{search.strip()}%"
        query = query.filter(
            or_(
                User.name.ilike(term),
                User.username.ilike(term),
                User.email.ilike(term),
                User.phone.ilike(term),
            )
        )

    users = query.order_by(User.created_at.desc()).all()
    results = []
    for u in users:
        results.append({
            "id": u.id,
            "name": u.name,
            "username": u.username,
            "email": u.email,
            "phone": u.phone,
            "address": u.address,
            "role_id": u.role_id,
            "role_name": u.role.name if u.role else None,
            "role_alias": u.role.alias if u.role else None,
            "role_color": u.role.color if u.role else "#3b82f6",
            "role": {
                "id": u.role.id,
                "name": u.role.name,
                "alias": u.role.alias,
                "color": u.role.color,
            } if u.role else None,
            "email_verified": u.email_verified,
            "last_login": u.last_login,
            "created_at": u.created_at,
            "updated_at": u.updated_at,
            "deleted_at": u.deleted_at,
        })

    return {"status": True, "data": results}


@router.post("")
def create_user(
    request: UserCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    existing = db.query(User).filter(
        (User.username.ilike(request.username.strip())) | (User.email.ilike(request.email.strip())),
        User.deleted_at.is_(None),
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Username or Email already registered")

    role = db.query(Role).filter(Role.id == request.role_id, Role.deleted_at.is_(None)).first()
    if not role:
        raise HTTPException(status_code=400, detail="Selected role not found")

    new_user = User(
        name=request.name.strip(),
        username=request.username.strip(),
        email=request.email.strip(),
        password=get_password_hash(request.password),
        phone=request.phone.strip() if request.phone else None,
        address=request.address.strip() if request.address else None,
        role_id=request.role_id,
        email_verified=True,
        created_by=current_user.id,
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return {
        "status": True,
        "message": "User created successfully",
        "data": {
            "id": new_user.id,
            "name": new_user.name,
            "username": new_user.username,
            "email": new_user.email,
            "phone": new_user.phone,
            "address": new_user.address,
            "role_id": new_user.role_id,
            "role_name": role.name,
            "role_alias": role.alias,
            "role_color": role.color,
        },
    }


@router.get("/{user_id}")
def get_user(
    user_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    user = db.query(User).filter(User.id == user_id, User.deleted_at.is_(None)).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return {
        "status": True,
        "data": {
            "id": user.id,
            "name": user.name,
            "username": user.username,
            "email": user.email,
            "phone": user.phone,
            "address": user.address,
            "role_id": user.role_id,
            "role_name": user.role.name if user.role else None,
            "role_alias": user.role.alias if user.role else None,
            "role_color": user.role.color if user.role else "#3b82f6",
            "role": {
                "id": user.role.id,
                "name": user.role.name,
                "alias": user.role.alias,
                "color": user.role.color,
            } if user.role else None,
            "last_login": user.last_login,
            "created_at": user.created_at,
            "updated_at": user.updated_at,
        },
    }


@router.put("/{user_id}")
def update_user(
    user_id: str,
    request: UserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    user = db.query(User).filter(User.id == user_id, User.deleted_at.is_(None)).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if request.username and request.username.strip() != user.username:
        dup = db.query(User).filter(User.username.ilike(request.username.strip()), User.id != user_id, User.deleted_at.is_(None)).first()
        if dup:
            raise HTTPException(status_code=400, detail="Username already in use")
        user.username = request.username.strip()

    if request.email and request.email.strip() != user.email:
        dup = db.query(User).filter(User.email.ilike(request.email.strip()), User.id != user_id, User.deleted_at.is_(None)).first()
        if dup:
            raise HTTPException(status_code=400, detail="Email already in use")
        user.email = request.email.strip()

    if request.name is not None:
        user.name = request.name.strip()
    if request.phone is not None:
        user.phone = request.phone.strip() if request.phone else None
    if request.address is not None:
        user.address = request.address.strip() if request.address else None
    if request.role_id is not None:
        role = db.query(Role).filter(Role.id == request.role_id, Role.deleted_at.is_(None)).first()
        if not role:
            raise HTTPException(status_code=400, detail="Selected role not found")
        user.role_id = request.role_id

    if request.password and request.password.strip():
        user.password = get_password_hash(request.password.strip())

    user.updated_by = current_user.id
    user.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(user)

    return {
        "status": True,
        "message": "User updated successfully",
        "data": {
            "id": user.id,
            "name": user.name,
            "username": user.username,
            "email": user.email,
            "phone": user.phone,
            "address": user.address,
            "role_id": user.role_id,
            "role_name": user.role.name if user.role else None,
            "role_alias": user.role.alias if user.role else None,
            "role_color": user.role.color if user.role else "#3b82f6",
        },
    }


@router.delete("/{user_id}")
def delete_user(
    user_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    user = db.query(User).filter(User.id == user_id, User.deleted_at.is_(None)).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if user.id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot delete your own account")

    if user.username.lower() == "admin":
        raise HTTPException(status_code=400, detail="Cannot delete default admin account")

    user.deleted_at = datetime.utcnow()
    user.deleted_by = current_user.id
    db.commit()

    return {"status": True, "message": "User deleted successfully"}
