import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import './Login.css';

export default function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();

  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  async function handleSubmit(e) {
    e.preventDefault();
    setError('');
    if (!username.trim() || !password.trim()) {
      setError('Please enter your credentials.');
      return;
    }
    setLoading(true);
    try {
      const profile = await login(username.trim(), password);
      navigate(profile.role === 'admin' ? '/?portal=admin' : '/');
    } catch (err) {
      const status = err.response?.status;
      if (status === 401) {
        setError('Invalid username or password. Please try again.');
      } else if (status === 503) {
        setError('Authentication service is temporarily unavailable. Try again in a moment.');
      } else {
        setError(err.response?.data?.detail || 'Something went wrong. Please try again.');
      }
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="pesu-login-page">
      <div className="pesu-bg-overlay" />

      <div className="pesu-logo-corner">
        <img src="/pesu-logo.png" alt="PES University" className="pesu-logo-img" />
      </div>

      <div className="pesu-card">
        <h1 className="pesu-title">Sign in</h1>

        <form onSubmit={handleSubmit} noValidate>
          <div className="pesu-field">
            <input
              className={`pesu-input ${error ? 'pesu-input-error' : ''}`}
              type="text"
              placeholder="Username"
              value={username}
              onChange={(e) => { setUsername(e.target.value); setError(''); }}
              autoFocus
              autoComplete="username"
              disabled={loading}
            />
          </div>

          <div className="pesu-field pesu-password-wrap">
            <input
              className={`pesu-input ${error ? 'pesu-input-error' : ''}`}
              type={showPassword ? 'text' : 'password'}
              placeholder="Password"
              value={password}
              onChange={(e) => { setPassword(e.target.value); setError(''); }}
              autoComplete="current-password"
              disabled={loading}
            />
            <button
              type="button"
              className="pesu-eye-btn"
              onClick={() => setShowPassword((v) => !v)}
              tabIndex={-1}
              aria-label={showPassword ? 'Hide password' : 'Show password'}
            >
              {showPassword ? (
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94"/>
                  <path d="M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19"/>
                  <line x1="1" y1="1" x2="23" y2="23"/>
                </svg>
              ) : (
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>
                  <circle cx="12" cy="12" r="3"/>
                </svg>
              )}
            </button>
          </div>

          {error && (
            <div className="pesu-error-msg">
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" style={{ flexShrink: 0 }}>
                <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>
              </svg>
              {error}
            </div>
          )}

          <button className="pesu-signin-btn" type="submit" disabled={loading}>
            {loading ? <span className="pesu-spinner" /> : 'Sign In'}
          </button>
        </form>

        <p className="pesu-hint">
          Students: use your PESU Academy credentials (SRN, PRN, email, or phone).<br />
          <span style={{ opacity: 0.6 }}>Staff / Admin: use your Employee ID (e.g. EMP001).</span>
        </p>
      </div>

      <p className="pesu-footer">PESU Sports Slot Booking &nbsp;·&nbsp; PES University</p>
    </div>
  );
}
