export interface AuditEntry {
  id: string;
  actor: { id: string; username: string | null };
  action: string;
  target_type: string;
  target_id: string;
  before: Record<string, unknown> | null;
  after: Record<string, unknown> | null;
  reason: string | null;
  created_at: string;
}

export interface AuditPage { total: number; items: AuditEntry[] }

export interface AdminStats {
  documents: { total: number; by_type: Record<string, number>; last_ingest: string | null };
  decisions: { total: number; extracted: number; pending: number };
  amendments: { acts_total: number; extracted: number; resolved: number; pending: number };
  users: { total: number; admins: number };
  subscriptions: Record<string, number>;
  conversations: { total: number; messages: number; messages_7d: number };
  feedback: { new: number };
  billing: { reconciliation_open: number; manual_pending: number };
  attention: { ingest_stale: boolean };
}

export type AdminConfig = Record<string, Record<string, string | number | boolean | null>>;

/** "role: user → admin" style summary of an audit entry's change. */
function show(value: unknown): string {
  if (value == null) return '—';
  return typeof value === 'object' ? JSON.stringify(value) : String(value);
}

export function summarizeChange(entry: AuditEntry): string {
  const keys = new Set([...Object.keys(entry.before ?? {}), ...Object.keys(entry.after ?? {})]);
  return [...keys].map((key) => {
    const from = entry.before?.[key];
    const to = entry.after?.[key];
    return `${key}: ${show(from)} → ${show(to)}`;
  }).join('; ');
}

export type PlanId = 'free' | 'pro' | 'business';

export interface AdminUserRow {
  id: string; username: string; email: string; role: 'user' | 'admin';
  created_at: string | null; last_login: string | null; plan: PlanId; period_end: string | null;
  is_active: boolean; email_verified: boolean;
}

export interface UsersPage { total: number; items: AdminUserRow[] }

export interface UserCard {
  profile: {
    id: string; username: string; email: string; full_name: string | null; role: 'user' | 'admin';
    effective_plan: PlanId; is_active: boolean; email_verified: boolean;
    created_at: string | null; last_login: string | null;
  };
  subscription: {
    plan: PlanId; status: 'active' | 'past_due' | 'canceled'; period_start: string | null;
    period_end: string | null; days_left: number | null; source: 'grant' | 'payment';
  } | null;
  payments: { id: string; created_at: string | null; amount_minor: number; currency: string; provider: string; status: string }[];
  checkouts: {
    id: string; created_at: string | null; plan: PlanId; months: number; amount_minor: number; currency: string;
    provider: string; status: string; expires_at: string | null;
  }[];
  activity: {
    conversations_7d: number; conversations_30d: number; questions_7d: number; questions_30d: number;
    questions_today: number | null; daily_limit: number | null; feedback_total: number;
  };
}

export type UserCardResponse = UserCard & { changed: boolean; sent?: boolean };
