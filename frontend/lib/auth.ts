/**
 * Client-side auth helpers. New sessions live in an HttpOnly cookie; the old
 * bearer token is read only as a migration fallback for existing browsers.
 */
const TOKEN_KEY = 'ta_token';
const AUTH_MARKER_KEY = 'ta_authenticated';

export type AuthErrorCode =
  | 'credentials'
  | 'inactive'
  | 'verification_required'
  | 'username_exists'
  | 'email_exists'
  | 'invalid_token'
  | 'service';

export class AuthClientError extends Error {
  constructor(readonly code: AuthErrorCode) {
    super(code);
  }
}

export function getToken(): string | null {
  if (typeof window === 'undefined') return null;
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string) {
  // The server has already set the HttpOnly cookie. Keep only a non-sensitive
  // UI marker and remove any legacy readable JWT.
  void token;
  localStorage.removeItem(TOKEN_KEY);
  localStorage.setItem(AUTH_MARKER_KEY, '1');
  window.dispatchEvent(new Event('ta-auth-changed'));
}

export function clearToken() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(AUTH_MARKER_KEY);
  window.dispatchEvent(new Event('ta-auth-changed'));
}

export function isLoggedIn(): boolean {
  if (typeof window === 'undefined') return false;
  return localStorage.getItem(AUTH_MARKER_KEY) === '1' || !!getToken();
}

export async function authFetch(input: string, init: RequestInit = {}): Promise<Response> {
  const token = getToken();
  const headers = new Headers(init.headers);
  if (token) headers.set('Authorization', `Bearer ${token}`);
  if (init.body && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json');
  const res = await fetch(input, { ...init, headers, credentials: 'same-origin' });
  if (res.status === 401) clearToken();
  return res;
}

export async function login(username: string, password: string): Promise<void> {
  const res = await fetch('/api/v1/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'same-origin',
    body: JSON.stringify({ username, password }),
  });
  if (!res.ok) {
    const detail = (await res.json().catch(() => null))?.detail;
    if (res.status === 401 || detail === 'Incorrect username or password') {
      throw new AuthClientError('credentials');
    }
    if (res.status === 403 || detail === 'Inactive user') {
      if (detail === 'Email verification required') {
        throw new AuthClientError('verification_required');
      }
      throw new AuthClientError('inactive');
    }
    throw new AuthClientError('service');
  }
  const data = await res.json();
  setToken(data.access_token);
}

export async function logout(): Promise<void> {
  try {
    await fetch('/api/v1/auth/logout', {
      method: 'POST',
      credentials: 'same-origin',
    });
  } finally {
    clearToken();
  }
}

export async function register(
  username: string,
  email: string,
  password: string,
): Promise<{ verificationRequired: boolean }> {
  const res = await fetch('/api/v1/auth/register', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, email, password }),
  });
  if (!res.ok) {
    const detail = (await res.json().catch(() => null))?.detail;
    if (detail === 'Username already registered') {
      throw new AuthClientError('username_exists');
    }
    if (detail === 'Email already registered') {
      throw new AuthClientError('email_exists');
    }
    throw new AuthClientError('service');
  }
  const data = await res.json();
  const verificationRequired = data.verification_required === true;
  if (!verificationRequired) await login(username, password);
  return { verificationRequired };
}

async function requestEmailAction(path: string, email: string): Promise<void> {
  const res = await fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email }),
  });
  if (!res.ok) throw new AuthClientError('service');
}

export function requestPasswordReset(email: string): Promise<void> {
  return requestEmailAction('/api/v1/auth/forgot-password', email);
}

export function resendVerification(email: string): Promise<void> {
  return requestEmailAction('/api/v1/auth/resend-verification', email);
}

export async function verifyEmail(token: string): Promise<void> {
  const res = await fetch('/api/v1/auth/verify-email', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ token }),
  });
  if (!res.ok) {
    if (res.status === 400 || res.status === 422) {
      throw new AuthClientError('invalid_token');
    }
    throw new AuthClientError('service');
  }
}

export async function resetPassword(token: string, newPassword: string): Promise<void> {
  const res = await fetch('/api/v1/auth/reset-password', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ token, new_password: newPassword }),
  });
  if (!res.ok) {
    if (res.status === 400 || res.status === 422) {
      throw new AuthClientError('invalid_token');
    }
    throw new AuthClientError('service');
  }
}
