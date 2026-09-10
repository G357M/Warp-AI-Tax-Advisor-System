'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { authFetch } from '@/lib/auth';
import { useT } from '@/lib/i18n';
import { reconciliationCopy } from '@/lib/billing-reconciliation';
import {
  DashboardIcon, FileTextIcon, PersonIcon, ActivityLogIcon,
  BarChartIcon, ChatBubbleIcon, GearIcon, ExitIcon, HamburgerMenuIcon,
} from '@radix-ui/react-icons';
import styles from './admin.module.css';

const navigation = [
  { name: 'Dashboard', href: '/admin', icon: DashboardIcon },
  { name: 'Documents', href: '/admin/documents', icon: FileTextIcon },
  { name: 'Analytics', href: '/admin/analytics', icon: BarChartIcon },
  { name: 'Users', href: '/admin/users', icon: PersonIcon },
  { name: 'Payments', href: '/admin/billing', icon: FileTextIcon },
  { name: 'Feedback', href: '/admin/feedback', icon: ChatBubbleIcon },
  { name: 'Scraper', href: '/admin/scraper', icon: ActivityLogIcon },
  { name: 'Settings', href: '/admin/settings', icon: GearIcon },
];

const copy = {
  ru: { menu: 'Меню администратора', checking: 'Проверяем доступ…', admin: 'Администрирование', back: 'На сайт' },
  ka: { menu: 'ადმინისტრატორის მენიუ', checking: 'წვდომა მოწმდება…', admin: 'ადმინისტრირება', back: 'საიტზე დაბრუნება' },
  en: { menu: 'Administrator menu', checking: 'Checking access…', admin: 'Administration', back: 'Back to site' },
};

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { lang } = useT();
  const c = copy[lang];
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

  if (!admin) return <div className={styles.checking} role="status">{c.checking}</div>;

  return <div className={styles.frame}>
    <header className={styles.header}>
      <div><strong>Tax Advisor</strong><span>{c.admin}</span></div>
      <span className={styles.username}>{admin.username}</span>
      <button type="button" className={styles.menuButton} aria-expanded={menuOpen} aria-controls="admin-navigation"
        onClick={() => setOpenPath(menuOpen ? null : pathname)}>
        <HamburgerMenuIcon aria-hidden="true" />{c.menu}
      </button>
    </header>
    <div className={styles.workspace}>
      <aside id="admin-navigation" className={styles.sidebar} data-open={menuOpen}>
        <nav aria-label={c.menu}>
          {navigation.map((item) => {
            const active = pathname === item.href || (item.href !== '/admin' && pathname.startsWith(`${item.href}/`));
            const Icon = item.icon;
            return <Link key={item.href} href={item.href} aria-current={active ? 'page' : undefined}
              onClick={() => setOpenPath(null)}>
              <Icon aria-hidden="true" />
              {item.href === '/admin/billing' ? reconciliationCopy[lang].title : item.name}
            </Link>;
          })}
        </nav>
        <Link href="/" className={styles.back}><ExitIcon aria-hidden="true" />{c.back}</Link>
      </aside>
      <main className={styles.content}>{children}</main>
    </div>
  </div>;
}
