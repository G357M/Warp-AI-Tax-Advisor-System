import type { Lang } from './i18n';

export interface ReconciliationItem {
  id: string;
  user_id: string;
  plan: string;
  amount_minor: number;
  currency: string;
  provider: string;
  provider_order_id: string | null;
  status: string;
  provider_status: string | null;
  reason: string | null;
  settled_payment_id: string | null;
  created_at: string;
  updated_at: string;
  expires_at: string;
  provider_checked_at: string | null;
}

export interface ReconciliationQueue {
  items: ReconciliationItem[];
  next_offset: number | null;
}

export interface ReconciliationDetail {
  checkout: ReconciliationItem;
  events: {
    id: string;
    provider_status: string;
    payload_sha256: string;
    processing_status: string;
    error_code: string | null;
    created_at: string;
    processed_at: string | null;
  }[];
  events_truncated: boolean;
}

const en = {
  title: 'Payment reconciliation', intro: 'Review uncertain payments and compare the recorded evidence with bank records.',
  refresh: 'Refresh queue', queue: 'Orders to review', details: 'Order details', select: 'Select an order to see its evidence.',
  loading: 'Loading orders…', loadingDetail: 'Loading order details…', empty: 'No orders to review',
  emptyBody: 'The current queue has no unresolved payments. Refresh it to check again.',
  pageEmpty: 'No orders on this page. Return to the first page to refresh the queue.', first: 'First page',
  unavailable: 'Could not load payment evidence. Try again.', forbidden: 'Administrator access is required.',
  signedOut: 'Your session has expired. Sign in again.', missing: 'This order is no longer available.',
  retry: 'Try again', login: 'Sign in', previous: 'Previous', next: 'Next', page: 'Page',
  rows: 'Orders on this page', order: 'Order', user: 'Account ID', bankOrder: 'Bank order',
  amount: 'Amount', plan: 'Plan', provider: 'Provider', created: 'Created', checked: 'Last bank check',
  expires: 'Order expiry', updated: 'Updated', noValue: 'Not recorded', bankStatus: 'Bank status',
  checkoutStatus: 'Order status', payment: 'Payment reference', recorded: 'Credit is recorded',
  unrecorded: 'Credit is not confirmed', events: 'Verified events', noEvents: 'No verified events recorded.',
  truncated: 'Showing the latest 50 events. Older evidence remains in the database.',
  readOnly: 'Viewing this page does not contact the bank or change payments and access.',
  resolution: 'Resolve refunds and review holds through the separately audited operator process.',
  timezone: 'All dates and times are UTC.', eventDetails: 'Evidence details', errorCode: 'Review code',
  digest: 'Evidence SHA-256', processed: 'Processed', eventId: 'Event ID', noReason: 'No review reason recorded',
  review: 'Manual review', unknown: 'Payment result unknown', overdue: 'Bank confirmation overdue',
  reviewHelp: 'Compare the order, amount and event history with bank records. Keep the review hold until an audited decision.',
  unknownHelp: 'Find the merchant order by its checkout ID before creating another charge.',
  overdueHelp: 'Check the bank order. Local expiry alone does not prove that the bank rejected payment.',
  noReasonHelp: 'This order may have left the queue. Its recorded evidence remains available here.',
};

