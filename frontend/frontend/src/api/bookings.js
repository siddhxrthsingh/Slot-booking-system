import client from './client';

export async function getAvailableSlots({ sport, date, campus, venue } = {}) {
  const params = {};
  if (sport) params.sport = sport;
  if (date) params.date = date;
  if (campus) params.campus = campus;
  if (venue) params.venue = venue;
  const { data } = await client.get('/bookings/available', { params });
  return data.data;
}

export async function createBooking(slotId, notes = null) {
  const { data } = await client.post('/bookings/create', { slot_id: slotId, notes });
  return data.data;
}

export async function getMyBookings(status = null) {
  const params = {};
  if (status) params.status = status;
  const { data } = await client.get('/bookings/my-bookings', { params });
  return data.data;
}

export async function cancelBooking(bookingId) {
  const { data } = await client.delete(`/bookings/${bookingId}`);
  return data.data;
}

export async function getMyBanStatus() {
  const { data } = await client.get('/bookings/my-ban');
  return data.data;
}
