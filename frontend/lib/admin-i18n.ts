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

export const ADMIN_ACTIONS = [
  'user.role_changed', 'subscription.activated', 'feedback.status_changed', 'user.blocked', 'user.unblocked',
  'subscription.granted', 'subscription.canceled', 'user.password_reset_sent', 'user.verification_sent',
] as const;
export type AdminAction = (typeof ADMIN_ACTIONS)[number];

export const ADMIN_ERROR_CODES = [
  'user_not_found', 'feedback_not_found', 'cannot_block_self', 'cannot_block_admin', 'cannot_demote_self',
  'user_blocked', 'admin_has_business', 'active_plan_differs', 'plan_unlimited', 'no_active_subscription',
  'email_already_verified', 'email_unavailable',
] as const;
export type AdminErrorCode = (typeof ADMIN_ERROR_CODES)[number];

const ru = {
  nav: {
    menu: 'Меню администратора', checking: 'Проверяем доступ…', admin: 'Администрирование', back: 'На сайт',
    dashboard: 'Обзор', documents: 'Документы', analytics: 'Аналитика споров', users: 'Пользователи',
    feedback: 'Обращения', scraper: 'Ингест', audit: 'Журнал действий', config: 'Конфигурация',
  },
  common: {
    loading: 'Загружаем…', loadError: 'Не удалось загрузить данные.', retry: 'Повторить', empty: 'Пока пусто.',
    refresh: 'Обновить', cancel: 'Отмена', confirm: 'Подтвердить', reason: 'Причина (необязательно)',
    reasonRequired: 'Причина (обязательно, не короче 3 символов)',
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
      'user.blocked': 'Блокировка', 'user.unblocked': 'Разблокировка', 'subscription.granted': 'Подарок тарифа',
      'subscription.canceled': 'Досрочное прекращение', 'user.password_reset_sent': 'Письмо сброса пароля',
      'user.verification_sent': 'Письмо подтверждения',
    } satisfies Record<AdminAction, string>,
    targets: { user: 'Пользователь', checkout: 'Заявка', feedback: 'Обращение' } as Record<string, string>,
  },
  config: {
    title: 'Конфигурация', subtitle: 'Текущие настройки сервера, только для чтения.',
    howToChange: 'Значения меняются в /root/infohub/.env на сервере и вступают в силу после деплоя. Секреты здесь не показываются, только признак «задан».',
    groups: { app: 'Приложение', llm: 'Модели и поиск', email: 'Почта', billing: 'Оплата', limits: 'Ограничения', secrets: 'Секреты' } as Record<string, string>,
    name: 'Параметр', value: 'Значение',
  },
  users: {
    status: 'Статус', search: 'Поиск по email, логину или имени', planFilter: 'Тариф', statusFilter: 'Статус',
    sortLabel: 'Сортировка', reset: 'Сбросить фильтры', notFound: 'Никого не найдено.',
    plans: { free: 'Free', pro: 'Pro', business: 'Business', expiring: 'Истекает в течение 7 дней' },
    statuses: { active: 'Активен', blocked: 'Заблокирован', unverified: 'Email не подтверждён', admin: 'Администратор' },
    sorts: { created_desc: 'Сначала новые', last_login_desc: 'По последнему входу', period_end_asc: 'По окончанию подписки' },
    title: 'Пользователи', settleTitle: 'Подтвердить заявку клиента после оплаты',
    checkoutPlaceholder: 'UUID заявки из кабинета клиента', settle: 'Подтвердить оплату',
    months: (n: number) => `${n} мес.`,
    days: (n: number) => `${n} дн.`,
    settled: (email: string, plan: string, until: string) => `Оплата подтверждена: ${email} → ${plan} до ${until}`,
    replayed: (email: string, plan: string, until: string) => `Уже подтверждено: ${email} → ${plan} до ${until}`,
    login: 'Логин', email: 'Email', role: 'Роль', plan: 'Тариф', until: 'Подписка до', lastLogin: 'Последний вход',
    confirmSettle: 'Подтвердить оплату по этой заявке и открыть доступ?',
  },
  card: {
    back: '← К списку', notFound: 'Пользователь не найден.',
    profile: 'Профиль', fullName: 'Полное имя', registered: 'Регистрация', lastLogin: 'Последний вход', role: 'Роль',
    subscription: 'Подписка', noSubscription: 'Подписки нет.', plan: 'Тариф', status: 'Статус', until: 'До',
    daysLeft: (n: number) => `осталось ${n} дн.`, source: 'Источник',
    sources: { grant: 'подарок', payment: 'оплата' },
    subStatuses: { active: 'активна', past_due: 'просрочена', canceled: 'прекращена' },
    payments: 'Платежи', checkouts: 'Заявки', date: 'Дата', amount: 'Сумма', provider: 'Способ', state: 'Статус',
    settle: 'Провести', none: 'Записей нет.',
    activity: 'Активность', questions7d: 'Вопросов за 7 дней', questions30d: 'Вопросов за 30 дней',
    conversations: (n: string) => `диалогов: ${n}`, today: 'Вопросов сегодня',
    todayValue: (n: string, m: string) => `${n} из ${m}`, noData: 'нет данных', feedback: 'Обращений',
    actions: 'Действия', access: 'Доступ', subscriptionGroup: 'Подписка', emails: 'Письма',
    block: 'Заблокировать', unblock: 'Разблокировать', changeRole: 'Сменить роль',
    demoteFirst: 'Чтобы заблокировать администратора, сначала снимите роль.',
    grant: 'Подарить или продлить', recordPayment: 'Записать оплату', cancel: 'Прекратить досрочно',
    sendReset: 'Отправить сброс пароля', sendVerification: 'Отправить подтверждение email',
    confirmBlock: (u: string) => `Заблокировать ${u}? Все активные сессии будут завершены.`,
    confirmUnblock: (u: string) => `Разблокировать ${u}?`,
    confirmRole: (u: string) => `Сменить роль ${u}?`, newRole: 'Новая роль',
    grantTitle: (u: string) => `Подарить или продлить тариф для ${u}`, daysLabel: 'Дней', customDays: 'Своё число',
    activeUntil: (d: string) => `Будет активно до ${d}`,
    replaceWarning: (p: string) => `Сейчас активен тариф ${p}. Оставшееся время по нему будет потеряно.`,
    replaceConfirm: 'Заменить текущий тариф',
    paymentTitle: (u: string) => `Записать оплату от ${u}`, monthsLabel: 'Месяцев', amountLabel: 'Сумма по тарифу',
    cancelTitle: (u: string) => `Прекратить подписку ${u} досрочно`, category: 'Причина прекращения',
    categories: { refund: 'Возврат средств', mistaken_activation: 'Ошибочная активация', fraud: 'Мошенничество или chargeback', other: 'Другое' },
    cancelWarning: (n: number) => `Оплачено ещё ${n} дн. Доступ закроется сразу. Возврат денег делается вне системы.`,
    confirmReset: (e: string) => `Отправить письмо для сброса пароля на ${e}?`,
    confirmVerification: (e: string) => `Отправить письмо подтверждения на ${e}?`,
    done: 'Готово.', unchanged: 'Изменений нет: состояние уже такое.',
    emailSent: 'Письмо отправлено.', emailCooldown: 'Письмо уже отправлялось недавно, попробуйте позже.',
  },
  errors: {
    user_not_found: 'Пользователь не найден.', feedback_not_found: 'Обращение не найдено.',
    cannot_block_self: 'Нельзя заблокировать самого себя.', cannot_block_admin: 'Сначала снимите роль администратора.',
    cannot_demote_self: 'Нельзя снять права администратора с самого себя.', user_blocked: 'Пользователь заблокирован.',
    admin_has_business: 'У администратора и так тариф Business.',
    active_plan_differs: 'Активен другой тариф — подтвердите замену.',
    plan_unlimited: 'У текущего тарифа нет даты окончания.', no_active_subscription: 'Нет активной платной подписки.',
    email_already_verified: 'Email уже подтверждён.', email_unavailable: 'Отправка почты не настроена.',
  } satisfies Record<AdminErrorCode, string>,
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
    reasonRequired: 'მიზეზი (სავალდებულოა, მინიმუმ 3 სიმბოლო)',
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
      'user.blocked': 'დაბლოკვა', 'user.unblocked': 'განბლოკვა', 'subscription.granted': 'ტარიფის ჩუქება',
      'subscription.canceled': 'ვადაზე ადრე შეწყვეტა', 'user.password_reset_sent': 'პაროლის აღდგენის წერილი',
      'user.verification_sent': 'დადასტურების წერილი',
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
    status: 'სტატუსი', search: 'ძიება ელფოსტით, მომხმარებლის სახელით ან სახელით', planFilter: 'ტარიფი', statusFilter: 'სტატუსი',
    sortLabel: 'დახარისხება', reset: 'ფილტრების გასუფთავება', notFound: 'არავინ მოიძებნა.',
    plans: { free: 'Free', pro: 'Pro', business: 'Business', expiring: 'ვადა 7 დღეში იწურება' },
    statuses: { active: 'აქტიურია', blocked: 'დაბლოკილია', unverified: 'ელფოსტა დაუდასტურებელია', admin: 'ადმინისტრატორი' },
    sorts: { created_desc: 'ჯერ ახალი', last_login_desc: 'ბოლო შესვლის მიხედვით', period_end_asc: 'გამოწერის დასრულების მიხედვით' },
    title: 'მომხმარებლები', settleTitle: 'კლიენტის განაცხადის დადასტურება გადახდის შემდეგ',
    checkoutPlaceholder: 'განაცხადის UUID კლიენტის კაბინეტიდან', settle: 'გადახდის დადასტურება',
    months: (n: number) => `${n} თვე`,
    days: (n: number) => `${n} დღე`,
    settled: (email: string, plan: string, until: string) => `გადახდა დადასტურდა: ${email} → ${plan}, ${until}-მდე`,
    replayed: (email: string, plan: string, until: string) => `უკვე დადასტურებულია: ${email} → ${plan}, ${until}-მდე`,
    login: 'მომხმარებლის სახელი', email: 'ელფოსტა', role: 'როლი', plan: 'ტარიფი', until: 'გამოწერის ვადა', lastLogin: 'ბოლო შესვლა',
    confirmSettle: 'დადასტურდეს ამ განაცხადის გადახდა და გაიხსნას წვდომა?',
  },
  card: {
    back: '← სიაში დაბრუნება', notFound: 'მომხმარებელი ვერ მოიძებნა.',
    profile: 'პროფილი', fullName: 'სრული სახელი', registered: 'რეგისტრაცია', lastLogin: 'ბოლო შესვლა', role: 'როლი',
    subscription: 'გამოწერა', noSubscription: 'გამოწერა არ არის.', plan: 'ტარიფი', status: 'სტატუსი', until: 'ვადა',
    daysLeft: (n: number) => `დარჩა ${n} დღე`, source: 'წყარო',
    sources: { grant: 'საჩუქარი', payment: 'გადახდა' },
    subStatuses: { active: 'აქტიურია', past_due: 'ვადაგასულია', canceled: 'შეწყვეტილია' },
    payments: 'გადახდები', checkouts: 'განაცხადები', date: 'თარიღი', amount: 'თანხა', provider: 'გადახდის მეთოდი', state: 'სტატუსი',
    settle: 'დადასტურება', none: 'ჩანაწერები არ არის.',
    activity: 'აქტივობა', questions7d: 'კითხვები ბოლო 7 დღეში', questions30d: 'კითხვები ბოლო 30 დღეში',
    conversations: (n: string) => `დიალოგები: ${n}`, today: 'კითხვები დღეს',
    todayValue: (n: string, m: string) => `${m}-დან ${n}`, noData: 'მონაცემები არ არის', feedback: 'მიმართვები',
    actions: 'მოქმედებები', access: 'წვდომა', subscriptionGroup: 'გამოწერა', emails: 'წერილები',
    block: 'დაბლოკვა', unblock: 'განბლოკვა', changeRole: 'როლის შეცვლა',
    demoteFirst: 'ადმინისტრატორის დასაბლოკად ჯერ როლი უნდა მოხსნათ.',
    grant: 'ტარიფის ჩუქება ან გახანგრძლივება', recordPayment: 'გადახდის ჩაწერა', cancel: 'ვადაზე ადრე შეწყვეტა',
    sendReset: 'პაროლის აღდგენის წერილის გაგზავნა', sendVerification: 'დადასტურების წერილის გაგზავნა',
    confirmBlock: (u: string) => `დაიბლოკოს ${u}? ყველა აქტიური სესია დასრულდება.`,
    confirmUnblock: (u: string) => `განიბლოკოს ${u}?`,
    confirmRole: (u: string) => `შეიცვალოს ${u}-ის როლი?`, newRole: 'ახალი როლი',
    grantTitle: (u: string) => `ტარიფის ჩუქება ან გახანგრძლივება: ${u}`, daysLabel: 'დღეები', customDays: 'სხვა რაოდენობა',
    activeUntil: (d: string) => `აქტიური იქნება ${d}-მდე`,
    replaceWarning: (p: string) => `ამჟამად აქტიურია ${p} ტარიფი. მასზე დარჩენილი დრო დაიკარგება.`,
    replaceConfirm: 'მიმდინარე ტარიფის ჩანაცვლება',
    paymentTitle: (u: string) => `გადახდის ჩაწერა: ${u}`, monthsLabel: 'თვეები', amountLabel: 'ტარიფის ფასი',
    cancelTitle: (u: string) => `გამოწერის ვადაზე ადრე შეწყვეტა: ${u}`, category: 'შეწყვეტის მიზეზი',
    categories: { refund: 'თანხის დაბრუნება', mistaken_activation: 'შეცდომით გააქტიურება', fraud: 'თაღლითობა ან chargeback', other: 'სხვა' },
    cancelWarning: (n: number) => `გადახდილია კიდევ ${n} დღე. წვდომა მაშინვე დაიკეტება. თანხას სისტემის გარეთ დააბრუნებენ.`,
    confirmReset: (e: string) => `გაიგზავნოს პაროლის აღდგენის წერილი მისამართზე ${e}?`,
    confirmVerification: (e: string) => `გაიგზავნოს დადასტურების წერილი მისამართზე ${e}?`,
    done: 'მზადაა.', unchanged: 'ცვლილება არ მომხდარა: მდგომარეობა უკვე ასეთია.',
    emailSent: 'წერილი გაიგზავნა.', emailCooldown: 'წერილი ცოტა ხნის წინ უკვე გაიგზავნა, სცადეთ მოგვიანებით.',
  },
  errors: {
    user_not_found: 'მომხმარებელი ვერ მოიძებნა.', feedback_not_found: 'მიმართვა ვერ მოიძებნა.',
    cannot_block_self: 'საკუთარი თავის დაბლოკვა შეუძლებელია.', cannot_block_admin: 'ჯერ ადმინისტრატორის როლი მოხსენით.',
    cannot_demote_self: 'საკუთარი ადმინისტრატორის უფლების მოხსნა შეუძლებელია.', user_blocked: 'მომხმარებელი დაბლოკილია.',
    admin_has_business: 'ადმინისტრატორს უკვე აქვს Business ტარიფი.',
    active_plan_differs: 'აქტიურია სხვა ტარიფი, დაადასტურეთ ჩანაცვლება.',
    plan_unlimited: 'მიმდინარე ტარიფს დასრულების თარიღი არ აქვს.', no_active_subscription: 'აქტიური ფასიანი გამოწერა არ არის.',
    email_already_verified: 'ელფოსტა უკვე დადასტურებულია.', email_unavailable: 'ფოსტის გაგზავნა არ არის გამართული.',
  } satisfies Record<AdminErrorCode, string>,
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
    reasonRequired: 'Reason (required, at least 3 characters)',
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
      'user.blocked': 'Block', 'user.unblocked': 'Unblock', 'subscription.granted': 'Plan gift',
      'subscription.canceled': 'Early cancellation', 'user.password_reset_sent': 'Password reset email',
      'user.verification_sent': 'Verification email',
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
    status: 'Status', search: 'Search by email, login or name', planFilter: 'Plan', statusFilter: 'Status',
    sortLabel: 'Sort', reset: 'Reset filters', notFound: 'No one found.',
    plans: { free: 'Free', pro: 'Pro', business: 'Business', expiring: 'Expires within 7 days' },
    statuses: { active: 'Active', blocked: 'Blocked', unverified: 'Email not verified', admin: 'Administrator' },
    sorts: { created_desc: 'Newest first', last_login_desc: 'By last login', period_end_asc: 'By subscription end' },
    title: 'Users', settleTitle: 'Confirm a customer order after payment',
    checkoutPlaceholder: 'Order UUID from the customer account', settle: 'Confirm payment',
    months: (n: number) => `${n} mo`,
    days: (n: number) => `${n} days`,
    settled: (email: string, plan: string, until: string) => `Payment confirmed: ${email} → ${plan} until ${until}`,
    replayed: (email: string, plan: string, until: string) => `Already confirmed: ${email} → ${plan} until ${until}`,
    login: 'Username', email: 'Email', role: 'Role', plan: 'Plan', until: 'Subscription until', lastLogin: 'Last login',
    confirmSettle: 'Confirm payment for this order and grant access?',
  },
  card: {
    back: '← Back to list', notFound: 'User not found.',
    profile: 'Profile', fullName: 'Full name', registered: 'Registered', lastLogin: 'Last login', role: 'Role',
    subscription: 'Subscription', noSubscription: 'No subscription.', plan: 'Plan', status: 'Status', until: 'Until',
    daysLeft: (n: number) => `${n} days left`, source: 'Source',
    sources: { grant: 'gift', payment: 'payment' },
    subStatuses: { active: 'active', past_due: 'past due', canceled: 'ended' },
    payments: 'Payments', checkouts: 'Orders', date: 'Date', amount: 'Amount', provider: 'Method', state: 'Status',
    settle: 'Settle', none: 'No records.',
    activity: 'Activity', questions7d: 'Questions, 7 days', questions30d: 'Questions, 30 days',
    conversations: (n: string) => `conversations: ${n}`, today: 'Questions today',
    todayValue: (n: string, m: string) => `${n} of ${m}`, noData: 'no data', feedback: 'Feedback',
    actions: 'Actions', access: 'Access', subscriptionGroup: 'Subscription', emails: 'Emails',
    block: 'Block', unblock: 'Unblock', changeRole: 'Change role',
    demoteFirst: 'To block an administrator, remove the admin role first.',
    grant: 'Gift or extend', recordPayment: 'Record payment', cancel: 'End early',
    sendReset: 'Send password reset', sendVerification: 'Send verification email',
    confirmBlock: (u: string) => `Block ${u}? All active sessions will end.`,
    confirmUnblock: (u: string) => `Unblock ${u}?`,
    confirmRole: (u: string) => `Change ${u}'s role?`, newRole: 'New role',
    grantTitle: (u: string) => `Gift or extend a plan for ${u}`, daysLabel: 'Days', customDays: 'Custom',
    activeUntil: (d: string) => `Active until ${d}`,
    replaceWarning: (p: string) => `${p} is active now. Its remaining time will be lost.`,
    replaceConfirm: 'Replace the current plan',
    paymentTitle: (u: string) => `Record a payment from ${u}`, monthsLabel: 'Months', amountLabel: 'Plan price',
    cancelTitle: (u: string) => `End ${u}'s subscription early`, category: 'Reason for ending',
    categories: { refund: 'Refund', mistaken_activation: 'Mistaken activation', fraud: 'Fraud or chargeback', other: 'Other' },
    cancelWarning: (n: number) => `${n} paid days remain. Access ends now. Refunds are handled outside the system.`,
    confirmReset: (e: string) => `Send a password reset email to ${e}?`,
    confirmVerification: (e: string) => `Send a verification email to ${e}?`,
    done: 'Done.', unchanged: 'No change: already in that state.',
    emailSent: 'Email sent.', emailCooldown: 'An email was sent recently; try again later.',
  },
  errors: {
    user_not_found: 'User not found.', feedback_not_found: 'Feedback not found.',
    cannot_block_self: 'You cannot block yourself.', cannot_block_admin: 'Remove the admin role first.',
    cannot_demote_self: 'You cannot remove your own admin role.', user_blocked: 'The user is blocked.',
    admin_has_business: 'Administrators already have Business.',
    active_plan_differs: 'Another plan is active — confirm the replacement.',
    plan_unlimited: 'The current plan has no end date.', no_active_subscription: 'No active paid subscription.',
    email_already_verified: 'Email is already verified.', email_unavailable: 'Email delivery is not configured.',
  } satisfies Record<AdminErrorCode, string>,
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
  return new Date(/(?:[zZ]|[+-]\d\d:?\d\d)$/.test(value) ? value : `${value}Z`);
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

export function actionLabel(c: AdminCopy, action: string): string {
  return (c.audit.actions as Record<string, string>)[action] ?? action;
}
