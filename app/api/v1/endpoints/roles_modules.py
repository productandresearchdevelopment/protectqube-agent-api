from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models.base_models import Role, RoleModule, Module, ModuleType
from app.schemas.role_module import (
    RoleResponse,
    RoleCreate,
    RoleUpdate,
    RoleModulePermissionUpdate,
    ModuleResponse,
    ModuleTypeResponse,
)
from app.api.deps import get_current_user

router = APIRouter(tags=["Roles & Modules"])


@router.get("/roles")
def get_roles(db: Session = Depends(get_db)):
    roles = db.query(Role).filter(Role.deleted_at.is_(None)).all()
    return {"status": True, "data": roles}


@router.post("/roles")
def create_role(request: RoleCreate, db: Session = Depends(get_db)):
    role = Role(**request.model_dump())
    db.add(role)
    db.commit()
    db.refresh(role)
    return {"status": True, "data": role}


@router.get("/roles/{role_id}/permissions")
def get_role_permissions(role_id: str, db: Session = Depends(get_db)):
    role = db.query(Role).filter(Role.id == role_id, Role.deleted_at.is_(None)).first()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")

    role_modules = db.query(RoleModule).filter(RoleModule.role_id == role_id).all()
    return {"status": True, "data": role_modules}


@router.put("/roles/{role_id}/permissions")
def update_role_permissions(
    role_id: str,
    payload: RoleModulePermissionUpdate,
    db: Session = Depends(get_db),
):
    role = db.query(Role).filter(Role.id == role_id, Role.deleted_at.is_(None)).first()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")

    for item in payload.permissions:
        rm = (
            db.query(RoleModule)
            .filter(RoleModule.role_id == role_id, RoleModule.module_id == item.module_id)
            .first()
        )
        if rm:
            rm.checked = item.checked
        else:
            new_rm = RoleModule(role_id=role_id, module_id=item.module_id, checked=item.checked)
            db.add(new_rm)

    db.commit()
    return {"status": True, "message": "Permissions updated successfully"}


@router.get("/modules")
def get_modules(db: Session = Depends(get_db)):
    modules = db.query(Module).filter(Module.deleted_at.is_(None)).all()
    return {"status": True, "data": modules}


@router.get("/module-types")
def get_module_types(db: Session = Depends(get_db)):
    types = db.query(ModuleType).filter(ModuleType.deleted_at.is_(None)).all()
    return {"status": True, "data": types}
