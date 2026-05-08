import { useState, useEffect, useCallback } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { useWebSocket } from '../hooks/useWebSocket';
import {
  getAvailableSlots,
  createBooking,
  getMyBookings,
  cancelBooking,
  getMyBanStatus,
} from '../api/bookings';
import {
  getMetrics,
  getPendingBookings,
  createSlot,
  updateSlot,
  cancelSlot,
  deleteSlotPermanently,
  getAllBookings,
  processBookingApproval,
  adminCancelBooking,
  getActiveBans,
  unbanUser,
  getAdminSlots,
} from '../api/admin';

// ── Sport metadata ────────────────────────────────────────────────────────────
const SPORT_META = {
  Football:       { image: '/images/football-hero.jpg', accent: 'Evening practice blocks and inter-department matches.' },
  Basketball:     { image: '/images/basketball.jpg',    accent: 'Quick drills, team scrims, and PE activity bookings.' },
  Cricket:        { image: '/images/cricket.jpg',       accent: 'Net sessions, bowling drills, and team trials access.' },
  Badminton:      { image: '/images/badminton.jpg',     accent: 'Singles and doubles court sessions for all skill levels.' },
  Volleyball:     { image: '/images/volleyball.jpg',    accent: 'Team practice sessions and inter-department tournaments.' },
  Squash:         { image: '/images/squash.jpg',        accent: 'Booked court sessions with equipment provided on site.' },
  'Table Tennis': { image: '/images/table-tennis.jpg',  accent: 'Competitive and casual table sessions in the indoor hall.' },
  Chess:          { image: '/images/chess.jpg',         accent: 'Strategy board game sessions and inter-college practice.' },
};

const announcements = [
  'Inter-college football selections begin this month.',
  'Basketball court B will be under maintenance on Sunday morning.',
  'Badminton and squash booking slots now open for RR campus.',
];
const upcomingEvents = [
  { title: 'Campus Sports Fest',              time: '27 Apr, 10:00 AM' },
  { title: 'Faculty vs Students Cricket',     time: '29 Apr, 4:30 PM' },
  { title: 'Chess Inter-Department Tournament', time: '30 Apr, 9:00 AM' },
];

const SPORTS_LIST = ['Football', 'Basketball', 'Cricket', 'Badminton', 'Volleyball', 'Squash', 'Table Tennis', 'Chess'];
const CAMPUSES    = ['RR', 'EC'];

// ── Helpers ───────────────────────────────────────────────────────────────────
function fmtStatus(s) {
  return (s || '').replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}
