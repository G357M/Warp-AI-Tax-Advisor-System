/**
 * Client-side auth helpers. New sessions live in an HttpOnly cookie; the old
 * bearer token is read only as a migration fallback for existing browsers.
 */
const TOKEN_KEY = 'ta_token';
const AUTH_MARKER_KEY = 'ta_authenticated';

export type AuthErrorCode =
  | 'credentials'
  | 'inactive'
  | 'username_exists'
  | 'email_exists'
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

export async function register(username: string, email: string, password: string): Promise<void> {
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
  await login(username, password);
}
