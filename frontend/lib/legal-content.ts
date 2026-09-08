import type { Lang } from '@/lib/i18n';

export const LEGAL_TERMS_VERSION = '2026-09-08';

export const OPERATOR = {
  legalName: 'Modern LLC',
  identificationCode: '431177120',
  address: 'Telavi, Kurdgelauri vil.',
  email: 'info@tax-advisor.ge',
  phone: '+995 550 052 050',
};

export type LegalSlug = 'terms' | 'refunds' | 'privacy' | 'delivery' | 'contact';

export interface LegalSection {
  id: string;
  title: string;
  body?: string[];
  bullets?: string[];
}

export interface LegalDocument {
  label: string;
  title: string;
  summary: string;
  updated: string;
  sections: LegalSection[];
  sources?: { label: string; href: string }[];
}

export const LEGAL_NAV: Record<Lang, Record<LegalSlug, string>> = {
  ru: {
    terms: 'Условия использования',
    refunds: 'Возврат и отмена',
    privacy: 'Конфиденциальность',
    delivery: 'Активация доступа',
    contact: 'Контакты',
  },
  ka: {
    terms: 'გამოყენების პირობები',
    refunds: 'თანხის დაბრუნება და გაუქმება',
    privacy: 'კონფიდენციალურობა',
    delivery: 'წვდომის გააქტიურება',
    contact: 'კონტაქტი',
  },
  en: {
    terms: 'Terms of use',
    refunds: 'Refunds and cancellation',
    privacy: 'Privacy',
    delivery: 'Access activation',
    contact: 'Contact',
  },
};

const commonSources = {
  consumer: 'https://matsne.gov.ge/ka/document/view/5420598',
  privacy: 'https://www.matsne.gov.ge/ka/document/view/5827307',
};

