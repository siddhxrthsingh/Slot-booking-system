// Shared display-only date/time formatting helpers.
// Stored values (Mongo/API) are never touched here — these only affect what
// is rendered to the user.

// Slot/booking "date" fields represent a calendar day (stored as UTC
// midnight), not a point-in-time timestamp — read UTC components directly so
// formatting never shifts the calendar day shown, regardless of the
// viewer's browser timezone.
export function formatDateDMY(dateLike) {
  if (!dateLike) return '—';
  const d = new Date(dateLike);
  if (Number.isNaN(d.getTime())) return '—';
  const day = String(d.getUTCDate()).padStart(2, '0');
  const month = String(d.getUTCMonth() + 1).padStart(2, '0');
  const year = d.getUTCFullYear();
  return `${day}-${month}-${year}`;
}

// Point-in-time timestamps (joined_at, cancelled_at, banned_until, ...) must
// display in Indian Standard Time regardless of stored/browser timezone.
export function formatDateTimeIST(dateLike) {
  if (!dateLike) return '—';
  const d = new Date(dateLike);
  if (Number.isNaN(d.getTime())) return '—';
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone: 'Asia/Kolkata',
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    hour12: true,
  }).formatToParts(d);
  const get = (type) => parts.find((p) => p.type === type)?.value || '';
  return `${get('day')}-${get('month')}-${get('year')}, ${get('hour')}:${get('minute')} ${get('dayPeriod')}`;
}

// UTC calendar-day key (yyyy-mm-dd), used to group/compare slot dates
// consistently with how the backend buckets slots by UTC day.
export function isoDateOnly(dateLike) {
  if (!dateLike) return '';
  const d = new Date(dateLike);
  if (Number.isNaN(d.getTime())) return '';
  return d.toISOString().slice(0, 10);
}

// ── IST business-day helpers ────────────────────────────────────────────────
// This application serves PES University RR Campus (India) exclusively, so
// "today"/"tomorrow"/"day after tomorrow" and slot expiry must always be
// decided from the current date/time in Asia/Kolkata — never the viewer's
// browser-local timezone (Date.toISOString()/getDate() etc. use browser
// local time, which silently shifts the calendar day for any viewer whose
// local clock isn't already IST, and even for IST viewers, naive UTC
// conversion mishandles the offset near local midnight).

const IST_OFFSET_MS = 5.5 * 60 * 60 * 1000;

// { year, month (1-12), day } of `from` as seen in Asia/Kolkata.
function istDateParts(from = new Date()) {
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Kolkata',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).formatToParts(from);
  const get = (type) => parts.find((p) => p.type === type)?.value;
  return { year: Number(get('year')), month: Number(get('month')), day: Number(get('day')) };
}

// A UTC-midnight Date object representing the IST calendar date `offsetDays`
// days from `from` (0 = today in IST, 1 = tomorrow, 2 = day after tomorrow).
// This matches the backend's calendar-day-bucket convention for slot.date.
export function istCalendarDate(offsetDays = 0, from = new Date()) {
  const { year, month, day } = istDateParts(from);
  const d = new Date(Date.UTC(year, month - 1, day));
  d.setUTCDate(d.getUTCDate() + offsetDays);
  return d;
}

// "YYYY-MM-DD" key for the IST calendar date `offsetDays` days from `from` —
// used as the API `date` query param so the backend never has to guess which
// calendar day was intended.
export function istDateKey(offsetDays = 0, from = new Date()) {
  const d = istCalendarDate(offsetDays, from);
  const y = d.getUTCFullYear();
  const m = String(d.getUTCMonth() + 1).padStart(2, '0');
  const day = String(d.getUTCDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

// A slot's `date` field is a calendar-day bucket (UTC midnight of that plain
// calendar date); its start_time/end_time strings are IST wall-clock times
// (RR campus business hours). This resolves the actual UTC instant a given
// HH:MM on that calendar day represents, for correct expiry comparisons
// against a real UTC "now".
export function slotTimeToUtcInstant(dateLike, hhmm) {
  const d = new Date(dateLike);
  const [h, m] = (hhmm || '00:00').split(':').map(Number);
  const utcMs = Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate(), h, m) - IST_OFFSET_MS;
  return new Date(utcMs);
}
