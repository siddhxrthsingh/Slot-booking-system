import { useState } from "react";

const sports = [
  {
    name: "Football",
    image: "/images/football.jpg",
    venue: "Main Turf Arena",
    availability: "14 slots open today",
    accent: "Evening practice blocks and inter-department matches",
    nextSlot: "Today, 5:30 PM",
  },
  {
    name: "Basketball",
    image: "/images/basketball.jpg",
    venue: "Indoor Hoop Court",
    availability: "9 slots open today",
    accent: "Quick drills, team scrims, and PE activity bookings",
    nextSlot: "Today, 4:15 PM",
  },
  {
    name: "Tennis",
    image: "/images/tennis.jpg",
    venue: "Ace Courts",
    availability: "6 slots open today",
    accent: "Singles and doubles sessions with faculty supervision",
    nextSlot: "Tomorrow, 7:00 AM",
  },
  {
    name: "Cricket",
    image: "/images/cricket.jpg",
    venue: "Practice Nets",
    availability: "11 slots open today",
    accent: "Net sessions, bowling drills, and team trials access",
    nextSlot: "Today, 6:00 PM",
  },
  {
    name: "Swimming",
    image: "/images/swimming.jpg",
    venue: "Aquatic Center",
    availability: "18 slonnts open today",
    accent: "Lane-wise attendance tracking for training hours",
    nextSlot: "Today, 3:30 PM",
  },
];

const studentBookings = [
  {
    sport: "Football",
    slot: "24 Apr, 5:30 PM to 6:30 PM",
    venue: "Main Turf Arena",
    status: "Confirmed",
  },
  {
    sport: "Swimming",
    slot: "25 Apr, 7:00 AM to 8:00 AM",
    venue: "Aquatic Center",
    status: "Pending approval",
  },
];

const announcements = [
  "Inter-college football selections begin on 26 April.",
  "Basketball court B will be under maintenance on Sunday morning.",
  "Swimming attendance is now mandatory for all coached sessions.",
];

const upcomingEvents = [
  { title: "Campus Sports Fest", time: "27 Apr, 10:00 AM" },
  { title: "Faculty vs Students Cricket", time: "29 Apr, 4:30 PM" },
  { title: "Tennis Ladder Matches", time: "30 Apr, 6:30 AM" },
];

const adminMetrics = [
  { label: "Active slots", value: "58" },
  { label: "Current occupancy", value: "76%" },
  { label: "Pending approvals", value: "12" },
  { label: "Today activity", value: "143 actions" },
];

const adminBookings = [
  {
    student: "Riya N",
    srn: "PES2UG23CS101",
    sport: "Basketball",
    slot: "24 Apr, 4:15 PM",
    status: "Pending",
  },
  {
    student: "Arjun M",
    srn: "PES2UG23ME088",
    sport: "Cricket",
    slot: "24 Apr, 6:00 PM",
    status: "Approved",
  },
  {
    student: "Neha K",
    srn: "PES2UG24EC044",
    sport: "Swimming",
    slot: "25 Apr, 7:00 AM",
    status: "Pending",
  },
];

