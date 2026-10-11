import { expect, Page, Route, test } from '@playwright/test';

const ID = '20000000-0000-0000-0000-000000000001';
const ADMIN_ID = '20000000-0000-0000-0000-000000000009';
const longEmail = `very.long.customer.address.${'x'.repeat(30)}@example-company-domain.ge`;
const row = {
  id: ID, username: 'customer', email: longEmail, role: 'user', created_at: '2026-10-01T10:00:00',
  last_login: '2026-10-10T18:00:00', plan: 'pro', period_end: '2026-11-01T00:00:00', is_active: true, email_verified: true,
};
const card = {
  profile: {
    id: ID, username: 'customer', email: longEmail, full_name: 'Nino Beridze', role: 'user', effective_plan: 'pro',
    is_active: true, email_verified: true, created_at: '2026-10-01T10:00:00', last_login: '2026-10-10T18:00:00',
  },
  subscription: {
    plan: 'pro', status: 'active', period_start: '2026-10-01T00:00:00', period_end: '2026-11-01T00:00:00',
    days_left: 12, source: 'payment',
  },
  payments: [{ id: 'p1', created_at: '2026-10-01T10:05:00', amount_minor: 4900, currency: 'GEL', provider: 'manual', status: 'succeeded' }],
  checkouts: [{
    id: 'c1', created_at: '2026-10-11T08:00:00', plan: 'pro', months: 1, amount_minor: 4900, currency: 'GEL',
    provider: 'manual', status: 'pending', expires_at: '2099-01-01T00:00:00',
  }],
  activity: {
    conversations_7d: 2, conversations_30d: 5, questions_7d: 9, questions_30d: 31,
    questions_today: null, daily_limit: null, feedback_total: 1,
  },
};
const adminCard = {
  ...card, subscription: null, payments: [], checkouts: [],
  profile: { ...card.profile, id: ADMIN_ID, username: 'admin', role: 'admin', effective_plan: 'business' },
};
const catalog = { plans: [{ id: 'pro', price_minor: 4900, currency: 'GEL' }, { id: 'business', price_minor: 14900, currency: 'GEL' }] };
const SEARCH = 'Поиск по email, логину или имени';

type Write = { method: string; path: string; body: unknown };
type Options = {
  lang?: 'ru' | 'ka' | 'en';
  card?: unknown;
  list?: (url: URL) => unknown;
  failWrite?: unknown;
};

async function json(route: Route, data: unknown, status = 200) {
  await route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(data) });
}

async function setup(page: Page, options: Options = {}) {
  const current = options.card ?? card;
  await page.addInitScript((language) => {
    localStorage.setItem('ta_lang', language);
    localStorage.setItem('ta_authenticated', '1');
  }, options.lang ?? 'ru');
  const writes: Write[] = [];
  const listQueries: string[] = [];
  await page.route('**/api/v1/**', async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    if (request.method() !== 'GET') {
      writes.push({ method: request.method(), path: url.pathname, body: request.postDataJSON() });
      return options.failWrite
        ? json(route, options.failWrite, 409)
        : json(route, { ...(current as object), changed: true });
    }
    if (url.pathname === '/api/v1/admin/users') {
      listQueries.push(url.search);
      return json(route, options.list ? await options.list(url) : { total: 1, items: [row] });
    }
    const fixtures: Record<string, unknown> = {
      '/api/v1/auth/me': { username: 'admin', role: 'admin' },
      [`/api/v1/admin/users/${ID}`]: current,
      [`/api/v1/admin/users/${ADMIN_ID}`]: adminCard,
      '/api/v1/billing/catalog': catalog,
    };
    return url.pathname in fixtures ? json(route, fixtures[url.pathname]) : json(route, { detail: 'No fixture' }, 404);
  });
  return { writes, listQueries };
}

async function openCardDialog(page: Page, button: string) {
  await page.goto(`/admin/users/${ID}`);
  await page.getByRole('button', { name: button, exact: true }).click();
  const dialog = page.getByRole('dialog');
  return {
    dialog,
    reason: dialog.getByRole('textbox', { name: /Причина/ }),
    confirm: dialog.getByRole('button', { name: 'Подтвердить' }),
  };
}

