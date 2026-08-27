from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional

from .legal_answer_contracts import (
    LegalAnswerContract,
    build_contract_cases,
)


CANONICAL_TAX_CODE_SOURCE_URL = "https://infohub.rs.ge/ka/workspace/document/800cbef0-32bf-4f06-94fe-8afd2bf144a0"
CANONICAL_TAX_CODE_TITLE = "საქართველოს საგადასახადო კოდექსი."


TaxFaqEntry = LegalAnswerContract


TAX_FAQ_MATRIX: List[TaxFaqEntry] = [
    TaxFaqEntry(
        slug="income-tax-individual",
        topic="tax",
        subject="individual",
        article_ref="81",
        question_class="canonical_law_lookup",
        response_kind="fixed_rate_with_exception",
        note="20% general PIT; rental housing can be a 5% exception.",
        sample_queries={
            "ru": "Какой подоходный налог в Грузии?",
            "en": "What is the personal income tax rate in Georgia?",
            "ka": "რა არის საშემოსავლო გადასახადის განაკვეთი საქართველოში?",
        },
        response_by_lang={
            "ru": "Подоходный налог для физлица в Грузии — 20% от налогооблагаемого дохода, если кодексом не предусмотрено иное. Частое исключение — доход от сдачи жилья в аренду: он облагается по ставке 5%, если не применяются вычеты.",
            "en": "The personal income tax rate in Georgia is 20% of taxable income, unless the code provides otherwise. A common exception is residential rental income, which is taxed at 5% if no deductions are applied.",
            "ka": "ფიზიკური პირის დასაბეგრი შემოსავალი საქართველოში 20 პროცენტით იბეგრება, თუ კოდექსით სხვა რამ არ არის გათვალისწინებული. ხშირი გამონაკლისია საცხოვრებელი ფართის გაქირავებიდან მიღებული შემოსავალი, რომელიც 5 პროცენტით იბეგრება, თუ გამოქვითვები არ გამოიყენება.",
        },
        smoke_contains={"ru": ["20%", "5%"], "en": ["20%", "5%"], "ka": ["20 პროცენტ", "5 პროცენტ"]},
    ),
    TaxFaqEntry(
        slug="short-term-rental-fixed-tax",
        topic="short_term_rental_tax",
        subject="individual",
        article_ref="309",
        question_class="canonical_law_lookup",
        response_kind="special_regime",
        note="Until 1 January 2028, an individual using classification code 55.2 for short-term accommodation can switch to a fixed personal income tax regime on application, subject to VAT-related conditions.",
        sample_queries={
            "ru": "Какой налог на посуточную аренду квартиры в Грузии?",
            "en": "What tax applies to Airbnb income in Georgia?",
            "ka": "რა გადასახადია ბინის მოკლევადიან გაქირავებაზე საქართველოში?",
        },
        response_by_lang={
            "ru": "До 1 января 2028 года для физлица, которое краткосрочно сдаёт своё жильё (деятельность 55.2), может применяться фиксированный подоходный налог по заявлению. Базовая ставка — 10 лари за 1 кв. м в календарный месяц; режим доступен, если лицо добровольно не зарегистрировано по НДС или оборот по этой деятельности за любые непрерывные 12 месяцев не превышает 100 000 лари. В период этого режима такая краткосрочная сдача не считается операцией, облагаемой НДС.",
            "en": "Until 1 January 2028, an individual who short-term lets their own accommodation (activity code 55.2) may, upon application, use a fixed personal income tax regime. The base rate is GEL 10 per square meter per calendar month; this regime is available if the person is not voluntarily VAT-registered or if turnover from this activity during any continuous 12 calendar months does not exceed GEL 100,000. During this regime, the short-term letting is not treated as a VAT-taxable transaction.",
            "ka": "2028 წლის 1 იანვრამდე ფიზიკურ პირს, რომელიც საკუთარ საცხოვრებელ ადგილს მოკლე ვადით გასცემს (55.2 საქმიანობა), საგადასახადო ორგანოსთვის მიმართვის შემთხვევაში შეუძლია ფიქსირებული საშემოსავლო გადასახადის რეჟიმის გამოყენება. საბაზო განაკვეთი არის 10 ლარი 1 კვ. მ-ზე კალენდარულ თვეში; რეჟიმი მოქმედებს, თუ პირი ნებაყოფლობით არ არის დღგ-ის გადამხდელად რეგისტრირებული ან ამ საქმიანობის ბრუნვა ნებისმიერ უწყვეტ 12 კალენდარულ თვეში 100 000 ლარს არ აღემატება. ამ რეჟიმის პერიოდში ასეთი მოკლევადიანი გაცემა დღგ-ით დასაბეგრ ოპერაციად არ ითვლება.",
        },
        smoke_contains={"ru": ["10 лари", "100 000 лари", "НДС"], "en": ["GEL 10", "GEL 100,000", "VAT"], "ka": ["10 ლარი", "100 000 ლარს", "დღგ"]},
    ),
    TaxFaqEntry(
        slug="rental-housing",
        topic="rental_income",
        subject="individual",
        article_ref="81",
        question_class="canonical_law_lookup",
        response_kind="conditional_rate",
        note="5% if no deductions are claimed from residential rental income; otherwise general rule may apply.",
        sample_queries={
            "ru": "Сколько налог на аренду жилья в Грузии?",
            "en": "What tax applies to residential rental income in Georgia?",
            "ka": "რა გადასახადია ბინის გაქირავებაზე საქართველოში?",
        },
        response_by_lang={
            "ru": "Доход от сдачи жилья в аренду в Грузии облагается по ставке 5%, если физлицо не применяет вычеты из этого дохода. Если это условие не выполняется, может применяться общее правило 20%.",
            "en": "Income from renting out residential property in Georgia is taxed at 5% if the individual does not claim deductions from that income. If that condition is not met, the general 20% personal income tax rule may apply.",
            "ka": "საცხოვრებელი ფართის გაქირავებიდან მიღებული შემოსავალი საქართველოში 5 პროცენტით იბეგრება, თუ ფიზიკური პირი ამ შემოსავლიდან გამოქვითვებს არ ახორციელებს. თუ ეს პირობა არ სრულდება, შეიძლება გავრცელდეს 20%-იანი ზოგადი წესი.",
        },
        smoke_contains={"ru": ["5%", "20%"], "en": ["5%", "20%"], "ka": ["5 პროცენტ", "20%"]},
    ),
    TaxFaqEntry(
        slug="property-tax-individual",
        topic="property_tax",
        subject="individual",
        article_ref="281",
        question_class="practical_tax_guidance",
        response_kind="range_not_fixed_rate",
        note="Do not answer with a false fixed 1%; for individuals the rate depends on income and can range from 0% to 0.8%.",
        sample_queries={
            "ru": "Сколько налог на имущество для физлица в Тбилиси?",
            "en": "What is the property tax for an individual in Tbilisi?",
            "ka": "ფიზიკური პირისთვის ქონების გადასახადი რამდენია თბილისში?",
        },
        response_by_lang={
            "ru": "Для физлица налог на имущество не следует описывать фиксированной ставкой 1%, потому что такая ставка относится к организациям. Для физических лиц налог зависит от дохода за предыдущий календарный год, а ставка может варьироваться от 0% до 0.8%. Если нужен точный расчёт, его нужно считать отдельно по доходу семьи и виду имущества.",
            "en": "For an individual, property tax should not be described as a fixed 1% rate, because that rate applies to companies. For individuals, the tax depends on the previous calendar year's family income, and the rate can range from 0% to 0.8%. If you need the exact amount, it should be calculated separately based on income and the type of property.",
            "ka": "ფიზიკური პირისთვის ქონების გადასახადი ფიქსირებული 1%-იანი განაკვეთით არ განისაზღვრება, რადგან ასეთი განაკვეთი ორგანიზაციებს ეხება. ფიზიკური პირებისთვის გადასახადი დამოკიდებულია წინა კალენდარული წლის ოჯახის შემოსავალზე და განაკვეთი შეიძლება იყოს 0%-დან 0.8%-მდე. ზუსტი თანხის დასადგენად საჭიროა ცალკე გამოთვლა შემოსავლისა და ქონების ტიპის მიხედვით.",
        },
        smoke_contains={"ru": ["0% до 0.8%"], "en": ["0% to 0.8%"], "ka": ["0%-დან 0.8%-მდე"]},
    ),
    TaxFaqEntry(
        slug="property-tax-company",
        topic="property_tax_company",
        subject="legal_entity",
        article_ref="202",
        question_class="canonical_law_lookup",
        response_kind="capped_rate",
        note="For an enterprise/organization, the annual property tax rate is up to 1% of taxable property value; leasing companies can have a special 0.6% rule for leased taxable property.",
        sample_queries={
            "ru": "Какой налог на имущество для компании в Грузии?",
            "en": "What is the property tax for a company in Georgia?",
            "ka": "კომპანიისთვის ქონების გადასახადი რამდენია საქართველოში?",
        },
        response_by_lang={
            "ru": "Для предприятия или организации в Грузии годовая ставка налога на имущество составляет не более 1% стоимости налогооблагаемого имущества. Для лизинговой компании по переданному в лизинг налогооблагаемому имуществу кодекс предусматривает специальное правило — не более 0.6%.",
            "en": "For an enterprise or organization in Georgia, the annual property tax rate is no more than 1% of the value of taxable property. For a leasing company, the code provides a special rule for leased taxable property of no more than 0.6%.",
            "ka": "საქართველოში საწარმოსთვის ან ორგანიზაციისთვის ქონების გადასახადის წლიური განაკვეთი დასაბეგრი ქონების ღირებულების არაუმეტეს 1%-ია. სალიზინგო კომპანიისთვის ლიზინგით გაცემულ დასაბეგრ ქონებაზე კოდექსი სპეციალურ წესსაც ითვალისწინებს — არაუმეტეს 0.6%-ს.",
        },
        smoke_contains={"ru": ["1%", "0.6%"], "en": ["1%", "0.6%"], "ka": ["1%", "0.6%"]},
    ),
    TaxFaqEntry(
        slug="excise-guardrail",
        topic="excise",
        article_ref="188",
        question_class="canonical_law_lookup",
        response_kind="no_single_rate_guardrail",
        note="Excise does not have one universal rate; it depends on the specific excisable goods. Alcoholic beverages are handled in Article 1881.",
        sample_queries={
            "ru": "Какой акциз в Грузии?",
            "en": "What is the excise tax in Georgia?",
            "ka": "რა არის აქციზის განაკვეთი საქართველოში?",
        },
        response_by_lang={
            "ru": "Единой ставки акциза в Грузии нет: она зависит от конкретного подакцизного товара. Для большинства подакцизных товаров ставки перечислены в статье 188 Налогового кодекса, а для алкогольных напитков — в статье 1881.",
            "en": "There is no single excise rate in Georgia: it depends on the specific excisable goods. For most excisable goods, the rates are listed in Article 188 of the Tax Code, and for alcoholic beverages in Article 1881.",
            "ka": "საქართველოში აქციზის ერთი საერთო განაკვეთი არ არსებობს: იგი დამოკიდებულია კონკრეტულ აქციზურ საქონელზე. აქციზური საქონლის უმეტესობაზე განაკვეთები ჩამოთვლილია საგადასახადო კოდექსის 188-ე მუხლში, ხოლო ალკოჰოლიან სასმელებზე — 1881 მუხლში.",
        },
        smoke_contains={"ru": ["статье 188", "1881"], "en": ["Article 188", "1881"], "ka": ["188-ე", "1881"]},
    ),
    TaxFaqEntry(
        slug="customs-duty-guardrail",
        topic="customs",
        article_ref="197",
        question_class="canonical_law_lookup",
        response_kind="no_single_rate_guardrail",
        note="There is no single customs/import duty rate; it depends on the tariff code and the specific goods. Article 197 includes a 12% rate for listed goods.",
        sample_queries={
            "ru": "Какая таможенная пошлина в Грузии?",
            "en": "What customs duty applies in Georgia?",
            "ka": "რა არის საბაჟო გადასახადის განაკვეთი საქართველოში?",
        },
        response_by_lang={
            "ru": "Единой ставки таможенной пошлины в Грузии нет: она зависит от конкретного товара и его тарифного кода. В статье 197 Налогового кодекса перечислены товары, облагаемые импортной пошлиной по ставке 12%, а для других товаров ставка определяется по соответствующей товарной позиции и правилам тарифа.",
            "en": "There is no single customs duty rate in Georgia: it depends on the specific goods and their tariff code. Article 197 of the Tax Code lists goods subject to a 12% import duty, while for other goods the rate is determined by the relevant tariff position and tariff rules.",
            "ka": "საქართველოში საბაჟო გადასახადის ერთი საერთო განაკვეთი არ არსებობს: იგი დამოკიდებულია კონკრეტულ საქონელსა და მის სატარიფო კოდზე. საგადასახადო კოდექსის 197-ე მუხლში ჩამოთვლილია საქონელი, რომელიც 12%-იანი იმპორტის გადასახადით იბეგრება, ხოლო სხვა საქონელზე განაკვეთი შესაბამისი სატარიფო პოზიციისა და ტარიფის წესების მიხედვით განისაზღვრება.",
        },
        smoke_contains={"ru": ["12%", "статье 197"], "en": ["12%", "Article 197"], "ka": ["12%", "197-ე"]},
    ),
    TaxFaqEntry(
        slug="vat-standard",
        topic="vat",
        article_ref="166",
        question_class="canonical_law_lookup",
        response_kind="fixed_rate",
        note="Standard VAT rate.",
        sample_queries={
            "ru": "Какая ставка НДС в Грузии?",
            "en": "What is the VAT rate in Georgia?",
            "ka": "დღგ-ის განაკვეთი რამდენია საქართველოში?",
        },
        response_by_lang={
            "ru": "Стандартная ставка НДС в Грузии — 18%.",
            "en": "The standard VAT rate in Georgia is 18%.",
            "ka": "დღგ-ის სტანდარტული განაკვეთი საქართველოში 18 პროცენტია.",
        },
        smoke_contains={"ru": ["18%"], "en": ["18%"], "ka": ["18 პროცენტ"]},
    ),
    TaxFaqEntry(
        slug="vat-import",
        topic="import_vat",
        article_ref="168",
        question_class="canonical_law_lookup",
        response_kind="yes_plus_rate",
        note="Import is generally subject to VAT at 18% unless a specific exemption applies.",
        sample_queries={
            "ru": "Есть ли НДС при импорте в Грузию?",
            "en": "Is VAT charged on import into Georgia?",
            "ka": "აქვს თუ არა იმპორტს დღგ საქართველოში?",
        },
        response_by_lang={
            "ru": "Да. Импорт в Грузию, как правило, облагается НДС, а стандартная ставка составляет 18%, если не действует специальное освобождение.",
            "en": "Yes. Import into Georgia is generally subject to VAT, and the standard rate is 18%, unless a specific exemption applies.",
            "ka": "დიახ. საქართველოში იმპორტი, როგორც წესი, დღგ-ით იბეგრება, ხოლო სტანდარტული განაკვეთი 18%-ია, თუ კონკრეტული გათავისუფლება არ მოქმედებს.",
        },
        smoke_contains={"ru": ["Да", "18%"], "en": ["Yes", "18%"], "ka": ["დიახ", "18%"]},
    ),
    TaxFaqEntry(
        slug="vat-registration-timing",
        topic="vat_registration_timing",
        article_ref="165",
        question_class="canonical_law_lookup",
        response_kind="timing_rule",
        note="The duty to calculate and pay VAT arises from the taxable operation that causes the cumulative amount to exceed GEL 100,000, including that operation.",
        sample_queries={
            "ru": "С какого момента возникает обязанность регистрации по НДС в Грузии?",
            "en": "When does the VAT registration obligation arise in Georgia?",
            "ka": "როდის წარმოიშობა დღგ-ის გადამხდელად რეგისტრაციის ვალდებულება საქართველოში?",
        },
        response_by_lang={
            "ru": "Обязанность по НДС в Грузии возникает с той облагаемой операции, по которой сумма таких операций превысила 100 000 лари за любые непрерывные 12 календарных месяцев; эта операция тоже включается.",
            "en": "In Georgia, the VAT obligation arises from the taxable operation by which the total amount of such operations exceeds GEL 100,000 during any continuous 12 calendar months, and that operation is included as well.",
            "ka": "საქართველოში დღგ-ის ვალდებულება წარმოიშობა იმ დასაბეგრი ოპერაციიდან, რომლითაც ასეთი ოპერაციების ჯამური თანხა ნებისმიერ უწყვეტ 12 კალენდარულ თვეში 100 000 ლარს გადააჭარბებს, და ეს ოპერაციაც ჩათვლით იგულისხმება.",
        },
        smoke_contains={"ru": ["100 000 лари"], "en": ["GEL 100,000"], "ka": ["100 000 ლარს"]},
    ),
    TaxFaqEntry(
        slug="vat-deregistration-threshold",
        topic="vat_deregistration_threshold",
        article_ref="165-1",
        question_class="canonical_law_lookup",
        response_kind="threshold_with_condition",
        note="A person may request VAT deregistration if the last 12 months' taxable operations do not exceed GEL 100,000 and at least one year has passed since the last VAT registration.",
        sample_queries={
            "ru": "Какой порог для отмены регистрации по НДС в Грузии?",
            "en": "What is the VAT deregistration threshold in Georgia?",
            "ka": "როგორ უქმდება დღგ-ის გადამხდელად რეგისტრაცია საქართველოში?",
        },
        response_by_lang={
            "ru": "Просить об отмене регистрации по НДС в Грузии можно, если за последние 12 календарных месяцев сумма соответствующих операций без НДС не превышает 100 000 лари и с последней регистрации плательщиком НДС прошёл 1 год.",
            "en": "A person may request VAT deregistration in Georgia if, during the last 12 calendar months, the relevant operations excluding VAT do not exceed GEL 100,000 and one year has passed since the last VAT registration.",
            "ka": "საქართველოში დღგ-ის რეგისტრაციის გაუქმება შეიძლება მოითხოვოს პირმა, თუ ბოლო 12 კალენდარული თვის განმავლობაში შესაბამისი ოპერაციების ჯამური თანხა დღგ-ის გარეშე 100 000 ლარს არ აღემატება და დღგ-ის გადამხდელად ბოლო რეგისტრაციიდან 1 წელია გასული.",
        },
        smoke_contains={"ru": ["100 000 лари", "1 год"], "en": ["GEL 100,000", "one year"], "ka": ["100 000 ლარს", "1 წელია"]},
    ),
    TaxFaqEntry(
        slug="profit-tax",
        topic="profit_tax",
        article_ref="98",
        question_class="canonical_law_lookup",
        response_kind="fixed_rate",
        note="Base profit tax rate.",
        sample_queries={
            "ru": "Какой налог на прибыль в Грузии?",
            "en": "What is the profit tax rate in Georgia?",
            "ka": "მოგების გადასახადის განაკვეთი რამდენია საქართველოში?",
        },
        response_by_lang={
            "ru": "Основная ставка налога на прибыль в Грузии — 15%. В отдельных специальных случаях кодекс предусматривает иной режим, но базовая ставка — 15%.",
            "en": "The standard profit tax rate in Georgia is 15%. In some special cases the code provides different treatment, but the base rate is 15%.",
            "ka": "საქართველოში მოგების გადასახადის ძირითადი განაკვეთი 15 პროცენტია. ცალკეულ სპეციალურ შემთხვევებში კოდექსი სხვა წესსაც ითვალისწინებს, მაგრამ საბაზისო განაკვეთი 15%-ია.",
        },
        smoke_contains={"ru": ["15%"], "en": ["15%"], "ka": ["15 პროცენტ"]},
    ),
    TaxFaqEntry(
        slug="dividends",
        topic="dividend_tax",
        article_ref="130",
        question_class="canonical_law_lookup",
        response_kind="fixed_rate",
        note="Resident enterprise paying an individual, taxed at source.",
        sample_queries={
            "ru": "Какой налог на дивиденды в Грузии?",
            "en": "What is the dividend tax rate in Georgia?",
            "ka": "დივიდენდზე რა გადასახადია საქართველოში?",
        },
        response_by_lang={
            "ru": "Дивиденды, выплачиваемые резидентным предприятием физлицу, как правило, облагаются у источника по ставке 5%.",
            "en": "Dividends paid by a resident enterprise to an individual are generally taxed at 5% at source.",
            "ka": "რეზიდენტი საწარმოს მიერ ფიზიკურ პირზე გაცემული დივიდენდები, როგორც წესი, 5 პროცენტით იბეგრება გადახდის წყაროსთან.",
        },
        smoke_contains={"ru": ["5%"], "en": ["5%"], "ka": ["5 პროცენტ"]},
    ),
    TaxFaqEntry(
        slug="small-business-status",
        topic="small_business",
        subject="individual",
        article_ref="90",
        question_class="canonical_law_lookup",
        response_kind="tiered_rate",
        note="1% standard rate for small business status; 3% when annual income exceeds the code threshold for the relevant period.",
        sample_queries={
            "ru": "Какой налог для ИП со статусом малого бизнеса в Грузии?",
            "en": "What is the small business tax rate in Georgia?",
            "ka": "მცირე ბიზნესის სტატუსის გადასახადი რამდენია საქართველოში?",
        },
        response_by_lang={
            "ru": "Для ИП со статусом малого бизнеса в Грузии стандартная ставка — 1% от налогооблагаемого дохода. Если годовой доход превышает установленный кодексом порог, на соответствующий период применяется ставка 3%.",
            "en": "For an individual entrepreneur with small business status in Georgia, the standard tax rate is 1% of taxable income. If annual income exceeds the threshold set by the code, the rate becomes 3% for the relevant period.",
            "ka": "საქართველოში მცირე ბიზნესის სტატუსის მქონე მეწარმე ფიზიკური პირისთვის სტანდარტული განაკვეთი დასაბეგრი შემოსავლის 1%-ია. თუ წლიური შემოსავალი კოდექსით დადგენილ ზღვარს გადააჭარბებს, შესაბამის პერიოდში განაკვეთი 3% ხდება.",
        },
        smoke_contains={"ru": ["1%", "3%"], "en": ["1%", "3%"], "ka": ["1%", "3%"]},
    ),
    TaxFaqEntry(
        slug="interest",
        topic="interest_tax",
        article_ref="131",
        question_class="canonical_law_lookup",
        response_kind="fixed_rate",
        note="Interest taxed at source.",
        sample_queries={
            "ru": "Какой налог на проценты в Грузии?",
            "en": "What is the tax rate on interest in Georgia?",
            "ka": "რა გადასახადია პროცენტზე საქართველოში?",
        },
        response_by_lang={
            "ru": "Проценты, выплачиваемые резидентом или постоянным учреждением нерезидента, как правило, облагаются у источника по ставке 5%.",
            "en": "Interest paid by a resident or a non-resident permanent establishment is generally taxed at 5% at source.",
            "ka": "რეზიდენტის ან არარეზიდენტის მუდმივი დაწესებულების მიერ გადახდილი პროცენტი, როგორც წესი, 5 პროცენტით იბეგრება გადახდის წყაროსთან.",
        },
        smoke_contains={"ru": ["5%"], "en": ["5%"], "ka": ["5 პროცენტ"]},
    ),
    TaxFaqEntry(
        slug="royalties",
        topic="royalty_tax",
        article_ref="132",
        question_class="canonical_law_lookup",
        response_kind="subject_split_rate",
        note="20% for resident individual royalties; 5% for non-resident royalties.",
        sample_queries={
            "ru": "Какой налог на роялти в Грузии?",
            "en": "What is the tax rate on royalties in Georgia?",
            "ka": "რა გადასახადია როიალტზე საქართველოში?",
        },
        response_by_lang={
            "ru": "Для резидента-физлица роялти, как правило, облагаются у источника по ставке 20%, а для нерезидента — по ставке 5%.",
            "en": "For a resident individual, royalties are generally taxed at 20% at source. For a non-resident, royalties are generally taxed at 5% at source.",
            "ka": "რეზიდენტი ფიზიკური პირისთვის როიალტი, როგორც წესი, 20 პროცენტით იბეგრება გადახდის წყაროსთან, ხოლო არარეზიდენტისთვის — 5 პროცენტით.",
        },
        smoke_contains={"ru": ["20%", "5%"], "en": ["20%", "5%"], "ka": ["20 პროცენტ", "5 პროცენტ"]},
    ),
    TaxFaqEntry(
        slug="apartment-sale",
        topic="apartment_sale_tax",
        subject="individual",
        article_ref="81",
        question_class="canonical_law_lookup",
        response_kind="capital_gain_rate",
        note="Excess income from the sale of a residential apartment/house and attached land is taxed at 5%.",
        sample_queries={
            "ru": "Какой налог на продажу квартиры в Грузии?",
            "en": "What tax applies to the sale of an apartment in Georgia?",
            "ka": "რა გადასახადია ბინის გაყიდვაზე საქართველოში?",
        },
        response_by_lang={
            "ru": "Наметй доход физлица от продажи жилой квартиры (дома) и прикреплённого земельного участка в Грузии облагается по ставке 5%.",
            "en": "Excess income of an individual from the sale of a residential apartment (house) and the attached land plot in Georgia is taxed at 5%.",
            "ka": "ფიზიკური პირის მიერ საცხოვრებელი ბინის (სახლის) და მასზე დამაგრებული მიწის ნაკვეთის გაყიდვით მიღებული ნამეტი შემოსავალი საქართველოში 5 პროცენტით იბეგრება.",
        },
        smoke_contains={"ru": ["5%"], "en": ["5%"], "ka": ["5 პროცენტ"]},
    ),
    TaxFaqEntry(
        slug="vehicle-sale",
        topic="vehicle_sale_tax",
        subject="individual",
        article_ref="81",
        question_class="canonical_law_lookup",
        response_kind="capital_gain_rate",
        note="Excess income from the sale of a motor vehicle is taxed at 5%.",
        sample_queries={
            "ru": "Какой налог на продажу машины в Грузии?",
            "en": "What tax applies to the sale of a car in Georgia?",
            "ka": "რა გადასახადია მანქანის გაყიდვაზე საქართველოში?",
        },
        response_by_lang={
            "ru": "Наметй доход физлица от продажи автотранспортного средства в Грузии облагается по ставке 5%.",
            "en": "Excess income of an individual from the sale of a motor vehicle in Georgia is taxed at 5%.",
            "ka": "ფიზიკური პირის მიერ ავტოსატრანსპორტო საშუალების გაყიდვით მიღებული ნამეტი შემოსავალი საქართველოში 5 პროცენტით იბეგრება.",
        },
        smoke_contains={"ru": ["5%"], "en": ["5%"], "ka": ["5 პროცენტ"]},
    ),
    TaxFaqEntry(
        slug="vat-registration-threshold",
        topic="vat_registration_threshold",
        article_ref="165",
        question_class="canonical_law_lookup",
        response_kind="threshold_amount",
        note="VAT registration is generally required once taxable operations exceed GEL 100,000 during any continuous 12 calendar months.",
        sample_queries={
            "ru": "Какой порог регистрации по НДС в Грузии?",
            "en": "What is the VAT registration threshold in Georgia?",
            "ka": "რა არის დღგ-ის რეგისტრაციის ზღვარი საქართველოში?",
        },
        response_by_lang={
            "ru": "Обязательная регистрация по НДС в Грузии обычно возникает с дня превышения 100 000 лари по операциям, облагаемым НДС, за любые непрерывные 12 календарных месяцев.",
            "en": "Mandatory VAT registration in Georgia generally arises from the day taxable VAT operations exceed GEL 100,000 during any continuous 12 calendar months.",
            "ka": "საქართველოში დღგ-ის გადამხდელად სავალდებულო რეგისტრაცია, როგორც წესი, წარმოიშობა იმ დღიდან, როცა დღგ-ით დასაბეგრი ოპერაციების თანხა ნებისმიერ უწყვეტ 12 კალენდარულ თვეში 100 000 ლარს გადააჭარბებს.",
        },
        smoke_contains={"ru": ["100 000 лари"], "en": ["GEL 100,000"], "ka": ["100 000 ლარს"]},
    ),
    TaxFaqEntry(
        slug="nonresident-services-withholding",
        topic="nonresident_service_wht",
        subject="non_resident",
        article_ref="134",
        question_class="canonical_law_lookup",
        response_kind="service_payment_rate",
        note="For many Georgian-source payments to a non-resident without a permanent establishment, including many service payments, the withholding rule is generally 10%, with a 15% rule for preferential-tax jurisdictions and other code-specific exceptions.",
        sample_queries={
            "ru": "Какой налог у источника на услуги нерезидента в Грузии?",
            "en": "What withholding tax applies to non-resident services in Georgia?",
            "ka": "არარეზიდენტის მომსახურებაზე რა შეკავება მოქმედებს საქართველოში?",
        },
        response_by_lang={
            "ru": "Для многих выплат за услуги нерезиденту без постоянного учреждения в Грузии обычно применяется удержание у источника 10%. Для льготных юрисдикций и отдельных специальных случаев кодекс предусматривает другие правила, включая ставку 15%. Это именно правило удержания у источника; в некоторых ситуациях у операции отдельно могут возникать и вопросы по НДС.",
            "en": "For many service payments to a non-resident without a permanent establishment in Georgia, the withholding tax is generally 10%. For preferential-tax jurisdictions and certain special cases, the code provides different rules, including a 15% rate. This is the withholding-at-source rule; in some situations the transaction may also raise separate VAT issues.",
            "ka": "საქართველოში მუდმივი დაწესებულების არმქონე არარეზიდენტისთვის მომსახურების მრავალ გადახდაზე, როგორც წესი, 10%-იანი შეკავება მოქმედებს. შეღავათიანი დაბეგვრის იურისდიქციებისა და ცალკეული სპეციალური შემთხვევებისთვის კოდექსი სხვა წესებსაც ითვალისწინებს, მათ შორის 15%-იან განაკვეთს. ეს სწორედ გადახდის წყაროსთან შეკავების წესია; ზოგიერთ შემთხვევაში ოპერაციაზე ცალკე დღგ-ის საკითხიც შეიძლება წარმოიშვას.",
        },
        smoke_contains={"ru": ["10%", "15%"], "en": ["10%", "15%"], "ka": ["10%", "15%"]},
    ),
    TaxFaqEntry(
        slug="nonresident-withholding",
        topic="nonresident_wht",
        subject="non_resident",
        article_ref="134",
        question_class="canonical_law_lookup",
        response_kind="rate_summary",
        note="Short summary by income type: dividends, interest, royalties, many other payments, and the preferential-tax-jurisdiction rule.",
        sample_queries={
            "ru": "Какой налог удерживается у источника для нерезидента в Грузии?",
            "en": "What withholding tax applies to non-residents in Georgia?",
            "ka": "არარეზიდენტისთვის გადახდის წყაროსთან რა გადასახადი მოქმედებს საქართველოში?",
        },
        response_by_lang={
            "ru": "Для нерезидента без постоянного учреждения в Грузии удержание у источника зависит от вида дохода: дивиденды — по статье 130, проценты — 5%, роялти — 5%, многие другие доходы из грузинского источника — 10%, а в отдельных случаях применяется ставка по статье 81 или правило 15% для льготных юрисдикций.",
            "en": "For non-residents without a permanent establishment in Georgia, withholding depends on the income type: dividends under Article 130, interest 5%, royalties 5%, many other Georgian-source payments 10%, and some cases use the Article 81 rate or a 15% rule for preferential-tax jurisdictions.",
            "ka": "საქართველოში მუდმივი დაწესებულების არმქონე არარეზიდენტისთვის გადახდის წყაროსთან დაბეგვრა დამოკიდებულია შემოსავლის ტიპზე: დივიდენდები — 130-ე მუხლის მიხედვით, პროცენტები — 5%, როიალტი — 5%, სხვა რიგი ქართული წყაროს შემოსავლები — 10%, ხოლო ცალკეულ შემთხვევებში მოქმედებს 81-ე მუხლის განაკვეთი ან 15%-იანი წესი შეღავათიანი დაბეგვრის იურისდიქციებისთვის.",
        },
        smoke_contains={"ru": ["5%", "10%", "15%"], "en": ["5%", "10%", "15%"], "ka": ["5%", "10%", "15%"]},
    ),
    TaxFaqEntry(
        slug="tax-residency-individual",
        topic="tax_residency",
        subject="individual",
        article_ref="34",
        question_class="canonical_law_lookup",
        response_kind="residency_test_with_exceptions",
        match_goals=("residency_status",),
        note="183-day rule for the whole current tax year, with statutory exceptions and treaty caveat.",
        sample_queries={
            "ru": "Когда физлицо становится налоговым резидентом Грузии?",
            "en": "When does an individual become a tax resident of Georgia?",
            "ka": "როდის ითვლება ფიზიკური პირი საქართველოს საგადასახადო რეზიდენტად?",
        },
        response_by_lang={
            "ru": "Физическое лицо считается налоговым резидентом Грузии за весь текущий налоговый год, если оно фактически находилось в Грузии 183 дня или более в любом непрерывном 12-месячном периоде, заканчивающемся в этом налоговом году. Статья 34 также предусматривает специальные правила и исключения, поэтому для конкретной ситуации нужно проверить их и применимое соглашение об избежании двойного налогообложения.",
            "en": "An individual is treated as a Georgian tax resident for the whole current tax year if they were physically present in Georgia for 183 days or more during any continuous 12-month period ending in that tax year. Article 34 also contains special rules and exceptions, so the facts and any applicable double-tax treaty must be checked for an individual case.",
            "ka": "ფიზიკური პირი საქართველოს საგადასახადო რეზიდენტად ითვლება მთელი მიმდინარე საგადასახადო წლის განმავლობაში, თუ იგი საქართველოში ფაქტობრივად იმყოფებოდა 183 დღე ან მეტი ნებისმიერი უწყვეტი 12-თვიანი პერიოდის განმავლობაში, რომელიც ამ საგადასახადო წელს სრულდება. 34-ე მუხლი ასევე შეიცავს სპეციალურ წესებსა და გამონაკლისებს, ამიტომ კონკრეტულ შემთხვევაში უნდა შემოწმდეს ფაქტები და ორმაგი დაბეგვრის შესაბამისი შეთანხმება.",
        },
        smoke_contains={
            "ru": ["183", "12-месячном", "статья 34"],
            "en": ["183", "12-month", "Article 34"],
            "ka": ["183", "12-თვიანი", "34-ე მუხლი"],
        },
    ),
    TaxFaqEntry(
        slug="late-payment-interest",
        topic="late_payment_interest",
        article_ref="272",
        question_class="canonical_law_lookup",
        response_kind="daily_penalty_with_exceptions",
        match_goals=("penalty_rate",),
        note="0.05% of unpaid tax for each overdue day; general start date and exceptions remain visible.",
        sample_queries={
            "ru": "Какая пеня начисляется за просрочку уплаты налога в Грузии?",
            "en": "What late payment interest applies to overdue tax in Georgia?",
            "ka": "რა საურავი ერიცხება ვადაგადაცილებულ გადასახადს საქართველოში?",
        },
        response_by_lang={
            "ru": "За каждый день просрочки уплаты налога начисляется пеня в размере 0,05% неуплаченной суммы; по общему правилу начисление начинается со дня, следующего за установленным сроком уплаты. Статья 272, пункты 3–4, предусматривает исключения, которые нужно проверить применительно к конкретному обязательству.",
            "en": "Late-payment interest accrues at 0.05% of the unpaid tax for each overdue day and, as a general rule, starts on the day after the statutory payment deadline. Article 272, points 3–4, contains exceptions that must be checked for the specific tax obligation.",
            "ka": "გადასახადის გადახდის ვადის გადაცილების ყოველი დღისთვის საურავი შეადგენს გადაუხდელი გადასახადის 0,05%-ს და, საერთო წესით, დარიცხვა იწყება გადახდის ვადის მომდევნო დღიდან. 272-ე მუხლის 3–4 პუნქტებით გათვალისწინებული გამონაკლისები უნდა შემოწმდეს კონკრეტული საგადასახადო ვალდებულებისთვის.",
        },
        smoke_contains={
            "ru": ["0,05%", "пункты 3–4"],
            "en": ["0.05%", "points 3–4"],
            "ka": ["0,05%", "3–4 პუნქტებით"],
        },
    ),
    TaxFaqEntry(
        slug="tax-appeal-procedure",
        topic="tax",
        article_ref="296",
        additional_article_refs=("297", "299"),
        question_class="practical_tax_guidance",
        response_kind="appeal_path_and_deadline",
        match_goals=("appeal_procedure",),
        note="Tax appeal path, delivery-based 30-day deadline, electronic filing and court option.",
        sample_queries={
            "ru": "Как обжаловать решение налоговой?",
            "en": "How do I appeal a tax authority decision?",
            "ka": "როგორ გავასაჩივრო საგადასახადოს გადაწყვეტილება?",
        },
        response_by_lang={
            "ru": "Решение налогового органа можно обжаловать в течение 30 дней со дня его вручения. В системе Министерства финансов спор обычно начинается с подачи жалобы в Службу доходов и является двухэтапным; на любой стадии этого административного рассмотрения заявитель вправе обратиться в суд. Жалоба, как правило, подаётся в электронной форме. Если решение не было направлено заявителю, срок обжалования исчисляется со дня, когда он узнал о решении.",
            "en": "A tax authority decision may be appealed within 30 days after it is delivered to the person. Within the Ministry of Finance system, a dispute normally begins by filing a complaint with the Revenue Service and proceeds in two stages; the complainant may go to court at any stage of that administrative process. The complaint is generally filed electronically. If the decision was not sent to the complainant, the appeal period runs from the day the decision became known to them.",
            "ka": "საგადასახადო ორგანოს გადაწყვეტილება შეგიძლიათ გაასაჩივროთ მისი ჩაბარებიდან 30 დღის ვადაში. საქართველოს ფინანსთა სამინისტროს სისტემაში დავა, როგორც წესი, იწყება საჩივრის შემოსავლების სამსახურში წარდგენით და ორეტაპიანია; ამ ადმინისტრაციული დავის ნებისმიერ ეტაპზე მომჩივანს შეუძლია მიმართოს სასამართლოს. საჩივარი, როგორც წესი, ელექტრონული ფორმით წარედგინება. თუ გადაწყვეტილება მომჩივანს არ გაეგზავნა, გასაჩივრების ვადა აითვლება იმ დღიდან, როდესაც გადაწყვეტილება მისთვის ცნობილი გახდა.",
        },
        smoke_contains={
            "ru": ["30", "Службу доходов", "электронной форме"],
            "en": ["30", "Revenue Service", "filed electronically"],
            "ka": ["30", "შემოსავლების სამსახურში", "ელექტრონული ფორმით"],
        },
    ),
    TaxFaqEntry(
        slug="small-business-llc-ineligible",
        topic="small_business",
        subject="legal_entity",
        article_ref="88",
        additional_article_refs=("90",),
        question_class="canonical_law_lookup",
        response_kind="legal_form_eligibility",
        match_goals=("small_business_eligibility",),
        note="Article 88 limits small-business status to an entrepreneur natural person; article 90 provides the 1% rate.",
        sample_queries={
            "ru": "Может ли ООО применять режим малого бизнеса 1%?",
            "en": "Can an LLC use the 1% small business regime?",
            "ka": "შეუძლია თუ არა შპს-ს მცირე ბიზნესის 1%-იანი რეჟიმის გამოყენება?",
        },
        response_by_lang={
            "ru": "Нет. Режим малого бизнеса со ставкой 1% доступен только индивидуальному предпринимателю — физическому лицу. ООО применять его не может.",
            "en": "No. The 1% small business regime is available only to an individual entrepreneur. An LLC cannot use it.",
            "ka": "არა. მცირე ბიზნესის 1%-იანი რეჟიმი ხელმისაწვდომია მხოლოდ ინდივიდუალური მეწარმისთვის — ფიზიკური პირისთვის. შპს ამ რეჟიმს ვერ გამოიყენებს.",
        },
        smoke_contains={
            "ru": ["1%", "ООО", "индивидуальному"],
            "en": ["1%", "LLC", "individual"],
            "ka": ["1%", "შპს", "ინდივიდუალური"],
        },
    ),
]


