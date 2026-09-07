"""
Admin service: slot management, booking approvals, metrics.
"""
from datetime import datetime, timedelta, timezone

from bson import ObjectId
from bson.errors import InvalidId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.services.booking_service import _slot_end_dt, _slot_start_dt, cancel_booking
from app.utils import ensure_utc


def _filter_active_slots(slots: list[dict], now: datetime | None = None) -> list[dict]:
    """Keep open/full slots whose end time has not passed."""
    now = now or datetime.now(timezone.utc)
    return [
        s for s in slots
        if s.get("status") in ("open", "full") and _slot_end_dt(s) >= now
    ]


# ---------------------------------------------------------------------------
# Slot management
# ---------------------------------------------------------------------------

async def list_all_slots(
    db: AsyncIOMotorDatabase,
    campus: str | None = None,
    sport: str | None = None,
    active_only: bool = True,
) -> list[dict]:
    query: dict = {}
    if active_only:
        query["status"] = {"$in": ["open", "full"]}
    if campus:
        query["campus"] = campus
    if sport:
        query["sport"] = {"$regex": sport, "$options": "i"}

    slots = await db["slots"].find(query).sort("date", 1).to_list(length=500)
    if active_only:
        slots = _filter_active_slots(slots)
    return slots


async def create_slot(db: AsyncIOMotorDatabase, slot_data: dict, admin_id: str) -> dict:
    """Create a manual (one-off) slot tied to a real, active RR facility.

    sport, facility_name, campus, and capacity are derived entirely from the
    facility document — never trusted from caller-supplied data — so a
    manual slot can never diverge from the authoritative facility record.
    Generated slots (created by slot_generation_service) are untouched by
    this function.
    """
    try:
        facility_oid = ObjectId(slot_data["facility_id"])
    except (InvalidId, TypeError, KeyError):
        raise ValueError("A valid facility_id is required.")

    facility = await db["facilities"].find_one({"_id": facility_oid})
    if not facility:
        raise LookupError("Facility not found.")
    if not facility.get("is_active", True):
        raise ValueError("Facility is not active.")
    if facility["campus"] != "RR":
        raise ValueError("Only RR campus facilities are supported.")

    candidate = {
        "date":       slot_data["date"],
        "start_time": slot_data["start_time"],
        "end_time":   slot_data["end_time"],
    }
    new_start = _slot_start_dt(candidate)
    new_end   = _slot_end_dt(candidate)
    if new_end <= new_start:
        raise ValueError("End time must be after start time.")

    # ── Overlap check: same facility, same day, any non-cancelled slot ──────
    day_start = new_start.replace(hour=0, minute=0, second=0, microsecond=0)
    day_end   = day_start + timedelta(days=1)
    same_day_slots = await db["slots"].find({
        "facility_id": facility_oid,
        "status":      {"$ne": "cancelled"},
        "date":        {"$gte": day_start, "$lt": day_end},
    }).to_list(length=200)
    for existing in same_day_slots:
        existing_start = _slot_start_dt(existing)
        existing_end   = _slot_end_dt(existing)
        if new_start < existing_end and new_end > existing_start:
            raise ValueError(
                "This manual slot overlaps an existing slot for this facility."
            )

    duration_minutes = int((new_end - new_start).total_seconds() // 60)

    doc = {
        "facility_id":       facility_oid,
        "facility_name":     facility["display_name"],
        "sport":             facility["sport"],
        "date":              slot_data["date"],
        "start_time":        slot_data["start_time"],
        "end_time":          slot_data["end_time"],
        "venue":             facility["display_name"],
        "campus":            facility["campus"],
        "capacity":          facility["capacity"],
        "duration_minutes":  duration_minutes,
        "slot_type":         "manual",
        "is_manual":         True,
        "requires_approval": slot_data.get("requires_approval", False),
        "leader_user_id":    None,
        "booked_count":      0,
        "status":            "open",
        "created_by":        ObjectId(admin_id),
        "created_at":        datetime.now(timezone.utc),
    }
    result = await db["slots"].insert_one(doc)
    doc["_id"] = result.inserted_id
    return doc


async def update_slot(
    db: AsyncIOMotorDatabase, slot_id: str, updates: dict
) -> dict | None:
    updates["updated_at"] = datetime.now(timezone.utc)
    updated = await db["slots"].find_one_and_update(
        {"_id": ObjectId(slot_id)},
        {"$set": updates},
        return_document=True,
    )
    return updated


async def update_manual_slot(
    db: AsyncIOMotorDatabase, slot_id: str, updates: dict
) -> dict:
    """Edit a manual slot's facility/date/start_time/end_time.

    Mirrors create_slot's validation exactly: the facility (existing or a
    newly selected one) is the authoritative source for sport, facility_name,
    venue, campus, and capacity — never trusted from caller-supplied data.
    Only slots with is_manual=true may be edited through this function;
    generated slots are rejected outright and left untouched.
    """
    try:
        slot_oid = ObjectId(slot_id)
    except (InvalidId, TypeError):
        raise ValueError("Invalid slot_id.")

    slot = await db["slots"].find_one({"_id": slot_oid})
    if not slot:
        raise LookupError("Slot not found.")
    if not slot.get("is_manual"):
        raise ValueError("Only manual slots can be edited through this flow.")

    facility_id_input = updates.get("facility_id")
    if facility_id_input:
        try:
            facility_oid = ObjectId(facility_id_input)
        except (InvalidId, TypeError):
            raise ValueError("A valid facility_id is required.")
    else:
        facility_oid = slot["facility_id"]

    facility = await db["facilities"].find_one({"_id": facility_oid})
    if not facility:
        raise LookupError("Facility not found.")
    if not facility.get("is_active", True):
        raise ValueError("Facility is not active.")
    if facility["campus"] != "RR":
        raise ValueError("Only RR campus facilities are supported.")

    new_date       = updates.get("date", slot["date"])
    new_start_time = updates.get("start_time", slot["start_time"])
    new_end_time   = updates.get("end_time", slot["end_time"])

    candidate = {"date": new_date, "start_time": new_start_time, "end_time": new_end_time}
    new_start = _slot_start_dt(candidate)
    new_end   = _slot_end_dt(candidate)
    if new_end <= new_start:
        raise ValueError("End time must be after start time.")

    # ── Overlap check: same facility, same day, any other non-cancelled slot ─
    day_start = new_start.replace(hour=0, minute=0, second=0, microsecond=0)
    day_end   = day_start + timedelta(days=1)
    same_day_slots = await db["slots"].find({
        "facility_id": facility_oid,
        "status":      {"$ne": "cancelled"},
        "date":        {"$gte": day_start, "$lt": day_end},
        "_id":         {"$ne": slot_oid},
    }).to_list(length=200)
    for existing in same_day_slots:
        existing_start = _slot_start_dt(existing)
        existing_end   = _slot_end_dt(existing)
        if new_start < existing_end and new_end > existing_start:
            raise ValueError(
                "This edit would overlap an existing slot for this facility."
            )

    # ── Active-participant conflict guard ────────────────────────────────────
    # Changing the facility would change sport/venue/capacity out from under
    # anyone who already joined; shrinking effective capacity below the
    # current active headcount is likewise never allowed.
    active_count = await db["bookings"].count_documents(
        {"slot_id": slot_oid, "status": {"$ne": "cancelled"}}
    )
    if active_count > 0:
        facility_changing = str(facility_oid) != str(slot.get("facility_id"))
        if facility_changing:
            raise ValueError(
                "Cannot change the facility for a slot with active participants."
            )
        if active_count > facility["capacity"]:
            raise ValueError(
                "Cannot reduce capacity below the number of active participants."
            )

    duration_minutes = int((new_end - new_start).total_seconds() // 60)

    update_fields = {
        "facility_id":      facility_oid,
        "facility_name":    facility["display_name"],
        "sport":            facility["sport"],
        "venue":            facility["display_name"],
        "campus":           facility["campus"],
        "capacity":         facility["capacity"],
        "date":             new_date,
        "start_time":       new_start_time,
        "end_time":         new_end_time,
        "duration_minutes": duration_minutes,
        "is_manual":        True,
        "updated_at":       datetime.now(timezone.utc),
    }
    updated = await db["slots"].find_one_and_update(
        {"_id": slot_oid},
        {"$set": update_fields},
        return_document=True,
    )
    return updated


async def cancel_slot(db: AsyncIOMotorDatabase, slot_id: str, admin_id: str) -> int:
    """Cancel a slot (manual or generated): the slot itself is marked
    cancelled — never deleted — and every active participation is cancelled
    through booking_service.cancel_booking, the same safe, historically-
    preserving logic used for individual cancellations. This keeps
    cancelled_by, cancelled_at, and leader bookkeeping consistent instead of
    stranding them via a bulk field update, and never applies the student
    late-cancellation ban since this is an admin action.
    """
    slot_oid = ObjectId(slot_id)
    slot = await db["slots"].find_one({"_id": slot_oid})
    if not slot:
        raise LookupError("Slot not found.")

    # Mark the slot cancelled up front. cancel_booking's per-booking capacity
    # release reopens a slot only when its status was "full" — cancelling
    # the slot first prevents that from firing mid-loop.
    await db["slots"].update_one({"_id": slot_oid}, {"$set": {"status": "cancelled"}})

    active_bookings = await db["bookings"].find(
        {"slot_id": slot_oid, "status": {"$ne": "cancelled"}}
    ).to_list(length=500)

    cancelled_count = 0
    for booking in active_bookings:
        try:
            await cancel_booking(
                db, str(booking["_id"]), str(booking["user_id"]),
                actor_id=admin_id, apply_late_ban=False,
            )
            cancelled_count += 1
        except ValueError:
            # Already cancelled (e.g. a concurrent request) — not fatal here.
            continue

    return cancelled_count


# ---------------------------------------------------------------------------
# Booking approvals
# ---------------------------------------------------------------------------

async def list_pending_bookings(db: AsyncIOMotorDatabase) -> list[dict]:
    bookings = (
        await db["bookings"]
        .find({"status": "pending_approval"})
        .sort("created_at", 1)
        .to_list(length=200)
    )
    enriched = []
    for b in bookings:
        user = await db["users"].find_one({"_id": b["user_id"]}, {"password": 0})
        slot = await db["slots"].find_one({"_id": b["slot_id"]})
        enriched.append(
            {
                "id": str(b["_id"]),
                "slot_id": str(b["slot_id"]),
                "sport": b["sport"],
                "status": b["status"],
                "booking_date": b["booking_date"],
                "notes": b.get("notes"),
                "user": {
                    "id": str(user["_id"]),
                    "name": user.get("name"),
                    "srn": user.get("srn"),
                    "email": user.get("email"),
                }
                if user
                else None,
                "slot": {
                    "date": slot.get("date"),
                    "start_time": slot.get("start_time"),
                    "end_time": slot.get("end_time"),
                    "venue": slot.get("venue"),
                    "campus": slot.get("campus"),
                }
                if slot
                else None,
            }
        )
    return enriched


async def process_approval(
    db: AsyncIOMotorDatabase,
    booking_id: str,
    action: str,  # "approve" | "reject"
    admin_id: str,
    notes: str | None = None,
) -> dict | None:
    new_status = "confirmed" if action == "approve" else "cancelled"
    now = datetime.now(timezone.utc)

    update: dict = {
        "status": new_status,
        "updated_at": now,
        "approved_by": ObjectId(admin_id),
    }
    if notes:
        update["notes"] = notes
    if new_status == "cancelled":
        update["cancelled_at"] = now

    updated = await db["bookings"].find_one_and_update(
        {"_id": ObjectId(booking_id), "status": "pending_approval"},
        {"$set": update},
        return_document=True,
    )

    # If rejected, release the seat
    if updated and new_status == "cancelled":
        await db["slots"].update_one(
            {"_id": updated["slot_id"]},
            {"$inc": {"booked_count": -1}, "$set": {"status": "open"}},
        )

    return updated


# ---------------------------------------------------------------------------
# Metrics / dashboard
# ---------------------------------------------------------------------------

async def get_metrics(db: AsyncIOMotorDatabase) -> dict:
    total_slots = await db["slots"].count_documents({})
    open_full_slots = (
        await db["slots"]
        .find({"status": {"$in": ["open", "full"]}})
        .to_list(length=500)
    )
    active_slots = _filter_active_slots(open_full_slots)
    open_slots = sum(1 for s in active_slots if s["status"] == "open")
    full_slots = sum(1 for s in active_slots if s["status"] == "full")
    cancelled_slots = await db["slots"].count_documents({"status": "cancelled"})
    total_bookings = await db["bookings"].count_documents({})
    confirmed_bookings = await db["bookings"].count_documents({"status": "confirmed"})
    pending_bookings = await db["bookings"].count_documents({"status": "pending_approval"})
    cancelled_bookings = await db["bookings"].count_documents({"status": "cancelled"})
    total_users = await db["users"].count_documents({})

    total_capacity = sum(s["capacity"] for s in active_slots)
    total_booked = sum(s["booked_count"] for s in active_slots)
    occupancy_pct = 0.0
    if total_capacity > 0:
        occupancy_pct = round(total_booked / total_capacity * 100, 1)

    return {
        "slots": {
            "total": total_slots,
            "open": open_slots,
            "full": full_slots,
            "active": len(active_slots),
            "cancelled": cancelled_slots,
        },
        "bookings": {
            "total": total_bookings,
            "confirmed": confirmed_bookings,
            "pending_approval": pending_bookings,
            "cancelled": cancelled_bookings,
        },
        "users": {"total": total_users},
        "occupancy_pct": occupancy_pct,
    }


async def list_all_bookings(
    db: AsyncIOMotorDatabase,
    status_filter: str | None = None,
) -> list[dict]:
    query: dict = {}
    if status_filter:
        query["status"] = status_filter

    bookings = (
        await db["bookings"].find(query).sort("created_at", -1).to_list(length=500)
    )
    enriched = []
    for b in bookings:
        user = await db["users"].find_one({"_id": b["user_id"]}, {"password": 0})
        slot = await db["slots"].find_one({"_id": b["slot_id"]})
        enriched.append(
            {
                "id": str(b["_id"]),
                "slot_id": str(b["slot_id"]),
                "sport": b["sport"],
                "status": b["status"],
                "booking_date": b["booking_date"],
                "cancelled_at": ensure_utc(b.get("cancelled_at")),
                "notes": b.get("notes"),
                "created_at": ensure_utc(b["created_at"]),
                "user": {
                    "id": str(user["_id"]),
                    "name": user.get("name"),
                    "srn": user.get("srn"),
                    "email": user.get("email"),
                }
                if user
                else None,
                "slot": {
                    "date": slot.get("date"),
                    "start_time": slot.get("start_time"),
                    "end_time": slot.get("end_time"),
                    "venue": slot.get("venue"),
                    "campus": slot.get("campus"),
                }
                if slot
                else None,
            }
        )
    return enriched


# ---------------------------------------------------------------------------
# Facility inventory (read-only)
# ---------------------------------------------------------------------------

async def list_facilities(db: AsyncIOMotorDatabase, campus: str = "RR") -> list[dict]:
    """Return the facility inventory for a campus, active and inactive alike.

    Ordering is deterministic: sort_order ascending, then name ascending —
    the same key used by seed_facilities.py's own verification query.
    """
    facilities = (
        await db["facilities"]
        .find({"campus": campus})
        .sort([("sort_order", 1), ("name", 1)])
        .to_list(length=200)
    )
    return [
        {
            "id":            str(f["_id"]),
            "campus":        f["campus"],
            "sport":         f["sport"],
            "facility_type": f["facility_type"],
            "name":          f["name"],
            "display_name":  f["display_name"],
            "capacity":      f["capacity"],
            "is_active":     f.get("is_active", True),
            "sort_order":    f.get("sort_order", 0),
        }
        for f in facilities
    ]


async def list_schedule_templates(db: AsyncIOMotorDatabase, campus: str = "RR") -> list[dict]:
    """Return all schedule templates for a campus (read-only viewer).

    Ordering is deterministic: sport ascending, facility_scope ascending,
    day_type ascending, priority descending (highest priority first).
    """
    templates = (
        await db["schedule_templates"]
        .find({"campus": campus})
        .sort([("sport", 1), ("facility_scope", 1), ("day_type", 1), ("priority", -1)])
        .to_list(length=500)
    )
    return [
        {
            "id":               str(t["_id"]),
            "campus":           t["campus"],
            "sport":            t["sport"],
            "facility_id":      str(t["facility_id"]) if t.get("facility_id") else None,
            "facility_name":    t.get("facility_name"),
            "facility_scope":   t["facility_scope"],
            "day_type":         t["day_type"],
            "periods":          t.get("periods", []),
            "is_active":        t.get("is_active", True),
            "priority":         t.get("priority", 0),
            "effective_from":   t.get("effective_from"),
            "effective_until":  t.get("effective_until"),
            "created_by":       str(t["created_by"]) if t.get("created_by") else None,
            "created_at":       t.get("created_at"),
            "updated_at":       t.get("updated_at"),
            "notes":            t.get("notes"),
        }
        for t in templates
    ]


# ---------------------------------------------------------------------------
# Schedule template management (create / update / activation / delete)
# ---------------------------------------------------------------------------

async def _resolve_template_facility(
    db: AsyncIOMotorDatabase, facility_scope: str, facility_id: str | None
) -> tuple[ObjectId | None, str | None]:
    """Facility identity is authoritative from the facilities collection —
    never trusted from caller-supplied facility_name — mirroring how manual
    slots derive their facility fields in create_slot/update_manual_slot.
    """
    if facility_scope != "facility":
        return None, None
    try:
        facility_oid = ObjectId(facility_id)
    except (InvalidId, TypeError):
        raise ValueError("A valid facility_id is required for a facility-scoped template.")
    facility = await db["facilities"].find_one({"_id": facility_oid})
    if not facility:
        raise LookupError("Facility not found.")
    return facility_oid, facility["display_name"]


def _template_response(t: dict) -> dict:
    return {
        "id":               str(t["_id"]),
        "campus":           t["campus"],
        "sport":            t["sport"],
        "facility_id":      str(t["facility_id"]) if t.get("facility_id") else None,
        "facility_name":    t.get("facility_name"),
        "facility_scope":   t["facility_scope"],
        "day_type":         t["day_type"],
        "periods":          t.get("periods", []),
        "is_active":        t.get("is_active", True),
        "priority":         t.get("priority", 0),
        "effective_from":   t.get("effective_from"),
        "effective_until":  t.get("effective_until"),
        "created_by":       str(t["created_by"]) if t.get("created_by") else None,
        "created_at":       t.get("created_at"),
        "updated_at":       t.get("updated_at"),
        "notes":            t.get("notes"),
    }


async def create_schedule_template(
    db: AsyncIOMotorDatabase, data: dict, admin_id: str
) -> dict:
    facility_oid, facility_name = await _resolve_template_facility(
        db, data["facility_scope"], data.get("facility_id")
    )

    doc = {
        "campus":           data["campus"],
        "sport":            data["sport"],
        "facility_id":      facility_oid,
        "facility_name":    facility_name,
        "facility_scope":   data["facility_scope"],
        "day_type":         data["day_type"],
        "periods":          data["periods"],
        "is_active":        data.get("is_active", True),
        "priority":         data.get("priority", 0),
        "effective_from":   data.get("effective_from"),
        "effective_until":  data.get("effective_until"),
        "created_by":       ObjectId(admin_id),
        "created_at":       datetime.now(timezone.utc),
        "updated_at":       None,
        "notes":            data.get("notes"),
    }
    result = await db["schedule_templates"].insert_one(doc)
    doc["_id"] = result.inserted_id
    return _template_response(doc)


async def update_schedule_template(
    db: AsyncIOMotorDatabase, template_id: str, updates: dict
) -> dict:
    try:
        template_oid = ObjectId(template_id)
    except (InvalidId, TypeError):
        raise ValueError("Invalid template_id.")

    template = await db["schedule_templates"].find_one({"_id": template_oid})
    if not template:
        raise LookupError("Schedule template not found.")

    update_fields = dict(updates)

    facility_scope = updates.get("facility_scope", template["facility_scope"])
    if "facility_scope" in updates or "facility_id" in updates:
        facility_id_input = updates.get("facility_id", str(template["facility_id"]) if template.get("facility_id") else None)
        facility_oid, facility_name = await _resolve_template_facility(db, facility_scope, facility_id_input)
        update_fields["facility_id"] = facility_oid
        update_fields["facility_name"] = facility_name
        update_fields["facility_scope"] = facility_scope

    update_fields["updated_at"] = datetime.now(timezone.utc)

    updated = await db["schedule_templates"].find_one_and_update(
        {"_id": template_oid},
        {"$set": update_fields},
        return_document=True,
    )
    return _template_response(updated)


async def delete_schedule_template(db: AsyncIOMotorDatabase, template_id: str) -> None:
    """Permanently remove a schedule template. Generated/manual slots are
    never touched — this only affects future generation runs' template
    resolution."""
    try:
        template_oid = ObjectId(template_id)
    except (InvalidId, TypeError):
        raise ValueError("Invalid template_id.")

    result = await db["schedule_templates"].delete_one({"_id": template_oid})
    if result.deleted_count == 0:
        raise LookupError("Schedule template not found.")


# ---------------------------------------------------------------------------
# Slot roster / accountability (read-only, admin-only)
# ---------------------------------------------------------------------------

async def get_slot_roster(db: AsyncIOMotorDatabase, slot_id: str) -> dict:
    """Return a slot's identity plus its full participation history.

    Includes active AND cancelled bookings (history is preserved, never
    deleted). Participant identity comes entirely from each booking's own
    stored `user_snapshot` — the live `users` collection is never queried
    here, since the snapshot is the historically-accurate accountability
    record for that participation.
    """
    try:
        slot_oid = ObjectId(slot_id)
    except InvalidId as e:
        # Normalize to ValueError, matching the ValueError -> 400 convention
        # already used by the student booking router (routers/bookings.py).
        raise ValueError(str(e)) from e

    slot = await db["slots"].find_one({"_id": slot_oid})
    if not slot:
        raise LookupError("Slot not found.")

    bookings = (
        await db["bookings"]
        .find({"slot_id": slot_oid})
        .sort("joined_at", 1)
        .to_list(length=500)
    )

    # A booking's own user_snapshot is the historically-accurate
    # accountability record and is what's used everywhere below — except
    # `phone`. Some older bookings were captured before the phone field was
    # wired into the snapshot (see auth_service.upsert_user), so for
    # accountability purposes only, fall back to the authoritative live
    # `users.phone` when the snapshot's own phone is missing. This never
    # rewrites the stored snapshot and never falls back for any other field.
    missing_phone_user_ids = [
        b["user_id"] for b in bookings if not (b.get("user_snapshot") or {}).get("phone")
    ]
    live_phone_by_user_id: dict = {}
    if missing_phone_user_ids:
        live_users = await db["users"].find(
            {"_id": {"$in": missing_phone_user_ids}}, {"phone": 1}
        ).to_list(length=len(missing_phone_user_ids))
        live_phone_by_user_id = {u["_id"]: u.get("phone") for u in live_users if u.get("phone")}

    participants = []
    for b in bookings:
        snapshot = dict(b.get("user_snapshot") or {})
        if not snapshot.get("phone") and b["user_id"] in live_phone_by_user_id:
            snapshot["phone"] = live_phone_by_user_id[b["user_id"]]
        participants.append({
            "booking_id":    str(b["_id"]),
            "user_id":       str(b["user_id"]),
            "status":        b["status"],
            "is_leader":     b.get("is_leader", False),
            "joined_at":     ensure_utc(b.get("joined_at")),
            "cancelled_at":  ensure_utc(b.get("cancelled_at")),
            "cancelled_by":  str(b["cancelled_by"]) if b.get("cancelled_by") else None,
            "user_snapshot": snapshot,
        })

    return {
        "slot": {
            "id":            str(slot["_id"]),
            "facility_id":   str(slot["facility_id"]) if slot.get("facility_id") else None,
            "facility_name": slot.get("facility_name"),
            "sport":         slot["sport"],
            "date":          slot["date"],
            "start_time":    slot["start_time"],
            "end_time":      slot["end_time"],
            "campus":        slot["campus"],
            "capacity":      slot["capacity"],
            "booked_count":  slot["booked_count"],
            "status":        slot["status"],
            "leader_user_id": str(slot["leader_user_id"]) if slot.get("leader_user_id") else None,
        },
        "participants": participants,
    }
