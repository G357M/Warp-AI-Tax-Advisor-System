import { expect, Page, Route, test } from '@playwright/test';
import path from 'node:path';
import { mkdir } from 'node:fs/promises';
import type { ReconciliationDetail, ReconciliationItem } from '../lib/billing-reconciliation';
import type { ReviewPreview } from '../lib/billing-review';

const ROOT = '/api/v1/billing/admin/reconciliation';
const first: ReconciliationItem = {
  id: '10000000-0000-0000-0000-000000000001', user_id: '20000000-0000-0000-0000-000000000001',
  plan: 'pro', amount_minor: 4900, currency: 'GEL', provider: 'tbc',
  provider_order_id: `merchant-order-${'b'.repeat(96)}`, status: 'provider_review', provider_status: 'PartialReturned',
  reason: 'provider_review', settled_payment_id: '30000000-0000-0000-0000-000000000001',
  created_at: '2026-09-08T09:15:00', updated_at: '2026-09-08T10:30:00',
  expires_at: '2026-09-08T09:27:00', provider_checked_at: '2026-09-08T10:30:00',
};
const second: ReconciliationItem = {
  ...first, id: '10000000-0000-0000-0000-000000000002', plan: 'business', amount_minor: 14900,
  provider_order_id: `merchant-${'a'.repeat(110)}`, status: 'provider_unknown', provider_status: null,
  reason: 'provider_unknown', settled_payment_id: null, provider_checked_at: null,
};

function detail(item: ReconciliationItem): ReconciliationDetail {
  return {
    checkout: item,
    events: item.reason === 'provider_review' ? [{
      id: '40000000-0000-0000-0000-000000000001', provider_status: 'PartialReturned',
      payload_sha256: 'a'.repeat(64), processing_status: 'review', error_code: 'provider_state_requires_review',
      created_at: '2026-09-08T10:30:00', processed_at: '2026-09-08T10:30:01',
    }] : [],
    events_truncated: item.reason === 'provider_review',
  };
}

async function json(route: Route, data: unknown, status = 200) {
  await route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(data) });
}

async function setup(page: Page, lang = 'en', role = 'admin') {
  await page.addInitScript((language) => {
    localStorage.setItem('ta_lang', language);
    localStorage.setItem('ta_authenticated', '1');
    localStorage.removeItem('ta_token');
  }, lang);
  const writes: string[] = [];
  await page.route('**/api/v1/**', async (route) => {
    const request = route.request();
    if (request.method() !== 'GET') writes.push(`${request.method()} ${request.url()}`);
    const url = new URL(request.url());
    if (url.pathname === '/api/v1/auth/me') return json(route, { username: 'review.operator', role });
    if (url.pathname === ROOT) return json(route, { items: [first, second], next_offset: null });
    if (url.pathname === `${ROOT}/${first.id}`) return json(route, detail(first));
    if (url.pathname === `${ROOT}/${second.id}`) return json(route, detail(second));
    return json(route, { detail: 'No fixture for this API' }, 404);
  });
  return writes;
}

async function open(page: Page) {
  await page.goto('/admin/billing');
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
}

async function capture(page: Page, name: string) {
  if (!process.env.BILLING_REVIEW_DIR) return;
  const dir = path.resolve(process.env.BILLING_REVIEW_DIR);
  await mkdir(dir, { recursive: true });
  await page.evaluate(async () => { await document.fonts.ready; });
  await page.screenshot({ path: path.join(dir, name), fullPage: true });
}

const reviewPreview: ReviewPreview = {
  state_sha256: 'a'.repeat(64), provider_sha256: 'b'.repeat(64),
  provider_evidence: { status: 'Succeeded', amount_minor: 4900, currency: 'GEL', provider_order_id: first.provider_order_id! },
  before: { checkout: { months: '1' }, subscription: null },
  actions: { keep_review: 'unchanged', confirm_payment: 'grant_period' },
};