test('search and filters live in the URL and survive reload', async ({ page }) => {
  const { listQueries } = await setup(page);
  await page.goto('/admin/users');
  await page.getByRole('searchbox', { name: SEARCH }).fill('cust');
  await expect(page).toHaveURL(/\?q=cust$/);
  await page.getByRole('combobox', { name: 'Тариф' }).selectOption('pro');
  await expect(page).toHaveURL(/\?q=cust&plan=pro$/);
  await page.reload();
  await expect(page.getByRole('searchbox', { name: SEARCH })).toHaveValue('cust');
  await expect(page.getByRole('combobox', { name: 'Тариф' })).toHaveValue('pro');
  await expect.poll(() => listQueries.at(-1)).toContain('q=cust');
  expect(listQueries.at(-1)).toContain('plan=pro');
});

test('opening a card and going back keeps the filters', async ({ page }) => {
  await setup(page);
  await page.goto('/admin/users?plan=pro&q=cust');
  await page.getByRole('link', { name: 'customer' }).click();
  await expect(page).toHaveURL(`/admin/users/${ID}?back=${encodeURIComponent('?plan=pro&q=cust')}`);
  await page.getByRole('link', { name: '← К списку' }).click();
  await expect(page).toHaveURL('/admin/users?plan=pro&q=cust');
});

test('a slow stale search response never overwrites the newer result', async ({ page }) => {
  await setup(page, {
    list: async (url) => {
      const q = url.searchParams.get('q');
      if (q === 'a') {
        await new Promise((resolve) => setTimeout(resolve, 1500));
        return { total: 1, items: [{ ...row, id: 'a', username: 'slow-a' }] };
      }
      if (q === 'ab') return { total: 1, items: [{ ...row, id: 'b', username: 'fast-b' }] };
      return { total: 1, items: [row] };
    },
  });
  await page.goto('/admin/users');
  const box = page.getByRole('searchbox', { name: SEARCH });
  await box.fill('a');
  await expect(page).toHaveURL(/\?q=a$/);
  await box.fill('ab');
  await expect(page.getByRole('link', { name: 'fast-b' })).toBeVisible();
  await page.waitForTimeout(2000);
  await expect(page.getByRole('link', { name: 'slow-a' })).toHaveCount(0);
  await expect(page.getByRole('link', { name: 'fast-b' })).toBeVisible();
});

test('empty search result offers a reset', async ({ page }) => {
  await setup(page, {
    list: (url) => (url.searchParams.get('q') === 'zzz' ? { total: 0, items: [] } : { total: 1, items: [row] }),
  });
  await page.goto('/admin/users?q=zzz');
  await expect(page.getByText('Никого не найдено.')).toBeVisible();
  await page.getByRole('button', { name: 'Сбросить фильтры' }).first().click();
  await expect(page).toHaveURL(/\/admin\/users$/);
  await expect(page.getByRole('link', { name: 'customer' })).toBeVisible();
});

test('grant over another active plan requires the replace checkbox', async ({ page }) => {
  const business = {
    ...card,
    profile: { ...card.profile, effective_plan: 'business' },
    subscription: { ...card.subscription, plan: 'business' },
  };
  const { writes } = await setup(page, { card: business });
  const { dialog, reason, confirm } = await openCardDialog(page, 'Подарить или продлить');
  await dialog.getByRole('combobox', { name: 'Тариф' }).selectOption('pro');
  await reason.fill('downgrade on request');
  await expect(confirm).toBeDisabled();
  await dialog.getByRole('checkbox', { name: 'Заменить текущий тариф' }).check();
  await confirm.click();
  await expect(dialog).toBeHidden();
  expect(writes).toEqual([{
    method: 'POST', path: `/api/v1/admin/users/${ID}/grant`,
    body: { plan: 'pro', days: 30, replace_active: true, reason: 'downgrade on request' },
  }]);
});

