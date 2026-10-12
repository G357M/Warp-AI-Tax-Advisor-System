import { expect, Page, Route, test } from '@playwright/test';

const rows = [
  {
    message_id: 'q-1', created_at: '2026-10-11T09:30:00', pseudonym: 'U-7F3A2C',
    question: 'Какой срок подачи декларации по НДС?', answer: 'Не позднее 15 числа следующего месяца.',
    flags: ['no_precise_citation'], rating: -1, verdict: null, processing_ms: 8400,
  },
  {
    message_id: 'q-2', created_at: '2026-10-11T08:10:00', pseudonym: 'U-19B0E4',
    question: 'Какая ставка налога на прибыль?', answer: 'Пятнадцать процентов.',
    flags: [], rating: 1, verdict: 'correct', processing_ms: 5200,
  },
  {
    message_id: 'q-3', created_at: '2026-10-10T17:45:00', pseudonym: 'U-7F3A2C',
    question: 'Нужна ли регистрация ИП для фрилансера?', answer: 'Зависит от дохода.',
    flags: ['no_evidence'], rating: null, verdict: null, processing_ms: null,
  },
];
const summary = {
  answers: 120, rated: 40, down: 10, down_share: 0.25, reviewed: 12, reviewed_share: 0.1,
  verdicts: { correct: 7, partial: 3, wrong: 2 },
  reasons: {
    not_in_corpus: 0, wrong_version: 0, wrong_citation: 2, fabricated: 0, incomplete: 0, language: 0, other: 0,
  },
  no_precise_citation_share: 0.3, median_processing_ms: 8400, down_unreviewed: 6,
};
const detail = (id: string) => ({
  message: {
    id, created_at: '2026-10-11T09:30:00', content: 'Не позднее 15 числа следующего месяца.',
    sources: [{ title: 'საგადასახადო კოდექსი', url: 'https://matsne.gov.ge/ka/document/view/1043717', article_ref: '168' }],
    evidence: {
      status: 'grounded', coverage: 'exact_provision', question_class: 'canonical_law_lookup', source_count: 2,
      has_precise_citation: false, retrieved_count: 8,
    },
    processing_ms: 8400, flags: ['no_precise_citation'],
  },
  conversation: {
    pseudonym: 'U-7F3A2C',
    messages: [
      { id: 'm-user', role: 'user', content: 'Какой срок подачи декларации по НДС?', created_at: '2026-10-11T09:29:50' },
      { id, role: 'assistant', content: 'Не позднее 15 числа следующего месяца.', created_at: '2026-10-11T09:30:00' },
    ],
  },
  rating: { value: -1, comment: 'Статья не та', updated_at: '2026-10-11T09:35:00' },
  reviews: [{
    verdict: 'partial', reasons: ['incomplete'], note: 'Нет ссылки на статью',
    created_at: '2026-10-11T12:00:00', reviewer: { username: 'admin' },
  }],
  neighbors: { prev_id: 'q-prev', next_id: 'q-next' },
});

type Write = { method: string; path: string; body: unknown };
type Options = { lang?: 'ru' | 'ka' | 'en'; list?: (url: URL) => unknown };

async function json(route: Route, data: unknown, status = 200) {
  await route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(data) });
}

