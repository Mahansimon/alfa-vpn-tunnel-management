"""Hub انتشار رویدادها روی WebSocket (Live Monitoring)."""
from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field

from fastapi import WebSocket

from app.core.logging import get_logger

log = get_logger("realtime")


@dataclass
class Hub:
    connections: dict[str, set[WebSocket]] = field(default_factory=dict)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def connect(self, topic: str, ws: WebSocket) -> None:
        async with self.lock:
            self.connections.setdefault(topic, set()).add(ws)

    async def disconnect(self, topic: str, ws: WebSocket) -> None:
        async with self.lock:
            peers = self.connections.get(topic)
            if peers:
                peers.discard(ws)
                if not peers:
                    self.connections.pop(topic, None)

    async def publish(self, topic: str, event: str, payload: dict) -> None:
        message = json.dumps({"event": event, "topic": topic, "data": payload}, default=str)
        async with self.lock:
            targets = list(self.connections.get(topic, ())) + list(self.connections.get("*", ()))
        dead: list[tuple[str, WebSocket]] = []
        for ws in targets:
            try:
                await ws.send_text(message)
            except Exception:
                dead.append((topic, ws))
        for topic_name, ws in dead:
            await self.disconnect(topic_name, ws)

    def count(self) -> int:
        return sum(len(v) for v in self.connections.values())


hub = Hub()
