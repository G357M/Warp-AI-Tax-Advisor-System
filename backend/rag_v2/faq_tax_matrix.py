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
        article_ref="202",
        additional_article_refs=("206",),
        question_class="practical_tax_guidance",
        response_kind="income_bands_with_exemption",
        note="Article 202 sets the individual income bands; Article 206 exempts non-land property when prior-year family income does not exceed GEL 40,000.",
        sample_queries={
            "ru": "Сколько налог на имущество для физлица в Тбилиси?",
            "en": "What is the property tax for an individual in Tbilisi?",
            "ka": "ფიზიკური პირისთვის ქონების გადასახადი რამდენია თბილისში?",
        },
        response_by_lang={
            "ru": "Для физлица ставка налога на облагаемое имущество зависит от дохода семьи: при доходе до 100 000 лари — от 0,05% до 0,2% рыночной стоимости, при доходе 100 000 лари и более — от 0,8% до 1%. Если доход семьи за предыдущий год не превышает 40 000 лари, облагаемое имущество физлица, кроме земли, освобождается от налога. Для земли, специальных льгот и точной суммы применяются отдельные правила.",
            "en": "For an individual, the property tax rate depends on family income: from 0.05% to 0.2% of market value where income is below GEL 100,000, and from 0.8% to 1% where income is GEL 100,000 or more. If the previous year's family income does not exceed GEL 40,000, the individual's taxable property other than land is exempt. Separate rules apply to land, special exemptions and the exact amount.",
            "ka": "ფიზიკური პირის ქონების გადასახადის განაკვეთი ოჯახის შემოსავალზეა დამოკიდებული: 100 000 ლარამდე შემოსავლისას — საბაზრო ღირებულების 0,05%-დან 0,2%-მდე, ხოლო 100 000 ლარის ან მეტი შემოსავლისას — 0,8%-დან 1%-მდე. თუ წინა წლის ოჯახის შემოსავალი 40 000 ლარს არ აღემატება, ფიზიკური პირის დასაბეგრი ქონება, მიწის გარდა, გადასახადისგან თავისუფლდება. მიწაზე, სპეციალურ შეღავათებსა და ზუსტ თანხაზე ცალკე წესები მოქმედებს.",
        },
        smoke_contains={
            "ru": ["0,05%", "0,2%", "0,8%", "1%", "40 000 лари"],
            "en": ["0.05%", "0.2%", "0.8%", "1%", "GEL 40,000"],
            "ka": ["0,05%", "0,2%", "0,8%", "1%", "40 000 ლარს"],
        },
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
        slug="property-tax-overview",
        topic="property_tax",
        article_ref="202",
        additional_article_refs=("206",),
        question_class="canonical_law_lookup",
        response_kind="taxpayer_specific_overview",
        note="A generic property-tax question must split company and individual rules instead of presenting one universal rate.",
        sample_queries={
            "ru": "Какая ставка налога на имущество в Грузии?",
            "en": "What is the property tax rate in Georgia?",
            "ka": "რა არის ქონების გადასახადის განაკვეთი საქართველოში?",
        },
        response_by_lang={
            "ru": "Единой ставки налога на имущество нет. Для предприятия или организации годовая ставка составляет не более 1% стоимости облагаемого имущества; для лизинговой компании по переданному в лизинг имуществу действует специальный предел 0,6%. Для физлица ставка зависит от дохода семьи: 0,05–0,2% при доходе до 100 000 лари и 0,8–1% при доходе 100 000 лари и более. При доходе семьи за предыдущий год не более 40 000 лари имущество физлица, кроме земли, освобождается.",
            "en": "There is no single property tax rate. For an enterprise or organization, the annual rate is no more than 1% of taxable property value; a special 0.6% cap applies to a leasing company's leased property. For an individual, the rate depends on family income: 0.05–0.2% below GEL 100,000 and 0.8–1% at GEL 100,000 or more. If the previous year's family income does not exceed GEL 40,000, the individual's property other than land is exempt.",
            "ka": "ქონების გადასახადის ერთი საერთო განაკვეთი არ არსებობს. საწარმოსთვის ან ორგანიზაციისთვის წლიური განაკვეთი დასაბეგრი ქონების ღირებულების არაუმეტეს 1%-ია; სალიზინგო კომპანიის ლიზინგით გაცემულ ქონებაზე სპეციალური 0,6%-იანი ზღვარი მოქმედებს. ფიზიკური პირისთვის განაკვეთი ოჯახის შემოსავალზეა დამოკიდებული: 100 000 ლარამდე — 0,05–0,2%, ხოლო 100 000 ლარის ან მეტის შემთხვევაში — 0,8–1%. თუ წინა წლის ოჯახის შემოსავალი 40 000 ლარს არ აღემატება, ფიზიკური პირის ქონება, მიწის გარდა, გადასახადისგან თავისუფლდება.",
        },
        smoke_contains={
            "ru": ["1%", "0,6%", "0,05–0,2%", "0,8–1%", "40 000 лари"],
            "en": ["1%", "0.6%", "0.05–0.2%", "0.8–1%", "GEL 40,000"],
            "ka": ["1%", "0,6%", "0,05–0,2%", "0,8–1%", "40 000 ლარს"],
        },
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
        slug="tour-operator-inbound-vat-exemption",
        topic="tour_operator_vat",
        article_ref="172",
        additional_article_refs=("157",),
        question_class="canonical_law_lookup",
        response_kind="conditional_exemption_with_credit",
        match_goals=("exemption_status",),
        note="The exemption applies to organized inbound tourism and supply of a qualifying tourist product, not every standalone tourism service.",
        sample_queries={
            "ru": "Освобождены ли услуги туроператора от НДС в Грузии?",
            "en": "Are tour operator services exempt from VAT in Georgia?",
            "ka": "გათავისუფლებულია თუ არა ტუროპერატორის მომსახურება დღგ-ისგან საქართველოში?",
        },
        response_by_lang={
            "ru": "От НДС с правом зачёта освобождается организованный туроператором въезд иностранного туриста в Грузию и предоставление ему в Грузии туристического продукта. Туристический продукт должен объединять не менее двух компонентов туристических услуг; поэтому освобождение не следует автоматически применять к любой отдельной туристической услуге.",
            "en": "The organized inbound travel of a foreign tourist to Georgia by a tour operator, together with the supply of a tourist product in Georgia, is VAT-exempt with the right to input VAT credit. A tourist product must combine at least two tourism-service components, so the exemption should not automatically be applied to every standalone tourism service.",
            "ka": "ტუროპერატორის მიერ უცხოელი ტურისტის საქართველოში ორგანიზებული შემოყვანა და მისთვის საქართველოში ტურისტული პროდუქტის მიწოდება დღგ-ისგან ჩათვლის უფლებით თავისუფლდება. ტურისტული პროდუქტი ტურისტული მომსახურების სულ მცირე ორ კომპონენტს უნდა აერთიანებდეს, ამიტომ შეღავათი ავტომატურად ყველა ცალკეულ ტურისტულ მომსახურებაზე არ ვრცელდება.",
        },
        smoke_contains={
            "ru": ["правом зачёта", "не менее двух"],
            "en": ["input VAT credit", "at least two"],
            "ka": ["ჩათვლის უფლებით", "სულ მცირე ორ"],
        },
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
        slug="profit-distribution-model",
        topic="profit_tax",
        article_ref="97",
        additional_article_refs=("98", "98-1"),
        question_class="canonical_law_lookup",
        response_kind="distributed_profit_model_with_deemed_objects",
        match_goals=("profit_distribution_model",),
        note="The Georgian distributed-profit model taxes Article 97 objects at the Article 98 rate; it is broader than dividends alone.",
        sample_queries={
            "ru": "Как работает эстонская модель налогообложения прибыли в Грузии?",
            "en": "How does the Estonian profit tax model work in Georgia?",
            "ka": "როგორ მუშაობს მოგების გადასახადის ესტონური მოდელი საქართველოში?",
        },
        response_by_lang={
            "ru": "В грузинской модели распределённой прибыли само получение и сохранение прибыли обычно не создаёт налог на прибыль. Налог возникает при распределении прибыли и по другим объектам статьи 97: расходам, не связанным с экономической деятельностью, безвозмездным передачам и сверхлимитным представительским расходам. По статье 98 сумма объекта делится на 0,85, после чего применяется ставка 15%; поэтому модель шире выплаты дивидендов, а просто умножать чистую выплату на 15% неверно.",
            "en": "Under Georgia's distributed-profit model, merely earning and retaining profit generally does not trigger profit tax. Tax arises on distributed profit and the other Article 97 objects: non-business expenses, gratuitous transfers and representation expenses above the statutory limit. Under Article 98, the object amount is divided by 0.85 and the 15% rate is then applied. The model is therefore broader than dividend payments alone, and simply multiplying the net distribution by 15% is not the statutory calculation.",
            "ka": "საქართველოს განაწილებული მოგების მოდელით მოგების მხოლოდ მიღება და გაუნაწილებლად დატოვება, როგორც წესი, მოგების გადასახადს არ წარმოშობს. გადასახადი წარმოიშობა განაწილებულ მოგებაზე და 97-ე მუხლის სხვა ობიექტებზე: ეკონომიკურ საქმიანობასთან დაუკავშირებელ ხარჯებზე, უსასყიდლო გადაცემებსა და ზღვრულ ოდენობაზე მეტ წარმომადგენლობით ხარჯებზე. 98-ე მუხლით ობიექტის თანხა იყოფა 0,85-ზე და შემდეგ ერიცხება 15%; ამიტომ მოდელი მხოლოდ დივიდენდის გაცემით არ შემოიფარგლება და წმინდა განაწილების 15%-ზე პირდაპირ გამრავლება კოდექსის გამოთვლა არ არის.",
        },
        smoke_contains={
            "ru": ["15%", "статьи 97", "0,85", "шире"],
            "en": ["15%", "Article 97", "0.85", "broader"],
            "ka": ["15%", "97-ე მუხლის", "0,85", "არ შემოიფარგლება"],
        },
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
    TaxFaqEntry(
        slug="funded-pension-contributions",
        topic="funded_pension",
        article_ref="3",
        registry_id="funded_pension_law",
        question_class="canonical_law_lookup",
        response_kind="tiered_contribution_rate",
        match_goals=("contribution_rate",),
        note="Employee/employer/self-employed rates and the three state-contribution income bands in article 3(6).",
        sample_queries={
            "ru": "Какие взносы действуют для накопительной пенсии в Грузии?",
            "en": "What funded pension contributions apply in Georgia?",
            "ka": "რა საპენსიო შენატანები მოქმედებს საქართველოს დაგროვებით საპენსიო სქემაში?",
        },
        response_by_lang={
            "ru": "Для участвующего работника работодатель перечисляет 2% облагаемой зарплаты за свой счёт и ещё 2% за счёт работника. Самозанятый перечисляет 4% своего дохода. Государство добавляет 2% в пределах первых 24 000 лари годового дохода, 1% на часть дохода свыше 24 000 до 60 000 лари включительно и не делает взнос на часть дохода свыше 60 000 лари. Обязанность и право отказа зависят от возраста и условий участия, поэтому их следует проверять отдельно.",
            "en": "For a participating employee, the employer transfers 2% of taxable salary at its own expense and another 2% at the employee's expense. A self-employed participant contributes 4% of their income. The state adds 2% on the first GEL 24,000 of annual income, 1% on the portion above GEL 24,000 up to and including GEL 60,000, and nothing on the portion above GEL 60,000. Mandatory participation and opt-out eligibility depend on age and participation conditions and must be checked separately.",
            "ka": "მონაწილე დასაქმებულისთვის დამსაქმებელი დასაბეგრი ხელფასის 2%-ს საკუთარი ხარჯით და კიდევ 2%-ს დასაქმებულის ხარჯით რიცხავს. თვითდასაქმებული თავისი შემოსავლის 4%-ს რიცხავს. სახელმწიფო წლიური შემოსავლის პირველ 24 000 ლარზე 2%-ს, 24 000 ლარის ზემოთ 60 000 ლარის ჩათვლით ნაწილზე 1%-ს რიცხავს, ხოლო 60 000 ლარის ზემოთ ნაწილზე შენატანს აღარ ახორციელებს. სავალდებულო მონაწილეობა და სქემიდან გასვლის უფლება ასაკსა და მონაწილეობის პირობებზეა დამოკიდებული და ცალკე უნდა შემოწმდეს.",
        },
        smoke_contains={
            "ru": ["2%", "4%", "24 000", "60 000"],
            "en": ["2%", "4%", "24,000", "60,000"],
            "ka": ["2%", "4%", "24 000", "60 000"],
        },
    ),
    TaxFaqEntry(
        slug="tax-limitation-period",
        topic="tax_limitation",
        article_ref="4",
        question_class="canonical_law_lookup",
        response_kind="limitation_period_with_exceptions",
        match_goals=("limitation_period",),
        note="General three-year assessment, sanction and audit limitation periods; article 4 contains extensions and exceptions.",
        sample_queries={
            "ru": "Какой срок давности по налоговой проверке в Грузии?",
            "en": "What is the tax audit limitation period in Georgia?",
            "ka": "რა არის საგადასახადო შემოწმების ხანდაზმულობის ვადა საქართველოში?",
        },
        response_by_lang={
            "ru": "Общий срок давности для начисления налога, большинства налоговых санкций и налоговой проверки составляет 3 года. Для проверки он исчисляется с окончания календарного года соответствующего проверяемого периода. Статья 4 предусматривает продление, приостановление и случаи неприменения срока, поэтому перед выводом по конкретному периоду нужно проверить все её условия.",
            "en": "The general limitation period for tax assessment, most tax sanctions and a tax audit is three years. For an audit, it runs from the end of the calendar year corresponding to the period under review. Article 4 provides extensions, suspensions and cases where the limitation does not apply, so all of its conditions must be checked for the specific period.",
            "ka": "გადასახადის დარიცხვის, საგადასახადო სანქციების უმეტესობისა და საგადასახადო შემოწმების საერთო ხანდაზმულობის ვადა 3 წელია. შემოწმებისთვის იგი აითვლება შესამოწმებელი პერიოდის შესაბამისი კალენდარული წლის დასრულებიდან. მე-4 მუხლი ითვალისწინებს ვადის გაგრძელების, შეჩერებისა და არგამოყენების შემთხვევებს, ამიტომ კონკრეტული პერიოდისთვის მისი ყველა პირობა უნდა შემოწმდეს.",
        },
        smoke_contains={"ru": ["3 года", "окончания календарного года"], "en": ["three years", "end of the calendar year"], "ka": ["3 წელია", "კალენდარული წლის დასრულებიდან"]},
    ),
    TaxFaqEntry(
        slug="tax-overpayment-refund",
        topic="tax_overpayment_refund",
        article_ref="63",
        question_class="canonical_law_lookup",
        response_kind="refund_deadline_and_offset",
        match_goals=("refund_procedure",),
        note="Refund on request within one month, offset against recognized debt, and the special 15-day mistaken-collection rule.",
        sample_queries={
            "ru": "Как вернуть переплату по налогам в Грузии?",
            "en": "How can I obtain a tax overpayment refund in Georgia?",
            "ka": "როგორ დავიბრუნო ზედმეტად გადახდილი გადასახადი საქართველოში?",
        },
        response_by_lang={
            "ru": "Переплата возвращается по требованию налогоплательщика не позднее одного месяца после подачи требования. Если имеется признанная налоговая задолженность, переплата направляется на её погашение. Для суммы, ошибочно списанной по инкассовому поручению, статья 63 устанавливает специальный срок возврата — не позднее 15 дней после заявления.",
            "en": "A tax overpayment is refunded at the taxpayer's request no later than one month after the request is filed. If there is recognized tax debt, the overpayment is applied against that debt. For an amount mistakenly collected under a tax collection order, Article 63 sets a special refund period of no later than 15 days after the application.",
            "ka": "ზედმეტად გადახდილი თანხა გადასახადის გადამხდელის მოთხოვნის საფუძველზე მოთხოვნის წარდგენიდან არაუგვიანეს 1 თვისა ბრუნდება. აღიარებული საგადასახადო დავალიანების არსებობისას ზედმეტობა მის დასაფარავად მიიმართება. საინკასო დავალებით შეცდომით ჩამოწერილი თანხისთვის 63-ე მუხლი ადგენს სპეციალურ ვადას — განცხადებიდან არაუგვიანეს 15 დღისა.",
        },
        smoke_contains={"ru": ["одного месяца", "15 дней"], "en": ["one month", "15 days"], "ka": ["1 თვისა", "15 დღისა"]},
    ),
    TaxFaqEntry(
        slug="tax-return-correction",
        topic="tax_return_correction",
        article_ref="69",
        question_class="canonical_law_lookup",
        response_kind="return_correction_rule",
        match_goals=("correction_procedure",),
        note="A liability-changing error must be corrected; a correction before the original deadline is treated as the original return.",
        sample_queries={
            "ru": "Как исправить ошибку в налоговой декларации?",
            "en": "How do I correct an error in a tax return?",
            "ka": "როგორ შევასწორო შეცდომა საგადასახადო დეკლარაციაში?",
        },
        response_by_lang={
            "ru": "Если ошибка в уже поданной декларации изменяет налоговое обязательство, лицо обязано внести соответствующее изменение или дополнение. Исправленная декларация, поданная до окончания первоначального срока, считается первоначально поданной. Для уже проверенного периода действуют дополнительные ограничения статьи 69, которые нужно проверить до исправления.",
            "en": "If an error in a filed tax return changes the tax liability, the person must make the corresponding amendment or addition. A corrected return filed before the original deadline is treated as the original return. Additional Article 69 restrictions apply to a period already audited and must be checked before amendment.",
            "ka": "თუ წარდგენილ დეკლარაციაში აღმოჩენილი შეცდომა საგადასახადო ვალდებულებას ცვლის, პირი ვალდებულია შეიტანოს შესაბამისი ცვლილება ან დამატება. თავდაპირველი ვადის გასვლამდე წარდგენილი შესწორებული დეკლარაცია თავდაპირველად წარდგენილად ითვლება. უკვე შემოწმებული პერიოდისთვის მოქმედებს 69-ე მუხლის დამატებითი შეზღუდვები, რომლებიც შესწორებამდე უნდა შემოწმდეს.",
        },
        smoke_contains={"ru": ["обязано", "первоначального срока"], "en": ["must", "original deadline"], "ka": ["ვალდებულია", "ვადის გასვლამდე"]},
    ),
    TaxFaqEntry(
        slug="payroll-declaration-deadline",
        topic="payroll_filing",
        article_ref="153",
        additional_article_refs=("154",),
        question_class="canonical_law_lookup",
        response_kind="monthly_payroll_filing_deadline",
        match_goals=("filing_deadline",),
        note="Monthly remuneration and withheld-tax return by the 15th; article 154 identifies withholding agents.",
        sample_queries={
            "ru": "Когда подавать декларацию по зарплате в Грузии?",
            "en": "What is the payroll tax return deadline in Georgia?",
            "ka": "როდის უნდა წარვადგინო ხელფასის დეკლარაცია საქართველოში?",
        },
        response_by_lang={
            "ru": "Предприниматель, предприятие или организация должны подать декларацию о выплаченной за отчётный месяц оплате труда и удержанном налоге не позднее 15-го числа следующего месяца. Обязанность удержания у источника у лица, выплачивающего зарплату, устанавливает статья 154 с предусмотренными в ней исключениями.",
            "en": "An entrepreneur, enterprise or organization must file the return for remuneration paid and tax withheld during the reporting month no later than the 15th day of the following month. Article 154 imposes withholding-agent duties on a salary payer, subject to its stated exceptions.",
            "ka": "მეწარმე ფიზიკური პირი, საწარმო ან ორგანიზაცია საანგარიშო თვის მიხედვით გაცემული შრომის ანაზღაურებისა და დაკავებული გადასახადის დეკლარაციას მომდევნო თვის 15 რიცხვამდე წარადგენს. ხელფასის გადამხდელის საგადასახადო აგენტის ვალდებულებას 154-ე მუხლი ადგენს, მასში მითითებული გამონაკლისების გათვალისწინებით.",
        },
        smoke_contains={"ru": ["15-го числа", "удержанном"], "en": ["15th day", "withheld"], "ka": ["15 რიცხვამდე", "დაკავებული"]},
    ),
    TaxFaqEntry(
        slug="vat-return-payment-deadline",
        topic="vat_return_deadline",
        article_ref="168",
        question_class="canonical_law_lookup",
        response_kind="vat_filing_and_payment_deadline",
        match_goals=("filing_deadline",),
        note="Registered taxable person files and pays by the 15th of the next month.",
        sample_queries={
            "ru": "Какой срок подачи декларации и уплаты НДС в Грузии?",
            "en": "What is the VAT return and payment deadline in Georgia?",
            "ka": "რა არის დღგ-ის დეკლარაციის წარდგენისა და გადახდის ვადა საქართველოში?",
        },
        response_by_lang={
            "ru": "Зарегистрированное плательщиком НДС налогооблагаемое лицо обязано подать декларацию по НДС не позднее 15-го числа месяца, следующего за отчётным периодом, и в тот же срок уплатить налог. Для импорта, reverse charge у незарегистрированного лица и отдельных товаров статья 168 предусматривает специальные правила.",
            "en": "A taxable person registered for VAT must file the VAT return no later than the 15th day of the month following the reporting period and pay the tax by the same deadline. Article 168 contains special rules for imports, reverse charge by an unregistered person and certain goods.",
            "ka": "დღგ-ის გადამხდელად რეგისტრირებული დასაბეგრი პირი დღგ-ის დეკლარაციას საანგარიშო პერიოდის მომდევნო თვის 15 რიცხვამდე წარადგენს და გადასახადსაც იმავე ვადაში იხდის. 168-ე მუხლი იმპორტის, არარეგისტრირებული პირის უკუდაბეგვრისა და ცალკეული საქონლისთვის სპეციალურ წესებს ითვალისწინებს.",
        },
        smoke_contains={"ru": ["15-го числа", "тот же срок"], "en": ["15th day", "same deadline"], "ka": ["15 რიცხვამდე", "იმავე ვადაში"]},
    ),
    TaxFaqEntry(
        slug="vat-reverse-charge-nonresident-services",
        topic="vat_reverse_charge",
        article_ref="161",
        question_class="canonical_law_lookup",
        response_kind="reverse_charge_scope",
        match_goals=("reverse_charge_rule",),
        note="Services supplied in Georgia by a non-established taxable person to a Georgian tax agent are reverse charged.",
        sample_queries={
            "ru": "Как применяется reverse charge НДС к услугам нерезидента?",
            "en": "How does reverse charge VAT apply to non-resident services in Georgia?",
            "ka": "როგორ იბეგრება უკუდაბეგვრით არარეზიდენტის მომსახურება საქართველოში?",
        },
        response_by_lang={
            "ru": "По правилу reverse charge облагаются услуги, оказанные на территории Грузии налоговому агенту налогооблагаемым лицом, которое не учреждено и обычно не проживает в Грузии либо не имеет здесь участвующего в услуге постоянного учреждения. Налоговым агентом обычно является учреждённое в Грузии лицо, кроме непредпринимателя-физлица и предприятия СИЗ; агент начисляет НДС на сумму, подлежащую выплате за услугу.",
            "en": "Reverse charge applies to services supplied in Georgia to a tax agent by a taxable person that is neither established nor ordinarily resident in Georgia, or that has no Georgian fixed establishment participating in the supply. The tax agent is generally a person established in Georgia, other than a non-entrepreneur individual or an FIZ enterprise, and accounts for VAT on the amount payable for the service.",
            "ka": "უკუდაბეგვრის წესით იბეგრება საქართველოში საგადასახადო აგენტისთვის იმ დასაბეგრი პირის მიერ გაწეული მომსახურება, რომელიც საქართველოში არ არის დაფუძნებული ან ჩვეულებრივ არ ცხოვრობს, ან აქ არ აქვს მომსახურებაში მონაწილე ფიქსირებული დაწესებულება. საგადასახადო აგენტია, როგორც წესი, საქართველოში დაფუძნებული პირი, გარდა არამეწარმე ფიზიკური პირისა და თიზ-ის საწარმოსი, და იგი დღგ-ს მომსახურებისთვის გასაცემ თანხაზე არიცხავს.",
        },
        smoke_contains={"ru": ["reverse charge", "налоговому агенту"], "en": ["Reverse charge", "tax agent"], "ka": ["უკუდაბეგვრის", "საგადასახადო აგენტ"]},
    ),
    TaxFaqEntry(
        slug="vat-input-deduction",
        topic="vat_input_deduction",
        article_ref="174",
        additional_article_refs=("175", "176"),
        question_class="canonical_law_lookup",
        response_kind="input_vat_eligibility_and_evidence",
        match_goals=("deduction_eligibility",),
        note="Registered taxable person, taxable-use purpose and statutory invoice/import/reverse-charge evidence.",
        sample_queries={
            "ru": "Когда можно принять входной НДС к вычету в Грузии?",
            "en": "When can a business claim input VAT in Georgia?",
            "ka": "როდის შეუძლია ბიზნესს დღგ-ის ჩათვლა საქართველოში?",
        },
        response_by_lang={
            "ru": "Право на вычет имеет зарегистрированное плательщиком НДС налогооблагаемое лицо, если товары или услуги предназначены либо используются для облагаемых НДС операций. Основанием обычно служит надлежащая налоговая счёт-фактура, импортная декларация или отражённый в декларации НДС по reverse charge. Для освобождённых и смешанных операций нужно отдельно проверить ограничения и пропорциональный вычет.",
            "en": "A taxable person registered for VAT may claim input VAT where the goods or services are intended for or used in VAT-taxable transactions. The evidence is normally a valid tax invoice, an import declaration, or reverse-charge VAT recorded in the VAT return. Restrictions and proportional deduction must be checked separately for exempt or mixed transactions.",
            "ka": "დღგ-ის ჩათვლის უფლება აქვს დღგ-ის გადამხდელად რეგისტრირებულ დასაბეგრ პირს, თუ საქონელი ან მომსახურება დღგ-ით დასაბეგრი ოპერაციისთვისაა განკუთვნილი ან გამოიყენება. საფუძველია, როგორც წესი, სათანადო საგადასახადო ანგარიშ-ფაქტურა, იმპორტის დეკლარაცია ან დღგ-ის დეკლარაციაში ასახული უკუდაბეგვრის დღგ. გათავისუფლებული ან შერეული ოპერაციებისთვის შეზღუდვები და პროპორციული ჩათვლა ცალკე უნდა შემოწმდეს.",
        },
        smoke_contains={"ru": ["зарегистрированное", "счёт-фактура"], "en": ["registered", "tax invoice"], "ka": ["რეგისტრირებულ", "ანგარიშ-ფაქტურა"]},
    ),
    TaxFaqEntry(
        slug="individual-property-tax-deadlines",
        topic="property_tax_filing",
        subject="individual",
        article_ref="205",
        question_class="canonical_law_lookup",
        response_kind="individual_property_filing_and_payment_deadlines",
        match_goals=("filing_deadline",),
        note="Individual return by 1 November and payment by 15 November, subject to filing exemptions.",
        sample_queries={
            "ru": "Когда физлицу подавать декларацию и платить налог на имущество?",
            "en": "What is the individual property tax return and payment deadline in Georgia?",
            "ka": "როდის უნდა წარადგინოს ფიზიკურმა პირმა ქონების გადასახადის დეკლარაცია და გადაიხადოს გადასახადი?",
        },
        response_by_lang={
            "ru": "Физическое лицо подаёт декларацию по налогу на имущество не позднее 1 ноября календарного года и уплачивает налог на имущество и землю не позднее 15 ноября. Статья 205 предусматривает случаи, когда декларацию можно не подавать, в том числе при отсутствии обязательства с учётом льгот, поэтому обязанность нужно проверить по конкретным доходам и имуществу.",
            "en": "An individual files the property tax return no later than 1 November of the calendar year and pays property and land tax no later than 15 November. Article 205 provides cases where no return is required, including where no liability arises after exemptions, so the obligation must be checked against the person's income and property.",
            "ka": "ფიზიკური პირი ქონების გადასახადის დეკლარაციას კალენდარული წლის 1 ნოემბრამდე წარადგენს, ხოლო ქონებასა და მიწაზე გადასახადს 15 ნოემბრამდე იხდის. 205-ე მუხლი ითვალისწინებს შემთხვევებს, როდესაც დეკლარაციის წარდგენა საჭირო არ არის, მათ შორის შეღავათების გათვალისწინებით ვალდებულების არარსებობისას, ამიტომ ვალდებულება კონკრეტული შემოსავლისა და ქონების მიხედვით უნდა შემოწმდეს.",
        },
        smoke_contains={"ru": ["1 ноября", "15 ноября"], "en": ["1 November", "15 November"], "ka": ["1 ნოემბრამდე", "15 ნოემბრამდე"]},
    ),
    TaxFaqEntry(
        slug="late-tax-return-penalty",
        topic="late_filing_penalty",
        article_ref="274",
        question_class="canonical_law_lookup",
        response_kind="tiered_late_filing_penalty",
        match_goals=("penalty_rate",),
        note="5% up to two months, 10% over two months, and no article-274 penalty where tax due is zero.",
        sample_queries={
            "ru": "Какой штраф за несвоевременную подачу налоговой декларации?",
            "en": "What is the late tax return filing penalty in Georgia?",
            "ka": "რა ჯარიმაა საგადასახადო დეკლარაციის დაგვიანებით წარდგენისთვის?",
        },
        response_by_lang={
            "ru": "Если просрочка подачи декларации или расчёта не превышает 2 месяцев, штраф составляет 5% налога, подлежащего начислению по этой декларации; при просрочке более 2 месяцев — 10%. Если подлежащая начислению сумма налога равна нулю, штраф по статье 274 не налагается.",
            "en": "If a tax return or calculation is filed no more than two months late, the penalty is 5% of the tax due under it; if the delay exceeds two months, the penalty is 10%. If the tax due is zero, no penalty is imposed under Article 274.",
            "ka": "თუ დეკლარაციის ან გაანგარიშების წარდგენის დაგვიანება 2 თვეს არ აღემატება, ჯარიმა ამ დეკლარაციით დასარიცხი გადასახადის 5%-ია; 2 თვეზე მეტი დაგვიანებისას — 10%. თუ დასარიცხი გადასახადი ნულის ტოლია, 274-ე მუხლით ჯარიმა არ გამოიყენება.",
        },
        smoke_contains={"ru": ["5%", "10%", "нулю"], "en": ["5%", "10%", "zero"], "ka": ["5%", "10%", "ნულის"]},
    ),
    TaxFaqEntry(
        slug="vat-registration-failure-penalty",
        topic="vat_registration_penalty",
        article_ref="282",
        question_class="canonical_law_lookup",
        response_kind="vat_registration_failure_penalty",
        match_goals=("penalty_rate",),
        note="5% of non-exempt VAT-taxable transactions during the unregistered activity period.",
        sample_queries={
            "ru": "Какой штраф за работу без регистрации по НДС?",
            "en": "What is the penalty for failing to register for VAT in Georgia?",
            "ka": "რა ჯარიმაა დღგ-ზე რეგისტრაციის გარეშე საქმიანობისთვის?",
        },
        response_by_lang={
            "ru": "Деятельность без обязательной регистрации плательщиком НДС влечёт штраф в размере 5% суммы облагаемых НДС операций, совершённых в период работы без регистрации; освобождённые операции в эту базу не включаются. Применение штрафа не заменяет проверку самой обязанности зарегистрироваться и налоговых обязательств за соответствующие периоды.",
            "en": "Operating without required VAT registration carries a penalty equal to 5% of the VAT-taxable transactions made during the unregistered period; exempt transactions are excluded from that base. The penalty does not replace verification of the registration duty and tax liabilities for the relevant periods.",
            "ka": "დღგ-ის გადამხდელად სავალდებულო რეგისტრაციის გარეშე საქმიანობა იწვევს რეგისტრაციის გარეშე პერიოდში განხორციელებული დღგ-ით დასაბეგრი ოპერაციების თანხის 5%-ის ოდენობის ჯარიმას; გათავისუფლებული ოპერაციები ამ ბაზაში არ შედის. ჯარიმა არ ცვლის რეგისტრაციის ვალდებულებისა და შესაბამისი პერიოდების საგადასახადო ვალდებულებების შემოწმებას.",
        },
        smoke_contains={"ru": ["5%", "освобождённые"], "en": ["5%", "exempt"], "ka": ["5%", "გათავისუფლებული"]},
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
TAX_CODE_FAQ_TOPICS: List[str] = [
    entry.topic for entry in TAX_FAQ_MATRIX if entry.registry_id == "tax_code"
]


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


def match_tax_faq_entry_for_parsed(parsed: Any) -> Optional[TaxFaqEntry]:
    """Resolve the contract and retrieval pointer from one parser result."""
    from .query_classifier import classify_query

    parsed_mapping = (
        parsed.model_dump() if hasattr(parsed, "model_dump") else dict(parsed or {})
    )
    classification = classify_query(parsed)
    return match_tax_faq_entry(parsed_mapping, classification.question_class)


def build_tax_answer_contract_cases() -> List[Dict[str, object]]:
    return build_contract_cases(TAX_FAQ_MATRIX)
