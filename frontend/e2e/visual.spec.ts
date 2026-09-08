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

const billingCatalog = {
  version: '2026-09-08',
  terms_version: '2026-09-08',
  legal_urls: {
    terms: '/legal/terms', refunds: '/legal/refunds', privacy: '/legal/privacy',
    delivery: '/legal/delivery', contact: '/legal/contact',
  },
  currency_minor_unit: 2,
  plans: [
    {
      id: 'free', name: 'Free', price_minor: 0, currency: 'GEL', billing_period: null,
      daily_questions: 5, history_enabled: false,
      feature_codes: ['daily_questions_5', 'precise_sources', 'no_chat_history'],
      highlighted: false, pricing_preliminary: false,
    },
    {
      id: 'pro', name: 'Pro', price_minor: 4900, currency: 'GEL', billing_period: '30_days',
      daily_questions: null, history_enabled: true,
      feature_codes: ['unlimited_questions', 'chat_history', 'dispute_statistics', 'law_change_timeline'],
      highlighted: true, pricing_preliminary: false,
    },
    {
      id: 'business', name: 'Business', price_minor: 14900, currency: 'GEL', billing_period: '30_days',
      daily_questions: null, history_enabled: true,
      feature_codes: ['everything_in_pro', 'company_invoice', 'priority_support'],
      highlighted: false, pricing_preliminary: false,
    },
  ],
  payment_methods: [
    {
      id: 'manual_invoice', provider: 'manual', status: 'available', recurring: false,
      contact_email: 'billing@tax-advisor.ge',
    },
    {
      id: 'tbc_checkout', provider: 'tbc', status: 'requires_merchant_activation', recurring: false,
      contact_email: null,
    },
    {
      id: 'bog_checkout', provider: 'bog', status: 'requires_merchant_activation', recurring: true,
      contact_email: null,
    },
  ],
};

const billingOverview = {
  subscription: {
    plan: 'pro', status: 'active', period_start: '2026-09-01T00:00:00',
    period_end: '2026-10-01T00:00:00', auto_renew: false, payment_provider: 'manual',
  },
  checkouts: [
    {
      id: '8e8bba4e-9638-45f0-9062-ff2bd4f3f953', plan: 'business', months: 1,
      amount_minor: 14900, currency: 'GEL', provider: 'manual', status: 'pending',
      expires_at: '2026-09-14T10:00:00', created_at: '2026-09-07T10:00:00',
    },
  ],
  payments: [
    {
      id: '0c88b35e-97df-4949-b311-8101b622a7f2', amount_minor: 4900,
      currency: 'GEL', provider: 'manual', status: 'succeeded', created_at: '2026-09-01T10:30:00',
    },
  ],
  payment_methods: billingCatalog.payment_methods,
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
  await page.route('**/api/v1/billing/catalog', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(billingCatalog) }),
  );
}

async function openAccountStable(page: Page, lang: Lang) {
  await page.addInitScript((selectedLanguage) => {
    window.localStorage.setItem('ta_lang', selectedLanguage);
    window.localStorage.setItem('ta_authenticated', '1');
    window.localStorage.removeItem('ta_token');
  }, lang);
  await mockApi(page);
  await page.route('**/api/v1/account', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        email: 'nino.beridze@example.ge', username: 'nino.beridze', full_name: 'Nino Beridze',
        role: 'user', plan: 'pro', usage: { questions_today: 12, daily_limit: null },
      }),
    }),
  );
  await page.route('**/api/v1/billing/overview', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(billingOverview) }),
  );
  await page.route('**/api/v1/query/conversations?limit=20', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([
        {
          id: 'e8477029-7b13-49cb-bda1-5248adf553ba',
          title: 'НДС при оказании услуг нерезиденту',
          created_at: '2026-09-03T09:00:00', updated_at: '2026-09-05T14:30:00', messages_count: 6,
        },
        {
          id: '07f8973f-f340-4fb4-9c4d-018d1461fb2c',
          title: 'Срок обжалования решения налоговой',
          created_at: '2026-08-27T11:00:00', updated_at: '2026-08-27T11:20:00', messages_count: 4,
        },
      ]),
    }),
  );
  await page.goto('/account', { waitUntil: 'networkidle' });
  await expect(page.locator('html')).toHaveAttribute('lang', lang);
  await page.evaluate(async () => {
    await document.fonts.ready;
  });
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

