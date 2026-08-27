"""Single-source contracts for deterministic multilingual legal answers.

The contract factory keeps the legal fact text, official provision identity,
localized citation and generated evaluation cases tied together.  The final
response enforcer is deliberately conservative: it only appends a citation
when the deterministic evidence contract already proves that a verified
official provision link is present.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple


SUPPORTED_LANGUAGES: Tuple[str, ...] = ("ru", "en", "ka")

_SUPERSCRIPT_TO_ASCII = str.maketrans("¹²³⁴⁵⁶⁷⁸⁹⁰", "1234567890")
_ASCII_TO_SUPERSCRIPT = str.maketrans("1234567890", "¹²³⁴⁵⁶⁷⁸⁹⁰")
_CANONICAL_ARTICLE = re.compile(r"\d+(?:-\d+)?")

_SOURCE_LABELS = {"ru": "Источник", "en": "Source", "ka": "წყარო"}
_SINGLE_ARTICLE_LABELS = {"ru": "статья", "en": "Article", "ka": "მუხლი"}
_MULTIPLE_ARTICLE_LABELS = {"ru": "статьи", "en": "Articles", "ka": "მუხლები"}
_ARTICLE_CONJUNCTIONS = {"ru": "и", "en": "and", "ka": "და"}

REGISTRY_TITLES: Mapping[str, Mapping[str, str]] = {
    "tax_code": {
        "ru": "Налоговый кодекс Грузии",
        "en": "Tax Code of Georgia",
        "ka": "საქართველოს საგადასახადო კოდექსი",
    },
    "general_administrative_code": {
        "ru": "Общий административный кодекс Грузии",
        "en": "General Administrative Code of Georgia",
        "ka": "საქართველოს ზოგადი ადმინისტრაციული კოდექსი",
    },
    "civil_code": {
        "ru": "Гражданский кодекс Грузии",
        "en": "Civil Code of Georgia",
        "ka": "საქართველოს სამოქალაქო კოდექსი",
    },
    "entrepreneurs_law": {
        "ru": "Закон Грузии «О предпринимателях»",
        "en": "Law of Georgia on Entrepreneurs",
        "ka": "საქართველოს კანონი „მეწარმეთა შესახებ“",
    },
    "labour_code": {
        "ru": "Трудовой кодекс Грузии",
        "en": "Labour Code of Georgia",
        "ka": "საქართველოს შრომის კოდექსი",
    },
}


def canonical_article_ref(value: str) -> str:
    """Normalize one provision identifier to the registry's ``N``/``N-M`` form."""
    cleaned = str(value or "").strip().replace("–", "-").replace("—", "-")
    superscript = re.fullmatch(r"(\d+)([¹²³⁴⁵⁶⁷⁸⁹⁰]+)", cleaned)
    if superscript:
        cleaned = (
            f"{superscript.group(1)}-"
            f"{superscript.group(2).translate(_SUPERSCRIPT_TO_ASCII)}"
        )
    if not _CANONICAL_ARTICLE.fullmatch(cleaned):
        raise ValueError(f"invalid canonical article reference: {value}")
    return cleaned


def display_article_ref(value: str) -> str:
    """Render inserted articles in their legal superscript form."""
    canonical = canonical_article_ref(value)
    inserted = re.fullmatch(r"(\d+)-(\d+)", canonical)
    if not inserted:
        return canonical
    return f"{inserted.group(1)}{inserted.group(2).translate(_ASCII_TO_SUPERSCRIPT)}"


def format_official_citation(
    language: str,
    registry_id: str,
    article_refs: Sequence[str],
) -> str:
    language = language if language in SUPPORTED_LANGUAGES else "ru"
    titles = REGISTRY_TITLES.get(registry_id)
    if not titles:
        raise ValueError(f"unsupported official provision registry: {registry_id}")
    refs = tuple(dict.fromkeys(canonical_article_ref(item) for item in article_refs))
    if not refs:
        raise ValueError("at least one article reference is required")
    displayed_refs = [display_article_ref(item) for item in refs]
    if len(displayed_refs) == 1:
        displayed = displayed_refs[0]
    elif len(displayed_refs) == 2:
        displayed = f"{displayed_refs[0]} {_ARTICLE_CONJUNCTIONS[language]} {displayed_refs[1]}"
    else:
        displayed = (
            f"{', '.join(displayed_refs[:-1])} "
            f"{_ARTICLE_CONJUNCTIONS[language]} {displayed_refs[-1]}"
        )
    article_label = (
        _SINGLE_ARTICLE_LABELS[language]
        if len(refs) == 1
        else _MULTIPLE_ARTICLE_LABELS[language]
    )
    return (
        f"{_SOURCE_LABELS[language]}: {titles[language]}, "
        f"{article_label} {displayed}."
    )


def _has_complete_source_line(
    response: str,
    language: str,
    registry_id: str,
    article_refs: Sequence[str],
) -> bool:
    label = _SOURCE_LABELS.get(language, _SOURCE_LABELS["ru"])
    source_lines = [
        line.strip()
        for line in str(response or "").splitlines()
        if line.strip().casefold().startswith(f"{label}:".casefold())
    ]
    if not source_lines:
        return False
    expected = format_official_citation(language, registry_id, article_refs)
    normalized_expected = re.sub(r"\s+", " ", expected).strip().casefold()
    return any(
        re.sub(r"\s+", " ", line).strip().casefold() == normalized_expected
        for line in source_lines
    )


