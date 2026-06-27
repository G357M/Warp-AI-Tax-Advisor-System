from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Optional

from core.config import settings
from core.database import SessionLocal
from models import Document, DocumentChunk
from rag.pipeline import rag_pipeline

from .pipeline_v2 import pipeline_v2
from .public_response import (
    compress_canonical_section_text,
    compress_rollout_context_text,
    direct_tax_faq_response,
    dividend_tax_rate_response,
    finalize_rollout_response,
    import_vat_response,
    income_tax_rate_response,
    individual_property_tax_rate_response,
    interest_tax_rate_response,
    nonresident_withholding_tax_response,
    profit_tax_rate_response,
    rental_income_tax_rate_response,
    royalty_tax_rate_response,
    small_business_tax_rate_response,
    vat_rate_response,
)


LOCALITY_TITLE_STEMS = {
    "dmanisi": ["დმანის"],
    "tbilisi": ["თბილის"],
    "gurjaani": ["გურჯაან"],
}

AMENDMENT_TITLE_MARKERS = [
    "ცვლილების შეტანის",
    "ცვლილებების შეტანის",
]


def _response_language(language: Optional[str]) -> str:
    lang = str(language or "ru").strip().lower()
    return lang if lang in {"ru", "en", "ka"} else "ru"


def _answer_language_name(language: Optional[str]) -> str:
    return {
        "ru": "Russian",
        "en": "English",
        "ka": "Georgian",
    }[_response_language(language)]


def _language_output_guard(language: Optional[str]) -> str:
    lang = _response_language(language)
    if lang == "en":
        return "Use English only. Do not switch to Russian or Georgian except inside official source titles or citation identifiers when absolutely necessary."
    if lang == "ka":
        return "Use Georgian only. Do not switch to Russian or English except inside official source titles, legal identifiers, article numbers, or unavoidable tax abbreviations."
    return "Use Russian only. Do not switch to English or Georgian except inside official source titles or citation identifiers when absolutely necessary."


def _mode() -> str:
    return (os.getenv("INFOHUB_RAG_V2_MODE") or "off").strip().lower()


def _rollout_classes() -> set[str]:
    raw = os.getenv(
        "INFOHUB_RAG_V2_ROLLOUT_CLASSES",
        "named_document_lookup,canonical_law_lookup",
    )
    configured = {item.strip() for item in raw.split(",") if item.strip()}
    configured.update({"practical_tax_guidance", "dispute_practice"})
    return configured


def _top_k() -> int:
    try:
        return max(1, min(5, int(os.getenv("INFOHUB_RAG_V2_ROLLOUT_TOP_K", "3"))))
    except Exception:
        return 3


def _has_explicit_point(section_text: str, point_ref: Optional[str]) -> bool:
    point_ref = str(point_ref or "").strip()
    if not point_ref or "." not in point_ref:
        return False
    _, point_num = point_ref.split(".", 1)
    return bool(re.search(rf"(?:^|\n)\s*{re.escape(point_num)}\.\s", section_text))


def _extract_point_subsection(section_text: str, point_ref: Optional[str]) -> Optional[str]:
    point_ref = str(point_ref or "").strip()
    if not point_ref or "." not in point_ref:
        return None
    _, point_num = point_ref.split(".", 1)
    start_match = re.search(rf"(?:^|\n)\s*{re.escape(point_num)}\.\s", section_text)
    if not start_match:
        return None

    subsection_tail = section_text[start_match.start():]
    next_point_match = re.search(r"\n\s*\d+\.\s", subsection_tail[2:])
    next_article_match = re.search(r"\n(?:####\s*)?(?:მუხლი|Article|Статья)\s+\d+", subsection_tail[2:])

    candidates = []
    if next_point_match:
        candidates.append(2 + next_point_match.start())
    if next_article_match:
        candidates.append(2 + next_article_match.start())
    end = min(candidates) if candidates else len(subsection_tail)
    return subsection_tail[:end].strip()