type Copy = { [K in keyof typeof en]: string };
export const reconciliationCopy: Record<Lang, Copy> = {
  en,
  ru: {
    title: 'Сверка платежей', intro: 'Проверьте неоднозначные платежи и сопоставьте сохранённые сведения с данными банка.',
    refresh: 'Обновить очередь', queue: 'Заявки для проверки', details: 'Детали заявки', select: 'Выберите заявку, чтобы посмотреть сведения о платеже.',
    loading: 'Загружаем заявки…', loadingDetail: 'Загружаем детали заявки…', empty: 'Нет заявок для проверки',
    emptyBody: 'В текущей очереди нет неразрешённых платежей. Обновите её для повторной проверки.',
    pageEmpty: 'На этой странице нет заявок. Вернитесь на первую страницу, чтобы обновить очередь.', first: 'На первую страницу',
    unavailable: 'Не удалось загрузить сведения о платежах. Повторите попытку.', forbidden: 'Требуется доступ администратора.',
    signedOut: 'Сессия завершена. Войдите снова.', missing: 'Эта заявка больше недоступна.',
    retry: 'Повторить', login: 'Войти', previous: 'Назад', next: 'Далее', page: 'Страница',
    rows: 'Заявок на странице', order: 'Заявка', user: 'ID аккаунта', bankOrder: 'Заказ в банке',
    amount: 'Сумма', plan: 'Тариф', provider: 'Способ оплаты', created: 'Создана', checked: 'Последняя проверка банка',
    expires: 'Срок заявки', updated: 'Обновлена', noValue: 'Не зафиксировано', bankStatus: 'Статус банка',
    checkoutStatus: 'Статус заявки', payment: 'ID платежа', recorded: 'Зачисление зарегистрировано',
    unrecorded: 'Зачисление не подтверждено', events: 'Проверенные события', noEvents: 'Проверенных событий пока нет.',
    truncated: 'Показаны последние 50 событий. Более ранние сведения сохранены в базе.',
    readOnly: 'Просмотр страницы не обращается в банк и не меняет платежи или доступ.',
    resolution: 'Возвраты и снятие ручной проверки требуют отдельного аудируемого решения оператора.',
    timezone: 'Все даты и время указаны в UTC.', eventDetails: 'Сведения о событии', errorCode: 'Код проверки',
    digest: 'SHA-256 подтверждения', processed: 'Обработано', eventId: 'ID события', noReason: 'Причина проверки не указана',
    review: 'Ручная проверка', unknown: 'Результат платежа неизвестен', overdue: 'Банк не подтвердил в срок',
    reviewHelp: 'Сопоставьте заказ, сумму и события с данными банка. Сохраните ручную проверку до аудируемого решения.',
    unknownHelp: 'Найдите заказ продавца по ID заявки, прежде чем создавать повторное списание.',
    overdueHelp: 'Проверьте заказ в банке. Истечение срока заявки само по себе не означает отказ банка.',
    noReasonHelp: 'Заявка могла выйти из очереди. Сохранённые сведения остаются доступны здесь.',
  },
  ka: {
    title: 'გადახდების შეჯერება', intro: 'შეამოწმეთ გაურკვეველი გადახდები და შეადარეთ შენახული ინფორმაცია ბანკის მონაცემებს.',
    refresh: 'რიგის განახლება', queue: 'შესამოწმებელი განაცხადები', details: 'განაცხადის დეტალები', select: 'გადახდის ინფორმაციის სანახავად აირჩიეთ განაცხადი.',
    loading: 'განაცხადები იტვირთება…', loadingDetail: 'განაცხადის დეტალები იტვირთება…', empty: 'შესამოწმებელი განაცხადები არ არის',
    emptyBody: 'მიმდინარე რიგში გადაუჭრელი გადახდები არ არის. ხელახლა შესამოწმებლად განაახლეთ რიგი.',
    pageEmpty: 'ამ გვერდზე განაცხადები არ არის. რიგის განსაახლებლად დაბრუნდით პირველ გვერდზე.', first: 'პირველი გვერდი',
    unavailable: 'გადახდის ინფორმაცია ვერ ჩაიტვირთა. სცადეთ ხელახლა.', forbidden: 'საჭიროა ადმინისტრატორის წვდომა.',
    signedOut: 'სესია დასრულდა. შედით ხელახლა.', missing: 'ეს განაცხადი აღარ არის ხელმისაწვდომი.',
    retry: 'ხელახლა ცდა', login: 'შესვლა', previous: 'წინა', next: 'შემდეგი', page: 'გვერდი',
    rows: 'განაცხადები გვერდზე', order: 'განაცხადი', user: 'ანგარიშის ID', bankOrder: 'ბანკის შეკვეთა',
    amount: 'თანხა', plan: 'პაკეტი', provider: 'გადახდის მეთოდი', created: 'შექმნილია', checked: 'ბანკის ბოლო შემოწმება',
    expires: 'განაცხადის ვადა', updated: 'განახლებულია', noValue: 'არ არის დაფიქსირებული', bankStatus: 'ბანკის სტატუსი',
    checkoutStatus: 'განაცხადის სტატუსი', payment: 'გადახდის ID', recorded: 'ჩარიცხვა დაფიქსირებულია',
    unrecorded: 'ჩარიცხვა დადასტურებული არ არის', events: 'შემოწმებული მოვლენები', noEvents: 'შემოწმებული მოვლენები ჯერ არ არის.',
    truncated: 'ნაჩვენებია ბოლო 50 მოვლენა. ძველი ინფორმაცია ინახება მონაცემთა ბაზაში.',
    readOnly: 'გვერდის ნახვა არ უკავშირდება ბანკს და არ ცვლის გადახდებს ან წვდომას.',
    resolution: 'დაბრუნება და ხელით შემოწმების დასრულება მოითხოვს ოპერატორის ცალკე აუდიტირებად გადაწყვეტილებას.',
    timezone: 'ყველა თარიღი და დრო მოცემულია UTC-ში.', eventDetails: 'მოვლენის ინფორმაცია', errorCode: 'შემოწმების კოდი',
    digest: 'დადასტურების SHA-256', processed: 'დამუშავებულია', eventId: 'მოვლენის ID', noReason: 'შემოწმების მიზეზი მითითებული არ არის',
    review: 'ხელით შემოწმება', unknown: 'გადახდის შედეგი უცნობია', overdue: 'ბანკის დადასტურება დაგვიანებულია',
    reviewHelp: 'შეადარეთ შეკვეთა, თანხა და მოვლენები ბანკის მონაცემებს. აუდიტირებად გადაწყვეტილებამდე შეინარჩუნეთ ხელით შემოწმება.',
    unknownHelp: 'ახალი ჩამოჭრის შექმნამდე იპოვეთ გამყიდველის შეკვეთა განაცხადის ID-ით.',
    overdueHelp: 'შეამოწმეთ შეკვეთა ბანკში. განაცხადის ვადის გასვლა თავისთავად ბანკის უარს არ ნიშნავს.',
    noReasonHelp: 'განაცხადი შესაძლოა რიგიდან გავიდა. შენახული ინფორმაცია აქ ხელმისაწვდომია.',
  },
};

export function reviewReason(reason: string | null, lang: Lang) {
  const c = reconciliationCopy[lang];
  if (reason === 'provider_review') return { title: c.review, help: c.reviewHelp };
  if (reason === 'provider_unknown') return { title: c.unknown, help: c.unknownHelp };
  if (reason === 'payment_verification_overdue') return { title: c.overdue, help: c.overdueHelp };
  return { title: reason || c.noReason, help: c.noReasonHelp };
}
