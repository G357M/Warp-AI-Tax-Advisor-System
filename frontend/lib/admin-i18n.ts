'use client';

/**
 * Admin panel copy (ru / ka / en). Language follows the site header via useLang().
 * Payments keep their own dictionary in lib/billing-reconciliation.ts.
 */
import { useLang, type Lang } from './i18n';

export type AdminLocale = string | string[];
// Chromium ICU ships no `ka` data, so ka-GE would fall back to en-US (11/1/2026).
// Intl uses the first supported entry; ru-RU gives dd.MM.yyyy, HH:mm, as in Georgia.
export const ADMIN_LOCALE: Record<Lang, AdminLocale> = { ru: 'ru-RU', ka: ['ka-GE', 'ru-RU'], en: 'en-GB' };

const ru = {
  nav: {
    menu: 'Меню администратора', checking: 'Проверяем доступ…', admin: 'Администрирование', back: 'На сайт',
    dashboard: 'Обзор', documents: 'Документы', analytics: 'Аналитика споров', users: 'Пользователи',
    feedback: 'Обращения', scraper: 'Ингест', audit: 'Журнал действий', config: 'Конфигурация',
  },
  common: {
    loading: 'Загружаем…', loadError: 'Не удалось загрузить данные.', retry: 'Повторить', empty: 'Пока пусто.',
    refresh: 'Обновить', cancel: 'Отмена', confirm: 'Подтвердить', reason: 'Причина (необязательно)',
    reasonHint: 'Попадёт в журнал действий.', saveError: 'Не удалось сохранить изменение.',
    prev: 'Назад', next: 'Вперёд', range: (from: number, to: number, total: string) => `${from}–${to} из ${total}`,
    all: 'Все', dash: '—', yes: 'да', no: 'нет', set: 'задан', notSet: 'не задан',
  },
  dashboard: {
    title: 'Обзор', subtitle: 'Что требует внимания и общее состояние системы.',
    attention: 'Требует внимания', allClear: 'Сейчас ничего не требует вашего внимания.',
    feedbackNew: (n: string) => `Новые обращения: ${n}`,
    reconciliation: (n: string) => `Платежи на сверке: ${n}`,
    manualPending: (n: string) => `Заявки ждут активации: ${n}`,
    ingestStale: 'Ночной ингест не обновлялся больше 36 часов',
    decisionsQueue: (n: string) => `Решения ждут извлечения фактов: ${n}`,
    documents: 'Документов в базе', lastIngest: (d: string) => `последний ингест ${d}`,
    decisions: 'Решения: извлечено фактов', queue: (n: string) => `в очереди ${n}`,
    amendments: 'Поправки: извлечено', amendmentsDetail: (r: string, p: string) => `закон найден: ${r} · в очереди ${p}`,
    users: 'Пользователи', admins: (n: string) => `администраторов: ${n}`,
    subscriptions: 'Активные подписки', noSubscriptions: 'пока нет',
    messages7d: 'Сообщений за 7 дней', conversations: (n: string) => `всего диалогов: ${n}`,
    corpus: 'Корпус по типам', recent: 'Последние действия', openAudit: 'Весь журнал',
  },
  audit: {
    title: 'Журнал действий', subtitle: 'Каждое изменение, сделанное администратором. Записи нельзя изменить или удалить.',
    when: 'Когда', who: 'Кто', action: 'Действие', target: 'Объект', change: 'Изменение', reason: 'Причина',
    actions: {
      'user.role_changed': 'Смена роли', 'subscription.activated': 'Активация подписки',
      'feedback.status_changed': 'Статус обращения',
    } as Record<string, string>,
    targets: { user: 'Пользователь', checkout: 'Заявка', feedback: 'Обращение' } as Record<string, string>,
  },
  config: {
    title: 'Конфигурация', subtitle: 'Текущие настройки сервера, только для чтения.',
    howToChange: 'Значения меняются в /root/infohub/.env на сервере и вступают в силу после деплоя. Секреты здесь не показываются, только признак «задан».',
    groups: { app: 'Приложение', llm: 'Модели и поиск', email: 'Почта', billing: 'Оплата', limits: 'Ограничения', secrets: 'Секреты' } as Record<string, string>,
    name: 'Параметр', value: 'Значение',
  },
  users: {
    title: 'Пользователи', settleTitle: 'Подтвердить заявку клиента после оплаты',
    checkoutPlaceholder: 'UUID заявки из кабинета клиента', settle: 'Подтвердить оплату',
    legacyTitle: 'Резервный режим без заявки (для старых счетов)', emailPlaceholder: 'email клиента',
    months: (n: number) => `${n} мес.`, activate: 'Активировать',
    settled: (email: string, plan: string, until: string) => `Оплата подтверждена: ${email} → ${plan} до ${until}`,
    replayed: (email: string, plan: string, until: string) => `Уже подтверждено: ${email} → ${plan} до ${until}`,
    activated: (email: string, plan: string, until: string) => `Активировано: ${email} → ${plan} до ${until}`,
    period: 'Срок',
    login: 'Логин', email: 'Email', role: 'Роль', plan: 'Тариф', until: 'Подписка до', lastLogin: 'Последний вход',
    confirmRole: (user: string, role: string) => `Сменить роль ${user} на «${role}»?`,
    confirmSettle: 'Подтвердить оплату по этой заявке и открыть доступ?',
    confirmActivate: (email: string, plan: string, months: number) => `Активировать ${plan} на ${months} мес. для ${email}?`,
  },
  feedback: {
    title: 'Обращения', date: 'Дата', user: 'Пользователь', page: 'Страница', message: 'Сообщение', status: 'Статус',
    statuses: { new: 'Новое', in_progress: 'В работе', fixed: 'Исправлено' } as Record<string, string>,
    confirmStatus: (status: string) => `Перевести обращение в статус «${status}»?`,
  },
  documents: {
    title: 'Документы', search: 'Поиск по названию или номеру…', allTypes: 'Все типы',
    name: 'Название', type: 'Тип', number: 'Номер', date: 'Дата', authority: 'Орган', notFound: 'Ничего не найдено.',
  },
  scraper: {
    title: 'Ингест и фоновые задачи', lastIngest: 'Последний ингест', today: (n: string) => `сегодня добавлено: ${n}`,
    decisions: 'Решения в очереди на разметку', amendments: 'Поправки в очереди', logEmpty: 'Лог пуст или недоступен.',
    logs: { scraper: 'Ночной скрейпер', law_amendments_backfill: 'Бэкфилл поправок', decision_facts_backfill: 'Бэкфилл решений' } as Record<string, string>,
  },
  analytics: {
    title: 'Аналитика споров', subtitle: 'Исходы налоговых и таможенных споров по решениям из официальной базы.',
    analyzed: 'Решений разобрано', coverage: (p: number, total: string) => `${p}% из ${total} в базе`,
    relief: 'Доля удовлетворённых', reliefDetail: 'жалоба удовлетворена полностью или частично',
    satisfied: 'Удовлетворено полностью', vsRejected: (n: string) => `против ${n} отказов`,
    byYear: 'Исходы по годам', byBody: 'Исходы по органам', topArticles: 'Самые оспариваемые статьи НК',
    article: 'Статья', decisions: 'Решений', split: 'Распределение исходов', reliefRate: 'Доля удовлетворённых',
    outcomes: { satisfied: 'Удовлетворено', partially_satisfied: 'Частично', rejected: 'Отказ' } as Record<string, string>,
    bodies: {
      revenue_service_council: 'Совет по спорам Службы доходов', mof_dispute_council: 'Совет по спорам Минфина',
      city_court: 'Городской суд', appeals_court: 'Апелляционный суд', supreme_court: 'Верховный суд', other: 'Другое',
    } as Record<string, string>,
    reliefShort: 'удовл.',
  },
};