def _extract_section_text(full_text: Optional[str], metadata: Dict[str, Any], fallback_size: int = 2200) -> Optional[str]:
    text = full_text or ""
    if not text:
        return None

    section_label = str(metadata.get("section_label") or "").strip()
    article_ref = str(metadata.get("article_ref") or "").strip()
    point_ref = str(metadata.get("point_ref") or "").strip()

    needles = [section_label]
    if point_ref and "." in point_ref:
        art, point = point_ref.split(".", 1)
        needles.extend([
            f"მუხლი {art} პუნქტი {point}",
            f"Article {art}",
            f"Статья {art}",
        ])
    if article_ref:
        needles.extend([
            f"მუხლი {article_ref}",
            f"Article {article_ref}",
            f"Статья {article_ref}",
        ])

    start = -1
    for needle in needles:
        if needle:
            start = text.find(needle)
            if start != -1:
                break
    if start == -1 and article_ref:
        match = re.search(rf"(?:მუხლი|Article|Статья)\s+{re.escape(article_ref)}\b", text)
        if match:
            start = match.start()
    if start == -1:
        return None

    tail = text[start:]
    next_match = re.search(r"\n(?:####\s*)?(?:მუხლი|Article|Статья)\s+\d+", tail[20:])
    if next_match:
        end = start + 20 + next_match.start()
    else:
        end = min(len(text), start + fallback_size)
    section = text[start:end].strip()
    section = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", r"\1", section).strip()

    point_subsection = _extract_point_subsection(section, point_ref)
    if point_subsection:
        article_label = f"Статья {article_ref}" if article_ref else "Статья"
        return f"{article_label}\n{point_subsection}".strip()

    return section.strip()


def _topic_chunk_terms(topic: Optional[str]) -> List[str]:
    topic = (topic or "").strip().lower()
    if topic == "vat":
        return ["დღგ", "დამატებული ღირებულების"]
    if topic == "property_tax":
        return ["ქონების გადასახ", "ადგილობრივი"]
    if topic == "profit_tax":
        return ["მოგების გადასახ"]
    if topic == "excise":
        return ["აქციზ"]
    if topic == "customs":
        return ["საბაჟო"]
    return []


def _fetch_doc_chunks(
    source_url: Optional[str],
    title: Optional[str],
    limit: int,
    *,
    chunk_hint: Optional[int] = None,
    section_label: Optional[str] = None,
    article_ref: Optional[str] = None,
    point_ref: Optional[str] = None,
    question_class: Optional[str] = None,
    topic: Optional[str] = None,
) -> List[Dict[str, Any]]:
    db = SessionLocal()
    try:
        doc = None
        if source_url:
            doc = db.query(Document).filter(Document.source_url == source_url).first()
        if not doc and title:
            doc = db.query(Document).filter(Document.title == title).first()
        if not doc and title:
            doc = db.query(Document).filter(Document.title.ilike(title)).first()
        if not doc:
            return []

        if section_label or article_ref or point_ref:
            section_text = _extract_section_text(doc.full_text, {
                "section_label": section_label,
                "article_ref": article_ref,
                "point_ref": point_ref,
            })
            if section_text:
                if point_ref and not _has_explicit_point(section_text, point_ref):
                    article_num, point_num = point_ref.split(".", 1)
                    section_text = (
                        f"Примечание: в статье {article_num} не выделен отдельный пункт {point_num}; ниже приведён полный текст статьи.\n\n"
                        f"{section_text}"
                    )
                if question_class == "canonical_law_lookup":
                    section_text = compress_canonical_section_text(
                        section_text,
                        article_ref=article_ref,
                        point_ref=point_ref,
                    )
                return [{
                    "id": f"synthetic:{doc.id}:{chunk_hint or article_ref or section_label or 'section'}",
                    "content": section_text,
                    "metadata": {
                        "document_id": str(doc.id),
                        "title": doc.title or title or "",
                        "document_title": doc.title or title or "",
                        "document_type": doc.document_type or "",
                        "source_url": doc.source_url or source_url or "",
                        "url": doc.source_url or source_url or "",
                        "category": getattr(doc, "category", None),
                        "language": getattr(doc, "language", None),
                    },
                    "similarity": 1.0,
                }]

        query = db.query(DocumentChunk).filter(DocumentChunk.document_id == doc.id)
        topic_terms = _topic_chunk_terms(topic)
        if question_class == "amendment_tracking" and topic_terms:
            amendment_chunks = None
            for term in topic_terms:
                candidate_chunks = (
                    query.filter(DocumentChunk.content.ilike(f"%{term}%"))
                    .order_by(DocumentChunk.chunk_index.asc())
                    .limit(limit)
                    .all()
                )
                if candidate_chunks:
                    amendment_chunks = candidate_chunks
                    break
            if amendment_chunks:
                chunks = amendment_chunks
            else:
                return []
        elif chunk_hint is not None:
            start = max(0, int(chunk_hint) - 1)
            end = int(chunk_hint) + max(1, limit)
            hinted = (
                query.filter(DocumentChunk.chunk_index >= start, DocumentChunk.chunk_index <= end)
                .order_by(DocumentChunk.chunk_index.asc())
                .limit(limit)
                .all()
            )
            chunks = hinted or query.order_by(DocumentChunk.chunk_index.asc()).limit(limit).all()
        else:
            chunks = query.order_by(DocumentChunk.chunk_index.asc()).limit(limit).all()

        rows: List[Dict[str, Any]] = []
        for chunk in chunks:
            rows.append(
                {
                    "id": str(chunk.id),
                    "content": chunk.content or "",
                    "metadata": {
                        "document_id": str(doc.id),
                        "title": doc.title or title or "",
                        "document_title": doc.title or title or "",
                        "document_type": doc.document_type or "",
                        "source_url": doc.source_url or source_url or "",
                        "url": doc.source_url or source_url or "",
                        "category": getattr(doc, "category", None),
                        "language": getattr(doc, "language", None),
                    },
                    "similarity": 1.0,
                }
            )
        return rows
    finally:
        db.close()


