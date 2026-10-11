"""Admin client management (search, card, account actions) on real PostgreSQL."""
import os
from datetime import timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from api.routes import admin_users as routes
from core.config import settings
from core.database import Base, engine
from core.time_utils import utc_now
from models import (AdminAuditLog, BillingCheckout, Conversation, Feedback, Message, Payment,
                    Subscription, User)
from models.user import AuthActionToken
from scripts.add_admin_audit_log import apply_schema

pytestmark = pytest.mark.skipif(os.getenv("BILLING_PROVIDER_POSTGRES_TESTS") != "1",
                                reason="requires dedicated PostgreSQL")

TABLES = [User, AuthActionToken, Subscription, Payment, BillingCheckout, Feedback, Conversation, Message]


@pytest.fixture
def database():
    schema = "admin_users_test_" + uuid4().hex
    with engine.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    local = create_engine(settings.DATABASE_URL, connect_args={"options": f"-csearch_path={schema},public"},
                          execution_options={"schema_translate_map": {None: schema}})
    Base.metadata.create_all(local, tables=[m.__table__ for m in TABLES])
    with local.begin() as conn:
        apply_schema(conn)
    sessions = sessionmaker(bind=local, autoflush=False)
    with sessions() as db:
        admin = User(email="boss@example.test", username="boss", password_hash="x", role="admin",
                     email_verified_at=utc_now())
        db.add(admin)
        db.commit()
        ids = SimpleNamespace(admin_id=admin.id)
    yield sessions, ids
    local.dispose()
    # The identifier is generated here, never supplied by an environment/user.
    with engine.begin() as conn:
        conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))


def _user(db, username, *, email=None, full_name=None, role="user", active=True, verified=True,
          created_days_ago=0, last_login_days_ago=None):
    now = utc_now()
    user = User(email=email or f"{username}@example.test", username=username, password_hash="x",
                full_name=full_name, role=role, is_active=active,
                email_verified_at=now if verified else None,
                created_at=now - timedelta(days=created_days_ago),
                last_login=None if last_login_days_ago is None else now - timedelta(days=last_login_days_ago))
    db.add(user)
    db.flush()
    return user


def _sub(db, user, plan, *, status="active", days=30, provider="manual"):
    now = utc_now()
    sub = Subscription(user_id=user.id, plan=plan, status=status, period_start=now,
                       period_end=None if days is None else now + timedelta(days=days),
                       payment_provider=provider)
    db.add(sub)
    db.flush()
    return sub


def _list(sessions, **kwargs):
    params = {"q": None, "plan": None, "status": None, "sort": "created_desc", "limit": 50, "offset": 0}
    params.update(kwargs)
    with sessions() as db:
        return routes.list_users(db=db, **params)


def _names(page):
    return [row["username"] for row in page["items"]]


def test_search_matches_email_username_and_full_name_case_insensitively(database):
    sessions, _ = database
    with sessions() as db:
        _user(db, "alpha", email="Owner@Acme.ge")
        _user(db, "beta", full_name="Nino Beridze")
        _user(db, "gamma")
        db.commit()
    assert _names(_list(sessions, q="acme")) == ["alpha"]
    assert _names(_list(sessions, q="  BERIDZE ")) == ["beta"]
    assert _names(_list(sessions, q="gam")) == ["gamma"]
    page = _list(sessions, q="a", limit=1)
    # "a" is in alpha, beta, gamma and boss@example.test
    assert page["total"] == 4 and len(page["items"]) == 1


def test_search_treats_like_wildcards_literally(database):
    sessions, _ = database
    with sessions() as db:
        _user(db, "under_score")
        _user(db, "underXscore")
        _user(db, "pct", full_name="100% done")
        _user(db, "slash", full_name="back\\slash")
        db.commit()
    assert _names(_list(sessions, q="under_")) == ["under_score"]
    assert _names(_list(sessions, q="100%")) == ["pct"]
    assert _names(_list(sessions, q="k\\s")) == ["slash"]


def test_plan_filter_uses_effective_plan(database):
    sessions, _ = database
    with sessions() as db:
        _sub(db, _user(db, "paid-pro"), "pro")
        _sub(db, _user(db, "unlimited-pro"), "pro", days=None)
        _sub(db, _user(db, "expired-pro"), "pro", days=-1)
        _sub(db, _user(db, "canceled-biz"), "business", status="canceled")
        _sub(db, _user(db, "paid-biz"), "business")
        _user(db, "nobody")
        db.commit()
    assert sorted(_names(_list(sessions, plan="pro"))) == ["paid-pro", "unlimited-pro"]
    assert sorted(_names(_list(sessions, plan="business"))) == ["boss", "paid-biz"]
    assert sorted(_names(_list(sessions, plan="free"))) == ["canceled-biz", "expired-pro", "nobody"]
    rows = {r["username"]: r for r in _list(sessions)["items"]}
    assert rows["boss"]["plan"] == "business" and rows["expired-pro"]["plan"] == "free"


def test_expiring_filter_is_paid_non_admin_within_seven_days(database):
    sessions, ids = database
    with sessions() as db:
        _sub(db, _user(db, "soon"), "pro", days=6)
        _sub(db, _user(db, "later"), "pro", days=8)
        _sub(db, _user(db, "gone"), "pro", days=-1)
        _sub(db, _user(db, "free-sub"), "free", days=3)
        _sub(db, db.get(User, ids.admin_id), "business", days=2)
        db.commit()
    assert _names(_list(sessions, plan="expiring")) == ["soon"]