test('grounded answer exposes a direct official article link', async ({ page }) => {
  await page.setViewportSize(DESKTOP);
  await page.route('**/api/v1/public/query', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        response: 'Стандартная ставка НДС в Грузии — 18%.',
        sources: [
          {
            title: 'საქართველოს საგადასახადო კოდექსი',
            document_type: 'law',
            url: 'https://infohub.rs.ge/ka/workspace/document/800cbef0-32bf-4f06-94fe-8afd2bf144a0',
            relevance: 1,
            article_ref: '166',
            official_act_url: 'https://matsne.gov.ge/ka/document/view/1043717',
            provision_links: [
              {
                article_ref: '166',
                point_ref: null,
                url: 'https://matsne.gov.ge/ka/document/view/1043717#part_553',
              },
            ],
          },
        ],
        evidence: {
          status: 'grounded',
          basis: 'authoritative',
          coverage: 'exact_provision',
          question_class: 'canonical_law_lookup',
          source_count: 1,
          official_sources_only: true,
          has_precise_citation: true,
          has_official_provision_link: true,
          generated_at: '2026-08-24T00:00:00+00:00',
        },
        conversation_id: '00000000-0000-0000-0000-000000000000',
        retrieved_count: 1,
      }),
    }),
  );
  await openStable(page, '/', 'ru');
  await page.getByRole('button', { name: 'Какая ставка НДС в Грузии?' }).click();

  const provision = page.getByRole('link', { name: 'ст. 166', exact: true });
  await expect(provision).toHaveAttribute(
    'href',
    'https://matsne.gov.ge/ka/document/view/1043717#part_553',
  );
  await expect(page.getByRole('link', { name: 'Официальный акт', exact: true })).toHaveAttribute(
    'href',
    'https://matsne.gov.ge/ka/document/view/1043717',
  );
  await expect(page.getByText('доступна прямая ссылка')).toBeVisible();
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

test('Russian client billing center on desktop', async ({ page }) => {
  await page.setViewportSize(DESKTOP);
  await openAccountStable(page, 'ru');
  await expect(page.getByRole('heading', { name: 'Способы оплаты' })).toBeVisible();
  await expect(page.getByText('8e8bba4e-9638-45f0-9062-ff2bd4f3f953')).toBeVisible();
  await expectNoHorizontalOverflow(page);
  await expect(page.locator('main')).toHaveScreenshot('account-billing-ru-desktop.png');
});

test('Georgian client billing center on mobile', async ({ page }) => {
  await page.setViewportSize(MOBILE);
  await openAccountStable(page, 'ka');
  await expect(page.getByRole('heading', { name: 'გადახდის მეთოდები' })).toBeVisible();
  await expectNoHorizontalOverflow(page);
  await expect(page.locator('main')).toHaveScreenshot('account-billing-ka-mobile.png');
});

test('paid checkout requires both confirmations and sends the current terms version', async ({ page }) => {
  await page.setViewportSize(DESKTOP);
  let requestBody: Record<string, unknown> | null = null;
  await page.route('**/api/v1/billing/checkout', async (route) => {
    requestBody = route.request().postDataJSON();
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        checkout: {
          id: '18d09f2b-5a5e-4a34-939a-c75f3652cbfa', plan: 'business', months: 1,
          amount_minor: 14900, currency: 'GEL', provider: 'manual', status: 'pending',
          provider_status: null, provider_redirect_url: null, provider_checked_at: null,
          terms_version: '2026-09-08', terms_accepted_at: '2026-09-08T00:00:00',
          immediate_service_requested_at: '2026-09-08T00:00:00',
          expires_at: '2026-09-15T00:00:00', created_at: '2026-09-08T00:00:00',
        },
        payment_method: {
          id: 'manual_invoice', provider: 'manual', status: 'available', recurring: false,
          contact_email: 'billing@tax-advisor.ge', instruction_code: 'contact_for_invoice',
        },
        replayed: false,
      }),
    });
  });
  await openAccountStable(page, 'en');

  const payButton = page.getByRole('button', { name: 'Pay for Business — 149 ₾' });
  await expect(payButton).toBeDisabled();
  await page.getByRole('checkbox', { name: /I accept the Terms of use/ }).check();
  await expect(payButton).toBeDisabled();
  await page.getByRole('checkbox', { name: /I request the digital service/ }).check();
  await expect(payButton).toBeEnabled();
  await payButton.click();

  expect(requestBody).toMatchObject({
    plan: 'business',
    provider: 'manual',
    language: 'en',
    terms_version: '2026-09-08',
    terms_accepted: true,
    immediate_service_requested: true,
  });
});

