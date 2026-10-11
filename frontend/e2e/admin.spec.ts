import { expect, Page, Route, test } from '@playwright/test';

const longEmail = `very.long.customer.address.${'x'.repeat(30)}@example-company-domain.ge`;
const stats = {
  documents: { total: 48211, by_type: { law: 1204, court_decision: 11249, guideline: 631 }, last_ingest: '2026-10-11T02:10:00' },
  decisions: { total: 11249, extracted: 11000, pending: 249 },
  amendments: { acts_total: 926, extracted: 926, resolved: 627, pending: 0 },
  users: { total: 42, admins: 1 },
  subscriptions: { pro: 3 },
  conversations: { total: 310, messages: 2400, messages_7d: 120 },
  feedback: { new: 2 },
  billing: { reconciliation_open: 1, manual_pending: 1 },
  attention: { ingest_stale: false },
};
const auditItems = [{
  id: 'a1', actor: { id: 'u0', username: 'admin' }, action: 'user.role_changed', target_type: 'user',
  target_id: '20000000-0000-0000-0000-000000000001', before: { role: 'user' }, after: { role: 'admin' },
  reason: 'promote accountant', created_at: '2026-10-11T09:00:00',
}];
const users = [{
  id: '20000000-0000-0000-0000-000000000001', username: 'customer', email: longEmail, role: 'user',
  created_at: '2026-10-01T10:00:00', last_login: '2026-10-10T18:00:00', plan: 'pro', period_end: '2026-11-01T00:00:00',
  is_active: true, email_verified: true,
}];
const config = {
  app: { APP_VERSION: '0.1.0', ENVIRONMENT: 'production', DEBUG: false },
  llm: { LLM_PROVIDER: 'openai', LLM_MODEL: 'gpt-4o-mini', EMBEDDING_MODEL: 'paraphrase-multilingual-mpnet-base-v2', RAG_TOP_K: 10, RAG_MIN_SIMILARITY: 0.5, JEV_MODE: 'off' },
  email: { EMAIL_DELIVERY_ENABLED: true, SMTP_HOST: 'smtp.resend.com', SMTP_PORT: 587, SMTP_FROM: 'Tax Advisor <info@tax-advisor.ge>' },
  billing: { BILLING_TBC_ENABLED: false, BILLING_CONTACT_EMAIL: 'info@tax-advisor.ge', FREE_DAILY_QUESTIONS: 5 },
  limits: { RATE_LIMIT_ENABLED: true },
  secrets: { OPENAI_API_KEY: true, ANTHROPIC_API_KEY: false, SMTP_PASSWORD: true, TBC_API_KEY: false, TBC_CLIENT_ID: false, TBC_CLIENT_SECRET: false, TYPESAFE_API_KEY: false },
};
const feedback = { total: 1, counts: { new: 1, in_progress: 0, fixed: 0 }, items: [{
  id: 'f1', message: 'Ссылка на статью 168 не открывается', page: '/laws', status: 'new',
  created_at: '2026-10-10T12:00:00', email: longEmail, username: 'customer',
}] };
const ops = { last_ingest: '2026-10-11T02:10:00', documents_today: 14, pending: { decision_facts: 249, law_amendments: 0 },
  logs: { scraper: ['2026-10-11 02:10 done: +14 new'], law_amendments_backfill: [], decision_facts_backfill: [] } };
const row = { total: 100, satisfied: 1, partially_satisfied: 27, rejected: 72, unclear: 0, taxpayer_relief_rate: 0.28 };
const analytics = { coverage: { decisions_in_corpus: 11249, decisions_extracted: 11000 }, overall: row,
  by_year: [{ ...row, year: 2025 }], by_body: [{ ...row, body: 'revenue_service_council' }], by_dispute_type: [],
  top_articles: [{ ...row, article: '168' }] };

async function json(route: Route, data: unknown, status = 200) {
  await route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(data) });
}

async function setup(page: Page, lang: 'ru' | 'ka' | 'en' = 'ru') {
  await page.addInitScript((language) => {
    localStorage.setItem('ta_lang', language);
    localStorage.setItem('ta_authenticated', '1');
  }, lang);
  const writes: { method: string; path: string; body: unknown }[] = [];
  await page.route('**/api/v1/**', async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    if (request.method() !== 'GET') {
      writes.push({ method: request.method(), path: url.pathname, body: request.postDataJSON() });
      return json(route, { id: users[0].id, username: 'customer', role: 'admin', status: 'fixed' });
    }
    const fixtures: Record<string, unknown> = {
      '/api/v1/auth/me': { username: 'admin', role: 'admin' },
      '/api/v1/admin/stats': stats,
      '/api/v1/admin/audit': { total: 1, items: auditItems },
      '/api/v1/admin/config': config,
      '/api/v1/admin/users': { total: 1, items: users },
      '/api/v1/admin/feedback': feedback,
      '/api/v1/admin/documents': { total: 0, items: [] },
      '/api/v1/admin/ops': ops,
      '/api/v1/analytics/decisions': analytics,
      '/api/v1/billing/admin/reconciliation': { items: [], next_offset: null },
    };
    return url.pathname in fixtures ? json(route, fixtures[url.pathname]) : json(route, { detail: 'No fixture' }, 404);
  });
  return writes;
}