export const LEGAL_CONTENT: Record<Lang, Record<LegalSlug, LegalDocument>> = {
  ru: {
    terms: {
      label: 'Юридическая информация',
      title: 'Условия использования',
      summary: 'Правила доступа к Tax Advisor, оплаты пакетов и использования юридической информации.',
      updated: 'Версия 2026-09-08 · действует с 8 сентября 2026 года',
      sections: [
        {
          id: 'operator',
          title: 'Поставщик услуги',
          body: [
            'Tax Advisor предоставляет Modern LLC, идентификационный код 431177120, юридический адрес: Telavi, Kurdgelauri vil. Контакты: info@tax-advisor.ge, +995 550 052 050.',
            'Modern LLC не зарегистрирована как плательщик НДС. Указанные цены являются окончательными; НДС отдельно не начисляется и не выделяется.',
          ],
        },
        {
          id: 'service',
          title: 'Что предоставляет Tax Advisor',
          body: [
            'Сервис помогает искать и понимать налоговое и смежное право Грузии, показывает официальные источники, историю изменений законодательства и практику налоговых споров.',
            'Ответы носят информационный характер и не создают отношений адвокат — клиент, не заменяют индивидуальную юридическую, налоговую или бухгалтерскую консультацию. Перед решением с существенными последствиями проверьте дату, применимую редакцию нормы и обстоятельства дела.',
          ],
        },
        {
          id: 'plans',
          title: 'Пакеты, цена и срок',
          bullets: [
            'Pro — 49 GEL за 30 дней.',
            'Business — 149 GEL за 30 дней.',
            'Цена и пакет фиксируются в заявке до перехода к оплате.',
            'Доступ не продлевается автоматически. Для следующего 30-дневного периода пользователь создаёт и оплачивает новую заявку.',
          ],
        },
        {
          id: 'payment',
          title: 'Оплата и активация',
          body: [
            'Доступны банковский перевод по счёту и, после активации merchant-аккаунта, оплата на защищённой странице TBC. Tax Advisor не получает и не хранит данные банковской карты.',
            'Платный доступ активируется в кабинете только после подтверждения поступления средств или серверной проверки успешного статуса банка. Письмо об активации является дополнительным уведомлением и отправляется только при работающей почтовой доставке.',
          ],
        },
        {
          id: 'account',
          title: 'Аккаунт и допустимое использование',
          bullets: [
            'Указывайте достоверные данные и защищайте доступ к аккаунту.',
            'Не пытайтесь обходить лимиты, нарушать работу сервиса, извлекать базу массово или использовать сервис для незаконных действий.',
            'При подтверждённой угрозе безопасности доступ может быть временно ограничен; мы сообщим причину и способ обращения, если это не запрещено законом.',
          ],
        },
        {
          id: 'rights',
          title: 'Отказ, возврат и применимое право',
          body: [
            'Правила добровольной 24-часовой гарантии, законного отказа и возврата опубликованы отдельно. Эти условия не ограничивают обязательные права потребителя по законодательству Грузии.',
            'К отношениям применяется право Грузии. Сначала направьте претензию на info@tax-advisor.ge; право обратиться в компетентный орган или суд сохраняется.',
          ],
        },
      ],
      sources: [{ label: 'Закон Грузии «О защите прав потребителей»', href: commonSources.consumer }],
    },
    refunds: {
      label: 'Оплата и защита клиента',
      title: 'Возврат и отмена',
      summary: 'Добровольная 24-часовая гарантия Modern LLC действует дополнительно к обязательным правам потребителя.',
      updated: 'Версия 2026-09-08 · действует с 8 сентября 2026 года',
      sections: [
        {
          id: 'guarantee',
          title: 'Добровольная гарантия 24 часа',
          body: [
            'Пользователь может запросить возврат первого платежа за Pro или Business в течение 24 часов после подтверждения оплаты. Объяснять причину необязательно. Гарантия применяется один раз к первому платному периоду аккаунта и не отменяет прав, которые предоставляет закон.',
          ],
        },
        {
          id: 'other-grounds',
          title: 'Другие основания',
          bullets: [
            'Двойное, ошибочное или несанкционированное списание.',
            'Платный доступ не активирован по вине платформы и проблема не устранена в разумный срок.',
            'Существенный технический недостаток не позволяет пользоваться оплаченной услугой и не был устранён после обращения.',
            'Любое иное основание, прямо предусмотренное применимым законодательством.',
          ],
        },
        {
          id: 'consumer-right',
          title: 'Право потребителя на отказ',
          body: [
            'Если пользователь является потребителем по закону Грузии, к дистанционному договору обычно применяется 14-дневное право на отказ. 24-часовая гарантия его не сокращает.',
            'При оформлении пользователь отдельно просит начать цифровую услугу немедленно и подтверждает ознакомление с условиями. Исключение из права на отказ применяется только в той мере, в какой оно действительно допускается законом, включая требования о предварительном согласии и уведомлении. Для Business-покупки в рамках предпринимательской или профессиональной деятельности потребительский режим может не применяться.',
          ],
        },
        {
          id: 'request',
          title: 'Как запросить возврат',
          body: [
            'Напишите на info@tax-advisor.ge с email аккаунта. Укажите номер заявки или платежа, пакет и дату оплаты. Не отправляйте номер карты, CVV, пароль или банковские коды.',
            'Можно использовать формулировку: «Прошу отказаться от договора/вернуть платёж за пакет [пакет], заявка [номер], оплата [дата]». Мы подтвердим получение обращения на доступный канал связи.',
          ],
        },
        {
          id: 'timing',
          title: 'Срок и способ возврата',
          body: [
            'После подтверждения основания возврат производится тем же способом оплаты, если стороны не согласовали иное, без неоправданной задержки и не позднее 14 календарных дней в случаях, когда такой срок требует закон. Фактическое зачисление может зависеть от банка.',
            'До появления отдельного операторского инструмента возвраты рассматриваются вручную; сайт не заявляет, что возврат выполнен, пока операция не подтверждена. После полного возврата платный доступ прекращается.',
          ],
        },
        {
          id: 'cancellation',
          title: 'Отмена следующего периода',
          body: [
            'Pro и Business предоставляются на фиксированные 30 дней без автопродления. Поэтому отдельная отмена следующего периода не нужна: новое списание не выполняется, пока пользователь сам не создаст и не оплатит новую заявку. Текущий оплаченный доступ действует до указанной в кабинете даты, если платёж не был возвращён.',
          ],
        },
      ],
      sources: [{ label: 'Закон Грузии «О защите прав потребителей», статьи 13–15', href: commonSources.consumer }],
    },
    privacy: {
      label: 'Защита данных',
      title: 'Политика конфиденциальности',
      summary: 'Какие данные использует Tax Advisor, зачем они нужны и как реализовать свои права.',
      updated: 'Версия 2026-09-08 · действует с 8 сентября 2026 года',
      sections: [
        {
          id: 'controller',
          title: 'Контролёр данных',
          body: ['Контролёр персональных данных — Modern LLC, код 431177120. Вопросы и запросы: info@tax-advisor.ge, +995 550 052 050.'],
        },
        {
          id: 'data',
          title: 'Какие данные обрабатываются',
          bullets: [
            'Данные аккаунта и контакта: email, имя пользователя, указанное имя, защищённый хеш пароля и статус проверки email.',
            'Содержание вопросов, диалогов и обратной связи, если пользователь их отправляет или сохраняет.',
            'Сведения об оплате: пакет, сумма, валюта, статус, идентификаторы заявки и операции. Данные карты Tax Advisor не получает.',
            'Технические журналы, IP-адрес и сигналы безопасности, необходимые для защиты сервиса, диагностики и ограничения злоупотреблений.',
          ],
        },
        {
          id: 'purposes',
          title: 'Цели и основания',
          body: [
            'Данные нужны для исполнения договора, предоставления ответов и истории, активации оплаченного доступа, поддержки, безопасности, выполнения юридических обязанностей и защиты законных требований. Там, где закон требует согласия, оно запрашивается отдельно и может быть отозвано на будущее.',
          ],
        },
        {
          id: 'recipients',
          title: 'Получатели и поставщики',
          body: [
            'В необходимом объёме данные могут обрабатываться поставщиками хостинга, баз данных, AI API, защиты инфраструктуры, банковской оплаты (включая TBC) и почтовой доставки после её включения. Поставщики получают только данные, нужные для их функции, и обязаны соблюдать применимые требования защиты данных.',
          ],
        },
        {
          id: 'retention',
          title: 'Хранение и безопасность',
          body: [
            'Данные хранятся не дольше, чем необходимо для соответствующей цели, договора, обязательной отчётности, разрешения спора и резервного восстановления. Конкретный срок зависит от категории данных и законного основания. Применяются разграничение доступа, хеширование паролей, журналирование, резервные копии и контроль целостности.',
          ],
        },
        {
          id: 'rights',
          title: 'Ваши права',
          body: [
            'В пределах закона можно запросить информацию и доступ, исправление, обновление, прекращение обработки, удаление или уничтожение, блокирование, перенос данных, возразить против обработки и обжаловать решение. Для защиты аккаунта мы можем проверить личность заявителя.',
            'Направьте запрос на info@tax-advisor.ge. Можно также обратиться в уполномоченный орган или суд в порядке, установленном законом.',
          ],
        },
      ],
      sources: [{ label: 'Закон Грузии «О защите персональных данных»', href: commonSources.privacy }],
    },
    delivery: {
      label: 'Цифровая услуга',
      title: 'Активация доступа',
      summary: 'Tax Advisor предоставляет цифровой доступ — физической доставки и стоимости доставки нет.',
      updated: 'Версия 2026-09-08 · действует с 8 сентября 2026 года',
      sections: [
        {
          id: 'scope',
          title: 'Что доставляется',
          body: ['Результат покупки — доступ к функциям пакета Pro или Business в аккаунте Tax Advisor на 30 дней. Товар по почте или курьером не отправляется, плата за доставку не взимается.'],
        },
        {
          id: 'online',
          title: 'Оплата TBC',
          body: ['После успешной оплаты на странице TBC сервер Tax Advisor самостоятельно проверяет статус, сумму и валюту у банка. При точном совпадении доступ обычно активируется в кабинете сразу. Возврат браузера со страницы банка сам по себе не является подтверждением оплаты.'],
        },
        {
          id: 'invoice',
          title: 'Банковский перевод',
          body: ['При оплате по счёту доступ активируется после проверки поступления средств оператором. Номер заявки из кабинета нужно указать в обращении или назначении платежа.'],
        },
        {
          id: 'delay',
          title: 'Если доступ не появился',
          body: ['Статус банка может оставаться в обработке или потребовать ручной сверки. Если после подтверждённого списания доступ не активировался в течение 30 минут, напишите на info@tax-advisor.ge и укажите email аккаунта и номер заявки. Не отправляйте данные карты или пароль.'],
        },
        {
          id: 'notice',
          title: 'Уведомление',
          body: ['Авторитетным подтверждением доступа является статус и дата окончания в кабинете. Email об активации отправляется дополнительно только при работающей почтовой доставке; отсутствие письма не отменяет уже активированный доступ.'],
        },
      ],
    },
    contact: {
      label: 'Modern LLC',
      title: 'Контакты и реквизиты',
      summary: 'Единый контакт для поддержки, претензий, возвратов и вопросов о персональных данных.',
      updated: 'Актуально с 8 сентября 2026 года',
      sections: [
        { id: 'details', title: 'Юридическое лицо', bullets: ['Modern LLC', 'Идентификационный код: 431177120', 'Юридический адрес: Telavi, Kurdgelauri vil.', 'Не зарегистрирована как плательщик НДС.'] },
        { id: 'channels', title: 'Каналы связи', bullets: ['Email: info@tax-advisor.ge', 'Телефон: +995 550 052 050'] },
        { id: 'support', title: 'Чтобы мы помогли быстрее', body: ['Укажите email аккаунта, краткое описание вопроса и, для оплаты, номер заявки. Никогда не отправляйте пароль, полный номер карты, CVV или одноразовый банковский код.'] },
      ],
    },
  },
  ka: {
    terms: {
      label: 'იურიდიული ინფორმაცია', title: 'გამოყენების პირობები', summary: 'Tax Advisor-ზე წვდომის, პაკეტების გადახდისა და იურიდიული ინფორმაციის გამოყენების წესები.', updated: 'ვერსია 2026-09-08 · მოქმედებს 2026 წლის 8 სექტემბრიდან',
      sections: [
        { id: 'operator', title: 'მომსახურების მიმწოდებელი', body: ['Tax Advisor-ის მომსახურებას გთავაზობთ Modern LLC, საიდენტიფიკაციო კოდი 431177120, იურიდიული მისამართი: Telavi, Kurdgelauri vil. კონტაქტი: info@tax-advisor.ge, +995 550 052 050.', 'Modern LLC არ არის დღგ-ის გადამხდელად რეგისტრირებული. მითითებული ფასები საბოლოოა; დღგ ცალკე არ ერიცხება და არ გამოიყოფა.'] },
        { id: 'service', title: 'რას გთავაზობთ Tax Advisor', body: ['სერვისი გეხმარებათ საქართველოს საგადასახადო და მომიჯნავე სამართლის მოძიებასა და გაგებაში და გაჩვენებთ ოფიციალურ წყაროებს, კანონმდებლობის ცვლილებების ისტორიასა და საგადასახადო დავების პრაქტიკას.', 'პასუხები საინფორმაციო ხასიათისაა, არ წარმოშობს ადვოკატსა და კლიენტს შორის ურთიერთობას და არ ცვლის ინდივიდუალურ იურიდიულ, საგადასახადო ან საბუღალტრო კონსულტაციას. მნიშვნელოვანი გადაწყვეტილების მიღებამდე გადაამოწმეთ თარიღი, ნორმის შესაბამისი რედაქცია და საქმის გარემოებები.'] },
        { id: 'plans', title: 'პაკეტები, ფასი და ვადა', bullets: ['Pro — 49 GEL 30 დღით.', 'Business — 149 GEL 30 დღით.', 'ფასი და პაკეტი გადახდამდე განაცხადში ფიქსირდება.', 'წვდომა ავტომატურად არ განახლდება. მომდევნო 30-დღიანი პერიოდისთვის მომხმარებელი ახალ განაცხადს ქმნის და იხდის.'] },
        { id: 'payment', title: 'გადახდა და გააქტიურება', body: ['ხელმისაწვდომია ინვოისით საბანკო გადარიცხვა და, merchant-ანგარიშის გააქტიურების შემდეგ, TBC-ის დაცულ გვერდზე გადახდა. Tax Advisor ბარათის მონაცემებს არ იღებს და არ ინახავს.', 'ფასიანი წვდომა კაბინეტში მხოლოდ თანხის მიღების დადასტურების ან ბანკის წარმატებული სტატუსის სერვერული შემოწმების შემდეგ აქტიურდება. ელფოსტა დამატებითი შეტყობინებაა და მხოლოდ მოქმედი საფოსტო მიწოდებისას იგზავნება.'] },
        { id: 'account', title: 'ანგარიში და დასაშვები გამოყენება', bullets: ['მიუთითეთ სწორი მონაცემები და დაიცავით ანგარიშზე წვდომა.', 'ნუ შეეცდებით ლიმიტების გვერდის ავლას, სერვისის მუშაობის დარღვევას, ბაზის მასობრივ ამოღებას ან უკანონო გამოყენებას.', 'უსაფრთხოების დადასტურებული საფრთხისას წვდომა შეიძლება დროებით შეიზღუდოს; თუ კანონი არ კრძალავს, გაცნობებთ მიზეზსა და გასაჩივრების გზას.'] },
        { id: 'rights', title: 'უარი, დაბრუნება და მოქმედი სამართალი', body: ['ნებაყოფლობითი 24-საათიანი გარანტიის, კანონით გათვალისწინებული უარისა და თანხის დაბრუნების წესები ცალკე გვერდზეა გამოქვეყნებული. ეს პირობები არ ზღუდავს საქართველოს კანონმდებლობით დადგენილ მომხმარებლის სავალდებულო უფლებებს.', 'ურთიერთობაზე ვრცელდება საქართველოს სამართალი. პრეტენზია პირველად გამოაგზავნეთ info@tax-advisor.ge-ზე; კომპეტენტურ ორგანოსა ან სასამართლოში მიმართვის უფლება შენარჩუნებულია.'] },
      ], sources: [{ label: 'საქართველოს კანონი „მომხმარებლის უფლებების დაცვის შესახებ“', href: commonSources.consumer }],
    },
    refunds: {
      label: 'გადახდა და მომხმარებლის დაცვა', title: 'თანხის დაბრუნება და გაუქმება', summary: 'Modern LLC-ის ნებაყოფლობითი 24-საათიანი გარანტია მომხმარებლის კანონით დადგენილ უფლებებს ემატება.', updated: 'ვერსია 2026-09-08 · მოქმედებს 2026 წლის 8 სექტემბრიდან',
      sections: [
        { id: 'guarantee', title: 'ნებაყოფლობითი 24-საათიანი გარანტია', body: ['მომხმარებელს შეუძლია Pro ან Business-ის პირველი გადახდის დაბრუნება მოითხოვოს გადახდის დადასტურებიდან 24 საათში მიზეზის განმარტების გარეშე. გარანტია ანგარიშის პირველ ფასიან პერიოდზე ერთხელ მოქმედებს და კანონით მინიჭებულ უფლებებს არ აუქმებს.'] },
        { id: 'other-grounds', title: 'სხვა საფუძვლები', bullets: ['ორმაგი, შეცდომითი ან არასანქცირებული ჩამოჭრა.', 'პლატფორმის ბრალით ფასიანი წვდომა არ გააქტიურდა და პრობლემა გონივრულ ვადაში არ გამოსწორდა.', 'არსებითი ტექნიკური ხარვეზი არ იძლევა ფასიანი მომსახურებით სარგებლობის საშუალებას და მიმართვის შემდეგ არ გამოსწორდა.', 'მოქმედი კანონმდებლობით პირდაპირ გათვალისწინებული ნებისმიერი სხვა საფუძველი.'] },
        { id: 'consumer-right', title: 'მომხმარებლის უარის უფლება', body: ['თუ პირი საქართველოს კანონით მომხმარებელია, დისტანციურ ხელშეკრულებაზე, როგორც წესი, ვრცელდება 14-დღიანი უარის უფლება. 24-საათიანი გარანტია ამ ვადას არ ამცირებს.', 'შეკვეთისას მომხმარებელი ცალკე ითხოვს ციფრული მომსახურების დაუყოვნებლივ დაწყებას და ადასტურებს პირობების გაცნობას. უარის უფლების გამონაკლისი გამოიყენება მხოლოდ კანონით დაშვებულ ფარგლებში, მათ შორის წინასწარი თანხმობისა და ინფორმირების მოთხოვნების დაცვით. სამეწარმეო ან პროფესიული მიზნის Business-შეძენაზე მომხმარებლის რეჟიმი შეიძლება არ გავრცელდეს.'] },
        { id: 'request', title: 'როგორ მოითხოვოთ დაბრუნება', body: ['ანგარიშის ელფოსტიდან მოგვწერეთ info@tax-advisor.ge-ზე. მიუთითეთ განაცხადის ან გადახდის ნომერი, პაკეტი და გადახდის თარიღი. არ გამოგვიგზავნოთ ბარათის ნომერი, CVV, პაროლი ან საბანკო კოდი.', 'შეგიძლიათ დაწეროთ: „მსურს ხელშეკრულებაზე უარი/თანხის დაბრუნება პაკეტისთვის [პაკეტი], განაცხადი [ნომერი], გადახდა [თარიღი]“. მიღებას ხელმისაწვდომ საკომუნიკაციო არხზე დაგიდასტურებთ.'] },
        { id: 'timing', title: 'ვადა და დაბრუნების გზა', body: ['საფუძვლის დადასტურების შემდეგ თანხა, თუ სხვაგვარად არ შევთანხმდით, იმავე გადახდის გზით დაბრუნდება გაუმართლებელი დაყოვნების გარეშე და, როცა ამას კანონი მოითხოვს, არაუგვიანეს 14 კალენდარული დღისა. ანგარიშზე ასახვა შეიძლება ბანკზე იყოს დამოკიდებული.', 'ცალკე საოპერატორო ინსტრუმენტის შექმნამდე დაბრუნება ხელით განიხილება; საიტი შესრულებულ დაბრუნებას არ აცხადებს, სანამ ოპერაცია არ დადასტურდება. სრული დაბრუნებისას ფასიანი წვდომა წყდება.'] },
        { id: 'cancellation', title: 'შემდეგი პერიოდის გაუქმება', body: ['Pro და Business ფიქსირებულ 30 დღეზე გაიცემა და ავტომატურად არ განახლდება. ამიტომ შემდეგი პერიოდის ცალკე გაუქმება საჭირო არ არის: ახალი თანხა არ ჩამოიჭრება, სანამ მომხმარებელი თავად არ შექმნის და გადაიხდის ახალ განაცხადს. მიმდინარე ფასიანი წვდომა კაბინეტში მითითებულ თარიღამდე მოქმედებს, თუ თანხა არ დაბრუნებულა.'] },
      ], sources: [{ label: 'საქართველოს კანონი „მომხმარებლის უფლებების დაცვის შესახებ“, მუხლები 13–15', href: commonSources.consumer }],
    },
    privacy: {
      label: 'მონაცემთა დაცვა', title: 'კონფიდენციალურობის პოლიტიკა', summary: 'რა მონაცემებს იყენებს Tax Advisor, რატომ გვჭირდება ისინი და როგორ გამოიყენოთ თქვენი უფლებები.', updated: 'ვერსია 2026-09-08 · მოქმედებს 2026 წლის 8 სექტემბრიდან',
      sections: [
        { id: 'controller', title: 'მონაცემთა დამუშავებისთვის პასუხისმგებელი პირი', body: ['პერსონალურ მონაცემთა დამუშავებისთვის პასუხისმგებელი პირია Modern LLC, კოდი 431177120. კითხვები და მოთხოვნები: info@tax-advisor.ge, +995 550 052 050.'] },
        { id: 'data', title: 'რა მონაცემები მუშავდება', bullets: ['ანგარიშისა და საკონტაქტო მონაცემები: ელფოსტა, მომხმარებლის სახელი, მითითებული სახელი, პაროლის დაცული ჰეში და ელფოსტის დადასტურების სტატუსი.', 'კითხვების, დიალოგებისა და უკუკავშირის შინაარსი, თუ მომხმარებელი მათ აგზავნის ან ინახავს.', 'გადახდის მონაცემები: პაკეტი, თანხა, ვალუტა, სტატუსი, განაცხადისა და ოპერაციის იდენტიფიკატორები. Tax Advisor ბარათის მონაცემებს არ იღებს.', 'ტექნიკური ჟურნალები, IP-მისამართი და უსაფრთხოების სიგნალები, რომლებიც საჭიროა სერვისის დაცვის, დიაგნოსტიკისა და ბოროტად გამოყენების შეზღუდვისთვის.'] },
        { id: 'purposes', title: 'მიზნები და საფუძვლები', body: ['მონაცემები საჭიროა ხელშეკრულების შესასრულებლად, პასუხებისა და ისტორიის მისაწოდებლად, ფასიანი წვდომის გასააქტიურებლად, მხარდაჭერისა და უსაფრთხოებისთვის, სამართლებრივი ვალდებულებებისა და კანონიერი მოთხოვნების დასაცავად. სადაც კანონი თანხმობას მოითხოვს, მას ცალკე ვითხოვთ და მომავალზე შეიძლება გაუქმდეს.'] },
        { id: 'recipients', title: 'მიმღებები და მომწოდებლები', body: ['საჭირო მოცულობით მონაცემები შეიძლება დაამუშაონ ჰოსტინგის, მონაცემთა ბაზის, AI API-ის, ინფრასტრუქტურის დაცვის, საბანკო გადახდის (მათ შორის TBC) და ჩართვის შემდეგ ელფოსტის მიწოდების მომწოდებლებმა. ისინი მხოლოდ საკუთარი ფუნქციისთვის საჭირო მონაცემებს იღებენ და ვალდებული არიან დაიცვან მოქმედი მოთხოვნები.'] },
        { id: 'retention', title: 'შენახვა და უსაფრთხოება', body: ['მონაცემები ინახება არა უმეტეს შესაბამისი მიზნის, ხელშეკრულების, სავალდებულო ანგარიშგების, დავის გადაწყვეტისა და სარეზერვო აღდგენის საჭირო ვადისა. კონკრეტული ვადა კატეგორიასა და სამართლებრივ საფუძველზეა დამოკიდებული. გამოიყენება წვდომის გამიჯვნა, პაროლების ჰეშირება, ჟურნალირება, სარეზერვო ასლები და მთლიანობის კონტროლი.'] },
        { id: 'rights', title: 'თქვენი უფლებები', body: ['კანონის ფარგლებში შეგიძლიათ მოითხოვოთ ინფორმაცია და წვდომა, გასწორება, განახლება, დამუშავების შეწყვეტა, წაშლა ან განადგურება, დაბლოკვა, გადატანა, დამუშავებაზე შეწინააღმდეგება და გადაწყვეტილების გასაჩივრება. ანგარიშის დასაცავად შეიძლება განმცხადებლის ვინაობა გადავამოწმოთ.', 'მოთხოვნა გამოაგზავნეთ info@tax-advisor.ge-ზე. კანონით დადგენილი წესით შეგიძლიათ ასევე მიმართოთ უფლებამოსილ ორგანოს ან სასამართლოს.'] },
      ], sources: [{ label: 'საქართველოს კანონი „პერსონალურ მონაცემთა დაცვის შესახებ“', href: commonSources.privacy }],
    },
    delivery: {
      label: 'ციფრული მომსახურება', title: 'წვდომის გააქტიურება', summary: 'Tax Advisor უზრუნველყოფს ციფრულ წვდომას — ფიზიკური მიწოდება და მიწოდების საფასური არ არსებობს.', updated: 'ვერსია 2026-09-08 · მოქმედებს 2026 წლის 8 სექტემბრიდან',
      sections: [
        { id: 'scope', title: 'რა მოგეწოდებათ', body: ['შეძენის შედეგია Tax Advisor-ის Pro ან Business ფუნქციებზე 30-დღიანი წვდომა ანგარიშში. ნივთი ფოსტით ან კურიერით არ იგზავნება და მიწოდების საფასური არ არსებობს.'] },
        { id: 'online', title: 'TBC-ით გადახდა', body: ['TBC-ის გვერდზე წარმატებული გადახდის შემდეგ Tax Advisor-ის სერვერი ბანკში დამოუკიდებლად ამოწმებს სტატუსს, თანხასა და ვალუტას. ზუსტი დამთხვევისას წვდომა კაბინეტში ჩვეულებრივ დაუყოვნებლივ აქტიურდება. ბანკის გვერდიდან ბრაუზერის დაბრუნება თავისთავად გადახდის მტკიცებულება არ არის.'] },
        { id: 'invoice', title: 'საბანკო გადარიცხვა', body: ['ინვოისით გადახდისას წვდომა ოპერატორის მიერ თანხის მიღების შემოწმების შემდეგ აქტიურდება. მიმართვაში ან დანიშნულებაში მიუთითეთ კაბინეტის განაცხადის ნომერი.'] },
        { id: 'delay', title: 'თუ წვდომა არ გამოჩნდა', body: ['ბანკის სტატუსი შეიძლება დამუშავებაში დარჩეს ან ხელით შედარება დასჭირდეს. თუ დადასტურებული ჩამოჭრიდან 30 წუთში წვდომა არ გააქტიურდა, მოგვწერეთ info@tax-advisor.ge-ზე და მიუთითეთ ანგარიშის ელფოსტა და განაცხადის ნომერი. არ გამოგვიგზავნოთ ბარათის მონაცემები ან პაროლი.'] },
        { id: 'notice', title: 'შეტყობინება', body: ['წვდომის ავტორიტეტული დადასტურებაა კაბინეტში ნაჩვენები სტატუსი და დასრულების თარიღი. ელფოსტა დამატებით მხოლოდ მოქმედი საფოსტო მიწოდებისას იგზავნება; წერილის არქონა უკვე გააქტიურებულ წვდომას არ აუქმებს.'] },
      ],
    },
    contact: {
      label: 'Modern LLC', title: 'კონტაქტი და რეკვიზიტები', summary: 'ერთიანი კონტაქტი მხარდაჭერისთვის, პრეტენზიისთვის, დაბრუნებისა და პერსონალურ მონაცემთა საკითხებისთვის.', updated: 'აქტუალურია 2026 წლის 8 სექტემბრიდან',
      sections: [
        { id: 'details', title: 'იურიდიული პირი', bullets: ['Modern LLC', 'საიდენტიფიკაციო კოდი: 431177120', 'იურიდიული მისამართი: Telavi, Kurdgelauri vil.', 'არ არის დღგ-ის გადამხდელად რეგისტრირებული.'] },
        { id: 'channels', title: 'საკონტაქტო არხები', bullets: ['ელფოსტა: info@tax-advisor.ge', 'ტელეფონი: +995 550 052 050'] },
        { id: 'support', title: 'სწრაფი დახმარებისთვის', body: ['მიუთითეთ ანგარიშის ელფოსტა, საკითხის მოკლე აღწერა და გადახდის შემთხვევაში განაცხადის ნომერი. არასოდეს გამოგვიგზავნოთ პაროლი, ბარათის სრული ნომერი, CVV ან ერთჯერადი საბანკო კოდი.'] },
      ],
    },
  },
  en: {
    terms: {
      label: 'Legal information', title: 'Terms of use', summary: 'Rules for accessing Tax Advisor, paying for plans, and using legal information.', updated: 'Version 2026-09-08 · effective 8 September 2026',
      sections: [
        { id: 'operator', title: 'Service provider', body: ['Tax Advisor is provided by Modern LLC, identification code 431177120, registered address: Telavi, Kurdgelauri vil. Contact: info@tax-advisor.ge, +995 550 052 050.', 'Modern LLC is not registered for VAT. The displayed prices are final; VAT is neither added nor shown separately.'] },
        { id: 'service', title: 'What Tax Advisor provides', body: ['The service helps users find and understand Georgian tax and related law, with official sources, legislation-change history, and tax-dispute practice.', 'Answers are informational, do not create a lawyer–client relationship, and do not replace individual legal, tax, or accounting advice. Before a consequential decision, verify the date, applicable version of the rule, and facts of the matter.'] },
        { id: 'plans', title: 'Plans, price, and term', bullets: ['Pro — GEL 49 for 30 days.', 'Business — GEL 149 for 30 days.', 'The price and plan are fixed in the checkout before payment.', 'Access does not renew automatically. The user creates and pays for a new checkout for each additional 30-day period.'] },
        { id: 'payment', title: 'Payment and activation', body: ['Bank transfer against an invoice is available and, once the merchant account is activated, card payment runs on TBC’s secure hosted page. Tax Advisor does not receive or store card details.', 'Paid access activates in the account only after receipt of funds is confirmed or the bank’s successful status is verified server-side. An activation email is an additional notice sent only when email delivery is operational.'] },
        { id: 'account', title: 'Account and acceptable use', bullets: ['Provide accurate details and protect account access.', 'Do not bypass limits, disrupt the service, extract the database at scale, or use the service unlawfully.', 'A verified security threat may result in temporary access restriction; unless prohibited by law, we will explain the reason and contact route.'] },
        { id: 'rights', title: 'Withdrawal, refunds, and governing law', body: ['The voluntary 24-hour guarantee and statutory withdrawal and refund rules are published separately. These terms do not restrict mandatory consumer rights under Georgian law.', 'Georgian law governs the relationship. Send a complaint first to info@tax-advisor.ge; the right to apply to a competent authority or court remains available.'] },
      ], sources: [{ label: 'Law of Georgia on the Protection of Consumer Rights', href: commonSources.consumer }],
    },
    refunds: {
      label: 'Payment and customer protection', title: 'Refunds and cancellation', summary: 'Modern LLC’s voluntary 24-hour guarantee is additional to mandatory consumer rights.', updated: 'Version 2026-09-08 · effective 8 September 2026',
      sections: [
        { id: 'guarantee', title: 'Voluntary 24-hour guarantee', body: ['A user may request a refund of the first Pro or Business payment within 24 hours after payment confirmation, without giving a reason. The guarantee applies once to the account’s first paid period and does not remove any statutory right.'] },
        { id: 'other-grounds', title: 'Other grounds', bullets: ['A duplicate, incorrect, or unauthorised charge.', 'Paid access failed to activate because of the platform and was not remedied within a reasonable time.', 'A material technical defect prevents use of the paid service and was not remedied after notice.', 'Any other ground expressly provided by applicable law.'] },
        { id: 'consumer-right', title: 'Consumer right of withdrawal', body: ['Where the user is a consumer under Georgian law, a distance contract generally carries a 14-day withdrawal right. The 24-hour guarantee does not shorten it.', 'At checkout, the user separately asks for immediate commencement of the digital service and confirms the terms. Any exception to withdrawal applies only to the extent allowed by law, including its prior-consent and notice requirements. The consumer regime may not apply to a Business purchase made for trade or professional purposes.'] },
        { id: 'request', title: 'How to request a refund', body: ['Email info@tax-advisor.ge from the account email and include the checkout or payment reference, plan, and payment date. Never send a card number, CVV, password, or bank code.', 'You may write: “I request withdrawal/refund for [plan], checkout [reference], paid [date].” We will confirm receipt through an available contact channel.'] },
        { id: 'timing', title: 'Refund time and method', body: ['Once the ground is confirmed, a refund is made by the same payment method unless otherwise agreed, without undue delay and no later than 14 calendar days where the law requires that period. Bank posting times may vary.', 'Until a dedicated operator tool exists, refunds are reviewed manually; the site does not represent a refund as completed until the transaction is confirmed. Full refund ends the paid access.'] },
        { id: 'cancellation', title: 'Cancelling the next period', body: ['Pro and Business are fixed 30-day periods with no automatic renewal. There is therefore no next period to cancel: no further charge occurs unless the user creates and pays for a new checkout. Current paid access continues until the date shown in the account unless the payment is refunded.'] },
      ], sources: [{ label: 'Law of Georgia on the Protection of Consumer Rights, Articles 13–15', href: commonSources.consumer }],
    },
    privacy: {
      label: 'Data protection', title: 'Privacy policy', summary: 'What data Tax Advisor uses, why it is needed, and how to exercise your rights.', updated: 'Version 2026-09-08 · effective 8 September 2026',
      sections: [
        { id: 'controller', title: 'Data controller', body: ['The personal-data controller is Modern LLC, code 431177120. Questions and requests: info@tax-advisor.ge, +995 550 052 050.'] },
        { id: 'data', title: 'Data we process', bullets: ['Account and contact data: email, username, supplied name, protected password hash, and email-verification status.', 'Questions, conversations, and feedback when submitted or saved by the user.', 'Payment records: plan, amount, currency, status, checkout and transaction identifiers. Tax Advisor does not receive card details.', 'Technical logs, IP address, and security signals required to protect and diagnose the service and limit abuse.'] },
        { id: 'purposes', title: 'Purposes and grounds', body: ['Data is needed to perform the contract, provide answers and history, activate paid access, support users, secure the service, comply with legal duties, and defend lawful claims. Where consent is required, it is requested separately and may be withdrawn prospectively.'] },
        { id: 'recipients', title: 'Recipients and providers', body: ['As necessary, data may be processed by hosting, database, AI API, infrastructure-security, bank-payment (including TBC), and, once enabled, email-delivery providers. Providers receive only what is needed for their function and must comply with applicable data-protection requirements.'] },
        { id: 'retention', title: 'Retention and security', body: ['Data is kept no longer than needed for its purpose, the contract, mandatory records, dispute resolution, and backup recovery. The exact period depends on data category and legal ground. Controls include access separation, password hashing, logging, backups, and integrity checks.'] },
        { id: 'rights', title: 'Your rights', body: ['Within the law, you may request information and access, rectification, updating, cessation of processing, erasure or destruction, blocking, portability, object to processing, and appeal a decision. We may verify identity to protect the account.', 'Send requests to info@tax-advisor.ge. You may also apply to the competent authority or a court as provided by law.'] },
      ], sources: [{ label: 'Law of Georgia on Personal Data Protection', href: commonSources.privacy }],
    },
    delivery: {
      label: 'Digital service', title: 'Access activation', summary: 'Tax Advisor delivers digital access; there is no physical delivery or delivery fee.', updated: 'Version 2026-09-08 · effective 8 September 2026',
      sections: [
        { id: 'scope', title: 'What is delivered', body: ['The purchase provides access to the Pro or Business features in the Tax Advisor account for 30 days. Nothing is sent by mail or courier, and no delivery fee is charged.'] },
        { id: 'online', title: 'TBC payment', body: ['After successful payment on TBC’s page, the Tax Advisor server independently checks the status, amount, and currency with the bank. On an exact match, access normally activates in the account immediately. A browser return from the bank page is not payment evidence by itself.'] },
        { id: 'invoice', title: 'Bank transfer', body: ['For invoice payments, access activates after an operator verifies receipt of funds. Include the account checkout reference in the message or payment description.'] },
        { id: 'delay', title: 'If access does not appear', body: ['A bank status may remain in processing or require manual reconciliation. If access is not active within 30 minutes after a confirmed charge, email info@tax-advisor.ge with the account email and checkout reference. Do not send card details or a password.'] },
        { id: 'notice', title: 'Notice', body: ['The authoritative confirmation is the status and end date shown in the account. An activation email is an additional notice sent only when email delivery is operational; a missing email does not cancel access already activated.'] },
      ],
    },
    contact: {
      label: 'Modern LLC', title: 'Contact and legal details', summary: 'One contact for support, complaints, refunds, and personal-data requests.', updated: 'Current from 8 September 2026',
      sections: [
        { id: 'details', title: 'Legal entity', bullets: ['Modern LLC', 'Identification code: 431177120', 'Registered address: Telavi, Kurdgelauri vil.', 'Not registered for VAT.'] },
        { id: 'channels', title: 'Contact channels', bullets: ['Email: info@tax-advisor.ge', 'Phone: +995 550 052 050'] },
        { id: 'support', title: 'Help us respond faster', body: ['Include the account email, a short description, and, for payment issues, the checkout reference. Never send a password, full card number, CVV, or one-time bank code.'] },
      ],
    },
  },
};