async function setup(page: Page, options: Options = {}) {
  await page.addInitScript((language) => {
    localStorage.setItem('ta_lang', language);
    localStorage.setItem('ta_authenticated', '1');
  }, options.lang ?? 'ru');
  const writes: Write[] = [];
  const listQueries: string[] = [];
  await page.route('**/api/v1/**', async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    if (request.method() !== 'GET') {
      writes.push({ method: request.method(), path, body: request.postDataJSON() });
      if (path.endsWith('/reveal-user')) return json(route, { user_id: 'u-123' });
      const id = /\/answers\/([^/]+)\//.exec(path)?.[1] ?? 'q-1';
      return json(route, {
        ...detail(id),
        reviews: [
          { verdict: 'wrong', reasons: ['wrong_citation', 'fabricated'], note: 'cites 168',
            created_at: '2026-10-12T10:00:00', reviewer: { username: 'admin' } },
          ...detail(id).reviews,
        ],
      });
    }
    if (path === '/api/v1/auth/me') return json(route, { username: 'admin', role: 'admin' });
    if (path === '/api/v1/admin/quality/answers') {
      listQueries.push(url.search);
      return json(route, options.list ? await options.list(url) : { total: rows.length, items: rows });
    }
    if (path === '/api/v1/admin/quality/summary') return json(route, summary);
    const match = /^\/api\/v1\/admin\/quality\/answers\/([^/]+)$/.exec(path);
    if (match) return json(route, detail(match[1]));
    return json(route, { detail: 'No fixture' }, 404);
  });
  return { writes, listQueries };
}

const QUESTION = rows[0].question;
const FILTERED = '?rating=down&verdict=unreviewed';

async function noHorizontalScroll(page: Page) {
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(0);
}

test('feed filters live in the URL and survive reload', async ({ page }) => {
  const { listQueries } = await setup(page);
  await page.goto('/admin/quality');
  await expect(page.getByRole('link', { name: QUESTION })).toBeVisible();
  await page.getByRole('button', { name: '👎 без разметки', exact: true }).click();
  await expect(page).toHaveURL(/\/admin\/quality\?rating=down&verdict=unreviewed$/);
  await page.getByRole('checkbox', { name: 'Нет точной ссылки' }).click();
  await expect(page).toHaveURL(/\/admin\/quality\?rating=down&verdict=unreviewed&flags=no_precise_citation$/);
  await page.reload();
  await expect(page.getByRole('combobox', { name: 'Оценка' })).toHaveValue('down');
  await expect(page.getByRole('combobox', { name: 'Вердикт' })).toHaveValue('unreviewed');
  await expect(page.getByRole('checkbox', { name: 'Нет точной ссылки' })).toBeChecked();
  await expect(page.getByRole('link', { name: QUESTION })).toBeVisible();
  await expect.poll(() => listQueries.at(-1)).toContain('flags=no_precise_citation');
  expect(listQueries.at(-1)).toContain('rating=down');
  expect(listQueries.at(-1)).toContain('verdict=unreviewed');
});

test('opening an answer and going back keeps the filters', async ({ page }) => {
  await setup(page);
  await page.goto(`/admin/quality${FILTERED}`);
  await page.getByRole('link', { name: QUESTION }).click();
  await expect(page).toHaveURL(`/admin/quality/q-1?back=${encodeURIComponent(FILTERED)}`);
  await page.getByRole('link', { name: '← К ленте' }).click();
  await expect(page).toHaveURL(`/admin/quality${FILTERED}`);
  await expect(page.getByRole('combobox', { name: 'Оценка' })).toHaveValue('down');
});

