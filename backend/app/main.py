import logging
from contextlib import asynccontextmanager

import json

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.config import get_settings
from app.database import close_db, connect_db, get_db
from app.dependencies import get_ws_user
from app.routers import admin, auth, bookings
from app.utils import error_response
from app.ws_manager import manager as ws_manager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

settings = get_settings()

# ---------------------------------------------------------------------------
# Rate limiter (shared across routers)
# ---------------------------------------------------------------------------
limiter = Limiter(key_func=get_remote_address, default_limits=["200/minute"])


# ---------------------------------------------------------------------------
# Lifespan (startup / shutdown)
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Connecting to MongoDB…")
    await connect_db()
    logger.info("MongoDB connected.")
    yield
    logger.info("Closing MongoDB connection…")
    await close_db()


# ---------------------------------------------------------------------------
# App instance
# ---------------------------------------------------------------------------
app = FastAPI(
    title="Slot Booking System API",
    description="Backend API for PESU Slot Booking System",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# Rate limiting
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.frontend_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Global exception handler — return standard error envelope
# ---------------------------------------------------------------------------
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled error: %s", exc)
    return JSONResponse(
        status_code=500,
        content=error_response("internal_error", "An unexpected error occurred"),
    )


# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------
app.include_router(auth.router)
app.include_router(bookings.router)
app.include_router(admin.router)


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------
@app.get("/health", tags=["Health"])
async def health():
    return {"status": "ok", "version": "1.0.0"}


# ---------------------------------------------------------------------------
# WebSocket — real-time dashboard updates
# ---------------------------------------------------------------------------
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await ws_manager.connect(websocket)
    try:
        while True:
            # Keep the connection alive; we only push from server to client.
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception:
        ws_manager.disconnect(websocket)


# ---------------------------------------------------------------------------
# WebSocket — authenticated slot occupancy subscriptions
# ---------------------------------------------------------------------------
@app.websocket("/ws/occupancy")
async def occupancy_ws_endpoint(websocket: WebSocket, token: str | None = None):
    if not token:
        await websocket.close(code=4401)
        return

    db = get_db()
    user = await get_ws_user(token, db)
    if not user:
        await websocket.close(code=4401)
        return

    await ws_manager.connect_authenticated(websocket, user_id=user["id"], role=user.get("role", "student"))
    try:
        while True:
            raw = await websocket.receive_text()
            try:
                message = json.loads(raw)
            except (TypeError, ValueError):
                await websocket.send_text(json.dumps({"type": "error", "data": {"message": "Invalid JSON"}}))
                continue

            action = message.get("action")
            slot_ids = message.get("slot_ids") or []
            slot_ids = [str(s) for s in slot_ids]

            if action == "subscribe":
                ws_manager.subscribe(websocket, slot_ids)
                await websocket.send_text(json.dumps({"type": "subscribed", "data": {"slot_ids": slot_ids}}))
            elif action == "unsubscribe":
                ws_manager.unsubscribe(websocket, slot_ids)
                await websocket.send_text(json.dumps({"type": "unsubscribed", "data": {"slot_ids": slot_ids}}))
            else:
                await websocket.send_text(json.dumps({"type": "error", "data": {"message": "Unknown action"}}))
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception:
        ws_manager.disconnect(websocket)