export type AdminCopy = typeof ru;

const ka: AdminCopy = {
  nav: {
    menu: 'ადმინისტრატორის მენიუ', checking: 'წვდომა მოწმდება…', admin: 'ადმინისტრირება', back: 'საიტზე დაბრუნება',
    dashboard: 'მიმოხილვა', documents: 'დოკუმენტები', analytics: 'დავების ანალიტიკა', users: 'მომხმარებლები',
    feedback: 'მიმართვები', scraper: 'მონაცემების შეგროვება', audit: 'მოქმედებების ჟურნალი', config: 'კონფიგურაცია',
  },
  common: {
    loading: 'იტვირთება…', loadError: 'მონაცემები ვერ ჩაიტვირთა.', retry: 'ხელახლა ცდა', empty: 'ჯერ ცარიელია.',
    refresh: 'განახლება', cancel: 'გაუქმება', confirm: 'დადასტურება', reason: 'მიზეზი (არასავალდებულო)',
    reasonHint: 'ჩაიწერება მოქმედებების ჟურნალში.', saveError: 'ცვლილება ვერ შეინახა.',
    prev: 'უკან', next: 'შემდეგი', range: (from: number, to: number, total: string) => `${from}–${to} / ${total}`,
    all: 'ყველა', dash: '—', yes: 'კი', no: 'არა', set: 'მითითებულია', notSet: 'არ არის მითითებული',
  },
  dashboard: {
    title: 'მიმოხილვა', subtitle: 'რას სჭირდება ყურადღება და სისტემის ზოგადი მდგომარეობა.',
    attention: 'საჭიროებს ყურადღებას', allClear: 'ამჟამად თქვენს ყურადღებას არაფერი საჭიროებს.',
    feedbackNew: (n: string) => `ახალი მიმართვები: ${n}`,
    reconciliation: (n: string) => `შესამოწმებელი გადახდები: ${n}`,
    manualPending: (n: string) => `გააქტიურების მომლოდინე განაცხადები: ${n}`,
    ingestStale: 'ღამის შეგროვება 36 საათზე მეტია არ განახლებულა',
    decisionsQueue: (n: string) => `ფაქტების ამოღების მომლოდინე გადაწყვეტილებები: ${n}`,
    documents: 'დოკუმენტები ბაზაში', lastIngest: (d: string) => `ბოლო შეგროვება ${d}`,
    decisions: 'გადაწყვეტილებები: ამოღებული ფაქტები', queue: (n: string) => `რიგშია ${n}`,
    amendments: 'ცვლილებები: დამუშავებული', amendmentsDetail: (r: string, p: string) => `კანონი ნაპოვნია: ${r} · რიგშია ${p}`,
    users: 'მომხმარებლები', admins: (n: string) => `ადმინისტრატორები: ${n}`,
    subscriptions: 'აქტიური გამოწერები', noSubscriptions: 'ჯერ არ არის',
    messages7d: 'შეტყობინებები ბოლო 7 დღეში', conversations: (n: string) => `სულ დიალოგები: ${n}`,
    corpus: 'კორპუსი ტიპების მიხედვით', recent: 'ბოლო მოქმედებები', openAudit: 'მთელი ჟურნალი',
  },
  audit: {
    title: 'მოქმედებების ჟურნალი', subtitle: 'ადმინისტრატორის ყველა ცვლილება. ჩანაწერის შეცვლა ან წაშლა შეუძლებელია.',
    when: 'როდის', who: 'ვინ', action: 'მოქმედება', target: 'ობიექტი', change: 'ცვლილება', reason: 'მიზეზი',
    actions: {
      'user.role_changed': 'როლის შეცვლა', 'subscription.activated': 'გამოწერის გააქტიურება',
      'feedback.status_changed': 'მიმართვის სტატუსი',
    },
    targets: { user: 'მომხმარებელი', checkout: 'განაცხადი', feedback: 'მიმართვა' },
  },
  config: {
    title: 'კონფიგურაცია', subtitle: 'სერვერის მიმდინარე პარამეტრები, მხოლოდ სანახავად.',
    howToChange: 'მნიშვნელობები სერვერზე, /root/infohub/.env ფაილში იცვლება და დეპლოის შემდეგ ამოქმედდება. საიდუმლო მნიშვნელობები აქ არ ჩანს, ჩანს მხოლოდ ის, მითითებულია თუ არა.',
    groups: { app: 'აპლიკაცია', llm: 'მოდელები და ძიება', email: 'ფოსტა', billing: 'გადახდა', limits: 'შეზღუდვები', secrets: 'საიდუმლოები' },
    name: 'პარამეტრი', value: 'მნიშვნელობა',
  },
  users: {
    title: 'მომხმარებლები', settleTitle: 'კლიენტის განაცხადის დადასტურება გადახდის შემდეგ',
    checkoutPlaceholder: 'განაცხადის UUID კლიენტის კაბინეტიდან', settle: 'გადახდის დადასტურება',
    legacyTitle: 'სარეზერვო რეჟიმი განაცხადის გარეშე (ძველი ანგარიშებისთვის)', emailPlaceholder: 'კლიენტის ელფოსტა',
    months: (n: number) => `${n} თვე`, activate: 'გააქტიურება',
    settled: (email: string, plan: string, until: string) => `გადახდა დადასტურდა: ${email} → ${plan}, ${until}-მდე`,
    replayed: (email: string, plan: string, until: string) => `უკვე დადასტურებულია: ${email} → ${plan}, ${until}-მდე`,
    activated: (email: string, plan: string, until: string) => `გააქტიურდა: ${email} → ${plan}, ${until}-მდე`,
    period: 'ვადა',
    login: 'მომხმარებლის სახელი', email: 'ელფოსტა', role: 'როლი', plan: 'ტარიფი', until: 'გამოწერის ვადა', lastLogin: 'ბოლო შესვლა',
    confirmRole: (user: string, role: string) => `შეიცვალოს ${user}-ის როლი „${role}“-ით?`,
    confirmSettle: 'დადასტურდეს ამ განაცხადის გადახდა და გაიხსნას წვდომა?',
    confirmActivate: (email: string, plan: string, months: number) => `გააქტიურდეს ${plan} ${months} თვით ${email}-ისთვის?`,
  },
  feedback: {
    title: 'მიმართვები', date: 'თარიღი', user: 'მომხმარებელი', page: 'გვერდი', message: 'შეტყობინება', status: 'სტატუსი',
    statuses: { new: 'ახალი', in_progress: 'მუშავდება', fixed: 'გამოსწორებულია' },
    confirmStatus: (status: string) => `მიენიჭოს მიმართვას სტატუსი „${status}“?`,
  },
  documents: {
    title: 'დოკუმენტები', search: 'ძიება სათაურით ან ნომრით…', allTypes: 'ყველა ტიპი',
    name: 'სათაური', type: 'ტიპი', number: 'ნომერი', date: 'თარიღი', authority: 'ორგანო', notFound: 'ვერაფერი მოიძებნა.',
  },
  scraper: {
    title: 'შეგროვება და ფონური ამოცანები', lastIngest: 'ბოლო შეგროვება', today: (n: string) => `დღეს დაემატა: ${n}`,
    decisions: 'დასამუშავებელი გადაწყვეტილებები', amendments: 'დასამუშავებელი ცვლილებები', logEmpty: 'ჟურნალი ცარიელია ან მიუწვდომელია.',
    logs: { scraper: 'ღამის შეგროვება', law_amendments_backfill: 'ცვლილებების დამუშავება', decision_facts_backfill: 'გადაწყვეტილებების დამუშავება' },
  },
  analytics: {
    title: 'დავების ანალიტიკა', subtitle: 'საგადასახადო და საბაჟო დავების შედეგები ოფიციალური ბაზის გადაწყვეტილებების მიხედვით.',
    analyzed: 'გაანალიზებული გადაწყვეტილებები', coverage: (p: number, total: string) => `${p}% ბაზაში არსებული ${total}-დან`,
    relief: 'დაკმაყოფილების წილი', reliefDetail: 'საჩივარი დაკმაყოფილდა სრულად ან ნაწილობრივ',
    satisfied: 'სრულად დაკმაყოფილდა', vsRejected: (n: string) => `${n} უარის წინააღმდეგ`,
    byYear: 'შედეგები წლების მიხედვით', byBody: 'შედეგები ორგანოების მიხედვით', topArticles: 'საგადასახადო კოდექსის ყველაზე სადავო მუხლები',
    article: 'მუხლი', decisions: 'გადაწყვეტილებები', split: 'შედეგების განაწილება', reliefRate: 'დაკმაყოფილების წილი',
    outcomes: { satisfied: 'დაკმაყოფილდა', partially_satisfied: 'ნაწილობრივ', rejected: 'უარი' },
    bodies: {
      revenue_service_council: 'შემოსავლების სამსახურის დავების საბჭო', mof_dispute_council: 'ფინანსთა სამინისტროს დავების საბჭო',
      city_court: 'საქალაქო სასამართლო', appeals_court: 'სააპელაციო სასამართლო', supreme_court: 'უზენაესი სასამართლო', other: 'სხვა',
    },
    reliefShort: 'დაკმ.',
  },
};