function fmtDate(d) {
  if (!d) return '';
  return new Date(d).toISOString().slice(0, 10);
}
function fmt(d) {
  if (!d) return '—';
  return new Date(d).toLocaleString('en-IN', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' });
}
function fmtBanDate(d) {
  if (!d) return '—';
  return new Date(d).toLocaleString('en-IN', { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' });
}

// ── Blank slot form ───────────────────────────────────────────────────────────
const BLANK_SLOT = {
  sport: 'Football', date: '', start_time: '', end_time: '',
  venue: '', campus: 'RR', capacity: '',
};

// ─────────────────────────────────────────────────────────────────────────────
export default function Dashboard() {
  const { user, logout, isAdmin } = useAuth();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();

  const [activePortal, setActivePortal] = useState(
    searchParams.get('portal') === 'admin' && isAdmin ? 'admin' : 'student'
  );

  // ── Student state ─────────────────────────────────────────────────────────
  const [slots,            setSlots]            = useState([]);
  const [slotsLoading,     setSlotsLoading]     = useState(true);
  const [myBookings,       setMyBookings]       = useState([]);
  const [bookingsLoading,  setBookingsLoading]  = useState(true);
  const [bookingInProgress,setBookingInProgress]= useState(null);
  const [cancelInProgress, setCancelInProgress] = useState(null);
  const [toast,            setToast]            = useState(null);
  const [banInfo,          setBanInfo]          = useState(null);

  // Student filters
  const [filterCampus, setFilterCampus] = useState('');
  const [filterSport,  setFilterSport]  = useState('');

  // ── Admin state ───────────────────────────────────────────────────────────
  const [metrics,           setMetrics]           = useState(null);
  const [pendingBookings,   setPendingBookings]   = useState([]);
  const [allBookings,       setAllBookings]       = useState([]);
  const [adminLoading,      setAdminLoading]      = useState(false);
  const [approvalInProgress,setApprovalInProgress]= useState(null);
  const [activeBans,        setActiveBans]        = useState([]);
  const [adminSlots,        setAdminSlots]        = useState([]);
  const [adminTab,          setAdminTab]          = useState('overview'); // overview | slots | bookings | bans

  // Admin slot creation form
  const [slotForm,       setSlotForm]       = useState(BLANK_SLOT);
  const [slotFormLoading,setSlotFormLoading]= useState(false);

  // Admin slot edit
  const [editingSlot,    setEditingSlot]    = useState(null); // slot object being edited
  const [editForm,       setEditForm]       = useState({});
  const [editLoading,    setEditLoading]    = useState(false);

  // Admin filters
  const [adminFilterCampus, setAdminFilterCampus] = useState('');
  const [adminFilterSport,  setAdminFilterSport]  = useState('');

  // ── Toast ─────────────────────────────────────────────────────────────────
  function showToast(msg, ok = true) {
    setToast({ msg, ok });
    setTimeout(() => setToast(null), 4000);
  }

  // ── Fetch helpers ─────────────────────────────────────────────────────────
  const fetchSlots = useCallback(async () => {
    setSlotsLoading(true);
    try {
      const params = {};
      if (filterCampus) params.campus = filterCampus;
      if (filterSport)  params.sport  = filterSport;
      const data = await getAvailableSlots(params);
      setSlots(data);
    } catch {
      showToast('Failed to load available slots.', false);
    } finally {
      setSlotsLoading(false);
    }
  }, [filterCampus, filterSport]);

  const fetchMyBookings = useCallback(async () => {
    setBookingsLoading(true);
    try {
      const data = await getMyBookings();
      setMyBookings(data);
    } catch {
      // silent
    } finally {
      setBookingsLoading(false);
    }
  }, []);

  const fetchBanStatus = useCallback(async () => {
    try {
      const b = await getMyBanStatus();
      setBanInfo(b.banned ? b : null);
    } catch {
      // silent
    }
  }, []);

  const fetchAdminData = useCallback(async () => {
    setAdminLoading(true);
    try {
      const params = {};
      if (adminFilterCampus) params.campus = adminFilterCampus;
      if (adminFilterSport)  params.sport  = adminFilterSport;
      const [m, pb, ab, bans, slots] = await Promise.all([
        getMetrics(),
        getPendingBookings(),
        getAllBookings(),
        getActiveBans(),
        getAdminSlots(params),
      ]);
      setMetrics(m);
      setPendingBookings(pb);
      setAllBookings(ab);
      setActiveBans(bans);
      setAdminSlots(slots);
    } catch {
      showToast('Failed to load admin data.', false);
    } finally {
      setAdminLoading(false);
    }
  }, [adminFilterCampus, adminFilterSport]);

  // ── Initial load ──────────────────────────────────────────────────────────
  useEffect(() => {
    fetchSlots();
    fetchMyBookings();
    fetchBanStatus();
  }, [fetchSlots, fetchMyBookings, fetchBanStatus]);

  useEffect(() => {
    if (activePortal === 'admin' && isAdmin) fetchAdminData();
  }, [activePortal, isAdmin, fetchAdminData]);

  // ── WebSocket live updates ────────────────────────────────────────────────
  const handleWsMessage = useCallback((msg) => {
    const refresh = () => {
      fetchSlots();
      fetchMyBookings();
      if (activePortal === 'admin' && isAdmin) fetchAdminData();
    };
    switch (msg.type) {
      case 'slot_created':
      case 'slot_updated':
      case 'slot_cancelled':
      case 'booking_created':
      case 'booking_cancelled':
      case 'booking_updated':
        refresh();
        break;
      default:
        break;
    }
  }, [fetchSlots, fetchMyBookings, fetchAdminData, activePortal, isAdmin]);

  useWebSocket(handleWsMessage, true);

  // ── Student actions ───────────────────────────────────────────────────────
  async function handleBook(slotId) {
    if (banInfo) {
      showToast(`Your booking access is suspended until ${fmtBanDate(banInfo.banned_until)}.`, false);
      return;
    }
    setBookingInProgress(slotId);
    try {
      await createBooking(slotId);
      showToast('Slot booked and confirmed!');
      fetchSlots();
      fetchMyBookings();
    } catch (err) {
      showToast(err.response?.data?.detail || 'Could not book slot.', false);
    } finally {
      setBookingInProgress(null);
    }
  }

  async function handleCancel(bookingId) {
    if (!window.confirm('Cancel this booking? Late cancellations (< 2 hours before) incur a 2-day booking ban.')) return;
    setCancelInProgress(bookingId);
    try {
      const result = await cancelBooking(bookingId);
      if (result.late_cancel) {
        showToast('Booking cancelled — late cancellation ban applied for 2 days.', false);
        fetchBanStatus();
      } else {
        showToast('Booking cancelled.');
      }
      fetchMyBookings();
      fetchSlots();
    } catch (err) {
      showToast(err.response?.data?.detail || 'Could not cancel booking.', false);
    } finally {
      setCancelInProgress(null);
    }
  }

  // ── Admin actions ─────────────────────────────────────────────────────────
  async function handleApproval(bookingId, action) {
    setApprovalInProgress(bookingId + action);
    try {
      await processBookingApproval(bookingId, action);
      showToast(`Booking ${action}d.`);
      fetchAdminData();
    } catch {
      showToast('Action failed.', false);
    } finally {
      setApprovalInProgress(null);
    }
  }

  async function handleCancelSlot(slotId) {
    if (!window.confirm('Cancel this slot and all its bookings?')) return;
    try {
      await cancelSlot(slotId);
      showToast('Slot cancelled.');
      fetchAdminData();
    } catch {
      showToast('Failed to cancel slot.', false);
    }
  }

  async function handleDeleteSlot(slotId) {
    if (!window.confirm('Permanently delete this slot and all its bookings? This cannot be undone.')) return;
    try {
      await deleteSlotPermanently(slotId);
      showToast('Slot deleted permanently.');
      fetchAdminData();
    } catch {
      showToast('Failed to delete slot.', false);
    }
  }

  async function handleAdminCancelBooking(bookingId) {
    if (!window.confirm('Force-cancel this student\'s booking?')) return;
    try {
      await adminCancelBooking(bookingId);
      showToast('Booking cancelled.');
      fetchAdminData();
    } catch (err) {
      showToast(err.response?.data?.detail || 'Failed to cancel booking.', false);
    }
  }

  async function handleUnban(userId) {
    if (!window.confirm('Lift this ban?')) return;
    try {
      await unbanUser(userId);
      showToast('Ban lifted.');
      fetchAdminData();
    } catch {
      showToast('Failed to lift ban.', false);
    }
  }

  async function handleCreateSlot(e) {
    e.preventDefault();
    if (!slotForm.date || !slotForm.start_time || !slotForm.end_time || !slotForm.venue || !slotForm.capacity) {
      showToast('Please fill in all fields.', false);
      return;
    }
    setSlotFormLoading(true);
    try {
      const payload = {
        ...slotForm,
        capacity: parseInt(slotForm.capacity, 10),
        date: new Date(slotForm.date).toISOString(),
      };
      await createSlot(payload);
      showToast('Slot created!');
      setSlotForm(BLANK_SLOT);
      fetchAdminData();
    } catch (err) {
      showToast(err.response?.data?.detail || 'Failed to create slot.', false);
    } finally {
      setSlotFormLoading(false);
    }
  }

  function startEditSlot(slot) {
    setEditingSlot(slot.id);
    setEditForm({
      sport:      slot.sport,
      venue:      slot.venue,
      campus:     slot.campus,
      capacity:   slot.capacity,
      start_time: slot.start_time,
      end_time:   slot.end_time,
      date:       fmtDate(slot.date),
    });
  }

  async function handleSaveEdit(slotId) {
    setEditLoading(true);
    try {
      const payload = { ...editForm, capacity: parseInt(editForm.capacity, 10) };
      if (editForm.date) payload.date = new Date(editForm.date).toISOString();
      await updateSlot(slotId, payload);
      showToast('Slot updated!');
      setEditingSlot(null);
      fetchAdminData();
    } catch (err) {
      showToast(err.response?.data?.detail || 'Failed to update slot.', false);
    } finally {
      setEditLoading(false);
    }
  }

  // ── Derived data ──────────────────────────────────────────────────────────
  const slotsBySport = slots.reduce((acc, s) => {
    if (!acc[s.sport]) acc[s.sport] = [];
    acc[s.sport].push(s);
    return acc;
  }, {});

  const displayedSports = filterSport
    ? SPORTS_LIST.filter(s => s === filterSport)
    : SPORTS_LIST;

  const metricCards = metrics
    ? [
        { label: 'Active slots',       value: metrics.slots.open + metrics.slots.full },
        { label: 'Occupancy',          value: `${metrics.occupancy_pct}%` },
        { label: 'Total bookings',     value: metrics.bookings.total },
        { label: 'Confirmed bookings', value: metrics.bookings.confirmed },
        { label: 'Total students',     value: metrics.users.total },
        { label: 'Active bans',        value: activeBans.length },
      ]
    : Array(6).fill(null).map((_, i) => ({ label: ['Active slots','Occupancy','Total bookings','Confirmed','Students','Active bans'][i], value: '—' }));

  const isStudent = activePortal === 'student';

  async function handleLogout() {
    await logout();
    navigate('/login');
  }

  // ── Input style helper ────────────────────────────────────────────────────
  const inp = {
    width: '100%',
    border: '1px solid rgba(167,139,250,0.22)',
    borderRadius: '16px',
    background: 'rgba(7,10,20,0.92)',
    padding: '12px 16px',
    color: '#f8fafc',
    fontSize: '0.9rem',
    boxSizing: 'border-box',
  };

  return (
    <main className="dashboard">
      {/* Toast */}
      {toast && (
        <div className={`toast ${toast.ok ? 'toast-ok' : 'toast-err'}`}>{toast.msg}</div>
      )}

      {/* ── Topbar ── */}
      <header className="topbar">
        <div>
          <p className="brand-kicker">PESU Sports Slot Booking</p>
          <h1 className="brand-title">Campus Arena</h1>
        </div>
        <div style={{ display: 'flex', gap: '16px', alignItems: 'center', flexWrap: 'wrap' }}>
          {/* Admins only see the Admin Panel label; students only see Student Portal */}
          <div className="portal-switch" role="tablist">
            {!isAdmin && (
              <button className="switch-chip active" type="button" disabled>
                Student Portal
              </button>
            )}
            {isAdmin && (
              <button className="switch-chip active" type="button" disabled>
                Admin Panel
              </button>
            )}
          </div>
          <div style={{ textAlign: 'right' }}>
            <p style={{ margin: 0, color: '#f5f3ff', fontWeight: 700, fontSize: '0.9rem' }}>
              {user?.name || user?.srn}
            </p>
            <button onClick={handleLogout} style={{ background: 'none', border: 'none', color: '#8dd8ff', cursor: 'pointer', fontSize: '0.82rem', padding: 0 }}>
              Sign out
            </button>
          </div>
        </div>
      </header>

      {/* ── Hero ── */}
      <section className="hero-panel">
        <div
          className="hero-copy hero-media"
          style={{ backgroundImage: 'linear-gradient(135deg, rgba(5,8,20,0.84), rgba(93,63,211,0.48)), url("/images/football-hero.jpg")' }}
        >
          <p className="eyebrow">{isStudent ? 'Student Sports Access' : 'Admin Control'}</p>
          <h2 className="hero-title">
            {isStudent
              ? 'Reserve college sports slots and manage bookings in one place.'
              : 'Create, update, and monitor campus sports slots in real time.'}
          </h2>
          <div className="hero-stats">
            <div><strong>{metrics?.slots.open ?? slots.length}</strong><span>Available slots</span></div>
            <div>
              <strong>{isStudent ? myBookings.filter(b => b.status !== 'cancelled').length : (metrics ? `${metrics.occupancy_pct}%` : '—')}</strong>
              <span>{isStudent ? 'My active bookings' : 'Occupancy'}</span>
            </div>
            <div><strong>Live</strong><span>Real-time updates</span></div>
          </div>
        </div>
        <div
          className="hero-highlight hero-media"
          style={{ backgroundImage: 'linear-gradient(180deg, rgba(12,14,30,0.3), rgba(12,14,30,0.88)), url("/images/pesu-campus.jpg")' }}
        >
          <span className="highlight-label">{isStudent ? 'Your session' : 'Operations snapshot'}</span>
          <h2>
            {isStudent
              ? `Welcome back, ${user?.name?.split(' ')[0] || user?.srn}.`
              : 'Slot management and live occupancy tracking.'}
          </h2>
          <p style={{ color: '#cbd5ff' }}>
            {isStudent
              ? `${user?.branch ? user.branch + ' · ' : ''}${user?.campus ? user.campus + ' Campus' : ''}`
              : `${activeBans.length} active ban${activeBans.length !== 1 ? 's' : ''} · ${metrics?.bookings.total ?? 0} total bookings`}
          </p>
        </div>
      </section>

      {/* ══ STUDENT PORTAL ══════════════════════════════════════════════════ */}
      {isStudent && (
        <>
          {/* Ban Banner */}
          {banInfo && (
            <div style={{
              background: 'rgba(192,57,43,0.18)', border: '1px solid #c0392b',
              borderRadius: '16px', padding: '16px 20px', margin: '0 0 24px',
              color: '#ff7c7c',
            }}>
              ⚠️ <strong>Booking suspended</strong> until{' '}
              <strong>{fmtBanDate(banInfo.banned_until)}</strong> — {banInfo.reason}
            </div>
          )}

          {/* Filters */}
          <section style={{ marginBottom: '24px', display: 'flex', gap: '12px', flexWrap: 'wrap', alignItems: 'center' }}>
            <p className="eyebrow" style={{ margin: 0, marginRight: '4px' }}>Filter:</p>
            <select style={{ ...inp, width: 'auto', padding: '10px 16px' }} value={filterCampus} onChange={e => setFilterCampus(e.target.value)}>
              <option value="">All Campuses</option>
              {CAMPUSES.map(c => <option key={c} value={c}>{c} Campus</option>)}
            </select>
            <select style={{ ...inp, width: 'auto', padding: '10px 16px' }} value={filterSport} onChange={e => setFilterSport(e.target.value)}>
              <option value="">All Sports</option>
              {SPORTS_LIST.map(s => <option key={s} value={s}>{s}</option>)}
            </select>
            {(filterCampus || filterSport) && (
              <button className="secondary-button" type="button" style={{ padding: '10px 16px' }} onClick={() => { setFilterCampus(''); setFilterSport(''); }}>
                Clear
              </button>
            )}
          </section>

          {/* Sports Cards */}
          <section className="sports-section">
            <div className="section-heading">
              <div>
                <p className="eyebrow">Available Sports</p>
                <h2>View and book slots by sport</h2>
              </div>
              <p className="section-copy">Live slot counts. Auto-confirmed on booking.</p>
            </div>

            {slotsLoading ? (
              <p style={{ color: '#cbd5ff', textAlign: 'center', padding: '40px 0' }}>Loading slots…</p>
            ) : (
              <div className="sports-grid">
                {displayedSports.map((sportName) => {
                  const sportSlots  = slotsBySport[sportName] || [];
                  const totalAvail  = sportSlots.reduce((s, sl) => s + sl.available_count, 0);
                  const meta        = SPORT_META[sportName] || { image: '', accent: '' };
                  const nextSlot    = sportSlots[0];
                  return (
                    <article className="sport-card" key={sportName}>
                      <div className="sport-image-wrap">
                        <img className="sport-image" src={meta.image} alt={sportName} />
                        <span className="sport-badge">
                          {totalAvail > 0 ? `${totalAvail} seats available` : 'No slots today'}
                        </span>
                      </div>
                      <div className="sport-content">
                        <div className="sport-header">
                          <div>
                            <h3>{sportName}</h3>
                            <p className="venue">{nextSlot?.venue || '—'}</p>
                          </div>
                          {nextSlot && <span className="slot-pill">{nextSlot.start_time}–{nextSlot.end_time}</span>}
                        </div>
                        <p className="sport-accent">{meta.accent}</p>
                        {sportSlots.length > 0 ? (
                          <div style={{ display: 'grid', gap: '8px' }}>
                            {sportSlots.slice(0, 3).map((sl) => (
                              <button
                                key={sl.id}
                                className="primary-button"
                                type="button"
                                disabled={!!banInfo || bookingInProgress === sl.id || sl.available_count === 0}
                                onClick={() => handleBook(sl.id)}
                                style={{ fontSize: '0.9rem', padding: '11px 14px' }}
                              >
                                {bookingInProgress === sl.id
                                  ? 'Booking…'
                                  : `Book — ${sl.start_time}–${sl.end_time} (${sl.available_count} left)`}
                              </button>
                            ))}
                          </div>
                        ) : (
                          <button className="secondary-button" type="button" disabled>No slots available</button>
                        )}
                      </div>
                    </article>
                  );
                })}
              </div>
            )}
          </section>

          {/* My Bookings + Announcements */}
          <section className="content-grid">
            <article className="panel">
              <div className="panel-header">
                <p className="eyebrow">My Bookings</p>
                <h3>Manage upcoming reservations</h3>
              </div>
              {bookingsLoading ? (
                <p style={{ color: '#cbd5ff' }}>Loading…</p>
              ) : myBookings.filter(b => b.status !== 'cancelled').length === 0 ? (
                <p style={{ color: '#cbd5ff' }}>No active bookings yet. Book a slot above!</p>
              ) : (
                <div className="booking-list">
                  {myBookings.filter(b => b.status !== 'cancelled').map((bk) => (
                    <div className="booking-row" key={bk.id}>
                      <div>
                        <strong>{bk.sport}</strong>
                        <p>{bk.slot_date ? fmtDate(bk.slot_date) : '—'}{bk.slot_start_time ? `, ${bk.slot_start_time}–${bk.slot_end_time}` : ''}</p>
                        <span>{bk.slot_venue || '—'}{bk.slot_campus ? ` · ${bk.slot_campus}` : ''}</span>
                      </div>
                      <div className="booking-actions">
                        <span className="status-chip">{fmtStatus(bk.status)}</span>
                        <button
                          className="secondary-button"
                          type="button"
                          disabled={cancelInProgress === bk.id}
                          onClick={() => handleCancel(bk.id)}
                        >
                          {cancelInProgress === bk.id ? 'Cancelling…' : 'Cancel'}
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </article>

            <article className="panel stacked-panel">
              <div>
                <div className="panel-header">
                  <p className="eyebrow">Announcements</p>
                  <h3>Notice board</h3>
                </div>
                <ul className="info-list">{announcements.map(a => <li key={a}>{a}</li>)}</ul>
              </div>
              <div>
                <div className="panel-header section-gap">
                  <p className="eyebrow">Upcoming Events</p>
                  <h3>Campus sports calendar</h3>
                </div>
                <div className="event-list">
                  {upcomingEvents.map(ev => (
                    <div className="event-row" key={ev.title}>
                      <strong>{ev.title}</strong>
                      <span>{ev.time}</span>
                    </div>
                  ))}
                </div>
              </div>
            </article>
          </section>
        </>
      )}

      {/* ══ ADMIN PORTAL ════════════════════════════════════════════════════ */}
      {!isStudent && isAdmin && (
        <>
          {/* Admin Tab Nav */}
          <div style={{ display: 'flex', gap: '10px', marginBottom: '24px', flexWrap: 'wrap' }}>
            {[
              { id: 'overview',  label: 'Overview' },
              { id: 'slots',     label: `Manage Slots (${adminSlots.length})` },
              { id: 'bookings',  label: `All Bookings (${allBookings.length})` },
              { id: 'bans',      label: `Bans (${activeBans.length})` },
            ].map(tab => (
              <button
                key={tab.id}
                className={adminTab === tab.id ? 'switch-chip active' : 'switch-chip'}
                type="button"
                onClick={() => setAdminTab(tab.id)}
              >
                {tab.label}
              </button>
            ))}
            <button className="secondary-button" type="button" onClick={fetchAdminData} disabled={adminLoading} style={{ marginLeft: 'auto', padding: '8px 18px', fontSize: '0.85rem' }}>
              {adminLoading ? 'Refreshing…' : '↻ Refresh'}
            </button>
          </div>

          {/* ── Overview Tab ── */}
          {adminTab === 'overview' && (
            <section className="content-grid admin-grid" style={{ marginBottom: '24px' }}>
              {/* Metrics */}
              <article className="panel">
                <div className="panel-header">
                  <p className="eyebrow">Live Metrics</p>
                  <h3>Operations pulse</h3>
                </div>
                <div className="mini-grid">
                  {metricCards.map(m => (
                    <div className="mini-stat" key={m.label}>
                      <strong>{m.value}</strong>
                      <span>{m.label}</span>
                    </div>
                  ))}
                </div>
              </article>

              {/* Create Slot */}
              <article className="panel">
                <div className="panel-header">
                  <p className="eyebrow">Create Slot</p>
                  <h3>Add new availability</h3>
                </div>
                <form className="form-grid" onSubmit={handleCreateSlot}>
                  <label>
                    <span>Sport</span>
                    <select style={inp} value={slotForm.sport} onChange={e => setSlotForm(f => ({ ...f, sport: e.target.value }))}>
                      {SPORTS_LIST.map(s => <option key={s}>{s}</option>)}
                    </select>
                  </label>
                  <label>
                    <span>Campus</span>
                    <select style={inp} value={slotForm.campus} onChange={e => setSlotForm(f => ({ ...f, campus: e.target.value }))}>
                      {CAMPUSES.map(c => <option key={c}>{c}</option>)}
                    </select>
                  </label>
                  <label><span>Date</span><input style={inp} type="date" value={slotForm.date} onChange={e => setSlotForm(f => ({ ...f, date: e.target.value }))} /></label>
                  <label><span>Venue</span><input style={inp} type="text" placeholder="e.g. Main Turf Arena" value={slotForm.venue} onChange={e => setSlotForm(f => ({ ...f, venue: e.target.value }))} /></label>
                  <label><span>Start time</span><input style={inp} type="time" value={slotForm.start_time} onChange={e => setSlotForm(f => ({ ...f, start_time: e.target.value }))} /></label>
                  <label><span>End time</span><input style={inp} type="time" value={slotForm.end_time} onChange={e => setSlotForm(f => ({ ...f, end_time: e.target.value }))} /></label>
                  <label><span>Max seats</span><input style={inp} type="number" min="1" placeholder="20" value={slotForm.capacity} onChange={e => setSlotForm(f => ({ ...f, capacity: e.target.value }))} /></label>
                  <div className="button-row" style={{ gridColumn: '1/-1', marginTop: '4px' }}>
                    <button className="primary-button" type="submit" disabled={slotFormLoading}>
                      {slotFormLoading ? 'Creating…' : 'Create slot'}
                    </button>
                    <button className="secondary-button" type="button" onClick={() => setSlotForm(BLANK_SLOT)}>Reset</button>
                  </div>
                </form>
              </article>
            </section>
          )}

          {/* ── Slots Tab ── */}
          {adminTab === 'slots' && (
            <section className="panel bookings-panel" style={{ marginBottom: '24px' }}>
              <div className="section-heading booking-heading">
                <div>
                  <p className="eyebrow">Manage Slots</p>
                  <h2>Edit or cancel existing slots</h2>
                </div>
                <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap' }}>
                  <select style={{ ...inp, width: 'auto', padding: '9px 14px' }} value={adminFilterCampus} onChange={e => setAdminFilterCampus(e.target.value)}>
                    <option value="">All Campuses</option>
                    {CAMPUSES.map(c => <option key={c} value={c}>{c}</option>)}
                  </select>
                  <select style={{ ...inp, width: 'auto', padding: '9px 14px' }} value={adminFilterSport} onChange={e => setAdminFilterSport(e.target.value)}>
                    <option value="">All Sports</option>
                    {SPORTS_LIST.map(s => <option key={s} value={s}>{s}</option>)}
                  </select>
                </div>
              </div>

              {(() => {
                // Hide deprecated sports that no longer exist in the college
                const DEPRECATED = ['Swimming', 'Tennis'];
                const visibleSlots = adminSlots.filter(sl => !DEPRECATED.includes(sl.sport));
                if (visibleSlots.length === 0) return <p style={{ color: '#cbd5ff' }}>No slots found.</p>;
                return (
                  <div className="admin-booking-list">
                    {visibleSlots.map(sl => (
                      <div key={sl.id}>
                        {editingSlot === sl.id ? (
                          <div className="admin-booking-row" style={{ flexWrap: 'wrap', gap: '12px', alignItems: 'flex-start' }}>
                            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px', flex: '1 1 400px' }}>
                              <label style={{ fontSize: '0.82rem' }}>
                                <span style={{ color: '#8899cc' }}>Venue</span>
                                <input style={{ ...inp, padding: '8px 12px', marginTop: '4px' }} value={editForm.venue} onChange={e => setEditForm(f => ({ ...f, venue: e.target.value }))} />
                              </label>
                              <label style={{ fontSize: '0.82rem' }}>
                                <span style={{ color: '#8899cc' }}>Capacity</span>
                                <input style={{ ...inp, padding: '8px 12px', marginTop: '4px' }} type="number" min="1" value={editForm.capacity} onChange={e => setEditForm(f => ({ ...f, capacity: e.target.value }))} />
                              </label>
                              <label style={{ fontSize: '0.82rem' }}>
                                <span style={{ color: '#8899cc' }}>Start</span>
                                <input style={{ ...inp, padding: '8px 12px', marginTop: '4px' }} type="time" value={editForm.start_time} onChange={e => setEditForm(f => ({ ...f, start_time: e.target.value }))} />
                              </label>
                              <label style={{ fontSize: '0.82rem' }}>
                                <span style={{ color: '#8899cc' }}>End</span>
                                <input style={{ ...inp, padding: '8px 12px', marginTop: '4px' }} type="time" value={editForm.end_time} onChange={e => setEditForm(f => ({ ...f, end_time: e.target.value }))} />
                              </label>
                            </div>
                            <div className="button-row compact" style={{ alignSelf: 'flex-end' }}>
                              <button className="primary-button compact-button" type="button" disabled={editLoading} onClick={() => handleSaveEdit(sl.id)}>
                                {editLoading ? '…' : 'Save'}
                              </button>
                              <button className="secondary-button compact-button" type="button" onClick={() => setEditingSlot(null)}>Discard</button>
                            </div>
                          </div>
                        ) : (
                          <div className="admin-booking-row">
                            <div>
                              <strong>{sl.sport}</strong>
                              <p style={{ color: '#8899cc', fontSize: '0.82rem' }}>{sl.campus} · {sl.venue}</p>
                            </div>
                            <div>
                              <strong>{fmtDate(sl.date)}</strong>
                              <p style={{ color: '#8899cc', fontSize: '0.82rem' }}>{sl.start_time}–{sl.end_time}</p>
                            </div>
                            <div>
                              <strong>{sl.booked_count}/{sl.capacity}</strong>
                              <p style={{ color: '#8899cc', fontSize: '0.82rem' }}>booked</p>
                            </div>
                            <span className="status-chip" style={{
                              background: sl.status === 'open' ? 'rgba(34,197,94,0.15)' : sl.status === 'full' ? 'rgba(245,158,11,0.15)' : 'rgba(239,68,68,0.15)',
                              color: sl.status === 'open' ? '#4ade80' : sl.status === 'full' ? '#fbbf24' : '#f87171',
                            }}>
                              {fmtStatus(sl.status)}
                            </span>
                            <div className="button-row compact">
                              {sl.status !== 'cancelled' && (
                                <button className="primary-button compact-button" type="button" onClick={() => startEditSlot(sl)}>Edit</button>
                              )}
                              {sl.status !== 'cancelled' && (
                                <button className="secondary-button compact-button" type="button" onClick={() => handleCancelSlot(sl.id)}>Cancel</button>
                              )}
                              <button
                                className="secondary-button compact-button"
                                type="button"
                                style={{ color: '#f87171', borderColor: 'rgba(248,113,113,0.3)' }}
                                onClick={() => handleDeleteSlot(sl.id)}
                              >
                                Delete
                              </button>
                            </div>
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                );
              })()}
            </section>
          )}

          {/* ── Bookings Tab ── */}
          {adminTab === 'bookings' && (
            <>
              {/* Pending */}
              {pendingBookings.length > 0 && (
                <section className="panel bookings-panel" style={{ marginBottom: '24px' }}>
                  <div className="section-heading booking-heading">
                    <div>
                      <p className="eyebrow">Pending Approvals</p>
                      <h2>Approve or reject requests</h2>
                    </div>
                    <p className="section-copy">{pendingBookings.length} awaiting action.</p>
                  </div>
                  <div className="admin-booking-list">
                    {pendingBookings.map(bk => (
                      <div className="admin-booking-row" key={bk.id}>
                        <div><strong>{bk.user?.name || '—'}</strong><p>{bk.user?.srn}</p></div>
                        <div><strong>{bk.sport}</strong><p>{bk.slot ? `${fmtDate(bk.slot.date)}, ${bk.slot.start_time}–${bk.slot.end_time}` : '—'}</p></div>
                        <span className="status-chip">Pending</span>
                        <div className="button-row compact">
                          <button className="primary-button compact-button" type="button" disabled={approvalInProgress === bk.id + 'approve'} onClick={() => handleApproval(bk.id, 'approve')}>
                            {approvalInProgress === bk.id + 'approve' ? '…' : 'Approve'}
                          </button>
                          <button className="secondary-button compact-button" type="button" disabled={approvalInProgress === bk.id + 'reject'} onClick={() => handleApproval(bk.id, 'reject')}>
                            {approvalInProgress === bk.id + 'reject' ? '…' : 'Reject'}
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                </section>
              )}

              {/* All bookings */}
              <section className="panel bookings-panel">
                <div className="section-heading booking-heading">
                  <div>
                    <p className="eyebrow">All Bookings</p>
                    <h2>Complete booking history</h2>
                  </div>
                </div>
                {allBookings.length === 0 ? (
                  <p style={{ color: '#cbd5ff' }}>No bookings yet.</p>
                ) : (
                  <div className="admin-booking-list">
                    {allBookings.map(bk => (
                      <div className="admin-booking-row" key={bk.id}>
                        <div><strong>{bk.user?.name || '—'}</strong><p>{bk.user?.srn}</p></div>
                        <div>
                          <strong>{bk.sport}</strong>
                          <p>{bk.slot ? `${fmtDate(bk.slot.date)}, ${bk.slot.start_time}–${bk.slot.end_time} · ${bk.slot.campus}` : '—'}</p>
                        </div>
                        <span className="status-chip">{fmtStatus(bk.status)}</span>
                        <span style={{ color: '#8899cc', fontSize: '0.8rem' }}>{fmt(bk.created_at)}</span>
                        {bk.status !== 'cancelled' && (
                          <button
                            className="secondary-button compact-button"
                            type="button"
                            style={{ color: '#f87171', borderColor: 'rgba(248,113,113,0.3)', fontSize: '0.8rem', padding: '6px 14px' }}
                            onClick={() => handleAdminCancelBooking(bk.id)}
                          >
                            Cancel
                          </button>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </section>
            </>
          )}

          {/* ── Bans Tab ── */}
          {adminTab === 'bans' && (
            <section className="panel bookings-panel">
              <div className="section-heading booking-heading">
                <div>
                  <p className="eyebrow">Active Bans</p>
                  <h2>Students with booking suspensions</h2>
                </div>
                <p className="section-copy">Bans are applied automatically on late cancellations.</p>
              </div>
              {activeBans.length === 0 ? (
                <p style={{ color: '#cbd5ff' }}>No active bans.</p>
              ) : (
                <div className="admin-booking-list">
                  {activeBans.map(b => (
                    <div className="admin-booking-row" key={b.id}>
                      <div>
                        <strong>{b.user_name || '—'}</strong>
                        <p style={{ color: '#8899cc' }}>{b.user_srn} · {b.user_email}</p>
                      </div>
                      <div>
                        <strong style={{ color: '#ff7c7c' }}>Banned until</strong>
                        <p>{fmtBanDate(b.banned_until)}</p>
                      </div>
                      <div style={{ flex: 1 }}>
                        <p style={{ color: '#8899cc', fontSize: '0.82rem' }}>{b.reason}</p>
                      </div>
                      <button className="primary-button compact-button" type="button" onClick={() => handleUnban(b.user_id)}>
                        Lift Ban
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </section>
          )}
        </>
      )}
    </main>
  );
}
