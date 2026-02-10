'use client';

import { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import {
  RocketIcon,
  PersonIcon,
  FileTextIcon,
  ClockIcon,
  CheckCircledIcon,
  CrossCircledIcon,
} from '@radix-ui/react-icons';

interface Stats {
  total_queries: number;
  total_users: number;
  total_documents: number;
  avg_response_time: number;
  success_rate: number;
  uptime: string;
}

interface RecentActivity {
  id: string;
  type: 'query' | 'user' | 'document' | 'scrape';
  message: string;
  timestamp: string;
  status: 'success' | 'error' | 'pending';
}

const StatCard = ({ title, value, icon: Icon, color, trend }: any) => (
  <motion.div
    whileHover={{ y: -4, scale: 1.02 }}
    style={{
      background: 'linear-gradient(135deg, rgba(255,255,255,0.05) 0%, rgba(255,255,255,0.02) 100%)',
      border: '1px solid rgba(255,255,255,0.1)',
      borderRadius: '1rem',
      padding: '1.5rem',
      position: 'relative',
      overflow: 'hidden',
    }}
  >
    <div
      style={{
        position: 'absolute',
        top: 0,
        right: 0,
        width: '100px',
        height: '100px',
        background: `radial-gradient(circle, ${color}20 0%, transparent 70%)`,
        filter: 'blur(20px)',
      }}
    />
    <div style={{ position: 'relative', zIndex: 1 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'start', marginBottom: '1rem' }}>
        <div
          style={{
            background: `${color}20`,
            padding: '0.75rem',
            borderRadius: '0.75rem',
          }}
        >
          <Icon style={{ width: '24px', height: '24px', color }} />
        </div>
        {trend && (
          <span style={{ fontSize: '0.875rem', color: trend > 0 ? '#4ade80' : '#f87171' }}>
            {trend > 0 ? '↑' : '↓'} {Math.abs(trend)}%
          </span>
        )}
      </div>
      <h3 style={{ fontSize: '2rem', fontWeight: 'bold', margin: '0 0 0.5rem 0' }}>{value}</h3>
      <p style={{ fontSize: '0.875rem', opacity: 0.7, margin: 0 }}>{title}</p>
    </div>
  </motion.div>
);

export default function AdminDashboard() {
  const [stats, setStats] = useState<Stats>({
    total_queries: 0,
    total_users: 0,
    total_documents: 0,
    avg_response_time: 0,
    success_rate: 0,
    uptime: '0h',
  });

  const [recentActivity, setRecentActivity] = useState<RecentActivity[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // Simulate fetching stats (replace with actual API call)
    const fetchStats = async () => {
      // Mock data - replace with actual API call to backend
      setTimeout(() => {
        setStats({
          total_queries: 1247,
          total_users: 89,
          total_documents: 156,
          avg_response_time: 2.3,
          success_rate: 98.5,
          uptime: '7d 12h',
        });

        setRecentActivity([
          {
            id: '1',
            type: 'query',
            message: 'New query: "What is VAT rate?"',
            timestamp: '2 min ago',
            status: 'success',
          },
          {
            id: '2',
            type: 'user',
            message: 'New user registered: user@example.com',
            timestamp: '15 min ago',
            status: 'success',
          },
          {
            id: '3',
            type: 'scrape',
            message: 'Scraper task completed: 45 documents',
            timestamp: '1 hour ago',
            status: 'success',
          },
          {
            id: '4',
            type: 'document',
            message: 'Document indexed: Tax Code 2024',
            timestamp: '2 hours ago',
            status: 'success',
          },
          {
            id: '5',
            type: 'query',
            message: 'Query failed: Rate limit exceeded',
            timestamp: '3 hours ago',
            status: 'error',
          },
        ]);

        setLoading(false);
      }, 500);
    };

    fetchStats();
  }, []);

  if (loading) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100%' }}>
        <motion.div
          animate={{ rotate: 360 }}
          transition={{ duration: 1, repeat: Infinity, ease: 'linear' }}
          style={{
            width: '48px',
            height: '48px',
            border: '4px solid rgba(255,255,255,0.1)',
            borderTop: '4px solid #667eea',
            borderRadius: '50%',
          }}
        />
      </div>
    );
  }

  return (
    <div>
      {/* Header */}
      <div style={{ marginBottom: '2rem' }}>
        <h1 style={{ fontSize: '2rem', fontWeight: 'bold', margin: '0 0 0.5rem 0' }}>Dashboard</h1>
        <p style={{ fontSize: '1rem', opacity: 0.7, margin: 0 }}>Welcome back! Here's what's happening.</p>
      </div>

      {/* Stats Grid */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
          gap: '1.5rem',
          marginBottom: '2rem',
        }}
      >
        <StatCard
          title="Total Queries"
          value={stats.total_queries.toLocaleString()}
          icon={RocketIcon}
          color="#667eea"
          trend={12}
        />
        <StatCard
          title="Total Users"
          value={stats.total_users.toLocaleString()}
          icon={PersonIcon}
          color="#f093fb"
          trend={8}
        />
        <StatCard
          title="Documents"
          value={stats.total_documents.toLocaleString()}
          icon={FileTextIcon}
          color="#4ade80"
          trend={5}
        />
        <StatCard
          title="Avg Response"
          value={`${stats.avg_response_time}s`}
          icon={ClockIcon}
          color="#fbbf24"
          trend={-3}
        />
      </div>

      {/* Secondary Stats */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(250px, 1fr))', gap: '1.5rem', marginBottom: '2rem' }}>
        <motion.div
          whileHover={{ scale: 1.02 }}
          style={{
            background: 'linear-gradient(135deg, rgba(74,222,128,0.1) 0%, rgba(74,222,128,0.05) 100%)',
            border: '1px solid rgba(74,222,128,0.2)',
            borderRadius: '1rem',
            padding: '1.5rem',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
            <CheckCircledIcon style={{ width: '32px', height: '32px', color: '#4ade80' }} />
            <div>
              <h3 style={{ fontSize: '1.5rem', fontWeight: 'bold', margin: 0, color: '#4ade80' }}>
                {stats.success_rate}%
              </h3>
              <p style={{ fontSize: '0.875rem', opacity: 0.7, margin: 0 }}>Success Rate</p>
            </div>
          </div>
        </motion.div>

        <motion.div
          whileHover={{ scale: 1.02 }}
          style={{
            background: 'linear-gradient(135deg, rgba(102,126,234,0.1) 0%, rgba(102,126,234,0.05) 100%)',
            border: '1px solid rgba(102,126,234,0.2)',
            borderRadius: '1rem',
            padding: '1.5rem',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
            <ClockIcon style={{ width: '32px', height: '32px', color: '#667eea' }} />
            <div>
              <h3 style={{ fontSize: '1.5rem', fontWeight: 'bold', margin: 0, color: '#667eea' }}>
                {stats.uptime}
              </h3>
              <p style={{ fontSize: '0.875rem', opacity: 0.7, margin: 0 }}>System Uptime</p>
            </div>
          </div>
        </motion.div>
      </div>

      {/* Recent Activity */}
      <div
        style={{
          background: 'linear-gradient(135deg, rgba(255,255,255,0.05) 0%, rgba(255,255,255,0.02) 100%)',
          border: '1px solid rgba(255,255,255,0.1)',
          borderRadius: '1rem',
          padding: '1.5rem',
        }}
      >
        <h2 style={{ fontSize: '1.25rem', fontWeight: 'bold', margin: '0 0 1.5rem 0' }}>Recent Activity</h2>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          {recentActivity.map((activity) => (
            <motion.div
              key={activity.id}
              whileHover={{ x: 4 }}
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                padding: '1rem',
                background: 'rgba(255,255,255,0.02)',
                borderRadius: '0.75rem',
                border: '1px solid rgba(255,255,255,0.05)',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
                {activity.status === 'success' ? (
                  <CheckCircledIcon style={{ width: '20px', height: '20px', color: '#4ade80' }} />
                ) : (
                  <CrossCircledIcon style={{ width: '20px', height: '20px', color: '#f87171' }} />
                )}
                <div>
                  <p style={{ margin: 0, fontSize: '0.875rem' }}>{activity.message}</p>
                  <p style={{ margin: '0.25rem 0 0 0', fontSize: '0.75rem', opacity: 0.5 }}>{activity.timestamp}</p>
                </div>
              </div>
              <span
                style={{
                  padding: '0.25rem 0.75rem',
                  borderRadius: '1rem',
                  fontSize: '0.75rem',
                  background:
                    activity.status === 'success'
                      ? 'rgba(74,222,128,0.1)'
                      : activity.status === 'error'
                      ? 'rgba(248,113,113,0.1)'
                      : 'rgba(251,191,36,0.1)',
                  color:
                    activity.status === 'success'
                      ? '#4ade80'
                      : activity.status === 'error'
                      ? '#f87171'
                      : '#fbbf24',
                }}
              >
                {activity.status}
              </span>
            </motion.div>
          ))}
        </div>
      </div>
    </div>
  );
}
