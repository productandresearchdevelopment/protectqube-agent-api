from typing import Optional
from datetime import datetime
from pydantic import BaseModel
from app.models.base_models import EmailVerificationStatus


class UserBase(BaseModel):
    name: str
    username: str
    email: str
    phone: Optional[str] = None
    address: Optional[str] = None
    role_id: str


class UserCreate(UserBase):
    password: str


class UserUpdate(BaseModel):
    name: Optional[str] = None
    username: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    role_id: Optional[str] = None
    password: Optional[str] = None


class UserResponse(UserBase):
    id: str
    avatar_id: Optional[str] = None
    last_login: Optional[datetime] = None
    email_verified: bool
    email_verification_status: EmailVerificationStatus
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
