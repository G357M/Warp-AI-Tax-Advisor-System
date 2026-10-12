import { expect, Page, Route, test } from '@playwright/test';

const QUESTION = 'Какая ставка НДС в Грузии?';
const answer = {
  response: 'Стандартная ставка НДС в Грузии — 18%.',
  sources: [],
  evidence: {
    status: 'grounded', basis: '', coverage: '', source_count: 1, official_sources_only: true,
    has_precise_citation: true, has_official_provision_link: false, generated_at: '2026-10-12T10:00:00',
  },
  conversation_id: 'c1',
  retrieved_count: 1,
  processing_time: 1.2,
};
const RATING_PATH = '/api/v1/query/messages/m1/rating';
const UP = 'Полезный ответ';
const DOWN = 'Неточный ответ';
const THANKS = 'Спасибо, это поможет улучшить ответы';
const RATING_ERROR = 'Не удалось сохранить оценку. Попробуйте ещё раз.';

type Write = { method: string; path: string; body: unknown };

async function json(route: Route, data: unknown, status = 200) {
  await route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(data) });
}

async function setup(page: Page, options: { authenticated?: boolean; failRating?: boolean } = {}) {
  const authenticated = options.authenticated ?? true;
  await page.addInitScript((signedIn) => {
    localStorage.setItem('ta_lang', 'ru');
    localStorage.removeItem('ta_token');
    if (signedIn) localStorage.setItem('ta_authenticated', '1');
    else localStorage.removeItem('ta_authenticated');
  }, authenticated);
  const writes: Write[] = [];
  await page.route('**/api/v1/**', async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    if (url.pathname === '/api/v1/query' && request.method() === 'POST') {
      return json(route, { ...answer, message_id: 'm1' });
    }
    if (url.pathname === '/api/v1/public/query' && request.method() === 'POST') {
      return json(route, answer);
    }
    if (url.pathname === RATING_PATH) {
      if (options.failRating) return json(route, { detail: 'boom' }, 500);
      const body = request.method() === 'PUT' ? request.postDataJSON() : null;
      writes.push({ method: request.method(), path: url.pathname, body });
      return json(route, { ok: true });
    }
    if (url.pathname === '/api/v1/auth/me') return json(route, { username: 'customer', role: 'user' });
    return json(route, { detail: 'No fixture' }, 404);
  });
  return writes;
}

async function ask(page: Page) {
  await page.goto('/');
  await page.getByRole('button', { name: QUESTION }).click();
  await expect(page.getByText(answer.response)).toBeVisible();
}

test('thumbs-up saves a rating and a second click withdraws it', async ({ page }) => {
  const writes = await setup(page);
  await ask(page);
  const up = page.getByRole('button', { name: UP });
  await expect(up).toHaveAttribute('aria-pressed', 'false');
  await up.click();
  await expect(up).toHaveAttribute('aria-pressed', 'true');
  await expect(page.getByText(THANKS)).toBeVisible();
  await up.click();
  await expect(up).toHaveAttribute('aria-pressed', 'false');
  await expect(page.getByText(THANKS)).toHaveCount(0);
  expect(writes).toEqual([
    { method: 'PUT', path: RATING_PATH, body: { value: 1 } },
    { method: 'DELETE', path: RATING_PATH, body: null },
  ]);
});

test('thumbs-down opens the comment box and sends the comment', async ({ page }) => {
  const writes = await setup(page);
  await ask(page);
  const down = page.getByRole('button', { name: DOWN });
  await down.click();
  await expect(down).toHaveAttribute('aria-pressed', 'true');
  const comment = page.getByRole('textbox', { name: 'Что не так?' });
  await expect(comment).toBeVisible();
  await comment.fill('Не та статья');
  await page.getByRole('button', { name: 'Отправить', exact: true }).click();
  await expect.poll(() => writes.length).toBe(2);
  expect(writes).toEqual([
    { method: 'PUT', path: RATING_PATH, body: { value: -1 } },
    { method: 'PUT', path: RATING_PATH, body: { value: -1, comment: 'Не та статья' } },
  ]);
});

test('a failed save returns the button to unpressed and shows the error', async ({ page }) => {
  const writes = await setup(page, { failRating: true });
  await ask(page);
  const up = page.getByRole('button', { name: UP });
  await up.click();
  await expect(page.getByRole('alert').filter({ hasText: RATING_ERROR })).toBeVisible();
  await expect(up).toHaveAttribute('aria-pressed', 'false');
  await expect(page.getByText(THANKS)).toHaveCount(0);
  expect(writes).toEqual([]);
});

test('guests get no rating buttons', async ({ page }) => {
  const writes = await setup(page, { authenticated: false });
  await ask(page);
  await expect(page.getByRole('button', { name: UP })).toHaveCount(0);
  await expect(page.getByRole('button', { name: DOWN })).toHaveCount(0);
  expect(writes).toEqual([]);
});