test('billing: decision retries preserve key and body after an uncertain response', async ({ page }) => {
  await setup(page, 'ru');
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.route(`**${ROOT}/${first.id}`, (route) => json(route, detail({ ...first, settled_payment_id: null, provider_status: 'WaitingConfirm' })));
  await page.route(`**${ROOT}/${first.id}/preview?*`, (route) => json(route, reviewPreview));
  const attempts: { key: string; body: string | null }[] = [];
  await page.route(`**${ROOT}/${first.id}/decisions`, async (route) => {
    attempts.push({ key: route.request().headers()['idempotency-key'], body: route.request().postData() });
    if (attempts.length === 1) return route.abort('failed');
    return json(route, { decision: { id: '50000000-0000-0000-0000-000000000001', action: 'confirm_payment', access_effect: 'grant_period' }, replayed: true });
  });
  await open(page);
  await page.getByRole('button', { name: `Заявка ${first.id}`, exact: true }).click();
  await page.getByRole('button', { name: 'Проверить банк для решения', exact: true }).click();
  await page.getByLabel('Решение', { exact: true }).selectOption('confirm_payment');
  await expect(page.getByText('Зачесть платёж один раз', { exact: false })).toBeVisible();
  const save = page.getByRole('button', { name: 'Записать решение', exact: true });
  await expect(save).toBeDisabled();
  await page.getByLabel('Обоснование и проверенные сведения', { exact: true }).fill('Сверены заказ, сумма и подтверждение банка.');
  await page.getByRole('checkbox').check();
  await capture(page, 'decision-desktop.png');
  await save.click();
  await expect(page.getByRole('main').getByRole('alert')).toContainText('Ответ не получен');
  await expect(page.getByLabel('Решение', { exact: true })).toBeDisabled();
  await page.getByRole('button', { name: 'Повторить то же решение', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Решение записано', exact: true })).toBeVisible();
  expect(attempts).toHaveLength(2);
  expect(attempts[1]).toEqual(attempts[0]);
  expect(attempts[0].key).toMatch(/^[a-f0-9-]{36}$/);
});

test('billing: stale decisions require new evidence and reset confirmation', async ({ page }) => {
  await setup(page);
  await page.route(`**${ROOT}/${first.id}/preview?*`, (route) => json(route, reviewPreview));
  await page.route(`**${ROOT}/${first.id}/decisions`, (route) => json(route, {}, 409));
  await open(page);
  await page.getByRole('button', { name: `Order ${first.id}`, exact: true }).click();
  await page.getByRole('button', { name: 'Check bank for a decision', exact: true }).click();
  await page.getByLabel('Reason and evidence checked', { exact: true }).fill('Reviewed the synthetic evidence.');
  await page.getByRole('checkbox').check();
  await page.getByRole('button', { name: 'Record decision', exact: true }).click();
  await expect(page.getByRole('main').getByRole('alert')).toContainText('The evidence changed');
  await expect(page.getByRole('combobox')).toHaveCount(0);
  await page.getByRole('button', { name: 'Prepare review note', exact: true }).click();
  await expect(page.getByRole('checkbox')).not.toBeChecked();
  await expect(page.getByRole('button', { name: 'Record decision', exact: true })).toBeDisabled();
});

test('billing: Georgian mobile review note and journal are usable without bank', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await setup(page, 'ka');
  await page.route(`**${ROOT}/${first.id}/preview?*`, (route) => {
    expect(new URL(route.request().url()).searchParams.get('verify_provider')).toBe('false');
    return json(route, { ...reviewPreview, provider_evidence: null, provider_sha256: null, actions: { keep_review: 'unchanged' } });
  });
  await page.route(`**${ROOT}/${first.id}/decisions?*`, (route) => json(route, { items: [{
    id: '50000000-0000-0000-0000-000000000001', actor_id: first.user_id, action: 'keep_review',
    reason: 'ბანკის მონაცემები დამატებით შემოწმებას საჭიროებს.', access_effect: 'unchanged', created_at: first.updated_at,
  }], next_offset: null }));
  await open(page);
  await page.getByRole('button', { name: `განაცხადი ${first.id}`, exact: true }).click();
  await page.getByRole('button', { name: 'შემოწმების ჩანაწერის მომზადება', exact: true }).click();
  await expect(page.getByRole('combobox').locator('option')).toHaveCount(1);
  await page.getByLabel('დასაბუთება და შემოწმებული ინფორმაცია', { exact: true }).fill('ბანკის მონაცემები დამატებით შემოწმებას საჭიროებს.');
  await page.getByRole('button', { name: 'ჟურნალის ჩატვირთვა', exact: true }).click();
  await page.getByRole('list', { name: 'გადაწყვეტილებების ჟურნალი', exact: true }).locator('summary').click();
  await expect(page.getByText('ოპერატორის ID', { exact: true })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBe(0);
  await capture(page, 'decision-mobile.png');
});

test('billing: revoked access during preview hides all retained evidence', async ({ page }) => {
  await setup(page);
  await page.route(`**${ROOT}/${first.id}/preview?*`, (route) => json(route, {}, 403));
  await open(page);
  await page.getByRole('button', { name: `Order ${first.id}`, exact: true }).click();
  await page.getByRole('button', { name: 'Prepare review note', exact: true }).click();
  await expect(page.getByRole('main').getByRole('alert')).toContainText('Administrator access is required');
  await expect(page.getByText(first.id, { exact: true })).toHaveCount(0);
  await expect(page.getByRole('heading', { name: 'Orders to review', exact: true })).toHaveCount(0);
});

test('billing: saving a decision resets the journal page boundary', async ({ page }) => {
  await setup(page);
  const rows = Array.from({ length: 26 }, (_, index) => ({
    id: `50000000-0000-0000-0000-${String(index).padStart(12, '0')}`,
    actor_id: first.user_id, action: 'keep_review', reason: `Recorded synthetic evidence ${index}.`,
    access_effect: 'unchanged', created_at: first.updated_at,
  }));
  const offsets: number[] = [];
  await page.route(`**${ROOT}/${first.id}/decisions?*`, (route) => {
    const offset = Number(new URL(route.request().url()).searchParams.get('offset'));
    offsets.push(offset);
    return json(route, { items: rows.slice(offset, offset + 25), next_offset: offset + 25 < rows.length ? offset + 25 : null });
  });
  await page.route(`**${ROOT}/${first.id}/preview?*`, (route) => json(route, { ...reviewPreview, actions: { keep_review: 'unchanged' } }));
  await page.route(`**${ROOT}/${first.id}/decisions`, (route) => {
    const decision = { ...rows[0], id: '50000000-0000-0000-0000-999999999999' };
    rows.unshift(decision);
    return json(route, { decision, replayed: false });
  });
  await open(page);
  await page.getByRole('button', { name: `Order ${first.id}`, exact: true }).click();
  await page.getByRole('button', { name: 'Load journal', exact: true }).click();
  const journal = page.getByRole('list', { name: 'Decision journal', exact: true });
  await expect(journal.locator(':scope > li')).toHaveCount(25);
  await page.getByRole('button', { name: 'Prepare review note', exact: true }).click();
  await page.getByLabel('Reason and evidence checked', { exact: true }).fill('Confirmed the synthetic evidence.');
  await page.getByRole('checkbox').check();
  await page.getByRole('button', { name: 'Record decision', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Decision recorded', exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Older decisions', exact: true })).toHaveCount(0);
  await page.getByRole('button', { name: 'Load journal', exact: true }).click();
  await page.getByRole('button', { name: 'Older decisions', exact: true }).click();
  await expect(journal.locator(':scope > li')).toHaveCount(27);
  expect(offsets).toEqual([0, 0, 25]);
  const ids = await journal.locator('dd').allTextContents();
  expect(new Set(ids.filter((id) => id.startsWith('50000000'))).size).toBe(27);
});

test('billing: Russian desktop evidence is read-only and uses UTC', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  const writes = await setup(page, 'ru');
  await open(page);
  await page.getByRole('button', { name: `Заявка ${first.id}`, exact: true }).click();
  await expect(page.getByText('Зачисление зарегистрировано', { exact: true })).toBeVisible();
  await expect(page.getByText('Показаны последние 50 событий.', { exact: false })).toBeVisible();
  await page.locator('summary').click();
  await expect(page.getByText('a'.repeat(64), { exact: true })).toBeVisible();
  await expect(page.locator('#billing-detail')).toContainText('10:30');
  await capture(page, 'desktop.png');
  expect(writes).toEqual([]);
  await expect(page.getByRole('button', { name: /refund|возврат|activate|активировать/i })).toHaveCount(0);
});