function Dashboard() {
  const [activePortal, setActivePortal] = useState("student");

  const isStudent = activePortal === "student";

  return (
    <main className="dashboard">
      <header className="topbar">
        <div>
          <p className="brand-kicker">College Sports Slot Booking</p>
          <h1 className="brand-title">Campus Arena</h1>
        </div>
        <div className="portal-switch" role="tablist" aria-label="Portal switcher">
          <button
            className={isStudent ? "switch-chip active" : "switch-chip"}
            onClick={() => setActivePortal("student")}
            type="button"
          >
            Student Portal
          </button>
          <button
            className={!isStudent ? "switch-chip active" : "switch-chip"}
            onClick={() => setActivePortal("admin")}
            type="button"
          >
            Teacher / Admin
          </button>
        </div>
      </header>

      <section className="hero-panel">
        <div
          className="hero-copy hero-media"
          style={{ backgroundImage: 'linear-gradient(135deg, rgba(5, 8, 20, 0.84), rgba(93, 63, 211, 0.48)), url("/images/football.jpg")' }}
        >
          <p className="eyebrow">
            {isStudent ? "Student Sports Access" : "Teacher and Admin Control"}
          </p>
          <h2 className="hero-title">
            {isStudent
              ? "Reserve college sports slots with your SRN and manage bookings in one place."
              : "Create, approve, and monitor campus sports slots from a single control dashboard."}
          </h2>
          <p className="hero-text">
            {isStudent
              ? "Students can sign in using SRN and password, explore open sports slots, book courts or pools, and cancel existing reservations without the clutter."
              : "Teachers and admins get a dedicated login, slot creation tools, booking approvals, cancellation controls, and a live activity overview for campus facilities."}
          </p>
          <div className="hero-stats">
            <div>
              <strong>5</strong>
              <span>Sports open</span>
            </div>
            <div>
              <strong>58</strong>
              <span>Available slots</span>
            </div>
            <div>
              <strong>Live</strong>
              <span>Occupancy tracking</span>
            </div>
          </div>
        </div>

        <div
          className="hero-highlight hero-media"
          style={{ backgroundImage: 'linear-gradient(180deg, rgba(12, 14, 30, 0.3), rgba(12, 14, 30, 0.92)), url("/images/cricket.jpg")' }}
        >
          <span className="highlight-label">
            {isStudent ? "Most requested today" : "Operations snapshot"}
          </span>
          <h2>
            {isStudent
              ? "Football, cricket, and swimming slots are moving fastest this evening."
              : "Slot approvals and occupancy spikes are visible the moment activity starts."}
          </h2>
          <p>
            {isStudent
              ? "Use the booking cards below to pick a sport, see slot counts instantly, and reserve a place before the next student rush."
              : "Monitor availability, confirm students quickly, and cancel or adjust sessions without losing track of recent booking activity."}
          </p>
        </div>
      </section>

      <section className="portal-grid">
        <article className="panel auth-panel">
          <div className="panel-header">
            <p className="eyebrow">{isStudent ? "Student Login" : "Teacher / Admin Login"}</p>
            <h3>{isStudent ? "Sign in with SRN" : "Separate faculty access"}</h3>
          </div>

          <div className="auth-fields">
            <label>
              <span>{isStudent ? "SRN" : "Employee ID / Admin ID"}</span>
              <input
                type="text"
                placeholder={isStudent ? "Enter SRN" : "Enter faculty ID"}
                readOnly
              />
            </label>
            <label>
              <span>Password</span>
              <input type="password" placeholder="Enter password" readOnly />
            </label>
          </div>

          <button className="primary-button" type="button">
            {isStudent ? "Login to student dashboard" : "Login to admin dashboard"}
          </button>

          <div className="auth-note">
            {isStudent
              ? "Book a slot, view upcoming sessions, and cancel bookings from your dashboard."
              : "Create slots, set max seats, approve or reject requests, and track live occupancy."}
          </div>
        </article>

        <article className="panel summary-panel">
          <div className="panel-header">
            <p className="eyebrow">{isStudent ? "Quick Overview" : "Live Dashboard"}</p>
            <h3>{isStudent ? "Today on campus" : "Operations pulse"}</h3>
          </div>

          <div className="mini-grid">
            {(isStudent ? adminMetrics.slice(0, 3) : adminMetrics).map((metric) => (
              <div className="mini-stat" key={metric.label}>
                <strong>{metric.value}</strong>
                <span>{metric.label}</span>
              </div>
            ))}
          </div>

          <div className="activity-feed">
            <p className="feed-title">Recent activity</p>
            <ul>
              <li>Football slot at 5:30 PM reached 80% occupancy.</li>
              <li>Swimming session for 7:00 AM opened additional lanes.</li>
              <li>Cricket practice nets updated with revised max seats.</li>
            </ul>
          </div>
        </article>
      </section>

      {isStudent ? (
        <>
          <section className="sports-section">
            <div className="section-heading">
              <div>
                <p className="eyebrow">Available Sports</p>
                <h2>View available slots by sport</h2>
              </div>
              <p className="section-copy">
                Card-based sport listings keep slot counts clear, with consistent spacing
                and direct booking actions for students.
              </p>
            </div>

            <div className="sports-grid">
              {sports.map((sport) => (
                <article className="sport-card" key={sport.name}>
                  <div className="sport-image-wrap">
                    <img className="sport-image" src={sport.image} alt={sport.name} />
                    <span className="sport-badge">{sport.availability}</span>
                  </div>

                  <div className="sport-content">
                    <div className="sport-header">
                      <div>
                        <h3>{sport.name}</h3>
                        <p className="venue">{sport.venue}</p>
                      </div>
                      <span className="slot-pill">{sport.nextSlot}</span>
                    </div>

                    <p className="sport-accent">{sport.accent}</p>

                    <button className="primary-button" type="button">
                      Book slot
                    </button>
                  </div>
                </article>
              ))}
            </div>
          </section>

          <section className="content-grid">
            <article className="panel">
              <div className="panel-header">
                <p className="eyebrow">My Bookings</p>
                <h3>Manage upcoming reservations</h3>
              </div>
              <div className="booking-list">
                {studentBookings.map((booking) => (
                  <div className="booking-row" key={`${booking.sport}-${booking.slot}`}>
                    <div>
                      <strong>{booking.sport}</strong>
                      <p>{booking.slot}</p>
                      <span>{booking.venue}</span>
                    </div>
                    <div className="booking-actions">
                      <span className="status-chip">{booking.status}</span>
                      <button className="secondary-button" type="button">
                        Cancel booking
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </article>

            <article className="panel stacked-panel">
              <div>
                <div className="panel-header">
                  <p className="eyebrow">Announcements</p>
                  <h3>Notice board</h3>
                </div>
                <ul className="info-list">
                  {announcements.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              </div>

              <div>
                <div className="panel-header section-gap">
                  <p className="eyebrow">Upcoming Events</p>
                  <h3>Campus sports calendar</h3>
                </div>
                <div className="event-list">
                  {upcomingEvents.map((event) => (
                    <div className="event-row" key={event.title}>
                      <strong>{event.title}</strong>
                      <span>{event.time}</span>
                    </div>
                  ))}
                </div>
              </div>
            </article>
          </section>
        </>
      ) : (
        <>
          <section className="content-grid admin-grid">
            <article className="panel">
              <div className="panel-header">
                <p className="eyebrow">Create Slots</p>
                <h3>Configure new sports availability</h3>
              </div>
              <div className="form-grid">
                <label>
                  <span>Sport</span>
                  <input type="text" placeholder="Select sport" readOnly />
                </label>
                <label>
                  <span>Date</span>
                  <input type="text" placeholder="Choose date" readOnly />
                </label>
                <label>
                  <span>Time</span>
                  <input type="text" placeholder="Choose time" readOnly />
                </label>
                <label>
                  <span>Max seats</span>
                  <input type="text" placeholder="Set max seats" readOnly />
                </label>
              </div>
              <div className="button-row">
                <button className="primary-button" type="button">
                  Create slot
                </button>
                <button className="secondary-button" type="button">
                  Cancel slot
                </button>
              </div>
            </article>

            <article className="panel">
              <div className="panel-header">
                <p className="eyebrow">Occupancy</p>
                <h3>Live sport activity</h3>
              </div>
              <div className="sports-occupancy">
                {sports.map((sport) => (
                  <div className="occupancy-row" key={sport.name}>
                    <div>
                      <strong>{sport.name}</strong>
                      <span>{sport.availability}</span>
                    </div>
                    <div className="occupancy-bar">
                      <span style={{ width: `${55 + sport.name.length * 5}%` }} />
                    </div>
                  </div>
                ))}
              </div>
            </article>
          </section>

          <section className="panel bookings-panel">
            <div className="section-heading booking-heading">
              <div>
                <p className="eyebrow">Bookings Control</p>
                <h2>View, approve, or reject student requests</h2>
              </div>
              <p className="section-copy">
                Teachers and admins can review all bookings, act on requests, and
                keep slot occupancy under control from one interface.
              </p>
            </div>

            <div className="admin-booking-list">
              {adminBookings.map((booking) => (
                <div className="admin-booking-row" key={`${booking.srn}-${booking.slot}`}>
                  <div>
                    <strong>{booking.student}</strong>
                    <p>{booking.srn}</p>
                  </div>
                  <div>
                    <strong>{booking.sport}</strong>
                    <p>{booking.slot}</p>
                  </div>
                  <span className="status-chip">{booking.status}</span>
                  <div className="button-row compact">
                    <button className="primary-button compact-button" type="button">
                      Approve
                    </button>
                    <button className="secondary-button compact-button" type="button">
                      Reject
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </section>
        </>
      )}
    </main>
  );
}

export default Dashboard;
