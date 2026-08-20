"""Regression tests for nightly maintenance queries and Unicode handling."""

from types import SimpleNamespace

from scripts.classify_news_subtypes import news_text_head, pending_news_rows


class _FakeResult:
    def all(self):
        return [SimpleNamespace(id="1", title="title", orig_type=None, full_text="text")]


class _FakeSession:
    def __init__(self):
        self.sql = ""

    def execute(self, statement):
        self.sql = str(statement)
        return _FakeResult()


def test_pending_news_query_fetches_valid_text_before_python_truncation():
    db = _FakeSession()

    rows = pending_news_rows(db, 200)

    assert len(rows) == 1
    assert "full_text" in db.sql
    assert "left(full_text" not in db.sql.lower()
    assert "LIMIT 200" in db.sql


def test_news_text_head_never_splits_multibyte_georgian_characters():
    text = "ა" * 1501

    head = news_text_head(text)

    assert len(head) == 1500
    assert head.encode("utf-8").decode("utf-8") == head