test('Russian refund policy on desktop', async ({ page }) => {
  await page.setViewportSize(DESKTOP);
  await openStable(page, '/legal/refunds', 'ru');
  await expect(page.getByRole('heading', { name: 'Возврат и отмена', level: 1 })).toBeVisible();
  await expect(page.getByText('14-дневное право на отказ', { exact: false })).toBeVisible();
  await expectNoHorizontalOverflow(page);
  await expect(page.locator('main')).toHaveScreenshot('legal-refunds-ru-desktop.png');
});

test('Georgian terms on mobile', async ({ page }) => {
  await page.setViewportSize(MOBILE);
  await openStable(page, '/legal/terms', 'ka');
  await expect(page.getByRole('heading', { name: 'გამოყენების პირობები', level: 1 })).toBeVisible();
  await expect(page.locator('main').getByText('Modern LLC · 431177120')).toBeVisible();
  await expectNoHorizontalOverflow(page);
  await expect(page.locator('main')).toHaveScreenshot('legal-terms-ka-mobile.png');
});

test('TBC return verifies the bank once and activates the subscription', async ({ page }) => {
  const checkoutId = '615bfb5e-a87c-4d27-9709-7ca8ee1ce313';
  const pendingCheckout = {
    id: checkoutId,
    plan: 'pro',
    months: 1,
    amount_minor: 4900,
    currency: 'GEL',
    provider: 'tbc',
    status: 'pending',
    provider_status: 'Processing',
    provider_redirect_url: 'https://tpay.tbcbank.ge/payments/615bfb5e-a87c-4d27-9709-7ca8ee1ce313',
    provider_checked_at: null,
    expires_at: '2026-09-07T10:12:00',
    created_at: '2026-09-07T10:00:00',
  };
  const paidCheckout = {
    ...pendingCheckout,
    status: 'paid',
    provider_status: 'Succeeded',
    provider_checked_at: '2026-09-07T10:04:00',
  };
  let overviewRequests = 0;
  let refreshRequests = 0;

  await page.addInitScript(() => {
    window.localStorage.setItem('ta_lang', 'en');
    window.localStorage.setItem('ta_authenticated', '1');
    window.localStorage.removeItem('ta_token');
  });
  await mockApi(page);
  await page.route('**/api/v1/billing/catalog', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        ...billingCatalog,
        payment_methods: billingCatalog.payment_methods.map((method) =>
          method.provider === 'tbc'
            ? { ...method, status: 'available', recurring: false }
            : method,
        ),
      }),
    }),
  );
  await page.route('**/api/v1/account', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        email: 'nino.beridze@example.ge',
        username: 'nino.beridze',
        full_name: 'Nino Beridze',
        role: 'user',
        plan: 'free',
        usage: { questions_today: 0, daily_limit: 5 },
      }),
    }),
  );
  await page.route('**/api/v1/billing/overview', (route) => {
    overviewRequests += 1;
    const settled = overviewRequests > 1;
    return route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        subscription: settled
          ? {
              plan: 'pro', status: 'active', period_start: '2026-09-07T10:04:00',
              period_end: '2026-10-07T10:04:00', auto_renew: false, payment_provider: 'tbc',
            }
          : {
              plan: 'free', status: null, period_start: null, period_end: null,
              auto_renew: false, payment_provider: null,
            },
        checkouts: [settled ? paidCheckout : pendingCheckout],
        payments: settled
          ? [{
              id: 'fee4f6b4-4db7-4bb7-b52f-e1261c253521', amount_minor: 4900,
              currency: 'GEL', provider: 'tbc', status: 'succeeded',
              created_at: '2026-09-07T10:04:00',
            }]
          : [],
        payment_methods: billingCatalog.payment_methods.map((method) =>
          method.provider === 'tbc'
            ? { ...method, status: 'available', recurring: false }
            : method,
        ),
      }),
    });
  });
  await page.route(`**/api/v1/billing/checkout/${checkoutId}/refresh`, (route) => {
    refreshRequests += 1;
    return route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ checkout: paidCheckout }),
    });
  });

  await page.goto(`/account?payment_return=tbc&checkout_id=${checkoutId}`, { waitUntil: 'networkidle' });

  await expect(page.getByText('Payment confirmed and subscription activated.')).toBeVisible();
  await expect(page).toHaveURL(/\/account$/);
  expect(refreshRequests).toBe(1);
  expect(overviewRequests).toBe(2);
});
