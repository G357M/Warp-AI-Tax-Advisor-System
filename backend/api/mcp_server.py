"""Private MCP endpoint: lets Claude (claude.ai connectors, Cowork, Claude Code)
query the tax-advisor.ge corpus directly.

Design constraints:
- read-only: no tool writes to the database or triggers ingestion;
- runs inside the existing backend process, so the already-loaded embedding
  model, DB pool and RAG pipeline are reused (no second copy of the model);
- disabled unless MCP_ACCESS_TOKEN is set (>= 32 chars). Clients authenticate
  with ``Authorization: Bearer <token>`` or ``X-MCP-Token``. Nginx maps the
  claude.ai-friendly URL ``/mcp/<token>`` to ``X-MCP-Token`` so the secret
  never reaches backend access logs or Prometheus endpoint labels;
- heavy modules (torch, pipeline) are imported lazily inside the tools, so
  importing this module is cheap and unit-testable.
"""
from __future__ import annotations

import contextlib
import hmac
import json
import logging
import os
import re
from typing import Any, Callable, Literal, Optional
from uuid import UUID

logger = logging.getLogger(__name__)

MIN_TOKEN_LENGTH = 32
MAX_SEARCH_LIMIT = 20
MAX_DOCUMENT_SLICE = 50_000
DEFAULT_ALLOWED_HOSTS = "tax-advisor.ge,www.tax-advisor.ge,localhost:*,127.0.0.1:*,backend:*"

INSTRUCTIONS = (
    "tax-advisor.ge corpus: Georgian tax and related law from infohub.rs.ge "
    "(Tax Code, laws, MoF orders, Revenue Service guidance, tax dispute decisions). "
    "Workflow: search_corpus first (prefer a Georgian query; ru/en are machine-translated), "
    "then get_document for full text, get_official_provision for a verified Matsne "
    "article link. Always cite document title, article and source_url. "
    "ask_tax_advisor returns the site's own LLM answer with an evidence status; use it "
    "as a second opinion, not as the source. If the corpus has nothing relevant, say so."
)

Language = Literal["ka", "ru", "en"]
ProvisionAct = Literal[
    "tax_code",
    "general_administrative_code",
    "civil_code",
    "entrepreneurs_law",
    "labour_code",
    "funded_pension_law",
]

_SOURCE_FIELDS = (
    "article_ref",
    "point_ref",
    "section_label",
    "document_number",
    "date_published",
    "date_effective",
    "document_status",
    "authority",
    "retrieval_channel",
)


# --------------------------------------------------------------------------- #
# Data access (overridable in tests)
# --------------------------------------------------------------------------- #

def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    return str(value)


def _retrieve_chunks(query: str, language: str) -> list[dict[str, Any]]:
    """Retrieval half of RAGPipeline.process_query (steps 1-3 + rerank/filter),
    without LLM answer generation. Keep in sync with rag/pipeline.py."""
    from core.config import settings
    from rag.pipeline import rag_pipeline as p

    retrieval_query = p._retrieval_query(query, language)
    direct = p._customs_handbook_direct_chunks(
        query, language=language, limit=max(settings.RAG_RERANK_TOP_K, 6)
    )
    if direct:
        return direct

    embedding = p.embeddings.encode_query(retrieval_query)
    search_results = p.vector_store.search(
        query_embedding=embedding,
        n_results=max(settings.RAG_TOP_K * 5, 50),
        where=p._build_search_filters(query, language=language) or None,
    )
    chunks = p._retrieve_chunks(search_results)

    lane = p._intent_lane(p._extract_query_hints(query, language=language))
    fallback_language = "ka" if language == "ru" and lane == "normative" else language
    k = settings.RAG_RERANK_TOP_K
    for extra in (
        p._canonical_override_chunks(retrieval_query, language=fallback_language, limit=4),
        p._title_lookup_chunks(retrieval_query, language=fallback_language, limit=max(k, 4)),
        p._keyword_fallback_chunks(retrieval_query, language=fallback_language, limit=max(k, 8)),
    ):
        if extra:
            chunks = extra + chunks
    chunks = p._rerank_chunks(retrieval_query, chunks, language=language)
    return p._filter_chunks_for_intent(query, chunks, language=language)


