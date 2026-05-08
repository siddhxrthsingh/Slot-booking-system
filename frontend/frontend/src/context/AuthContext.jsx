import { createContext, useContext, useState, useCallback } from 'react';
import { login as apiLogin, logout as apiLogout } from '../api/auth';

const AuthContext = createContext(null);

// Session-only helpers — data is cleared when the browser tab is closed
const session = {
  get: (k) => { try { return JSON.parse(sessionStorage.getItem(k)); } catch { return null; } },
  set: (k, v) => sessionStorage.setItem(k, typeof v === 'string' ? v : JSON.stringify(v)),
  remove: (...keys) => keys.forEach((k) => sessionStorage.removeItem(k)),
};

export function AuthProvider({ children }) {
  const [user, setUser] = useState(() => session.get('user'));

  const login = useCallback(async (username, password) => {
    const { access_token, refresh_token, user: profile } = await apiLogin(username, password);
    session.set('access_token', access_token);
    session.set('refresh_token', refresh_token);
    session.set('user', profile);
    setUser(profile);
    return profile;
  }, []);

  const logout = useCallback(async () => {
    const refreshToken = session.get('refresh_token');
    try {
      if (refreshToken) await apiLogout(refreshToken);
    } catch {
      // ignore errors on logout
    } finally {
      session.remove('access_token', 'refresh_token', 'user');
      setUser(null);
    }
  }, []);

  return (
    <AuthContext.Provider value={{ user, login, logout, isAdmin: user?.role === 'admin' }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used inside AuthProvider');
  return ctx;
}