const en: AdminCopy = {
  nav: {
    menu: 'Administrator menu', checking: 'Checking access…', admin: 'Administration', back: 'Back to site',
    dashboard: 'Overview', documents: 'Documents', analytics: 'Dispute analytics', users: 'Users',
    feedback: 'Feedback', scraper: 'Ingest', audit: 'Action log', config: 'Configuration',
  },
  common: {
    loading: 'Loading…', loadError: 'Could not load the data.', retry: 'Retry', empty: 'Nothing here yet.',
    refresh: 'Refresh', cancel: 'Cancel', confirm: 'Confirm', reason: 'Reason (optional)',
    reasonHint: 'Saved to the action log.', saveError: 'Could not save the change.',
    prev: 'Previous', next: 'Next', range: (from: number, to: number, total: string) => `${from}–${to} of ${total}`,
    all: 'All', dash: '—', yes: 'yes', no: 'no', set: 'set', notSet: 'not set',
  },
  dashboard: {
    title: 'Overview', subtitle: 'What needs attention and the overall state of the system.',
    attention: 'Needs attention', allClear: 'Nothing needs your attention right now.',
    feedbackNew: (n: string) => `New feedback: ${n}`,
    reconciliation: (n: string) => `Payments to reconcile: ${n}`,
    manualPending: (n: string) => `Orders awaiting activation: ${n}`,
    ingestStale: 'The nightly ingest has not run for more than 36 hours',
    decisionsQueue: (n: string) => `Decisions awaiting fact extraction: ${n}`,
    documents: 'Documents in the corpus', lastIngest: (d: string) => `last ingest ${d}`,
    decisions: 'Decisions: facts extracted', queue: (n: string) => `${n} queued`,
    amendments: 'Amendments: extracted', amendmentsDetail: (r: string, p: string) => `law resolved: ${r} · ${p} queued`,
    users: 'Users', admins: (n: string) => `administrators: ${n}`,
    subscriptions: 'Active subscriptions', noSubscriptions: 'none yet',
    messages7d: 'Messages in 7 days', conversations: (n: string) => `conversations in total: ${n}`,
    corpus: 'Corpus by type', recent: 'Recent actions', openAudit: 'Full log',
  },
  audit: {
    title: 'Action log', subtitle: 'Every change made by an administrator. Entries cannot be edited or deleted.',
    when: 'When', who: 'Who', action: 'Action', target: 'Target', change: 'Change', reason: 'Reason',
    actions: {
      'user.role_changed': 'Role change', 'subscription.activated': 'Subscription activation',
      'feedback.status_changed': 'Feedback status',
    },
    targets: { user: 'User', checkout: 'Order', feedback: 'Feedback' },
  },
  config: {
    title: 'Configuration', subtitle: 'Current server settings, read-only.',
    howToChange: 'Values are changed in /root/infohub/.env on the server and take effect after a deploy. Secrets are never shown here, only whether they are set.',
    groups: { app: 'Application', llm: 'Models and retrieval', email: 'Email', billing: 'Billing', limits: 'Limits', secrets: 'Secrets' },
    name: 'Setting', value: 'Value',
  },
  users: {
    title: 'Users', settleTitle: 'Confirm a customer order after payment',
    checkoutPlaceholder: 'Order UUID from the customer account', settle: 'Confirm payment',
    legacyTitle: 'Fallback without an order (legacy invoices)', emailPlaceholder: 'customer email',
    months: (n: number) => `${n} mo`, activate: 'Activate',
    settled: (email: string, plan: string, until: string) => `Payment confirmed: ${email} → ${plan} until ${until}`,
    replayed: (email: string, plan: string, until: string) => `Already confirmed: ${email} → ${plan} until ${until}`,
    activated: (email: string, plan: string, until: string) => `Activated: ${email} → ${plan} until ${until}`,
    period: 'Period',
    login: 'Username', email: 'Email', role: 'Role', plan: 'Plan', until: 'Subscription until', lastLogin: 'Last login',
    confirmRole: (user: string, role: string) => `Change ${user}'s role to “${role}”?`,
    confirmSettle: 'Confirm payment for this order and grant access?',
    confirmActivate: (email: string, plan: string, months: number) => `Activate ${plan} for ${months} mo for ${email}?`,
  },
  feedback: {
    title: 'Feedback', date: 'Date', user: 'User', page: 'Page', message: 'Message', status: 'Status',
    statuses: { new: 'New', in_progress: 'In progress', fixed: 'Fixed' },
    confirmStatus: (status: string) => `Set this report to “${status}”?`,
  },
  documents: {
    title: 'Documents', search: 'Search by title or number…', allTypes: 'All types',
    name: 'Title', type: 'Type', number: 'Number', date: 'Date', authority: 'Authority', notFound: 'Nothing found.',
  },
  scraper: {
    title: 'Ingest and background jobs', lastIngest: 'Last ingest', today: (n: string) => `added today: ${n}`,
    decisions: 'Decisions awaiting extraction', amendments: 'Amendments awaiting extraction', logEmpty: 'Log is empty or unavailable.',
    logs: { scraper: 'Nightly scraper', law_amendments_backfill: 'Amendments backfill', decision_facts_backfill: 'Decision facts backfill' },
  },
  analytics: {
    title: 'Dispute analytics', subtitle: 'Outcomes of tax and customs dispute decisions from the official corpus.',
    analyzed: 'Decisions analysed', coverage: (p: number, total: string) => `${p}% of ${total} in the corpus`,
    relief: 'Taxpayer relief rate', reliefDetail: 'complaint satisfied fully or partially',
    satisfied: 'Fully satisfied', vsRejected: (n: string) => `vs ${n} rejected`,
    byYear: 'Outcomes by year', byBody: 'Outcomes by deciding body', topArticles: 'Most contested Tax Code articles',
    article: 'Article', decisions: 'Decisions', split: 'Outcome split', reliefRate: 'Relief rate',
    outcomes: { satisfied: 'Satisfied', partially_satisfied: 'Partially', rejected: 'Rejected' },
    bodies: {
      revenue_service_council: 'Revenue Service dispute council', mof_dispute_council: 'MoF dispute council',
      city_court: 'City court', appeals_court: 'Appeals court', supreme_court: 'Supreme court', other: 'Other',
    },
    reliefShort: 'relief',
  },
};

const COPY: Record<Lang, AdminCopy> = { ru, ka, en };

export function useAdminCopy(): { lang: Lang; c: AdminCopy; locale: AdminLocale } {
  const lang = useLang();
  return { lang, c: COPY[lang], locale: ADMIN_LOCALE[lang] };
}

/** Backend timestamps are naive UTC ISO strings; treat them as UTC. */
function parseUtc(value: string): Date {
  return new Date(/[zZ]|[+-]\d\d:?\d\d$/.test(value) ? value : `${value}Z`);
}

export function formatDateTime(value: string | null, locale: AdminLocale): string {
  return value ? parseUtc(value).toLocaleString(locale, { dateStyle: 'short', timeStyle: 'short' }) : '—';
}

export function formatDate(value: string | null, locale: AdminLocale): string {
  return value ? parseUtc(value).toLocaleDateString(locale) : '—';
}

export function formatNumber(value: number, locale: AdminLocale): string {
  return value.toLocaleString(locale);
}
