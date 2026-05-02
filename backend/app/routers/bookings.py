from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.database import get_db
from app.dependencies import get_current_user
from app.schemas.booking import BookingCreate
from app.services import booking_service
from app.utils import success_response

router = APIRouter(prefix="/bookings", tags=["Bookings"])


@router.get("/available")
async def list_available_slots(
    sport: str | None = Query(default=None),
    date: datetime | None = Query(default=None),
    campus: Literal["RR", "EC"] | None = Query(default=None),
    venue: str | None = Query(default=None),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    slots = await booking_service.list_available_slots(db, sport, date, campus, venue)
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
        }
        for s in slots
    ]
    return success_response(data=result, message="Available slots fetched")


@router.post("/create")
async def create_booking(
    body: BookingCreate,
    db: AsyncIOMotorDatabase = Depends(get_db),
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

    return success_response(
        data={
            "booking_id": str(booking["_id"]),
            "status": booking["status"],
            "sport": booking["sport"],
            "slot_id": str(booking["slot_id"]),
        },
        message="Booking created successfully",
    )


@router.get("/my-bookings")
async def my_bookings(
    status_filter: str | None = Query(default=None, alias="status"),
    db: AsyncIOMotorDatabase = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    bookings = await booking_service.get_user_bookings(
        db, str(current_user["_id"]), status_filter
    )
    return success_response(data=bookings, message="Bookings fetched")


@router.delete("/{booking_id}")
async def cancel_booking(
    booking_id: str,
    db: AsyncIOMotorDatabase = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    try:
        updated = await booking_service.cancel_booking(db, booking_id, str(current_user["_id"]))
    except LookupError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    return success_response(
        data={"booking_id": booking_id, "status": updated["status"]},
        message="Booking cancelled",
    )
