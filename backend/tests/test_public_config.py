"""The admin config view exposes a fixed whitelist and never a secret value."""
import json
import re
from types import SimpleNamespace

from pydantic import SecretStr

from core.config import Settings
from core.public_config import PUBLIC_CONFIG, SECRET_PRESENCE, public_config

SECRET_NAME = re.compile(r"SECRET|PASSWORD|KEY|TOKEN")


def fake_source(**overrides):
    values = {name: f"value-{name}" for keys in PUBLIC_CONFIG.values() for name in keys}
    values.update({name: SecretStr(f"leak-{name}-0123456789") for name in SECRET_PRESENCE})
    values.update(overrides)
    return SimpleNamespace(**values)


def test_secret_values_never_appear():
    source = fake_source()
    payload = json.dumps(public_config(source), default=str)
    for name in SECRET_PRESENCE:
        assert f"leak-{name}" not in payload
    assert public_config(source)["secrets"] == {name: True for name in SECRET_PRESENCE}


def test_missing_or_blank_secrets_are_false():
    source = fake_source(OPENAI_API_KEY=None, SMTP_PASSWORD=SecretStr("   "), TBC_API_KEY="")
    secrets = public_config(source)["secrets"]
    assert secrets["OPENAI_API_KEY"] is False and secrets["SMTP_PASSWORD"] is False and secrets["TBC_API_KEY"] is False


def test_whitelist_contains_no_secret_named_settings():
    exposed = {name for keys in PUBLIC_CONFIG.values() for name in keys}
    secret_fields = {name for name in Settings.model_fields if SECRET_NAME.search(name)}
    assert exposed.isdisjoint(secret_fields)
    assert set(SECRET_PRESENCE) <= set(Settings.model_fields)
    assert exposed <= set(Settings.model_fields)


def test_free_quota_is_reported():
    assert public_config(fake_source())["billing"]["FREE_DAILY_QUESTIONS"] == 5
