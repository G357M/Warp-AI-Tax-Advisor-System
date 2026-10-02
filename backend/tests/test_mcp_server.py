"""Contract tests for the private MCP endpoint (no DB, no model, no LLM)."""
from __future__ import annotations

import json
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api import mcp_server as m

TOKEN = "t" * 40
ACCEPT = {"accept": "application/json, text/event-stream", "content-type": "application/json"}
DOC_ID = str(uuid4())


def _chunk(text="მუხლი 168. ...", article="168"):
    return {
        "content": text,
        "similarity": 0.81,
        "metadata": {
            "document_id": DOC_ID,
            "title": "საქართველოს საგადასახადო კოდექსი",
            "document_type": "law",
            "source_url": "https://infohub.rs.ge/ka/workspace/document/x",
            "article_ref": article,
        },
    }


@pytest.fixture
def calls():
    return {}


@pytest.fixture
def client(calls, monkeypatch):
    def retrieve(q, lang):
        calls["retrieve"] = (q, lang)
        return [_chunk("A" * 50), _chunk("B" * 10, "169"), _chunk("C", "170")]

    def load_document(doc_id):
        calls["doc"] = doc_id
        return {"document_id": str(doc_id), "title": "T", "full_text": "x" * 2500, "date_published": None}

    def public(q, lang):
        calls["public"] = (q, lang)
        return {"response": "ok", "sources": [], "evidence": {"status": "insufficient"}}

    server = m.build_mcp_server(
        retrieve=retrieve,
        load_document=load_document,
        load_article_chunks=lambda url, forms: calls.setdefault("article", (url, forms)) and [],
        run_public_query=public,
    )
    monkeypatch.setattr(m, "_enrich", lambda s: s)  # registries have their own tests
    app = FastAPI()
    assert m.install_mcp(app, token=TOKEN, allowed_hosts="testserver", server=server)
    with TestClient(app) as c:
        yield c


def rpc(client, method, params=None, headers=None, url="/mcp/"):
    body = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}}
    h = {**ACCEPT, "authorization": f"Bearer {TOKEN}", "mcp-protocol-version": "2025-06-18", **(headers or {})}
    return client.post(url, content=json.dumps(body), headers=h)


def call(client, name, args):
    r = rpc(client, "tools/call", {"name": name, "arguments": args})
    assert r.status_code == 200, r.text
    result = r.json()["result"]
    assert not result.get("isError"), result
    return result["structuredContent"]


def test_disabled_without_token():
    app = FastAPI()
    assert m.install_mcp(app, token="") is False
    assert all(getattr(r, "path", "") != "/mcp" for r in app.routes)


def test_short_token_rejected():
    with pytest.raises(RuntimeError):
        m.install_mcp(FastAPI(), token="short")


@pytest.mark.parametrize("headers", [{}, {"authorization": "Bearer wrong"}, {"x-mcp-token": "t" * 39}])
def test_unauthorized(client, headers):
    h = {**ACCEPT, **headers}
    r = client.post("/mcp/", content="{}", headers=h)
    assert r.status_code == 401


def test_x_mcp_token_header_accepted(client):
    r = rpc(client, "tools/list", headers={"authorization": "", "x-mcp-token": TOKEN})
    assert r.status_code == 200, r.text


def test_foreign_host_rejected(client):
    r = rpc(client, "tools/list", headers={"host": "evil.example"})
    assert r.status_code in (400, 403, 421)


def test_initialize_and_list_tools(client):
    r = rpc(client, "initialize", {
        "protocolVersion": "2025-06-18",
        "capabilities": {},
        "clientInfo": {"name": "pytest", "version": "0"},
    })
    assert r.status_code == 200, r.text
    assert r.json()["result"]["serverInfo"]["name"] == "tax-advisor"
    tools = {t["name"]: t for t in rpc(client, "tools/list").json()["result"]["tools"]}
    assert set(tools) == {"search_corpus", "get_document", "get_official_provision", "ask_tax_advisor"}
    assert tools["search_corpus"]["annotations"]["readOnlyHint"] is True


def test_search_corpus_limits_and_truncates(client, calls):
    out = call(client, "search_corpus", {"query": "დღგ ", "limit": 2, "max_chars_per_chunk": 20})
    assert calls["retrieve"] == ("დღგ", "ka")
    assert out["count"] == 2
    first = out["results"][0]
    assert first["document_id"] == DOC_ID and first["article_ref"] == "168"
    assert first["source_url"].startswith("https://infohub.rs.ge/")
    assert first["relevance"] == 0.81
    # min clamp is 200 chars, so 50 chars fit
    assert first["text"] == "A" * 50 and first["text_truncated"] is False


def test_get_document_pagination(client):
    out = call(client, "get_document", {"document_id": DOC_ID, "max_chars": 1000})
    assert out["total_chars"] == 2500 and out["next_offset"] == 1000 and len(out["text"]) == 1000
    out = call(client, "get_document", {"document_id": DOC_ID, "offset": 2000, "max_chars": 1000})
    assert out["next_offset"] is None and len(out["text"]) == 500


def test_get_document_bad_id_is_tool_error(client):
    r = rpc(client, "tools/call", {"name": "get_document", "arguments": {"document_id": "nope"}})
    assert r.json()["result"]["isError"] is True


def test_ask_tax_advisor_passthrough(client, calls):
    out = call(client, "ask_tax_advisor", {"question": "ставка НДС?"})
    assert calls["public"] == ("ставка НДС?", "ru")
    assert out["evidence"]["status"] == "insufficient"


@pytest.mark.parametrize("raw,key,forms", [
    ("168", "168", ["168"]),
    ("166-1", "166-1", ["166-1", "166¹"]),
    ("166¹", "166-1", ["166-1", "166¹"]),
    (" 82.2 ", "82-2", ["82-2", "82²"]),
])
def test_article_forms(raw, key, forms):
    assert m._article_forms(raw) == (key, forms)


def test_article_forms_rejects_garbage():
    with pytest.raises(ValueError):
        m._article_forms("article 5")


def test_official_provision_uses_verified_registry(client, calls):
    out = call(client, "get_official_provision", {"act": "tax_code", "article": "168"})
    assert out["official_link_verified"] is True
    assert out["official_provision_url"].startswith("https://matsne.gov.ge/ka/document/view/1043717#")
    url, forms = calls["article"]
    assert url.startswith("https://infohub.rs.ge/") and forms == ["168"]
    assert out["corpus_text_found"] is False


def test_official_provision_unknown_article_is_not_verified(client):
    out = call(client, "get_official_provision", {"act": "tax_code", "article": "9999"})
    assert out["official_link_verified"] is False and out["official_provision_url"] is None
    assert out["note"]
