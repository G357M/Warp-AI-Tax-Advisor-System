"""record_admin_action validates input and never commits."""
from types import SimpleNamespace
from uuid import uuid4

import pytest

from core.admin_audit import ADMIN_ACTIONS, REASON_MAX_LENGTH, record_admin_action


class FakeSession:
    def __init__(self):
        self.added, self.flushed, self.committed = [], 0, 0

    def add(self, obj):
        self.added.append(obj)

    def flush(self):
        self.flushed += 1

    def commit(self):  # pragma: no cover - must never be called
        self.committed += 1


def actor():
    return SimpleNamespace(id=uuid4())


def test_records_entry_without_commit():
    db, admin, target = FakeSession(), actor(), uuid4()
    entry = record_admin_action(db, actor=admin, action="user.role_changed", target_type="user",
                                target_id=target, before={"role": "user"}, after={"role": "admin"},
                                reason="  promote  ")
    assert db.added == [entry] and db.flushed == 1 and db.committed == 0
    assert entry.actor_id == admin.id and entry.target_id == str(target)
    assert entry.before == {"role": "user"} and entry.after == {"role": "admin"}
    assert entry.reason == "promote"


@pytest.mark.parametrize("reason", [None, "", "   \n\t"])
def test_blank_reason_is_null(reason):
    entry = record_admin_action(FakeSession(), actor=actor(), action="feedback.status_changed",
                                target_type="feedback", target_id=uuid4(), reason=reason)
    assert entry.reason is None


def test_reason_is_truncated():
    entry = record_admin_action(FakeSession(), actor=actor(), action="feedback.status_changed",
                                target_type="feedback", target_id=uuid4(), reason="x" * 1500)
    assert len(entry.reason) == REASON_MAX_LENGTH == 1000


def test_unknown_action_and_target_are_rejected():
    with pytest.raises(ValueError):
        record_admin_action(FakeSession(), actor=actor(), action="user.deleted", target_type="user", target_id=uuid4())
    with pytest.raises(ValueError):
        record_admin_action(FakeSession(), actor=actor(), action="user.role_changed", target_type="org", target_id=uuid4())


def test_action_set_is_closed():
    assert ADMIN_ACTIONS == {"user.role_changed", "subscription.activated", "feedback.status_changed"}
