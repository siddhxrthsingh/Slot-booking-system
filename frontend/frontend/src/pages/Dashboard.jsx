import { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { useWebSocket } from '../hooks/useWebSocket';
import { useOccupancySocket } from '../hooks/useOccupancySocket';
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
  getFacilities,
  getSlotRoster,
  getScheduleTemplates,
  createScheduleTemplate,
  updateScheduleTemplate,
  deleteScheduleTemplate,
} from '../api/admin';

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

// Maps a sport name (as returned by the backend) to an existing real sport
// photo for the facility card header. Purely a presentational asset choice —
// it does not add sports/facilities to the bookable inventory, which still
// comes entirely from the API.
const SPORT_IMAGES = {
  Badminton:      '/images/badminton.jpg',
  Basketball:     '/images/basketball.jpg',
  'Table Tennis': '/images/table-tennis.jpg',
  Squash:         '/images/squash.jpg',
  Volleyball:     '/images/volleyball.jpg',
};
const DEFAULT_FACILITY_IMAGE = '/images/pesu-campus.jpg';

const MAX_ACTIVE_SLOTS_PER_DAY = 2; // mirrors the backend's locked daily-quota rule

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
function initials(name, srn) {
  const source = (name || srn || '').trim();
  if (!source) return '—';
  const parts = source.split(/\s+/);
  return parts.length > 1
    ? (parts[0][0] + parts[1][0]).toUpperCase()
    : source.slice(0, 2).toUpperCase();
}

// ── Blank slot form ───────────────────────────────────────────────────────────
// Manual slots are tied to a real RR facility — sport/venue/capacity are
// derived server-side from the selected facility, never entered here.
const BLANK_SLOT = {
  facility_id: '', date: '', start_time: '', end_time: '',
};

const BLANK_PERIOD = {
  start_time: '', end_time: '', period_type: 'student', is_bookable: true, label: '',
};

