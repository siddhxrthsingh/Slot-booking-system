\# PESU Sports Slot Booking System — Claude Code Project Rules



\## 1. Project Goal



Build a PESU Sports Slot Booking System.



Initial scope:

\- Campus: RR only

\- EC support is deferred until actual requirements are known.

\- Students can view available/full sports slots and join shared slots.

\- Students must never see other participants' identities.

\- Admin/faculty will later have participant/accountability visibility.



\---



\## 2. Tech Stack



\- Frontend: React

\- Backend: Python + FastAPI

\- Database: MongoDB

\- MongoDB driver: Motor (async)

\- Authentication: PESUAuth

\- Business logic: Python service layer

\- Real-time updates: WebSockets planned

\- Deployment: TBD



Architecture:



React frontend

→ FastAPI routes

→ Python services

→ MongoDB



PESUAuth handles authentication.



Keep business logic in services rather than putting complex logic directly in routers.



\---



\## 3. Core Booking Rules — LOCKED



These rules are authoritative. Do not change them unless explicitly instructed.



\### Shared slots



\- Multiple students can join the same slot.

\- Do NOT create a uniqueness constraint preventing multiple participants per slot.

\- Capacity is enforced by the backend.

\- First active participant becomes the leader/accountable user.

\- If the leader leaves, the earliest joined remaining active participant becomes leader.

\- If no active participants remain, `leader\_user\_id = null`.

\- `slot.booked\_count` represents CURRENT active participants only.



\### Capacity



Badminton:

\- Capacity = 6 per court



Table Tennis:

\- Capacity = 6 per table



Squash:

\- Capacity = 6 per court



Basketball:

\- Capacity = 12 per court



Volleyball:

\- Capacity = 12 per court



\### Student booking limits



\- Maximum 2 ACTIVE joined slots per student per calendar day.

\- This limit applies across all sports and facilities.

\- Active bookings for the same student must not overlap.

\- Overlap checks must support arbitrary-duration manual slots, not only 1-hour slots.



\### Cancellation / leaving



\- Once a student leaves/cancels a particular slot, they CANNOT rejoin that same slot.

\- Do not resurrect/reuse the old participation record.

\- Cancellation must preserve historical participation data.

\- Normal cancellation changes booking status; do not physically delete the booking.

\- Leaving before the ban window frees that student's active daily quota.

\- Leaving during the ban window does NOT bypass the ban.

\- Leaving an already-started slot must not be usable as a way to obtain another overlapping booking.



Existing default policy:

\- Cancellation window: 2 hours

\- Ban duration: 2 days



Apply these to individual participation/booking records as the booking system is redesigned.



\### Historical accountability



Retain:

\- who joined

\- when they joined

\- who left/cancelled

\- when they left/cancelled

\- cancellation actor

\- user snapshot

\- leader status/history as appropriate



\### Atomicity



Join/capacity operations must be safe against concurrent requests.



Use an atomic MongoDB capacity check/update so:



\- booked\_count never exceeds capacity

\- booked\_count never becomes negative

\- double increments/decrements are prevented

\- concurrent joins cannot overbook a slot



Backend is authoritative. Frontend must NOT enforce critical booking rules.



\---



\## 4. Privacy Rules — LOCKED



Students must NEVER receive participant identity information.



Student-facing responses must not expose:

\- participant names

\- SRNs/PRNs

\- phone numbers

\- branch

\- program

\- semester

\- section

\- campus

\- participant user IDs

\- `user\_snapshot`

\- other participant details



Admin/faculty functionality may later expose appropriate accountability information.



\---



\## 5. RR Facility Inventory — LOCKED



There are exactly 11 initial RR facilities:



\### Badminton

\- Badminton Court 1 — capacity 6

\- Badminton Court 2 — capacity 6

\- Badminton Court 3 — capacity 6



\### Table Tennis

\- Table Tennis Table 1 — capacity 6

\- Table Tennis Table 2 — capacity 6

\- Table Tennis Table 3 — capacity 6



