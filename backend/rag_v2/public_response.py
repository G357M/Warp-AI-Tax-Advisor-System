from __future__ import annotations

import re
from typing import Any, Dict, Optional

from .faq_tax_matrix import get_tax_faq_entry


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
    question_class = trace.classification.get("question_class")
    if question_class == "amendment_tracking":
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
    return direct_tax_faq_response(trace)


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
