import { authFetch } from '@/lib/auth';
import type { AdminCopy, AdminErrorCode } from '@/lib/admin-i18n';

export class AdminApiError extends Error {
  constructor(readonly status: number, readonly code: string | null, message: string) {
    super(message);
  }
}

function detailCode(detail: unknown): string | null {
  if (detail && typeof detail === 'object' && !Array.isArray(detail)) {
    const code = (detail as { code?: unknown }).code;
    return typeof code === 'string' ? code : null;
  }
  return null;
}

export async function adminSend<T>(url: string, method: 'POST' | 'PATCH', body: object): Promise<T> {
  const res = await authFetch(url, { method, body: JSON.stringify(body) });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = (data as { detail?: unknown }).detail;
    throw new AdminApiError(res.status, detailCode(detail), typeof detail === 'string' ? detail : '');
  }
  return data as T;
}

/** Localised text for a failed admin request: coded errors first, then a plain string detail. */
export function errorText(c: AdminCopy, error: unknown): string {
  if (error instanceof AdminApiError) {
    if (error.code && error.code in c.errors) return c.errors[error.code as AdminErrorCode];
    if (error.message) return error.message;
  }
  return c.common.saveError;
}