def _extract_query_year(raw_query: Optional[str]) -> Optional[str]:
    match = re.search(r"\b(20\d{2})\b", raw_query or "")
    return match.group(1) if match else None


def _doc_matches_rollout_class(doc: Dict[str, Any], trace) -> bool:
    question_class = trace.classification.get("question_class")
    parsed = trace.parsed_query or {}
    title = str(doc.get("title") or "")
    metadata = doc.get("metadata") or {}

    if question_class == "local_regulation_lookup":
        locality = str(parsed.get("locality") or "")
        localities = [str(x) for x in (metadata.get("localities") or [])]
        locality_stems = LOCALITY_TITLE_STEMS.get(locality, [])
        title_has_locality = any(stem in title for stem in locality_stems)
        return doc.get("document_type") == "regulation" and (
            not locality or locality in localities or title_has_locality
        )

    if question_class == "amendment_tracking":
        topic = str(parsed.get("topic") or "")
        if topic and topic not in {"tax", "vat", "property_tax", "profit_tax", "excise", "customs"}:
            return False
        if "საგადასახადო კოდექსში ცვლილების შეტანის შესახებ" not in title:
            return False
        year = _extract_query_year(parsed.get("raw_query"))
        if year and year not in title:
            return False
        return True

    if question_class == "dispute_practice":
        return doc.get("document_type") == "court_decision"

    return True


def _filtered_rollout_docs(trace) -> List[Dict[str, Any]]:
    ranked = trace.reranking.get("top_ranked_documents", [])
    question_class = trace.classification.get("question_class")
    if question_class in {"local_regulation_lookup", "amendment_tracking"}:
        ranked = [doc for doc in ranked if _doc_matches_rollout_class(doc, trace)]
    if question_class == "local_regulation_lookup":
        primary = next(
            (
                doc for doc in ranked
                if not any(marker in str(doc.get("title") or "") for marker in AMENDMENT_TITLE_MARKERS)
            ),
            ranked[0] if ranked else None,
        )
        return [primary] if primary else []
    if question_class == "canonical_law_lookup":
        return ranked[:1]
    if question_class == "named_document_lookup":
        return ranked[:1]
    if question_class == "amendment_tracking":
        return ranked[:2]
    return ranked[: _top_k()]


