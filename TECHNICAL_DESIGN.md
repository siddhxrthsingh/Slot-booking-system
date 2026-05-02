# Slot Booking System - Technical High-Level Design

## 1. System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    FRONTEND (React + Vite)                  │
│  - Dashboard (View available slots)                          │
│  - Booking Management (Create/Cancel bookings)              │
│  - Admin Panel (Manage slots, approvals)                    │
└────────────────────┬────────────────────────────────────────┘
                     │ REST API + JWT
┌────────────────────▼────────────────────────────────────────┐
│              BACKEND (Python - FastAPI)                      │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────────────┐ │
│  │   Auth      │  │  Bookings    │  │  Admin/Slots       │ │
│  │ Service     │  │  Service     │  │  Service           │ │
│  └─────────────┘  └──────────────┘  └────────────────────┘ │
└────────────────────┬────────────────────────────────────────┘
                     │
        ┌────────────┼────────────┐
        │            │            │
┌───────▼──┐  ┌──────▼─────┐  ┌──▼──────────┐
│ MongoDB  │  │  PESUAuth  │  │  JWT/Auth   │
│ Database │  │  API       │  │  Tokens     │
└──────────┘  └────────────┘  └─────────────┘
```

---

## 2. Frontend Architecture

### Components
- **Authentication**: Login page (SRN + Password)
- **Student Dashboard**: View available slots, my bookings, upcoming events
- **Admin Panel**: Manage all bookings, approve/reject, create slots
- **Booking Flow**: Select sport → Choose slot → Confirm booking

### Tech Stack
| Tool | Choice | Reason |
|------|--------|--------|
| Framework | React 18 | Already in use |
| Build Tool | Vite | Already configured |
| Styling | Tailwind CSS | Already configured |
| State Management | TBD | Context API or Redux? |
| HTTP Client | Axios/Fetch | For API calls |
| Auth Storage | LocalStorage/SessionStorage | Store JWT tokens |

### Key Decisions
- **State Management**: Should we use Context API (simple) or Redux (scalable)?
- **Token Storage**: LocalStorage (persistent but less secure) vs SessionStorage (session-only)?
- **Error Handling**: Centralized error boundary or per-component?

---

## 3. Backend Architecture

### Core Services

#### 3.1 Authentication Service
```
POST /auth/login
├─ Input: username (SRN/Email), password
├─ Call PESUAuth API
├─ If Success: Create user record + JWT token
├─ Response: { access_token, refresh_token, user_profile }
└─ Error: 401 Unauthorized

POST /auth/refresh
├─ Input: refresh_token
├─ Validate refresh token in MongoDB
├─ Generate new access_token
└─ Response: { access_token }

POST /auth/logout
├─ Invalidate refresh token
└─ Response: { status: "success" }
```

#### 3.2 Bookings Service
```
GET /bookings/available
├─ Filter by sport, date, campus
└─ Return: List of open slots

POST /bookings/create
├─ Input: sport_id, slot_id
├─ Check availability & user quota
├─ Create booking record
├─ Return: { booking_id, status }
└─ Possible Status: "confirmed" or "pending_approval"

GET /bookings/my-bookings
├─ Auth: JWT required
├─ Return: User's bookings
└─ Include: status, cancellation window

DELETE /bookings/:id
├─ Auth: JWT required
├─ Check cancellation policy
└─ Return: { status: "cancelled" }
```

#### 3.3 Admin Service
```
GET /admin/slots
├─ Auth: Admin JWT required
├─ Return: All slots with occupancy

POST /admin/slots/create
├─ Create new sport slot
├─ Input: sport, date, time, capacity, venue
└─ Return: slot_id

GET /admin/bookings/pending
├─ Return: Bookings awaiting approval

PATCH /admin/bookings/:id/approve
├─ Approve/Reject booking
└─ Notify user

GET /admin/metrics
├─ Dashboard stats: active slots, occupancy %, pending approvals
└─ Return: analytics data
```

### Tech Stack
| Component | Choice | Reason |
|-----------|--------|--------|
| Framework | FastAPI | Modern, async, auto-documentation |
| Database | MongoDB | Already in use, flexible schema |
| Auth | JWT + PESUAuth | Stateless + university credentials |
| Validation | Pydantic | Built-in type validation |
| CORS | FastAPI-CORS | Handle cross-origin requests |
| Logging | Python logging | Track errors and audits |

### Database Schema

```javascript
// Users Collection
{
  _id: ObjectId,
  srn: "PES1201800001",
  email: "student@pesu.ac.in",
  name: "John Doe",
  program: "B.Tech",
  branch: "CSE",
  campus: "RR",
  role: "student" | "admin",
  created_at: Date,
  last_login: Date
}

// Slots Collection
{
  _id: ObjectId,
  sport_id: ObjectId,
  date: Date,
  start_time: "14:00",
  end_time: "15:00",
  venue: "Main Turf Arena",
  capacity: 20,
  booked_count: 18,
  status: "open" | "full" | "cancelled",
  created_by: ObjectId (admin),
  created_at: Date
}

// Bookings Collection
{
  _id: ObjectId,
  user_id: ObjectId,
  slot_id: ObjectId,
  sport_id: ObjectId,
  status: "confirmed" | "pending_approval" | "cancelled",
  booking_date: Date,
  cancelled_at: Date,
  notes: String,
  created_at: Date,
  updated_at: Date
}

