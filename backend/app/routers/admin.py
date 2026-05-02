from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.database import get_db
from app.dependencies import require_admin
from app.schemas.booking import ApprovalAction
from app.schemas.slot import SlotCreate
from app.services import admin_service
from app.utils import success_response

router = APIRouter(prefix="/admin", tags=["Admin"])


# ---------------------------------------------------------------------------
# Slot management
# ---------------------------------------------------------------------------

@router.get("/slots")
async def get_slots(
    campus: Literal["RR", "EC"] | None = Query(default=None),
    sport: str | None = Query(default=None),
    db: AsyncIOMotorDatabase = Depends(get_db),
    admin: dict = Depends(require_admin),
):
    slots = await admin_service.list_all_slots(db, campus, sport)
    result = [
        {
            "id": str(s["_id"]),
            "sport": s["sport"],
            "date": s["date"],
            "start_time": s["start_time"],
            "end_time": s["end_time"],
            "venue": s["venue"],
            "campus": s["campus"],
            "capacity": s["capacity"],
            "booked_count": s["booked_count"],
            "available_count": s["capacity"] - s["booked_count"],
            "status": s["status"],
            "requires_approval": s.get("requires_approval", False),
            "created_at": s.get("created_at"),
        }
        for s in slots
    ]
    return success_response(data=result, message="Slots fetched")


@router.post("/slots/create")
async def create_slot(
    body: SlotCreate,
    db: AsyncIOMotorDatabase = Depends(get_db),
    admin: dict = Depends(require_admin),
):
    slot_data = body.model_dump()
    slot = await admin_service.create_slot(db, slot_data, str(admin["_id"]))
    return success_response(
        data={"slot_id": str(slot["_id"]), "sport": slot["sport"]},
        message="Slot created successfully",
    )


@router.patch("/slots/{slot_id}")
async def update_slot(
    slot_id: str,
    updates: dict,
    db: AsyncIOMotorDatabase = Depends(get_db),
    admin: dict = Depends(require_admin),
):
    # Strip protected fields from the update payload
    for key in ("_id", "created_by", "created_at", "booked_count"):
        updates.pop(key, None)

    slot = await admin_service.update_slot(db, slot_id, updates)
    if not slot:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Slot not found")
    return success_response(data={"slot_id": slot_id}, message="Slot updated")


@router.delete("/slots/{slot_id}/cancel")
async def cancel_slot(
    slot_id: str,
    db: AsyncIOMotorDatabase = Depends(get_db),
    admin: dict = Depends(require_admin),
):
    affected = await admin_service.cancel_slot(db, slot_id)
    return success_response(
        data={"slot_id": slot_id, "bookings_cancelled": affected},
        message="Slot cancelled and all associated bookings cancelled",
    )


# ---------------------------------------------------------------------------
# Booking management
# ---------------------------------------------------------------------------

@router.get("/bookings")
async def get_all_bookings(
    status_filter: str | None = Query(default=None, alias="status"),
    db: AsyncIOMotorDatabase = Depends(get_db),
    admin: dict = Depends(require_admin),
):
    bookings = await admin_service.list_all_bookings(db, status_filter)
    return success_response(data=bookings, message="Bookings fetched")


@router.get("/bookings/pending")
async def get_pending_bookings(
    db: AsyncIOMotorDatabase = Depends(get_db),
    admin: dict = Depends(require_admin),
):
    bookings = await admin_service.list_pending_bookings(db)
    return success_response(data=bookings, message="Pending bookings fetched")


@router.patch("/bookings/{booking_id}/approve")
async def approve_or_reject(
    booking_id: str,
    body: ApprovalAction,
    db: AsyncIOMotorDatabase = Depends(get_db),
    admin: dict = Depends(require_admin),
):
    updated = await admin_service.process_approval(
        db, booking_id, body.action, str(admin["_id"]), body.notes
    )
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Booking not found or not in pending state",
        )
    return success_response(
        data={"booking_id": booking_id, "status": updated["status"]},
        message=f"Booking {body.action}d successfully",
    )


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

@router.get("/metrics")
async def get_metrics(
    db: AsyncIOMotorDatabase = Depends(get_db),
    admin: dict = Depends(require_admin),
):
    metrics = await admin_service.get_metrics(db)
    return success_response(data=metrics, message="Metrics fetched")
