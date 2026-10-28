from typing import Optional, List, Any
from pydantic import BaseModel


class LoginRequest(BaseModel):
    username_or_email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class UserProfileResponse(BaseModel):
    id: str
    name: str
    username: str
    email: str
    phone: Optional[str] = None
    address: Optional[str] = None
    role_id: str
    role_name: Optional[str] = None
    role_alias: Optional[str] = None
    permissions: List[str] = []


class RefreshTokenRequest(BaseModel):
    refresh_token: str