test('blocking requires a reason of at least 3 characters', async ({ page }) => {
  const { writes } = await setup(page);
  const { reason, confirm } = await openCardDialog(page, 'Заблокировать');
  await reason.fill('ab');
  await expect(confirm).toBeDisabled();
  await reason.fill('spam bot');
  await confirm.click();
  await expect(page.getByText('Готово.')).toBeVisible();
  expect(writes).toEqual([{ method: 'POST', path: `/api/v1/admin/users/${ID}/block`, body: { reason: 'spam bot' } }]);
});

test('early cancel sends the chosen category and warns about paid days', async ({ page }) => {
  const { writes } = await setup(page);
  const { dialog, reason, confirm } = await openCardDialog(page, 'Прекратить досрочно');
  await expect(dialog).toContainText('Оплачено ещё 12 дн.');
  await dialog.getByRole('combobox', { name: 'Причина прекращения' }).selectOption('fraud');
  await reason.fill('chargeback from bank');
  await confirm.click();
  await expect(dialog).toBeHidden();
  expect(writes).toEqual([{
    method: 'POST', path: `/api/v1/admin/users/${ID}/cancel-subscription`,
    body: { category: 'fraud', reason: 'chargeback from bank' },
  }]);
});

test('role change lives in the card and sends PATCH with the reason', async ({ page }) => {
  const { writes } = await setup(page);
  const { dialog, reason, confirm } = await openCardDialog(page, 'Сменить роль');
  await dialog.getByRole('combobox', { name: 'Новая роль' }).selectOption('admin');
  await reason.fill('promote accountant');
  await confirm.click();
  await expect(dialog).toBeHidden();
  expect(writes).toEqual([{
    method: 'PATCH', path: `/api/v1/admin/users/${ID}/role`, body: { role: 'admin', reason: 'promote accountant' },
  }]);
});

test('admin card hides block, role and subscription actions', async ({ page }) => {
  await setup(page);
  await page.goto(`/admin/users/${ADMIN_ID}`);
  await expect(page.getByText('Чтобы заблокировать администратора, сначала снимите роль.')).toBeVisible();
  for (const name of ['Заблокировать', 'Подарить или продлить', 'Записать оплату', 'Сменить роль']) {
    await expect(page.getByRole('button', { name, exact: true })).toHaveCount(0);
  }
});

test('a coded backend error is shown inside the open dialog', async ({ page }) => {
  await setup(page, { failWrite: { detail: { code: 'cannot_block_admin', message: 'Remove the admin role before blocking' } } });
  const { dialog, reason, confirm } = await openCardDialog(page, 'Заблокировать');
  await reason.fill('spam bot');
  await confirm.click();
  await expect(dialog.getByRole('alert')).toHaveText('Сначала снимите роль администратора.');
  await expect(dialog).toBeVisible();
});

test('card has no horizontal scroll on a 390px phone with a long email', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await setup(page);
  await page.goto(`/admin/users/${ID}`);
  await expect(page.getByText('Nino Beridze')).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Платежи' })).toBeVisible();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(0);
});

test('user card visual baseline', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await setup(page);
  await page.goto(`/admin/users/${ID}`);
  await expect(page.getByText('Вопросов за 30 дней')).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Платежи' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Сменить роль', exact: true })).toBeVisible();
  await page.evaluate(async () => { await document.fonts.ready; });
  await expect(page).toHaveScreenshot('admin-user-card-ru-desktop.png', { fullPage: true });
  const mobile = await page.context().newPage();
  await setup(mobile, { lang: 'ka' });
  await mobile.setViewportSize({ width: 390, height: 844 });
  await mobile.goto(`/admin/users/${ID}`);
  await expect(mobile.getByText('Nino Beridze')).toBeVisible();
  await expect(mobile.getByText('კითხვები ბოლო 30 დღეში')).toBeVisible();
  await expect(mobile.getByRole('heading', { name: 'გადახდები' })).toBeVisible();
  await expect(mobile.getByRole('button', { name: 'როლის შეცვლა', exact: true })).toBeVisible();
  await mobile.evaluate(async () => { await document.fonts.ready; });
  await expect(mobile).toHaveScreenshot('admin-user-card-ka-mobile.png', { fullPage: true });
  await mobile.close();
});
