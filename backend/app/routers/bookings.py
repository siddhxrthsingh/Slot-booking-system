from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.database import get_db
from app.dependencies import get_current_user
from app.schemas.booking import BookingCreate
from app.services import booking_service, email_service
from app.utils import success_response
from app.ws_manager import manager as ws_manager

router = APIRouter(prefix="/bookings", tags=["Bookings"])


@router.get("/available")
async def list_available_slots(
    sport:  str | None = Query(default=None),
    date:   datetime | None = Query(default=None),
    campus: Literal["RR", "EC"] | None = Query(default=None),
    venue:  str | None = Query(default=None),
    db:     AsyncIOMotorDatabase = Depends(get_db),
):
    slots = await booking_service.list_available_slots(db, sport, date, campus, venue)
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
        }
        for s in slots
    ]
    return success_response(data=result, message="Available slots fetched")


@router.post("/create")
async def create_booking(
    body:         BookingCreate,
    db:           AsyncIOMotorDatabase = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    try:
        booking = await booking_service.create_booking(
            db,
            user_id=str(current_user["_id"]),
            slot_id=body.slot_id,
            notes=body.notes,
        )
    except LookupError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    # Broadcast live update
    await ws_manager.broadcast("booking_created", {
        "booking_id": str(booking["_id"]),
        "sport":      booking["sport"],
        "slot_id":    str(booking["slot_id"]),
    })

    # Send confirmation email (best-effort)
    slot = await db["slots"].find_one({"_id": booking["slot_id"]})
    if slot and current_user.get("email"):
        await email_service.send_booking_confirmation(
            to_email   = current_user["email"],
            name       = current_user.get("name", current_user.get("srn", "Student")),
            sport      = booking["sport"],
            date       = slot["date"].strftime("%d %b %Y") if hasattr(slot["date"], "strftime") else str(slot["date"]),
            time_range = f"{slot['start_time']}–{slot['end_time']}",
            venue      = slot.get("venue", ""),
            campus     = slot.get("campus", ""),
        )

    return success_response(
        data={
            "booking_id": str(booking["_id"]),
            "status":     booking["status"],
            "sport":      booking["sport"],
            "slot_id":    str(booking["slot_id"]),
        },
        message="Booking confirmed successfully",
    )


@router.get("/my-bookings")
async def my_bookings(
    status_filter: str | None = Query(default=None, alias="status"),
    db:            AsyncIOMotorDatabase = Depends(get_db),
    current_user:  dict = Depends(get_current_user),
):
    bookings = await booking_service.get_user_bookings(
        db, str(current_user["_id"]), status_filter
    )
    return success_response(data=bookings, message="Bookings fetched")


@router.get("/my-ban")
async def my_ban_status(
    db:           AsyncIOMotorDatabase = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Return the user's active ban, if any."""
    from bson import ObjectId
    ban = await booking_service.check_user_ban(db, ObjectId(str(current_user["_id"])))
    if ban:
        return success_response(
            data={"banned": True, "banned_until": ban["banned_until"], "reason": ban.get("reason")},
            message="User is banned",
        )
    return success_response(data={"banned": False}, message="No active ban")


@router.delete("/{booking_id}")
async def cancel_booking(
    booking_id:   str,
    db:           AsyncIOMotorDatabase = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    try:
        updated = await booking_service.cancel_booking(
            db, booking_id, str(current_user["_id"])
        )
    except LookupError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    # Broadcast live update
    await ws_manager.broadcast("booking_cancelled", {
        "booking_id": booking_id,
        "sport":      updated["sport"],
    })

    # Send cancellation email (best-effort)
    slot = await db["slots"].find_one({"_id": updated["slot_id"]})
    late = updated.get("late_cancel", False)
    banned_until_str = None
    if late and current_user.get("email"):
        from bson import ObjectId
        ban = await booking_service.check_user_ban(db, ObjectId(str(current_user["_id"])))
        if ban:
            banned_until_str = ban["banned_until"].strftime("%d %b %Y, %H:%M UTC")

    if slot and current_user.get("email"):
        await email_service.send_booking_cancellation(
            to_email   = current_user["email"],
            name       = current_user.get("name", current_user.get("srn", "Student")),
            sport      = updated["sport"],
            date       = slot["date"].strftime("%d %b %Y") if hasattr(slot["date"], "strftime") else str(slot["date"]),
            time_range = f"{slot['start_time']}–{slot['end_time']}",
            late       = late,
            banned_until = banned_until_str,
        )

    return success_response(
        data={
            "booking_id":  booking_id,
            "status":      updated["status"],
            "late_cancel": late,
        },
        message="Booking cancelled" + (" — late cancellation ban applied." if late else ""),
    )
