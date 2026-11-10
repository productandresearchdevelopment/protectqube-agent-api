import logging
from datetime import datetime
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import or_
from app.core.database import get_db
from app.models.base_models import Role, RoleModule, Module, ModuleType, User
from app.schemas.role_module import (
    RoleResponse,
    RoleCreate,
    RoleUpdate,
    RoleModulePermissionUpdate,
    RoleModuleSingleUpdate,
    RoleModuleCheckRequest,
    ModuleResponse,
    ModuleCreate,
    ModuleUpdate,
    ModuleTypeResponse,
    ModuleTypeCreate,
    ModuleTypeUpdate,
)
from app.api.deps import get_current_user
from app.core.rbac import require_permission, is_privileged_role

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Roles & Modules"], dependencies=[Depends(require_permission("/configuration"))])


# =========================================================================
# ROLES CRUD
# =========================================================================

@router.get("/roles")
def get_roles(
    search: Optional[str] = Query(None),
    include_deleted: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(Role)
    if not include_deleted:
        query = query.filter(Role.deleted_at.is_(None))

    if search and search.strip():
        term = f"%{search.strip()}%"
        query = query.filter(or_(Role.name.ilike(term), Role.alias.ilike(term), Role.description.ilike(term)))

    roles = query.order_by(Role.created_at.asc()).all()
    results = []
    for r in roles:
        u_count = db.query(User).filter(User.role_id == r.id, User.deleted_at.is_(None)).count()
        results.append({
            "id": r.id,
            "name": r.name,
            "alias": r.alias,
            "color": r.color or "#3b82f6",
            "description": r.description,
            "user_count": u_count,
            "created_at": r.created_at,
            "updated_at": r.updated_at,
            "deleted_at": r.deleted_at,
        })

    return {"status": True, "data": results}


@router.post("/roles")
def create_role(
    request: RoleCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    existing = db.query(Role).filter(
        (Role.name.ilike(request.name.strip())) | (Role.alias.ilike(request.alias.strip())),
        Role.deleted_at.is_(None),
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Role with this name or alias already exists")

    role = Role(
        name=request.name.strip(),
        alias=request.alias.strip(),
        color=request.color or "#3b82f6",
        description=request.description,
        created_by=current_user.id,
    )
    db.add(role)
    db.commit()
    db.refresh(role)
    return {"status": True, "message": "Role created successfully", "data": role}


@router.get("/roles/{role_id}")
def get_role_by_id(
    role_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    role = db.query(Role).filter(Role.id == role_id, Role.deleted_at.is_(None)).first()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")
    u_count = db.query(User).filter(User.role_id == role.id, User.deleted_at.is_(None)).count()
    return {
        "status": True,
        "data": {
            "id": role.id,
            "name": role.name,
            "alias": role.alias,
            "color": role.color,
            "description": role.description,
            "user_count": u_count,
            "created_at": role.created_at,
            "updated_at": role.updated_at,
        },
    }


@router.put("/roles/{role_id}")
def update_role(
    role_id: str,
    request: RoleUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    role = db.query(Role).filter(Role.id == role_id, Role.deleted_at.is_(None)).first()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")

    if request.name is not None:
        role.name = request.name.strip()
    if request.alias is not None:
        role.alias = request.alias.strip()
    if request.color is not None:
        role.color = request.color
    if request.description is not None:
        role.description = request.description

    role.updated_by = current_user.id
    role.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(role)
    return {"status": True, "message": "Role updated successfully", "data": role}


@router.delete("/roles/{role_id}")
def delete_role(
    role_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    role = db.query(Role).filter(Role.id == role_id, Role.deleted_at.is_(None)).first()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")

    if role.name.lower() in ["super admin", "superadmin"] or role.alias.lower() == "super-admin":
        raise HTTPException(status_code=400, detail="Cannot delete default Super Admin role")

    # Check if active users are attached
    user_count = db.query(User).filter(User.role_id == role.id, User.deleted_at.is_(None)).count()
    if user_count > 0:
        raise HTTPException(status_code=400, detail=f"Cannot delete role: {user_count} active user(s) assigned to this role")

    role.deleted_at = datetime.utcnow()
    role.deleted_by = current_user.id
    db.commit()
    return {"status": True, "message": "Role deleted successfully"}


# =========================================================================
# ROLE PERMISSIONS MATRIX
# =========================================================================

@router.get("/roles/{role_id}/permissions")
def get_role_permissions(
    role_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    role = db.query(Role).filter(Role.id == role_id, Role.deleted_at.is_(None)).first()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")

    modules = db.query(Module).filter(Module.deleted_at.is_(None)).order_by(Module.id.asc()).all()
    role_modules = db.query(RoleModule).filter(RoleModule.role_id == role_id, RoleModule.deleted_at.is_(None)).all()
    checked_map = {rm.module_id: rm.checked for rm in role_modules}

    is_super = role.name.lower() in ["super admin", "superadmin"] or role.alias.lower() == "super-admin"

    results = []
    for m in modules:
        # For super admin default to True if not explicitly set False
        is_checked = checked_map.get(m.id, is_super)
        results.append({
            "module_id": m.id,
            "role_id": role_id,
            "checked": bool(is_checked),
            "name": m.name,
            "route": m.route,
            "icon": m.icon,
            "parent_id": m.parent_id,
            "module_type_id": m.module_type_id,
            "module_type_name": m.module_type.name if m.module_type else None,
            "description": m.description,
        })

    return {"status": True, "data": results}


@router.put("/roles/{role_id}/permissions")
def update_role_permissions_batch(
    role_id: str,
    payload: RoleModulePermissionUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
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
            rm.updated_at = datetime.utcnow()
            rm.updated_by = current_user.id
        else:
            new_rm = RoleModule(
                role_id=role_id,
                module_id=item.module_id,
                checked=item.checked,
                created_by=current_user.id,
            )
            db.add(new_rm)

    db.commit()
    return {"status": True, "message": "Permissions updated successfully"}


@router.put("/roles/{role_id}/permission")
def update_role_permission_single(
    role_id: str,
    payload: RoleModuleSingleUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    role = db.query(Role).filter(Role.id == role_id, Role.deleted_at.is_(None)).first()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")

    rm = (
        db.query(RoleModule)
        .filter(RoleModule.role_id == role_id, RoleModule.module_id == payload.module_id)
        .first()
    )
    if rm:
        rm.checked = payload.checked
        rm.updated_at = datetime.utcnow()
        rm.updated_by = current_user.id
    else:
        rm = RoleModule(
            role_id=role_id,
            module_id=payload.module_id,
            checked=payload.checked,
            created_by=current_user.id,
        )
        db.add(rm)

    db.commit()
    return {"status": True, "message": "Permission updated successfully", "data": {"module_id": payload.module_id, "checked": payload.checked}}


@router.post("/roles/{role_id}/modules/check")
def check_role_modules_batch(
    role_id: str,
    payload: RoleModuleCheckRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    role = db.query(Role).filter(Role.id == role_id, Role.deleted_at.is_(None)).first()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")

    if is_privileged_role(role):
        result = {mod: True for mod in payload.modules}
        return {"status": True, "data": result}

    role_modules = (
        db.query(RoleModule)
        .filter(
            RoleModule.role_id == role_id,
            RoleModule.checked.is_(True),
            RoleModule.deleted_at.is_(None),
        )
        .all()
    )
    module_ids = [rm.module_id for rm in role_modules]
    modules = db.query(Module).filter(Module.id.in_(module_ids), Module.deleted_at.is_(None)).all() if module_ids else []

    allowed_set = set()
    for m in modules:
        if m.route:
            allowed_set.add(m.route.lower().strip())
        if m.name:
            allowed_set.add(m.name.lower().strip())

    result = {}
    for item in payload.modules:
        clean = item.lower().strip()
        norm = "/" + clean.lstrip("/")
        matched = False
        if clean in allowed_set or norm in allowed_set:
            matched = True
        else:
            for allowed in allowed_set:
                if allowed.startswith("/"):
                    if norm.startswith(allowed + "/") or allowed.startswith(norm + "/"):
                        matched = True
                        break
        result[item] = matched

    return {"status": True, "data": result}


# =========================================================================
# MODULES CRUD
# =========================================================================

@router.get("/modules")
def get_modules(
    search: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(Module).filter(Module.deleted_at.is_(None))
    if search and search.strip():
        term = f"%{search.strip()}%"
        query = query.filter(or_(Module.name.ilike(term), Module.route.ilike(term), Module.description.ilike(term)))

    modules = query.order_by(Module.parent_id.asc().nullsfirst(), Module.id.asc()).all()
    results = []
    for m in modules:
        results.append({
            "id": m.id,
            "module_type_id": m.module_type_id,
            "parent_id": m.parent_id,
            "path": m.path,
            "name": m.name,
            "icon": m.icon,
            "route": m.route,
            "description": m.description,
            "parent_name": m.parent.name if m.parent else None,
            "module_type": {
                "id": m.module_type.id,
                "name": m.module_type.name,
                "icon": m.module_type.icon,
                "description": m.module_type.description,
            } if m.module_type else None,
            "created_at": m.created_at,
            "updated_at": m.updated_at,
        })

    return {"status": True, "data": results}


@router.post("/modules")
def create_module(
    request: ModuleCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    mod_type = db.query(ModuleType).filter(ModuleType.id == request.module_type_id).first()
    if not mod_type:
        raise HTTPException(status_code=400, detail="Invalid module_type_id")

    if request.parent_id:
        parent = db.query(Module).filter(Module.id == request.parent_id).first()
        if not parent:
            raise HTTPException(status_code=400, detail="Parent module not found")

    module = Module(
        name=request.name.strip(),
        module_type_id=request.module_type_id,
        parent_id=request.parent_id,
        path=request.path,
        icon=request.icon,
        route=request.route,
        description=request.description,
        created_by=current_user.id,
    )
    db.add(module)
    db.commit()
    db.refresh(module)

    # Automatically grant permission to Super Admin
    admin_role = db.query(Role).filter(Role.name.ilike("Super Admin")).first()
    if admin_role:
        rm = RoleModule(role_id=admin_role.id, module_id=module.id, checked=True)
        db.add(rm)
        db.commit()

    return {"status": True, "message": "Module created successfully", "data": module}


@router.get("/modules/{module_id}")
def get_module_by_id(
    module_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    module = db.query(Module).filter(Module.id == module_id, Module.deleted_at.is_(None)).first()
    if not module:
        raise HTTPException(status_code=404, detail="Module not found")
    return {
        "status": True,
        "data": {
            "id": module.id,
            "module_type_id": module.module_type_id,
            "parent_id": module.parent_id,
            "path": module.path,
            "name": module.name,
            "icon": module.icon,
            "route": module.route,
            "description": module.description,
            "parent_name": module.parent.name if module.parent else None,
            "module_type": {
                "id": module.module_type.id,
                "name": module.module_type.name,
            } if module.module_type else None,
        },
    }


@router.put("/modules/{module_id}")
def update_module(
    module_id: int,
    request: ModuleUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    module = db.query(Module).filter(Module.id == module_id, Module.deleted_at.is_(None)).first()
    if not module:
        raise HTTPException(status_code=404, detail="Module not found")

    if request.name is not None:
        module.name = request.name.strip()
    if request.module_type_id is not None:
        module.module_type_id = request.module_type_id
    if request.parent_id is not None:
        module.parent_id = request.parent_id if request.parent_id > 0 else None
    if request.path is not None:
        module.path = request.path
    if request.icon is not None:
        module.icon = request.icon
    if request.route is not None:
        module.route = request.route
    if request.description is not None:
        module.description = request.description

    module.updated_by = current_user.id
    module.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(module)
    return {"status": True, "message": "Module updated successfully", "data": module}


@router.delete("/modules/{module_id}")
def delete_module(
    module_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    module = db.query(Module).filter(Module.id == module_id, Module.deleted_at.is_(None)).first()
    if not module:
        raise HTTPException(status_code=404, detail="Module not found")

    # Soft delete children or orphan them
    children = db.query(Module).filter(Module.parent_id == module_id, Module.deleted_at.is_(None)).all()
    for child in children:
        child.parent_id = None

    module.deleted_at = datetime.utcnow()
    module.deleted_by = current_user.id
    db.commit()
    return {"status": True, "message": "Module deleted successfully"}


# =========================================================================
# MODULE TYPES CRUD
# =========================================================================

@router.get("/module-types")
def get_module_types(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    types = db.query(ModuleType).filter(ModuleType.deleted_at.is_(None)).order_by(ModuleType.created_at.asc()).all()
    return {"status": True, "data": types}


@router.post("/module-types")
def create_module_type(
    request: ModuleTypeCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    existing = db.query(ModuleType).filter(
        ModuleType.name.ilike(request.name.strip()),
        ModuleType.deleted_at.is_(None),
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Module type with this name already exists")

    m_type = ModuleType(
        name=request.name.strip(),
        icon=request.icon,
        description=request.description,
        created_by=current_user.id,
    )
    db.add(m_type)
    db.commit()
    db.refresh(m_type)
    return {"status": True, "message": "Module type created successfully", "data": m_type}


@router.put("/module-types/{type_id}")
def update_module_type(
    type_id: str,
    request: ModuleTypeUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    m_type = db.query(ModuleType).filter(ModuleType.id == type_id, ModuleType.deleted_at.is_(None)).first()
    if not m_type:
        raise HTTPException(status_code=404, detail="Module type not found")

    if request.name is not None:
        m_type.name = request.name.strip()
    if request.icon is not None:
        m_type.icon = request.icon
    if request.description is not None:
        m_type.description = request.description

    m_type.updated_by = current_user.id
    m_type.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(m_type)
    return {"status": True, "message": "Module type updated successfully", "data": m_type}


@router.delete("/module-types/{type_id}")
def delete_module_type(
    type_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    m_type = db.query(ModuleType).filter(ModuleType.id == type_id, ModuleType.deleted_at.is_(None)).first()
    if not m_type:
        raise HTTPException(status_code=404, detail="Module type not found")

    # Check if modules are using this type
    mod_count = db.query(Module).filter(Module.module_type_id == type_id, Module.deleted_at.is_(None)).count()
    if mod_count > 0:
        raise HTTPException(status_code=400, detail=f"Cannot delete module type: {mod_count} module(s) still use it")

    m_type.deleted_at = datetime.utcnow()
    m_type.deleted_by = current_user.id
    db.commit()
    return {"status": True, "message": "Module type deleted successfully"}
