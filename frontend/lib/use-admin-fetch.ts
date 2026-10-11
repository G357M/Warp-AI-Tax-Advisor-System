'use client';

import { useCallback, useEffect, useState } from 'react';
import { authFetch } from '@/lib/auth';

type Loaded<T> = { key: string | null; data: T | null; error: boolean; status: number | null };

/** GET `url` with the admin token; a newer url (or reload) aborts the older request so a slow
 *  stale response can never overwrite fresh data. `null` skips the request. */
export function useAdminFetch<T>(url: string | null) {
  const [nonce, setNonce] = useState(0);
  const [loaded, setLoaded] = useState<Loaded<T>>({ key: null, data: null, error: false, status: null });
  const key = url === null ? null : `${nonce}|${url}`;

  useEffect(() => {
    if (url === null) return;
    const controller = new AbortController();
    const requestKey = `${nonce}|${url}`;
    authFetch(url, { signal: controller.signal })
      .then(async (res) => {
        if (!res.ok) throw Object.assign(new Error('http'), { status: res.status });
        const data = (await res.json()) as T;
        if (!controller.signal.aborted) setLoaded({ key: requestKey, data, error: false, status: res.status });
      })
      .catch((e: { status?: number }) => {
        if (controller.signal.aborted) return;
        setLoaded((prev) => ({ key: requestKey, data: prev.data, error: true, status: e.status ?? 0 }));
      });
    return () => controller.abort();
  }, [url, nonce]);

  const reload = useCallback(() => setNonce((n) => n + 1), []);
  const setData = useCallback((data: T) => setLoaded((prev) => ({ ...prev, data, error: false })), []);
  const current = loaded.key === key;
  return {
    data: loaded.data,
    error: current && loaded.error,
    status: current ? loaded.status : null,
    loading: key !== null && !current,
    reload,
    setData,
  };
}
