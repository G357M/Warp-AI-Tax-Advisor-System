"""Regression tests for account-plan quota accounting."""

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from core import plans


class FakeRedis:
    def __init__(self):
        self.values = {}

    def incr(self, key):
        self.values[key] = int(self.values.get(key, 0)) + 1
        return self.values[key]

    def decr(self, key):
        self.values[key] = int(self.values.get(key, 0)) - 1
        return self.values[key]

    def expire(self, _key, _seconds):
        return True

    def set(self, key, value, **_kwargs):
        self.values[key] = int(value)
        return True

    def get(self, key):
        return self.values.get(key)


def test_rejected_free_question_does_not_inflate_visible_usage(monkeypatch):
    redis = FakeRedis()
    user = SimpleNamespace(id="free-user")
    monkeypatch.setattr(plans, "_redis", lambda: redis)

    for _ in range(plans.FREE_DAILY_QUESTIONS):
        plans.check_and_count_question(user, "free")

    with pytest.raises(HTTPException) as exc:
        plans.check_and_count_question(user, "free")

    assert exc.value.status_code == 429
    assert plans.questions_used_today(user.id) == plans.FREE_DAILY_QUESTIONS


def test_failed_question_refund_never_leaves_negative_usage(monkeypatch):
    redis = FakeRedis()
    user = SimpleNamespace(id="failed-user")
    monkeypatch.setattr(plans, "_redis", lambda: redis)

    plans.check_and_count_question(user, "free")
    plans.refund_question(user, "free")
    plans.refund_question(user, "free")

    assert plans.questions_used_today(user.id) == 0


def test_paid_questions_do_not_touch_daily_counter(monkeypatch):
    redis = FakeRedis()
    user = SimpleNamespace(id="pro-user")
    monkeypatch.setattr(plans, "_redis", lambda: redis)

    plans.check_and_count_question(user, "pro")
    plans.refund_question(user, "pro")

    assert redis.values == {}