def test_status_filters(database):
    sessions, _ = database
    with sessions() as db:
        _user(db, "blocked-one", active=False)
        _user(db, "unverified-one", verified=False)
        _user(db, "fine")
        db.commit()
    assert _names(_list(sessions, status="blocked")) == ["blocked-one"]
    assert _names(_list(sessions, status="unverified")) == ["unverified-one"]
    assert _names(_list(sessions, status="admin")) == ["boss"]
    assert "blocked-one" not in _names(_list(sessions, status="active"))
    rows = {r["username"]: r for r in _list(sessions)["items"]}
    assert rows["blocked-one"]["is_active"] is False and rows["unverified-one"]["email_verified"] is False


def test_sorts_put_empty_values_last(database):
    sessions, _ = database
    with sessions() as db:
        _user(db, "old", created_days_ago=10, last_login_days_ago=1)
        _user(db, "new", created_days_ago=1, last_login_days_ago=5)
        _user(db, "never", created_days_ago=5)
        _sub(db, db.query(User).filter_by(username="old").one(), "pro", days=40)
        _sub(db, db.query(User).filter_by(username="new").one(), "pro", days=3)
        db.commit()
    by_created = _names(_list(sessions, q="e", sort="created_desc"))
    assert by_created.index("new") < by_created.index("never") < by_created.index("old")
    by_login = _names(_list(sessions, q="e", sort="last_login_desc"))
    assert by_login[:2] == ["old", "new"] and set(by_login[2:]) == {"never", "boss"}
    by_end = _names(_list(sessions, q="e", sort="period_end_asc"))
    assert by_end[:2] == ["new", "old"]


def _card(sessions, user_id):
    with sessions() as db:
        return routes.get_user_card(user_id, db)


def test_card_has_profile_subscription_payments_checkouts_and_activity(database, monkeypatch):
    sessions, _ = database
    from core import admin_users as core_users
    monkeypatch.setattr(core_users, "questions_used_today_or_none", lambda _uid: 2)
    now = utc_now()
    with sessions() as db:
        user = _user(db, "carded", full_name="Card Holder")
        sub = _sub(db, user, "pro", days=10, provider="grant")
        db.add(Payment(subscription_id=sub.id, amount_gel=49, amount_minor=4900, currency="GEL",
                       provider="manual", status="succeeded"))
        db.add(BillingCheckout(user_id=user.id, plan="pro", months=1, amount_minor=4900, currency="GEL",
                               provider="manual", status="pending", idempotency_key=uuid4().hex,
                               expires_at=now + timedelta(hours=1)))
        recent = Conversation(user_id=user.id, created_at=now - timedelta(days=2))
        older = Conversation(user_id=user.id, created_at=now - timedelta(days=20))
        db.add_all([recent, older])
        db.flush()
        db.add_all([Message(conversation_id=recent.id, role="user", content="q1", created_at=now - timedelta(days=2)),
                    Message(conversation_id=recent.id, role="assistant", content="a1", created_at=now - timedelta(days=2)),
                    Message(conversation_id=older.id, role="user", content="q2", created_at=now - timedelta(days=20)),
                    Feedback(user_id=user.id, message="hi")])
        db.commit()
        user_id = user.id
    card = _card(sessions, user_id)
    assert card["profile"]["username"] == "carded" and card["profile"]["full_name"] == "Card Holder"
    assert card["profile"]["effective_plan"] == "pro" and card["profile"]["is_active"] is True
    assert card["subscription"]["source"] == "grant" and card["subscription"]["days_left"] in (9, 10)
    assert len(card["payments"]) == 1 and card["payments"][0]["amount_minor"] == 4900
    assert card["checkouts"][0]["status"] == "pending"
    assert card["activity"] == {"conversations_7d": 1, "conversations_30d": 2, "questions_7d": 1,
                                "questions_30d": 2, "questions_today": 2, "daily_limit": None,
                                "feedback_total": 1}


def test_card_without_subscription_or_redis(database, monkeypatch):
    sessions, ids = database
    from core import admin_users as core_users
    monkeypatch.setattr(core_users, "questions_used_today_or_none", lambda _uid: None)
    with sessions() as db:
        user = _user(db, "freebie")
        db.commit()
        user_id = user.id
    card = _card(sessions, user_id)
    assert card["subscription"] is None and card["profile"]["effective_plan"] == "free"
    assert card["activity"]["questions_today"] is None and card["activity"]["daily_limit"] == 5
    assert _card(sessions, ids.admin_id)["profile"]["effective_plan"] == "business"


def test_card_for_expired_subscription_has_no_days_left(database):
    sessions, _ = database
    with sessions() as db:
        user = _user(db, "lapsed")
        _sub(db, user, "pro", days=-3)
        db.commit()
        user_id = user.id
    card = _card(sessions, user_id)
    assert card["subscription"]["plan"] == "pro" and card["subscription"]["days_left"] is None
    assert card["profile"]["effective_plan"] == "free"


def test_card_for_missing_user_is_coded_404(database):
    sessions, _ = database
    with pytest.raises(HTTPException) as exc:
        _card(sessions, uuid4())
    assert exc.value.status_code == 404 and exc.value.detail["code"] == "user_not_found"
