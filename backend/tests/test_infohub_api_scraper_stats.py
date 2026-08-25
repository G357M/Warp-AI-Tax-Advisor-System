from types import SimpleNamespace

import scraper.infohub_api_scraper as scraper_module
from scraper.infohub_api_scraper import InfoHubAPIScraper, ShortContentRetryCache


class _FakeQuery:
    def __init__(self, known_urls):
        self.known_urls = known_urls
        self.source_url = None

    def filter_by(self, *, source_url):
        self.source_url = source_url
        return self

    def first(self):
        return object() if self.source_url in self.known_urls else None


class _FakeDB:
    def __init__(self, known_urls):
        self.known_urls = known_urls

    def query(self, _column):
        return _FakeQuery(self.known_urls)

    def rollback(self):
        pass

    def close(self):
        pass


class _FakeShortRetryCache:
    def __init__(self, deferred=()):
        self.deferred = set(deferred)
        self.marked = []
        self.cleared = []
        self.error_count = 0

    @staticmethod
    def fingerprint(item):
        return f"fingerprint:{item['uniqueKey']}:{item.get('name', '')}"

    def should_defer(self, _language, _species, unique_key, _fingerprint):
        return unique_key in self.deferred

    def mark_short(self, _language, _species, unique_key, fingerprint):
        self.marked.append((unique_key, fingerprint))

    def clear(self, _language, _species, unique_key):
        self.cleared.append(unique_key)


class _FakeRedis:
    def __init__(self, *, fail_reads=False):
        self.values = {}
        self.expiries = {}
        self.fail_reads = fail_reads
        self.read_calls = 0

    def get(self, key):
        self.read_calls += 1
        if self.fail_reads:
            raise ConnectionError("redis unavailable")
        return self.values.get(key)

    def set(self, key, value, *, ex):
        self.values[key] = value
        self.expiries[key] = ex

    def delete(self, key):
        self.values.pop(key, None)
        self.expiries.pop(key, None)


def test_scraper_reports_known_unseen_ingested_and_short_documents(monkeypatch):
    known_url = "https://infohub.rs.ge/ka/workspace/document/known"
    monkeypatch.setattr(
        scraper_module,
        "SessionLocal",
        lambda: _FakeDB({known_url}),
    )
    short_cache = _FakeShortRetryCache()
    scraper = InfoHubAPIScraper(
        page_size=50,
        delay=0,
        short_retry_cache=short_cache,
    )
    page_calls = []

    def fetch_page(species, skip):
        page_calls.append((species, skip))
        if skip:
            return [], 3
        return [
            {"uniqueKey": "known"},
            {"uniqueKey": "short"},
            {"uniqueKey": "stored"},
        ], 3

    scraper.fetch_page = fetch_page
    scraper.fetch_details = lambda uid: {"uniqueKey": uid}

    def store(detail, _source_url, _db):
        if detail["uniqueKey"] == "short":
            return None
        scraper.documents_scraped += 1
        return SimpleNamespace(id="stored")

    scraper.store = store

    result = scraper.scrape(species_list=["Bill"], max_docs=10)

    assert result["documents_scraped"] == 1
    assert page_calls == [("Bill", 0)]
    assert result["species"]["Bill"] == {
        "source_total": 3,
        "pages_visited": 1,
        "known": 1,
        "unseen": 2,
        "ingested": 1,
        "skipped_short": 1,
        "deferred_short": 0,
        "short_cache_errors": 0,
        "detail_failures": 0,
        "processing_errors": 0,
    }
    assert [item[0] for item in short_cache.marked] == ["short"]
    assert short_cache.cleared == ["stored"]


