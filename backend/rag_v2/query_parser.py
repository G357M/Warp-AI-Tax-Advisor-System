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

    if any(token in q for token in ["импорт", "import", "იმპორტ"]) and any(token in q for token in ["ндс", "vat", "დღგ"]):
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

    if any(token in q for token in ["налогов", "tax code", "საგადასახადო კოდექს"]):
        if topic is None:
            topic = "tax"

    if is_income_tax_query or topic in {"small_business", "rental_income", "short_term_rental_tax", "apartment_sale_tax", "vehicle_sale_tax"} or any(token in q for token in ["физическ", "физлиц", "physical person", "физическое лицо", "individual", "ფიზიკური პირ", "ип", "individual entrepreneur", "sole proprietor", "მეწარმე ფიზიკურ"]):
        subject = "individual"
    elif topic == "property_tax_company" or any(token in q for token in ["юрлиц", "компан", "company", "юридическ"]):
        subject = "legal_entity"
    elif topic in {"nonresident_wht", "nonresident_service_wht"} or any(token in q for token in ["нерезидент", "non-resident", "non-residents", "არარეზიდენტ"]):
        subject = "non_resident"

    citations = extract_citations(raw_query)
    point_ref = extract_point_ref(raw_query)
    document_ref = citations["doc_numbers"][0] if citations["doc_numbers"] else None
    article_ref = citations["articles"][0] if citations["articles"] else None
    decision_ref = document_ref if document_ref and "/" in document_ref else None

    if any(token in q for token in ["как рассчиты", "как считать", "как применять", "how to calculate", "როგორ გამოითვლ", "როგორ ითვლ"]):
        goal = "calculation_rule"
        signals.append("practical")
    elif any(token in q for token in ["ставка", "rate", "withholding", "threshold", "limit", "განაკვეთი", "процент", "порог", "лимит", "ზღვარი"]) or topic in {"nonresident_wht", "nonresident_service_wht", "vat_registration_timing", "vat_deregistration_threshold"} or (is_income_tax_query and any(token in q for token in income_tax_rate_markers)) or (topic in {"vat", "profit_tax", "dividend_tax", "interest_tax", "royalty_tax", "small_business", "rental_income", "short_term_rental_tax", "apartment_sale_tax", "vehicle_sale_tax", "import_vat", "vat_registration_threshold", "vat_registration_timing", "vat_deregistration_threshold", "nonresident_wht", "nonresident_service_wht", "excise", "customs", "property_tax_company"} and any(token in q for token in generic_rate_question_markers)) or (topic == "property_tax" and subject == "individual" and any(token in q for token in generic_rate_question_markers)):
        goal = "rate_lookup"
        signals.append("normative")
    elif (not article_ref and not point_ref) and any(token in q for token in ["что в документе", "что в документ", "document", "документ", "handbook", "что сказано", "რა წერია დოკუმენტ", "რა არის დოკუმენტ"]):
        goal = "document_summary"
        signals.append("named_document")
    elif any(token in q for token in ["решение", "спор", "жалоб", "დავა", "გადაწყვეტილებ"]):
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
