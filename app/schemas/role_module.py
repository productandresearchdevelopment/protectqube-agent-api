from typing import Optional, List, Any
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
    user_count: Optional[int] = 0
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    deleted_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ModuleTypeBase(BaseModel):
    name: str
    icon: Optional[str] = None
    description: Optional[str] = None


class ModuleTypeCreate(ModuleTypeBase):
    pass


class ModuleTypeUpdate(BaseModel):
    name: Optional[str] = None
    icon: Optional[str] = None
    description: Optional[str] = None


class ModuleTypeResponse(ModuleTypeBase):
    id: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    deleted_at: Optional[datetime] = None

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


class ModuleCreate(ModuleBase):
    pass


class ModuleUpdate(BaseModel):
    module_type_id: Optional[str] = None
    parent_id: Optional[int] = None
    path: Optional[str] = None
    name: Optional[str] = None
    icon: Optional[str] = None
    route: Optional[str] = None
    description: Optional[str] = None


class ModuleResponse(ModuleBase):
    id: int
    module_type: Optional[ModuleTypeResponse] = None
    parent_name: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    deleted_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class RoleModulePermissionItem(BaseModel):
    module_id: int
    checked: bool


class RoleModulePermissionUpdate(BaseModel):
    permissions: List[RoleModulePermissionItem]


class RoleModuleSingleUpdate(BaseModel):
    module_id: int
    checked: bool


class RoleModuleCheckRequest(BaseModel):
    modules: List[str]


class RoleModuleDetailResponse(BaseModel):
    id: str
    role_id: str
    module_id: int
    checked: bool
    module: Optional[ModuleResponse] = None

    class Config:
        from_attributes = True