test('billing: Georgian mobile navigation and long order evidence fit the screen', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await setup(page, 'ka');
  await open(page);
  const menu = page.getByRole('button', { name: 'ადმინისტრატორის მენიუ', exact: true });
  await expect(menu).toHaveAttribute('aria-expanded', 'false');
  await menu.click();
  await expect(menu).toHaveAttribute('aria-expanded', 'true');
  await page.getByRole('link', { name: 'გადახდების შეჯერება', exact: true }).click();
  await expect(menu).toHaveAttribute('aria-expanded', 'false');
  await page.getByRole('button', { name: `განაცხადი ${first.id}`, exact: true }).click();
  await expect(page.getByText(first.provider_order_id!, { exact: true })).toBeVisible();
  await page.locator('summary').click();
  await expect(page.getByText('a'.repeat(64), { exact: true })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBe(0);
  await capture(page, 'mobile.png');
});

test('billing: queue failure is not shown as empty and can be retried', async ({ page }) => {
  await setup(page);
  let attempts = 0;
  await page.route(`**${ROOT}?*`, (route) => {
    attempts += 1;
    return attempts === 1 ? json(route, {}, 503) : json(route, { items: [], next_offset: null });
  });
  await open(page);
  await expect(page.getByRole('main').getByRole('alert')).toContainText('Could not load');
  await expect(page.getByText('No orders to review', { exact: true })).toHaveCount(0);
  await page.getByRole('button', { name: 'Try again', exact: true }).click();
  await expect(page.getByText('No orders to review', { exact: true })).toBeVisible();
});