const LOADING = /Загружаем|იტვირთება|Loading/;

// `ready` proves fixture data (not a loading or error frame) is on screen before we measure.
type Ready = (page: Page) => Promise<void>;
const text = (value: string, exact = false): Ready => (page) =>
  expect(page.getByText(value, { exact }).first()).toBeVisible();
const loaded: Ready = async (page) => {
  const status = page.getByRole('status').first();
  await expect(status).toBeVisible();
  await expect(status).not.toHaveText(LOADING);
};
const PAGES: { path: string; ready: Ready }[] = [
  { path: '/admin', ready: text('guideline') },
  { path: '/admin/users', ready: text(longEmail) },
  { path: '/admin/billing', ready: loaded },
  { path: '/admin/feedback', ready: text(longEmail) },
  { path: '/admin/documents', ready: loaded },
  { path: '/admin/analytics', ready: text('168', true) },
  { path: '/admin/scraper', ready: text('2026-10-11 02:10 done: +14 new') },
  { path: '/admin/audit', ready: text(users[0].id) },
  { path: '/admin/settings', ready: text('gpt-4o-mini') },
];

for (const lang of ['ru', 'ka'] as const) {
  for (const viewport of [{ width: 1280, height: 900 }, { width: 390, height: 844 }]) {
    test(`every admin page renders without horizontal scroll (${lang}, ${viewport.width}px)`, async ({ page }) => {
      await page.setViewportSize(viewport);
      await setup(page, lang);
      for (const { path, ready } of PAGES) {
        await page.goto(path);
        await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
        await ready(page);
        await expect(page.getByRole('main').getByRole('alert')).toHaveCount(0);
        const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
        expect(overflow, `${path} overflows by ${overflow}px`).toBeLessThanOrEqual(0);
      }
    });
  }
}

test('dashboard lists what needs attention', async ({ page }) => {
  await setup(page, 'en');
  await page.goto('/admin');
  const attention = page.getByRole('region', { name: 'Needs attention' });
  await expect(attention.getByRole('link', { name: 'New feedback: 2' })).toHaveAttribute('href', '/admin/feedback');
  await expect(attention.getByRole('link', { name: 'Payments to reconcile: 1' })).toHaveAttribute('href', '/admin/billing');
  await expect(attention.getByRole('link', { name: 'Orders awaiting activation: 1' })).toBeVisible();
  await expect(page.getByText('role: user → admin')).toBeVisible();
});

test('cancelling a feedback status change sends nothing', async ({ page }) => {
  const writes = await setup(page, 'en');
  await page.goto('/admin/feedback');
  await page.getByRole('combobox', { name: 'Status' }).selectOption('fixed');
  await page.getByRole('dialog').getByRole('button', { name: 'Cancel' }).first().click();
  await expect(page.getByRole('dialog')).toBeHidden();
  await expect(page.getByRole('combobox', { name: 'Status' })).toHaveValue('new');
  expect(writes).toEqual([]);
});

test('config shows secrets only as set / not set', async ({ page }) => {
  await setup(page, 'en');
  await page.goto('/admin/settings');
  await expect(page.getByRole('heading', { name: 'Secrets' })).toBeVisible();
  const secretsTable = page.getByRole('table').last();
  await expect(secretsTable.getByText('set', { exact: true }).first()).toBeVisible();
  await expect(secretsTable.getByText('not set', { exact: true }).first()).toBeVisible();
});

test('Georgian dates render as dd.mm.yyyy, not US style', async ({ page }) => {
  await setup(page, 'ka');
  await page.goto('/admin/users');
  await expect(page.getByText(longEmail).first()).toBeVisible();
  await expect(page.getByText('01.11.2026').first()).toBeVisible();
  await expect(page.getByText(/10\.10\.2026, 18:00/).first()).toBeVisible();
});

test('admin visual baseline', async ({ page }) => {
  await setup(page, 'ru');
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.goto('/admin');
  await expect(page.getByText('role: user → admin')).toBeVisible();
  await page.evaluate(async () => { await document.fonts.ready; });
  await expect(page).toHaveScreenshot('admin-dashboard-ru-desktop.png', { fullPage: true });

  const mobile = await page.context().newPage();
  await setup(mobile, 'ka');
  await mobile.setViewportSize({ width: 390, height: 844 });
  await mobile.goto('/admin/users');
  await expect(mobile.getByRole('heading', { level: 1 })).toBeVisible();
  await expect(mobile.getByText(longEmail).first()).toBeVisible();
  await mobile.evaluate(async () => { await document.fonts.ready; });
  await expect(mobile).toHaveScreenshot('admin-users-ka-mobile.png', { fullPage: true });
});