def _enrich(source: dict[str, Any]) -> dict[str, Any]:
    from rag_v2.official_provisions import enrich_source

    try:
        return enrich_source(source)
    except Exception:  # registry problems must not break search
        logger.exception("official provision enrichment failed")
        return source


def _format_chunk(chunk: dict[str, Any], max_chars: int) -> dict[str, Any]:
    md = chunk.get("metadata") or {}
    content = chunk.get("content") or ""
    source = {
        "document_id": md.get("document_id"),
        "title": md.get("title") or md.get("document_title") or "",
        "document_type": md.get("document_type") or "",
        "url": md.get("source_url") or md.get("url") or "",
        **{f: md.get(f) for f in _SOURCE_FIELDS},
    }
    source = _enrich(source)
    source["source_url"] = source.pop("url", "")
    source["relevance"] = round(float(chunk.get("_rerank_score", chunk.get("similarity", 0.0)) or 0.0), 4)
    source["text"] = content[:max_chars]
    source["text_truncated"] = len(content) > max_chars
    return _jsonable(source)


def _load_document(document_id: UUID) -> Optional[dict[str, Any]]:
    from core.database import SessionLocal
    from models.document import Document

    db = SessionLocal()
    try:
        doc = db.get(Document, document_id)
        if doc is None:
            return None
        return {
            "document_id": str(doc.id),
            "title": doc.title,
            "document_type": doc.document_type,
            "document_number": doc.document_number,
            "date_published": doc.date_published,
            "date_effective": doc.date_effective,
            "language": doc.language,
            "category": doc.category,
            "authority": doc.authority,
            "status": doc.status,
            "source_url": doc.source_url,
            "full_text": doc.full_text or "",
        }
    finally:
        db.close()


_ARTICLE_INPUT = re.compile(r"^\s*(\d+)\s*(?:(?:-|\.|_)\s*(\d+)|([¹²³⁴⁵⁶⁷⁸⁹⁰]+))?\s*$")
_SUPERSCRIPT = str.maketrans("1234567890", "¹²³⁴⁵⁶⁷⁸⁹⁰")
_FROM_SUPERSCRIPT = str.maketrans("¹²³⁴⁵⁶⁷⁸⁹⁰", "1234567890")


def _article_forms(article: str) -> tuple[str, list[str]]:
    """'166-1' / '166¹' / '166.1' -> (registry key '166-1', DB forms ['166-1','166¹'])."""
    m = _ARTICLE_INPUT.match(article or "")
    if not m:
        raise ValueError("article must look like '168', '166-1' or '166¹'")
    base, dashed, sup = m.groups()
    suffix = dashed or (sup.translate(_FROM_SUPERSCRIPT) if sup else None)
    if not suffix:
        return base, [base]
    key = f"{base}-{suffix}"
    return key, [key, f"{base}{suffix.translate(_SUPERSCRIPT)}"]


def _load_article_chunks(infohub_source_url: str, forms: list[str]) -> list[dict[str, Any]]:
    from sqlalchemy import bindparam, text
    from core.database import SessionLocal

    doc_key = infohub_source_url.rstrip("/").rsplit("/", 1)[-1]
    sql = text(
        """
        SELECT d.id::text AS document_id, d.title, d.source_url,
               c.chunk_index, c.content, c.metadata::text AS metadata
        FROM documents d
        JOIN document_chunks c ON c.document_id = d.id
        WHERE d.source_url LIKE :doc_like
          AND (c.metadata::jsonb ->> 'article_ref') IN :forms
        ORDER BY d.updated_at DESC, c.chunk_index
        LIMIT 20
        """
    ).bindparams(bindparam("forms", expanding=True))
    db = SessionLocal()
    try:
        rows = db.execute(sql, {"doc_like": f"%{doc_key}", "forms": forms}).mappings().all()
    finally:
        db.close()
    if not rows:
        return []
    newest = rows[0]["document_id"]
    out = []
    for row in rows:
        if row["document_id"] != newest:
            continue
        md = json.loads(row["metadata"] or "{}")
        out.append({
            "document_id": row["document_id"],
            "title": row["title"],
            "source_url": row["source_url"],
            "chunk_index": row["chunk_index"],
            "article_part": md.get("article_part"),
            "section_label": md.get("section_label"),
            "text": row["content"],
        })
    return out


