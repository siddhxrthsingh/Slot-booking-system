import client from './client';

export async function getAdminSlots({ campus, sport } = {}) {
  const params = {};
  if (campus) params.campus = campus;
  if (sport) params.sport = sport;
  const { data } = await client.get('/admin/slots', { params });
  return data.data;
}

export async function createSlot(slotData) {
  const { data } = await client.post('/admin/slots/create', slotData);
  return data.data;
}

export async function updateSlot(slotId, updates) {
  const { data } = await client.patch(`/admin/slots/${slotId}`, updates);
  return data.data;
}

export async function cancelSlot(slotId) {
  const { data } = await client.delete(`/admin/slots/${slotId}/cancel`);
  return data.data;
}

export async function deleteSlotPermanently(slotId) {
  const { data } = await client.delete(`/admin/slots/${slotId}/delete`);
  return data.data;
}

export async function getPendingBookings() {
  const { data } = await client.get('/admin/bookings/pending');
  return data.data;
}

export async function getAllBookings(status = null) {
  const params = {};
  if (status) params.status = status;
  const { data } = await client.get('/admin/bookings', { params });
  return data.data;
}

export async function processBookingApproval(bookingId, action, notes = null) {
  const { data } = await client.patch(`/admin/bookings/${bookingId}/approve`, { action, notes });
  return data.data;
}

export async function adminCancelBooking(bookingId) {
  const { data } = await client.delete(`/admin/bookings/${bookingId}/cancel`);
  return data.data;
}

export async function getMetrics() {
  const { data } = await client.get('/admin/metrics');
  return data.data;
}

export async function getActiveBans() {
  const { data } = await client.get('/admin/bans');
  return data.data;
}

export async function unbanUser(userId) {
  const { data } = await client.delete(`/admin/bans/${userId}`);
  return data.data;
}

export async function getAllUsers({ campus } = {}) {
  const params = {};
  if (campus) params.campus = campus;
  const { data } = await client.get('/admin/users', { params });
  return data.data;
}