\### Squash

\- Squash Court 1 — capacity 6

\- Squash Court 2 — capacity 6



\### Basketball

\- Basketball Court 1 — capacity 12

\- Basketball Court 2 — capacity 12



\### Volleyball

\- Volleyball Court 1 — capacity 12



All:

\- campus = RR

\- active

\- deterministic sort order



Do not invent additional facilities.



\---



\## 6. Data Model Status



Current redesigned models include:



\### User

Relevant fields:

\- prn

\- phone

\- semester

\- section

\- auth\_provider

\- updated\_at



\### Facility

Relevant fields:

\- `\_id`

\- campus

\- sport

\- facility\_type

\- name

\- display\_name

\- capacity

\- is\_active

\- sort\_order

\- created\_at

\- updated\_at



\### Slot

Relevant fields:

\- facility\_id

\- facility\_name

\- duration\_minutes

\- slot\_type

\- leader\_user\_id

\- override\_reason

\- notes

\- is\_manual

\- updated\_at



\### Booking / participation

Relevant fields:

\- user\_id

\- facility\_id

\- joined\_at

\- cancelled\_by

\- is\_leader

\- user\_snapshot



User snapshot contains appropriate historical fields such as:

\- name

\- srn

\- phone

\- branch

\- program

\- semester

\- section

\- campus



Historical snapshots should be retained for accountability.



\---



\## 7. Schedule Architecture — LOCKED



Use a hybrid schedule-template architecture.



MongoDB stores active schedule templates for configurability.



Python seed/config scripts provide initial RR defaults.



The slot generator reads templates from MongoDB. Do NOT hardcode sport-specific schedule logic into the generator.



Manual faculty/admin slots are stored as actual slots and must not be overwritten by generation.



\### Schedule template fields



Main fields:



\- `\_id`

\- campus

\- sport

\- facility\_id

\- facility\_name

\- facility\_scope

\- day\_type

\- periods

\- is\_active

\- priority

\- effective\_from

\- effective\_until

\- created\_by

\- created\_at

\- updated\_at

\- notes



Period fields:



\- start\_time

\- end\_time

\- period\_type

\- duration\_minutes

\- is\_bookable

\- label

\- notes



`facility\_scope`:

\- `sport`

\- `facility`



`day\_type`:

\- `weekday`

\- `saturday`

\- `sunday`

\- `holiday`



\### Template resolution



When generating:



1\. Active facility-specific template wins over sport-level template.

2\. Inactive templates are ignored.

3\. Effective date range must be respected.

4\. Highest priority wins.

5\. If priority ties, newest `updated\_at` wins.

6\. Sport-level template is fallback.



Day resolution:

\- Monday–Friday → `weekday`

\- Saturday → `saturday`

\- Sunday → `sunday`

\- Holiday support is planned separately.



Initially, holiday behavior should mirror Sunday when holiday functionality is implemented.



\---



\## 8. Schedule Rules Currently Defined



\### Badminton Court 1 — weekday



\- 06–07 staff

\- 07–08 staff

\- 08–09 cleaning

\- 09–10 student

\- 10–11 student

\- 11–12 student

\- 12–13 student

\- 13–14 lunch

\- 14–15 student

\- 15–16 student

\- 16–17 staff

\- 17–18 staff

\- 18–19 staff



\### Badminton Court 1 — Sunday/initial holiday behavior



\- 06–07 staff

\- 07–08 staff

\- 08–09 cleaning

\- 09–10 student

\- ends at 10



\### Badminton sport-level — Sunday/holiday pattern



\- 06–07 student

\- 07–08 student

\- 08–09 cleaning

\- 09–10 student

\- ends at 10



\### Table Tennis — weekday



Same general student schedule pattern as sport-level Badminton.



\### Table Tennis — Sunday/holiday



Same sport-level Sunday pattern:

\- 06–07 student

\- 07–08 student

\- 08–09 cleaning

\- 09–10 student

\- ends at 10



\### Squash — Sunday/holiday



