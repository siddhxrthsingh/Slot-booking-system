# PESU Sports Slot Booking System — Project Context & Handover

RR Campus • branch `slot-system-redesign` • last verified against code: 2026-08-16

This document is the persistent context for this project: the agreed product model,
locked rules, current architecture, verified implementation status, and next work.
**Always re-verify against the actual repository before assuming any endpoint, model,
or behavior described here exists** — this file can go stale as work progresses.

## 1. Project Goal

Build a PESU sports slot-booking system, initially for RR campus. Students see
sport/date availability and JOIN shared slots (not book an entire court). Students see
Available/Full/occupancy counts but never participant identities. Admin/faculty will
later see full occupancy and participant/accountability details.

## 2. Scope & Product Decisions — LOCKED

- RR campus only. EC deferred (facility/sport requirements unknown — do not invent them).
- Students JOIN a slot; they do not independently book an entire court.
- Normal generated slots are exactly 1 hour. Faculty/admin manual overrides may have
  arbitrary duration.
- Capacity: Badminton / Table Tennis / Squash = 6 per facility. Basketball / Volleyball = 12.
- Max 2 ACTIVE joined slots per calendar day per student, across all sports/facilities.
- No overlapping active slots for the same student.
- First active participant is the accountable leader. If the leader leaves, the
  earliest-joined remaining active participant becomes leader. If no active participants
  remain, `slot.leader_user_id` becomes null.
- Students never see participant names/SRNs/phone/branch/program/snapshots — only
  aggregate occupancy.
- Participant history is retained permanently for accountability, including leavers.
- Once a student leaves a slot, they cannot rejoin that same slot.
- College holidays follow the Sunday schedule. Do not invent unspecified
  basketball/volleyball holiday rules — holiday resolution is still future work.
- Admin will later see: name, SRN, phone, branch, program, semester, section.

## 3. RR Facilities (11 total, seeded)

| Sport | Facility | Capacity |
|---|---|---|
| Badminton | Court 1 / 2 / 3 | 6 each |
| Table Tennis | Table 1 / 2 / 3 | 6 each |
| Squash | Court 1 / 2 | 6 each |
| Basketball | Court 1 / 2 | 12 each |
| Volleyball | Court 1 | 12 |

## 4. Schedule Rules

- `schedule_templates` collection drives generation (no hardcoded sport schedules).
- Templates support weekday / saturday / sunday / holiday day types; facility-specific
  templates override sport-level templates.
- Cleaning, lunch, staff periods are non-bookable and are never generated as student slots.
- Badminton Court 1 has a facility-specific staff schedule (weekday and Sunday variants);
  all other sports use sport-level templates.
- Holiday templates were **not** seeded — holiday resolution is future work.

## 5. Core MongoDB Collections

`users`, `facilities`, `slots`, `bookings`, `schedule_templates`, `sessions`, `bans`

Relationships: `users → bookings` (participation), `facilities → slots`, `slots → bookings`,
`users → slots` (leader).

## 6. Key Model Fields (current, in code)

**Facility** (`app/models/facility.py`): `_id, campus, sport, facility_type, name,
display_name, capacity, is_active, sort_order, created_at, updated_at`. Stable seed
identity = campus + sport + name.

**Slot** (`app/models/slot.py`): `facility_id, facility_name, sport, date, start_time,
end_time, venue, campus, capacity, booked_count, status (open/full/closed/cancelled),
duration_minutes, slot_type (generated/manual/staff/cleaning/lunch), leader_user_id,
created_by, override_reason, notes, is_manual`.

**Booking** (`app/models/booking.py`): `user_id, slot_id, facility_id, sport, status
(confirmed/pending_approval/cancelled), joined_at, cancelled_at, cancelled_by, is_leader,
user_snapshot {name, srn, phone, branch, program, semester, section, campus}, notes,
approved_by`.

**User** (`app/models/user.py`): `srn, prn, email, phone, name, program, branch,
semester, section, campus, role, auth_provider`. PESUAuth (`auth_service.py`) supplies
phone/semester/section — persist all of it for future admin accountability.

## 7. Booking Rules — LOCKED

