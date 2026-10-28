from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.security import get_password_hash
from app.models.base_models import User
from app.schemas.user import UserCreate, UserUpdate
from app.api.deps import get_current_user

router = APIRouter(prefix="/users", tags=["Users"])


@router.get("")
def list_users(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    users = db.query(User).filter(User.deleted_at.is_(None)).all()
    return {"status": True, "data": users}


@router.post("")
def create_user(request: UserCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    existing = db.query(User).filter(
        (User.username == request.username) | (User.email == request.email),
        User.deleted_at.is_(None),
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Username or Email already registered")

    user_data = request.model_dump()
    user_data["password"] = get_password_hash(user_data["password"])
    new_user = User(**user_data)
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return {"status": True, "data": new_user}


@router.get("/{user_id}")
def get_user(user_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    user = db.query(User).filter(User.id == user_id, User.deleted_at.is_(None)).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return {"status": True, "data": user}
