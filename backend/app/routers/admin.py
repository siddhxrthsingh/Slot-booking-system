from datetime import datetime, timezone
from typing import Literal

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query, status
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.database import get_db
from app.dependencies import require_admin
from app.schemas.booking import ApprovalAction
from app.schemas.schedule_template import ScheduleTemplateCreate, ScheduleTemplateUpdate
from app.schemas.slot import SlotCreate
from app.services import admin_service, booking_service
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
    include_inactive: bool = Query(default=False),
    db: AsyncIOMotorDatabase = Depends(get_db),
    admin: dict = Depends(require_admin),
):
    slots = await admin_service.list_all_slots(
        db, campus, sport, active_only=not include_inactive
    )
    result = []
    for s in slots:
        capacity = s.get("capacity", 0)
        booked_count = s.get("booked_count", 0)
        result.append({
            "id":                str(s["_id"]),
            "sport":             s.get("sport"),
            "date":              s.get("date"),
            "start_time":        s.get("start_time"),
            "end_time":          s.get("end_time"),
            "venue":             s.get("venue") or s.get("facility_name"),
            "campus":            s.get("campus"),
            "capacity":          capacity,
            "booked_count":      booked_count,
            "available_count":   max(capacity - booked_count, 0),
            "status":            s.get("status"),
            "requires_approval": s.get("requires_approval", False),
            "created_at":        s.get("created_at"),
            "is_manual":         s.get("is_manual", False),
            "facility_id":       str(s["facility_id"]) if s.get("facility_id") else None,
        })
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
    try:
        slot = await admin_service.create_slot(db, slot_data, str(admin["_id"]))
    except LookupError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
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
    existing = await db["slots"].find_one({"_id": ObjectId(slot_id)})
    if not existing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Slot not found")

    if existing.get("is_manual"):
        # Validated, facility-authoritative edit flow (Phase 6.2) — generated
        # slots never go through this branch, and this function itself also
        # rejects a non-manual slot defensively.
        for key in ("_id", "created_by", "created_at", "booked_count", "is_manual"):
            updates.pop(key, None)
        try:
            slot = await admin_service.update_manual_slot(db, slot_id, updates)
        except LookupError as e:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
        except ValueError as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    else:
        # Unchanged: generated slots keep their existing free-text edit path.
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
    try:
        affected = await admin_service.cancel_slot(db, slot_id, str(admin["_id"]))
    except LookupError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    await ws_manager.broadcast("slot_cancelled", {
        "slot_id":           slot_id,
        "bookings_cancelled": affected,
    })

    slot = await db["slots"].find_one({"_id": ObjectId(slot_id)})
    if slot:
        await ws_manager.broadcast_occupancy(str(slot["_id"]), {
            "capacity":        slot["capacity"],
            "booked_count":    slot["booked_count"],
            "available_count": max(slot["capacity"] - slot["booked_count"], 0),
            "status":          slot["status"],
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
    """Admin force-cancel any active booking.

    Reuses booking_service.cancel_booking — the same atomic capacity
    release, leader-reassignment, and historical-preservation logic used
    for student self-cancellation — with the admin recorded as the
    cancelling actor (cancelled_by) instead of the booking's owner.
    """
    booking = await db["bookings"].find_one({"_id": ObjectId(booking_id)})
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    try:
        updated = await booking_service.cancel_booking(
            db, booking_id, str(booking["user_id"]),
            actor_id=str(admin["_id"]), apply_late_ban=False,
        )
    except LookupError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    await ws_manager.broadcast("booking_cancelled", {"booking_id": booking_id, "sport": updated["sport"]})

    slot = await db["slots"].find_one({"_id": updated["slot_id"]})
    if slot:
        await ws_manager.broadcast_occupancy(str(slot["_id"]), {
            "capacity":        slot["capacity"],
            "booked_count":    slot["booked_count"],
            "available_count": max(slot["capacity"] - slot["booked_count"], 0),
            "status":          slot["status"],
        })

    return success_response(
        data={"booking_id": booking_id, "status": updated["status"]},
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


@router.get("/slots/{slot_id}/roster")
async def get_slot_roster(
    slot_id: str,
    db: AsyncIOMotorDatabase = Depends(get_db),
    admin: dict = Depends(require_admin),
):
    """Admin-only: a slot's identity plus its full (active + historical)
    participation roster, for occupancy/accountability purposes."""
    try:
        roster = await admin_service.get_slot_roster(db, slot_id)
    except LookupError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return success_response(data=roster, message="Slot roster fetched")


@router.get("/facilities")
async def get_facilities(
    campus: Literal["RR"] = Query(default="RR"),
    db: AsyncIOMotorDatabase = Depends(get_db),
    admin: dict = Depends(require_admin),
):
    """Read-only facility inventory (RR only for now)."""
    facilities = await admin_service.list_facilities(db, campus)
    return success_response(data=facilities, message="Facilities fetched")


@router.get("/schedule-templates")
async def get_schedule_templates(
    campus: Literal["RR"] = Query(default="RR"),
    db: AsyncIOMotorDatabase = Depends(get_db),
    admin: dict = Depends(require_admin),
):
    """Read-only schedule template viewer (RR only for now)."""
    templates = await admin_service.list_schedule_templates(db, campus)
    return success_response(data=templates, message="Schedule templates fetched")


@router.post("/schedule-templates")
async def create_schedule_template(
    body: ScheduleTemplateCreate,
    db: AsyncIOMotorDatabase = Depends(get_db),
    admin: dict = Depends(require_admin),
):
    try:
        template = await admin_service.create_schedule_template(
            db, body.model_dump(), str(admin["_id"])
        )
    except LookupError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return success_response(data=template, message="Schedule template created")


@router.patch("/schedule-templates/{template_id}")
async def update_schedule_template(
    template_id: str,
    body: ScheduleTemplateUpdate,
    db: AsyncIOMotorDatabase = Depends(get_db),
    admin: dict = Depends(require_admin),
):
    updates = body.model_dump(exclude_unset=True)
    try:
        template = await admin_service.update_schedule_template(db, template_id, updates)
    except LookupError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return success_response(data=template, message="Schedule template updated")


@router.delete("/schedule-templates/{template_id}")
async def delete_schedule_template(
    template_id: str,
    db: AsyncIOMotorDatabase = Depends(get_db),
    admin: dict = Depends(require_admin),
):
    try:
        await admin_service.delete_schedule_template(db, template_id)
    except LookupError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return success_response(data={"template_id": template_id}, message="Schedule template deleted")


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
