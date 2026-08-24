from __future__ import annotations

import os
import re
from typing import Any, Dict, Optional, Tuple

from .faq_tax_matrix import get_tax_faq_entry


def _disabled_guard_topics() -> set:
    """Per-topic kill switch for the authoritative guards (П3 of the hardening
    plan): INFOHUB_DISABLED_GUARDS=vat_threshold,estonian_model routes those
    topics through real retrieval instead of the curated answer. Env-driven so
    a guard flips with a container recreate, no rebuild needed."""
    raw = os.getenv("INFOHUB_DISABLED_GUARDS", "")
    return {t.strip() for t in raw.split(",") if t.strip()}


def _response_language(trace: Any) -> str:
    parsed = getattr(trace, "parsed_query", None) or {}
    language = str(parsed.get("language") or "ru").strip().lower()
    return language if language in {"ru", "en", "ka"} else "ru"


def strip_trailing_source_line(text: str) -> str:
    cleaned = (text or "").strip()
    cleaned = re.sub(r"\n+(?:Источник|Source|წყარო):.*$", "", cleaned, flags=re.IGNORECASE | re.DOTALL)
    return cleaned.strip()


def strip_generated_source_mentions(text: str) -> str:
    cleaned = (text or "").strip()
    cleaned = re.sub(r"\s*\((?:Источник|Source|წყარო):[^)]+\)", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+(?:Источник|Source|წყარო):\s*.*$", "", cleaned, flags=re.IGNORECASE | re.DOTALL)
    cleaned = re.sub(r"[ \t]+\n", "\n", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


_REFUSAL_SENTENCE_PATTERNS = [
    r"В предоставленных официальных источниках ответ(?:\s+на этот вопрос)? не найден\.?",
    r"In the provided official sources[^.]*not found\.?",
    r"მოწოდებულ ოფიციალურ წყაროებში[^.]*?(?:ვერ მოიძებნა|არ მოიძებნა)\.?",
]


def is_pure_refusal(text: str) -> bool:
    """True when the answer is only the strict-prompt refusal sentence.

    Such an answer must not carry a citation: "not found" plus
    "Источник: …, статья N" contradict each other.
    """
    cleaned = (text or "").strip()
    if not cleaned:
        return False
    matched_refusal = False
    for pattern in _REFUSAL_SENTENCE_PATTERNS:
        cleaned, replacements = re.subn(pattern, "", cleaned, flags=re.IGNORECASE)
        matched_refusal = matched_refusal or replacements > 0
        cleaned = cleaned.strip()
    return matched_refusal and len(cleaned) < 8


def strip_contradictory_refusal(text: str) -> str:
    """Drop the strict-prompt refusal sentence when the answer also has real content.

    The generator sometimes appends "…ответ не найден." after actually stating the
    rule, producing a self-contradictory answer. A pure refusal (only this sentence)
    is left intact so honest "no answer" responses still work.
    """
    cleaned = (text or "").strip()
    for pattern in _REFUSAL_SENTENCE_PATTERNS:
        without = re.sub(pattern, "", cleaned, flags=re.IGNORECASE).strip()
        without = re.sub(r"\n{3,}", "\n\n", without).strip()
        if without and without != cleaned and len(without) >= 8:
            cleaned = without
    return cleaned


def normalize_citation_title(title: str) -> str:
    cleaned = (title or "").strip()
    cleaned = re.sub(r"[\s,.;:]+$", "", cleaned)
    cleaned = re.sub(r"\s*[.:-]?\s*მუხლი\s+\d+(?:\s+პუნქტი\s+\d+)?\s*$", "", cleaned)
    cleaned = re.sub(r"[\s,.;:]+$", "", cleaned)
    return cleaned or title


def normalize_public_response_text(text: str) -> str:
    cleaned = (text or "").strip()
    cleaned = re.sub(r"\*\*(.*?)\*\*", r"\1", cleaned)
    cleaned = re.sub(r"__([^_]+)__", r"\1", cleaned)
    cleaned = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", r"\1", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def sanitize_language_drift(text: str, trace: Any) -> str:
    cleaned = (text or "").strip()
    lang = _response_language(trace)
    if lang == "ka":
        cleaned = re.sub(r"\bсоставляет\b", "შეადგენს", cleaned, flags=re.IGNORECASE)
    return cleaned.strip()


def compress_canonical_section_text(
    section_text: Optional[str],
    *,
    article_ref: Optional[str] = None,
    point_ref: Optional[str] = None,
    article_budget: int = 1100,
    point_budget: int = 800,
) -> Optional[str]:
    if not section_text:
        return section_text

    text = normalize_public_response_text(section_text)
    budget = point_budget if point_ref else article_budget
    if len(text) <= budget:
        return text

    lines = text.splitlines()
    heading = lines[0].strip() if lines else ""
    body = "\n".join(lines[1:]).strip() if len(lines) > 1 else text
    prefix = f"{heading}\n" if heading else ""
    usable_budget = max(300, budget - len(prefix))

    numbered_parts = [part.strip() for part in re.split(r"(?=\n\s*\d+\.\s)", f"\n{body}") if part.strip()]
    if len(numbered_parts) > 1:
        kept: list[str] = []
        total = 0
        for part in numbered_parts:
            candidate_len = len(part) + (2 if kept else 0)
            if kept and total + candidate_len > usable_budget:
                break
            if not kept and len(part) > usable_budget:
                kept.append(_trim_to_boundary(part, usable_budget))
                total = len(kept[0])
                break
            kept.append(part)
            total += candidate_len
        compressed = "\n\n".join(kept).strip()
        return f"{prefix}{compressed}".strip()

    trimmed = _trim_to_boundary(body, usable_budget)
    if article_ref and heading:
        return f"{prefix}{trimmed}".strip()
    return f"{prefix}{trimmed}".strip()


def compress_rollout_context_text(
    section_text: Optional[str],
    *,
    question_class: Optional[str] = None,
) -> Optional[str]:
    if not section_text:
        return section_text

    text = normalize_public_response_text(section_text)
    text = re.sub(r"\*([^*]+)\*", r"\1", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()

    if question_class == "named_document_lookup":
        return _trim_to_boundary(text, 700)
    if question_class == "amendment_tracking":
        return _trim_to_boundary(text, 650)
    return text


def format_precise_citation(trace: Any) -> Optional[str]:
    ranked = trace.reranking.get("top_ranked_documents", [])
    if not ranked:
        return None

    top = ranked[0]
    metadata = top.get("metadata") or {}
    title = normalize_citation_title(top.get("title") or metadata.get("title_normalized") or "Источник")
    point_ref = str(metadata.get("point_ref") or "").strip()
    article_ref = str(metadata.get("article_ref") or "").strip()

    lang = _response_language(trace)
    if lang == "en":
        source_label = "Source"
        article_word = "Article"
        point_word = "point"
    elif lang == "ka":
        source_label = "წყარო"
        article_word = "მუხლი"
        point_word = "პუნქტი"
    else:
        source_label = "Источник"
        article_word = "статья"
        point_word = "пункт"

    if point_ref and "." in point_ref:
        article_num, point_num = point_ref.split(".", 1)
        return f"{source_label}: {title}, {article_word} {article_num}, {point_word} {point_num}."
    if article_ref:
        return f"{source_label}: {title}, {article_word} {article_ref}."
    return None


def finalize_rollout_response(response: str, trace: Any) -> str:
    base = normalize_public_response_text(strip_generated_source_mentions(strip_trailing_source_line(response)))
    base = sanitize_language_drift(base, trace)
    base = strip_contradictory_refusal(base)
    question_class = trace.classification.get("question_class")
    if question_class == "amendment_tracking":
        return base
    if is_pure_refusal(base):
        return base
    citation = format_precise_citation(trace)
    if citation:
        if base:
            return f"{base}\n\n{citation}"
        return citation
    return base


def direct_tax_faq_response(trace: Any) -> Optional[str]:
    parsed = getattr(trace, "parsed_query", None) or {}
    classification = getattr(trace, "classification", None) or {}
    topic = parsed.get("topic")
    entry = get_tax_faq_entry(topic)
    if not entry:
        return None
    if classification.get("question_class") != entry.question_class:
        return None
    if parsed.get("goal") != "rate_lookup":
        return None
    if entry.subject and parsed.get("subject") not in {None, entry.subject}:
        return None
    return entry.response_by_lang.get(_response_language(trace)) or entry.response_by_lang.get("ru")


def interest_tax_rate_response(trace: Any) -> Optional[str]:
    parsed = getattr(trace, "parsed_query", None) or {}
    if parsed.get("topic") != "interest_tax":
        return None
    return direct_tax_faq_response(trace)


def royalty_tax_rate_response(trace: Any) -> Optional[str]:
    parsed = getattr(trace, "parsed_query", None) or {}
    if parsed.get("topic") != "royalty_tax":
        return None
    return direct_tax_faq_response(trace)


def import_vat_response(trace: Any) -> Optional[str]:
    parsed = getattr(trace, "parsed_query", None) or {}
    if parsed.get("topic") != "import_vat":
        return None
    # Import VAT is the one topic retrieval can't ground (it pulls customs-value or
    # returning-resident chunks, not "import is a VAT-taxable operation"), and the
    # strict prompt then refuses non-deterministically. The FAQ entry answers both
    # "is it taxed" and "what rate" ("Да … 18%"), so serve it for any goal, not only
    # rate_lookup — this is the single retained import-VAT guard.
    entry = get_tax_faq_entry("import_vat")
    if not entry:
        return None
    return entry.response_by_lang.get(_response_language(trace)) or entry.response_by_lang.get("ru")


def nonresident_withholding_tax_response(trace: Any) -> Optional[str]:
    parsed = getattr(trace, "parsed_query", None) or {}
    if parsed.get("topic") != "nonresident_wht":
        return None
    return direct_tax_faq_response(trace)


def rental_income_tax_rate_response(trace: Any) -> Optional[str]:
    parsed = getattr(trace, "parsed_query", None) or {}
    if parsed.get("topic") != "rental_income":
        return None
    return direct_tax_faq_response(trace)


def dividend_tax_rate_response(trace: Any) -> Optional[str]:
    parsed = getattr(trace, "parsed_query", None) or {}
    if parsed.get("topic") != "dividend_tax":
        return None
    return direct_tax_faq_response(trace)


def out_of_jurisdiction_response(trace: Any) -> Optional[str]:
    """Refuse non-Georgian jurisdictions instead of answering with Georgian rates."""
    parsed = getattr(trace, "parsed_query", None) or {}
    q = str(parsed.get("normalized_query") or "").lower()
    foreign = any(tok in q for tok in (
        "сша", "u.s.a", "usa", "америк", "росси", "украин", "германи", "франци",
        "турци", "армени", "азербайджан", "казахстан", "united states", "russia",
        "ukraine", "germany", "აშშ", "ამერიკ", "რუსეთ", "უკრაინ", "გერმან",
        "საფრანგ", "თურქეთ", "სომხეთ", "აზერბაიჯან", "ყაზახ",
    ))
    georgia = any(tok in q for tok in ("груз", "georgia", "საქართველ"))
    if not foreign or georgia:
        return None
    answers = {
        "ru": "Я консультирую только по налоговому законодательству Грузии и не отвечаю по налогам других стран.",
        "en": "I only advise on Georgian tax law and do not cover the tax rules of other countries.",
        "ka": "ვაკონსულტირებ მხოლოდ საქართველოს საგადასახადო კანონმდებლობაზე და სხვა ქვეყნების გადასახადებს არ ვფარავ.",
    }
    return answers.get(_response_language(trace), answers["ru"])


def out_of_domain_response(trace: Any) -> Optional[str]:
    """Refuse obvious non-legal requests without retrieval or generation."""
    parsed = getattr(trace, "parsed_query", None) or {}
    q = str(parsed.get("normalized_query") or "").lower()
    weather = any(token in q for token in (
        "погод", "прогноз погоды", "weather", "forecast", "ამინდ", "ამინდის პროგნოზ",
    ))
    if not weather:
        return None
    answers = {
        "ru": (
            "Я отвечаю на вопросы по налоговому и связанному с ним законодательству Грузии. "
            "Прогноз погоды находится вне тематики сервиса."
        ),
        "en": (
            "I answer questions about Georgian tax law and related legal matters. "
            "Weather forecasts are outside the scope of this service."
        ),
        "ka": (
            "ვპასუხობ საქართველოს საგადასახადო და მასთან დაკავშირებულ სამართლებრივ საკითხებზე. "
            "ამინდის პროგნოზი ამ სერვისის თემატიკის ფარგლებს გარეთაა."
        ),
    }
    return answers.get(_response_language(trace), answers["ru"])


def out_of_scope_response(trace: Any) -> Optional[str]:
    """Return a localized refusal for a clearly unsupported request."""
    return out_of_jurisdiction_response(trace) or out_of_domain_response(trace)


def tax_appeal_procedure_response(trace: Any) -> Optional[str]:
    """Deterministic public answer for the generic tax-appeal procedure.

    This high-stakes procedural answer is grounded in the canonical Tax Code
    articles 296, 297 and 299.  Keeping the wording deterministic prevents the
    generator from combining the 30-day delivery rule, the court exception and
    the not-sent deadline into a legally different statement.  The guard has
    the same environment kill switch as the other authoritative answers.
    """
    parsed = getattr(trace, "parsed_query", None) or {}
    if parsed.get("goal") != "appeal_procedure":
        return None
    if "appeal_procedure" in _disabled_guard_topics():
        return None

    answers = {
        "ru": (
            "Решение налогового органа можно обжаловать в течение 30 дней со дня его вручения. "
            "В системе Министерства финансов спор обычно начинается с подачи жалобы в Службу доходов и является двухэтапным; "
            "на любой стадии этого административного рассмотрения заявитель вправе обратиться в суд. "
            "Жалоба, как правило, подаётся в электронной форме. Если решение не было направлено заявителю, "
            "срок обжалования исчисляется со дня, когда он узнал о решении."
        ),
        "en": (
            "A tax authority decision may be appealed within 30 days after it is delivered to the person. "
            "Within the Ministry of Finance system, a dispute normally begins by filing a complaint with the Revenue Service and proceeds in two stages; "
            "the complainant may go to court at any stage of that administrative process. "
            "The complaint is generally filed electronically. If the decision was not sent to the complainant, "
            "the appeal period runs from the day the decision became known to them."
        ),
        "ka": (
            "საგადასახადო ორგანოს გადაწყვეტილება შეგიძლიათ გაასაჩივროთ მისი ჩაბარებიდან 30 დღის ვადაში. "
            "საქართველოს ფინანსთა სამინისტროს სისტემაში დავა, როგორც წესი, იწყება საჩივრის შემოსავლების სამსახურში წარდგენით და ორეტაპიანია; "
            "ამ ადმინისტრაციული დავის ნებისმიერ ეტაპზე მომჩივანს შეუძლია მიმართოს სასამართლოს. "
            "საჩივარი, როგორც წესი, ელექტრონული ფორმით წარედგინება. თუ გადაწყვეტილება მომჩივანს არ გაეგზავნა, "
            "გასაჩივრების ვადა აითვლება იმ დღიდან, როდესაც გადაწყვეტილება მისთვის ცნობილი გახდა."
        ),
    }
    return answers.get(_response_language(trace), answers["ru"])


def authoritative_tax_fact_response(trace: Any) -> Optional[Tuple[str, str]]:
    """Authoritative answers for high-value facts that retrieval misses.

    Topics listed in INFOHUB_DISABLED_GUARDS fall through to real retrieval —
    the guard-removal path of the hardening plan (П3), one topic at a time.
    """
    result = _authoritative_tax_fact_impl(trace)
    if result and result[0] in _disabled_guard_topics():
        return None
    return result


def _authoritative_tax_fact_impl(trace: Any) -> Optional[Tuple[str, str]]:
    """Curated high-value facts, matched on query text because the parser does
    not reliably tag these question shapes.

    Returns ``(topic, answer)`` so the caller can cite the actual legal basis
    (most topics rest on the Tax Code; the funded pension rests on its own law).
    """
    parsed = getattr(trace, "parsed_query", None) or {}
    q = str(parsed.get("normalized_query") or "").lower()
    lang = _response_language(trace)

    def pick(d: Dict[str, str]) -> str:
        return d.get(lang) or d["ru"]

    has_vat = any(t in q for t in ("ндс", "vat", "დღგ"))

    # Tour operator VAT exemption (Tax Code art. 172)
    if ("туропер" in q or "tour oper" in q or "ტუროპერ" in q
            or ((("турист" in q) or ("tourist" in q) or ("ტურист" in q)) and has_vat)):
        return "tour_operator_vat", pick({
            "ru": "Организованный въезд иностранных туристов в Грузию (услуги туроператора) освобождён от НДС с правом зачёта входного НДС (Налоговый кодекс Грузии, статья 172). Туроператор по таким услугам НДС не начисляет, но сохраняет право на зачёт входного НДС.",
            "en": "The organized inbound travel of foreign tourists to Georgia (tour operator services) is VAT-exempt with the right to credit input VAT (Georgian Tax Code, Article 172). The operator does not charge VAT on such services but keeps the input VAT credit.",
            "ka": "უცხოელი ტურისტების ორგანიზებული შემოყვანა საქართველოში (ტუროპერატორის მომსახურება) გათავისუფლებულია დღგ-სგან ჩათვლის უფლებით (საგადასახადო კოდექსი, მუხლი 172).",
        })

    # VAT registration threshold
    if has_vat and any(t in q for t in ("оборот", "регистр", "порог", "threshold", "turnover", "registr", "რეგისტრ", "ბრუნვ")):
        return "vat_threshold", pick({
            "ru": "Регистрация плательщиком НДС обязательна, когда облагаемый оборот превышает 100 000 лари за любые непрерывные 12 календарных месяцев.",
            "en": "VAT registration is mandatory once taxable turnover exceeds 100,000 GEL over any continuous 12 calendar months.",
            "ka": "დღგ-ის გადამხდელად რეგისტრაცია სავალდებულოა, როცა დასაბეგრი ბრუნვა აღემატება 100 000 ლარს ნებისმიერ უწყვეტ 12 კალენდარულ თვეში.",
        })

    # Micro business — guard removed (Phase 4): retrieval grounds this correctly in
    # ru+en (eval), so the answer now comes from the retrieved law, not curated text.

    # Mandatory funded pension contributions (Law of Georgia "On Funded Pension",
    # not the Tax Code — cited accordingly)
    if any(t in q for t in ("пенси", "pension", "საპენსიო", "პენსი")):
        return "funded_pension", pick({
            "ru": "Накопительная пенсия в Грузии формируется из взносов: 2% удерживает работодатель из зарплаты работника, 2% добавляет работодатель и 2% — государство (для дохода до установленного потолка). Основание — закон Грузии «О накопительной пенсии».",
            "en": "Georgia's funded pension is built from contributions: 2% withheld from the employee's salary, 2% added by the employer, and 2% by the state (for income up to the cap). Legal basis — the Law of Georgia \"On Funded Pension\".",
            "ka": "საქართველოს დაგროვებითი საპენსიო სისტემა იქმნება შენატანებით: 2% იკავება დასაქმებულის ხელფასიდან, 2% ამატებს დამსაქმებელი და 2% — სახელმწიფო (ჭერამდე შემოსავალზე). საფუძველი — საქართველოს კანონი „დაგროვებითი პენსიის შესახებ“.",
        })

    # Estonian model of profit taxation
    if any(t in q for t in ("эстонск", "estonian", "ესტონ")):
        return "estonian_model", pick({
            "ru": "По эстонской модели в Грузии налог на прибыль (15%) уплачивается не на заработанную прибыль, а только при её распределении (например, дивиденды). Нераспределённая и реинвестированная прибыль налогом на прибыль не облагается.",
            "en": "Under Georgia's Estonian model, profit tax (15%) is paid not on earned profit but only when profit is distributed (e.g. dividends). Retained and reinvested profit is not subject to profit tax.",
            "ka": "ესტონური მოდელით საქართველოში მოგების გადასახადი (15%) იხდება არა მიღებულ მოგებაზე, არამედ მხოლოდ მისი განაწილებისას (მაგ. დივიდენდი). გაუნაწილებელი და რეინვესტირებული მოგება მოგების გადასახადით არ იბეგრება.",
        })

    # Property tax
    if any(t in q for t in ("налог на имущество", "имуществ", "property tax", "ქონების გადასახად")):
        return "property_tax", pick({
            "ru": "Ставка налога на имущество зависит от плательщика. Для предприятия (организации) — не более 1% стоимости налогооблагаемого имущества (для лизинговой компании по переданному в лизинг имуществу — не более 0.6%). Для физлица фиксированной ставки 1% нет: налог зависит от дохода семьи за предыдущий год и составляет от 0% до 0.8%.",
            "en": "The property tax rate depends on the taxpayer. For a company, it is no more than 1% of the value of taxable property (for a leasing company's leased property, no more than 0.6%). For an individual there is no fixed 1% rate: the tax depends on the family's previous-year income and ranges from 0% to 0.8%.",
            "ka": "ქონების გადასახადის განაკვეთი დამოკიდებულია გადამხდელზე. საწარმოსთვის — დასაბეგრი ქონების ღირებულების არაუმეტეს 1% (სალიზინგო კომპანიის ლიზინგით გაცემულ ქონებაზე — არაუმეტეს 0.6%). ფიზიკური პირისთვის ფიქსირებული 1% არ არსებობს: გადასახადი დამოკიდებულია ოჯახის წინა წლის შემოსავალზე და შეადგენს 0%-დან 0.8%-მდე.",
        })

    return None


def small_business_legal_form_response(trace: Any) -> Optional[str]:
    """Authoritative guard: an LLC (ООО/შპს) cannot use the 1% small-business regime.

    Only an individual entrepreneur qualifies; an LLC is taxed under the Estonian
    profit-tax model (15% on distribution). The query parser does not reliably tag
    the legal form for this question, so match on the normalized query text.
    """
    parsed = getattr(trace, "parsed_query", None) or {}
    q = str(parsed.get("normalized_query") or "").lower()
    legal_form = any(tok in q for tok in (
        "ооо", "о.о.о", "llc", "ltd", "шпс", "შპს", "компани", "company",
        "юридическ", "legal entity", "საწარმო",
    ))
    small_biz = any(tok in q for tok in (
        "1%", "1 %", "малого бизнеса", "малый бизнес", "small business", "მცირე ბიზნეს",
    ))
    if not (legal_form and small_biz):
        return None
    answers = {
        "ru": (
            "Нет. Режим малого бизнеса со ставкой 1% доступен только индивидуальному "
            "предпринимателю (физлицу-предпринимателю). ООО (общество с ограниченной "
            "ответственностью) применять его не может. Прибыль ООО облагается по эстонской "
            "модели — 15% при распределении прибыли."
        ),
        "en": (
            "No. The 1% small business regime is available only to an individual entrepreneur. "
            "An LLC cannot use it. An LLC's profit is taxed under the Estonian model at 15% "
            "upon distribution of profit."
        ),
        "ka": (
            "არა. მცირე ბიზნესის 1%-იანი რეჟიმი ხელმისაწვდომია მხოლოდ ინდივიდუალური "
            "მეწარმისთვის (ფიზიკური პირისთვის). შპს ამ რეჟიმს ვერ გამოიყენებს. შპს-ის მოგება "
            "იბეგრება ე.წ. ესტონური მოდელით — 15% მოგების განაწილებისას."
        ),
    }
    return answers.get(_response_language(trace), answers["ru"])


def small_business_tax_rate_response(trace: Any) -> Optional[str]:
    parsed = getattr(trace, "parsed_query", None) or {}
    if parsed.get("topic") != "small_business":
        return None
    return direct_tax_faq_response(trace)


def vat_rate_response(trace: Any) -> Optional[str]:
    parsed = getattr(trace, "parsed_query", None) or {}
    if parsed.get("topic") != "vat":
        return None
    return direct_tax_faq_response(trace)


def profit_tax_rate_response(trace: Any) -> Optional[str]:
    parsed = getattr(trace, "parsed_query", None) or {}
    if parsed.get("topic") != "profit_tax":
        return None
    return direct_tax_faq_response(trace)


def income_tax_rate_response(trace: Any) -> Optional[str]:
    parsed = getattr(trace, "parsed_query", None) or {}
    if parsed.get("topic") != "tax":
        return None
    return direct_tax_faq_response(trace)


def individual_property_tax_rate_response(trace: Any) -> Optional[str]:
    parsed = getattr(trace, "parsed_query", None) or {}
    classification = getattr(trace, "classification", None) or {}
    if classification.get("question_class") != "practical_tax_guidance":
        return None
    if parsed.get("topic") != "property_tax":
        return None
    if parsed.get("subject") != "individual":
        return None
    if parsed.get("goal") != "rate_lookup":
        return None

    locality = str(parsed.get("locality") or "").strip()
    lang = _response_language(trace)

    ru_labels = {
        "dmanisi": "Дманиси",
        "tbilisi": "Тбилиси",
        "gurjaani": "Гурджаани",
        "municipality": "указанном муниципалитете",
    }
    en_labels = {
        "dmanisi": "Dmanisi",
        "tbilisi": "Tbilisi",
        "gurjaani": "Gurjaani",
        "municipality": "the relevant municipality",
    }
    ka_labels = {
        "dmanisi": "დმანისში",
        "tbilisi": "თბილისში",
        "gurjaani": "გურჯაანში",
        "municipality": "შესაბამის მუნიციპალიტეტში",
    }

    if lang == "en":
        locality_text = f" in {en_labels.get(locality, locality)}" if locality else ""
        return (
            f"For an individual, property tax{locality_text} should not be described as a fixed 1% rate, because that rate applies to companies. "
            "For individuals, the tax depends on the previous calendar year's family income, and the rate can range from 0% to 0.8%. "
            "If you need the exact amount, it should be calculated separately based on income and the type of property."
        )
    if lang == "ka":
        locality_text = f" {ka_labels.get(locality, locality)}" if locality else ""
        return (
            f"ფიზიკური პირისთვის ქონების გადასახადი{locality_text} ფიქსირებული 1%-იანი განაკვეთით არ განისაზღვრება, რადგან ასეთი განაკვეთი ორგანიზაციებს ეხება. "
            "ფიზიკური პირებისთვის გადასახადი დამოკიდებულია წინა კალენდარული წლის ოჯახის შემოსავალზე და განაკვეთი შეიძლება იყოს 0%-დან 0.8%-მდე. "
            "ზუსტი თანხის დასადგენად საჭიროა ცალკე გამოთვლა შემოსავლისა და ქონების ტიპის მიხედვით."
        )

    locality_text = f" в {ru_labels.get(locality, locality)}" if locality else ""
    return (
        f"Для физлица налог на имущество{locality_text} не следует описывать фиксированной ставкой 1%, "
        "потому что такая ставка относится к организациям. Для физических лиц налог зависит от дохода за "
        "предыдущий календарный год, а ставка может варьироваться от 0% до 0.8%. Если нужен точный расчёт, "
        "его нужно считать отдельно по доходу семьи и виду имущества."
    )


def _trim_to_boundary(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text.strip()

    clipped = text[:limit].rstrip()
    boundary = max(clipped.rfind("\n"), clipped.rfind(". "), clipped.rfind("; "))
    if boundary >= max(80, limit // 3):
        clipped = clipped[: boundary + 1].rstrip()
    return clipped.strip()
