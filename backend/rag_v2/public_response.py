from __future__ import annotations

import os
import re
from typing import Any, Dict, Optional, Tuple

from .faq_tax_matrix import (
    get_tax_faq_entry_by_slug,
    match_tax_faq_entry,
)


def _disabled_guard_topics() -> set:
    """Per-topic kill switch for the authoritative guards (П3 of the hardening
    plan): INFOHUB_DISABLED_GUARDS=vat_threshold,estonian_model routes those
    topics through real retrieval instead of the curated answer. Env-driven so
    a guard flips with a container recreate, no rebuild needed."""
    raw = os.getenv("INFOHUB_DISABLED_GUARDS", "")
    return {t.strip() for t in raw.split(",") if t.strip()}


def _disabled_legal_answer_contracts() -> set[str]:
    """Independent kill switch for expert-verified answer contracts.

    ``INFOHUB_DISABLED_GUARDS`` controls the older broad text guards.  Keeping
    a separate namespace prevents a retired legacy guard from silently
    disabling the exact parser-backed contract that replaced it.
    """
    raw = os.getenv("INFOHUB_DISABLED_LEGAL_ANSWER_CONTRACTS", "")
    return {topic.strip() for topic in raw.split(",") if topic.strip()}


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
    entry = match_tax_faq_entry(parsed, classification.get("question_class"))
    if not entry:
        return None
    disabled = _disabled_legal_answer_contracts()
    if entry.topic in disabled or entry.slug in disabled:
        return None
    return entry.response(_response_language(trace))


def _contract_response_by_slug(slug: str, trace: Any) -> Optional[str]:
    entry = get_tax_faq_entry_by_slug(slug)
    if not entry:
        return None
    disabled = _disabled_legal_answer_contracts()
    if entry.topic in disabled or entry.slug in disabled:
        return None
    return entry.response(_response_language(trace))


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
    return _contract_response_by_slug("vat-import", trace)


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
    return _contract_response_by_slug("tax-appeal-procedure", trace)


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
    """Compatibility routes for formerly curated high-value tax facts.

    Tax Code facts delegate to parser-backed contracts. Funded pension is the
    only temporary hard-coded exception and rests on its own external law.
    """
    parsed = getattr(trace, "parsed_query", None) or {}
    q = str(parsed.get("normalized_query") or "").lower()
    lang = _response_language(trace)

    def pick(d: Dict[str, str]) -> str:
        return d.get(lang) or d["ru"]

    has_vat = any(t in q for t in ("ндс", "vat", "დღგ"))

    # Individual tax residency (Tax Code art. 34). The rule is framed as a
    # whole-tax-year status and deliberately keeps the statutory exceptions
    # visible instead of presenting the day count as the only legal test.
    if parsed.get("goal") == "residency_status":
        response = _contract_response_by_slug("tax-residency-individual", trace)
        return ("tax_residency", response) if response else None

    # Late-payment surcharge (Tax Code art. 272, especially points 3-4).
    if parsed.get("goal") == "penalty_rate":
        response = _contract_response_by_slug("late-payment-interest", trace)
        return ("late_payment_interest", response) if response else None

    # Tour operator VAT exemption (Tax Code arts. 172 and 157).
    if ("туропер" in q or "tour oper" in q or "ტუროპერ" in q
            or ((("турист" in q) or ("tourist" in q) or ("ტურისტ" in q)) and has_vat)):
        response = _contract_response_by_slug(
            "tour-operator-inbound-vat-exemption", trace
        )
        return ("tour_operator_vat", response) if response else None

    # VAT registration threshold
    if has_vat and any(t in q for t in ("оборот", "регистр", "порог", "threshold", "turnover", "registr", "რეგისტრ", "ბრუნვ")):
        response = _contract_response_by_slug("vat-registration-threshold", trace)
        return ("vat_registration_threshold", response) if response else None

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
        response = _contract_response_by_slug("profit-distribution-model", trace)
        return ("profit_tax", response) if response else None

    # Property tax
    if any(t in q for t in ("налог на имущество", "имуществ", "property tax", "ქონების გადასახად")):
        response = _contract_response_by_slug("property-tax-overview", trace)
        return ("property_tax", response) if response else None

    return None


def small_business_legal_form_response(trace: Any) -> Optional[str]:
    """Authoritative guard: an LLC (ООО/შპს) cannot use the 1% small-business regime.

    Tax Code article 88 limits the status to an entrepreneur natural person;
    article 90 supplies the regime's 1% rate. Match on normalized query text as
    a defense in depth even though the parser also tags the eligibility intent.
    """
    parsed = getattr(trace, "parsed_query", None) or {}
    q = str(parsed.get("normalized_query") or "").lower()
    goal = str(parsed.get("goal") or "")
    legal_form = any(tok in q for tok in (
        "ооо", "о.о.о", "llc", "ltd", "шпс", "შპს", "компани", "company",
        "юридическ", "legal entity", "საწარმო",
    ))
    explicit_small_biz = any(tok in q for tok in (
        "малого бизнеса", "малый бизнес", "small business", "მცირე ბიზნეს",
    ))
    if not (
        legal_form
        and (goal == "small_business_eligibility" or explicit_small_biz)
    ):
        return None
    return _contract_response_by_slug("small-business-llc-ineligible", trace)


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
    contract_response = _contract_response_by_slug("property-tax-individual", trace)
    if contract_response is None:
        return None
    if not locality:
        return contract_response

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
        context = (
            f"For property in {en_labels.get(locality, locality)}, the national "
            "Tax Code bands below apply; the exact amount also depends on the "
            "municipal rate, property type and taxable value."
        )
    elif lang == "ka":
        context = (
            f"{ka_labels.get(locality, locality)} მდებარე ქონებაზე ქვემოთ მოცემული "
            "საგადასახადო კოდექსის საერთო ზღვრები მოქმედებს; ზუსტი თანხა ასევე "
            "მუნიციპალურ განაკვეთზე, ქონების სახესა და დასაბეგრ ღირებულებაზეა დამოკიდებული."
        )
    else:
        context = (
            f"Для имущества в {ru_labels.get(locality, locality)} применяются "
            "приведённые ниже общие диапазоны Налогового кодекса; точная сумма "
            "также зависит от муниципальной ставки, вида и облагаемой стоимости имущества."
        )
    return f"{context}\n\n{contract_response}"


def _trim_to_boundary(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text.strip()

    clipped = text[:limit].rstrip()
    boundary = max(clipped.rfind("\n"), clipped.rfind(". "), clipped.rfind("; "))
    if boundary >= max(80, limit // 3):
        clipped = clipped[: boundary + 1].rstrip()
    return clipped.strip()