def _build_rollout_chunks(trace) -> List[Dict[str, Any]]:
    ranked = _filtered_rollout_docs(trace)
    chunks: List[Dict[str, Any]] = []
    for index, doc in enumerate(ranked):
        source_url = doc.get("source_url")
        title = doc.get("title")
        metadata = doc.get("metadata") or {}
        chunk_hint = metadata.get("chunk_hint")
        section_label = metadata.get("section_label")
        article_ref = metadata.get("article_ref")
        point_ref = metadata.get("point_ref")
        if trace.classification.get("question_class") == "amendment_tracking":
            limit = 1
        elif trace.classification.get("question_class") == "named_document_lookup":
            limit = 1
        else:
            limit = 2 if doc.get("channel") in {"article_resolver", "point_resolver"} else 2
        fetched = _fetch_doc_chunks(
            source_url,
            title,
            limit=limit,
            chunk_hint=chunk_hint,
            section_label=section_label,
            article_ref=article_ref,
            point_ref=point_ref,
            question_class=trace.classification.get("question_class"),
            topic=trace.parsed_query.get("topic"),
        )
        if index == 0 and not fetched:
            return []
        for item in fetched:
            item["content"] = compress_rollout_context_text(
                item.get("content"),
                question_class=trace.classification.get("question_class"),
            )
            item["_rerank_score"] = doc.get("final_score", 0.0)
            item["metadata"] = {
                **item.get("metadata", {}),
                "retrieval_channel": doc.get("channel"),
                "chunk_hint": chunk_hint,
                "section_label": section_label,
                "article_ref": article_ref,
                "point_ref": point_ref,
            }
        chunks.extend(fetched)
    return chunks


def _topic_label_ru(topic: str) -> str:
    return {
        "vat": "НДС / налогу на добавленную стоимость",
        "property_tax": "налогу на имущество",
        "profit_tax": "налогу на прибыль",
        "excise": "акцизу",
        "customs": "таможенным правилам / таможенным вопросам",
        "tax": "изменениям в Налоговом кодексе",
    }.get(topic, topic)


def _topic_label(language: Optional[str], topic: str) -> str:
    lang = _response_language(language)
    labels = {
        "ru": {
            "vat": "НДС / налогу на добавленную стоимость",
            "property_tax": "налогу на имущество",
            "profit_tax": "налогу на прибыль",
            "excise": "акцизу",
            "customs": "таможенным правилам / таможенным вопросам",
            "tax": "изменениям в Налоговом кодексе",
        },
        "en": {
            "vat": "VAT / value added tax",
            "property_tax": "property tax",
            "profit_tax": "profit tax",
            "excise": "excise tax",
            "customs": "customs rules / customs matters",
            "tax": "changes to the Tax Code",
        },
        "ka": {
            "vat": "დღგ-ს",
            "property_tax": "ქონების გადასახადს",
            "profit_tax": "მოგების გადასახადს",
            "excise": "აქციზს",
            "customs": "საბაჟო საკითხებს",
            "tax": "საგადასახადო კოდექსის ცვლილებებს",
        },
    }
    return labels[lang].get(topic, topic)


def _no_evidence_amendment_response(trace) -> Optional[Dict[str, Any]]:
    parsed = trace.parsed_query or {}
    if trace.classification.get("question_class") != "amendment_tracking":
        return None

    topic = str(parsed.get("topic") or "")
    if topic not in {"vat", "property_tax", "profit_tax", "excise", "customs", "tax"}:
        return None

    ranked = _filtered_rollout_docs(trace)
    if not ranked:
        return None

    year = _extract_query_year(parsed.get("raw_query"))
    year_text = f" в {year} году" if year else ""
    source_chunks: List[Dict[str, Any]] = []
    for doc in ranked[:3]:
        fetched = _fetch_doc_chunks(
            doc.get("source_url"),
            doc.get("title"),
            limit=1,
        )
        if fetched:
            for item in fetched:
                item["_rerank_score"] = doc.get("final_score", 0.0)
            source_chunks.extend(fetched)

    sources = rag_pipeline._prepare_sources(source_chunks)
    if not sources:
        return None

    lang = _response_language(parsed.get("language"))
    topic_label = _topic_label(lang, topic)
    if lang == "en":
        year_text = f" in {year}" if year else ""
        response = (
            f"In the amendment acts for the Tax Code found{year_text}, I did not find fragments that directly relate to {topic_label}. "
            f"So I will not claim that the live corpus confirms amendments on {topic_label} for that period."
        )
    elif lang == "ka":
        year_text = f" {year} წელს" if year else ""
        response = (
            f"საგადასახადო კოდექსში ცვლილებების შესახებ ნაპოვნ აქტებში{year_text} ვერ ვიპოვე ფრაგმენტები, რომლებიც პირდაპირ ეხება {topic_label}. "
            f"ამიტომ არ დავადასტურებ, რომ live corpus-ში ამ პერიოდზე {topic_label}-თან დაკავშირებული დადასტურებული ცვლილებებია."
        )
    else:
        response = (
            f"В найденных актах о внесении изменений в Налоговый кодекс{year_text} я не нашёл фрагментов, "
            f"которые прямо относятся к {topic_label}. "
            f"Поэтому не буду утверждать, что в live corpus есть подтверждённые поправки по {topic_label} за этот период."
        )
    return {
        "response": response,
        "sources": sources,
        "retrieved_count": len(source_chunks),
        "_rag_v2": {
            "mode": "rollout",
            "question_class": "amendment_tracking",
            "channels_used": trace.candidate_generation.get("channels_used", []),
            "top_titles": [doc.get("title") for doc in ranked[:3]],
            "grounded_no_evidence": True,
        },
    }


