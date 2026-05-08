"""
WebSocket connection manager — broadcast real-time events to all connected clients.
"""
import json
import logging
from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self):
        self.active: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active.append(websocket)
        logger.info("WS client connected. Total: %d", len(self.active))

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active:
            self.active.remove(websocket)
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


# Singleton used across routers
manager = ConnectionManager()
