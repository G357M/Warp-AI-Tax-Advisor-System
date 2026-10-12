import { expect, Page, Route, test } from '@playwright/test';

type Bucket = Record<string, number | string | boolean | null>;

function days(count: number, last: string): string[] {
  const end = new Date(`${last}T00:00:00Z`);
  return Array.from({ length: count }, (_, i) => {
    const d = new Date(end);
    d.setUTCDate(end.getUTCDate() - (count - 1 - i));
    return d.toISOString().slice(0, 10);
  });
}

function months(count: number, last: string): string[] {
  const [y, m] = last.split('-').map(Number);
  return Array.from({ length: count }, (_, i) => {
    const total = y * 12 + (m - 1) - (count - 1 - i);
    return `${Math.floor(total / 12)}-${String((total % 12) + 1).padStart(2, '0')}-01`;
  });
}

function bucket(start: string, i: number, partial: boolean, zero: boolean, clean = false): Bucket {
  const v = (n: number) => (zero ? 0 : n);
  const withEvidence = zero || i < 25 ? 0 : 4;
  return {
    start, partial, signups: v(i % 3), askers: v(2 + (i % 4)), questions: v(5 + ((i * 7) % 11)),
    payments: v(i % 5 === 0 ? 1 : 0), revenue_minor: v(i % 5 === 0 ? 4900 : 0),
    up: v(i >= 25 ? 2 : 0), down: v(i >= 27 ? 1 : 0), answers: v(5 + ((i * 7) % 11)),
    answers_with_evidence: withEvidence, flagged: withEvidence && !clean ? 1 : 0,
    median_processing_ms: withEvidence ? 8400 : null,
  };
}

function trends(period: '30d' | '12m', zero = false, clean = false) {
  const starts = period === '30d' ? days(30, '2026-10-12') : months(12, '2026-10-01');
  const buckets = starts.map((s, i) => bucket(s, i, i === starts.length - 1, zero, clean));
  const sum = (key: string) => buckets.reduce((acc, b) => acc + Number(b[key]), 0);
  const current = {
    signups: sum('signups'), askers: zero ? 0 : 9, questions: sum('questions'), payments: sum('payments'),
    revenue_minor: sum('revenue_minor'), up: sum('up'), down: sum('down'),
  };
  const previous = zero ? { ...current } : { ...current, revenue_minor: 9800, payments: 3, signups: 0 };
  return {
    period, bucket: period === '30d' ? 'day' : 'month', timezone: 'Asia/Tbilisi',
    quality_since: zero ? null : '2026-10-07', median_processing_ms: zero ? null : 8400,
    buckets, totals: { current, previous },
  };
}

type Options = { lang?: 'ru' | 'ka'; zero?: boolean; clean?: boolean; failFirst?: boolean };

async function json(route: Route, data: unknown, status = 200) {
  await route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(data) });
}

async function setup(page: Page, options: Options = {}) {
  await page.addInitScript((language) => {
    localStorage.setItem('ta_lang', language);
    localStorage.setItem('ta_authenticated', '1');
  }, options.lang ?? 'ru');
  const queries: string[] = [];
  let failures = options.failFirst ? 1 : 0;
  await page.route('**/api/v1/**', async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname === '/api/v1/auth/me') return json(route, { username: 'admin', role: 'admin' });
    if (url.pathname === '/api/v1/admin/trends') {
      queries.push(url.searchParams.get('period') ?? '');
      if (failures > 0) {
        failures -= 1;
        return json(route, { detail: 'boom' }, 500);
      }
      return json(route, trends(url.searchParams.get('period') === '12m' ? '12m' : '30d', options.zero, options.clean));
    }
    return json(route, { detail: 'No fixture' }, 404);
  });
  return { queries };
}

async function noHorizontalScroll(page: Page) {
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(0);
}

test('default period loads 30 days with totals and deltas', async ({ page }) => {
  const { queries } = await setup(page);
  await page.goto('/admin/trends');
  await expect(page.getByRole('heading', { level: 1, name: 'Динамика' })).toBeVisible();
  await expect(page.getByRole('button', { name: '30 дней' })).toHaveAttribute('aria-pressed', 'true');
  await expect(page.getByText('294 ₾')).toBeVisible();
  await expect(page.getByText('+200% к прошлому периоду')).toBeVisible();
  await expect(page.getByText('в прошлом периоде было 0')).toBeVisible();
  await expect(page.getByText('Данные о качестве собираются с 07.10.')).toBeVisible();
  await expect(page.getByText('Медианное время ответа: 8,4 с')).toBeVisible();
  expect(queries).toEqual(['30d']);
});

