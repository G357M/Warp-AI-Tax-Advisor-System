'use client';

import { motion } from 'framer-motion';
import { GearIcon, LockClosedIcon, BellIcon } from '@radix-ui/react-icons';

export default function SettingsPage() {
  return (
    <div>
      <div style={{ marginBottom: '2rem' }}>
        <h1 style={{ fontSize: '2rem', fontWeight: 'bold', margin: '0 0 0.5rem 0' }}>Settings</h1>
        <p style={{ fontSize: '1rem', opacity: 0.7, margin: 0 }}>Configure system settings</p>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
        {/* General Settings */}
        <motion.div
          whileHover={{ scale: 1.01 }}
          style={{
            background: 'linear-gradient(135deg, rgba(255,255,255,0.05) 0%, rgba(255,255,255,0.02) 100%)',
            border: '1px solid rgba(255,255,255,0.1)',
            borderRadius: '1rem',
            padding: '1.5rem',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', marginBottom: '1.5rem' }}>
            <GearIcon style={{ width: '24px', height: '24px', color: '#667eea' }} />
            <h2 style={{ fontSize: '1.25rem', fontWeight: 'bold', margin: 0 }}>General</h2>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
            <div>
              <label style={{ display: 'block', fontSize: '0.875rem', marginBottom: '0.5rem', opacity: 0.8 }}>
                Site Name
              </label>
              <input
                type="text"
                defaultValue="InfoHub AI Tax Advisor"
                style={{
                  width: '100%',
                  padding: '0.75rem 1rem',
                  background: 'rgba(255,255,255,0.05)',
                  border: '1px solid rgba(255,255,255,0.1)',
                  borderRadius: '0.5rem',
                  color: 'white',
                  fontSize: '0.875rem',
                }}
              />
            </div>
            <div>
              <label style={{ display: 'block', fontSize: '0.875rem', marginBottom: '0.5rem', opacity: 0.8 }}>
                API Base URL
              </label>
              <input
                type="text"
                defaultValue="http://localhost:8000/api/v1"
                style={{
                  width: '100%',
                  padding: '0.75rem 1rem',
                  background: 'rgba(255,255,255,0.05)',
                  border: '1px solid rgba(255,255,255,0.1)',
                  borderRadius: '0.5rem',
                  color: 'white',
                  fontSize: '0.875rem',
                }}
              />
            </div>
          </div>
        </motion.div>

        {/* Security Settings */}
        <motion.div
          whileHover={{ scale: 1.01 }}
          style={{
            background: 'linear-gradient(135deg, rgba(255,255,255,0.05) 0%, rgba(255,255,255,0.02) 100%)',
            border: '1px solid rgba(255,255,255,0.1)',
            borderRadius: '1rem',
            padding: '1.5rem',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', marginBottom: '1.5rem' }}>
            <LockClosedIcon style={{ width: '24px', height: '24px', color: '#f093fb' }} />
            <h2 style={{ fontSize: '1.25rem', fontWeight: 'bold', margin: 0 }}>Security</h2>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div>
                <div style={{ fontSize: '0.875rem', fontWeight: '600' }}>Guest Rate Limit</div>
                <div style={{ fontSize: '0.75rem', opacity: 0.6 }}>Queries per minute for unauthenticated users</div>
              </div>
              <input
                type="number"
                defaultValue="10"
                style={{
                  width: '80px',
                  padding: '0.5rem',
                  background: 'rgba(255,255,255,0.05)',
                  border: '1px solid rgba(255,255,255,0.1)',
                  borderRadius: '0.5rem',
                  color: 'white',
                  fontSize: '0.875rem',
                  textAlign: 'center',
                }}
              />
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div>
                <div style={{ fontSize: '0.875rem', fontWeight: '600' }}>User Rate Limit</div>
                <div style={{ fontSize: '0.75rem', opacity: 0.6 }}>Queries per minute for authenticated users</div>
              </div>
              <input
                type="number"
                defaultValue="60"
                style={{
                  width: '80px',
                  padding: '0.5rem',
                  background: 'rgba(255,255,255,0.05)',
                  border: '1px solid rgba(255,255,255,0.1)',
                  borderRadius: '0.5rem',
                  color: 'white',
                  fontSize: '0.875rem',
                  textAlign: 'center',
                }}
              />
            </div>
          </div>
        </motion.div>

        {/* Notifications */}
        <motion.div
          whileHover={{ scale: 1.01 }}
          style={{
            background: 'linear-gradient(135deg, rgba(255,255,255,0.05) 0%, rgba(255,255,255,0.02) 100%)',
            border: '1px solid rgba(255,255,255,0.1)',
            borderRadius: '1rem',
            padding: '1.5rem',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', marginBottom: '1.5rem' }}>
            <BellIcon style={{ width: '24px', height: '24px', color: '#4ade80' }} />
            <h2 style={{ fontSize: '1.25rem', fontWeight: 'bold', margin: 0 }}>Notifications</h2>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div>
                <div style={{ fontSize: '0.875rem', fontWeight: '600' }}>Email Alerts</div>
                <div style={{ fontSize: '0.75rem', opacity: '0.6' }}>Receive email notifications for system events</div>
              </div>
              <label style={{ position: 'relative', display: 'inline-block', width: '44px', height: '24px' }}>
                <input type="checkbox" defaultChecked style={{ opacity: 0, width: 0, height: 0 }} />
                <span
                  style={{
                    position: 'absolute',
                    cursor: 'pointer',
                    top: 0,
                    left: 0,
                    right: 0,
                    bottom: 0,
                    background: '#4ade80',
                    borderRadius: '24px',
                    transition: '0.4s',
                  }}
                />
              </label>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div>
                <div style={{ fontSize: '0.875rem', fontWeight: '600' }}>Slack Integration</div>
                <div style={{ fontSize: '0.75rem', opacity: '0.6' }}>Send notifications to Slack</div>
              </div>
              <label style={{ position: 'relative', display: 'inline-block', width: '44px', height: '24px' }}>
                <input type="checkbox" defaultChecked style={{ opacity: 0, width: 0, height: 0 }} />
                <span
                  style={{
                    position: 'absolute',
                    cursor: 'pointer',
                    top: 0,
                    left: 0,
                    right: 0,
                    bottom: 0,
                    background: '#4ade80',
                    borderRadius: '24px',
                    transition: '0.4s',
                  }}
                />
              </label>
            </div>
          </div>
        </motion.div>

        {/* Save Button */}
        <button
          style={{
            padding: '0.75rem 2rem',
            background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
            border: 'none',
            borderRadius: '0.5rem',
            color: 'white',
            cursor: 'pointer',
            fontSize: '1rem',
            fontWeight: '600',
            alignSelf: 'flex-start',
          }}
        >
          Save Settings
        </button>
      </div>
    </div>
  );
}
