from datetime import datetime, timezone
from typing import Literal

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query, status
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.database import get_db
from app.dependencies import require_admin
from app.schemas.booking import ApprovalAction
from app.schemas.slot import SlotCreate
from app.services import admin_service
from app.utils import success_response
from app.ws_manager import manager as ws_manager

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
            "id":                str(s["_id"]),
            "sport":             s["sport"],
            "date":              s["date"],
            "start_time":        s["start_time"],
            "end_time":          s["end_time"],
            "venue":             s["venue"],
            "campus":            s["campus"],
            "capacity":          s["capacity"],
            "booked_count":      s["booked_count"],
            "available_count":   s["capacity"] - s["booked_count"],
            "status":            s["status"],
            "requires_approval": s.get("requires_approval", False),
            "created_at":        s.get("created_at"),
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
    # Force auto-confirm (no approval required)
    slot_data["requires_approval"] = False
    slot = await admin_service.create_slot(db, slot_data, str(admin["_id"]))
    await ws_manager.broadcast("slot_created", {
        "slot_id": str(slot["_id"]),
        "sport":   slot["sport"],
        "campus":  slot["campus"],
    })
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
    for key in ("_id", "created_by", "created_at", "booked_count"):
        updates.pop(key, None)

    slot = await admin_service.update_slot(db, slot_id, updates)
    if not slot:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Slot not found")

    await ws_manager.broadcast("slot_updated", {"slot_id": slot_id})
    return success_response(data={"slot_id": slot_id}, message="Slot updated")


@router.delete("/slots/{slot_id}/cancel")
async def cancel_slot(
    slot_id: str,
    db: AsyncIOMotorDatabase = Depends(get_db),
    admin: dict = Depends(require_admin),
):
    affected = await admin_service.cancel_slot(db, slot_id)
    await ws_manager.broadcast("slot_cancelled", {
        "slot_id":           slot_id,
        "bookings_cancelled": affected,
    })
    return success_response(
        data={"slot_id": slot_id, "bookings_cancelled": affected},
        message="Slot cancelled and all associated bookings cancelled",
    )


@router.delete("/slots/{slot_id}/delete")
async def delete_slot_permanently(
    slot_id: str,
    db: AsyncIOMotorDatabase = Depends(get_db),
    admin: dict = Depends(require_admin),
):
    """Permanently remove a slot (and its bookings) from the database."""
    from bson import ObjectId
    slot_oid = ObjectId(slot_id)
    await db["bookings"].delete_many({"slot_id": slot_oid})
    result = await db["slots"].delete_one({"_id": slot_oid})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Slot not found")
    await ws_manager.broadcast("slot_cancelled", {"slot_id": slot_id})
    return success_response(data={"slot_id": slot_id}, message="Slot permanently deleted")


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


@router.delete("/bookings/{booking_id}/cancel")
async def admin_cancel_booking(
    booking_id: str,
    db: AsyncIOMotorDatabase = Depends(get_db),
    admin: dict = Depends(require_admin),
):
    """Admin force-cancel any active booking and release the seat."""
    from bson import ObjectId
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    booking = await db["bookings"].find_one({"_id": ObjectId(booking_id)})
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    if booking["status"] == "cancelled":
        raise HTTPException(status_code=400, detail="Booking is already cancelled")

    # Release the seat
    await db["slots"].update_one(
        {"_id": booking["slot_id"]},
        {"$inc": {"booked_count": -1}, "$set": {"status": "open"}},
    )
    updated = await db["bookings"].find_one_and_update(
        {"_id": ObjectId(booking_id)},
        {"$set": {"status": "cancelled", "cancelled_at": now, "updated_at": now,
                  "admin_cancelled": True, "approved_by": ObjectId(str(admin["_id"]))}},
        return_document=True,
    )
    await ws_manager.broadcast("booking_cancelled", {"booking_id": booking_id, "sport": updated["sport"]})
    return success_response(
        data={"booking_id": booking_id, "status": "cancelled"},
        message="Booking cancelled by admin",
    )


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
    await ws_manager.broadcast("booking_updated", {
        "booking_id": booking_id,
        "status":     updated["status"],
    })
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


# ---------------------------------------------------------------------------
# Ban management
# ---------------------------------------------------------------------------

@router.get("/bans")
async def list_bans(
    db: AsyncIOMotorDatabase = Depends(get_db),
    admin: dict = Depends(require_admin),
):
    """List all active bans."""
    now = datetime.now(timezone.utc)
    bans = await db["bans"].find({"banned_until": {"$gt": now}}).to_list(length=200)
    result = []
    for b in bans:
        user = await db["users"].find_one({"_id": b["user_id"]}, {"password": 0})
        result.append({
            "id":           str(b["_id"]),
            "user_id":      str(b["user_id"]),
            "user_name":    user.get("name") if user else None,
            "user_srn":     user.get("srn") if user else None,
            "user_email":   user.get("email") if user else None,
            "reason":       b.get("reason", ""),
            "banned_until": b["banned_until"],
            "created_at":   b.get("created_at"),
        })
    return success_response(data=result, message="Active bans fetched")


@router.delete("/bans/{user_id}")
async def unban_user(
    user_id: str,
    db: AsyncIOMotorDatabase = Depends(get_db),
    admin: dict = Depends(require_admin),
):
    """Lift a ban for a specific user."""
    result = await db["bans"].delete_one({"user_id": ObjectId(user_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="No active ban found for this user")
    return success_response(data={"user_id": user_id}, message="Ban lifted")


@router.get("/users")
async def list_users(
    campus: Literal["RR", "EC"] | None = Query(default=None),
    db: AsyncIOMotorDatabase = Depends(get_db),
    admin: dict = Depends(require_admin),
):
    """List all students."""
    query: dict = {"role": "student"}
    if campus:
        query["campus"] = campus
    users = await db["users"].find(query, {"password": 0}).sort("name", 1).to_list(length=500)
    return success_response(
        data=[
            {
                "id":       str(u["_id"]),
                "name":     u.get("name"),
                "srn":      u.get("srn"),
                "email":    u.get("email"),
                "branch":   u.get("branch"),
                "campus":   u.get("campus"),
                "role":     u.get("role"),
            }
            for u in users
        ],
        message="Users fetched",
    )
