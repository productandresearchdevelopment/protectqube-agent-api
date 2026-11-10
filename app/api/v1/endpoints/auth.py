from datetime import datetime
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.security import verify_password, create_access_token, create_refresh_token, decode_token
from app.core.rbac import is_privileged_role
from app.models.base_models import User, RoleModule, Module
from app.schemas.auth import LoginRequest, RefreshTokenRequest
from app.api.deps import get_current_user

router = APIRouter(prefix="/auth", tags=["Auth"])


def get_user_permissions(user: User, db: Session) -> List[str]:
    """Retrieve allowed module route paths and names for user's role."""
    if is_privileged_role(user.role):
        all_modules = db.query(Module).filter(Module.deleted_at.is_(None)).all()
        perms = set()
        for m in all_modules:
            if m.route:
                perms.add(m.route)
            if m.name:
                perms.add(m.name)
        perms.add("*")
        return list(perms)

    if not user.role_id:
        return []

    role_modules = (
        db.query(RoleModule)
        .filter(
            RoleModule.role_id == user.role_id,
            RoleModule.checked.is_(True),
            RoleModule.deleted_at.is_(None),
        )
        .all()
    )
    module_ids = [rm.module_id for rm in role_modules]
    if not module_ids:
        return []

    modules = db.query(Module).filter(Module.id.in_(module_ids), Module.deleted_at.is_(None)).all()
    perms = set()
    for m in modules:
        if m.route:
            perms.add(m.route)
        if m.name:
            perms.add(m.name)
    return list(perms)


def serialize_user_profile(user: User, permissions: List[str]) -> dict:
    return {
        "id": user.id,
        "name": user.name,
        "username": user.username,
        "email": user.email,
        "phone": user.phone,
        "address": user.address,
        "role_id": user.role_id,
        "role": {
            "id": user.role.id,
            "name": user.role.name,
            "alias": user.role.alias,
            "color": user.role.color,
        }
        if user.role
        else None,
        "role_name": user.role.name if user.role else None,
        "role_alias": user.role.alias if user.role else None,
        "permissions": permissions,
    }


@router.post("/login")
def login(request: LoginRequest, db: Session = Depends(get_db)):
    user = (
        db.query(User)
        .filter(
            (User.username == request.username_or_email) | (User.email == request.username_or_email),
            User.deleted_at.is_(None),
        )
        .first()
    )

    if not user or not verify_password(request.password, user.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )

    user.last_login = datetime.utcnow()
    db.commit()

    import uuid
    session_id = str(uuid.uuid4())
    access_token = create_access_token(user.id, session_id=session_id)
    refresh_token = create_refresh_token(user.id)

    permissions = get_user_permissions(user, db)

    return {
        "status": True,
        "message": "Login successful",
        "data": {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "session_id": session_id,
            "token_type": "bearer",
            "user": serialize_user_profile(user, permissions),
        },
    }


@router.post("/refresh-token")
def refresh_token(request: RefreshTokenRequest, db: Session = Depends(get_db)):
    payload = decode_token(request.refresh_token)
    if not payload or payload.get("type") != "refresh":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    user_id = payload.get("sub")
    user = db.query(User).filter(User.id == user_id, User.deleted_at.is_(None)).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    new_access_token = create_access_token(user.id)
    new_refresh_token = create_refresh_token(user.id)

    return {
        "status": True,
        "message": "Token refreshed successfully",
        "data": {
            "access_token": new_access_token,
            "refresh_token": new_refresh_token,
            "token_type": "bearer",
        },
    }


@router.get("/me")
def get_profile(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    permissions = get_user_permissions(current_user, db)
    return {
        "status": True,
        "data": serialize_user_profile(current_user, permissions),
    }


@router.post("/logout")
def logout(current_user: User = Depends(get_current_user)):
    return {
        "status": True,
        "message": "Logged out successfully",
    }