def test_scraper_stops_when_the_page_is_fully_known(monkeypatch):
    known_url = "https://infohub.rs.ge/ka/workspace/document/known"
    monkeypatch.setattr(
        scraper_module,
        "SessionLocal",
        lambda: _FakeDB({known_url}),
    )
    scraper = InfoHubAPIScraper(
        page_size=50,
        delay=0,
        short_retry_cache=_FakeShortRetryCache(),
    )
    calls = []

    def fetch_page(species, skip):
        calls.append((species, skip))
        return [{"uniqueKey": "known"}], 1

    scraper.fetch_page = fetch_page

    result = scraper.scrape(species_list=["NewDocument"], max_docs=10)

    assert calls == [("NewDocument", 0)]
    assert result["species"]["NewDocument"]["known"] == 1
    assert result["species"]["NewDocument"]["unseen"] == 0


def test_unchanged_short_card_is_deferred_without_detail_fetch(monkeypatch):
    monkeypatch.setattr(scraper_module, "SessionLocal", lambda: _FakeDB(set()))
    short_cache = _FakeShortRetryCache(deferred={"short"})
    scraper = InfoHubAPIScraper(
        page_size=50,
        delay=0,
        short_retry_cache=short_cache,
    )
    scraper.fetch_page = lambda _species, _skip: ([{"uniqueKey": "short"}], 1)
    scraper.fetch_details = lambda _uid: (_ for _ in ()).throw(
        AssertionError("deferred card must not fetch detail")
    )
    scraper.store = lambda *_args: (_ for _ in ()).throw(
        AssertionError("deferred card must not reach storage")
    )

    result = scraper.scrape(species_list=["Bill"], max_docs=10)

    assert result["documents_scraped"] == 0
    assert result["species"]["Bill"]["unseen"] == 1
    assert result["species"]["Bill"]["deferred_short"] == 1
    assert result["species"]["Bill"]["skipped_short"] == 0


def test_retry_cache_uses_fingerprint_ttl_and_changed_card_rechecks():
    redis_client = _FakeRedis()
    cache = ShortContentRetryCache(
        client=redis_client,
        retry_seconds=1234,
        enabled=True,
    )
    unique_key = "candidate-uuid-123"
    original = {"uniqueKey": unique_key, "name": "Draft"}
    changed = {"uniqueKey": unique_key, "name": "Draft with text"}
    original_fingerprint = cache.fingerprint(original)

    cache.mark_short("ka", "Bill", unique_key, original_fingerprint)

    assert cache.should_defer("ka", "Bill", unique_key, original_fingerprint)
    assert not cache.should_defer(
        "ka", "Bill", unique_key, cache.fingerprint(changed)
    )
    assert set(redis_client.expiries.values()) == {1234}
    assert all(unique_key not in key for key in redis_client.values)

    cache.clear("ka", "Bill", unique_key)
    assert redis_client.values == {}


def test_retry_cache_failure_is_single_attempt_and_fail_open():
    redis_client = _FakeRedis(fail_reads=True)
    cache = ShortContentRetryCache(client=redis_client, enabled=True)

    assert not cache.should_defer("ka", "Bill", "one", "fingerprint")
    assert not cache.should_defer("ka", "Bill", "two", "fingerprint")
    assert cache.error_count == 1
    assert redis_client.read_calls == 1


def test_scraper_reports_cache_error_but_still_ingests(monkeypatch):
    monkeypatch.setattr(scraper_module, "SessionLocal", lambda: _FakeDB(set()))
    cache = ShortContentRetryCache(
        client=_FakeRedis(fail_reads=True),
        enabled=True,
    )
    scraper = InfoHubAPIScraper(
        page_size=50,
        delay=0,
        short_retry_cache=cache,
    )
    scraper.fetch_page = lambda _species, _skip: ([{"uniqueKey": "stored"}], 1)
    scraper.fetch_details = lambda uid: {"uniqueKey": uid}

    def store(_detail, _source_url, _db):
        scraper.documents_scraped += 1
        return SimpleNamespace(id="stored")

    scraper.store = store

    result = scraper.scrape(species_list=["NewDocument"], max_docs=10)

    assert result["documents_scraped"] == 1
    assert result["species"]["NewDocument"]["ingested"] == 1
    assert result["species"]["NewDocument"]["short_cache_errors"] == 1