def _run_public_query(question: str, language: str) -> dict[str, Any]:
    from api.routes.public import PublicQueryRequest, process_public_query

    result = process_public_query(PublicQueryRequest(query=question, language=language))
    return result.model_dump(mode="json")


# --------------------------------------------------------------------------- #
# MCP server
# --------------------------------------------------------------------------- #

def build_mcp_server(
    *,
    retrieve: Callable[[str, str], list[dict[str, Any]]] = _retrieve_chunks,
    load_document: Callable[[UUID], Optional[dict[str, Any]]] = _load_document,
    load_article_chunks: Callable[[str, list[str]], list[dict[str, Any]]] = _load_article_chunks,
    run_public_query: Callable[[str, str], dict[str, Any]] = _run_public_query,
):
    from mcp.server.mcpserver import MCPServer
    from mcp.types import ToolAnnotations

    server = MCPServer("tax-advisor", title="tax-advisor.ge", instructions=INSTRUCTIONS)
    read_only = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)

    @server.tool(annotations=read_only)
    def search_corpus(
        query: str,
        language: Language = "ka",
        limit: int = 8,
        max_chars_per_chunk: int = 4000,
    ) -> dict[str, Any]:
        """Search the Georgian tax/legal corpus (laws, Tax Code articles, MoF orders,
        Revenue Service guidance, tax dispute decisions). Returns ranked passages with
        document_id, title, article_ref, dates, source_url and, where verified, official
        Matsne provision_links. No LLM answer is generated. Prefer a Georgian query
        (language='ka'); ru/en queries are machine-translated before retrieval."""
        query = (query or "").strip()
        if not query or len(query) > 2000:
            raise ValueError("query must be 1..2000 characters")
        limit = max(1, min(int(limit), MAX_SEARCH_LIMIT))
        max_chars = max(200, min(int(max_chars_per_chunk), 20_000))
        chunks = retrieve(query, language)[:limit]
        return {
            "query": query,
            "language": language,
            "count": len(chunks),
            "results": [_format_chunk(c, max_chars) for c in chunks],
        }

    @server.tool(annotations=read_only)
    def get_document(document_id: str, offset: int = 0, max_chars: int = 20_000) -> dict[str, Any]:
        """Full text of one corpus document by document_id (from search_corpus), paginated.
        Call again with next_offset while it is not null."""
        try:
            doc_uuid = UUID(str(document_id))
        except ValueError as exc:
            raise ValueError("document_id must be a UUID from search_corpus") from exc
        doc = load_document(doc_uuid)
        if doc is None:
            raise ValueError(f"document {document_id} not found")
        full_text = doc.pop("full_text", "") or ""
        offset = max(0, int(offset))
        size = max(1000, min(int(max_chars), MAX_DOCUMENT_SLICE))
        end = min(len(full_text), offset + size)
        doc.update({
            "total_chars": len(full_text),
            "offset": offset,
            "next_offset": end if end < len(full_text) else None,
            "text": full_text[offset:end],
        })
        return _jsonable(doc)

    @server.tool(annotations=read_only)
    def get_official_provision(act: ProvisionAct, article: str) -> dict[str, Any]:
        """Verified official Matsne link for an article of a supported act, plus the
        article text held in the corpus when available. Acts: tax_code (Tax Code),
        general_administrative_code, civil_code, entrepreneurs_law, labour_code,
        funded_pension_law. article: '168', '166-1' or '166¹'."""
        from rag_v2.official_provisions import load_official_provision_registries

        key, forms = _article_forms(article)
        registry = next(
            (r for r in load_official_provision_registries() if r["registry_id"] == act), None
        )
        if registry is None:
            raise ValueError(f"unknown act {act}")
        link = (registry.get("article_links") or {}).get(key)
        anchor = (registry.get("article_anchors") or {}).get(key)
        if not link and anchor:
            link = f"{registry['matsne_document_url']}#{anchor}"
        chunks = load_article_chunks(registry["infohub_source_url"], forms)
        return _jsonable({
            "act": act,
            "act_title": registry.get("act_title"),
            "article": key,
            "official_provision_url": link,
            "official_link_verified": bool(link),
            "official_act_url": registry.get("matsne_document_url"),
            "registry_version": registry.get("registry_version"),
            "registry_verified_at": registry.get("verified_at_utc"),
            "verified_publication_url": registry.get("verified_publication_url"),
            "infohub_source_url": registry.get("infohub_source_url"),
            "corpus_text_found": bool(chunks),
            "corpus_chunks": chunks,
            "note": None if link else "Article is not in the verified registry (absent, repealed or ambiguous anchor); cite the act-level URL.",
        })

    @server.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=False, openWorldHint=False))
    def ask_tax_advisor(question: str, language: Language = "ru") -> dict[str, Any]:
        """Run the full tax-advisor.ge answer pipeline (same as the public site) and
        return its answer, sources and deterministic evidence status
        (exact norm / documentary / partial / insufficient / out of jurisdiction).
        Uses the site's LLM budget; treat it as a second opinion and verify against
        search_corpus / get_official_provision."""
        question = (question or "").strip()
        if not question or len(question) > 2000:
            raise ValueError("question must be 1..2000 characters")
        return run_public_query(question, language)

    return server


