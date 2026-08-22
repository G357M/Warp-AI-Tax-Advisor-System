import { expect, Page, test } from '@playwright/test';

type Lang = 'ru' | 'ka' | 'en';

const DESKTOP = { width: 1440, height: 900 };
const MOBILE = { width: 390, height: 844 };

const decisionStats = {
  coverage: {
    decisions_in_corpus: 12_184,
    decisions_extracted: 11_370,
    documents_total: 15_140,
  },
  overall: {
    total: 11_370,
    taxpayer_relief_rate: 0.274,
  },
  top_articles: [
    { article: '269', total: 841, taxpayer_relief_rate: 0.31 },
  ],
};

const laws = {
  laws: [
    {
      law_id: 'tax-code',
      title: 'Tax Code of Georgia — consolidated edition with all transitional provisions',
      amendments: 184,
      last_adoption: '2026-07-14',
    },
    {
      law_id: 'order-996',
      title: 'Order N996 on Tax Administration by the Minister of Finance of Georgia',
      amendments: 126,
      last_adoption: '2026-06-30',
    },
    {
      law_id: 'long-title',
      title:
        'Rules for determining the place of supply, documentary evidence and reporting obligations for cross-border digital services supplied through electronic platforms',
      amendments: 42,
      last_adoption: '2026-05-21',
    },
    {
      law_id: 'customs-code',
      title: 'Customs Code of Georgia',
      amendments: 37,
      last_adoption: '2026-04-09',
    },
    {
      law_id: 'international-tax',
      title: 'Instruction on international controlled transactions and transfer pricing documentation',
      amendments: 18,
      last_adoption: '2026-03-18',
    },
  ],
};

async function setLanguage(page: Page, lang: Lang) {
  await page.addInitScript((selectedLanguage) => {
    window.localStorage.setItem('ta_lang', selectedLanguage);
    window.localStorage.removeItem('ta_authenticated');
    window.localStorage.removeItem('ta_token');
  }, lang);
}

async function mockApi(page: Page) {
  await page.route('**/api/v1/analytics/decisions', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(decisionStats) }),
  );
  await page.route('**/api/v1/amendments/laws', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(laws) }),
  );
  await page.route('**/api/v1/guides/registry', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        published: '2026-08-01',
        source_url: 'https://www.rs.ge/LegalEntityTaxManuals',
        total: 0,
        active: 0,
        withdrawn: 0,
        sections: [],
      }),
    }),
  );
  await page.route('**/api/v1/auth/login', (route) =>
    route.fulfill({
      status: 401,
      contentType: 'application/json',
      body: JSON.stringify({ detail: 'Incorrect username or password' }),
    }),
  );
}

async function openStable(page: Page, path: string, lang: Lang) {
  await setLanguage(page, lang);
  await mockApi(page);
  await page.goto(path, { waitUntil: 'networkidle' });
  await expect(page.locator('html')).toHaveAttribute('lang', lang);
  await page.evaluate(async () => {
    await document.fonts.ready;
  });
}

async function expectNoHorizontalOverflow(page: Page) {
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  );
  expect(overflow).toBeLessThanOrEqual(0);
}

test('Russian landing page on desktop', async ({ page }) => {
  await page.setViewportSize(DESKTOP);
  await openStable(page, '/', 'ru');
  await expect(page.getByText('11 370').first()).toBeVisible();
  await expectNoHorizontalOverflow(page);
  await expect(page.locator('main')).toHaveScreenshot('home-ru-desktop.png');
});

test('Georgian landing page on mobile', async ({ page }) => {
  await page.setViewportSize(MOBILE);
  await openStable(page, '/', 'ka');
  await expect(page.getByText('11 370').first()).toBeVisible();
  await expectNoHorizontalOverflow(page);
  await expect(page.locator('main')).toHaveScreenshot('home-ka-mobile.png');
});

test('Georgian mobile navigation', async ({ page }) => {
  await page.setViewportSize(MOBILE);
  await openStable(page, '/', 'ka');
  await page.locator('header button[aria-expanded]').click();
  await expect(page.locator('header button[aria-expanded]')).toHaveAttribute('aria-expanded', 'true');
  await expectNoHorizontalOverflow(page);
  await expect(page).toHaveScreenshot('home-ka-mobile-menu.png');
});

test('English laws page with long legal titles', async ({ page }) => {
  await page.setViewportSize(DESKTOP);
  await openStable(page, '/laws', 'en');
  await expect(page.getByText('Tax Code of Georgia', { exact: false }).first()).toBeVisible();
  await expectNoHorizontalOverflow(page);
  await expect(page.locator('main')).toHaveScreenshot('laws-en-long-content.png');
});

test('Georgian guides empty state on mobile', async ({ page }) => {
  await page.setViewportSize(MOBILE);
  await openStable(page, '/guides', 'ka');
  await expect(page.getByText('ამ სახელით ვერაფერი მოიძებნა.')).toBeVisible();
  await expectNoHorizontalOverflow(page);
  await expect(page.locator('main')).toHaveScreenshot('guides-ka-empty-mobile.png');
});

test('Russian login credentials error', async ({ page }) => {
  await page.setViewportSize(DESKTOP);
  await openStable(page, '/login', 'ru');
  await page.locator('input[autocomplete="username"]').fill('visual-reviewer');
  await page.locator('input[autocomplete="current-password"]').fill('not-a-real-password');
  await page.getByRole('button', { name: 'Войти' }).click();
  await expect(page.getByText('Неверный логин или пароль.')).toBeVisible();
  await expectNoHorizontalOverflow(page);
  await expect(page.locator('main')).toHaveScreenshot('login-ru-error.png');
});

test('English invalid reset token on mobile', async ({ page }) => {
  await page.setViewportSize(MOBILE);
  await openStable(page, '/reset-password', 'en');
  await expect(page.getByText('The link is invalid or expired. Request a new one.', { exact: false })).toBeVisible();
  await expectNoHorizontalOverflow(page);
  await expect(page.locator('main')).toHaveScreenshot('reset-en-invalid-mobile.png');
});
