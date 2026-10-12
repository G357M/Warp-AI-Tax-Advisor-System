'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { authFetch } from '@/lib/auth';
import { useAdminCopy } from '@/lib/admin-i18n';
import { reconciliationCopy } from '@/lib/billing-reconciliation';
import {
  DashboardIcon, FileTextIcon, PersonIcon, ActivityLogIcon, BarChartIcon, ChatBubbleIcon,
  GearIcon, ExitIcon, CheckCircledIcon, HamburgerMenuIcon, CardStackIcon, ReaderIcon,
} from '@radix-ui/react-icons';
import styles from './admin.module.css';

const navigation = [
  { key: 'dashboard', href: '/admin', icon: DashboardIcon },
  { key: 'users', href: '/admin/users', icon: PersonIcon },
  { key: 'quality', href: '/admin/quality', icon: CheckCircledIcon },
  { key: 'payments', href: '/admin/billing', icon: CardStackIcon },
  { key: 'feedback', href: '/admin/feedback', icon: ChatBubbleIcon },
  { key: 'documents', href: '/admin/documents', icon: FileTextIcon },
  { key: 'analytics', href: '/admin/analytics', icon: BarChartIcon },
  { key: 'scraper', href: '/admin/scraper', icon: ActivityLogIcon },
  { key: 'audit', href: '/admin/audit', icon: ReaderIcon },
  { key: 'config', href: '/admin/settings', icon: GearIcon },
] as const;

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { lang, c } = useAdminCopy();
  const [openPath, setOpenPath] = useState<string | null>(null);
  const [admin, setAdmin] = useState<{ username: string } | null>(null);
  const menuOpen = openPath === pathname;

  useEffect(() => {
    const controller = new AbortController();
    authFetch('/api/v1/auth/me', { signal: controller.signal, cache: 'no-store' })
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then((me) => {
        if (controller.signal.aborted) return;
        if (me.role === 'admin') setAdmin({ username: me.username });
        else router.replace('/login');
      })
      .catch(() => { if (!controller.signal.aborted) router.replace('/login'); });
    return () => controller.abort();
  }, [router]);

  if (!admin) return <div className={styles.checking} role="status">{c.nav.checking}</div>;

  return <div className={styles.frame}>
    <header className={styles.header}>
      <div className={styles.brand}><strong>Tax Advisor</strong><span>{c.nav.admin}</span></div>
      <span className={styles.username}>{admin.username}</span>
      <button type="button" className={styles.menuButton} aria-expanded={menuOpen} aria-controls="admin-navigation"
        onClick={() => setOpenPath(menuOpen ? null : pathname)}>
        <HamburgerMenuIcon aria-hidden="true" />{c.nav.menu}
      </button>
    </header>
    <div className={styles.workspace}>
      <aside id="admin-navigation" className={styles.sidebar} data-open={menuOpen}>
        <nav aria-label={c.nav.menu}>
          {navigation.map((item) => {
            const active = pathname === item.href || (item.href !== '/admin' && pathname.startsWith(`${item.href}/`));
            const Icon = item.icon;
            const label = item.key === 'payments' ? reconciliationCopy[lang].title : c.nav[item.key];
            return <Link key={item.href} href={item.href} aria-current={active ? 'page' : undefined}
              onClick={() => setOpenPath(null)}>
              <Icon aria-hidden="true" />{label}
            </Link>;
          })}
        </nav>
        <Link href="/" className={styles.back}><ExitIcon aria-hidden="true" />{c.nav.back}</Link>
      </aside>
      <main className={styles.content}>{children}</main>
    </div>
  </div>;
}