test('billing: ordinary accounts cannot load operator evidence', async ({ page }) => {
  await setup(page, 'en', 'user');
  const calls: string[] = [];
  page.on('request', (request) => { if (request.url().includes(ROOT)) calls.push(request.url()); });
  await page.goto('/admin/billing');
  await expect(page).toHaveURL(/\/login$/);
  expect(calls).toEqual([]);
});

test('billing: expired sessions show sign-in instead of an empty worklist', async ({ page }) => {
  await setup(page);
  await page.route(`**${ROOT}?*`, (route) => json(route, {}, 401));
  await open(page);
  await expect(page.getByRole('main').getByRole('alert')).toContainText('Your session has expired');
  await expect(page.getByRole('main').getByRole('alert').getByRole('link', { name: 'Sign in' })).toHaveAttribute('href', '/login');
});

test('billing: pagination and refresh clear selected evidence', async ({ page }) => {
  await setup(page);
  const rows = Array.from({ length: 25 }, (_, index) => ({ ...first, id: `${first.id.slice(0, -2)}${String(index + 1).padStart(2, '0')}` }));
  await page.route(`**${ROOT}?*`, (route) => {
    const offset = new URL(route.request().url()).searchParams.get('offset');
    return json(route, offset === '0' ? { items: rows, next_offset: 25 } : { items: [second], next_offset: null });
  });
  await open(page);
  await page.getByRole('button', { name: `Order ${first.id}`, exact: true }).click();
  await expect(page.getByText('Credit is recorded', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Next', exact: true }).click();
  await expect(page.getByText('Page 2', { exact: true })).toBeVisible();
  await expect(page.getByText('Credit is recorded', { exact: true })).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Next', exact: true })).toBeDisabled();
  await page.getByRole('button', { name: 'Refresh queue', exact: true }).click();
  await expect(page.getByText('Page 1', { exact: true })).toBeVisible();
});

test('billing: a late detail response cannot replace the selected order', async ({ page }) => {
  await setup(page);
  let release: () => void = () => {};
  let markStarted: () => void = () => {};
  let markDone: () => void = () => {};
  const held = new Promise<void>((resolve) => { release = resolve; });
  const started = new Promise<void>((resolve) => { markStarted = resolve; });
  const done = new Promise<void>((resolve) => { markDone = resolve; });
  await page.route(`**${ROOT}/${first.id}`, async (route) => {
    markStarted();
    await held;
    try { await json(route, detail(first)); } finally { markDone(); }
  });
  await open(page);
  await page.getByRole('button', { name: `Order ${first.id}`, exact: true }).click();
  await started;
  await page.getByRole('button', { name: `Order ${second.id}`, exact: true }).click();
  await expect(page.getByText(second.provider_order_id!, { exact: true })).toBeVisible();
  release();
  await done;
  await expect(page.locator('#billing-detail')).toContainText(second.id);
  await expect(page.getByText('Credit is recorded', { exact: true })).toHaveCount(0);
});

test('billing: detail errors are retryable without stale payment evidence', async ({ page }) => {
  await setup(page);
  let attempts = 0;
  await page.route(`**${ROOT}/${first.id}`, (route) => {
    attempts += 1;
    return attempts === 1 ? json(route, {}, 503) : json(route, detail(first));
  });
  await open(page);
  const button = page.getByRole('button', { name: `Order ${first.id}`, exact: true });
  await button.focus();
  await page.keyboard.press('Enter');
  await expect(page.locator('#billing-detail')).toBeFocused();
  await expect(page.getByRole('main').getByRole('alert')).toBeVisible();
  await expect(page.getByText('Credit is recorded', { exact: true })).toHaveCount(0);
  await page.getByRole('button', { name: 'Try again', exact: true }).click();
  await expect(page.getByText('Credit is recorded', { exact: true })).toBeVisible();
});

test('billing: loss of permission hides previously loaded queue evidence', async ({ page }) => {
  await setup(page);
  await page.route(`**${ROOT}/${first.id}`, (route) => json(route, {}, 403));
  await open(page);
  await page.getByRole('button', { name: `Order ${first.id}`, exact: true }).click();
  await expect(page.getByRole('main').getByRole('alert')).toContainText('Administrator access is required');
  await expect(page.getByRole('button', { name: `Order ${second.id}`, exact: true })).toHaveCount(0);
  await expect(page.getByText(second.id, { exact: true })).toHaveCount(0);
});
