import re
from typing import Optional, List
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.api.deps import get_current_user
from app.models.base_models import User, Role, Module, RoleModule


def normalize_path(p: str) -> str:
    """Normalize path like rbac.go in Go."""
    if not p:
        return "/"
    p = re.sub(r"/+", "/", p)
    if len(p) > 1 and p.endswith("/"):
        p = p[:-1]
    if not p.startswith("/"):
        p = "/" + p
    return p


def match_path(db_path: str, req_path: str) -> bool:
    """Match request path against module route, supporting :param segments."""
    db_path = normalize_path(db_path)
    req_path = normalize_path(req_path)

    db_parts = [seg for seg in db_path.strip("/").split("/") if seg]
    req_parts = [seg for seg in req_path.strip("/").split("/") if seg]

    if len(db_parts) != len(req_parts):
        return False

    for db_seg, req_seg in zip(db_parts, req_parts):
        if db_seg.startswith(":"):
            continue
        if db_seg.lower() != req_seg.lower():
            return False

    return True


def is_privileged_role(role: Optional[Role]) -> bool:
    """Check if role has superadmin/developer bypass privileges."""
    if not role:
        return False
    name = (role.name or "").lower().strip()
    alias = (role.alias or "").lower().strip()
    return name in ["super admin", "superadmin", "developer", "admin"] or alias in [
        "super-admin",
        "superadmin",
        "developer",
        "admin",
    ]


def require_permission(module_route: Optional[str] = None):
    """
    FastAPI Dependency to check RBAC permissions.
    If module_route is omitted, matches against request.url.path.
    """
    def dependency(
        request: Request,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> User:
        if is_privileged_role(current_user.role):
            return current_user

        target_path = module_route or request.url.path
        target_path = normalize_path(target_path)

        # Remove api prefix if matching against frontend module routes
        clean_path = target_path
        if clean_path.startswith("/api/v1"):
            clean_path = clean_path[len("/api/v1") :] or "/"

        modules: List[Module] = (
            db.query(Module).filter(Module.deleted_at.is_(None)).all()
        )
        if not modules:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Modules not configured",
            )

        matched_module: Optional[Module] = None
        for m in modules:
            if not m.route:
                continue
            m_route = normalize_path(m.route)
            if match_path(m_route, clean_path) or match_path(m_route, target_path):
                matched_module = m
                break

        if not matched_module:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Route '{target_path}' is not registered as a module",
            )

        role_module = (
            db.query(RoleModule)
            .filter(
                RoleModule.role_id == current_user.role_id,
                RoleModule.module_id == matched_module.id,
                RoleModule.checked.is_(True),
                RoleModule.deleted_at.is_(None),
            )
            .first()
        )

        if not role_module:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: module not permitted for this role",
            )

        return current_user

    return dependency