def ensure_exact_provision_citations(
    result: Dict[str, Any], language: Optional[str]
) -> Dict[str, Any]:
    """Append missing localized citations proven by exact-provision evidence."""
    evidence = result.get("evidence") or {}
    if (
        evidence.get("coverage") != "exact_provision"
        or evidence.get("has_official_provision_link") is not True
    ):
        return result

    selected_language = language if language in SUPPORTED_LANGUAGES else "ru"
    groups: Dict[str, List[str]] = {}
    for source in result.get("sources") or []:
        if not isinstance(source, dict):
            continue
        registry_id = str(source.get("provision_registry_id") or "").strip()
        if registry_id not in REGISTRY_TITLES:
            continue
        for link in source.get("provision_links") or []:
            if not isinstance(link, dict):
                continue
            try:
                article_ref = canonical_article_ref(str(link.get("article_ref") or ""))
            except ValueError:
                continue
            groups.setdefault(registry_id, []).append(article_ref)

    response = str(result.get("response") or "").strip()
    additions = []
    for registry_id, raw_refs in groups.items():
        refs = tuple(dict.fromkeys(raw_refs))
        if refs and not _has_complete_source_line(
            response, selected_language, registry_id, refs
        ):
            additions.append(
                format_official_citation(selected_language, registry_id, refs)
            )
    if additions:
        result["response"] = "\n\n".join([response, *additions]).strip()
    return result


@dataclass(frozen=True)
class LegalAnswerContract:
    slug: str
    topic: str
    article_ref: str
    question_class: str
    response_kind: str
    sample_queries: Dict[str, str]
    response_by_lang: Dict[str, str]
    match_goals: Tuple[str, ...] = ("rate_lookup",)
    note: str = ""
    subject: Optional[str] = None
    smoke_contains: Optional[Dict[str, List[str]]] = None
    additional_article_refs: Tuple[str, ...] = ()
    registry_id: str = "tax_code"

    def matches(
        self,
        parsed: Mapping[str, Any],
        question_class: Optional[str],
    ) -> bool:
        """Return whether deterministic parser output selects this contract."""
        if parsed.get("topic") != self.topic:
            return False
        if question_class != self.question_class:
            return False
        if parsed.get("goal") not in self.match_goals:
            return False
        if self.subject and parsed.get("subject") not in {None, self.subject}:
            return False
        return True

    @property
    def article_refs(self) -> Tuple[str, ...]:
        return tuple(
            dict.fromkeys(
                canonical_article_ref(item)
                for item in (self.article_ref, *self.additional_article_refs)
            )
        )

    def citation(self, language: str) -> str:
        return format_official_citation(language, self.registry_id, self.article_refs)

    def response(self, language: str) -> str:
        selected = language if language in SUPPORTED_LANGUAGES else "ru"
        base = self.response_by_lang.get(selected) or self.response_by_lang["ru"]
        if _has_complete_source_line(
            base, selected, self.registry_id, self.article_refs
        ):
            return base
        return f"{base.rstrip()}\n\n{self.citation(selected)}"


def build_contract_cases(
    contracts: Iterable[LegalAnswerContract],
) -> List[Dict[str, Any]]:
    """Generate all localized evaluation cases directly from the contracts."""
    from .official_provisions import load_official_provision_registries

    registries = {
        registry["registry_id"]: registry
        for registry in load_official_provision_registries()
    }
    cases: List[Dict[str, Any]] = []
    for contract in contracts:
        registry = registries.get(contract.registry_id)
        if not registry:
            raise ValueError(
                f"contract {contract.slug} uses unknown registry {contract.registry_id}"
            )
        primary_ref = contract.article_refs[0]
        anchor = registry["article_anchors"].get(primary_ref)
        if not anchor:
            raise ValueError(
                f"contract {contract.slug} article {primary_ref} has no verified anchor"
            )
        for language in SUPPORTED_LANGUAGES:
            required = list((contract.smoke_contains or {}).get(language) or [])
            required.extend(
                [
                    display_article_ref(primary_ref),
                    contract.citation(language),
                ]
            )
            cases.append(
                {
                    "id": f"{contract.slug}_{language}",
                    "slug": contract.slug,
                    "topic": contract.topic,
                    "language": language,
                    "query": contract.sample_queries[language],
                    "required_response_all": list(dict.fromkeys(required)),
                    "article_refs": list(contract.article_refs),
                    "evidence": {
                        "status": "grounded",
                        "coverage": "exact_provision",
                        "official_sources_only": True,
                        "has_precise_citation": True,
                        "has_official_provision_link": True,
                        "min_source_count": 1,
                    },
                    "official_provision": {
                        "registry_id": contract.registry_id,
                        "article_ref": primary_ref,
                        "url": f"{registry['matsne_document_url']}#{anchor}",
                        "verified_publication_url": registry[
                            "verified_publication_url"
                        ],
                    },
                }
            )
    return cases
