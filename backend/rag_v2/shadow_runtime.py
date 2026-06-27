from __future__ import annotations

import json
import os
import random
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from .pipeline_v2 import pipeline_v2


def _mode() -> str:
    return (os.getenv("INFOHUB_RAG_V2_MODE") or "off").strip().lower()


def _sample_rate() -> float:
    try:
        return max(0.0, min(1.0, float(os.getenv("INFOHUB_RAG_V2_SHADOW_SAMPLE_RATE", "1.0"))))
    except Exception:
        return 1.0


def _log_path() -> str:
    return os.getenv("INFOHUB_RAG_V2_SHADOW_LOG_PATH", "/tmp/rag_v2_shadow.jsonl")


def _summarize_legacy_result(result: Dict[str, Any]) -> Dict[str, Any]:
    sources = []
    for item in (result or {}).get("sources", [])[:5]:
        sources.append(
            {
                "document_id": item.get("document_id"),
                "title": item.get("title"),
                "document_type": item.get("document_type"),
                "url": item.get("url"),
                "relevance": item.get("relevance"),
            }
        )

    return {
        "retrieved_count": (result or {}).get("retrieved_count"),
        "sources": sources,
        "response_preview": ((result or {}).get("response") or "")[:400],
    }


def _append_jsonl(path_str: str, record: Dict[str, Any]) -> None:
    path = Path(path_str)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def maybe_run_shadow(
    *,
    query: str,
    language: str,
    route: str,
    legacy_result: Dict[str, Any],
    extra: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    if _mode() != "shadow":
        return None
    if random.random() > _sample_rate():
        return None

    record: Dict[str, Any] = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "route": route,
        "query": query,
        "language": language,
        "extra": extra or {},
        "legacy": _summarize_legacy_result(legacy_result),
    }

    try:
        trace = pipeline_v2.build_trace(query, language=language)
        reranked = trace.reranking.get("top_ranked_documents", [])
        record["v2"] = {
            "question_class": trace.classification.get("question_class"),
            "channels_used": trace.candidate_generation.get("channels_used", []),
            "source_audit": trace.source_audit,
            "top_ranked_documents": reranked[:5],
        }
        record["status"] = "ok"
    except Exception as exc:  # pragma: no cover - runtime safety path
        record["status"] = "error"
        record["error"] = f"{type(exc).__name__}: {exc}"

    print("[RAG_V2_SHADOW] " + json.dumps(record, ensure_ascii=False))
    try:
        _append_jsonl(_log_path(), record)
    except Exception as exc:  # pragma: no cover - runtime safety path
        print(f"[RAG_V2_SHADOW] log-write-error: {type(exc).__name__}: {exc}")

    return record
