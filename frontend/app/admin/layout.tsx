'use client';

import { useState } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { motion } from 'framer-motion';
import {
  DashboardIcon,
  FileTextIcon,
  PersonIcon,
  ActivityLogIcon,
  GearIcon,
  ExitIcon,
} from '@radix-ui/react-icons';

const navigation = [
  { name: 'Dashboard', href: '/admin', icon: DashboardIcon },
  { name: 'Documents', href: '/admin/documents', icon: FileTextIcon },
  { name: 'Users', href: '/admin/users', icon: PersonIcon },
  { name: 'Scraper', href: '/admin/scraper', icon: ActivityLogIcon },
  { name: 'Settings', href: '/admin/settings', icon: GearIcon },
];

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [sidebarOpen, setSidebarOpen] = useState(true);

  return (
    <div style={{ display: 'flex', height: '100vh', background: '#0f172a', color: 'white' }}>
      {/* Sidebar */}
      <motion.aside
        initial={{ x: -280 }}
        animate={{ x: sidebarOpen ? 0 : -280 }}
        style={{
          width: '280px',
          background: 'linear-gradient(180deg, #1e293b 0%, #0f172a 100%)',
          borderRight: '1px solid rgba(255,255,255,0.1)',
          display: 'flex',
          flexDirection: 'column',
          position: 'fixed',
          height: '100vh',
          zIndex: 100,
        }}
      >
        {/* Logo */}
        <div
          style={{
            padding: '1.5rem',
            borderBottom: '1px solid rgba(255,255,255,0.1)',
          }}
        >
          <h1 style={{ fontSize: '1.5rem', fontWeight: 'bold', margin: 0 }}>
            InfoHub AI
          </h1>
          <p style={{ fontSize: '0.875rem', opacity: 0.7, margin: '0.25rem 0 0 0' }}>
            Admin Panel
          </p>
        </div>

        {/* Navigation */}
        <nav style={{ flex: 1, padding: '1rem', overflowY: 'auto' }}>
          {navigation.map((item) => {
            const isActive = pathname === item.href || (item.href !== '/admin' && pathname.startsWith(item.href));
            const Icon = item.icon;

            return (
              <Link key={item.name} href={item.href} style={{ textDecoration: 'none' }}>
                <motion.div
                  whileHover={{ x: 4 }}
                  whileTap={{ scale: 0.98 }}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '0.75rem',
                    padding: '0.75rem 1rem',
                    borderRadius: '0.5rem',
                    marginBottom: '0.5rem',
                    background: isActive
                      ? 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)'
                      : 'transparent',
                    color: 'white',
                    cursor: 'pointer',
                    transition: 'background 0.2s',
                  }}
                  onMouseEnter={(e) => {
                    if (!isActive) {
                      e.currentTarget.style.background = 'rgba(255,255,255,0.05)';
                    }
                  }}
                  onMouseLeave={(e) => {
                    if (!isActive) {
                      e.currentTarget.style.background = 'transparent';
                    }
                  }}
                >
                  <Icon style={{ width: '20px', height: '20px' }} />
                  <span style={{ fontSize: '0.875rem', fontWeight: isActive ? '600' : '400' }}>
                    {item.name}
                  </span>
                </motion.div>
              </Link>
            );
          })}
        </nav>

        {/* Footer */}
        <div
          style={{
            padding: '1rem',
            borderTop: '1px solid rgba(255,255,255,0.1)',
          }}
        >
          <Link href="/" style={{ textDecoration: 'none' }}>
            <motion.div
              whileHover={{ x: 4 }}
              whileTap={{ scale: 0.98 }}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '0.75rem',
                padding: '0.75rem 1rem',
                borderRadius: '0.5rem',
                background: 'transparent',
                color: 'white',
                cursor: 'pointer',
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.background = 'rgba(255,255,255,0.05)';
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.background = 'transparent';
              }}
            >
              <ExitIcon style={{ width: '20px', height: '20px' }} />
              <span style={{ fontSize: '0.875rem' }}>Back to App</span>
            </motion.div>
          </Link>
        </div>
      </motion.aside>

      {/* Main Content */}
      <main
        style={{
          marginLeft: sidebarOpen ? '280px' : '0',
          flex: 1,
          display: 'flex',
          flexDirection: 'column',
          transition: 'margin-left 0.3s',
        }}
      >
        {/* Top Bar */}
        <header
          style={{
            height: '64px',
            borderBottom: '1px solid rgba(255,255,255,0.1)',
            background: 'rgba(30,41,59,0.5)',
            backdropFilter: 'blur(10px)',
            display: 'flex',
            alignItems: 'center',
            padding: '0 2rem',
            justifyContent: 'space-between',
          }}
        >
          <button
            onClick={() => setSidebarOpen(!sidebarOpen)}
            style={{
              background: 'rgba(255,255,255,0.1)',
              border: 'none',
              borderRadius: '0.5rem',
              padding: '0.5rem 1rem',
              color: 'white',
              cursor: 'pointer',
              fontSize: '0.875rem',
            }}
          >
            {sidebarOpen ? '←' : '→'} {sidebarOpen ? 'Hide' : 'Show'} Sidebar
          </button>

          <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '0.5rem',
                padding: '0.5rem 1rem',
                background: 'rgba(74,222,128,0.1)',
                borderRadius: '2rem',
                fontSize: '0.875rem',
              }}
            >
              <div
                style={{
                  width: '8px',
                  height: '8px',
                  borderRadius: '50%',
                  background: '#4ade80',
                }}
              />
              <span style={{ color: '#4ade80' }}>System Online</span>
            </div>

            <div
              style={{
                padding: '0.5rem 1rem',
                background: 'rgba(255,255,255,0.05)',
                borderRadius: '0.5rem',
                fontSize: '0.875rem',
              }}
            >
              Admin User
            </div>
          </div>
        </header>

        {/* Content */}
        <div
          style={{
            flex: 1,
            overflowY: 'auto',
            padding: '2rem',
          }}
        >
          {children}
        </div>
      </main>
    </div>
  );
}