Same sport-level Sunday pattern.



\### Basketball — weekday



Student:

\- 09–10

\- 10–11

\- 11–12

\- 12–13



Lunch:

\- 13–14



Student:

\- 14–15

\- 15–16

\- 16–17

\- 17–18

\- 18–19



No cleaning period is currently specified for Basketball.



\### Volleyball — weekday



Same broad 09–19 pattern as Basketball with:

\- 13–14 lunch

\- student periods before and after lunch



Do NOT invent Basketball/Volleyball holiday schedules until requirements are known.



Cleaning/lunch/staff periods are non-bookable blockers and should not become student slots.



\---



\## 9. Slot Generation Status



Implemented:



`generate\_slots\_for\_date(db, target\_date, campus="RR")`



Current behavior:

\- Resolves schedule templates from MongoDB.

\- Uses facility-specific template before sport fallback.

\- Respects active/effective/priority rules.

\- Generates normal slots as 1-hour slots unless template specifies otherwise.

\- Generated slot identity includes:

&#x20; - campus

&#x20; - facility\_id

&#x20; - date

&#x20; - start\_time

&#x20; - end\_time

&#x20; - slot\_type = generated

\- Uses atomic upsert / `$setOnInsert`.

\- Rerunning generation must NOT reset:

&#x20; - booked\_count

&#x20; - status

&#x20; - leader

&#x20; - existing booking state

\- Manual slots are never modified/deleted by normal generation.

\- Manual overlaps are reported rather than silently overwritten.



\---



\## 10. Student Slot Retrieval Status



Student available-slot retrieval has been redesigned to be facility-aware.



Existing legacy response fields must remain compatible:



\- sport

\- venue

\- date

\- start\_time

\- end\_time

\- capacity

\- booked\_count

\- available\_count

\- status



Additional fields:



\- facility\_id

\- facility\_name

\- duration\_minutes

\- slot\_type

\- is\_manual



`venue` may fall back to `facility\_name`.



`available\_count = max(capacity - booked\_count, 0)`.



Student retrieval must never expose participant identities.



Only appropriate open/full student-bookable slots should be returned; closed/cancelled slots are not student-available.



\---



\## 11. Current Implementation Status



Completed:



\### Phase 0

Preparation/Git safety.



\### Phase 1

Database/facility redesign:

\- user model updates

\- slot model updates

\- booking model updates

\- facility model/schema

\- database indexes

\- RR facility seed



\### Phase 2

Schedule and slot system:

\- schedule template model/schema

\- RR schedule seed

\- slot generation service

\- generator tests

\- facility-aware student retrieval

\- generator hardening

\- manual overlap detection



\### Phase 3 Step 1A

Participation schemas:

\- UserSnapshotSchema

\- booking participation fields

\- slot leader\_user\_id

\- participation tests



Runtime join/leave behavior has NOT yet been fully redesigned.



\---



\## 12. Remaining Roadmap



Implement in small, focused steps:



1\. Phase 3 — Join/Leave backend

&#x20;  - join participation

&#x20;  - leave/cancellation

&#x20;  - leader promotion

&#x20;  - bans

&#x20;  - daily limit

&#x20;  - overlap checks

&#x20;  - historical participation

&#x20;  - atomic capacity handling



2\. Phase 4 — Student frontend

&#x20;  - facility-aware slot display

&#x20;  - availability

&#x20;  - join/leave

&#x20;  - student-safe responses

&#x20;  - dashboard integration



3\. Phase 5 — Admin/faculty

&#x20;  - participant visibility

&#x20;  - occupancy

&#x20;  - accountability/history

&#x20;  - management views



4\. Phase 6 — Manual faculty/admin slots

&#x20;  - arbitrary durations

&#x20;  - overrides

&#x20;  - manual slot creation/editing

&#x20;  - conflict/overlap handling



5\. Phase 7 — Holidays / closures

&#x20;  - holidays

&#x20;  - facility closures

&#x20;  - campus closures

&#x20;  - approval/workflow if required



