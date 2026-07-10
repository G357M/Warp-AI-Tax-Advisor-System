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

/**
 * The document shell must follow the UI language: screen readers pick the
 * pronunciation from <html lang>, and the tab title is the product's face.
 */
function applyDocumentLang(lang: Lang) {
  document.documentElement.lang = lang;
  document.title = translate(lang, 'meta.title');
  document
    .querySelector('meta[name="description"]')
    ?.setAttribute('content', translate(lang, 'meta.desc'));
}

export function useLang(): Lang {
  const [lang, set] = useState<Lang>('ru');
  useEffect(() => {
    const sync = () => {
      const l = getLang();
      set(l);
      applyDocumentLang(l);
    };
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
  // Document shell
  'meta.title': {
    ru: 'Tax Advisor — налоговое право Грузии с точными источниками',
    ka: 'Tax Advisor — საქართველოს საგადასახადო სამართალი ზუსტი წყაროებით',
    en: 'Tax Advisor — Georgian tax law with exact sources',
  },
  'meta.desc': {
    ru: 'Ответы по налоговому праву Грузии строго по официальной базе: Налоговый кодекс, решения советов по спорам, статистика исходов.',
    ka: 'პასუხები საქართველოს საგადასახადო სამართალზე მხოლოდ ოფიციალური ბაზიდან: საგადასახადო კოდექსი, დავების საბჭოების გადაწყვეტილებები, შედეგების სტატისტიკა.',
    en: 'Answers on Georgian tax law strictly from the official base: the Tax Code, dispute-council decisions, outcome statistics.',
  },

  // Header / footer
  'nav.chat': { ru: 'Чат', ka: 'ჩატი', en: 'Chat' },
  'nav.laws': { ru: 'Законы', ka: 'კანონები', en: 'Laws' },
  'nav.guides': { ru: 'Руководства', ka: 'სახელმძღვანელოები', en: 'Guides' },
  'nav.news': { ru: 'Новости', ka: 'სიახლეები', en: 'News' },
  'nav.stats': { ru: 'Статистика решений', ka: 'სტატისტიკა', en: 'Dispute statistics' },
  'nav.pricing': { ru: 'Тарифы', ka: 'ტარიფები', en: 'Pricing' },
  'nav.menu': { ru: 'Меню', ka: 'მენიუ', en: 'Menu' },
  'nav.login': { ru: 'Войти', ka: 'შესვლა', en: 'Sign in' },
  'nav.account': { ru: 'Кабинет', ka: 'კაბინეტი', en: 'Account' },
  'footer.disclaimer': {
    ru: 'Ответы строятся только на официальной базе: Налоговый кодекс Грузии, подзаконные акты, решения советов по рассмотрению споров. Сервис носит информационный характер и не заменяет юридическую консультацию.',
    ka: 'პასუხები ეყრდნობა მხოლოდ ოფიციალურ ბაზას: საქართველოს საგადასახადო კოდექსი, კანონქვემდებარე აქტები, დავების განხილვის საბჭოების გადაწყვეტილებები. სერვისი საინფორმაციო ხასიათისაა და არ ცვლის იურიდიულ კონსულტაციას.',
    en: 'Answers rest solely on the official database: the Georgian Tax Code, secondary legislation and dispute-council decisions. The service is informational and does not replace legal advice.',
  },
  'footer.source': { ru: 'Источник данных: infohub.rs.ge', ka: 'მონაცემთა წყარო: infohub.rs.ge', en: 'Data source: infohub.rs.ge' },
  'footer.ecosystem': { ru: 'часть экосистемы Modern', ka: 'Modern ეკოსისტემის ნაწილი', en: 'part of the Modern Ecosystem' },
  'eco.badge': { ru: 'Часть экосистемы Modern', ka: 'Modern ეკოსისტემის ნაწილი', en: 'Part of the Modern Ecosystem' },
  'hero.tag': { ru: 'AI', ka: 'AI', en: 'AI' },
  'cta.title': { ru: 'Ваш первый вопрос — бесплатно.', ka: 'თქვენი პირველი კითხვა — უფასოა.', en: 'Your first question is free.' },
  'cta.sub': {
    ru: 'Спросите прямо сейчас. Без карты. Каждый ответ — со ссылкой на источник.',
    ka: 'იკითხეთ ახლავე. ბარათის გარეშე. ყოველი პასუხი — წყაროს მითითებით.',
    en: 'Ask right now. No card required. Every answer cites its source.',
  },
  'cta.ask': { ru: 'Задать вопрос', ka: 'კითხვის დასმა', en: 'Ask a question' },
  'cta.pricing': { ru: 'Посмотреть тарифы', ka: 'ტარიფების ნახვა', en: 'See pricing' },
  'footer.sections': { ru: 'Разделы', ka: 'განყოფილებები', en: 'Sections' },
  'footer.contact': { ru: 'Контакты', ka: 'კონტაქტი', en: 'Contact' },

  // Hero
  'hero.eyebrow': { ru: 'Официальная база · {n} документов', ka: 'ოფიციალური ბაზა · {n} დოკუმენტი', en: 'Official database · {n} documents' },
  'hero.eyebrow0': { ru: 'Официальная база документов Грузии', ka: 'საქართველოს ოფიციალური დოკუმენტების ბაზა', en: 'Georgia’s official document base' },
  'hero.title1': { ru: 'Спросите о налогах Грузии.', ka: 'გვკითხეთ გადასახადებზე.', en: 'Ask about Georgian taxes.' },
  'hero.title2': { ru: 'Ответим статьёй закона.', ka: 'გიპასუხებთ კანონის მუხლით.', en: 'We’ll answer with the law.' },
  'hero.sub': {
    ru: 'Мы собрали в одну базу Налоговый кодекс, приказы Минфина и решения по спорам. Спросите своими словами — найдём, что говорит закон, и покажем, откуда это взято. А если ответа в базе нет, так и скажем.',
    ka: 'ერთ ბაზაში შევკრიბეთ საგადასახადო კოდექსი, ფინანსთა სამინისტროს ბრძანებები და დავების გადაწყვეტილებები. იკითხეთ თქვენი სიტყვებით — ვიპოვით, რას ამბობს კანონი, და გაჩვენებთ ზუსტ წყაროს. თუ პასუხი ბაზაში არ არის, პირდაპირ გეტყვით.',
    en: 'We put the Tax Code, Ministry of Finance orders and dispute decisions into one base. Ask in your own words — we’ll find what the law says and show you exactly where it says it. And if the base has no answer, we’ll tell you straight.',
  },

  // Chat
  'chat.placeholder': { ru: 'Спросите о налогах…', ka: 'დასვით კითხვა…', en: 'Ask about taxes…' },
  'chat.ask': { ru: 'Спросить', ka: 'კითხვა', en: 'Ask' },
  'chat.asking': { ru: 'Ищу…', ka: 'ვეძებ…', en: 'Searching…' },
  'chat.question': { ru: 'Вопрос:', ka: 'კითხვა:', en: 'Question:' },
  'chat.searching': { ru: 'Ищу ответ в официальной базе…', ka: 'ვეძებ პასუხს ოფიციალურ ბაზაში…', en: 'Searching the official database…' },
  'chat.err.network': {
    ru: 'Не получилось связаться с сервером. Проверьте подключение к интернету и попробуйте ещё раз.',
    ka: 'სერვერთან დაკავშირება ვერ მოხერხდა. შეამოწმეთ ინტერნეტ-კავშირი და სცადეთ თავიდან.',
    en: 'We couldn’t reach the server. Check your connection and try again.',
  },
  'chat.err.service': {
    ru: 'Не получилось получить ответ — проблема на нашей стороне. Попробуйте ещё раз через минуту.',
    ka: 'პასუხის მიღება ვერ მოხერხდა — პრობლემა ჩვენს მხარესაა. სცადეთ თავიდან ერთ წუთში.',
    en: 'We couldn’t get an answer — the problem is on our side. Try again in a minute.',
  },
  'chat.err.rate': {
    ru: 'Дневной лимит вопросов исчерпан — он обновится завтра. На тарифе Pro вопросы без ограничений.',
    ka: 'კითხვების დღიური ლიმიტი ამოიწურა — განახლდება ხვალ. Pro ტარიფზე კითხვები შეუზღუდავია.',
    en: 'You’ve used today’s question limit — it resets tomorrow. The Pro plan has unlimited questions.',
  },
  'chat.err.retry_cta': { ru: 'Повторить вопрос', ka: 'კითხვის გამეორება', en: 'Ask again' },
  'chat.sources': { ru: 'Источники', ka: 'წყაროები', en: 'Sources' },

  // Document types (SourceChip)
  'doc.law': { ru: 'закон', ka: 'კანონი', en: 'law' },
  'doc.regulation': { ru: 'подзаконный акт', ka: 'კანონქვემდებარე აქტი', en: 'regulation' },
  'doc.court_decision': { ru: 'решение по спору', ka: 'დავის გადაწყვეტილება', en: 'dispute decision' },
  'doc.guideline': { ru: 'разъяснение', ka: 'განმარტება', en: 'guideline' },
  'doc.news': { ru: 'новости законодательства', ka: 'საკანონმდებლო სიახლე', en: 'legislation news' },
  'doc.bill': { ru: 'законопроект', ka: 'კანონპროექტი', en: 'bill' },
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
  'steps.heading': {
    ru: 'Задайте вопрос. Получите ответ с источником.',
    ka: 'დასვით კითხვა. მიიღეთ პასუხი წყაროთი.',
    en: 'Ask a question. Get a sourced answer.',
  },
  'pricing.heading': {
    ru: 'Начните бесплатно. Растите с нами.',
    ka: 'დაიწყეთ უფასოდ. იზარდეთ ჩვენთან.',
    en: 'Start free. Grow with us.',
  },
  'stats.title': { ru: 'Статистика налоговых споров', ka: 'საგადასახადო დავების სტატისტიკა', en: 'Tax dispute statistics' },
  'stats.sub': {
    ru: 'Мы разобрали решения советов по рассмотрению споров Службы доходов и Минфина и посчитали, как они заканчиваются — чтобы вы могли трезво оценить свою стратегию.',
    ka: 'გავაანალიზეთ შემოსავლების სამსახურისა და ფინანსთა სამინისტროს დავების საბჭოების გადაწყვეტილებები და დავთვალეთ მათი შედეგები — რომ თქვენი სტრატეგია რეალურად შეაფასოთ.',
    en: 'We parsed the Revenue Service and MoF dispute-council decisions and counted how they end — so you can judge your strategy soberly.',
  },
  'stats.analyzed': { ru: 'Решений проанализировано', ka: 'გაანალიზებული გადაწყვეტილება', en: 'Decisions analyzed' },
  'stats.of': { ru: 'из {n} в базе', ka: '{n}-დან ბაზაში', en: 'of {n} in the base' },
  'stats.analyzed_detail': {
    ru: 'советы по спорам Службы доходов и Минфина',
    ka: 'შემოსავლების სამსახურისა და ფინანსთა სამინისტროს დავების საბჭოები',
    en: 'Revenue Service and MoF dispute councils',
  },
  'stats.relief': {
    ru: 'Жалоб достигают полного или частичного удовлетворения',
    ka: 'საჩივრები კმაყოფილდება სრულად ან ნაწილობრივ',
    en: 'Complaints granted full or partial relief',
  },
  'stats.top_article': {
    ru: 'Самая оспариваемая статья НК',
    ka: 'სსკ-ის ყველაზე გასაჩივრებული მუხლი',
    en: 'Most contested Tax Code article',
  },
  'stats.decisions': { ru: '{n} решений', ka: '{n} გადაწყვეტილება', en: '{n} decisions' },
  'stats.art': { ru: 'ст. {n}', ka: 'მუხ. {n}', en: 'art. {n}' },
  'stats.unavailable': {
    ru: 'Статистика временно недоступна — данные не загрузились. Приблизительные числа мы не показываем.',
    ka: 'სტატისტიკა დროებით მიუწვდომელია — მონაცემები ვერ ჩაიტვირთა. მიახლოებით რიცხვებს არ ვაჩვენებთ.',
    en: 'Statistics are temporarily unavailable — the data did not load. We don’t show approximate numbers.',
  },
  'stats.retry': { ru: 'Обновить', ka: 'განახლება', en: 'Retry' },

  // Pricing
  'pricing.title': { ru: 'Тарифы', ka: 'ტარიფები', en: 'Pricing' },
  'pricing.month': { ru: '/мес', ka: '/თვე', en: '/mo' },
  'pricing.recommended': { ru: 'Рекомендуем', ka: 'გირჩევთ', en: 'Recommended' },
  'pricing.free_cta': { ru: 'Начать бесплатно', ka: 'დაიწყეთ უფასოდ', en: 'Start free' },
  'pricing.paid_cta': { ru: 'Подключить', ka: 'გამოწერა', en: 'Subscribe' },
  'pricing.note': {
    ru: 'Оформление — в личном кабинете, оплата по счёту. Активируем в течение рабочего дня. Цены предварительные.',
    ka: 'გამოწერა — პირად კაბინეტში, გადახდა ინვოისით. გააქტიურება ერთი სამუშაო დღის განმავლობაში. ფასები წინასწარია.',
    en: 'Subscribe from your account; pay by invoice. Activated within one business day. Prices are preliminary.',
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
  'laws.showmore': { ru: 'Показать ещё {n}', ka: 'კიდევ {n}-ის ჩვენება', en: 'Show {n} more' },
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

  // Methodological guides (situational-guides registry)
  'guides.title': { ru: 'Методические руководства', ka: 'მეთოდური სახელმძღვანელოები', en: 'Methodological guides' },
  'guides.sub': {
    ru: 'Реестр ситуационных руководств Службы доходов: пошаговые разъяснения по конкретным налоговым ситуациям. Реестр показывает, какие руководства действуют, а какие отозваны. Каждое руководство открывается в первоисточнике.',
    ka: 'შემოსავლების სამსახურის სიტუაციური სახელმძღვანელოების რეესტრი: ეტაპობრივი განმარტებები კონკრეტულ საგადასახადო სიტუაციებზე. რეესტრი აჩვენებს, რომელი სახელმძღვანელო მოქმედებს და რომელია ამოღებული. თითოეული იხსნება პირველწყაროში.',
    en: 'The registry of the Revenue Service situational guides: step-by-step explanations for specific tax situations. The registry shows which guides are in force and which have been withdrawn. Each guide opens at the official source.',
  },
  'guides.search': { ru: 'Найти руководство…', ka: 'იპოვეთ სახელმძღვანელო…', en: 'Find a guide…' },
  'guides.total': { ru: 'всего: {n}', ka: 'სულ: {n}', en: 'total: {n}' },
  'guides.filter_all': { ru: 'Все', ka: 'ყველა', en: 'All' },
  'guides.active': { ru: 'Действует', ka: 'მოქმედი', en: 'In force' },
  'guides.withdrawn': { ru: 'Отозвано', ka: 'ამოღებულია', en: 'Withdrawn' },
  'guides.active_n': { ru: 'действуют: {n}', ka: 'მოქმედი: {n}', en: 'in force: {n}' },
  'guides.withdrawn_n': { ru: 'отозваны: {n}', ka: 'ამოღებული: {n}', en: 'withdrawn: {n}' },
  'guides.edition': { ru: 'редакция от {d}', ka: 'რედაქცია: {d}', en: 'edition of {d}' },
  'guides.withdrawn_on': { ru: 'отозвано {d}', ka: 'ამოღებულია {d}', en: 'withdrawn {d}' },
  'guides.registry_src': { ru: 'Официальный реестр', ka: 'ოფიციალური რეესტრი', en: 'Official registry' },

  // News feed by subcategory
  'news.title': { ru: 'Новости законодательства', ka: 'საკანონმდებლო სიახლეები', en: 'Legislation news' },
  'news.sub': {
    ru: 'Всё, что публикует InfoHub Службы доходов, — разобрано по полочкам: международные соглашения, нормы потерь, приказы, руководства, решения по спорам. Каждый документ открывается в первоисточнике.',
    ka: 'ყველაფერი, რასაც შემოსავლების სამსახურის InfoHub აქვეყნებს — დალაგებული თაროებზე: საერთაშორისო შეთანხმებები, დანაკარგის ნორმები, ბრძანებები, სახელმძღვანელოები, დავების გადაწყვეტილებები. თითოეული იხსნება პირველწყაროში.',
    en: 'Everything the Revenue Service InfoHub publishes, sorted onto shelves: international agreements, loss norms, orders, guides, dispute decisions. Each document opens at the official source.',
  },
  'news.search': { ru: 'Найти документ…', ka: 'იპოვეთ დოკუმენტი…', en: 'Find a document…' },
  'news.all': { ru: 'Все', ka: 'ყველა', en: 'All' },
  'news.showmore': { ru: 'Показать ещё {n}', ka: 'კიდევ {n}-ის ჩვენება', en: 'Show {n} more' },
  'news.cat.treaty': {
    ru: 'Международные соглашения',
    ka: 'საერთაშორისო შეთანხმებები',
    en: 'International agreements',
  },
  'news.cat.loss_norms': { ru: 'Нормы потерь', ka: 'დანაკარგის ნორმები', en: 'Loss norms' },
  'news.cat.dispute_decisions': { ru: 'Решения по спорам', ka: 'დავების გადაწყვეტილებები', en: 'Dispute decisions' },
  'news.cat.guidance': { ru: 'Руководства и указания', ka: 'სახელმძღვანელოები და მითითებები', en: 'Guides & instructions' },
  'news.cat.legislation': { ru: 'Законы и законопроекты', ka: 'კანონები და კანონპროექტები', en: 'Laws & bills' },
  'news.cat.orders_resolutions': { ru: 'Приказы и постановления', ka: 'ბრძანებები და დადგენილებები', en: 'Orders & resolutions' },
  'news.cat.general': { ru: 'Прочие новости', ka: 'სხვა სიახლეები', en: 'Other news' },

  // Dispute statistics page
  'disputes.title': { ru: 'Статистика налоговых споров', ka: 'საგადასახადო დავების სტატისტიკა', en: 'Tax dispute statistics' },
  'disputes.sub': {
    ru: 'Каждое решение советов по спорам и судов разобрано машиной: инстанция, оспоренные статьи НК, сумма, исход. Нажмите на любую цифру — откроется список споров, которые за ней стоят.',
    ka: 'დავების საბჭოებისა და სასამართლოების ყველა გადაწყვეტილება მანქანურადაა გარჩეული: ინსტანცია, სადავო მუხლები, თანხა, შედეგი. დააჭირეთ ნებისმიერ ციფრს — გაიხსნება მის უკან მდგარი დავების სია.',
    en: 'Every dispute-council and court decision is machine-parsed: instance, contested Tax Code articles, amount, outcome. Click any number to open the list of disputes behind it.',
  },
  'disputes.coverage': {
    ru: 'проанализировано {a} из {b} решений в базе',
    ka: 'გაანალიზებულია {a} {b}-დან ბაზაში',
    en: '{a} of {b} decisions in the base analyzed',
  },
  'disputes.tile.analyzed': { ru: 'Решений проанализировано', ka: 'გაანალიზებული გადაწყვეტილება', en: 'Decisions analyzed' },
  'disputes.tile.relief': { ru: 'Жалоб удовлетворено полностью или частично', ka: 'საჩივრები დაკმაყოფილდა სრულად ან ნაწილობრივ', en: 'Complaints granted full or partial relief' },
  'disputes.tile.median': { ru: 'Медианная сумма спора', ka: 'დავის მედიანური თანხა', en: 'Median disputed amount' },
  'disputes.tile.median_note': { ru: 'по {n} решениям с указанной суммой', ka: '{n} გადაწყვეტილებაზე მითითებული თანხით', en: 'across {n} decisions stating an amount' },
  'disputes.tile.chains': { ru: 'Связанных апелляционных пар', ka: 'დაკავშირებული სააპელაციო წყვილი', en: 'Linked appeal pairs' },
  'disputes.outcome.satisfied': { ru: 'Удовлетворено', ka: 'დაკმაყოფილდა', en: 'Satisfied' },
  'disputes.outcome.partially_satisfied': { ru: 'Частично', ka: 'ნაწილობრივ', en: 'Partially' },
  'disputes.outcome.rejected': { ru: 'Отклонено', ka: 'არ დაკმაყოფილდა', en: 'Rejected' },
  'disputes.outcome.unclear': { ru: 'Неясно', ka: 'გაურკვეველი', en: 'Unclear' },
  'disputes.body.revenue_service_council': { ru: 'Совет по спорам Службы доходов', ka: 'შემოსავლების სამსახურის დავების საბჭო', en: 'Revenue Service dispute council' },
  'disputes.body.mof_dispute_council': { ru: 'Совет по спорам Минфина', ka: 'ფინანსთა სამინისტროს დავების საბჭო', en: 'MoF dispute council' },
  'disputes.body.city_court': { ru: 'Городской суд', ka: 'საქალაქო სასამართლო', en: 'City court' },
  'disputes.body.appeals_court': { ru: 'Апелляционный суд', ka: 'სააპელაციო სასამართლო', en: 'Appeals court' },
  'disputes.body.supreme_court': { ru: 'Верховный суд', ka: 'უზენაესი სასამართლო', en: 'Supreme court' },
  'disputes.body.other': { ru: 'Другое', ka: 'სხვა', en: 'Other' },
  'disputes.sec.year': { ru: 'Исходы по годам', ka: 'შედეგები წლების მიხედვით', en: 'Outcomes by year' },
  'disputes.sec.instance': { ru: 'Исходы по инстанциям', ka: 'შედეგები ინსტანციების მიხედვით', en: 'Outcomes by instance' },
  'disputes.sec.amounts': { ru: 'Суммы споров', ka: 'დავების თანხები', en: 'Disputed amounts' },
  'disputes.sec.articles': { ru: 'Оспариваемые статьи НК', ka: 'სადავო მუხლები', en: 'Contested Tax Code articles' },
  'disputes.sec.chains': { ru: 'Апелляционные цепочки', ka: 'სააპელაციო ჯაჭვები', en: 'Appeal chains' },
  'disputes.amounts.sum': { ru: 'Всего оспорено', ka: 'სულ სადავო', en: 'Total contested' },
  'disputes.amounts.avg': { ru: 'Средняя сумма', ka: 'საშუალო თანხა', en: 'Average amount' },
  'disputes.amounts.median': { ru: 'Медиана', ka: 'მედიანა', en: 'Median' },
  'disputes.amounts.p90': { ru: '90-й процентиль', ka: '90-ე პროცენტილი', en: '90th percentile' },
  'disputes.amounts.note': {
    ru: 'Сумма указана в {p}% решений — остальные статистика сумм не учитывает.',
    ka: 'თანხა მითითებულია გადაწყვეტილებების {p}%-ში — დანარჩენებს თანხების სტატისტიკა არ ითვალისწინებს.',
    en: 'An amount is stated in {p}% of decisions — the rest are excluded from amount statistics.',
  },
  'disputes.table.article': { ru: 'Статья', ka: 'მუხლი', en: 'Article' },
  'disputes.table.decisions': { ru: 'Решений', ka: 'გადაწყვეტილება', en: 'Decisions' },
  'disputes.table.split': { ru: 'Исходы', ka: 'შედეგები', en: 'Outcomes' },
  'disputes.table.relief': { ru: 'Успех жалоб', ka: 'საჩივრის წარმატება', en: 'Relief rate' },
  'disputes.table.median': { ru: 'Медиана GEL', ka: 'მედიანა GEL', en: 'Median GEL' },
  'disputes.table.instances': { ru: 'Инстанции', ka: 'ინსტანციები', en: 'Instances' },
  'disputes.chains.transition': { ru: '{from} → {to}', ka: '{from} → {to}', en: '{from} → {to}' },
  'disputes.chains.changed': { ru: 'исход изменился: {n}', ka: 'შედეგი შეიცვალა: {n}', en: 'outcome changed: {n}' },
  'disputes.chains.to_taxpayer': { ru: 'в пользу плательщика: {n}', ka: 'გადამხდელის სასარგებლოდ: {n}', en: 'flipped to taxpayer: {n}' },
  'disputes.chains.to_authority': { ru: 'в пользу органа: {n}', ka: 'ორგანოს სასარგებლოდ: {n}', en: 'flipped to authority: {n}' },
  'disputes.chains.reached_court': { ru: 'дошли до суда: {n}', ka: 'სასამართლომდე მივიდა: {n}', en: 'reached court: {n}' },
  'disputes.chains.reached_supreme': { ru: 'до Верховного суда: {n}', ka: 'უზენაეს სასამართლომდე: {n}', en: 'reached Supreme court: {n}' },
  'disputes.chains.note': {
    ru: 'Учитываются только дела, где решение явно ссылается на предыдущую инстанцию или совпадает номер дела.',
    ka: 'ითვლება მხოლოდ საქმეები, სადაც გადაწყვეტილება ცალსახად უთითებს წინა ინსტანციას ან ემთხვევა საქმის ნომერი.',
    en: 'Only cases where the decision explicitly references the lower instance or the case number matches are counted.',
  },
  'disputes.dialog.title': { ru: 'Споры · {n}', ka: 'დავები · {n}', en: 'Disputes · {n}' },
  'disputes.dialog.more': { ru: 'Показать ещё', ka: 'მეტის ჩვენება', en: 'Show more' },
  'disputes.dialog.empty': { ru: 'По этому фильтру споров не нашлось.', ka: 'ამ ფილტრით დავები ვერ მოიძებნა.', en: 'No disputes match this filter.' },
  'disputes.dialog.close': { ru: 'Закрыть', ka: 'დახურვა', en: 'Close' },
  'disputes.year_n': { ru: '{n} год', ka: '{n} წელი', en: '{n}' },
  'disputes.with_amount': { ru: 'С указанной суммой', ka: 'მითითებული თანხით', en: 'With stated amount' },
  'stats.more': { ru: 'Вся статистика споров', ka: 'დავების სრული სტატისტიკა', en: 'Full dispute statistics' },

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
  'acc.bug_title': { ru: 'Нашли ошибку?', ka: 'იპოვეთ შეცდომა?', en: 'Found a bug?' },
  'acc.bug_hint': {
    ru: 'Опишите проблему — неверный ответ, битая ссылка, сбой оплаты. Сообщение сразу попадёт к нам.',
    ka: 'აღწერეთ პრობლემა — არასწორი პასუხი, გაფუჭებული ბმული, გადახდის შეფერხება. შეტყობინება პირდაპირ ჩვენთან მოვა.',
    en: 'Describe the problem — a wrong answer, a broken link, a payment failure. The message goes straight to us.',
  },
  'acc.bug_button': { ru: 'Сообщить об ошибке', ka: 'შეცდომის შეტყობინება', en: 'Report a bug' },
  'acc.bug_placeholder': { ru: 'Что пошло не так?', ka: 'რა მოხდა?', en: 'What went wrong?' },
  'acc.bug_send': { ru: 'Отправить', ka: 'გაგზავნა', en: 'Send' },
  'acc.bug_sending': { ru: 'Отправляю…', ka: 'იგზავნება…', en: 'Sending…' },
  'acc.bug_sent': { ru: 'Спасибо! Сообщение отправлено.', ka: 'მადლობა! შეტყობინება გაიგზავნა.', en: 'Thank you! Your report has been sent.' },
  'acc.bug_error': { ru: 'Не удалось отправить. Попробуйте ещё раз.', ka: 'გაგზავნა ვერ მოხერხდა. სცადეთ ხელახლა.', en: 'Could not send. Please try again.' },
  'acc.bug_short': { ru: 'Опишите проблему подробнее (минимум 5 символов).', ka: 'აღწერეთ პრობლემა უფრო ვრცლად (მინ. 5 სიმბოლო).', en: 'Please describe the problem in more detail (5+ characters).' },
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

// Number grouping: space for ru and ka (CLDR ka-GE uses commas, which read
// as English in Georgian text), comma for en.
export function formatNum(lang: Lang, n: number): string {
  return n.toLocaleString(lang === 'en' ? 'en-GB' : 'ru-RU');
}
