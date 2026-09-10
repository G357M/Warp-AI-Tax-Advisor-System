import type { Lang } from './i18n';

export type ReviewAction = 'keep_review' | 'confirm_payment' | 'confirm_no_charge';
export type AccessEffect = 'unchanged' | 'grant_period';
export interface ReviewPreview {
  state_sha256: string;
  provider_sha256: string | null;
  provider_evidence: { status: string; amount_minor: number; currency: string; provider_order_id: string } | null;
  before: { checkout: { months: string }; subscription: { period_end: string | null; plan: string } | null };
  actions: Partial<Record<ReviewAction, AccessEffect>>;
}
export interface ReviewDecision {
  id: string; actor_id: string; action: ReviewAction; reason: string; access_effect: AccessEffect; created_at: string;
}
export interface DecisionBody {
  action: ReviewAction; reason: string; expected_state_sha256: string;
  expected_provider_sha256: string | null; expected_access_effect: AccessEffect;
}
export interface DecisionHistory { items: ReviewDecision[]; next_offset: number | null }

const en = {
  title: 'Operator decision', intro: 'Record a reason to retain the hold, or check the bank before resolving the order.',
  hold: 'Prepare review note', verify: 'Check bank for a decision', checking: 'Preparing evidence…',
  action: 'Decision', keep_review: 'Keep under review', confirm_payment: 'Confirm payment', confirm_no_charge: 'Confirm bank failure or expiry',
  reason: 'Reason and evidence checked', reasonHint: '10–2,000 characters. Do not include secrets, card details or personal contact information.',
  unchanged: 'Customer access and the paid period will remain unchanged.',
  granted: 'This decision credited the payment and granted one Pro period.',
  unchangedPast: 'This decision did not change customer access or the paid period.',
  historyLoading: 'Loading the decision journal…',
  grant: 'Credit this payment once and grant Pro for {days} days. An unexpired Pro period is extended; otherwise the period starts when saved.',
  confirm: 'I have checked the evidence and the effect on access.', save: 'Record decision', saving: 'Recording…',
  cancel: 'Cancel preview', saved: 'Decision recorded', refresh: 'Refresh order evidence',
  bank: 'Fresh bank result', noResolution: 'Only continued review is supported by this evidence.',
  unavailable: 'Could not prepare the evidence. Try again, or prepare a review note without a bank call.',
  stale: 'The evidence changed or this decision is no longer supported. Prepare a new preview.',
  uncertain: 'The response was not received. Retry this same decision to retrieve or record its result safely.',
  retry: 'Retry same decision', invalid: 'Check the reason and prepare a new preview.',
  history: 'Decision journal', empty: 'No operator decisions recorded.', historyError: 'Could not load the journal.',
  load: 'Load journal', more: 'Older decisions', actor: 'Operator ID', id: 'Decision ID',
  refund: 'Returns, partial returns and preauthorizations stay under review. This form does not send refunds or revoke access.',
};
type Copy = { [K in keyof typeof en]: string };
export const reviewCopy: Record<Lang, Copy> = {
  en,
  ru: {
    title: 'Решение оператора', intro: 'Укажите причину продолжения проверки или проверьте банк перед завершением заявки.',
    hold: 'Подготовить запись проверки', verify: 'Проверить банк для решения', checking: 'Готовим сведения…',
    action: 'Решение', keep_review: 'Оставить на проверке', confirm_payment: 'Подтвердить оплату', confirm_no_charge: 'Подтвердить отказ банка или истечение срока',
    reason: 'Обоснование и проверенные сведения', reasonHint: '10–2 000 символов. Не указывайте секреты, реквизиты карты и личные контакты.',
    unchanged: 'Доступ клиента и оплаченный период останутся без изменений.',
    granted: 'Это решение зачло платёж и предоставило один период Pro.',
    unchangedPast: 'Это решение не изменило доступ клиента и оплаченный период.',
    historyLoading: 'Загружаем журнал решений…',
    grant: 'Зачесть платёж один раз и предоставить Pro на {days} дней. Действующий период Pro продлевается; иначе период начнётся при сохранении.',
    confirm: 'Я проверил сведения и влияние решения на доступ.', save: 'Записать решение', saving: 'Записываем…',
    cancel: 'Отменить подготовку', saved: 'Решение записано', refresh: 'Обновить сведения о заявке',
    bank: 'Свежий результат банка', noResolution: 'Эти сведения позволяют только продолжить ручную проверку.',
    unavailable: 'Не удалось подготовить сведения. Повторите попытку или подготовьте запись проверки без обращения в банк.',
    stale: 'Сведения изменились или решение больше недоступно. Подготовьте новый просмотр.',
    uncertain: 'Ответ не получен. Повторите то же решение, чтобы безопасно получить или записать результат.',
    retry: 'Повторить то же решение', invalid: 'Проверьте обоснование и подготовьте новый просмотр.',
    history: 'Журнал решений', empty: 'Решений оператора пока нет.', historyError: 'Не удалось загрузить журнал.',
    load: 'Загрузить журнал', more: 'Более ранние решения', actor: 'ID оператора', id: 'ID решения',
    refund: 'Возвраты, частичные возвраты и предавторизации остаются на проверке. Эта форма не отправляет возврат и не отзывает доступ.',
  },
  ka: {
    title: 'ოპერატორის გადაწყვეტილება', intro: 'მიუთითეთ შემოწმების გაგრძელების მიზეზი ან განაცხადის დასრულებამდე გადაამოწმეთ ბანკი.',
    hold: 'შემოწმების ჩანაწერის მომზადება', verify: 'ბანკის შემოწმება გადაწყვეტილებისთვის', checking: 'ინფორმაცია მზადდება…',
    action: 'გადაწყვეტილება', keep_review: 'დარჩეს შემოწმებაზე', confirm_payment: 'გადახდის დადასტურება', confirm_no_charge: 'ბანკის უარის ან ვადის გასვლის დადასტურება',
    reason: 'დასაბუთება და შემოწმებული ინფორმაცია', reasonHint: '10–2 000 სიმბოლო. არ მიუთითოთ საიდუმლოებები, ბარათის მონაცემები ან პირადი საკონტაქტო ინფორმაცია.',
    unchanged: 'კლიენტის წვდომა და გადახდილი პერიოდი უცვლელი დარჩება.',
    granted: 'ამ გადაწყვეტილებამ გადახდა ჩარიცხა და Pro-ის ერთი პერიოდი მიანიჭა.',
    unchangedPast: 'ამ გადაწყვეტილებას კლიენტის წვდომა და გადახდილი პერიოდი არ შეუცვლია.',
    historyLoading: 'გადაწყვეტილებების ჟურნალი იტვირთება…',
    grant: 'გადახდა ჩაირიცხება ერთხელ და Pro მიენიჭება {days} დღით. მოქმედი Pro პერიოდი გაგრძელდება; სხვა შემთხვევაში პერიოდი შენახვისას დაიწყება.',
    confirm: 'შევამოწმე ინფორმაცია და გადაწყვეტილების გავლენა წვდომაზე.', save: 'გადაწყვეტილების ჩაწერა', saving: 'იწერება…',
    cancel: 'მომზადების გაუქმება', saved: 'გადაწყვეტილება ჩაიწერა', refresh: 'განაცხადის ინფორმაციის განახლება',
    bank: 'ბანკის ახალი შედეგი', noResolution: 'ეს ინფორმაცია მხოლოდ ხელით შემოწმების გაგრძელების საშუალებას იძლევა.',
    unavailable: 'ინფორმაცია ვერ მომზადდა. სცადეთ ხელახლა ან მოამზადეთ შემოწმების ჩანაწერი ბანკთან დაკავშირების გარეშე.',
    stale: 'ინფორმაცია შეიცვალა ან გადაწყვეტილება აღარ არის ხელმისაწვდომი. მოამზადეთ ახალი გადახედვა.',
    uncertain: 'პასუხი არ არის მიღებული. შედეგის უსაფრთხოდ მისაღებად ან ჩასაწერად გაიმეორეთ იგივე გადაწყვეტილება.',
    retry: 'იგივე გადაწყვეტილების გამეორება', invalid: 'შეამოწმეთ დასაბუთება და მოამზადეთ ახალი გადახედვა.',
    history: 'გადაწყვეტილებების ჟურნალი', empty: 'ოპერატორის გადაწყვეტილებები ჯერ არ არის.', historyError: 'ჟურნალი ვერ ჩაიტვირთა.',
    load: 'ჟურნალის ჩატვირთვა', more: 'ძველი გადაწყვეტილებები', actor: 'ოპერატორის ID', id: 'გადაწყვეტილების ID',
    refund: 'დაბრუნება, ნაწილობრივი დაბრუნება და წინასწარი ავტორიზაცია შემოწმებაზე რჩება. ეს ფორმა არ აგზავნის დაბრუნებას და არ აუქმებს წვდომას.',
  },
};