# --------------------------------------------------------------------------- #
# ASGI wiring
# --------------------------------------------------------------------------- #

class _TokenGate:
    """Constant-time token check in front of the MCP session manager."""

    def __init__(self, handle: Callable, token: str):
        self._handle = handle
        self._token = token.encode()

    def _authorized(self, scope) -> bool:
        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers") or []}
        candidates = [headers.get("x-mcp-token", "")]
        auth = headers.get("authorization", "")
        if auth.lower().startswith("bearer "):
            candidates.append(auth[7:].strip())
        return any(c and hmac.compare_digest(c.encode(), self._token) for c in candidates)

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return
        if not self._authorized(scope):
            body = b'{"error":"unauthorized"}'
            await send({"type": "http.response.start", "status": 401, "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode()),
                (b"www-authenticate", b"Bearer"),
            ]})
            await send({"type": "http.response.body", "body": body})
            return
        await self._handle(scope, receive, send)


def install_mcp(app, *, token: Optional[str] = None, allowed_hosts: Optional[str] = None, server=None) -> bool:
    """Mount the MCP endpoint at /mcp if MCP_ACCESS_TOKEN is configured."""
    from mcp.server.transport_security import TransportSecuritySettings

    token = (token if token is not None else os.getenv("MCP_ACCESS_TOKEN", "")).strip()
    if not token:
        logger.info("MCP endpoint disabled (MCP_ACCESS_TOKEN not set)")
        return False
    if len(token) < MIN_TOKEN_LENGTH:
        raise RuntimeError(f"MCP_ACCESS_TOKEN must be at least {MIN_TOKEN_LENGTH} characters")

    hosts = [h.strip() for h in (allowed_hosts or os.getenv("MCP_ALLOWED_HOSTS", DEFAULT_ALLOWED_HOSTS)).split(",") if h.strip()]
    server = server or build_mcp_server()
    server.streamable_http_app(
        stateless_http=True,
        json_response=True,
        host="0.0.0.0",
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=hosts,
            allowed_origins=["https://claude.ai", "https://claude.com"],
        ),
    )
    manager = server.session_manager
    app.mount("/mcp", _TokenGate(manager.handle_request, token))

    # The session manager needs a running task group. Startup and shutdown
    # handlers run inside the same lifespan task, so the context is entered and
    # exited in one task.
    stack = contextlib.AsyncExitStack()

    async def _start():
        await stack.enter_async_context(manager.run())

    async def _stop():
        await stack.aclose()

    app.router.add_event_handler("startup", _start)
    app.router.add_event_handler("shutdown", _stop)
    logger.info("MCP endpoint mounted at /mcp (stateless, read-only tools)")
    return True