test('review is sent with verdict, reasons, note and the journal reason', async ({ page }) => {
  const { writes } = await setup(page);
  await page.goto('/admin/quality/q-1');
  const save = page.getByRole('button', { name: 'Сохранить разметку' });
  const reason = page.getByRole('textbox', { name: /Причина \(обязательно/ });
  await expect(save).toBeDisabled();
  await page.getByRole('button', { name: 'Неверно', exact: true }).click();
  await expect(save).toBeDisabled();
  await reason.fill('ab');
  await expect(save).toBeDisabled();
  await page.getByRole('checkbox', { name: 'Ошибка ссылки' }).check();
  await page.getByRole('checkbox', { name: 'Выдумано' }).check();
  await page.getByRole('textbox', { name: 'Заметка' }).fill('cites 168');
  await reason.fill('weekly review');
  await expect(save).toBeEnabled();
  await save.click();
  await expect(page.getByText('Разметка сохранена.')).toBeVisible();
  expect(writes).toEqual([{
    method: 'POST', path: '/api/v1/admin/quality/answers/q-1/review',
    body: { verdict: 'wrong', reasons: ['wrong_citation', 'fabricated'], note: 'cites 168', reason: 'weekly review' },
  }]);
  await expect(page.getByText('cites 168')).toBeVisible();
  await expect(save).toBeDisabled();
});

test('opening the client needs a reason, is posted, then leads to the user card', async ({ page }) => {
  const { writes } = await setup(page);
  await page.goto('/admin/quality/q-1');
  await page.getByRole('button', { name: 'Открыть клиента', exact: true }).click();
  const dialog = page.getByRole('dialog');
  const confirm = dialog.getByRole('button', { name: 'Подтвердить' });
  await expect(dialog.getByRole('heading', { name: 'Открыть данные клиента?' })).toBeVisible();
  await expect(confirm).toBeDisabled();
  await dialog.getByRole('textbox', { name: /Причина/ }).fill('ab');
  await expect(confirm).toBeDisabled();
  await dialog.getByRole('textbox', { name: /Причина/ }).fill('refund complaint');
  await confirm.click();
  await expect(page).toHaveURL(/\/admin\/users\/u-123$/);
  expect(writes).toEqual([{
    method: 'POST', path: '/api/v1/admin/quality/answers/q-1/reveal-user', body: { reason: 'refund complaint' },
  }]);
});

test('next answer keeps the filters in the back parameter', async ({ page }) => {
  await setup(page);
  await page.goto(`/admin/quality/q-1?back=${encodeURIComponent(FILTERED)}`);
  await page.getByRole('link', { name: 'Следующий →' }).click();
  await expect(page).toHaveURL(`/admin/quality/q-next?back=${encodeURIComponent(FILTERED)}`);
  await expect(page.getByRole('link', { name: '← К ленте' })).toHaveAttribute('href', `/admin/quality${FILTERED}`);
  await expect(page.getByRole('heading', { name: 'Признаки' })).toBeVisible();
});

test('feed and review have no horizontal scroll on a 390px phone', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await setup(page);
  await page.goto('/admin/quality');
  await expect(page.getByRole('link', { name: QUESTION })).toBeVisible();
  await expect(page.getByText('Доля 👎', { exact: true })).toBeVisible();
  await noHorizontalScroll(page);
  await page.goto('/admin/quality/q-1');
  await expect(page.getByRole('heading', { name: 'История разметки' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Признаки' })).toBeVisible();
  await noHorizontalScroll(page);
});

test('answer quality visual baseline', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await setup(page);
  await page.goto('/admin/quality');
  await expect(page.getByText('Доля 👎', { exact: true })).toBeVisible();
  await expect(page.getByText('Медианное время ответа', { exact: true })).toBeVisible();
  await expect(page.getByText('из 40 оценённых')).toBeVisible();
  await expect(page.getByRole('link', { name: QUESTION })).toBeVisible();
  await expect(page.getByRole('link', { name: rows[2].question })).toBeVisible();
  await expect(page.getByText('U-19B0E4')).toBeVisible();
  await page.evaluate(async () => { await document.fonts.ready; });
  await expect(page).toHaveScreenshot('admin-quality-ru-desktop.png', { fullPage: true });

  const mobile = await page.context().newPage();
  await setup(mobile, { lang: 'ka' });
  await mobile.setViewportSize({ width: 390, height: 844 });
  await mobile.goto('/admin/quality/q-1');
  await expect(mobile.getByRole('heading', { name: 'ნიშნები' })).toBeVisible();
  await expect(mobile.getByRole('heading', { name: 'მომხმარებლის შეფასება' })).toBeVisible();
  await expect(mobile.getByRole('heading', { name: 'შემოწმების ისტორია' })).toBeVisible();
  await expect(mobile.getByText('Статья не та')).toBeVisible();
  await expect(mobile.getByText('Нет ссылки на статью')).toBeVisible();
  await mobile.evaluate(async () => { await document.fonts.ready; });
  await expect(mobile).toHaveScreenshot('admin-quality-review-ka-mobile.png', { fullPage: true });
  await mobile.close();
});
