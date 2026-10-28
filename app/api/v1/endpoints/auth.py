from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.security import verify_password, create_access_token, create_refresh_token, decode_token
from app.models.base_models import User, RoleModule, Module
from app.schemas.auth import LoginRequest, RefreshTokenRequest
from app.api.deps import get_current_user

router = APIRouter(prefix="/auth", tags=["Auth"])


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

    access_token = create_access_token(user.id)
    refresh_token = create_refresh_token(user.id)

    return {
        "status": True,
        "message": "Login successful",
        "data": {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "user": {
                "id": user.id,
                "name": user.name,
                "username": user.username,
                "email": user.email,
                "role_id": user.role_id,
            },
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
    role_modules = (
        db.query(RoleModule)
        .filter(RoleModule.role_id == current_user.role_id, RoleModule.checked.is_(True))
        .all()
    )
    module_ids = [rm.module_id for rm in role_modules]
    modules = db.query(Module).filter(Module.id.in_(module_ids)).all() if module_ids else []
    permissions = [m.route for m in modules if m.route]

    return {
        "status": True,
        "data": {
            "id": current_user.id,
            "name": current_user.name,
            "username": current_user.username,
            "email": current_user.email,
            "phone": current_user.phone,
            "address": current_user.address,
            "role_id": current_user.role_id,
            "role_name": current_user.role.name if current_user.role else None,
            "role_alias": current_user.role.alias if current_user.role else None,
            "permissions": permissions,
        },
    }


@router.post("/logout")
def logout(current_user: User = Depends(get_current_user)):
    return {
        "status": True,
        "message": "Logged out successfully",
    }
