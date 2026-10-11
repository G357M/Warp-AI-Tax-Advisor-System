'use client';

import { useState } from 'react';
import { GlassDialog } from '@/components/ui/Dialog';
import styles from '@/app/admin/admin.module.css';
import { useAdminCopy } from '@/lib/admin-i18n';

export function ConfirmDialog({ open, onOpenChange, title, description, confirmLabel, withReason = true, onConfirm }: {
  open: boolean; onOpenChange: (open: boolean) => void; title: string; description?: string;
  confirmLabel?: string; withReason?: boolean; onConfirm: (reason: string) => Promise<void>;
}) {
  const { c } = useAdminCopy();
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const change = (next: boolean) => {
    if (busy) return;
    if (!next) { setReason(''); setError(null); }
    onOpenChange(next);
  };

  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      await onConfirm(reason.trim());
      setReason('');
      onOpenChange(false);
    } catch (e) {
      setError(e instanceof Error && e.message ? e.message : c.common.saveError);
    } finally {
      setBusy(false);
    }
  };

  return <GlassDialog open={open} onOpenChange={change} title={title} closeLabel={c.common.cancel}>
    <div className={styles.dialogBody}>
      {description && <p>{description}</p>}
      {withReason && <label className={styles.field}>
        {c.common.reason}
        <textarea className={styles.textarea} maxLength={1000} value={reason}
          onChange={(e) => setReason(e.target.value)} />
        <span className={styles.muted}>{c.common.reasonHint}</span>
      </label>}
      {error && <p className={styles.noticeError} role="alert">{error}</p>}
      <div className={styles.dialogActions}>
        <button type="button" className={styles.button} onClick={() => change(false)} disabled={busy}>{c.common.cancel}</button>
        <button type="button" className={`${styles.button} ${styles.buttonPrimary}`} onClick={submit} disabled={busy}>
          {confirmLabel ?? c.common.confirm}
        </button>
      </div>
    </div>
  </GlassDialog>;
}