6\. Final integration

&#x20;  - WebSockets/live updates

&#x20;  - integration tests

&#x20;  - bug fixes

&#x20;  - deployment polish



Do not implement future phases unless explicitly requested.



\---



\## 13. Development Rules for Claude Code



\### Scope



For every task:

\- Implement ONLY the requested step.

\- Do not start future phases.

\- Do not perform unrelated refactors.

\- Do not redesign already-locked architecture.

\- Prefer the smallest clean change that satisfies the requirement.



\### Repository inspection



\- Inspect only files directly relevant to the current task.

\- Do not read the entire repository unnecessarily.

\- Do not repeatedly rediscover architecture already documented here.

\- Before modifying something, inspect the relevant existing implementation.



\### Compatibility



\- Preserve existing working behavior unless the current task explicitly changes it.

\- Preserve legacy API response fields when practical.

\- Avoid breaking existing tests/routes/models unnecessarily.



\### Backend



\- Keep business logic in Python services.

\- Keep routers thin.

\- Backend is authoritative for booking rules.

\- Use MongoDB atomic operations where concurrency matters.

\- Do not rely on frontend validation for security/business rules.



\### Testing



\- Add focused tests for new behavior.

\- Run focused relevant tests rather than the entire repository unless needed.

\- For FastAPI/API changes, perform a focused API/OpenAPI smoke check when useful.

\- Do not spend tokens on unrelated verification.



\### Files / generated artifacts



\- Do not create unnecessary files.

\- Do not modify or commit `\_\_pycache\_\_` files.

\- Do not add generated artifacts unless required.



\### Git



\- Do NOT commit or push unless explicitly asked.

\- User handles commits/pushes manually.

\- Do not change branches.

\- Current development branch: `slot-system-redesign`.



\### Reporting



After completing a requested task, report briefly:



1\. What was implemented

2\. Files changed

3\. Focused tests/checks run

4\. Any blockers or assumptions



Do not provide a long explanation unless requested.



\---



\## Token-Efficient Claude Workflow



\- Keep implementation work narrowly scoped to the requested feature.

\- Do not inspect the whole repository or reread unrelated files.

\- Do not re-read CLAUDE.md sections repeatedly once the relevant rule is known.

\- Do not perform broad architectural reviews unless explicitly requested.

\- Do not run full test suites after every change; run only focused tests for the changed behavior.

\- Do not run lint/build unless the changed files make them relevant or the task explicitly requests them.

\- Do not produce lengthy implementation reports; report only files changed, focused test result, and important blockers.

\- Do not proactively refactor, clean up, rename, or improve unrelated code.

\- Do not create extra documentation unless explicitly requested.

\- Prefer modifying existing code paths over introducing abstractions.

\- When requirements are already established in CLAUDE.md, follow them directly instead of rediscovering them from the repository.

\- Do not use Claude for Git commit/push operations; the developer handles Git.

\- At checkpoints, do not perform another review unless there is evidence of a problem.



Minimize context reading and tool usage. Correctness is required, but unnecessary inspection and verification are not.



\---



\## 14. Important "Do Not" Rules



Do NOT:



\- invent missing facility schedules

\- invent EC requirements

\- expose participant identities to students

\- prevent multiple participants from joining the same slot

\- reset existing bookings during slot regeneration

\- delete historical participation on cancellation

\- allow cancelled users to rejoin the same slot

\- put critical booking rules only in React

\- silently overwrite manual slots

\- introduce unrelated architecture changes

\- perform broad repository refactors

\- commit/push without explicit instruction



When requirements are genuinely missing, preserve the existing architecture and ask only the minimum necessary clarification.



\---



\## 15. Source of Truth



This file contains the project's current locked architecture and business rules.



However:

\- The actual codebase is authoritative for implementation details.

\- If this file conflicts with an explicit new user instruction, follow the new explicit instruction and update this file when the decision becomes permanent.

\- Do not silently change locked rules.

\- Keep this file updated after major permanent architecture/business-rule decisions.