test('period switch lives in the URL and survives reload', async ({ page }) => {
  const { queries } = await setup(page);
  await page.goto('/admin/trends');
  await page.getByRole('button', { name: '12 месяцев' }).click();
  await expect(page).toHaveURL(/\?period=12m$/);
  await expect(page.getByRole('button', { name: '12 месяцев' })).toHaveAttribute('aria-pressed', 'true');
  await page.reload();
  await expect(page.getByRole('button', { name: '12 месяцев' })).toHaveAttribute('aria-pressed', 'true');
  await page.getByRole('button', { name: '30 дней' }).click();
  await expect(page).toHaveURL(/\/admin\/trends$/);
  expect(queries).toEqual(['30d', '12m', '12m', '30d']);
});

test('unknown period in the URL falls back to 30 days', async ({ page }) => {
  const { queries } = await setup(page);
  await page.goto('/admin/trends?period=bogus');
  await expect(page.getByRole('button', { name: '30 дней' })).toHaveAttribute('aria-pressed', 'true');
  expect(queries).toEqual(['30d']);
});

test('data table shows every bucket and marks the running one', async ({ page }) => {
  await setup(page);
  await page.goto('/admin/trends');
  const revenue = page.getByRole('figure').filter({ hasText: 'Выручка' }).first();
  await revenue.getByText('Показать данные').click();
  await expect(revenue.locator('tbody tr')).toHaveCount(30);
  await expect(revenue.locator('tbody tr').last()).toContainText('текущий период ещё идёт');
  const flagged = page.getByRole('figure').filter({ hasText: 'Доля ответов с признаками проблем' });
  await flagged.getByText('Показать данные').click();
  await expect(flagged.locator('tbody tr').first()).toContainText('—');
  await expect(flagged.locator('tbody tr').last()).toContainText('25%');
});

test('hovering a column shows its values', async ({ page }) => {
  await setup(page);
  await page.goto('/admin/trends');
  const ratings = page.getByRole('figure').filter({ hasText: 'Оценки ответов' });
  await ratings.locator('button').last().hover();
  await expect(ratings.getByText('👍 полезно: 2')).toBeVisible();
  await expect(ratings.getByText('👎 неточно: 1')).toBeVisible();
});

test('load error offers a retry', async ({ page }) => {
  const { queries } = await setup(page, { failFirst: true });
  await page.goto('/admin/trends');
  await expect(page.getByRole('alert')).toBeVisible();
  await page.getByRole('button', { name: 'Повторить' }).click();
  await expect(page.getByText('294 ₾')).toBeVisible();
  expect(queries).toEqual(['30d', '30d']);
});

test('empty period shows no NaN and says there is no data', async ({ page }) => {
  await setup(page, { zero: true });
  await page.goto('/admin/trends');
  await expect(page.getByText('За период данных нет').first()).toBeVisible();
  await expect(page.getByText('Данных о качестве пока нет.')).toBeVisible();
  const body = await page.locator('main').innerText();
  expect(body).not.toMatch(/NaN|Infinity/);
});

test('a real 0% flagged share is shown as 0%, not as missing data', async ({ page }) => {
  await setup(page, { clean: true });
  await page.goto('/admin/trends');
  const flagged = page.getByRole('figure').filter({ hasText: 'Доля ответов с признаками проблем' });
  await expect(flagged.getByText('Данные о качестве собираются с 07.10.')).toBeVisible();
  await expect(flagged.getByText('За период данных нет')).toHaveCount(0);
  await flagged.getByText('Показать данные').click();
  await expect(flagged.locator('tbody tr').last()).toContainText('0%');
});

test('12-month axis does not put the last two month labels side by side', async ({ page }) => {
  await setup(page);
  await page.goto('/admin/trends?period=12m');
  await expect(page.getByRole('button', { name: '12 месяцев' })).toHaveAttribute('aria-pressed', 'true');
  const axis = page.getByRole('figure').filter({ hasText: 'Выручка' }).first().locator('[data-axis="x"] > span');
  await expect(axis).toHaveCount(12);
  const shown = (await axis.allInnerTexts()).map((t) => t.trim() !== '');
  expect(shown.slice(-2)).toEqual([false, true]);
});

test('trends visual baseline', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await setup(page);
  await page.goto('/admin/trends');
  await expect(page.getByText('294 ₾')).toBeVisible();
  await page.evaluate(async () => { await document.fonts.ready; });
  await expect(page).toHaveScreenshot('admin-trends-ru-desktop.png', { fullPage: true });

  const mobile = await page.context().newPage();
  await setup(mobile, { lang: 'ka' });
  await mobile.setViewportSize({ width: 390, height: 844 });
  await mobile.goto('/admin/trends');
  await expect(mobile.getByRole('heading', { level: 1, name: 'დინამიკა' })).toBeVisible();
  await expect(mobile.getByText('294 ₾')).toBeVisible();
  await noHorizontalScroll(mobile);
  await mobile.evaluate(async () => { await document.fonts.ready; });
  await expect(mobile).toHaveScreenshot('admin-trends-ka-mobile.png', { fullPage: true });
  await mobile.close();
});
