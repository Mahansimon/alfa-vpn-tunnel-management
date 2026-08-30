"""WebSocket برای مانیتورینگ زنده و لاگ استقرار.

احراز هویت WebSocket: کوکی نشست (همان کوکی پنل) بررسی می‌شود؛ اتصال بدون
احراز هویت بلافاصله بسته می‌شود.
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from sqlalchemy import select

from app.core.config import settings
from app.core.crypto import hash_token
from app.core.logging import get_logger
from app.core.security import decode_jwt
from app.db.models.user import User, UserSession
from app.db.session import SessionLocal
from app.services.realtime import hub

router = APIRouter()
log = get_logger("ws")

ALLOWED_TOPICS = {"metrics", "servers", "tunnels", "notifications", "*"}


async def _authenticate(websocket: WebSocket) -> User | None:
    raw = websocket.cookies.get(settings.COOKIE_NAME)
    if not raw:
        return None
    payload = decode_jwt(raw)
    if not payload:
        return None
    async with SessionLocal() as db:
        session = (
            await db.execute(
                select(UserSession).where(
                    UserSession.id == payload.get("sid"), UserSession.revoked.is_(False)
                )
            )
        ).scalar_one_or_none()
        if session is None or session.expires_at < datetime.now(timezone.utc):
            return None
        if session.token_hash != hash_token(raw):
            return None
        user = await db.get(User, session.user_id)
        return user if user and user.is_active else None


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, topic: str = Query(default="metrics")):
    user = await _authenticate(websocket)
    if user is None:
        await websocket.close(code=4401)
        return
    if topic not in ALLOWED_TOPICS and not topic.startswith("deployment:"):
        await websocket.close(code=4400)
        return
    await websocket.accept()
    await hub.connect(topic, websocket)
    await websocket.send_text(json.dumps({"event": "connected", "topic": topic}))
    try:
        while True:
            # اتصال را زنده نگه می‌داریم و به ping پاسخ می‌دهیم
            try:
                message = await asyncio.wait_for(websocket.receive_text(), timeout=30)
                if message == "ping":
                    await websocket.send_text(json.dumps({"event": "pong"}))
            except asyncio.TimeoutError:
                await websocket.send_text(json.dumps({"event": "heartbeat"}))
    except WebSocketDisconnect:
        pass
    except Exception as exc:  # pragma: no cover
        log.debug("ws_error", error=str(exc))
    finally:
        await hub.disconnect(topic, websocket)
