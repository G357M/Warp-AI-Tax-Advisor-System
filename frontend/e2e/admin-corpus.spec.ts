import { expect, Page, Route, test } from '@playwright/test';

const weeks = Array.from({ length: 12 }, (_, i) => {
  const d = new Date(Date.UTC(2026, 6, 27 + i * 7));
  return { week_start: d.toISOString().slice(0, 10), added: [9, 4, 0, 12, 7, 3, 5, 8, 2, 6, 11, 1][i], partial: i === 11 };
});
const CORPUS = {
  totals: { documents: 14725, chunks: 269218, added_7d: 12, added_30d: 61, last_ingest: '2026-10-12T03:12:40' },
  by_type: [
    { document_type: 'court_decision', documents: 11249, added_30d: 40, without_date: 0, without_chunks: 0 },
    { document_type: 'law', documents: 1204, added_30d: 3, without_date: 572, without_chunks: 2 },
  ],
  weekly: weeks,
  pending: { decision_facts: 4, law_amendments: 0 },
};

async function json(route: Route, data: unknown, status = 200) {
  await route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(data) });
}

async function setup(page: Page, lang = 'ru') {
  await page.addInitScript((language) => {
    localStorage.setItem('ta_lang', language);
    localStorage.setItem('ta_authenticated', '1');
  }, lang);
  const documentQueries: string[] = [];
  await page.route('**/api/v1/**', async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname === '/api/v1/auth/me') return json(route, { username: 'admin', role: 'admin' });
    if (url.pathname === '/api/v1/admin/corpus') return json(route, CORPUS);
    if (url.pathname === '/api/v1/admin/documents') {
      documentQueries.push(url.searchParams.get('doc_type') ?? '');
      return json(route, { total: 0, items: [] });
    }
    return json(route, { detail: 'No fixture' }, 404);
  });
  return { documentQueries };
}

test('totals, queues and per-type gaps', async ({ page }) => {
  await setup(page);
  await page.goto('/admin/corpus');
  await expect(page.getByRole('heading', { level: 1, name: 'Корпус' })).toBeVisible();
  await expect(page.getByText(/14\s725/)).toBeVisible();
  await expect(page.getByText(/269\s218/)).toBeVisible();
  await expect(page.getByText('Решения ждут извлечения фактов')).toBeVisible();
  const law = page.getByRole('row').filter({ hasText: 'law' });
  await expect(law).toContainText('572');
});

test('weekly chart lists 12 weeks and marks the running one', async ({ page }) => {
  await setup(page);
  await page.goto('/admin/corpus');
  const chart = page.getByRole('figure').filter({ hasText: 'Поступления по неделям' });
  await chart.getByText('Показать данные').click();
  await expect(chart.locator('tbody tr')).toHaveCount(12);
  await expect(chart.locator('tbody tr').last()).toContainText('текущий период ещё идёт');
});

test('a type links to the filtered documents list', async ({ page }) => {
  const { documentQueries } = await setup(page);
  await page.goto('/admin/corpus');
  await page.getByRole('link', { name: 'law', exact: true }).click();
  await expect(page).toHaveURL(/\/admin\/documents\?doc_type=law$/);
  await expect(page.getByRole('combobox', { name: 'Тип' })).toHaveValue('law');
  await expect.poll(() => documentQueries.at(-1)).toBe('law');
});

test('unknown doc_type in the URL is ignored', async ({ page }) => {
  const { documentQueries } = await setup(page);
  await page.goto('/admin/documents?doc_type=evil');
  await expect.poll(() => documentQueries.at(-1)).toBe('');
});

test('corpus visual baseline', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await setup(page);
  await page.goto('/admin/corpus');
  await expect(page.getByText(/14\s725/)).toBeVisible();
  await page.evaluate(async () => { await document.fonts.ready; });
  await expect(page).toHaveScreenshot('admin-corpus-ru-desktop.png', { fullPage: true });
});
