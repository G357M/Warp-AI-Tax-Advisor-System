"""Public evidence contract for every generated legal answer.

The contract deliberately says ``grounded`` rather than ``verified``: a link
to an official document proves provenance, but it does not by itself prove
that every generated sentence is legally correct or current.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict
from urllib.parse import urlparse

OFFICIAL_SOURCE_HOSTS = {
    "infohub.rs.ge",
    "infohubapi.rs.ge",
    "rs.ge",
    "www.rs.ge",
    "matsne.gov.ge",
    "www.matsne.gov.ge",
}


def _is_official_source(source: Dict[str, Any]) -> bool:
    url = str(source.get("url") or source.get("source_url") or "").strip()
    if not url:
        return False
    try:
        return (urlparse(url).hostname or "").lower() in OFFICIAL_SOURCE_HOSTS
    except ValueError:
        return False


def attach_evidence(result: Dict[str, Any]) -> Dict[str, Any]:
    """Attach a stable, non-LLM evidence summary to a RAG result."""
    sources = [
        source for source in (result.get("sources") or []) if isinstance(source, dict)
    ]
    rag_meta = result.get("_rag_v2") or {}
    mode = str(rag_meta.get("mode") or "legacy")
    question_class = rag_meta.get("question_class")
    grounded_no_evidence = bool(rag_meta.get("grounded_no_evidence"))

    precise = any(
        source.get("article_ref")
        or source.get("point_ref")
        or source.get("document_number")
        for source in sources
    )
    official_only = bool(sources) and all(
        _is_official_source(source) for source in sources
    )

    if mode == "rollout_scope":
        status = "out_of_scope"
        basis = "scope"
    elif grounded_no_evidence or not sources:
        status = "insufficient"
        basis = "none"
    elif official_only:
        status = "grounded"
        basis = "authoritative" if mode == "rollout_authoritative" else "retrieval"
    else:
        status = "partial"
        basis = "retrieval"

    result["evidence"] = {
        "status": status,
        "basis": basis,
        "coverage": (
            "exact_provision"
            if precise
            else ("official_documents" if sources else "none")
        ),
        "question_class": question_class,
        "source_count": len(sources),
        "official_sources_only": official_only,
        "has_precise_citation": precise,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    return result
