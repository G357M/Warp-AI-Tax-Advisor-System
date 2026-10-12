"""Unit tests for the per-user answer-rating limiter (no real Redis)."""
from datetime import datetime

from api.routes import query


class FakeRedis:
    def __init__(self):
        self.counts = {}
        self.expires = []

    def incr(self, key):
        self.counts[key] = self.counts.get(key, 0) + 1
        return self.counts[key]

    def expire(self, key, seconds):
        self.expires.append((key, seconds))


def _use(monkeypatch, client):
    monkeypatch.setattr(query, "_redis", lambda: client)
    monkeypatch.setattr(query, "utc_now", lambda: datetime(2026, 10, 12, 9, 30))


def test_limit_trips_on_the_sixty_first_call(monkeypatch):
    client = FakeRedis()
    _use(monkeypatch, client)
    results = [query.rating_rate_limited("u-1") for _ in range(61)]
    assert results[:60] == [False] * 60
    assert results[60] is True


def test_expire_is_set_only_on_the_first_increment(monkeypatch):
    client = FakeRedis()
    _use(monkeypatch, client)
    for _ in range(5):
        query.rating_rate_limited("u-1")
    assert client.expires == [("rating:u-1:2026101209", 3600)]


def test_key_is_per_user_and_hour(monkeypatch):
    client = FakeRedis()
    _use(monkeypatch, client)
    query.rating_rate_limited("u-1")
    query.rating_rate_limited("u-2")
    assert set(client.counts) == {"rating:u-1:2026101209", "rating:u-2:2026101209"}


def test_no_redis_means_no_limit(monkeypatch):
    _use(monkeypatch, None)
    assert query.rating_rate_limited("u-1") is False


def test_redis_errors_mean_no_limit(monkeypatch):
    class Broken:
        def incr(self, key):
            raise RuntimeError("redis down")

    _use(monkeypatch, Broken())
    assert query.rating_rate_limited("u-1") is False