def _locality_label_ru(locality: str) -> str:
    return {
        "dmanisi": "Дманиси",
        "tbilisi": "Тбилиси",
        "gurjaani": "Гурджаани",
        "municipality": "указанному муниципалитету",
    }.get(locality, locality)


def _locality_label(language: Optional[str], locality: str) -> str:
    lang = _response_language(language)
    labels = {
        "ru": {
            "dmanisi": "Дманиси",
            "tbilisi": "Тбилиси",
            "gurjaani": "Гурджаани",
            "municipality": "указанному муниципалитету",
        },
        "en": {
            "dmanisi": "Dmanisi",
            "tbilisi": "Tbilisi",
            "gurjaani": "Gurjaani",
            "municipality": "the specified municipality",
        },
        "ka": {
            "dmanisi": "დმანისს",
            "tbilisi": "თბილისს",
            "gurjaani": "გურჯაანს",
            "municipality": "მითითებულ მუნიციპალიტეტს",
        },
    }
    return labels[lang].get(locality, locality)


def _no_evidence_local_regulation_response(trace) -> Optional[Dict[str, Any]]:
    parsed = trace.parsed_query or {}
    if trace.classification.get("question_class") != "local_regulation_lookup":
        return None

    locality = str(parsed.get("locality") or "").strip()
    topic = str(parsed.get("topic") or "").strip()
    if not locality or topic != "property_tax":
        return None

    lang = _response_language(parsed.get("language"))
    locality_label = _locality_label(lang, locality)
    if lang == "en":
        response = (
            f"I did not find a confirmed local normative act for {locality_label} in the live corpus with an exact property-tax rate, "
            "so I will not invent a rate without a reliable source."
        )
    elif lang == "ka":
        response = (
            f"live corpus-ში ვერ ვიპოვე {locality_label}-თან დაკავშირებული დადასტურებული ადგილობრივი ნორმატიული აქტი ქონების გადასახადის ზუსტი განაკვეთით, "
            "ამიტომ სანდო წყაროს გარეშე განაკვეთს ვერ მოვიგონებ."
        )
    else:
        response = (
            f"Я не нашёл в live corpus подтверждённый локальный нормативный акт по { locality_label } "
            "с точной ставкой налога на имущество, поэтому не буду придумывать ставку без надёжного источника."
        )
    return {
        "response": response,
        "sources": [],
        "retrieved_count": 0,
        "_rag_v2": {
            "mode": "rollout",
            "question_class": "local_regulation_lookup",
            "channels_used": trace.candidate_generation.get("channels_used", []),
            "top_titles": [],
            "grounded_no_evidence": True,
        },
    }


