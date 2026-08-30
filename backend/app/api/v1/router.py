"""جمع‌آوری همه روترهای نسخه ۱ API."""
from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import agents, auth, monitoring, ops, servers, tunnels, users

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(servers.router)
api_router.include_router(agents.router)
api_router.include_router(tunnels.router)
api_router.include_router(monitoring.router)
api_router.include_router(ops.router)