CANONICAL_RATE_ARTICLES: Dict[str, str] = {
    entry.topic: entry.article_ref
    for entry in TAX_FAQ_MATRIX
    if (
        entry.question_class == "canonical_law_lookup"
        and "rate_lookup" in entry.match_goals
    )
}


FAQ_TOPICS: List[str] = [entry.topic for entry in TAX_FAQ_MATRIX]


def get_tax_faq_entry(topic: Optional[str]) -> Optional[TaxFaqEntry]:
    if not topic:
        return None
    for entry in TAX_FAQ_MATRIX:
        if entry.topic == topic:
            return entry
    return None


def get_tax_faq_entry_by_slug(slug: Optional[str]) -> Optional[TaxFaqEntry]:
    if not slug:
        return None
    for entry in TAX_FAQ_MATRIX:
        if entry.slug == slug:
            return entry
    return None


def match_tax_faq_entry(
    parsed: Mapping[str, Any],
    question_class: Optional[str],
) -> Optional[TaxFaqEntry]:
    """Select one parser-backed contract without broad text heuristics."""
    for entry in TAX_FAQ_MATRIX:
        if entry.matches(parsed, question_class):
            return entry
    return None


def build_tax_answer_contract_cases() -> List[Dict[str, object]]:
    return build_contract_cases(TAX_FAQ_MATRIX)