def _no_evidence_dispute_response(trace) -> Optional[Dict[str, Any]]:
    parsed = trace.parsed_query or {}
    if trace.classification.get("question_class") != "dispute_practice":
        return None

    decision_ref = str(parsed.get("decision_ref") or parsed.get("document_ref") or "").strip()
    if not decision_ref:
        return None

    ranked = trace.reranking.get("top_ranked_documents", [])
    if any(decision_ref in str(doc.get("title") or "") for doc in ranked[:5]):
        return None

    lang = _response_language(parsed.get("language"))
    if lang == "en":
        response = (
            f"I did not find a confirmed decision in the live corpus specifically for dispute №{decision_ref}, "
            "so I will not attribute the outcome of another case to this dispute."
        )
    elif lang == "ka":
        response = (
            f"live corpus-ში ვერ ვიპოვე დადასტურებული გადაწყვეტილება კონკრეტულად დავაზე №{decision_ref}, "
            "ამიტომ სხვა საქმის შედეგს ამ დავას არ მივაწერ."
        )
    else:
        response = (
            f"Я не нашёл в live corpus подтверждённое решение именно по спору №{decision_ref}, "
            "поэтому не буду приписывать выводы другого дела этому спору."
        )
    return {
        "response": response,
        "sources": [],
        "retrieved_count": 0,
        "_rag_v2": {
            "mode": "rollout",
            "question_class": "dispute_practice",
            "channels_used": trace.candidate_generation.get("channels_used", []),
            "top_titles": [doc.get("title") for doc in ranked[:3]],
            "grounded_no_evidence": True,
        },
    }


def _generation_query(query: str, trace, context: str) -> str:
    ranked = trace.reranking.get("top_ranked_documents", [])
    metadata = (ranked[0].get("metadata") or {}) if ranked else {}
    point_ref = str(metadata.get("point_ref") or "").strip()
    article_ref = str(metadata.get("article_ref") or "").strip()
    question_class = trace.classification.get("question_class")
    parsed = trace.parsed_query or {}
    lang = _response_language(parsed.get("language"))
    answer_lang = _answer_language_name(lang)
    language_guard = _language_output_guard(lang)
    if point_ref and len(context or "") > 2500:
        return (
            f"{query}\n\n"
            f"Answer in {answer_lang}. Keep it concise and to the point: 2-4 sentences. "
            "List only the main categories or rules without copying long subpoints. "
            f"{language_guard}"
        )
    if question_class == "canonical_law_lookup" and article_ref and not point_ref:
        return (
            f"{query}\n\n"
            f"Answer in {answer_lang} as plain text, very briefly and accurately based on the found article. "
            "Format: at most 2-3 sentences. First state the main rule of the article, then one important clarification or exception if needed. "
            "Do not retell the full article text, do not use markdown emphasis, and do not include markdown links."
            f" {language_guard}"
        )
    if question_class == "amendment_tracking":
        return (
            f"{query}\n\n"
            f"Answer in {answer_lang}, briefly and strictly based on the found amendments. "
            "Format: at most one very short intro sentence, then a numbered list of 1-2 short points. "
            "Each point should be a single short sentence: what changed and, if visible in context, the article or part. "
            "Do not use markdown emphasis, links, or long restatements of the legal text. If an exact detail is not present in context, do not invent it."
            f" {language_guard}"
        )
    if question_class == "named_document_lookup":
        return (
            f"{query}\n\n"
            f"Answer in {answer_lang} as plain text, very briefly. "
            "Format: at most 2 sentences. First say what kind of document it is, then what it generally explains or which practical issue it focuses on. "
            "Do not retell every case fact and do not use markdown emphasis or markdown links."
            f" {language_guard}"
        )
    if question_class == "canonical_law_lookup":
        return (
            f"{query}\n\n"
            f"Answer in {answer_lang} as plain text, briefly and accurately based on the found provision. "
            "Start with a direct answer in 1-3 short paragraphs. Do not use markdown emphasis or markdown links. "
            "Do not copy unnecessary article text if a short accurate summary is enough."
            f" {language_guard}"
        )
    if question_class == "local_regulation_lookup":
        return (
            f"{query}\n\n"
            f"Answer in {answer_lang} as plain text, briefly and practically. "
            "Start with the rate or the main rule, then add 1-2 clarifications if needed. Do not use markdown emphasis or markdown links. "
            f"{language_guard}"
        )
    if question_class == "practical_tax_guidance":
        if parsed.get("topic") == "property_tax" and parsed.get("subject") == "individual":
            return (
                f"{query}\n\n"
                f"Answer in {answer_lang} as plain text, briefly and practically. "
                "If the question is about an individual's property tax, do not replace it with the corporate rate. "
                "First say directly that for an individual the tax depends on income and applicability conditions, then add 1-2 key rules. "
                "If context contains a separate corporate rate, you may briefly note that it is a different regime. Do not use markdown emphasis, bullet lists, or markdown links."
                f" {language_guard}"
            )
        return (
            f"{query}\n\n"
            f"Answer in {answer_lang} as plain text, briefly and practically. "
            "Format: at most 3-5 sentences. Start with the direct practical takeaway, then add 1-2 key application rules. "
            "Do not use markdown emphasis, bullet lists, or markdown links."
            f" {language_guard}"
        )
    if question_class == "dispute_practice":
        return (
            f"{query}\n\n"
            f"Answer in {answer_lang} as plain text, briefly and strictly based on the found dispute. "
            "If the context does not contain a confirmed match for the dispute number, do not invent details. "
            "Do not use markdown emphasis or markdown links."
            f" {language_guard}"
        )
    return query


