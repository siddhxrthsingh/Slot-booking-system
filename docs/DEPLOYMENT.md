# Deployment Guide

Target architecture:

- **Frontend** — Vercel (React/Vite, `frontend/frontend`)
- **Backend** — Render (FastAPI, `backend`)
- **Database** — MongoDB Atlas
- **PESUAuth** — existing external service (no changes needed)

This document only describes configuration. No deployment has been performed and no accounts have been created by this change.

## 1. Backend on Render

- Root directory: `backend`
- Build command: `pip install -r requirements.txt`
- Start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
  (Render injects `$PORT`; the app already binds via Uvicorn, no code change needed.)
- A `render.yaml` at the repo root documents this (Render Blueprint format). Secret-bearing variables are marked `sync: false` and must be entered manually in the Render dashboard — none are stored in the repo.

### Required backend environment variables

| Variable | Notes |
|---|---|
| `APP_ENV` | Set to `production` |
| `SECRET_KEY` | Strong random value, required in production |
| `MONGO_URI` | MongoDB Atlas connection string |
| `MONGO_DB_NAME` | e.g. `slot_booking` |
| `PESU_AUTH_URL` | Existing PESUAuth endpoint |
| `FRONTEND_ORIGIN` | Exact Vercel production URL (comma-separate multiple origins, e.g. preview + prod, with no spaces) — used for CORS |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Existing default 60 is fine |
| `REFRESH_TOKEN_EXPIRE_DAYS` | Existing default 1 is fine |
| `RATE_LIMIT_LOGIN` | Existing default `10/minute` is fine |
| `ADMIN_EMPLOYEE_ID`, `ADMIN_PASSWORD`, `ADMIN_NAME`, `ADMIN_EMAIL` | Change from defaults before going live |
| `CANCEL_WINDOW_HOURS`, `BAN_DURATION_DAYS` | Booking policy, defaults 2 and 2 |
| `SMTP_*` | Optional — leave blank to keep email notifications disabled |

All of these already exist in `backend/app/config.py` / `backend/.env.example`; no new variable names were introduced.

## 2. Frontend on Vercel

- Root directory: `frontend/frontend`
- Build command: `npm run build` (Vite default, no change needed)
- Output directory: `dist`

### Required frontend environment variables

| Variable | Notes |
|---|---|
| `VITE_API_BASE_URL` | Full Render backend URL, **no trailing slash and no `/api` suffix** (e.g. `https://pesu-slot-booking-backend.onrender.com`). Backend routes are mounted at `/auth`, `/bookings`, `/admin` directly — the `/api` prefix used in local dev only exists because of the Vite dev proxy rewrite in `vite.config.js`, and does not apply in production. |
| `VITE_WS_BASE_URL` | Full WebSocket URL of the Render backend (e.g. `wss://pesu-slot-booking-backend.onrender.com`). Required because frontend and backend are on different hosts in production — see `src/hooks/wsBaseUrl.js`. |

Both variables already exist in the frontend source (`src/api/client.js`, `src/hooks/wsBaseUrl.js`); this task did not add new ones.

## 3. WebSocket configuration

- Backend exposes `/ws` and `/ws/occupancy` directly on the FastAPI app (no `/api` prefix).
- With `VITE_WS_BASE_URL` set to the Render backend's `wss://` origin, the frontend connects cross-host correctly. Render supports WebSockets on its web services by default — no extra config needed.

## 4. CORS

- `FRONTEND_ORIGIN` (backend) must exactly match the deployed Vercel origin(s), comma-separated if there is more than one (e.g. production + a preview domain). `CORSMiddleware` in `backend/app/main.py` already reads this via `settings.frontend_origins`.

## 5. MongoDB Atlas

- Only `MONGO_URI` (and `MONGO_DB_NAME`) need to be set to the Atlas connection string — no other backend code changes are required. Ensure Atlas Network Access allows connections from Render's IPs (or `0.0.0.0/0` if using Atlas's shared-tier constraints).

## 6. Secrets

- No secrets are committed. `backend/.env` is git-ignored; `backend/.env.example` documents variable names with placeholder values only. `render.yaml` marks every sensitive variable `sync: false` so real values are entered directly in the Render dashboard, never in the repo.

## Manual steps still required (not performed by this change)

1. Create the MongoDB Atlas cluster/project and obtain `MONGO_URI`.
2. Create the Render web service (via Blueprint using `render.yaml`, or manually) and set the `sync: false` env vars in its dashboard.
3. Create the Vercel project pointed at `frontend/frontend` and set `VITE_API_BASE_URL` / `VITE_WS_BASE_URL` once the Render URL is known.
4. After the Vercel URL is known, set `FRONTEND_ORIGIN` on Render to that exact URL and redeploy the backend.
5. Run `seed_facilities.py` / `seed_schedule_templates.py` (and any other seed scripts) against the Atlas database as needed.
