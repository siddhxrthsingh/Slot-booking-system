# Slot Booking System — Backend

FastAPI backend for the PESU Slot Booking System.

## Tech Stack

| Layer | Choice |
|-------|--------|
| Framework | FastAPI 0.115 |
| Database | MongoDB (Motor async driver) |
| Auth | JWT (access + refresh) + PESUAuth |
| Validation | Pydantic v2 |
| Rate limiting | SlowAPI |

## Project Layout

```
backend/
├── app/
│   ├── main.py           # FastAPI app, startup/shutdown, CORS, routers
│   ├── config.py         # Pydantic settings (reads .env)
│   ├── database.py       # Motor MongoDB async client
│   ├── dependencies.py   # JWT auth guards (get_current_user, require_admin)
│   ├── utils.py          # Standard success/error response helpers
│   ├── models/           # MongoDB document shapes (Pydantic)
│   │   ├── user.py
│   │   ├── slot.py
│   │   ├── booking.py
│   │   └── session.py
│   ├── schemas/          # Request / response DTOs
│   │   ├── auth.py
│   │   ├── slot.py
│   │   └── booking.py
│   ├── routers/          # Route handlers
│   │   ├── auth.py
│   │   ├── bookings.py
│   │   └── admin.py
│   └── services/         # Business logic
│       ├── auth_service.py
│       ├── booking_service.py
│       └── admin_service.py
├── requirements.txt
├── .env.example
└── README.md
```

## Setup

### 1. Create virtual environment

```bash
python -m venv venv
# Windows
venv\Scripts\activate
# macOS/Linux
source venv/bin/activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure environment

```bash
cp .env.example .env
# Edit .env with your MongoDB URI, secret key, and PESUAuth URL
```

### 4. Run the server

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

API docs available at **http://localhost:8000/docs**

---

## API Overview

### Authentication (`/auth`)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/auth/login` | Login with SRN + password (PESUAuth) |
| POST | `/auth/refresh` | Get new access token using refresh token |
| POST | `/auth/logout` | Invalidate refresh token |
| GET  | `/auth/me` | Get current user profile |

### Bookings (`/bookings`)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/bookings/available` | Public | List available slots (filter by sport/date/campus/venue) |
| POST | `/bookings/create` | Student | Create a new booking |
| GET | `/bookings/my-bookings` | Student | Get own bookings |
| DELETE | `/bookings/{id}` | Student | Cancel a booking |

### Admin (`/admin`)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/admin/slots` | All slots with occupancy |
| POST | `/admin/slots/create` | Create a new slot |
| PATCH | `/admin/slots/{id}` | Update a slot |
| DELETE | `/admin/slots/{id}/cancel` | Cancel slot (cascades to bookings) |
| GET | `/admin/bookings` | All bookings |
| GET | `/admin/bookings/pending` | Bookings awaiting approval |
| PATCH | `/admin/bookings/{id}/approve` | Approve or reject a booking |
| GET | `/admin/metrics` | Dashboard analytics |

---

## Response Format

All endpoints return a standard envelope:

```json
// Success
{
  "status": true,
  "data": { ... },
  "message": "Operation successful",
  "timestamp": "2026-05-02T10:30:00Z"
}

// Error
{
  "status": false,
  "error": "invalid_slot",
  "message": "Slot not available",
  "timestamp": "2026-05-02T10:30:00Z"
}
```

---

## PESUAuth Integration

In **production**, set `PESU_AUTH_URL` to the real PESUAuth endpoint. The service sends:

```json
POST /api/login
{ "username": "PES1...", "password": "..." }
```

In **development** (`APP_ENV=development`), if the PESUAuth URL is unreachable, a mock profile is returned so you can test without credentials.

---

## MongoDB Collections

| Collection | Purpose |
|-----------|---------|
| `users` | Student & admin profiles |
| `slots` | Sport slots (date, time, venue, capacity) |
| `bookings` | Booking records (confirmed / pending / cancelled) |
| `sessions` | Hashed refresh tokens for session management |
