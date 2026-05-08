import client from './client';

export async function login(username, password) {
  const { data } = await client.post('/auth/login', { username, password });
  return data.data; // { access_token, refresh_token, user }
}

export async function logout(refreshToken) {
  await client.post('/auth/logout', { refresh_token: refreshToken });
}

export async function refreshToken(token) {
  const { data } = await client.post('/auth/refresh', { refresh_token: token });
  return data.data; // { access_token }
}

export async function getMe() {
  const { data } = await client.get('/auth/me');
  return data.data;
}