def maybe_run_live_rollout(
    *,
    query: str,
    language: str,
    conversation_history: Optional[List[Dict[str, str]]] = None,
) -> Optional[Dict[str, Any]]:
    if _mode() != "rollout":
        return None

    trace = pipeline_v2.build_trace(query, language=language)
    question_class = trace.classification.get("question_class")
    if question_class not in _rollout_classes():
        return None
    if not trace.source_audit.get("passed"):
        local_no_evidence = _no_evidence_local_regulation_response(trace)
        if local_no_evidence:
            print("[RAG_V2_ROLLOUT] class=local_regulation_lookup grounded_no_evidence=1")
            return local_no_evidence
        dispute_no_evidence = _no_evidence_dispute_response(trace)
        if dispute_no_evidence:
            print("[RAG_V2_ROLLOUT] class=dispute_practice grounded_no_evidence=1")
            return dispute_no_evidence
        return None

    rollout_chunks = _build_rollout_chunks(trace)
    if not rollout_chunks:
        local_no_evidence = _no_evidence_local_regulation_response(trace)
        if local_no_evidence:
            print("[RAG_V2_ROLLOUT] class=local_regulation_lookup grounded_no_evidence=1")
            return local_no_evidence
        dispute_no_evidence = _no_evidence_dispute_response(trace)
        if dispute_no_evidence:
            print("[RAG_V2_ROLLOUT] class=dispute_practice grounded_no_evidence=1")
            return dispute_no_evidence
        no_evidence = _no_evidence_amendment_response(trace)
        if no_evidence:
            print("[RAG_V2_ROLLOUT] class=amendment_tracking grounded_no_evidence=1")
            return no_evidence
        return None

    context = rag_pipeline._assemble_context(rollout_chunks)
    generation_query = _generation_query(query, trace, context)
    response = rag_pipeline.llm.generate_response(
        query=generation_query,
        context=context,
        conversation_history=conversation_history,
    )
    response = (
        direct_tax_faq_response(trace)
        or nonresident_withholding_tax_response(trace)
        or import_vat_response(trace)
        or royalty_tax_rate_response(trace)
        or interest_tax_rate_response(trace)
        or rental_income_tax_rate_response(trace)
        or dividend_tax_rate_response(trace)
        or small_business_tax_rate_response(trace)
        or vat_rate_response(trace)
        or profit_tax_rate_response(trace)
        or income_tax_rate_response(trace)
        or individual_property_tax_rate_response(trace)
        or response
    )
    response = finalize_rollout_response(response, trace)
    sources = rag_pipeline._prepare_sources(rollout_chunks)
    if not sources:
        return None

    result = {
        "response": response,
        "sources": sources,
        "retrieved_count": len(rollout_chunks),
        "_rag_v2": {
            "mode": "rollout",
            "question_class": question_class,
            "channels_used": trace.candidate_generation.get("channels_used", []),
            "top_titles": [doc.get("title") for doc in trace.reranking.get("top_ranked_documents", [])[:3]],
        },
    }
    print(f"[RAG_V2_ROLLOUT] class={question_class} sources={len(sources)} chunks={len(rollout_chunks)}")
    return result
