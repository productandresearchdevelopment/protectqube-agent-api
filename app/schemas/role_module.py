from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel


class RoleBase(BaseModel):
    name: str
    alias: str
    color: str = "#3b82f6"
    description: Optional[str] = None


class RoleCreate(RoleBase):
    pass


class RoleUpdate(BaseModel):
    name: Optional[str] = None
    alias: Optional[str] = None
    color: Optional[str] = None
    description: Optional[str] = None


class RoleResponse(RoleBase):
    id: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ModuleTypeResponse(BaseModel):
    id: str
    name: str
    icon: Optional[str] = None
    description: Optional[str] = None

    class Config:
        from_attributes = True


class ModuleBase(BaseModel):
    module_type_id: str
    parent_id: Optional[int] = None
    path: Optional[str] = None
    name: str
    icon: Optional[str] = None
    route: Optional[str] = None
    description: Optional[str] = None


class ModuleResponse(ModuleBase):
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class RoleModulePermissionItem(BaseModel):
    module_id: int
    checked: bool


class RoleModulePermissionUpdate(BaseModel):
    permissions: List[RoleModulePermissionItem]
