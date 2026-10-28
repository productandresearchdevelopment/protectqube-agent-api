from fastapi import APIRouter
from app.api.v1.endpoints import auth, monitoring, roles_modules, users

api_router = APIRouter()

api_router.include_router(auth.router)
api_router.include_router(monitoring.router)
api_router.include_router(roles_modules.router)
api_router.include_router(users.router)
