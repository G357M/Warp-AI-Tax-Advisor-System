from __future__ import annotations

import re
from .models import ParsedQuery
from .citation_resolver import extract_citations
from .point_resolver import extract_point_ref


def _normalize(text: str) -> str:
    text = (text or "").strip().lower()
    text = re.sub(r"\s+", " ", text)
    return text


def parse_query(raw_query: str, language: str = "ru") -> ParsedQuery:
    q = _normalize(raw_query)
    signals = []
    topic = None
    subject = None
    goal = None
    locality = None

    # A generic "how do I appeal?" question asks for the statutory procedure,
    # not for the outcome of an individual dispute.  Keep this signal separate
    # across all supported languages so retrieval can prefer the Tax Code over
    # fact-heavy court decisions.
    appeal_procedure_markers = [
        "как обжаловать",
        "как подать жалоб",
        "куда обжаловать",
        "порядок обжал",
        "срок обжал",
        "how do i appeal",
        "how can i appeal",
        "how to appeal",
        "appeal procedure",
        "where to appeal",
        "appeal deadline",
        "file an appeal",
        "როგორ გავასაჩივრ",
        "როგორ უნდა გავასაჩივრ",
        "სად გავასაჩივრ",
        "გასაჩივრების წეს",
        "გასაჩივრების ვად",
        "საჩივარი როგორ",
        "საჩივრის წარდგენ",
    ]
    is_appeal_procedure_query = any(
        token in q for token in appeal_procedure_markers
    )

    tax_residency_markers = [
        "налоговый резидент",
        "налоговым резидентом",
        "резидентом грузии",
        "резидентство грузии",
        "183 дня",
        "tax resident",
        "tax residency",
        "resident of georgia",
        "183 days",
        "საგადასახადო რეზიდენტ",
        "საქართველოს რეზიდენტ",
        "183 დღე",
        "რეზიდენტი ვარ",
    ]
    is_tax_residency_query = any(token in q for token in tax_residency_markers)

    late_payment_penalty_markers = [
        "пеня за просрочку",
        "пени за просрочку",
        "пеня начис",
        "пеня по налог",
        "просрочку уплаты налог",
        "просрочка уплаты налог",
        "просроченный налог",
        "late payment interest",
        "late tax payment",
        "overdue tax",
        "tax arrears interest",
        "საურავი",
        "ვადაგადაცილებულ გადასახად",
        "გადასახადის დაგვიანებით",
    ]
    is_late_payment_penalty_query = any(
        token in q for token in late_payment_penalty_markers
    )

    is_tour_operator_vat_query = (
        any(token in q for token in ("туропер", "tour oper", "ტუროპერ"))
        and any(token in q for token in ("ндс", "vat", "დღგ"))
    )

    funded_pension_markers = [
        "накопительн", "пенсионн взнос", "взносы в пенс",
        "funded pension", "pension contribution",
        "დაგროვებითი პენს", "საპენსიო შენატან",
    ]
    is_funded_pension_query = any(token in q for token in funded_pension_markers)

    tax_limitation_markers = [
        "срок давности по налог", "налоговая давность", "давность налоговой провер",
        "tax limitation period", "tax statute of limitations", "tax audit limitation",
        "საგადასახადო ხანდაზმულ", "გადასახადის ხანდაზმულ", "შემოწმების ხანდაზმულ",
    ]
    is_tax_limitation_query = any(token in q for token in tax_limitation_markers)

    tax_overpayment_refund_markers = [
        "возврат переплаты", "вернуть переплату по налог", "переплата по налог",
        "tax overpayment refund", "refund overpaid tax", "tax refund of overpayment",
        "ზედმეტად გადახდილი გადასახად", "ზედმეტად გადახდილი თანხის დაბრუნ",
    ]
    is_tax_overpayment_refund_query = any(
        token in q for token in tax_overpayment_refund_markers
    )

    tax_return_correction_markers = [
        "исправить налоговую декларацию", "ошибку в налоговой декларации", "уточненная декларация",
        "исправленная декларация", "корректировка декларации",
        "amend a tax return", "correct a tax return", "correct an error in a tax return", "corrected tax return",
        "საგადასახადო დეკლარაციის შესწორ", "დეკლარაციაში ცვლილების შეტანა", "შეცდომა საგადასახადო დეკლარაციაში",
    ]
    is_tax_return_correction_query = any(
        token in q for token in tax_return_correction_markers
    )

    payroll_filing_markers = [
        "декларация по зарплат", "декларацию по зарплат", "отчет по зарплат", "срок зарплатной декларации",
        "payroll declaration", "payroll tax return", "salary tax return deadline",
        "ხელფასის დეკლარაცი", "შრომის ანაზღაურების დეკლარაცი",
    ]
    is_payroll_filing_query = any(token in q for token in payroll_filing_markers)

    vat_return_deadline_markers = [
        "декларация по ндс", "срок подачи ндс", "срок уплаты ндс",
        "срок подачи декларации и уплаты ндс",
        "когда платить ндс", "vat return deadline", "vat filing deadline",
        "when is vat due", "vat return and payment deadline",
        "დღგ-ის დეკლარაციის ვადა", "დღგ-ის გადახდის ვადა",
        "დღგ-ის დეკლარაციის წარდგენისა და გადახდის ვადა",
    ]
    is_vat_return_deadline_query = any(
        token in q for token in vat_return_deadline_markers
    )

    vat_reverse_charge_markers = [
        "обратное начисление ндс", "реверсный ндс", "reverse charge ндс", "ндс по услугам нерезидента",
        "reverse charge vat", "vat on non-resident services", "უკუდაბეგვრ",
        "არარეზიდენტის მომსახურების დღგ",
    ]
    is_vat_reverse_charge_query = any(token in q for token in vat_reverse_charge_markers)

    vat_input_deduction_markers = [
        "вычет входного ндс", "входной ндс", "зачет входного ндс", "зачет ндс", "вычет ндс",
        "input vat deduction", "input vat credit", "claim input vat",
        "დღგ-ის ჩათვლა", "ჩასათვლელი დღგ",
    ]
    is_vat_input_deduction_query = any(
        token in q for token in vat_input_deduction_markers
    )

    property_tax_filing_markers = [
        "декларация по налогу на имущество", "срок уплаты налога на имущество",
        "когда платить налог на имущество", "декларацию и платить налог на имущество",
        "property tax return deadline",
        "property tax payment deadline", "property tax return and payment deadline",
        "ქონების გადასახადის დეკლარაციის ვადა",
        "ქონების გადასახადის გადახდის ვადა",
        "ქონების გადასახადის დეკლარაცია და გადაიხადოს",
    ]
    is_property_tax_filing_query = any(
        token in q for token in property_tax_filing_markers
    )

    late_filing_penalty_markers = [
        "штраф за несвоевременную декларацию", "штраф за несвоевременную подачу налоговой декларации",
        "штраф за просрочку декларации", "late filing penalty", "late tax return penalty",
        "late tax return filing penalty", "დეკლარაციის დაგვიანებით", "დეკლარაციის ვადის დარღვევა",
    ]
    is_late_filing_penalty_query = any(
        token in q for token in late_filing_penalty_markers
    )

    vat_registration_penalty_markers = [
        "штраф без регистрации по ндс", "работу без регистрации по ндс", "штраф за отсутствие регистрации по ндс",
        "vat registration failure penalty", "penalty for not registering for vat", "failing to register for vat",
        "დღგ-ზე რეგისტრაციის გარეშე საქმიანობის ჯარიმა",
        "დღგ-ის რეგისტრაციის გარეშე საქმიანობის ჯარიმა", "დღგ-ზე რეგისტრაციის გარეშე საქმიან",
    ]
    is_vat_registration_penalty_query = any(
        token in q for token in vat_registration_penalty_markers
    )

    is_profit_distribution_model_query = any(
        token in q for token in ("эстонск", "estonian", "ესტონ")
    )

    # The homepage asks whether an LLC may use the "1% tax regime" without
    # naming small-business status.  Treat the legal form + regime combination
    # as an eligibility question.  Exclude property-tax wording because a 1%
    # company property-tax question belongs to a different Tax Code provision.
    legal_entity_markers = [
        "ооо", "о.о.о", "llc", "ltd", "шпс", "შპს", "компани", "company",
        "юридическ", "legal entity", "საწარმო",
    ]
    one_percent_regime_markers = [
        "1%", "1 %", "1%-იან", "1 %-იან", "1 percent", "one percent",
    ]
    small_business_regime_markers = [
        "малого бизнес", "малый бизнес", "small business", "მცირე ბიზნეს",
    ]
    eligibility_markers = [
        "может ли", "может применять", "применять", "использовать", "режим",
        "can ", "can an", "use", "regime", "eligible",
        "შეუძლია", "გამოიყენ", "რეჟიმ",
    ]
    property_tax_markers = [
        "налог на имущество", "имущественный налог", "имуществ", "property tax",
        "ქონების გადასახად",
    ]
    is_small_business_legal_form_query = (
        any(token in q for token in legal_entity_markers)
        and (
            any(token in q for token in small_business_regime_markers)
            or (
                any(token in q for token in one_percent_regime_markers)
                and any(token in q for token in eligibility_markers)
            )
        )
        and not any(token in q for token in property_tax_markers)
    )

    income_tax_markers = [
        "подоход",
        "ндфл",
        "налог на доходы физ",
        "personal income tax",
        "income tax",
        "საშემოსავლო",
    ]
    income_tax_rate_markers = [
        "сколько",
        "сколько составляет",
        "какой",
        "what is",
        "how much",
        "რამდენ",
        "რა პროცენტ",
        "პროცენტ",
    ]
    generic_rate_question_markers = [
        "сколько",
        "сколько составляет",
        "какой",
        "какая",
        "есть ли",
        "нужно ли",
        "облагается ли",
        "what is",
        "what tax",
        "which",
        "is there",
        "does",
        "applies",
        "subject to",
        "charged",
        "taxed",
        "trigger",
        "how much",
        "რა არის",
        "არის თუ არა",
        "აქვს თუ არა",
        "უნდა გადავიხადო",
        "იბეგრებ",
        "რა გადასახად",
        "რამდენ",
        "რა პროცენტ",
        "პროცент",
    ]
    salary_tax_markers = [
        "налог на зарплат",
        "налог с зарплат",
        "salary tax",
        "tax on salary",
        "payroll tax",
        "ხელფასის გადასახად",
    ]
    is_income_tax_query = any(token in q for token in income_tax_markers) or any(token in q for token in salary_tax_markers)

    short_term_markers = ["посуточ", "краткосрочн", "airbnb", "booking.com", "booking", "short-term rental", "short term rental", "short-term let", "short term let", "airbnb income", "მოკლევადიან გაქირავ", "მოკლე ვადით გაცემ", "booking.com-ით"]

    if is_funded_pension_query:
        topic = "funded_pension"
    elif is_tax_limitation_query:
        topic = "tax_limitation"
    elif is_tax_overpayment_refund_query:
        topic = "tax_overpayment_refund"
    elif is_tax_return_correction_query:
        topic = "tax_return_correction"
    elif is_payroll_filing_query:
        topic = "payroll_filing"
    elif is_vat_return_deadline_query:
        topic = "vat_return_deadline"
    elif is_vat_reverse_charge_query:
        topic = "vat_reverse_charge"
    elif is_vat_input_deduction_query:
        topic = "vat_input_deduction"
    elif is_property_tax_filing_query:
        topic = "property_tax_filing"
    elif is_late_filing_penalty_query:
        topic = "late_filing_penalty"
    elif is_vat_registration_penalty_query:
        topic = "vat_registration_penalty"
    elif is_tax_residency_query:
        topic = "tax_residency"
    elif is_late_payment_penalty_query:
        topic = "late_payment_interest"
    elif is_profit_distribution_model_query:
        topic = "profit_tax"
    elif is_tour_operator_vat_query:
        topic = "tour_operator_vat"
    elif is_small_business_legal_form_query:
        topic = "small_business"
    elif any(token in q for token in ["импорт", "import", "იმპორტ"]) and any(token in q for token in ["ндс", "vat", "დღგ"]):
        topic = "import_vat"
    elif any(token in q for token in short_term_markers):
        topic = "short_term_rental_tax"
    elif any(token in q for token in ["аннулировать регистрацию по ндс", "отмена регистрации по ндс", "отмены регистрации по ндс", "снять с ндс", "сняться с ндс", "отменить ндс регистрацию", "vat deregistration threshold", "vat deregistration", "cancel vat registration", "cancel vat", "deregister from vat", "vat cancellation", "რეგისტრაციის გაუქმებისთვის", "რეგისტრაციის გაუქმება", "უქმდება დღგ-ის გადამხდელად რეგისტრაცია", "დღგ-ის გადამხდელად რეგისტრაციის გაუქმება", "დღგ-დან მოხსნა", "როგორ მოვიხსნა დღგ-დან", "მოვიხსნა დღგ-დან", "როგორ გავაუქმო დღგ-ის რეგისტრაცია", "გავაუქმო დღგ-ის რეგისტრაცია"]):
        topic = "vat_deregistration_threshold"
    elif any(token in q for token in ["с какого момента возникает обязанность регистрации по ндс", "когда возникает обязанность по ндс", "когда надо регистрироваться по ндс", "when does the vat registration obligation arise", "when must register for vat", "when do you need to register for vat", "when does vat registration start", "როდის წარმოიშობა დღგ-ის გადამხდელად რეგისტრაციის ვალდებულება", "როდის არის დღგ-ზე რეგისტრაცია სავალდებულო", "როდის ხდება დღგ-ზე რეგისტრაცია სავალდებულო", "როდის უნდა დავრეგისტრირდე დღგ-ზე", "როდის მიწევს დღგ-ზე დარეგისტრირება", "როდის ვალდებული ვარ დღგ-ზე დარეგისტრირდე", "დღგ-ზე დარეგისტრირება", "100 000 ლარის გადაჭარბებისას"]):
        topic = "vat_registration_timing"
    elif any(token in q for token in ["порог регистрации по ндс", "лимит по ндс", "порог для ндс", "vat registration threshold", "vat threshold", "vat limit", "when vat threshold is reached", "დღგ-ის რეგისტრაციის ზღვარი", "დღგის რეგისტრაციის ზღვარი", "დღგ-ის ლიმიტი", "100 000 ლარს", "100 000 lari"]):
        topic = "vat_registration_threshold"
    elif any(token in q for token in ["ндс", "vat", "დღგ"]):
        topic = "vat"
    elif any(token in q for token in ["дивиденд", "dividend", "დივიდენდ"]):
        topic = "dividend_tax"
    elif (not is_income_tax_query) and any(token in q for token in ["interest", "проценты", "процент по вкладу", "საპროცენტო", "პროცენტზე", "პროცენტის გადასახად"]):
        topic = "interest_tax"
    elif any(token in q for token in ["роялти", "royalt", "როიალტ"]):
        topic = "royalty_tax"
    elif any(token in q for token in ["малого бизнес", "small business", "მცირე ბიზნეს", "მცირე მეწარმ"]):
        topic = "small_business"
    elif any(token in q for token in ["услуг нерезидент", "услуги нерезидент", "по услугам нерезидента", "оплата услуг нерезидент", "services paid to a non-resident", "services to a non-resident", "non-resident services", "service payments to a non-resident", "service fee to a non-resident", "tax on payments for services to a non-resident", "არარეზიდენტის მომსახურებ", "მომსახურებაზე", "მომსახურების გადახდა არარეზიდენტ", "არარეზიდენტს მომსახურების გადახდაზე", "არარეზიდენტის მომსახურების გადახდაზე"]):
        topic = "nonresident_service_wht"
    elif any(token in q for token in ["нерезидент", "non-resident", "non-residents", "არარეზიდენტ"]):
        topic = "nonresident_wht"
    elif any(token in q for token in ["продажу дома", "продажа дома", "продать дом", "налог при продаже дома", "продажу квартир", "продажа квартир", "продажу квартиры", "продать квартиру", "налог при продаже квартиры", "sale of apartment", "sale of an apartment", "sell an apartment", "tax on selling an apartment", "sale of house", "sale of a house", "sell a house", "tax on selling a house", "sale of flat", "sale of a flat", "apartment sale", "house sale", "flat sale", "ბინის გაყიდვ", "სახლის გაყიდვ"]):
        topic = "apartment_sale_tax"
    elif any(token in q for token in ["продажу машин", "продажа машин", "продажу машины", "продать машину", "налог при продаже машины", "sale of car", "sale of a car", "sell a car", "tax on selling a car", "sale of vehicle", "sale of a vehicle", "car sale", "vehicle sale", "მანქანის გაყიდვ", "ავტოსატრანსპორტო საშუალების გაყიდვ"]):
        topic = "vehicle_sale_tax"
    elif any(token in q for token in ["аренд", "сдач", "rent", "rental", "გაქირავ", "ქირავ", "ქირიდან"]):
        topic = "rental_income"
    elif any(token in q for token in ["налог на имущество для компании", "налог на имущество для юр", "property tax for a company", "property tax for company", "კომპანიისთვის ქონების გადასახადი"]):
        topic = "property_tax_company"
    elif any(token in q for token in ["имуществ", "property tax", "ქონების გადასახ"]):
        topic = "property_tax"
    elif any(token in q for token in ["прибыл", "profit tax", "მოგების გადასახ"]):
        topic = "profit_tax"
    elif any(token in q for token in ["акциз", "excise", "აქციზ"]):
        topic = "excise"
    elif any(token in q for token in ["тамож", "customs", "საბაჟო"]):
        topic = "customs"
    elif is_income_tax_query:
        topic = "tax"

    if is_appeal_procedure_query and topic is None:
        topic = "tax"

    if any(
        token in q for token in ["налогов", "tax code", "საგადასახადო კოდექს"]
    ) or re.search(r"\bнк(?:\s+грузии)?\b", q):
        if topic is None:
            topic = "tax"

    if is_tax_residency_query:
        subject = "individual"
    elif is_small_business_legal_form_query:
        subject = "legal_entity"
    elif is_income_tax_query or topic in {"small_business", "rental_income", "short_term_rental_tax", "apartment_sale_tax", "vehicle_sale_tax"} or any(token in q for token in ["физическ", "физлиц", "physical person", "физическое лицо", "individual", "ფიზიკური პირ", "ип", "individual entrepreneur", "sole proprietor", "მეწარმე ფიზიკურ"]):
        subject = "individual"
    elif topic == "property_tax_company" or any(token in q for token in legal_entity_markers):
        subject = "legal_entity"
    elif topic in {"nonresident_wht", "nonresident_service_wht"} or any(token in q for token in ["нерезидент", "non-resident", "non-residents", "არარეზიდენტ"]):
        subject = "non_resident"

    citations = extract_citations(raw_query)
    point_ref = extract_point_ref(raw_query)
    document_ref = citations["doc_numbers"][0] if citations["doc_numbers"] else None
    article_ref = citations["articles"][0] if citations["articles"] else None
    decision_ref = document_ref if document_ref and "/" in document_ref else None

    if is_funded_pension_query:
        goal = "contribution_rate"
        signals.extend(["normative", "funded_pension_contribution"])
    elif is_tax_limitation_query:
        goal = "limitation_period"
        signals.extend(["normative", "tax_limitation"])
    elif is_tax_overpayment_refund_query:
        goal = "refund_procedure"
        signals.extend(["practical", "tax_overpayment_refund"])
    elif is_tax_return_correction_query:
        goal = "correction_procedure"
        signals.extend(["practical", "tax_return_correction"])
    elif is_payroll_filing_query or is_vat_return_deadline_query or is_property_tax_filing_query:
        goal = "filing_deadline"
        signals.extend(["practical", "filing_deadline"])
    elif is_vat_reverse_charge_query:
        goal = "reverse_charge_rule"
        signals.extend(["normative", "vat_reverse_charge"])
    elif is_vat_input_deduction_query:
        goal = "deduction_eligibility"
        signals.extend(["normative", "vat_input_deduction"])
    elif is_late_filing_penalty_query or is_vat_registration_penalty_query:
        goal = "penalty_rate"
        signals.extend(["normative", "filing_or_registration_penalty"])
    elif is_tax_residency_query:
        goal = "residency_status"
        signals.extend(["normative", "tax_residency"])
    elif is_late_payment_penalty_query:
        goal = "penalty_rate"
        signals.extend(["normative", "late_payment_penalty"])
    elif is_profit_distribution_model_query:
        goal = "profit_distribution_model"
        signals.extend(["normative", "profit_distribution_model"])
    elif is_tour_operator_vat_query:
        goal = "exemption_status"
        signals.extend(["normative", "tour_operator_vat_exemption"])
    elif is_appeal_procedure_query and not decision_ref:
        goal = "appeal_procedure"
        signals.extend(["practical", "appeal_procedure"])
    elif is_small_business_legal_form_query:
        goal = "small_business_eligibility"
        signals.extend(["normative", "small_business_legal_form"])
    elif any(token in q for token in ["как рассчиты", "как считать", "как применять", "how to calculate", "როგორ გამოითვლ", "როგორ ითვლ"]):
        goal = "calculation_rule"
        signals.append("practical")
    elif any(token in q for token in ["ставка", "rate", "withholding", "threshold", "limit", "განაკვეთი", "процент", "порог", "лимит", "ზღვარი"]) or topic in {"nonresident_wht", "nonresident_service_wht", "vat_registration_timing", "vat_deregistration_threshold"} or (is_income_tax_query and any(token in q for token in income_tax_rate_markers)) or (topic in {"vat", "profit_tax", "dividend_tax", "interest_tax", "royalty_tax", "small_business", "rental_income", "short_term_rental_tax", "apartment_sale_tax", "vehicle_sale_tax", "import_vat", "vat_registration_threshold", "vat_registration_timing", "vat_deregistration_threshold", "nonresident_wht", "nonresident_service_wht", "excise", "customs", "property_tax_company"} and any(token in q for token in generic_rate_question_markers)) or (topic == "property_tax" and subject == "individual" and any(token in q for token in generic_rate_question_markers)):
        goal = "rate_lookup"
        signals.append("normative")
    elif (not article_ref and not point_ref) and any(token in q for token in ["что в документе", "что в документ", "document", "документ", "handbook", "что сказано", "რა წერია დოკუმენტ", "რა არის დოკუმენტ"]):
        goal = "document_summary"
        signals.append("named_document")
    elif any(token in q for token in [
        "решение", "спор", "жалоб",
        "dispute", "decision", "appeal",
        "დავა", "გადაწყვეტილებ",
    ]):
        goal = "dispute_outcome"
        signals.append("dispute")
    elif any(token in q for token in ["изменил", "изменени", "редакц", "amendment", "amendments", "change to", "changes to", "changed", "поправк", "ცვლილებ"]):
        goal = "amendment_tracking"
        signals.append("amendment")

    if any(token in q for token in ["дманиси", "dmanisi", "დმანის"]):
        locality = "dmanisi"
        signals.append("locality")
    elif any(token in q for token in ["тбилиси", "tbilisi", "თბილის"]):
        locality = "tbilisi"
        signals.append("locality")
    elif any(token in q for token in ["gurjaani", "гурджаани", "გურჯაან"]):
        locality = "gurjaani"
        signals.append("locality")
    elif "муниципал" in q:
        locality = "municipality"
        signals.append("locality")

    if document_ref:
        signals.append("document_ref")
    if article_ref:
        signals.append("article_ref")
    if point_ref:
        signals.append("point_ref")

    return ParsedQuery(
        raw_query=raw_query,
        language=language,
        normalized_query=q,
        topic=topic,
        subject=subject,
        goal=goal,
        document_ref=document_ref,
        article_ref=article_ref,
        point_ref=point_ref,
        decision_ref=decision_ref,
        locality=locality,
        signals=signals,
        entities={
            "topic": topic,
            "subject": subject,
            "goal": goal,
            "locality": locality,
            "document_ref": document_ref,
            "article_ref": article_ref,
            "point_ref": point_ref,
            "decision_ref": decision_ref,
        },
    )
