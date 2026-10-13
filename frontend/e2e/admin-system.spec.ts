import { expect, Page, Route, test } from '@playwright/test';

const NOW = Date.parse('2026-10-12T10:00:00Z');
const job = (name: string, state: string, extra: Record<string, unknown> = {}) => ({
  job: name, state, started_at: '2026-10-12T03:00:00Z', finished_at: '2026-10-12T03:40:00Z', exit_code: 0,
  summary: 'ok', trigger: 'cron', skipped: false, log_tail: ['first line', 'last line'], ...extra,
});
const STATUS = {
  generated_at: '2026-10-12T10:00:00',
  jobs: [
    job('scraper', 'ok', { summary: '+3 new docs (full)', trigger: 'manual' }),
    job('canary', 'failed', { exit_code: 1, summary: 'CANARY: 7/10 failed=pit_rate' }),
    job('backup', 'stale', { finished_at: '2026-10-10T01:37:00Z', summary: 'ok infohub_ai-20261010T013001Z.dump 2710 MiB' }),
    { job: 'restore_drill', state: 'unknown', started_at: null, finished_at: null, exit_code: null, summary: null,
      trigger: null, skipped: false, log_tail: [] },
  ],
};

async function json(route: Route, data: unknown, status = 200) {
  await route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(data) });
}

async function setup(page: Page, lang = 'ru', failFirst = false, status: unknown = STATUS) {
  await page.clock.setFixedTime(NOW);
  await page.addInitScript((language) => {
    localStorage.setItem('ta_lang', language);
    localStorage.setItem('ta_authenticated', '1');
  }, lang);
  let failures = failFirst ? 1 : 0;
  await page.route('**/api/v1/**', async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname === '/api/v1/auth/me') return json(route, { username: 'admin', role: 'admin' });
    if (url.pathname === '/api/v1/admin/system') {
      if (failures > 0) { failures -= 1; return json(route, { detail: 'boom' }, 500); }
      return json(route, status);
    }
    return json(route, { detail: 'No fixture' }, 404);
  });
}

const card = (page: Page, name: string) => page.getByRole('article').filter({ has: page.getByRole('heading', { name }) });

test('each job shows its state, summary and age', async ({ page }) => {
  await setup(page);
  await page.goto('/admin/system');
  await expect(page.getByRole('heading', { level: 1, name: 'Состояние системы' })).toBeVisible();
  await expect(card(page, 'Скрапер')).toContainText('В порядке');
  await expect(card(page, 'Скрапер')).toContainText('+3 new docs (full)');
  await expect(card(page, 'Скрапер')).toContainText('запущено вручную');
  await expect(card(page, 'Скрапер')).toContainText('6 ч назад');
  await expect(card(page, 'Канарейка')).toContainText('Ошибка');
  await expect(card(page, 'Канарейка')).toContainText('код выхода 1');
  await expect(card(page, 'Бэкап базы')).toContainText('Просрочено');
  await expect(card(page, 'Бэкап базы')).toContainText('2 дн. назад');
  await expect(card(page, 'Проверка восстановления')).toContainText('Нет данных');
  await expect(card(page, 'Проверка восстановления')).toContainText('Статус ещё не записан');
});

test('log is collapsed until asked for', async ({ page }) => {
  await setup(page);
  await page.goto('/admin/system');
  const scraper = card(page, 'Скрапер');
  await expect(scraper.getByText('last line')).toBeHidden();
  await scraper.getByText('Показать лог').click();
  await expect(scraper.getByText('last line')).toBeVisible();
  await expect(card(page, 'Проверка восстановления').getByText('Показать лог')).toHaveCount(0);
});

test('load error offers a retry', async ({ page }) => {
  await setup(page, 'ru', true);
  await page.goto('/admin/system');
  await expect(page.getByRole('main').getByRole('alert')).toBeVisible();
  await page.getByRole('button', { name: 'Повторить' }).click();
  await expect(card(page, 'Скрапер')).toContainText('В порядке');
});

test('english and georgian copy render', async ({ page }) => {
  await setup(page, 'en');
  await page.goto('/admin/system');
  await expect(card(page, 'Database backup')).toContainText('Overdue');
  await setup(page, 'ka');
  await page.goto('/admin/system');
  await expect(page.getByRole('heading', { level: 1, name: 'სისტემის მდგომარეობა' })).toBeVisible();
});

test('system visual baseline', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await setup(page);
  await page.goto('/admin/system');
  await expect(card(page, 'Скрапер')).toContainText('В порядке');
  await page.evaluate(async () => { await document.fonts.ready; });
  await expect(page).toHaveScreenshot('admin-system-ru-desktop.png', { fullPage: true });

  const mobile = await page.context().newPage();
  await setup(mobile, 'ka');
  await mobile.setViewportSize({ width: 390, height: 844 });
  await mobile.goto('/admin/system');
  await expect(mobile.getByRole('heading', { level: 1, name: 'სისტემის მდგომარეობა' })).toBeVisible();
  const overflow = await mobile.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(0);
  await mobile.evaluate(async () => { await document.fonts.ready; });
  await expect(mobile).toHaveScreenshot('admin-system-ka-mobile.png', { fullPage: true });
  await mobile.close();
});

test('skipped job shows the busy state without an exit code', async ({ page }) => {
  const skipped = {
    ...STATUS,
    jobs: STATUS.jobs.map((j) => (j.job === 'restore_drill'
      ? job('restore_drill', 'skipped', {
        skipped: true, exit_code: 75, finished_at: '2026-10-11T22:20:00Z',
        summary: 'skipped: a backup or another drill holds the lock',
      })
      : j)),
  };
  await setup(page, 'ru', false, skipped);
  await page.goto('/admin/system');
  const drill = card(page, 'Проверка восстановления');
  await expect(drill).toContainText('Пропущено (занято)');
  await expect(drill).toContainText('skipped: a backup or another drill holds the lock');
  await expect(drill).not.toContainText('код выхода 75');
});