// Sessions Collection (for refresh tokens)
{
  _id: ObjectId,
  user_id: ObjectId,
  refresh_token_hash: String,
  expires_at: Date,
  ip_address: String,
  created_at: Date
}
```

---

## 4. Authentication Flow

```
User Login:
1. Frontend: Send SRN + Password to /auth/login
2. Backend: Validate with PESUAuth API
3. If Valid:
   - Create/Update user in MongoDB
   - Fetch profile (name, branch, campus, etc)
   - Generate Access Token (15 min) + Refresh Token (7 days)
   - Store refresh token hash in Sessions collection
4. Response: { access_token, refresh_token, user: {...} }
5. Frontend: Store tokens, redirect to dashboard

Token Refresh:
1. Access token expires
2. Frontend detects 401, sends refresh_token to /auth/refresh
3. Backend: Validate refresh token against database
4. Generate new access_token
5. Frontend: Retry original request with new token

Logout:
1. Frontend: Send DELETE /auth/logout
2. Backend: Delete refresh token from Sessions
3. Frontend: Clear localStorage/sessionStorage
```

---

## 5. Security Considerations

| Concern | Decision | Implementation |
|---------|----------|-----------------|
| **Password Storage** | Don't store | Delegate to PESUAuth API |
| **Token Security** | JWT in localStorage | Consider httpOnly cookies as alternative |
| **CORS** | Whitelist frontend domain | Only allow frontend origin |
| **Rate Limiting** | Implement on login | Prevent brute force |
| **User Roles** | student \| admin | Check role in protected routes |
| **Session Tracking** | Store refresh tokens | Invalidate old sessions |
| **Sensitive Data** | Log sparingly | No passwords, tokens in logs |

---

## 6. Key Design Decisions & Tradeoffs

### Decision 1: Stateless JWT vs Stateful Sessions
- **Choice**: JWT + Refresh Tokens (Stateless with session tracking)
- **Pros**: Scalable, no session server needed, works with microservices
- **Cons**: Token revocation needs database lookup
- **Alternative**: Traditional sessions with cookies (simpler but less scalable)

### Decision 2: Booking Approval Workflow
- **Choice**: Optional approval queue (Admin can approve/reject)
- **Pros**: Admin control, flexibility
- **Cons**: Extra latency for users
- **Alternative**: Auto-confirm bookings (faster but less control)

### Decision 3: Database Transactions
- **Choice**: MongoDB (eventual consistency)
- **Risk**: Overbooking if two users book last slot simultaneously
- **Mitigation**: Check availability atomically before booking
- **Alternative**: PostgreSQL with ACID (slower but safer)

### Decision 4: Real-time Slot Updates
- **Current**: Polling (Frontend checks every N seconds)
- **Alternative**: WebSockets (real-time but more complex)
- **Decision Needed**: Is real-time essential or polling acceptable?

---

## 7. Open Questions / Decisions Needed

1. **Approval Workflow**: Should all bookings auto-confirm, or require admin approval?
2. **Booking Limits**: Can a student book multiple slots per day? Per week?
3. **Cancellation Policy**: How long before slot must users cancel? Any penalty?
4. **Role-Based Access**: Should instructors/faculty have special privileges?
5. **Campus Support**: Separate slots per campus (RR/EC) or shared?
6. **Notifications**: Email/SMS for booking confirmation and cancellations?
7. **Audit Trail**: Log all booking changes for compliance?
8. **Search/Filter**: What filters matter most? (Sport, date, time, venue, campus)
9. **Bulk Operations**: Admin ability to create multiple slots at once?
10. **Timezone Handling**: How to handle students from different zones?

---

## 8. Deployment & DevOps

| Layer | Deployment | Considerations |
|-------|------------|-----------------|
| Frontend | Vercel / Netlify | Static hosting, CDN |
| Backend | AWS EC2 / Heroku | Python app hosting |
| Database | MongoDB Atlas | Cloud MongoDB |
| Auth | PESUAuth API | External, no hosting needed |

---

## 9. API Response Format (Standardized)

```json
// Success
{
  "status": true,
  "data": { /* payload */ },
  "message": "Operation successful",
  "timestamp": "2024-05-02T10:30:00Z"
}

// Error
{
  "status": false,
  "error": "invalid_slot",
  "message": "Slot not available",
  "timestamp": "2024-05-02T10:30:00Z"
}
```

---

## 10. Development Timeline (Estimated)

| Phase | Duration | Deliverables |
|-------|----------|--------------|
| Phase 1: Setup | 1-2 days | Backend scaffold, DB schema |
| Phase 2: Auth | 2-3 days | Login, token refresh, logout |
| Phase 3: Bookings | 3-4 days | Create, view, cancel bookings |
| Phase 4: Admin | 2-3 days | Slot management, approvals |
| Phase 5: Frontend Integration | 4-5 days | Connect React to APIs |
| Phase 6: Testing & Deployment | 2-3 days | Unit tests, integration, go-live |

---

## Next Steps

1. **Confirm open questions** (Section 7)
2. **Choose state management** solution for frontend
3. **Decide on approval workflow**
4. **Set up development environment**
5. **Begin Phase 1: Backend setup**
