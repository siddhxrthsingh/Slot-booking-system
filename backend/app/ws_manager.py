"""
WebSocket connection manager.

Two things live here:
  - `broadcast()` — existing global fan-out used by admin/booking routers for
    coarse dashboard refresh events. Unchanged.
  - Per-connection slot subscriptions + `broadcast_occupancy()` — lets an
    authenticated client subscribe to specific slot IDs and receive only the
    occupancy events for those slots.
"""
import json
import logging
from dataclasses import dataclass, field

from fastapi import WebSocket

logger = logging.getLogger(__name__)


@dataclass
class Connection:
    websocket: WebSocket
    user_id: str
    role: str
    subscriptions: set[str] = field(default_factory=set)


class ConnectionManager:
    def __init__(self):
        self.active: list[WebSocket] = []
        self._connections: dict[WebSocket, Connection] = {}

    # ── Legacy global broadcast (unauthenticated /ws) ───────────────────────
    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active.append(websocket)
        logger.info("WS client connected. Total: %d", len(self.active))

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active:
            self.active.remove(websocket)
        self._connections.pop(websocket, None)
        logger.info("WS client disconnected. Total: %d", len(self.active))

    async def broadcast(self, event_type: str, payload: dict | None = None):
        """Send a JSON message to every connected client; remove dead connections."""
        message = json.dumps({"type": event_type, "data": payload or {}})
        dead: list[WebSocket] = []
        for ws in self.active:
            try:
                await ws.send_text(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)

    # ── Authenticated occupancy subscriptions (/ws/occupancy) ───────────────
    async def connect_authenticated(self, websocket: WebSocket, user_id: str, role: str) -> Connection:
        await websocket.accept()
        conn = Connection(websocket=websocket, user_id=user_id, role=role)
        self.active.append(websocket)
        self._connections[websocket] = conn
        logger.info("Authenticated WS client connected (user=%s). Total: %d", user_id, len(self.active))
        return conn

    def subscribe(self, websocket: WebSocket, slot_ids: list[str]):
        conn = self._connections.get(websocket)
        if conn:
            conn.subscriptions.update(slot_ids)

    def unsubscribe(self, websocket: WebSocket, slot_ids: list[str]):
        conn = self._connections.get(websocket)
        if conn:
            conn.subscriptions.difference_update(slot_ids)

    async def broadcast_occupancy(self, slot_id: str, payload: dict):
        """Send an occupancy_update event only to clients subscribed to this slot_id."""
        message = json.dumps({"type": "occupancy_update", "data": {"slot_id": slot_id, **payload}})
        dead: list[WebSocket] = []
        for ws, conn in list(self._connections.items()):
            if slot_id not in conn.subscriptions:
                continue
            try:
                await ws.send_text(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


# Singleton used across routers
manager = ConnectionManager()
