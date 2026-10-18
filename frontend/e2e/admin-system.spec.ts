import { expect, Page, Route, test } from '@playwright/test';

const NOW = Date.parse('2026-10-12T10:00:00Z');
const job = (name: string, state: string, extra: Record<string, unknown> = {}) => ({
  job: name, state, started_at: '2026-10-12T03:00:00Z', finished_at: '2026-10-12T03:40:00Z', exit_code: 0,
  summary: 'ok', trigger: 'cron', skipped: false, log_tail: ['first line', 'last line'], request: null, ...extra,
});
const STATUS = {
  generated_at: '2026-10-12T10:00:00',
  jobs: [
    job('scraper', 'ok', { summary: '+3 new docs (full)', trigger: 'manual' }),
    job('canary', 'failed', { exit_code: 1, summary: 'CANARY: 7/10 failed=pit_rate' }),
    job('backup', 'stale', { finished_at: '2026-10-10T01:37:00Z', summary: 'ok infohub_ai-20261010T013001Z.dump 2710 MiB' }),
    { job: 'restore_drill', state: 'unknown', started_at: null, finished_at: null, exit_code: null, summary: null,
      trigger: null, skipped: false, log_tail: [], request: null },
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

const RID = '7a1c0d3e-1111-4222-8333-944455556666';
const req = (job: string, state: string, extra: Record<string, unknown> = {}) => ({
  job, state, request_id: RID, requested_at: '2026-10-12T09:58:00Z', started_at: null, finished_at: null,
  exit_code: null, reason: null, ...extra,
});
const withRequest = (name: string, request: unknown) => ({
  ...STATUS, jobs: STATUS.jobs.map((j) => (j.job === name ? { ...j, request } : j)),
});

/** System mock whose GET answer the test switches with `set`; POSTs are recorded. */
async function setupRuns(page: Page, initial: unknown, post = { status: 202, body: { request_id: RID, state: 'queued' } as unknown }) {
  await page.addInitScript(() => {
    localStorage.setItem('ta_lang', 'ru');
    localStorage.setItem('ta_authenticated', '1');
  });
  let current = initial;
  const posts: string[] = [];
  await page.route('**/api/v1/**', async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname === '/api/v1/auth/me') return json(route, { username: 'admin', role: 'admin' });
    if (url.pathname === '/api/v1/admin/system') return json(route, current);
    if (url.pathname.startsWith('/api/v1/admin/system/jobs/') && route.request().method() === 'POST') {
      posts.push(url.pathname);
      return json(route, post.body, post.status);
    }
    return json(route, { detail: 'No fixture' }, 404);
  });
  return { posts, set: (next: unknown) => { current = next; } };
}

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

test('each card offers only its whitelisted runs', async ({ page }) => {
  await setup(page);
  await page.goto('/admin/system');
  await expect(card(page, 'Скрапер').getByRole('button', { name: 'Загрузить новые документы' })).toBeEnabled();
  await expect(card(page, 'Скрапер').getByRole('button', { name: 'Полный ночной прогон' })).toBeEnabled();
  await expect(card(page, 'Канарейка').getByRole('button', { name: 'Прогнать канарейку' })).toBeEnabled();
  await expect(card(page, 'Бэкап базы').getByRole('button', { name: 'Бэкап сейчас' })).toBeEnabled();
  await expect(card(page, 'Проверка восстановления').getByRole('button')).toHaveCount(0);
});

test('manual run: confirm the cost, then the card follows the request to done', async ({ page }) => {
  await page.clock.setFixedTime(NOW);
  const mock = await setupRuns(page, STATUS);
  await page.goto('/admin/system');
  const canary = card(page, 'Канарейка');
  await canary.getByRole('button', { name: 'Прогнать канарейку' }).click();
  const dialog = page.getByRole('dialog');
  await expect(dialog).toContainText('около 10 вызовов gpt-4o-mini');
  mock.set(withRequest('canary', req('canary', 'queued')));
  await dialog.getByRole('button', { name: 'Запустить' }).click();
  await expect(dialog).toBeHidden();
  expect(mock.posts).toEqual(['/api/v1/admin/system/jobs/canary']);
  await expect(canary).toContainText('В очереди');
  await expect(canary.getByRole('button', { name: 'Прогнать канарейку' })).toBeDisabled();

  mock.set(withRequest('canary', req('canary', 'running', { started_at: '2026-10-12T10:00:30Z' })));
  await page.getByRole('button', { name: 'Обновить' }).click();
  await expect(canary).toContainText('Выполняется с');

  mock.set(withRequest('canary', req('canary', 'done', {
    started_at: '2026-10-12T10:00:30Z', finished_at: '2026-10-12T10:02:10Z', exit_code: 0,
  })));
  await page.getByRole('button', { name: 'Обновить' }).click();
  await expect(canary).toContainText('Ручной запуск завершён');
  await expect(canary.getByRole('button', { name: 'Прогнать канарейку' })).toBeEnabled();
});

test('a refused run explains itself on the card', async ({ page }) => {
  await page.clock.setFixedTime(NOW);
  await setupRuns(page, STATUS, { status: 409, body: { detail: { code: 'backup_too_recent', message: 'x' } } });
  await page.goto('/admin/system');
  await card(page, 'Бэкап базы').getByRole('button', { name: 'Бэкап сейчас' }).click();
  const dialog = page.getByRole('dialog');
  await expect(dialog).toContainText('Хранится 4 последних дампа; самый старый будет удалён.');
  await dialog.getByRole('button', { name: 'Запустить' }).click();
  await expect(dialog).toBeHidden();
  await expect(card(page, 'Бэкап базы')).toContainText('Последний бэкап был меньше 6 часов назад.');
});

test('an active request is re-read every 15 seconds and locks both scraper buttons', async ({ page }) => {
  await page.clock.install({ time: NOW });
  const mock = await setupRuns(page, withRequest('scraper', req('scraper_full', 'running', { started_at: '2026-10-12T09:59:00Z' })));
  await page.goto('/admin/system');
  const scraper = card(page, 'Скрапер');
  await expect(scraper).toContainText('Выполняется с');
  await expect(scraper.getByRole('button', { name: 'Загрузить новые документы' })).toBeDisabled();
  await expect(scraper.getByRole('button', { name: 'Полный ночной прогон' })).toBeDisabled();
  mock.set(withRequest('scraper', req('scraper_full', 'skipped', {
    started_at: '2026-10-12T09:59:00Z', finished_at: '2026-10-12T09:59:01Z', exit_code: 0, reason: 'busy',
  })));
  await page.clock.runFor(15_000);
  await expect(scraper).toContainText('Ручной запуск пропущен');
  await expect(scraper.getByRole('button', { name: 'Полный ночной прогон' })).toBeEnabled();
});