// Sport/facility values are always sourced from the facility list fetched
// from the backend — never hardcoded here.
const BLANK_TEMPLATE = {
  sport: '', facility_scope: 'sport', facility_id: '', day_type: 'weekday',
  priority: 0, is_active: true, notes: '',
  periods: [{ ...BLANK_PERIOD }],
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
  const [bookingsError,    setBookingsError]    = useState(null);
  const [slotsError,       setSlotsError]       = useState(null);
  const [bookingInProgress,setBookingInProgress]= useState(null);
  const [cancelInProgress, setCancelInProgress] = useState(null);
  const [toast,            setToast]            = useState(null);
  const [banInfo,          setBanInfo]          = useState(null);

  // Synchronous guards against double-submit from rapid repeat clicks before
  // React has a chance to re-render the disabled button state.
  const bookingLockRef = useRef(new Set());
  const cancelLockRef  = useRef(new Set());

  // Click-outside handling for the profile/mobile nav menus.
  const profileRef = useRef(null);

  // Student filters (RR only for now; sport options are derived from the
  // facility-aware slot data returned by the backend, not hardcoded)
  const [filterSport, setFilterSport] = useState('');
  const [profileOpen, setProfileOpen] = useState(false);
  const [mobileNavOpen, setMobileNavOpen] = useState(false);

  // ── Admin state ───────────────────────────────────────────────────────────
  const [metrics,           setMetrics]           = useState(null);
  const [pendingBookings,   setPendingBookings]   = useState([]);
  const [allBookings,       setAllBookings]       = useState([]);
  const [adminLoading,      setAdminLoading]      = useState(false);
  const [approvalInProgress,setApprovalInProgress]= useState(null);
  const [activeBans,        setActiveBans]        = useState([]);
  const [adminSlots,        setAdminSlots]        = useState([]);
  const [facilities,        setFacilities]        = useState([]);
  const [scheduleTemplates, setScheduleTemplates] = useState([]);
  const [adminTab,          setAdminTab]          = useState('overview'); // overview | slots | bookings | bans | facilities | schedule

  // Slot roster modal (admin-only accountability view)
  const [rosterSlotId, setRosterSlotId] = useState(null);
  const [rosterData,   setRosterData]   = useState(null);
  const [rosterLoading,setRosterLoading]= useState(false);
  const [rosterError,  setRosterError]  = useState(null);

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

  // Admin schedule template create/edit
  const [templateForm,        setTemplateForm]        = useState(BLANK_TEMPLATE);
  const [templateFormLoading, setTemplateFormLoading] = useState(false);
  const [editingTemplateId,   setEditingTemplateId]   = useState(null); // null = create mode

  // ── Toast ─────────────────────────────────────────────────────────────────
  function showToast(msg, ok = true) {
    setToast({ msg, ok });
    setTimeout(() => setToast(null), 4000);
  }

  // ── Fetch helpers ─────────────────────────────────────────────────────────
  const fetchSlots = useCallback(async () => {
    setSlotsLoading(true);
    try {
      // RR only for now — sport filtering happens client-side (below) so the
      // filter dropdown's option list can be derived from the full set of
      // facilities/sports the backend actually returns.
      //
      // Today and tomorrow are requested explicitly (rather than relying on
      // an implicit "no date" query) so each request hits the backend's
      // existing lazy generate_slots_for_date() trigger for that specific
      // date — otherwise slots for a date are never generated.
      const today = new Date();
      const tomorrow = new Date(today);
      tomorrow.setDate(tomorrow.getDate() + 1);
      const [todaySlots, tomorrowSlots] = await Promise.all([
        getAvailableSlots({ campus: 'RR', date: today.toISOString() }),
        getAvailableSlots({ campus: 'RR', date: tomorrow.toISOString() }),
      ]);
      const byId = new Map();
      [...todaySlots, ...tomorrowSlots].forEach((s) => byId.set(s.id, s));
      setSlots([...byId.values()]);
      setSlotsError(null);
    } catch {
      setSlotsError('Failed to load available slots.');
      showToast('Failed to load available slots.', false);
    } finally {
      setSlotsLoading(false);
    }
  }, []);

  const fetchMyBookings = useCallback(async () => {
    setBookingsLoading(true);
    try {
      const data = await getMyBookings();
      setMyBookings(data);
      setBookingsError(null);
    } catch {
      setBookingsError('Failed to load your bookings.');
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
      const [m, pb, ab, bans, slots, facilityList, templates] = await Promise.all([
        getMetrics(),
        getPendingBookings(),
        getAllBookings(),
        getActiveBans(),
        getAdminSlots(params),
        getFacilities(),
        getScheduleTemplates(),
      ]);
      setMetrics(m);
      setPendingBookings(pb);
      setAllBookings(ab);
      setActiveBans(bans);
      setAdminSlots(slots);
      setFacilities(facilityList);
      setScheduleTemplates(templates);
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

  // Close the profile/mobile nav dropdowns on an outside click so they don't
  // stay open and obscure content after the user has moved on.
  useEffect(() => {
    if (!profileOpen && !mobileNavOpen) return;
    function handleOutsideClick(e) {
      if (profileRef.current && !profileRef.current.contains(e.target)) {
        setProfileOpen(false);
        setMobileNavOpen(false);
      }
    }
    document.addEventListener('mousedown', handleOutsideClick);
    return () => document.removeEventListener('mousedown', handleOutsideClick);
  }, [profileOpen, mobileNavOpen]);

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

  // ── Live occupancy updates (student portal only) ─────────────────────────
  // Subscribes to exactly the slot IDs currently displayed, so join/leave
  // events elsewhere update booked_count/available_count/status in place
  // without a full slot refetch.
  const displayedSlotIds = useMemo(() => slots.map((s) => s.id), [slots]);

  const handleOccupancyUpdate = useCallback((data) => {
    setSlots((prev) => prev.map((s) => (
      s.id === data.slot_id
        ? {
            ...s,
            booked_count:    data.booked_count ?? s.booked_count,
            available_count: data.available_count ?? s.available_count,
            status:          data.status ?? s.status,
          }
        : s
    )));
  }, []);

  useOccupancySocket(displayedSlotIds, handleOccupancyUpdate, activePortal === 'student');

  // ── Student actions ───────────────────────────────────────────────────────
  async function handleBook(slotId) {
    if (banInfo) {
      showToast(`Your booking access is suspended until ${fmtBanDate(banInfo.banned_until)}.`, false);
      return;
    }
    // Ref-based guard closes the race between a rapid double-click and the
    // next React render actually disabling the button.
    if (bookingLockRef.current.has(slotId)) return;
    bookingLockRef.current.add(slotId);
    setBookingInProgress(slotId);
    try {
      await createBooking(slotId);
      showToast('Slot booked and confirmed!');
      // Refresh both together so the facility list and My Bookings settle in
      // the same render instead of one briefly lagging behind the other.
      await Promise.all([fetchSlots(), fetchMyBookings()]);
    } catch (err) {
      showToast(err.response?.data?.detail || 'Could not book slot.', false);
    } finally {
      bookingLockRef.current.delete(slotId);
      setBookingInProgress(null);
    }
  }

  async function handleCancel(bookingId) {
    if (!window.confirm('Cancel this booking? Late cancellations (< 2 hours before) incur a 2-day booking ban.')) return;
    if (cancelLockRef.current.has(bookingId)) return;
    cancelLockRef.current.add(bookingId);
    setCancelInProgress(bookingId);
    try {
      const result = await cancelBooking(bookingId);
      if (result.late_cancel) {
        showToast('Booking cancelled — late cancellation ban applied for 2 days.', false);
        fetchBanStatus();
      } else {
        showToast('Booking cancelled.');
      }
      // Refresh both together so the facility list and My Bookings settle in
      // the same render instead of one briefly lagging behind the other.
      await Promise.all([fetchMyBookings(), fetchSlots()]);
    } catch (err) {
      showToast(err.response?.data?.detail || 'Could not cancel booking.', false);
    } finally {
      cancelLockRef.current.delete(bookingId);
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

  // ── Schedule template actions ─────────────────────────────────────────────
  function startEditTemplate(t) {
    setEditingTemplateId(t.id);
    setTemplateForm({
      sport:          t.sport,
      facility_scope: t.facility_scope,
      facility_id:    t.facility_id || '',
      day_type:       t.day_type,
      priority:       t.priority ?? 0,
      is_active:      t.is_active,
      notes:          t.notes || '',
      periods: (t.periods || []).map(p => ({
        start_time: p.start_time, end_time: p.end_time, period_type: p.period_type,
        is_bookable: p.is_bookable, label: p.label || '',
      })),
    });
  }

  function cancelEditTemplate() {
    setEditingTemplateId(null);
    setTemplateForm(BLANK_TEMPLATE);
  }

  function updatePeriodField(index, field, value) {
    setTemplateForm(f => ({
      ...f,
      periods: f.periods.map((p, i) => (i === index ? { ...p, [field]: value } : p)),
    }));
  }

  function addPeriodRow() {
    setTemplateForm(f => ({ ...f, periods: [...f.periods, { ...BLANK_PERIOD }] }));
  }

  function removePeriodRow(index) {
    setTemplateForm(f => ({ ...f, periods: f.periods.filter((_, i) => i !== index) }));
  }

  async function handleSubmitTemplate(e) {
    e.preventDefault();
    if (!templateForm.sport || !templateForm.periods.length) {
      showToast('Sport and at least one period are required.', false);
      return;
    }
    if (templateForm.facility_scope === 'facility' && !templateForm.facility_id) {
      showToast('Select a facility for a facility-specific template.', false);
      return;
    }
    setTemplateFormLoading(true);
    try {
      const payload = {
        sport:          templateForm.sport,
        facility_scope: templateForm.facility_scope,
        facility_id:    templateForm.facility_scope === 'facility' ? templateForm.facility_id : null,
        day_type:       templateForm.day_type,
        priority:       Number(templateForm.priority) || 0,
        is_active:      templateForm.is_active,
        notes:          templateForm.notes || null,
        periods: templateForm.periods.map(p => ({
          start_time: p.start_time, end_time: p.end_time, period_type: p.period_type,
          is_bookable: p.is_bookable, label: p.label || null,
        })),
      };
      if (editingTemplateId) {
        await updateScheduleTemplate(editingTemplateId, payload);
        showToast('Schedule template updated.');
      } else {
        await createScheduleTemplate({ campus: 'RR', ...payload });
        showToast('Schedule template created.');
      }
      cancelEditTemplate();
      fetchAdminData();
    } catch (err) {
      showToast(err.response?.data?.detail || 'Failed to save schedule template.', false);
    } finally {
      setTemplateFormLoading(false);
    }
  }

  async function handleToggleTemplateActive(t) {
    try {
      await updateScheduleTemplate(t.id, { is_active: !t.is_active });
      showToast(t.is_active ? 'Template deactivated.' : 'Template activated.');
      fetchAdminData();
    } catch {
      showToast('Failed to update template.', false);
    }
  }

  async function handleDeleteTemplate(templateId) {
    if (!window.confirm('Permanently delete this schedule template? This does not affect already-generated slots.')) return;
    try {
      await deleteScheduleTemplate(templateId);
      showToast('Schedule template deleted.');
      if (editingTemplateId === templateId) cancelEditTemplate();
      fetchAdminData();
    } catch {
      showToast('Failed to delete template.', false);
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

  async function handleViewRoster(slotId) {
    setRosterSlotId(slotId);
    setRosterData(null);
    setRosterError(null);
    setRosterLoading(true);
    try {
      const data = await getSlotRoster(slotId);
      setRosterData(data);
    } catch (err) {
      setRosterError(err.response?.data?.detail || 'Failed to load slot roster.');
    } finally {
      setRosterLoading(false);
    }
  }

  function closeRoster() {
    setRosterSlotId(null);
    setRosterData(null);
    setRosterError(null);
    setRosterLoading(false);
  }

  useEffect(() => {
    if (!rosterSlotId) return;
    function handleEscape(e) {
      if (e.key === 'Escape') closeRoster();
    }
    document.addEventListener('keydown', handleEscape);
    return () => document.removeEventListener('keydown', handleEscape);
  }, [rosterSlotId]);

  async function handleCreateSlot(e) {
    e.preventDefault();
    if (!slotForm.facility_id || !slotForm.date || !slotForm.start_time || !slotForm.end_time) {
      showToast('Please fill in all fields.', false);
      return;
    }
    setSlotFormLoading(true);
    try {
      const payload = {
        facility_id: slotForm.facility_id,
        start_time:  slotForm.start_time,
        end_time:    slotForm.end_time,
        date:        new Date(slotForm.date).toISOString(),
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
    if (slot.is_manual) {
      setEditForm({
        facility_id: slot.facility_id || '',
        start_time:  slot.start_time,
        end_time:    slot.end_time,
        date:        fmtDate(slot.date),
      });
    } else {
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
  }

  async function handleSaveEdit(slotId, isManual) {
    setEditLoading(true);
    try {
      const payload = isManual
        ? { facility_id: editForm.facility_id, start_time: editForm.start_time, end_time: editForm.end_time }
        : { ...editForm, capacity: parseInt(editForm.capacity, 10) };
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
  // Sport filter options come from whatever the backend actually returned —
  // never a hardcoded sport list. RR only for now.
  const availableSports = [...new Set(slots.map(s => s.sport))].sort();

  const visibleSlots = filterSport ? slots.filter(s => s.sport === filterSport) : slots;

  // Group by individual facility (not just by sport) using facility_id from
  // the facility-aware API response, falling back to facility_name for any
  // legacy/manual slot that predates facility linkage.
  const facilityGroups = Object.values(
    visibleSlots.reduce((acc, s) => {
      const key = s.facility_id || `${s.sport}::${s.facility_name || s.venue}`;
      if (!acc[key]) {
        acc[key] = {
          key,
          facilityName: s.facility_name || s.venue || 'Unknown facility',
          sport: s.sport,
          slots: [],
        };
      }
      acc[key].slots.push(s);
      return acc;
    }, {})
  ).map(group => ({
    ...group,
    slots: group.slots.slice().sort((a, b) => {
      const dateCmp = new Date(a.date) - new Date(b.date);
      if (dateCmp !== 0) return dateCmp;
      return a.start_time.localeCompare(b.start_time);
    }),
  })).sort((a, b) => a.facilityName.localeCompare(b.facilityName));

  // `is_past` is computed server-side (backend is authoritative for slot
  // end-time comparisons) — a booking is "active/upcoming" only while it is
  // neither cancelled nor past; everything else goes to history.
  const activeBookings = myBookings.filter(b => b.status !== 'cancelled' && !b.is_past);
  const historyBookings = myBookings.filter(b => b.status === 'cancelled' || b.is_past);
  // Derived purely from existing state (myBookings) — not a new backend
  // rule — so slot cards can show "Joined" instead of "Join" for slots the
  // student already has an active participation in.
  const joinedSlotIds = new Set(activeBookings.map(b => b.slot_id));
  const todayKey = fmtDate(new Date());
  const todaysActiveCount = activeBookings.filter(
    b => b.slot_date && fmtDate(b.slot_date) === todayKey
  ).length;

  const metricCards = metrics
    ? [
        { label: 'Active slots',       value: metrics.slots.active ?? (metrics.slots.open + metrics.slots.full) },
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

  if (isStudent) {
    return (
      <div className="sd-shell">
        {/* ── Top navigation (full-bleed, sticky + blurred like the v0 reference) ── */}
        <header className="sd-nav">
          <div className="sd-nav-inner">
            <div className="sd-brand">
              <img src="/pesu-compass-mark.webp" alt="PES University" className="sd-brand-mark" />
              <div className="sd-brand-text">
                <strong>SPORTS HUB</strong>
              </div>
            </div>
            <nav className="sd-nav-links">
              <a href="#discover">Discover</a>
              <a href="#my-bookings">My bookings</a>
              <button type="button" onClick={() => showToast('For help with bookings, contact your sports coordinator.')}>
                Help
              </button>
            </nav>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <button
                className="sd-nav-toggle"
                type="button"
                aria-label={mobileNavOpen ? 'Close menu' : 'Open menu'}
                aria-expanded={mobileNavOpen}
                onClick={() => setMobileNavOpen(o => !o)}
              >
                ☰
              </button>
              <div className="sd-profile" ref={profileRef}>
                <button
                  className="sd-profile-trigger"
                  type="button"
                  aria-haspopup="true"
                  aria-expanded={profileOpen}
                  onClick={() => setProfileOpen(o => !o)}
                >
                  <span className="sd-avatar">{initials(user?.name, user?.srn)}</span>
                  <span className="sd-profile-name">
                    <strong>{user?.name || user?.srn}</strong>
                    <span>{user?.srn}</span>
                  </span>
                  <span aria-hidden="true" style={{ color: 'var(--sd-muted)' }}>▾</span>
                </button>
                {profileOpen && (
                  <div className="sd-profile-menu">
                    <button type="button" onClick={handleLogout}>Sign out</button>
                  </div>
                )}
                {mobileNavOpen && (
                  <div className="sd-mobile-menu">
                    <a href="#discover" onClick={() => setMobileNavOpen(false)}>Discover</a>
                    <a href="#my-bookings" onClick={() => setMobileNavOpen(false)}>My bookings</a>
                    <button
                      type="button"
                      onClick={() => {
                        setMobileNavOpen(false);
                        showToast('For help with bookings, contact your sports coordinator.');
                      }}
                    >
                      Help
                    </button>
                  </div>
                )}
              </div>
            </div>
          </div>
        </header>

        <div className="sd-inner">
          {/* ── Hero ── */}
          <section className="sd-hero">
            <div>
              <span className="sd-eyebrow-chip">🏅 Open courts, better days</span>
              <h1 className="sd-hero-title">
                Find your next <em>game.</em>
              </h1>
              <p className="sd-hero-sub">
                Reserve a spot, join fellow students, and make the most of RR campus.
                {user?.name ? ` Welcome back, ${user.name.split(' ')[0]}.` : ''}
              </p>
            </div>
            <div className="sd-hero-card">
              <div className="sd-hero-card-icon">📅</div>
              <div className="sd-hero-card-body">
                <div>
                  <p className="sd-hero-card-label">Today</p>
                  <p className="sd-hero-card-value">
                    {new Date().toLocaleDateString('en-IN', { weekday: 'long', day: '2-digit', month: 'long' })}
                  </p>
                </div>
                <div>
                  <p className="sd-hero-card-label">Daily limit</p>
                  <p className="sd-hero-card-value">{todaysActiveCount}/{MAX_ACTIVE_SLOTS_PER_DAY} slots</p>
                </div>
              </div>
            </div>
          </section>

          {toast && (
            <div className={`sd-notice ${toast.ok ? 'sd-notice-ok' : 'sd-notice-err'}`} role="status">
              <span>{toast.ok ? '✓' : '⚠️'} {toast.msg}</span>
              <button className="sd-notice-dismiss" type="button" aria-label="Dismiss notification" onClick={() => setToast(null)}>✕</button>
            </div>
          )}

          {banInfo && (
            <div className="sd-ban-banner">
              ⚠️ <strong>Booking suspended</strong> until{' '}
              <strong>{fmtBanDate(banInfo.banned_until)}</strong> — {banInfo.reason}
            </div>
          )}

          {/* ── Main layout: facility discovery + my bookings sidebar ── */}
          <div className="sd-layout">
            <div id="discover">
              <div className="sd-section-head">
                <p className="sd-section-eyebrow">Explore facilities</p>
                <h2 className="sd-section-title">Pick a sport, pick a slot</h2>
                <p className="sd-section-meta">📍 PES University, RR Campus</p>
              </div>

              <div className="sd-chip-row">
                <button
                  type="button"
                  className={`sd-chip ${!filterSport ? 'active' : ''}`}
                  onClick={() => setFilterSport('')}
                >
                  All sports
                </button>
                {availableSports.map(s => (
                  <button
                    key={s}
                    type="button"
                    className={`sd-chip ${filterSport === s ? 'active' : ''}`}
                    onClick={() => setFilterSport(s)}
                  >
                    {s}
                  </button>
                ))}
              </div>

              {slotsLoading ? (
                <p className="sd-empty">Loading slots…</p>
              ) : slotsError ? (
                <p className="sd-empty">
                  {slotsError}{' '}
                  <button type="button" className="sd-chip" onClick={fetchSlots}>Retry</button>
                </p>
              ) : facilityGroups.length === 0 ? (
                <p className="sd-empty">No slots available right now.</p>
              ) : (
                <div className="sd-facility-grid">
                  {facilityGroups.map((group) => {
                    const openSlots = group.slots.filter(
                      sl => sl.status !== 'full' && sl.available_count > 0
                    ).length;
                    return (
                      <article className="sd-facility-card" key={group.key}>
                        <div
                          className="sd-facility-image"
                          style={{ backgroundImage: `url("${SPORT_IMAGES[group.sport] || DEFAULT_FACILITY_IMAGE}")` }}
                        >
                          <span className="sd-facility-tag">{group.sport}</span>
                          <p className="sd-facility-name">{group.facilityName}</p>
                        </div>
                        <div className="sd-facility-body">
                          <p className="sd-facility-location">📍 RR Campus</p>
                          {group.slots.length > 0 ? (
                            <div className="sd-slot-list">
                              {group.slots.map((sl) => {
                                const isJoined = joinedSlotIds.has(sl.id);
                                const isFull = !isJoined && (sl.status === 'full' || sl.available_count === 0);
                                return (
                                  <div className={`sd-slot-row ${isJoined ? 'sd-slot-row-joined' : ''}`} key={sl.id}>
                                    <div>
                                      <p className="sd-slot-time">🕒 {sl.start_time} – {sl.end_time}</p>
                                      <p className="sd-slot-meta">{sl.booked_count}/{sl.capacity} joined</p>
                                    </div>
                                    {isJoined ? (
                                      <span className="sd-joined-pill">✓ Joined</span>
                                    ) : isFull ? (
                                      <span className="sd-full-pill">Full</span>
                                    ) : (
                                      <button
                                        className="sd-join-btn"
                                        type="button"
                                        disabled={!!banInfo || bookingInProgress === sl.id}
                                        onClick={() => handleBook(sl.id)}
                                      >
                                        {bookingInProgress === sl.id ? 'Joining…' : '+ Join'}
                                      </button>
                                    )}
                                  </div>
                                );
                              })}
                            </div>
                          ) : (
                            <p className="sd-empty">No slots available</p>
                          )}
                          <div className="sd-facility-footer">
                            {openSlots > 0 ? (
                              <span className="sd-availability-ok">{openSlots} slot{openSlots !== 1 ? 's' : ''} available</span>
                            ) : (
                              <span className="sd-availability-none">No slots available</span>
                            )}
                          </div>
                        </div>
                      </article>
                    );
                  })}
                </div>
              )}
            </div>

            {/* ── My bookings sidebar ── */}
            <aside className="sd-sidebar" id="my-bookings">
              <div className="sd-card">
                <div className="sd-card-head">
                  <div>
                    <p className="sd-section-eyebrow">Your schedule</p>
                    <h3 className="sd-section-title" style={{ fontSize: '1.15rem' }}>My bookings</h3>
                  </div>
                </div>

                {bookingsLoading ? (
                  <p className="sd-empty">Loading…</p>
                ) : bookingsError ? (
                  <p className="sd-empty">
                    {bookingsError}{' '}
                    <button type="button" className="sd-chip" onClick={fetchMyBookings}>Retry</button>
                  </p>
                ) : activeBookings.length === 0 ? (
                  <p className="sd-empty">No active bookings yet. Join a slot to get started!</p>
                ) : (
                  <div className="sd-booking-list">
                    {activeBookings.map((bk) => (
                      <div className="sd-booking-item" key={bk.id}>
                        <div className="sd-booking-item-head">
                          <span className="sd-booking-sport">
                            <span className="sd-dot" />
                            {bk.sport}
                            {bk.is_leader && <span className="sd-leader-badge">Leader</span>}
                          </span>
                        </div>
                        <p className="sd-booking-meta">
                          🕒 {bk.slot_date ? fmtDate(bk.slot_date) : '—'}
                          {bk.slot_start_time ? ` · ${bk.slot_start_time}–${bk.slot_end_time}` : ''}
                        </p>
                        <p className="sd-booking-meta">
                          📍 {bk.slot_venue || '—'}{bk.slot_campus ? ` · ${bk.slot_campus}` : ''}
                        </p>
                        <div className="sd-booking-footer">
                          <span className="sd-status-confirmed">✓ {fmtStatus(bk.status)}</span>
                          <div className="sd-booking-footer-right">
                            <span className="sd-booking-id">#{bk.id.slice(-4)}</span>
                            <button
                              className="sd-leave-btn"
                              type="button"
                              disabled={cancelInProgress === bk.id}
                              onClick={() => handleCancel(bk.id)}
                            >
                              {cancelInProgress === bk.id ? 'Leaving…' : (<>↪ Leave slot</>)}
                            </button>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                )}

                <div className="sd-note-box">
                  <span>ℹ️</span>
                  <span>
                    You can join up to {MAX_ACTIVE_SLOTS_PER_DAY} active slots per day. Leave a slot early if your plans change.
                  </span>
                </div>
              </div>

              {/* ── History (past + cancelled bookings) ── */}
              <div className="sd-card">
                <div className="sd-card-head">
                  <div>
                    <p className="sd-section-eyebrow">Past activity</p>
                    <h3 className="sd-section-title" style={{ fontSize: '1.15rem' }}>History</h3>
                  </div>
                </div>

                {bookingsLoading ? (
                  <p className="sd-empty">Loading…</p>
                ) : historyBookings.length === 0 ? (
                  <p className="sd-empty">No past bookings yet.</p>
                ) : (
                  <div className="sd-booking-list">
                    {historyBookings.map((bk) => (
                      <div className="sd-booking-item" key={bk.id}>
                        <div className="sd-booking-item-head">
                          <span className="sd-booking-sport">
                            <span className="sd-dot" />
                            {bk.sport}
                          </span>
                        </div>
                        <p className="sd-booking-meta">
                          🕒 {bk.slot_date ? fmtDate(bk.slot_date) : '—'}
                          {bk.slot_start_time ? ` · ${bk.slot_start_time}–${bk.slot_end_time}` : ''}
                        </p>
                        <p className="sd-booking-meta">
                          📍 {bk.slot_venue || '—'}{bk.slot_campus ? ` · ${bk.slot_campus}` : ''}
                        </p>
                        <div className="sd-booking-footer">
                          <span className={bk.status === 'cancelled' ? 'sd-status-cancelled' : 'sd-status-confirmed'}>
                            {bk.status === 'cancelled' ? '✕' : '✓'} {fmtStatus(bk.status)}
                          </span>
                          <span className="sd-booking-id">#{bk.id.slice(-4)}</span>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </aside>
          </div>

          {/* ── Announcements / events (existing content, restyled) ── */}
          <div className="sd-extras">
            <div className="sd-card">
              <div className="sd-card-head">
                <h3 className="sd-section-title" style={{ fontSize: '1.05rem' }}>Announcements</h3>
              </div>
              <ul>{announcements.map(a => <li key={a}>{a}</li>)}</ul>
            </div>
            <div className="sd-card">
              <div className="sd-card-head">
                <h3 className="sd-section-title" style={{ fontSize: '1.05rem' }}>Upcoming events</h3>
              </div>
              {upcomingEvents.map(ev => (
                <div className="sd-event-row" key={ev.title}>
                  <strong>{ev.title}</strong>
                  <span>{ev.time}</span>
                </div>
              ))}
            </div>
          </div>

          <footer className="sd-footer">
            <span>Built for better campus days.</span>
            <a href="#discover" style={{ color: 'inherit', textDecoration: 'none' }}>Back to top ↑</a>
          </footer>
        </div>
      </div>
    );
  }

  const ADMIN_TABS = [
    { id: 'overview',   label: 'Dashboard',   count: null },
    { id: 'facilities', label: 'Facilities',  count: facilities.length },
    { id: 'schedule',   label: 'Schedule',     count: scheduleTemplates.length },
    { id: 'slots',      label: 'Slots',       count: adminSlots.length },
    { id: 'bookings',   label: 'Bookings',    count: allBookings.length },
    { id: 'bans',       label: 'Bans',        count: activeBans.length },
  ];
  const ADMIN_TABS_SOON = ['Users / Students'];

  const slotStatusPill = (status) => {
    if (status === 'open') return <span className="ad-pill ad-pill-open">{fmtStatus(status)}</span>;
    if (status === 'full') return <span className="ad-pill ad-pill-full">{fmtStatus(status)}</span>;
    return <span className="ad-pill ad-pill-neutral">{fmtStatus(status)}</span>;
  };

  return (
    <div className="ad-shell">
      {toast && (
        <div className={`sd-toast ${toast.ok ? 'sd-toast-ok' : 'sd-toast-err'}`}>{toast.msg}</div>
      )}

      {/* ── Sidebar navigation ── */}
      <aside className="ad-sidebar">
        <div className="ad-sidebar-brand">
          <img src="/pesu-compass-mark.webp" alt="PES University" className="ad-sidebar-logo" />
          <div className="ad-sidebar-brand-text">
            <strong>PESU SPORTS</strong>
            <span>Operations</span>
          </div>
        </div>

        <p className="ad-nav-label">Workspace</p>
        <nav className="ad-nav-list">
          {ADMIN_TABS.map(tab => (
            <button
              key={tab.id}
              type="button"
              className={`ad-nav-item ${adminTab === tab.id ? 'active' : ''}`}
              onClick={() => setAdminTab(tab.id)}
            >
              {tab.label}
              {tab.count !== null && <span className="ad-nav-count">{tab.count}</span>}
            </button>
          ))}
          {ADMIN_TABS_SOON.map(label => (
            <button key={label} type="button" className="ad-nav-item" disabled>
              {label}
              <span className="ad-nav-soon">Soon</span>
            </button>
          ))}
        </nav>

        <div className="ad-sidebar-footer">
          <div className="ad-sidebar-user">
            <span className="sd-avatar">{initials(user?.name, user?.srn)}</span>
            <div>
              <p className="ad-sidebar-user-name" style={{ margin: 0 }}>{user?.name || user?.srn}</p>
              <p className="ad-sidebar-user-role" style={{ margin: 0 }}>{user?.role || 'Admin'}</p>
            </div>
          </div>
          <button className="ad-sidebar-signout" type="button" onClick={handleLogout}>Sign out</button>
        </div>
      </aside>

      {/* ── Main content ── */}
      <main className="ad-main">
        <div className="ad-topbar">
          <div>
            <p className="ad-topbar-eyebrow">Admin Console</p>
            <h1 className="ad-topbar-title">Sports operations · RR Campus</h1>
          </div>
          <button className="ad-refresh-btn" type="button" onClick={fetchAdminData} disabled={adminLoading}>
            {adminLoading ? 'Refreshing…' : '↻ Refresh'}
          </button>
        </div>

        {/* ── Dashboard (Overview) ── */}
        {adminTab === 'overview' && (
          <>
            <div className="ad-metric-grid">
              {metricCards.map(m => (
                <div className="ad-metric-card" key={m.label}>
                  <p className="ad-metric-label">{m.label}</p>
                  <p className="ad-metric-value">{m.value}</p>
                </div>
              ))}
            </div>

            <div className="ad-card">
              <div className="ad-card-head">
                <p className="ad-card-eyebrow">Create slot</p>
                <h2 className="ad-card-title">Add new availability</h2>
              </div>
              <form className="ad-form-grid" onSubmit={handleCreateSlot}>
                <label style={{ gridColumn: '1/-1' }}>
                  <span>Facility</span>
                  <select
                    className="ad-input"
                    value={slotForm.facility_id}
                    onChange={e => setSlotForm(f => ({ ...f, facility_id: e.target.value }))}
                  >
                    <option value="">Select a facility…</option>
                    {facilities.filter(f => f.is_active).map(f => (
                      <option key={f.id} value={f.id}>{f.display_name} ({f.sport})</option>
                    ))}
                  </select>
                </label>
                {(() => {
                  const selectedFacility = facilities.find(f => f.id === slotForm.facility_id);
                  return selectedFacility ? (
                    <p className="ad-row-sub" style={{ gridColumn: '1/-1', margin: '-6px 0 0' }}>
                      {selectedFacility.sport} · capacity {selectedFacility.capacity}
                    </p>
                  ) : null;
                })()}
                <label><span>Date</span><input className="ad-input" type="date" value={slotForm.date} onChange={e => setSlotForm(f => ({ ...f, date: e.target.value }))} /></label>
                <label><span>Start time</span><input className="ad-input" type="time" value={slotForm.start_time} onChange={e => setSlotForm(f => ({ ...f, start_time: e.target.value }))} /></label>
                <label><span>End time</span><input className="ad-input" type="time" value={slotForm.end_time} onChange={e => setSlotForm(f => ({ ...f, end_time: e.target.value }))} /></label>
                <div className="ad-btn-row" style={{ gridColumn: '1/-1', marginTop: '4px' }}>
                  <button className="ad-btn-primary" type="submit" disabled={slotFormLoading}>
                    {slotFormLoading ? 'Creating…' : 'Create slot'}
                  </button>
                  <button className="ad-btn-secondary" type="button" onClick={() => setSlotForm(BLANK_SLOT)}>Reset</button>
                </div>
              </form>
            </div>
          </>
        )}

        {/* ── Facilities ── */}
        {adminTab === 'facilities' && (
          <div className="ad-card">
            <div className="ad-card-head">
              <p className="ad-card-eyebrow">RR campus inventory</p>
              <h2 className="ad-card-title">Facilities</h2>
            </div>

            {adminLoading ? (
              <p className="ad-empty">Loading facilities…</p>
            ) : facilities.length === 0 ? (
              <p className="ad-empty">No facilities found.</p>
            ) : (
              <div className="ad-row-list">
                {facilities.map(f => (
                  <div className="ad-row" key={f.id}>
                    <div className="ad-row-main">
                      <strong>{f.display_name || f.name}</strong>
                      <p className="ad-row-sub">{f.sport}</p>
                    </div>
                    <div className="ad-row-main">
                      <strong>{fmtStatus(f.facility_type)}</strong>
                      <p className="ad-row-sub">{f.name}</p>
                    </div>
                    <div className="ad-row-main">
                      <strong>{f.capacity}</strong>
                      <p className="ad-row-sub">capacity</p>
                    </div>
                    {f.is_active ? (
                      <span className="ad-pill ad-pill-open">Active</span>
                    ) : (
                      <span className="ad-pill ad-pill-neutral">Inactive</span>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* ── Schedule ── */}
        {adminTab === 'schedule' && (
          <>
            <div className="ad-card">
              <div className="ad-card-head">
                <p className="ad-card-eyebrow">{editingTemplateId ? 'Editing template' : 'New template'}</p>
                <h2 className="ad-card-title">{editingTemplateId ? 'Edit schedule template' : 'Create schedule template'}</h2>
              </div>
              <form className="ad-form-grid" onSubmit={handleSubmitTemplate}>
                <label>
                  <span>Sport</span>
                  <select
                    className="ad-input"
                    value={templateForm.sport}
                    onChange={e => setTemplateForm(f => ({ ...f, sport: e.target.value }))}
                  >
                    <option value="">Select a sport…</option>
                    {[...new Set(facilities.map(f => f.sport))].map(sport => (
                      <option key={sport} value={sport}>{sport}</option>
                    ))}
                  </select>
                </label>
                <label>
                  <span>Scope</span>
                  <select
                    className="ad-input"
                    value={templateForm.facility_scope}
                    onChange={e => setTemplateForm(f => ({ ...f, facility_scope: e.target.value, facility_id: '' }))}
                  >
                    <option value="sport">Sport-level</option>
                    <option value="facility">Facility-specific</option>
                  </select>
                </label>
                {templateForm.facility_scope === 'facility' && (
                  <label style={{ gridColumn: '1/-1' }}>
                    <span>Facility</span>
                    <select
                      className="ad-input"
                      value={templateForm.facility_id}
                      onChange={e => setTemplateForm(f => ({ ...f, facility_id: e.target.value }))}
                    >
                      <option value="">Select a facility…</option>
                      {facilities
                        .filter(f => !templateForm.sport || f.sport === templateForm.sport)
                        .map(f => (
                          <option key={f.id} value={f.id}>{f.display_name} ({f.sport})</option>
                        ))}
                    </select>
                  </label>
                )}
                <label>
                  <span>Day type</span>
                  <select
                    className="ad-input"
                    value={templateForm.day_type}
                    onChange={e => setTemplateForm(f => ({ ...f, day_type: e.target.value }))}
                  >
                    <option value="weekday">Weekday</option>
                    <option value="saturday">Saturday</option>
                    <option value="sunday">Sunday</option>
                  </select>
                </label>
                <label>
                  <span>Priority</span>
                  <input
                    className="ad-input" type="number"
                    value={templateForm.priority}
                    onChange={e => setTemplateForm(f => ({ ...f, priority: e.target.value }))}
                  />
                </label>
                <label style={{ display: 'flex', alignItems: 'center', gap: '8px', flexDirection: 'row' }}>
                  <input
                    type="checkbox"
                    checked={templateForm.is_active}
                    onChange={e => setTemplateForm(f => ({ ...f, is_active: e.target.checked }))}
                  />
                  <span>Active</span>
                </label>
                <label style={{ gridColumn: '1/-1' }}>
                  <span>Notes</span>
                  <input
                    className="ad-input"
                    value={templateForm.notes}
                    onChange={e => setTemplateForm(f => ({ ...f, notes: e.target.value }))}
                  />
                </label>

                <div style={{ gridColumn: '1/-1', display: 'flex', flexDirection: 'column', gap: '8px' }}>
                  <span>Periods</span>
                  {templateForm.periods.map((p, i) => (
                    <div key={i} style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', alignItems: 'center' }}>
                      <input className="ad-input" type="time" style={{ width: '110px' }}
                        value={p.start_time} onChange={e => updatePeriodField(i, 'start_time', e.target.value)} />
                      <input className="ad-input" type="time" style={{ width: '110px' }}
                        value={p.end_time} onChange={e => updatePeriodField(i, 'end_time', e.target.value)} />
                      <select className="ad-input" style={{ width: '130px' }}
                        value={p.period_type} onChange={e => updatePeriodField(i, 'period_type', e.target.value)}>
                        <option value="student">Student</option>
                        <option value="staff">Staff</option>
                        <option value="cleaning">Cleaning</option>
                        <option value="lunch">Lunch</option>
                      </select>
                      <label style={{ display: 'flex', alignItems: 'center', gap: '6px', flexDirection: 'row' }}>
                        <input type="checkbox" checked={p.is_bookable}
                          onChange={e => updatePeriodField(i, 'is_bookable', e.target.checked)} />
                        <span style={{ fontSize: '13px' }}>Bookable</span>
                      </label>
                      <input className="ad-input" placeholder="Label" style={{ width: '140px' }}
                        value={p.label} onChange={e => updatePeriodField(i, 'label', e.target.value)} />
                      <button type="button" className="ad-btn-secondary" onClick={() => removePeriodRow(i)}
                        disabled={templateForm.periods.length <= 1}>Remove</button>
                    </div>
                  ))}
                  <button type="button" className="ad-btn-secondary" style={{ alignSelf: 'flex-start' }} onClick={addPeriodRow}>
                    + Add period
                  </button>
                </div>

                <div className="ad-btn-row" style={{ gridColumn: '1/-1', marginTop: '4px' }}>
                  <button className="ad-btn-primary" type="submit" disabled={templateFormLoading}>
                    {templateFormLoading ? 'Saving…' : editingTemplateId ? 'Save changes' : 'Create template'}
                  </button>
                  <button className="ad-btn-secondary" type="button" onClick={cancelEditTemplate}>
                    {editingTemplateId ? 'Cancel edit' : 'Reset'}
                  </button>
                </div>
              </form>
            </div>

            <div className="ad-card">
              <div className="ad-card-head">
                <p className="ad-card-eyebrow">RR campus templates</p>
                <h2 className="ad-card-title">Schedule</h2>
              </div>

              {adminLoading ? (
                <p className="ad-empty">Loading schedule templates…</p>
              ) : scheduleTemplates.length === 0 ? (
                <p className="ad-empty">No schedule templates found.</p>
              ) : (
                <div className="ad-row-list">
                  {scheduleTemplates.map(t => (
                    <div className="ad-row" key={t.id} style={{ flexDirection: 'column', alignItems: 'stretch', gap: '10px' }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '12px' }}>
                        <div className="ad-row-main">
                          <strong>{t.facility_name || t.sport}</strong>
                          <p className="ad-row-sub">
                            {t.sport} · {t.facility_scope === 'facility' ? 'Facility-specific' : 'Sport-level'} · {fmtStatus(t.day_type)} · priority {t.priority}
                          </p>
                        </div>
                        <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                          {t.is_active ? (
                            <span className="ad-pill ad-pill-open">Active</span>
                          ) : (
                            <span className="ad-pill ad-pill-neutral">Inactive</span>
                          )}
                          <button className="ad-btn-secondary" type="button" onClick={() => startEditTemplate(t)}>Edit</button>
                          <button className="ad-btn-secondary" type="button" onClick={() => handleToggleTemplateActive(t)}>
                            {t.is_active ? 'Deactivate' : 'Activate'}
                          </button>
                          <button className="ad-btn-danger" type="button" onClick={() => handleDeleteTemplate(t.id)}>Delete</button>
                        </div>
                      </div>
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                        {(t.periods || []).map((p, i) => (
                          <div key={i} style={{ display: 'flex', justifyContent: 'space-between', gap: '12px', fontSize: '13px' }}>
                            <span>{p.start_time}–{p.end_time}{p.label ? ` · ${p.label}` : ''}</span>
                            <span style={{ display: 'flex', gap: '8px' }}>
                              <span className="ad-row-sub">{fmtStatus(p.period_type)}</span>
                              {p.is_bookable ? (
                                <span className="ad-pill ad-pill-open">Bookable</span>
                              ) : (
                                <span className="ad-pill ad-pill-neutral">Non-bookable</span>
                              )}
                            </span>
                          </div>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </>
        )}

        {/* ── Slots ── */}
        {adminTab === 'slots' && (
          <div className="ad-card">
            <div className="ad-card-head" style={{ display: 'flex', justifyContent: 'space-between', flexWrap: 'wrap', gap: '12px' }}>
              <div>
                <p className="ad-card-eyebrow">Slots &amp; bookings</p>
                <h2 className="ad-card-title">Edit or cancel existing slots</h2>
              </div>
              <div className="ad-filters">
                <select className="ad-input" style={{ width: 'auto' }} value={adminFilterCampus} onChange={e => setAdminFilterCampus(e.target.value)}>
                  <option value="">All Campuses</option>
                  {CAMPUSES.map(c => <option key={c} value={c}>{c}</option>)}
                </select>
                <select className="ad-input" style={{ width: 'auto' }} value={adminFilterSport} onChange={e => setAdminFilterSport(e.target.value)}>
                  <option value="">All Sports</option>
                  {SPORTS_LIST.map(s => <option key={s} value={s}>{s}</option>)}
                </select>
              </div>
            </div>

            {(() => {
              // Hide deprecated sports that no longer exist in the college
              const DEPRECATED = ['Swimming', 'Tennis'];
              const visibleSlots = adminSlots.filter(sl => !DEPRECATED.includes(sl.sport));
              if (visibleSlots.length === 0) return <p className="ad-empty">No slots found.</p>;
              return (
                <div className="ad-row-list">
                  {visibleSlots.map(sl => (
                    <div key={sl.id}>
                      {editingSlot === sl.id ? (
                        <div className="ad-row" style={{ alignItems: 'flex-start' }}>
                          <div className="ad-edit-grid">
                            {sl.is_manual ? (
                              <>
                                <label style={{ gridColumn: '1/-1' }}>
                                  <span>Facility</span>
                                  <select
                                    className="ad-input"
                                    value={editForm.facility_id}
                                    onChange={e => setEditForm(f => ({ ...f, facility_id: e.target.value }))}
                                  >
                                    <option value="">Select a facility…</option>
                                    {facilities.filter(f => f.is_active).map(f => (
                                      <option key={f.id} value={f.id}>{f.display_name} ({f.sport})</option>
                                    ))}
                                  </select>
                                </label>
                                <label>
                                  <span>Date</span>
                                  <input className="ad-input" type="date" value={editForm.date} onChange={e => setEditForm(f => ({ ...f, date: e.target.value }))} />
                                </label>
                                <label>
                                  <span>Start</span>
                                  <input className="ad-input" type="time" value={editForm.start_time} onChange={e => setEditForm(f => ({ ...f, start_time: e.target.value }))} />
                                </label>
                                <label>
                                  <span>End</span>
                                  <input className="ad-input" type="time" value={editForm.end_time} onChange={e => setEditForm(f => ({ ...f, end_time: e.target.value }))} />
                                </label>
                              </>
                            ) : (
                              <>
                                <label>
                                  <span>Venue</span>
                                  <input className="ad-input" value={editForm.venue} onChange={e => setEditForm(f => ({ ...f, venue: e.target.value }))} />
                                </label>
                                <label>
                                  <span>Capacity</span>
                                  <input className="ad-input" type="number" min="1" value={editForm.capacity} onChange={e => setEditForm(f => ({ ...f, capacity: e.target.value }))} />
                                </label>
                                <label>
                                  <span>Start</span>
                                  <input className="ad-input" type="time" value={editForm.start_time} onChange={e => setEditForm(f => ({ ...f, start_time: e.target.value }))} />
                                </label>
                                <label>
                                  <span>End</span>
                                  <input className="ad-input" type="time" value={editForm.end_time} onChange={e => setEditForm(f => ({ ...f, end_time: e.target.value }))} />
                                </label>
                              </>
                            )}
                          </div>
                          <div className="ad-btn-row" style={{ alignSelf: 'flex-end' }}>
                            <button className="ad-btn-primary ad-btn-sm" type="button" disabled={editLoading} onClick={() => handleSaveEdit(sl.id, sl.is_manual)}>
                              {editLoading ? '…' : 'Save'}
                            </button>
                            <button className="ad-btn-secondary ad-btn-sm" type="button" onClick={() => setEditingSlot(null)}>Discard</button>
                          </div>
                        </div>
                      ) : (
                        <div className="ad-row">
                          <div className="ad-row-main">
                            <strong>{sl.sport}</strong>
                            <p className="ad-row-sub">{sl.campus} · {sl.venue}</p>
                          </div>
                          <div className="ad-row-main">
                            <strong>{fmtDate(sl.date)}</strong>
                            <p className="ad-row-sub">{sl.start_time}–{sl.end_time}</p>
                          </div>
                          <div className="ad-occupancy">
                            <p className="ad-occupancy-label">{sl.booked_count}/{sl.capacity} booked</p>
                            <div className="ad-occupancy-bar">
                              <div
                                className="ad-occupancy-fill"
                                style={{ width: `${sl.capacity ? Math.min(100, (sl.booked_count / sl.capacity) * 100) : 0}%` }}
                              />
                            </div>
                          </div>
                          {slotStatusPill(sl.status)}
                          <div className="ad-btn-row">
                            <button className="ad-btn-secondary ad-btn-sm" type="button" onClick={() => handleViewRoster(sl.id)}>Roster</button>
                            {sl.status !== 'cancelled' && (
                              <button className="ad-btn-primary ad-btn-sm" type="button" onClick={() => startEditSlot(sl)}>Edit</button>
                            )}
                            {sl.status !== 'cancelled' && (
                              <button className="ad-btn-secondary ad-btn-sm" type="button" onClick={() => handleCancelSlot(sl.id)}>Cancel</button>
                            )}
                            <button className="ad-btn-danger ad-btn-sm" type="button" onClick={() => handleDeleteSlot(sl.id)}>Delete</button>
                          </div>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              );
            })()}
          </div>
        )}

        {/* ── Bookings ── */}
        {adminTab === 'bookings' && (
          <>
            {pendingBookings.length > 0 && (
              <div className="ad-card">
                <div className="ad-card-head">
                  <p className="ad-card-eyebrow">Pending approvals</p>
                  <h2 className="ad-card-title">{pendingBookings.length} awaiting action</h2>
                </div>
                <div className="ad-row-list">
                  {pendingBookings.map(bk => (
                    <div className="ad-row" key={bk.id}>
                      <div className="ad-row-main">
                        <strong>{bk.user?.name || '—'}</strong>
                        <p className="ad-row-sub">{bk.user?.srn}</p>
                      </div>
                      <div className="ad-row-main">
                        <strong>{bk.sport}</strong>
                        <p className="ad-row-sub">{bk.slot ? `${fmtDate(bk.slot.date)}, ${bk.slot.start_time}–${bk.slot.end_time}` : '—'}</p>
                      </div>
                      <span className="ad-pill ad-pill-neutral">Pending</span>
                      <div className="ad-btn-row">
                        <button className="ad-btn-primary ad-btn-sm" type="button" disabled={approvalInProgress === bk.id + 'approve'} onClick={() => handleApproval(bk.id, 'approve')}>
                          {approvalInProgress === bk.id + 'approve' ? '…' : 'Approve'}
                        </button>
                        <button className="ad-btn-secondary ad-btn-sm" type="button" disabled={approvalInProgress === bk.id + 'reject'} onClick={() => handleApproval(bk.id, 'reject')}>
                          {approvalInProgress === bk.id + 'reject' ? '…' : 'Reject'}
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            <div className="ad-card">
              <div className="ad-card-head">
                <p className="ad-card-eyebrow">All bookings</p>
                <h2 className="ad-card-title">Complete booking history</h2>
              </div>
              {allBookings.length === 0 ? (
                <p className="ad-empty">No bookings yet.</p>
              ) : (
                <div className="ad-row-list">
                  {allBookings.map(bk => (
                    <div className="ad-row" key={bk.id}>
                      <div className="ad-row-main">
                        <strong>{bk.user?.name || '—'}</strong>
                        <p className="ad-row-sub">{bk.user?.srn}</p>
                      </div>
                      <div className="ad-row-main">
                        <strong>{bk.sport}</strong>
                        <p className="ad-row-sub">{bk.slot ? `${fmtDate(bk.slot.date)}, ${bk.slot.start_time}–${bk.slot.end_time} · ${bk.slot.campus}` : '—'}</p>
                      </div>
                      <span className="ad-pill ad-pill-neutral">{fmtStatus(bk.status)}</span>
                      <span className="ad-row-sub">{fmt(bk.created_at)}</span>
                      {bk.status !== 'cancelled' && (
                        <button className="ad-btn-danger ad-btn-sm" type="button" onClick={() => handleAdminCancelBooking(bk.id)}>
                          Cancel
                        </button>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          </>
        )}

        {/* ── Bans ── */}
        {adminTab === 'bans' && (
          <div className="ad-card">
            <div className="ad-card-head">
              <p className="ad-card-eyebrow">Active bans</p>
              <h2 className="ad-card-title">Students with booking suspensions</h2>
            </div>
            {activeBans.length === 0 ? (
              <p className="ad-empty">No active bans.</p>
            ) : (
              <div className="ad-row-list">
                {activeBans.map(b => (
                  <div className="ad-row" key={b.id}>
                    <div className="ad-row-main">
                      <strong>{b.user_name || '—'}</strong>
                      <p className="ad-row-sub">{b.user_srn} · {b.user_email}</p>
                    </div>
                    <div className="ad-row-main">
                      <strong style={{ color: 'var(--sd-accent)' }}>Banned until</strong>
                      <p className="ad-row-sub">{fmtBanDate(b.banned_until)}</p>
                    </div>
                    <p className="ad-row-sub" style={{ flex: 1 }}>{b.reason}</p>
                    <button className="ad-btn-primary ad-btn-sm" type="button" onClick={() => handleUnban(b.user_id)}>
                      Lift ban
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </main>

      {/* ── Slot roster modal (accountability view, admin-only) ── */}
      {rosterSlotId && (
        <div className="ad-modal-overlay" onClick={closeRoster}>
          <div
            className="ad-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="roster-modal-title"
            onClick={e => e.stopPropagation()}
          >
            <div className="ad-modal-header">
              <div>
                <p className="ad-card-eyebrow">Slot roster</p>
                <h2 className="ad-card-title" id="roster-modal-title">Occupancy &amp; accountability</h2>
              </div>
              <button className="ad-modal-close" type="button" aria-label="Close slot roster" onClick={closeRoster}>✕ Close</button>
            </div>

            {rosterLoading ? (
              <p className="ad-empty">Loading roster…</p>
            ) : rosterError ? (
              <p className="ad-empty" style={{ color: 'var(--sd-accent)' }}>{rosterError}</p>
            ) : rosterData ? (
              (() => {
                const { slot, participants } = rosterData;
                const active = participants.filter(p => p.status !== 'cancelled');
                const cancelled = participants.filter(p => p.status === 'cancelled');
                const leader = active.find(p => p.is_leader);
                return (
                  <>
                    <div className="ad-roster-summary">
                      <div>
                        <p className="ad-roster-summary-label">Sport</p>
                        <p className="ad-roster-summary-value">{slot.sport}</p>
                      </div>
                      <div>
                        <p className="ad-roster-summary-label">Facility</p>
                        <p className="ad-roster-summary-value">{slot.facility_name || '—'}</p>
                      </div>
                      <div>
                        <p className="ad-roster-summary-label">Date / time</p>
                        <p className="ad-roster-summary-value">{fmtDate(slot.date)}, {slot.start_time}–{slot.end_time}</p>
                      </div>
                      <div>
                        <p className="ad-roster-summary-label">Occupancy</p>
                        <p className="ad-roster-summary-value">{slot.booked_count}/{slot.capacity} booked</p>
                      </div>
                      <div>
                        <p className="ad-roster-summary-label">Leader</p>
                        <p className="ad-roster-summary-value">{leader?.user_snapshot?.name || leader?.user_snapshot?.srn || '—'}</p>
                      </div>
                    </div>

                    <div className="ad-roster-section">
                      <p className="ad-roster-section-title">Active participants ({active.length})</p>
                      {active.length === 0 ? (
                        <p className="ad-empty">No one has joined this slot yet.</p>
                      ) : (
                        <div className="ad-roster-list">
                          {active.map(p => (
                            <div className="ad-roster-participant" key={p.booking_id}>
                              <div className="ad-roster-participant-head">
                                <span className="ad-roster-participant-name">
                                  {p.user_snapshot?.name || '—'}
                                  {p.is_leader && <span className="ad-pill ad-pill-open">Leader</span>}
                                </span>
                                <span className="ad-roster-summary-label" style={{ margin: 0 }}>
                                  Joined {fmt(p.joined_at)}
                                </span>
                              </div>
                              <div className="ad-roster-detail-grid">
                                <span><strong>SRN:</strong> {p.user_snapshot?.srn || '—'}</span>
                                <span><strong>Phone:</strong> {p.user_snapshot?.phone || '—'}</span>
                                <span><strong>Branch:</strong> {p.user_snapshot?.branch || '—'}</span>
                                <span><strong>Program:</strong> {p.user_snapshot?.program || '—'}</span>
                                <span><strong>Semester:</strong> {p.user_snapshot?.semester || '—'}</span>
                                <span><strong>Section:</strong> {p.user_snapshot?.section || '—'}</span>
                                <span><strong>Campus:</strong> {p.user_snapshot?.campus || '—'}</span>
                                <span><strong>Status:</strong> {fmtStatus(p.status)}</span>
                              </div>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>

                    <div className="ad-roster-section">
                      <p className="ad-roster-section-title">Historical / cancelled ({cancelled.length})</p>
                      {cancelled.length === 0 ? (
                        <p className="ad-empty">No cancellations recorded for this slot.</p>
                      ) : (
                        <div className="ad-roster-list">
                          {cancelled.map(p => (
                            <div className="ad-roster-participant cancelled" key={p.booking_id}>
                              <div className="ad-roster-participant-head">
                                <span className="ad-roster-participant-name">{p.user_snapshot?.name || '—'}</span>
                                <span className="ad-roster-summary-label" style={{ margin: 0 }}>
                                  Joined {fmt(p.joined_at)}
                                </span>
                              </div>
                              <div className="ad-roster-detail-grid">
                                <span><strong>SRN:</strong> {p.user_snapshot?.srn || '—'}</span>
                                <span><strong>Branch:</strong> {p.user_snapshot?.branch || '—'}</span>
                                <span><strong>Campus:</strong> {p.user_snapshot?.campus || '—'}</span>
                                <span><strong>Cancelled:</strong> {fmt(p.cancelled_at)}</span>
                                <span><strong>Cancelled by:</strong> {p.cancelled_by ? `#${p.cancelled_by.slice(-4)}` : '—'}</span>
                              </div>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  </>
                );
              })()
            ) : null}
          </div>
        </div>
      )}
    </div>
  );
}