| Rule | Decision |
|---|---|
| Multiple participants | No uniqueness constraint may prevent multiple users joining the same slot |
| Occupancy | `slot.booked_count` = current ACTIVE participants only |
| Leader | First active participant is leader; promotion to earliest remaining active participant on leader exit |
| Capacity | 6 (Badminton/TT/Squash), 12 (Basketball/Volleyball) |
| Daily limit | Max 2 active slots/day across ALL sports/facilities |
| Overlap | No overlapping active slots for the same student |
| Same-slot rejoin | Blocked once a student has left that slot |
| Cancel before ban window | Frees quota; student may join a different slot |
| Cancel inside ban window | Existing ban applies; student cannot join elsewhere while banned |
| History | Never physically delete; retain who joined/left, when, actor, snapshot |
| Atomicity | Join must atomically require `booked_count < capacity` before incrementing |
| Safety | Never `booked_count > capacity`, never negative, never double inc/dec |

## 8. Implementation Status (verified against code 2026-08-16)

| Area | Status |
|---|---|
| Phase 0 — prep/git safety | DONE |
| Phase 1 — facility model redesign + RR seed | DONE (`app/models/facility.py`, seed scripts) |
| Phase 2 — schedule templates, slot generator, facility-aware retrieval, generator hardening | DONE (`app/services/slot_generation_service.py`, `app/routers/bookings.py::/available`) |
| Phase 3 Step 1A — participation schemas | DONE (`BookingModel`/`SlotModel` have the new fields; `tests/test_participation_models.py` passes) |
| **Phase 3 Step 1B — Join Slot runtime** | **NOT DONE** — `app/services/booking_service.py` still runs the OLD single-participant policy (1 booking per SPORT/day, no same-slot-rejoin block, no leader assignment, no snapshot capture) |
| Phase 3 — leave/cancellation/leader redesign | NOT DONE |
| Phase 3 — 2-slot daily limit + overlap enforcement (new rules) | NOT DONE |
| Admin occupancy/participant API/UI | NOT DONE |
| Manual faculty arbitrary-duration slot management | NOT DONE |
| Holiday/closure + approval workflow | NOT DONE |
| Live WebSocket/live feed | Basic broadcast exists (`ws_manager.py`), not redesigned for participation |
| Frontend redesign/integration | NOT DONE |
| EC campus | DEFERRED |

**Gap to close next:** `booking_service.create_booking()` / `cancel_booking()` need a
full rewrite to the participation model. Current logic (verified in
`app/services/booking_service.py`):
- Enforces 1 booking per **sport** per day — must become max 2 ACTIVE slots per day
  across ALL sports.
- Has no same-slot-rejoin block.
- Has no leader assignment or promotion logic.
- Does not capture `user_snapshot` on join.
- Cancel logic decrements `booked_count` and reopens slot but doesn't handle leader
  promotion or `leader_user_id` clearing.

## 9. Testing Baseline

- FastAPI `/docs` smoke test must return 200 after any scoped change.
- After Phase 2 Step 5: 14 slot-generation tests passed.
- After Phase 2 Step 4: 16 retrieval + generation tests passed.
- After Phase 3 Step 1A: 25 participation/retrieval/generation tests passed.
- `datetime.utcnow()` deprecation warning exists in older code — intentionally left
  alone during scoped steps (do not fix opportunistically mid-feature-step).
- Never modify or commit `__pycache__` / `.pyc` files.

## 10. Git / Working Practices

- Development branch: `slot-system-redesign`.
- Completed steps are committed and pushed as checkpoints.
- Before changing code: `git status`, inspect recent commits, inspect relevant current
  files — never trust this doc alone.
- Do not commit until tests and diff have been reviewed.

## 11. Roadmap

Phase 3 (multi-participant Join Slot backend, in progress) → Phase 4 (student
dashboard/frontend) → Phase 5 (admin/faculty occupancy + accountability) → Phase 6
(manual faculty overrides) → Phase 7 (holidays/closures/approvals) → Later (live
WebSockets, deployment hardening, EC campus, deferred group/privacy features).

## 12. Non-Negotiable Constraints for Future Agents

- Do not invent EC sports/facilities.
- Do not expose participant identities to students.
- Do not revert to one-student-per-slot semantics.
- Do not delete historical participation records on normal cancellation.
- Do not allow `booked_count` above capacity or below zero.
- Do not allow more than 2 active slots/day per student.
- Do not allow overlapping active slots.
- Do not allow same-slot rejoin after leaving.
- Do not let generation overwrite manual slots or booking state.
- Backend is authoritative for capacity, limits, overlap, leader, and cancellation rules.
- Use small, testable implementation steps; report exact files/tests/compatibility impact.
