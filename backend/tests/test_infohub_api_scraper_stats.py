from types import SimpleNamespace

import scraper.infohub_api_scraper as scraper_module
from scraper.infohub_api_scraper import InfoHubAPIScraper


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


def test_scraper_reports_known_unseen_ingested_and_short_documents(monkeypatch):
    known_url = "https://infohub.rs.ge/ka/workspace/document/known"
    monkeypatch.setattr(
        scraper_module,
        "SessionLocal",
        lambda: _FakeDB({known_url}),
    )
    scraper = InfoHubAPIScraper(page_size=50, delay=0)
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
        "detail_failures": 0,
        "processing_errors": 0,
    }


def test_scraper_stops_when_the_page_is_fully_known(monkeypatch):
    known_url = "https://infohub.rs.ge/ka/workspace/document/known"
    monkeypatch.setattr(
        scraper_module,
        "SessionLocal",
        lambda: _FakeDB({known_url}),
    )
    scraper = InfoHubAPIScraper(page_size=50, delay=0)
    calls = []

    def fetch_page(species, skip):
        calls.append((species, skip))
        return [{"uniqueKey": "known"}], 1

    scraper.fetch_page = fetch_page

    result = scraper.scrape(species_list=["NewDocument"], max_docs=10)

    assert calls == [("NewDocument", 0)]
    assert result["species"]["NewDocument"]["known"] == 1
    assert result["species"]["NewDocument"]["unseen"] == 0
