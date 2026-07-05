'use client';

/**
 * Site-wide localization (ru / ka / en).
 *
 * The language picked in the header drives both the UI strings and the
 * answer language of the chat. Stored in localStorage, synced across
 * components via the 'ta-lang-changed' event.
 */
import { useEffect, useState } from 'react';

export type Lang = 'ru' | 'ka' | 'en';

const LANG_KEY = 'ta_lang';

export function getLang(): Lang {
  if (typeof window === 'undefined') return 'ru';
  const v = localStorage.getItem(LANG_KEY);
  return v === 'ka' || v === 'en' ? v : 'ru';
}

export function setLang(lang: Lang) {
  localStorage.setItem(LANG_KEY, lang);
  window.dispatchEvent(new Event('ta-lang-changed'));
}

export function useLang(): Lang {
  const [lang, set] = useState<Lang>('ru');
  useEffect(() => {
    const sync = () => set(getLang());
    sync();
    window.addEventListener('ta-lang-changed', sync);
    window.addEventListener('storage', sync);
    return () => {
      window.removeEventListener('ta-lang-changed', sync);
      window.removeEventListener('storage', sync);
    };
  }, []);
  return lang;
}

type Entry = { ru: string; ka: string; en: string };

const DICT: Record<string, Entry> = {
  // Header / footer
  'nav.chat': { ru: 'Чат', ka: 'ჩატი', en: 'Chat' },
  'nav.laws': { ru: 'Законы', ka: 'კანონმდებლობა', en: 'Laws' },
  'nav.guides': { ru: 'Руководства', ka: 'სახელმძღვანელოები', en: 'Guides' },
  'nav.stats': { ru: 'Статистика решений', ka: 'დავების სტატისტიკა', en: 'Dispute statistics' },
  'nav.pricing': { ru: 'Тарифы', ka: 'ტარიფები', en: 'Pricing' },
  'nav.login': { ru: 'Войти', ka: 'შესვლა', en: 'Sign in' },
  'nav.account': { ru: 'Кабинет', ka: 'კაბინეტი', en: 'Account' },
  'footer.disclaimer': {
    ru: 'Ответы строятся только на официальной базе: Налоговый кодекс Грузии, подзаконные акты, решения советов по рассмотрению споров. Сервис носит информационный характер и не заменяет юридическую консультацию.',
    ka: 'პასუხები ეყრდნობა მხოლოდ ოფიციალურ ბაზას: საქართველოს საგადასახადო კოდექსი, კანონქვემდებარე აქტები, დავების განხილვის საბჭოების გადაწყვეტილებები. სერვისი საინფორმაციო ხასიათისაა და არ ცვლის იურიდიულ კონსულტაციას.',
    en: 'Answers rest solely on the official database: the Georgian Tax Code, secondary legislation and dispute-council decisions. The service is informational and does not replace legal advice.',
  },
  'footer.source': { ru: 'Источник данных: infohub.rs.ge', ka: 'მონაცემთა წყარო: infohub.rs.ge', en: 'Data source: infohub.rs.ge' },

  // Hero
  'hero.eyebrow': { ru: 'Официальная база · {n} документов', ka: 'ოფიციალური ბაზა · {n} დოკუმენტი', en: 'Official database · {n} documents' },
  'hero.eyebrow0': { ru: 'Официальная база документов Грузии', ka: 'საქართველოს ოფიციალური დოკუმენტების ბაზა', en: 'Georgia’s official document base' },
  'hero.title1': { ru: 'Налоговое право Грузии.', ka: 'საქართველოს საგადასახადო სამართალი.', en: 'Georgian tax law.' },
  'hero.title2': { ru: 'С точными источниками.', ka: 'ზუსტი წყაროებით.', en: 'With precise sources.' },
  'hero.sub': {
    ru: 'Ответы строго по официальной базе: Налоговый кодекс, подзаконные акты, решения советов по спорам — и статистика их исходов.',
    ka: 'პასუხები მკაცრად ოფიციალური ბაზიდან: საგადასახადო კოდექსი, კანონქვემდებარე აქტები, დავების საბჭოების გადაწყვეტილებები — და მათი შედეგების სტატისტიკა.',
    en: 'Answers strictly from the official database: the Tax Code, secondary acts, dispute-council decisions — and outcome statistics.',
  },

  // Chat
  'chat.placeholder': { ru: 'Спросите о налогах Грузии…', ka: 'ჰკითხეთ საქართველოს გადასახადებზე…', en: 'Ask about Georgian taxes…' },
  'chat.ask': { ru: 'Спросить', ka: 'კითხვა', en: 'Ask' },
  'chat.asking': { ru: 'Ищу…', ka: 'ვეძებ…', en: 'Searching…' },
  'chat.question': { ru: 'Вопрос:', ka: 'კითხვა:', en: 'Question:' },
  'chat.searching': { ru: 'Ищу ответ в официальной базе…', ka: 'ვეძებ პასუხს ოფიციალურ ბაზაში…', en: 'Searching the official database…' },
  'chat.error': { ru: 'Не получилось получить ответ:', ka: 'პასუხის მიღება ვერ მოხერხდა:', en: 'Could not get an answer:' },
  'chat.retry': { ru: 'Попробуйте ещё раз.', ka: 'სცადეთ თავიდან.', en: 'Please try again.' },
  'chat.sources': { ru: 'Источники', ka: 'წყაროები', en: 'Sources' },
  'chat.ex1': { ru: 'Какая ставка НДС в Грузии?', ka: 'რა არის დღგ-ის განაკვეთი საქართველოში?', en: 'What is the VAT rate in Georgia?' },
  'chat.ex2': { ru: 'Может ли ООО применять налог 1%?', ka: 'შეუძლია თუ არა შპს-ს 1%-იანი გადასახადი?', en: 'Can an LLC use the 1% tax regime?' },
  'chat.ex3': { ru: 'Как обжаловать решение налоговой?', ka: 'როგორ გავასაჩივრო საგადასახადოს გადაწყვეტილება?', en: 'How do I appeal a tax decision?' },

  // How it works
  'steps.title': { ru: 'Как это работает', ka: 'როგორ მუშაობს', en: 'How it works' },
  'steps.1.title': { ru: 'Вопрос', ka: 'კითხვა', en: 'Question' },
  'steps.1.text': {
    ru: 'Задайте вопрос на русском, грузинском или английском — о ставках, режимах, спорах.',
    ka: 'დასვით კითხვა ქართულად, რუსულად ან ინგლისურად — განაკვეთებზე, რეჟიმებზე, დავებზე.',
    en: 'Ask in Georgian, Russian or English — about rates, regimes, disputes.',
  },
  'steps.2.title': { ru: 'Поиск по официальной базе', ka: 'ძიება ოფიციალურ ბაზაში', en: 'Official-database search' },
  'steps.2.text': {
    ru: 'Система ищет только в официальных документах: кодексы, приказы, решения советов по спорам.',
    ka: 'სისტემა ეძებს მხოლოდ ოფიციალურ დოკუმენტებში: კოდექსები, ბრძანებები, დავების საბჭოების გადაწყვეტილებები.',
    en: 'The system searches only official documents: codes, orders, dispute-council decisions.',
  },
  'steps.3.title': { ru: 'Ответ с цитатой', ka: 'პასუხი ციტატით', en: 'Answer with a citation' },
  'steps.3.text': {
    ru: 'Каждый ответ сопровождается точным источником — вплоть до статьи закона. Если ответа в базе нет, система честно говорит об этом.',
    ka: 'ყოველ პასუხს ახლავს ზუსტი წყარო — კანონის მუხლამდე. თუ ბაზაში პასუხი არ არის, სისტემა ამას პირდაპირ ამბობს.',
    en: 'Every answer carries a precise source — down to the article. When the base has no answer, the system says so honestly.',
  },

  // Stats section
  'stats.title': { ru: 'Статистика налоговых споров', ka: 'საგადასახადო დავების სტატისტიკა', en: 'Tax dispute statistics' },
  'stats.sub': {
    ru: 'Мы разобрали решения советов по рассмотрению споров Службы доходов и Минфина и посчитали, как они заканчиваются — чтобы вы могли трезво оценить свою стратегию.',
    ka: 'გავაანალიზეთ შემოსავლების სამსახურისა და ფინანსთა სამინისტროს დავების საბჭოების გადაწყვეტილებები და დავთვალეთ მათი შედეგები — რომ თქვენი სტრატეგია რეალურად შეაფასოთ.',
    en: 'We parsed the Revenue Service and MoF dispute-council decisions and counted how they end — so you can judge your strategy soberly.',
  },
  'stats.analyzed': { ru: 'Решений проанализировано', ka: 'გაანალიზებული გადაწყვეტილება', en: 'Decisions analyzed' },
  'stats.of': { ru: 'из {n} в базе', ka: '{n}-დან ბაზაში', en: 'of {n} in the base' },
  'stats.relief': { ru: 'Жалоб получают облегчение', ka: 'საჩივრები კმაყოფილდება', en: 'Complaints get relief' },
  'stats.relief_detail': { ru: 'полное или частичное удовлетворение', ka: 'სრულად ან ნაწილობრივ', en: 'full or partial satisfaction' },
  'stats.top_article': { ru: 'Самая спорная статья НК', ka: 'ყველაზე სადავო მუხლი', en: 'Most contested article' },
  'stats.decisions': { ru: '{n} решений', ka: '{n} გადაწყვეტილება', en: '{n} decisions' },
  'stats.art': { ru: 'ст. {n}', ka: 'მუხ. {n}', en: 'art. {n}' },

  // Pricing
  'pricing.title': { ru: 'Тарифы', ka: 'ტარიფები', en: 'Pricing' },
  'pricing.month': { ru: '/мес', ka: '/თვე', en: '/mo' },
  'pricing.free_cta': { ru: 'Начать бесплатно', ka: 'დაიწყეთ უფასოდ', en: 'Start free' },
  'pricing.paid_cta': { ru: 'Скоро — начните с Free', ka: 'მალე — დაიწყეთ Free-ით', en: 'Soon — start with Free' },
  'pricing.note': {
    ru: 'Подписки Pro и Business откроются вместе с личным кабинетом. Цены предварительные.',
    ka: 'Pro და Business გამოწერები მალე გაიხსნება. ფასები წინასწარია.',
    en: 'Pro and Business subscriptions open soon. Prices are preliminary.',
  },
  'plan.free.tagline': { ru: 'Познакомиться с сервисом', ka: 'სერვისის გასაცნობად', en: 'Get to know the service' },
  'plan.free.f1': { ru: '5 вопросов в день', ka: '5 კითხვა დღეში', en: '5 questions a day' },
  'plan.free.f2': { ru: 'Ответы с точными источниками', ka: 'პასუხები ზუსტი წყაროებით', en: 'Answers with precise sources' },
  'plan.free.f3': { ru: 'Без истории диалогов', ka: 'დიალოგების ისტორიის გარეშე', en: 'No chat history' },
  'plan.pro.tagline': { ru: 'Для бухгалтера и предпринимателя', ka: 'ბუღალტრისა და მეწარმისთვის', en: 'For accountants and entrepreneurs' },
  'plan.pro.f1': { ru: 'Вопросы без ограничений', ka: 'შეუზღუდავი კითხვები', en: 'Unlimited questions' },
  'plan.pro.f2': { ru: 'История диалогов', ka: 'დიალოგების ისტორია', en: 'Chat history' },
  'plan.pro.f3': { ru: 'Статистика решений по спорам', ka: 'დავების გადაწყვეტილებების სტატისტიკა', en: 'Dispute outcome statistics' },
  'plan.pro.f4': { ru: 'Таймлайн изменений законов', ka: 'კანონმდებლობის ცვლილებების ქრონოლოგია', en: 'Law-change timeline' },
  'plan.business.tagline': { ru: 'Для компании и консалтинга', ka: 'კომპანიისა და საკონსულტაციო ფირმისთვის', en: 'For companies and consultancies' },
  'plan.business.f1': { ru: 'Всё из Pro', ka: 'ყველაფერი Pro-დან', en: 'Everything in Pro' },
  'plan.business.f2': { ru: 'До 5 пользователей', ka: '5-მდე მომხმარებელი', en: 'Up to 5 users' },
  'plan.business.f3': { ru: 'Приоритетная поддержка', ka: 'პრიორიტეტული მხარდაჭერა', en: 'Priority support' },

  // Laws list
  'laws.title': { ru: 'Изменения законодательства', ka: 'კანონმდებლობის ცვლილებები', en: 'Legislation changes' },
  'laws.sub': {
    ru: 'Хронология поправок к законам Грузии и подзаконным актам — включая приказы Минфина (например, №996 об администрировании налогов): когда принята, когда вступила в силу, какие статьи затронула и что изменилось по существу.',
    ka: 'საქართველოს კანონებისა და კანონქვემდებარე აქტების ცვლილებების ქრონოლოგია — მათ შორის ფინანსთა მინისტრის ბრძანებები (მაგ. №996 გადასახადების ადმინისტრირებაზე): როდის მიიღეს, როდის ამოქმედდა, რომელი მუხლები შეიცვალა და რა შეიცვალა არსებითად.',
    en: 'A chronology of amendments to Georgian laws and secondary acts — including MoF orders (e.g. №996 on tax administration): when adopted, when in force, which articles changed and what changed in substance.',
  },
  'laws.search': { ru: 'Найти закон или приказ…', ka: 'იპოვეთ კანონი ან ბრძანება…', en: 'Find a law or order…' },
  'laws.featured': { ru: 'Чаще всего меняются', ka: 'ყველაზე ხშირად იცვლება', en: 'Most frequently amended' },
  'laws.last': { ru: 'последняя поправка — {d}', ka: 'ბოლო ცვლილება — {d}', en: 'last amendment — {d}' },
  'laws.amendments': { ru: '{n} поправок', ka: '{n} ცვლილება', en: '{n} amendments' },
  'laws.loading': { ru: 'Загружаю…', ka: 'იტვირთება…', en: 'Loading…' },
  'laws.error': { ru: 'Не получилось загрузить. Обновите страницу.', ka: 'ჩატვირთვა ვერ მოხერხდა. განაახლეთ გვერდი.', en: 'Failed to load. Refresh the page.' },
  'laws.empty': { ru: 'Поправки ещё обрабатываются — загляните позже.', ka: 'ცვლილებები ჯერ მუშავდება — შემოიარეთ მოგვიანებით.', en: 'Amendments are still being processed — check back later.' },
  'laws.nomatch': { ru: 'Ничего не нашлось по этому названию.', ka: 'ამ სახელით ვერაფერი მოიძებნა.', en: 'Nothing matches that name.' },

  // Timeline
  'tl.back': { ru: '← Все законы', ka: '← ყველა აქტი', en: '← All acts' },
  'tl.filter': { ru: 'Фильтр по статье, напр. 165', ka: 'ფილტრი მუხლით, მაგ. 165', en: 'Filter by article, e.g. 165' },
  'tl.count': { ru: '{n} поправок', ka: '{n} ცვლილება', en: '{n} amendments' },
  'tl.count_art': { ru: '{n} поправок к ст. {a}', ka: '{n} ცვლილება {a}-ე მუხლზე', en: '{n} amendments to art. {a}' },
  'tl.adopted': { ru: 'принята {d}', ka: 'მიღებულია {d}', en: 'adopted {d}' },
  'tl.effective': { ru: 'вступила {d}', ka: 'ამოქმედდა {d}', en: 'in force {d}' },
  'tl.in_force': { ru: 'действует', ka: 'მოქმედი', en: 'in force' },
  'tl.not_yet': { ru: 'ещё не вступила', ka: 'ჯერ არ ამოქმედებულა', en: 'not yet in force' },
  'tl.unknown': { ru: 'дата вступления не указана', ka: 'ამოქმედების თარიღი უცნობია', en: 'entry date not stated' },
  'tl.art': { ru: 'ст. {n}', ka: 'მუხლი {n}', en: 'art. {n}' },
  'tl.amended': { ru: 'изменена', ka: 'შეიცვალა', en: 'amended' },
  'tl.added': { ru: 'добавлена', ka: 'დაემატა', en: 'added' },
  'tl.repealed': { ru: 'отменена', ka: 'გაუქმდა', en: 'repealed' },
  'tl.was': { ru: 'Было:', ka: 'იყო:', en: 'Was:' },
  'tl.became': { ru: 'Стало:', ka: 'გახდა:', en: 'Now:' },
  'tl.none_art': { ru: 'Поправок к статье {a} в базе не найдено.', ka: '{a}-ე მუხლზე ცვლილებები ბაზაში არ მოიძებნა.', en: 'No amendments to article {a} found.' },
  'tl.none': { ru: 'Поправки к этому закону ещё обрабатываются.', ka: 'ამ აქტის ცვლილებები ჯერ მუშავდება.', en: 'Amendments to this act are still being processed.' },
  'tl.note_ru': {
    ru: '',
    ka: 'ცვლილებების შინაარსობრივი შეჯამებები ამ ეტაპზე რუსულადაა.',
    en: 'Substance summaries of amendments are currently in Russian.',
  },

  // Situational guides
  'guides.title': { ru: 'Ситуационные руководства', ka: 'სიტუაციური სახელმძღვანელოები', en: 'Situational guides' },
  'guides.sub': {
    ru: 'Пошаговые разъяснения Службы доходов по конкретным налоговым ситуациям — от НДС на рекламу нерезидента до вычета нематериальных активов. Каждое руководство открывается в первоисточнике.',
    ka: 'შემოსავლების სამსახურის ეტაპობრივი განმარტებები კონკრეტულ საგადასახადო სიტუაციებზე — არარეზიდენტის რეკლამის დღგ-დან არამატერიალური აქტივების გამოქვითვამდე. თითოეული იხსნება პირველწყაროში.',
    en: 'Step-by-step Revenue Service explanations for specific tax situations — from VAT on non-resident advertising to intangible asset deductions. Each guide opens at the official source.',
  },
  'guides.search': { ru: 'Найти руководство…', ka: 'იპოვეთ სახელმძღვანელო…', en: 'Find a guide…' },
  'guides.total': { ru: 'всего: {n}', ka: 'სულ: {n}', en: 'total: {n}' },

  // Auth & account
  'auth.login': { ru: 'Вход', ka: 'შესვლა', en: 'Sign in' },
  'auth.username': { ru: 'Логин', ka: 'მომხმარებელი', en: 'Username' },
  'auth.password': { ru: 'Пароль', ka: 'პაროლი', en: 'Password' },
  'auth.signin': { ru: 'Войти', ka: 'შესვლა', en: 'Sign in' },
  'auth.signing': { ru: 'Вхожу…', ka: 'შესვლა…', en: 'Signing in…' },
  'auth.noaccount': { ru: 'Нет аккаунта?', ka: 'არ გაქვთ ანგარიში?', en: 'No account?' },
  'auth.createfree': { ru: 'Создать бесплатно', ka: 'შექმენით უფასოდ', en: 'Create one free' },
  'reg.title': { ru: 'Регистрация', ka: 'რეგისტრაცია', en: 'Sign up' },
  'reg.sub': { ru: 'Бесплатный тариф: 5 вопросов в день с точными источниками.', ka: 'უფასო ტარიფი: 5 კითხვა დღეში ზუსტი წყაროებით.', en: 'Free plan: 5 questions a day with precise sources.' },
  'reg.username': { ru: 'Логин (от 3 символов)', ka: 'მომხმარებელი (მინ. 3 სიმბოლო)', en: 'Username (3+ characters)' },
  'reg.password': { ru: 'Пароль (минимум 8 символов)', ka: 'პაროლი (მინ. 8 სიმბოლო)', en: 'Password (8+ characters)' },
  'reg.pwshort': { ru: 'Пароль — минимум 8 символов.', ka: 'პაროლი — მინიმუმ 8 სიმბოლო.', en: 'Password must be 8+ characters.' },
  'reg.create': { ru: 'Создать аккаунт', ka: 'ანგარიშის შექმნა', en: 'Create account' },
  'reg.creating': { ru: 'Создаю…', ka: 'იქმნება…', en: 'Creating…' },
  'reg.have': { ru: 'Уже есть аккаунт?', ka: 'უკვე გაქვთ ანგარიში?', en: 'Already have an account?' },
  'acc.title': { ru: 'Кабинет', ka: 'კაბინეტი', en: 'Account' },
  'acc.admin': { ru: 'Админпанель', ka: 'ადმინპანელი', en: 'Admin panel' },
  'acc.logout': { ru: 'Выйти', ka: 'გასვლა', en: 'Sign out' },
  'acc.plan': { ru: 'Тариф', ka: 'ტარიფი', en: 'Plan' },
  'acc.until': { ru: 'действует до {d}', ka: 'მოქმედებს {d}-მდე', en: 'active until {d}' },
  'acc.upgrade_pro': { ru: 'Перейти на Pro', ka: 'Pro-ზე გადასვლა', en: 'Upgrade to Pro' },
  'acc.today': { ru: 'Вопросы сегодня', ka: 'დღევანდელი კითხვები', en: 'Questions today' },
  'acc.of': { ru: 'из {n}', ka: '{n}-დან', en: 'of {n}' },
  'acc.unlimited': { ru: 'без ограничений', ka: 'შეუზღუდავად', en: 'unlimited' },
  'acc.laws_hint': { ru: 'Хронология изменений законов — в разделе', ka: 'კანონმდებლობის ცვლილებების ქრონოლოგია — განყოფილებაში', en: 'The law-change timeline lives in' },
  'acc.loading': { ru: 'Загружаю…', ka: 'იტვირთება…', en: 'Loading…' },
};

export function translate(lang: Lang, key: string, vars?: Record<string, string | number>): string {
  const entry = DICT[key];
  let text = entry ? entry[lang] || entry.ru : key;
  if (vars) {
    for (const [k, v] of Object.entries(vars)) {
      text = text.replace(`{${k}}`, String(v));
    }
  }
  return text;
}

export function useT() {
  const lang = useLang();
  return {
    lang,
    t: (key: string, vars?: Record<string, string | number>) => translate(lang, key, vars),
  };
}

export const DATE_LOCALES: Record<Lang, string> = { ru: 'ru-RU', ka: 'ka-GE', en: 'en-GB' };
