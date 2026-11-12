from typing import Optional
from datetime import datetime
from pydantic import BaseModel, Field


class ClientBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255, description="Corporate / Client name")
    code: Optional[str] = Field(None, max_length=100, description="Short code / alias")
    is_active: bool = Field(True, description="Active status")


class ClientCreate(ClientBase):
    pass


class ClientUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    code: Optional[str] = Field(None, max_length=100)
    is_active: Optional[bool] = None


class ClientResponse(ClientBase):
    id: str
    devices_count: int = 0
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True
