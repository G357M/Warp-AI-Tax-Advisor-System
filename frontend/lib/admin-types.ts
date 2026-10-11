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
export function summarizeChange(entry: AuditEntry): string {
  const keys = new Set([...Object.keys(entry.before ?? {}), ...Object.keys(entry.after ?? {})]);
  return [...keys].map((key) => {
    const from = entry.before?.[key];
    const to = entry.after?.[key];
    return `${key}: ${from == null ? '—' : String(from)} → ${to == null ? '—' : String(to)}`;
  }).join('; ');
}
