/**
 * Subscription plans shown on the landing page.
 * Prices are placeholders until final GEL pricing is confirmed — edit here only.
 */
export interface Plan {
  id: 'free' | 'pro' | 'business';
  name: string;
  priceGel: number;
  period: string;
  tagline: string;
  features: string[];
  highlighted?: boolean;
}

export const PLANS: Plan[] = [
  {
    id: 'free',
    name: 'Free',
    priceGel: 0,
    period: '',
    tagline: 'Познакомиться с сервисом',
    features: [
      '5 вопросов в день',
      'Ответы с точными источниками',
      'Без истории диалогов',
    ],
  },
  {
    id: 'pro',
    name: 'Pro',
    priceGel: 49,
    period: '/мес',
    tagline: 'Для бухгалтера и предпринимателя',
    highlighted: true,
    features: [
      'Вопросы без ограничений',
      'История диалогов',
      'Статистика решений по спорам',
      'Таймлайн изменений законов',
    ],
  },
  {
    id: 'business',
    name: 'Business',
    priceGel: 149,
    period: '/мес',
    tagline: 'Для компании и консалтинга',
    features: [
      'Всё из Pro',
      'До 5 пользователей',
      'Приоритетная поддержка',
    ],
  },
];
